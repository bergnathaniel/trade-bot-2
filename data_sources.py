"""
Data sources for discovering "graduated" tokens and their live prices.

MockDataSource: fully synthetic, works right now with zero setup. Use this
                 to test the strategy logic in paper mode.

LiveDataSource: real feed. Graduation events come from PumpPortal's free
                 WebSocket API (pumpportal.fun/data-api) — an unofficial,
                 third-party feed since pump.fun has no official public API.
                 Token metadata/liquidity/holder data and prices come from
                 Jupiter's Token API v2 and Price API v3 (developers.jup.ag).
                 Both are unofficial-ish or fast-moving surfaces — schemas
                 aren't guaranteed stable, so this parses defensively and
                 logs+skips anything it can't understand instead of crashing.
"""

import json
import os
import queue
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import certifi
import requests
import websocket

from config import Config


@dataclass
class TokenCandidate:
    symbol: str
    mint: str
    graduated_at: float          # unix timestamp
    liquidity_usd: float
    holder_count: int
    top_wallet_pct: float
    renounced: bool
    lp_locked: bool
    # "Real research" signals from Jupiter's Token API (not in the original stub):
    organic_score: float         # Jupiter's own anti-wash-trading signal, 0-100 continuous
    price_change_5m_pct: float   # negative = actively dumping right now, not just noisy
    price_change_1h_pct: float   # same, over a longer window — catches a 5m bounce inside
                                  # a real 1h collapse
    num_organic_buyers_5m: int   # Jupiter's count of buyers it doesn't think are wash-trading
                                  # bots — real distinct human-looking demand, not just volume
    dev_mints: int               # how many other tokens this same wallet has created — a
                                  # high count is a real signal for a serial rug-factory dev


@dataclass
class PriceTick:
    mint: str
    price_usd: float
    timestamp: float


class MockDataSource:
    """Synthetic graduation events + random-walk prices, for paper testing."""

    def __init__(self, seed: Optional[int] = None):
        self.rng = random.Random(seed)
        self._active_tokens: dict[str, dict] = {}
        self._next_id = 0

    def poll_new_graduations(self) -> list[TokenCandidate]:
        """Randomly spawns 0-2 new 'graduated' tokens per call."""
        out = []
        n = self.rng.choices([0, 1, 2], weights=[70, 25, 5])[0]
        for _ in range(n):
            self._next_id += 1
            mint = f"MOCK{self._next_id:05d}"
            candidate = TokenCandidate(
                symbol=f"TKN{self._next_id}",
                mint=mint,
                graduated_at=time.time(),
                liquidity_usd=self.rng.uniform(1500, 15000),
                holder_count=self.rng.randint(10, 200),
                top_wallet_pct=self.rng.uniform(2, 35),
                renounced=self.rng.random() > 0.2,
                lp_locked=self.rng.random() > 0.3,
                organic_score=self.rng.uniform(0, 100),
                price_change_5m_pct=self.rng.uniform(-30, 30),
                price_change_1h_pct=self.rng.uniform(-50, 50),
                num_organic_buyers_5m=self.rng.randint(0, 20),
                dev_mints=self.rng.randint(1, 10),
            )
            start_price = self.rng.uniform(0.00001, 0.01)
            self._active_tokens[mint] = {
                "price": start_price,
                "drift": self.rng.uniform(-0.15, 0.20),  # bias per tick, mimics early volatility
                "vol": self.rng.uniform(0.03, 0.12),
            }
            out.append(candidate)
        return out

    def get_price(self, mint: str) -> Optional[PriceTick]:
        state = self._active_tokens.get(mint)
        if not state:
            return None
        shock = self.rng.gauss(state["drift"] * 0.1, state["vol"])
        state["price"] = max(state["price"] * (1 + shock), 1e-12)
        return PriceTick(mint=mint, price_usd=state["price"], timestamp=time.time())


class LiveDataSource:
    """
    Real graduation feed (PumpPortal WebSocket, subscribeMigration) enriched
    with Jupiter's Token API v2 (liquidity/holders/audit) and priced via
    Jupiter's Price API v3. Requires JUPITER_API_KEY (free at portal.jup.ag).
    """

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg or Config()
        self.jupiter_api_key = os.environ.get("JUPITER_API_KEY")
        if not self.jupiter_api_key:
            print("[LiveDataSource] JUPITER_API_KEY not set — using Jupiter's unauthenticated "
                  "free tier (works, but more rate-limited). Get a key at https://portal.jup.ag.")
        self.session = requests.Session()
        self._events: "queue.Queue[dict]" = queue.Queue()
        self._seen_mints: set[str] = set()
        self._pending: list = []  # [(ready_at_timestamp, mint), ...]
        self._stop = threading.Event()
        self._ws_thread = threading.Thread(target=self._run_ws, daemon=True)
        self._ws_thread.start()
        time.sleep(1)  # give the socket a moment to connect before the first poll

    def _headers(self) -> dict:
        return {"x-api-key": self.jupiter_api_key} if self.jupiter_api_key else {}

    # ---------- websocket plumbing ----------

    def _run_ws(self):
        while not self._stop.is_set():
            try:
                ws = websocket.WebSocketApp(
                    self.cfg.pumpportal_ws_url,
                    on_open=self._on_open,
                    on_message=self._on_message,
                    on_error=lambda ws, err: print(f"[LiveDataSource] websocket error: {err}"),
                )
                # macOS python.org builds ship an empty default CA bundle, which makes
                # wss:// fail with CERTIFICATE_VERIFY_FAILED unless pointed at certifi's.
                ws.run_forever(ping_interval=30, sslopt={"ca_certs": certifi.where()})
            except Exception as e:
                print(f"[LiveDataSource] websocket crashed: {e}")
            if not self._stop.is_set():
                print("[LiveDataSource] reconnecting in 5s...")
                time.sleep(5)

    def _on_open(self, ws):
        ws.send(json.dumps({"method": "subscribeMigration"}))
        print("[LiveDataSource] subscribed to pump.fun migration events")

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            return
        self._events.put(data)

    def close(self):
        self._stop.set()

    # ---------- candidate discovery ----------
    #
    # A migration event fires the instant a token graduates — at that moment
    # Jupiter's indexer often hasn't priced the new pool yet (liquidity comes
    # back as 0) and almost nobody has bought in yet (holder count in single
    # digits). Judging entry filters against that snapshot rejects nearly
    # everything for being "too new", not for being bad. So new mints sit in
    # a buffer for candidate_evaluation_delay_seconds before we fetch info
    # and actually run the filters — giving the pool and the indexer a beat
    # to catch up to reality first.

    def poll_new_graduations(self) -> list[TokenCandidate]:
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            mint = event.get("mint") or event.get("ca") or event.get("contractAddress")
            if not mint:
                continue  # non-candidate messages, e.g. the subscription ack
            if mint in self._seen_mints:
                continue
            self._seen_mints.add(mint)
            ready_at = time.time() + self.cfg.candidate_evaluation_delay_seconds
            self._pending.append((ready_at, mint))

        out = []
        still_pending = []
        now = time.time()
        for ready_at, mint in self._pending:
            if now >= ready_at:
                candidate = self._build_candidate(mint)
                if candidate:
                    out.append(candidate)
            else:
                still_pending.append((ready_at, mint))
        self._pending = still_pending
        return out

    def _build_candidate(self, mint: str) -> Optional[TokenCandidate]:
        info = self._fetch_token_info(mint)
        if not info:
            return None

        audit = info.get("audit") or {}
        stats5m = info.get("stats5m") or {}
        stats1h = info.get("stats1h") or {}
        return TokenCandidate(
            symbol=info.get("symbol", "?"),
            mint=mint,
            graduated_at=time.time(),
            liquidity_usd=float(info.get("liquidity") or 0.0),
            holder_count=int(info.get("holderCount") or 0),
            # missing/unknown data defaults to the *conservative* (fails-a-filter) side
            top_wallet_pct=float(audit.get("topHoldersPercentage", 100.0)),
            renounced=bool(audit.get("mintAuthorityDisabled")) and bool(audit.get("freezeAuthorityDisabled")),
            # pump.fun's bonding-curve migration burns the LP position automatically
            # as part of the protocol — true for pump.fun-origin graduations specifically,
            # not a general guarantee. Re-verify if this ever points at another source.
            lp_locked=True,
            organic_score=float(info.get("organicScore") or 0.0),
            price_change_5m_pct=float(stats5m.get("priceChange", -100.0)),
            price_change_1h_pct=float(stats1h.get("priceChange", -100.0)),
            num_organic_buyers_5m=int(stats5m.get("numOrganicBuyers") or 0),
            dev_mints=int(audit.get("devMints", 999)),
        )

    def _fetch_token_info(self, mint: str) -> Optional[dict]:
        try:
            r = self.session.get(
                self.cfg.jupiter_token_info_base_url,
                params={"query": mint},
                headers=self._headers(),
                timeout=10,
            )
            r.raise_for_status()
            results = r.json()
            if not results:
                return None
            for item in results:
                if item.get("id") == mint:
                    return item
            return results[0]
        except Exception as e:
            print(f"[LiveDataSource] token info lookup failed for {mint}: {e}")
            return None

    # ---------- pricing ----------

    def get_price(self, mint: str) -> Optional[PriceTick]:
        try:
            r = self.session.get(
                self.cfg.jupiter_price_base_url,
                params={"ids": mint},
                headers=self._headers(),
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            if mint not in data:
                return None  # Jupiter omits tokens it has no reliable price for
            return PriceTick(mint=mint, price_usd=float(data[mint]["usdPrice"]), timestamp=time.time())
        except Exception as e:
            print(f"[LiveDataSource] price lookup failed for {mint}: {e}")
            return None
