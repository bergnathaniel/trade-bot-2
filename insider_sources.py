"""
On-chain data layer for the insider copy-trade bot.

MockInsiderSource : no network. Synthetic wallets + tokens, for paper mode.
LiveInsiderSource : real data. Uses Helius' Enhanced Transactions REST API
                    (https://docs.helius.dev) for wallet/token history and
                    Jupiter's Price/Token APIs (same as data_sources.py) for
                    prices and metadata.

The Helius api-key is read straight out of HELIUS_RPC_URL (…/?api-key=XXX),
so you only ever configure the RPC URL once (already needed for bot.py live
mode). Everything here parses defensively: unknown/rate-limited responses are
logged and skipped, never crash the loop.
"""

import os
import random
import statistics
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse, parse_qs

import requests

from insider_config import InsiderConfig


class _Throttle:
    """Minimum spacing between calls to a rate-limited host (Jupiter free tier
    is ~1 req/s). Shared process-wide so discovery and pricing don't collide."""

    def __init__(self, min_interval_s: float):
        self.min_interval = min_interval_s
        self._last = 0.0

    def wait(self):
        gap = time.time() - self._last
        if gap < self.min_interval:
            time.sleep(self.min_interval - gap)
        self._last = time.time()


_JUPITER_THROTTLE = _Throttle(1.1)


# --------------------------------------------------------------------------
# shared value objects
# --------------------------------------------------------------------------

@dataclass
class SwapEvent:
    signature: str
    timestamp: float
    wallet: str
    action: str          # "buy" or "sell" (of `mint`, paying/receiving SOL or USDC)
    mint: str
    token_amount: float
    usd_value: float


@dataclass
class WalletStats:
    wallet: str
    tokens_tracked: int = 0
    hit_rate: float = 0.0            # fraction of bought tokens that reached >= 2x
    median_multiple: float = 0.0
    best_multiple: float = 0.0
    early_wins: int = 0             # early entries into >= winner_min_multiple tokens
    first_seen_ts: float = 0.0
    last_trade_ts: float = 0.0      # most recent swap we can see — powers recency scoring
    score: float = 0.0
    note: str = ""


@dataclass
class CopySignal:
    mint: str
    symbol: str
    wallets: list          # followed wallets that bought it inside the window
    first_buy_ts: float
    insider_usd: float     # total USD the followed wallets put in
    token_age_minutes: float
    liquidity_usd: float
    holder_count: int
    price_change_1h_pct: float
    price_usd: float
    insider_avg_entry_usd: float = 0.0   # avg price the insiders paid, for the
                                         # "don't be exit liquidity" check
    conviction: float = 0.0              # summed watchlist score of the buyers
    # "research the coin" fields
    price_change_5m_pct: float = 0.0
    num_organic_buyers_5m: int = 0
    organic_score: float = 0.0
    liquidity_change_1h_pct: float = 0.0


# --------------------------------------------------------------------------
# MOCK — paper mode
# --------------------------------------------------------------------------

class MockInsiderSource:
    """Synthetic wallets/tokens. Deterministic-ish via seed."""

    def __init__(self, cfg: InsiderConfig, seed: Optional[int] = None):
        self.cfg = cfg
        self.rng = random.Random(seed)
        self._tokens: dict[str, dict] = {}
        self._id = 0
        # a fixed roster of fake "insider" wallets with baked-in skill levels
        self._wallets = [f"InsiderWallet{i:02d}" for i in range(8)]
        self._skill = {w: self.rng.uniform(0.3, 0.8) for w in self._wallets}

    # ---- discovery ----
    def find_winner_mints(self) -> list[str]:
        return [f"WINNER{i}" for i in range(6)]

    def early_buyers_of(self, mint: str) -> list[tuple]:
        n = self.rng.randint(3, 6)
        return [(self.rng.choice(self._wallets), time.time() - self.rng.uniform(60, 3600), self.rng.uniform(1e-6, 1e-4))
                for _ in range(n)]

    def wallet_stats(self, wallet: str) -> Optional[WalletStats]:
        skill = self._skill.get(wallet, 0.4)
        multiples = [max(0.05, self.rng.lognormvariate(skill, 0.9)) for _ in range(self.rng.randint(6, 30))]
        wins = [m for m in multiples if m >= 2]
        return WalletStats(
            wallet=wallet,
            tokens_tracked=len(multiples),
            hit_rate=len(wins) / len(multiples),
            median_multiple=statistics.median(multiples),
            best_multiple=max(multiples),
            early_wins=sum(1 for m in multiples if m >= self.cfg.winner_min_multiple),
            first_seen_ts=time.time() - self.rng.uniform(5, 200) * 86400,
            last_trade_ts=time.time() - self.rng.uniform(0, 10) * 86400,
        )

    # ---- live tracking ----
    def poll_new_graduations(self):  # not used; kept for symmetry
        return []

    def recent_buys(self, wallet: str, since_ts: float) -> list[SwapEvent]:
        out = []
        if self.rng.random() < 0.15:  # occasionally a watched wallet buys something
            self._id += 1
            mint = f"MOCKTOK{self._id:04d}"
            self._tokens[mint] = {
                "price": self.rng.uniform(1e-6, 5e-5),
                "drift": self.rng.uniform(-0.1, 0.25),
                "vol": self.rng.uniform(0.04, 0.14),
                "born": time.time() - self.rng.uniform(0, 90) * 60,
                "holders": self.rng.randint(20, 400),
                "liq": self.rng.uniform(2000, 20000),
            }
            out.append(SwapEvent(
                signature=f"sig{self._id}", timestamp=time.time(), wallet=wallet,
                action="buy", mint=mint, token_amount=self.rng.uniform(1e5, 1e7),
                usd_value=self.rng.uniform(80, 600),
            ))
        return out

    def token_info(self, mint: str) -> Optional[dict]:
        t = self._tokens.get(mint)
        if not t:
            return None
        return {
            "symbol": mint[-4:],
            "age_minutes": (time.time() - t["born"]) / 60,
            "liquidity_usd": t["liq"],
            "holder_count": t["holders"],
            "price_change_1h_pct": self.rng.uniform(-20, 120),
            "price_change_5m_pct": self.rng.uniform(-15, 25),
            "num_organic_buyers_5m": self.rng.randint(0, 20),
            "organic_score": self.rng.uniform(0, 90),
            "liquidity_change_1h_pct": self.rng.uniform(-40, 60),
        }

    def get_price(self, mint: str) -> Optional[float]:
        t = self._tokens.get(mint)
        if not t:
            return None
        shock = self.rng.gauss(t["drift"] * 0.1, t["vol"])
        t["price"] = max(t["price"] * (1 + shock), 1e-12)
        return t["price"]

    def insiders_still_holding(self, mint: str, wallets: list) -> list:
        return [w for w in wallets if self.rng.random() > 0.2]


# --------------------------------------------------------------------------
# LIVE — Helius enhanced tx + Jupiter
# --------------------------------------------------------------------------

class LiveInsiderSource:
    def __init__(self, cfg: Optional[InsiderConfig] = None):
        self.cfg = cfg or InsiderConfig()
        self.session = requests.Session()
        self.jupiter_api_key = os.environ.get("JUPITER_API_KEY")
        self.helius_key = self._extract_helius_key()
        if not self.helius_key:
            raise RuntimeError(
                "Could not read an api-key from HELIUS_RPC_URL. The insider bot "
                "needs Helius for wallet/token history. Set HELIUS_RPC_URL to "
                "your full https://…helius-rpc.com/?api-key=XXX URL (free tier "
                "is enough)."
            )
        self.rpc_url = os.environ["HELIUS_RPC_URL"]
        self._sol_price = 0.0
        self._sol_price_ts = 0.0
        self._price_cache: dict[str, tuple] = {}   # mint -> (price, fetched_at)
        self._price_ttl = 20.0

    # ---- setup helpers ----

    def _extract_helius_key(self) -> Optional[str]:
        url = os.environ.get("HELIUS_RPC_URL", "")
        try:
            q = parse_qs(urlparse(url).query)
            return (q.get("api-key") or q.get("api_key") or [None])[0]
        except Exception:
            return None

    def _jup_headers(self) -> dict:
        return {"x-api-key": self.jupiter_api_key} if self.jupiter_api_key else {}

    def _jget(self, url: str, params: dict, timeout: int = 15):
        """Rate-limited GET to Jupiter with one 429 backoff-retry. Returns
        parsed JSON or None. Everything Jupiter-facing goes through here so the
        free tier (~1 req/s) doesn't 429 us mid-run like it did on the first
        real discovery pass."""
        for attempt in (1, 2):
            _JUPITER_THROTTLE.wait()
            try:
                r = self.session.get(url, params=params, headers=self._jup_headers(), timeout=timeout)
                if r.status_code == 429:
                    time.sleep(2.5 * attempt)
                    continue
                r.raise_for_status()
                return r.json()
            except Exception as e:
                if attempt == 2:
                    print(f"[insider] jupiter GET failed ({url.rsplit('/', 1)[-1]}): {e}")
                    return None
                time.sleep(1.5)
        return None

    # ---- low level: Helius enhanced transactions ----

    def _address_txs(self, address: str, before: Optional[str] = None,
                     tx_type: Optional[str] = "SWAP", limit: int = 100) -> list[dict]:
        params = {"api-key": self.helius_key, "limit": limit}
        if tx_type:
            params["type"] = tx_type
        if before:
            params["before"] = before
        try:
            r = self.session.get(
                f"{self.cfg.helius_api_base}/addresses/{address}/transactions",
                params=params, timeout=20,
            )
            if r.status_code == 429:
                time.sleep(2)
                return []
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else []
        except Exception as e:
            print(f"[insider] helius tx fetch failed for {address[:6]}…: {e}")
            return []

    def _rpc(self, method: str, params: list):
        try:
            resp = self.session.post(
                self.rpc_url,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json().get("result")
        except Exception as e:
            print(f"[insider] rpc {method} failed: {e}")
            return None

    # ---- pricing ----

    def _sol_usd(self) -> float:
        if time.time() - self._sol_price_ts < 60 and self._sol_price:
            return self._sol_price
        p = self.get_price(self.cfg.sol_mint) or self._sol_price or 150.0
        self._sol_price, self._sol_price_ts = p, time.time()
        return p

    @staticmethod
    def _extract_usd_price(data, mint: str) -> Optional[float]:
        if not isinstance(data, dict):
            return None
        node = data.get(mint) or (data.get("data") or {}).get(mint)
        if node and node.get("usdPrice") is not None:
            return float(node["usdPrice"])
        return None

    def get_price(self, mint: str) -> Optional[float]:
        cached = self._price_cache.get(mint)
        if cached and time.time() - cached[1] < self._price_ttl:
            return cached[0]
        data = self._jget(self.cfg.jupiter_price_base_url, {"ids": mint}, timeout=10)
        price = self._extract_usd_price(data, mint)
        if price is not None:
            self._price_cache[mint] = (price, time.time())
        return price

    def _prices(self, mints: list[str]) -> dict[str, float]:
        out: dict[str, float] = {}
        now = time.time()
        fresh = [m for m in mints if not (self._price_cache.get(m) and now - self._price_cache[m][1] < self._price_ttl)]
        for m in mints:
            c = self._price_cache.get(m)
            if c and now - c[1] < self._price_ttl:
                out[m] = c[0]
        for i in range(0, len(fresh), 50):
            chunk = fresh[i:i + 50]
            data = self._jget(self.cfg.jupiter_price_base_url, {"ids": ",".join(chunk)})
            body = data.get("data", data) if isinstance(data, dict) else {}
            for m, node in (body or {}).items():
                if node and node.get("usdPrice") is not None:
                    out[m] = float(node["usdPrice"])
                    self._price_cache[m] = (out[m], time.time())
        return out

    # ---- parse a Helius enhanced tx into a SwapEvent for one wallet ----

    def _parse_swap(self, tx: dict, wallet: str) -> Optional[SwapEvent]:
        """Decide whether `wallet` bought or sold a non-SOL/USDC token in `tx`.
        Prefers Helius' structured `events.swap` (clean in/out amounts); falls
        back to reconstructing from raw token/native transfers."""
        ev = self._parse_swap_event(tx, wallet)
        if ev:
            return ev

        ts = float(tx.get("timestamp") or 0)
        sig = tx.get("signature", "")

        recv: dict[str, float] = {}   # mint -> token amount wallet received
        sent: dict[str, float] = {}
        sol_delta = 0.0               # + = wallet gained SOL, - = wallet spent SOL
        usdc_delta = 0.0

        for tt in tx.get("tokenTransfers") or []:
            mint = tt.get("mint")
            amt = float(tt.get("tokenAmount") or 0)
            if not mint or amt == 0:
                continue
            if tt.get("toUserAccount") == wallet:
                if mint == self.cfg.usdc_mint:
                    usdc_delta += amt
                elif mint == self.cfg.sol_mint:
                    sol_delta += amt
                else:
                    recv[mint] = recv.get(mint, 0) + amt
            if tt.get("fromUserAccount") == wallet:
                if mint == self.cfg.usdc_mint:
                    usdc_delta -= amt
                elif mint == self.cfg.sol_mint:
                    sol_delta -= amt
                else:
                    sent[mint] = sent.get(mint, 0) + amt

        for nt in tx.get("nativeTransfers") or []:
            lamports = float(nt.get("amount") or 0)
            if nt.get("toUserAccount") == wallet:
                sol_delta += lamports / 1e9
            if nt.get("fromUserAccount") == wallet:
                sol_delta -= lamports / 1e9

        sol_usd = self._sol_usd()
        paid_usd = max(0.0, -sol_delta) * sol_usd + max(0.0, -usdc_delta)
        got_usd = max(0.0, sol_delta) * sol_usd + max(0.0, usdc_delta)

        if recv and paid_usd > got_usd:
            mint = max(recv, key=recv.get)
            return SwapEvent(sig, ts, wallet, "buy", mint, recv[mint], paid_usd)
        if sent and got_usd > paid_usd:
            mint = max(sent, key=sent.get)
            return SwapEvent(sig, ts, wallet, "sell", mint, sent[mint], got_usd)
        return None

    def _parse_swap_event(self, tx: dict, wallet: str) -> Optional[SwapEvent]:
        """Use the structured events.swap block when Helius provides it."""
        swap = ((tx.get("events") or {}).get("swap")) if isinstance(tx.get("events"), dict) else None
        if not swap:
            return None
        ts = float(tx.get("timestamp") or 0)
        sig = tx.get("signature", "")
        stable = {self.cfg.sol_mint, self.cfg.usdc_mint}
        sol_usd = self._sol_usd()

        def _amt(node) -> float:
            raw = (node or {}).get("rawTokenAmount") or {}
            try:
                return abs(float(raw.get("tokenAmount", 0))) / (10 ** int(raw.get("decimals", 0)))
            except Exception:
                return 0.0

        def _usd_in_leg(node) -> float:
            m = (node or {}).get("mint")
            if m == self.cfg.usdc_mint:
                return _amt(node)
            if m == self.cfg.sol_mint:
                return _amt(node) * sol_usd
            return 0.0

        native_in = float((swap.get("nativeInput") or {}).get("amount") or 0) / 1e9
        native_out = float((swap.get("nativeOutput") or {}).get("amount") or 0) / 1e9
        tok_in = swap.get("tokenInputs") or []
        tok_out = swap.get("tokenOutputs") or []

        paid_usd = native_in * sol_usd + sum(_usd_in_leg(n) for n in tok_in)
        got_usd = native_out * sol_usd + sum(_usd_in_leg(n) for n in tok_out)

        bought = [(n.get("mint"), _amt(n)) for n in tok_out if n.get("mint") not in stable]
        sold = [(n.get("mint"), _amt(n)) for n in tok_in if n.get("mint") not in stable]

        if bought and paid_usd > got_usd > -1:
            mint, amt = max(bought, key=lambda x: x[1])
            if mint and amt > 0 and paid_usd > 0:
                return SwapEvent(sig, ts, wallet, "buy", mint, amt, paid_usd)
        if sold and got_usd > paid_usd:
            mint, amt = max(sold, key=lambda x: x[1])
            if mint and amt > 0 and got_usd > 0:
                return SwapEvent(sig, ts, wallet, "sell", mint, amt, got_usd)
        return None

    # ---- DISCOVERY ----

    def find_winner_mints(self) -> list[str]:
        mints = list(self.cfg.seed_winner_mints)
        rows = self._jget(self.cfg.jupiter_trending_url, {})
        rows = rows.get("data", rows) if isinstance(rows, dict) else rows
        kept = 0
        for row in rows or []:
            mint = row.get("id") or row.get("address") or row.get("mint")
            stats = row.get("stats24h") or row.get("stats") or {}
            chg = stats.get("priceChange")
            if chg is None:
                chg = row.get("priceChange24h")
            # keep tokens that ran hard in the last day
            if mint and chg is not None and float(chg) >= (self.cfg.winner_min_multiple - 1) * 100:
                mints.append(mint)
                kept += 1
        if not kept and not self.cfg.seed_winner_mints:
            print("[insider] trending feed returned nothing usable; set "
                  "seed_winner_mints in insider_config.py to mine specific runners")
        # de-dupe, drop SOL/USDC, cap the count
        seen, out = set(), []
        for m in mints:
            if m and m not in seen and m not in {self.cfg.sol_mint, self.cfg.usdc_mint}:
                seen.add(m)
                out.append(m)
        return out[:self.cfg.max_winner_tokens]

    def early_buyers_of(self, mint: str) -> list[tuple]:
        """Page a winner token's SWAP history to the beginning; return
        [(wallet, first_buy_ts, approx_price_usd), …] for its earliest buyers."""
        pages, before, all_txs = 0, None, []
        while pages < self.cfg.max_tx_pages_per_token:
            batch = self._address_txs(mint, before=before, tx_type="SWAP", limit=100)
            if not batch:
                break
            all_txs.extend(batch)
            before = batch[-1].get("signature")
            pages += 1
            if len(batch) < 100:
                break
            time.sleep(0.2)
        if not all_txs:
            return []

        all_txs.sort(key=lambda t: t.get("timestamp") or 0)
        first_ts = all_txs[0].get("timestamp") or 0
        cutoff = first_ts + self.cfg.early_window_minutes * 60

        buyers: dict[str, tuple] = {}
        for tx in all_txs:
            ts = tx.get("timestamp") or 0
            if len(buyers) >= self.cfg.early_first_n_buyers:
                break
            if ts > cutoff:
                break
            # find the wallet that received `mint` while paying out SOL/USDC
            paid = {nt.get("fromUserAccount") for nt in (tx.get("nativeTransfers") or [])
                    if float(nt.get("amount") or 0) > 0}
            for tt in tx.get("tokenTransfers") or []:
                if tt.get("mint") != mint:
                    continue
                w = tt.get("toUserAccount")
                amt = float(tt.get("tokenAmount") or 0)
                if not w or amt <= 0 or w in buyers:
                    continue
                # crude buyer check: they also sent SOL somewhere in this tx
                if w in paid or any(
                    t2.get("fromUserAccount") == w and t2.get("mint") in
                    {self.cfg.sol_mint, self.cfg.usdc_mint}
                    for t2 in (tx.get("tokenTransfers") or [])
                ):
                    ev = self._parse_swap(tx, w)
                    price = (ev.usd_value / ev.token_amount) if ev and ev.token_amount else 0.0
                    buyers[w] = (w, float(ts), price)
        return list(buyers.values())

    def _wallet_swaps(self, wallet: str, max_pages: int = 0) -> list[SwapEvent]:
        max_pages = max_pages or self.cfg.wallet_history_pages
        pages, before, events = 0, None, []
        while pages < max_pages:
            batch = self._address_txs(wallet, before=before, tx_type="SWAP", limit=100)
            if not batch:
                break
            for tx in batch:
                ev = self._parse_swap(tx, wallet)
                if ev:
                    events.append(ev)
            before = batch[-1].get("signature")
            pages += 1
            if len(batch) < 100:
                break
            time.sleep(0.2)
        return events

    def wallet_stats(self, wallet: str) -> Optional[WalletStats]:
        events = self._wallet_swaps(wallet)
        if not events:
            return None
        by_mint: dict[str, dict] = {}
        for ev in events:
            d = by_mint.setdefault(ev.mint, {
                "bought_usd": 0.0, "sold_usd": 0.0,
                "bought_tok": 0.0, "sold_tok": 0.0,
                "first_ts": ev.timestamp, "last_ts": ev.timestamp,
            })
            d["first_ts"] = min(d["first_ts"], ev.timestamp)
            d["last_ts"] = max(d["last_ts"], ev.timestamp)
            if ev.action == "buy":
                d["bought_usd"] += ev.usd_value
                d["bought_tok"] += ev.token_amount
            else:
                d["sold_usd"] += ev.usd_value
                d["sold_tok"] += ev.token_amount

        # Only score tokens where the wallet put in a real (non-dust) amount.
        # A real run without this floor computed medians of ~1e16 off $0.0001
        # "buys" that were really rent/route noise.
        real = {m: d for m, d in by_mint.items()
                if d["bought_usd"] >= self.cfg.min_buy_usd_for_stats and d["bought_tok"] > 0}
        if not real:
            return None

        open_mints = [m for m, d in real.items()
                      if d["sold_tok"] < d["bought_tok"] * 0.99]
        prices = self._prices(open_mints) if open_mints else {}

        cap = self.cfg.per_token_multiple_cap
        multiples = []
        for m, d in real.items():
            remaining = max(0.0, d["bought_tok"] - d["sold_tok"])
            still_open = remaining > d["bought_tok"] * 0.01
            if still_open and m not in prices:
                # can't mark an open bag with no price — count only realized part,
                # but don't let a big unrealized winner look like a total loss:
                # skip the token rather than distort the median in either direction.
                if d["sold_usd"] < self.cfg.min_buy_usd_for_stats:
                    continue
            mark = remaining * prices.get(m, 0.0)
            mult = (d["sold_usd"] + mark) / d["bought_usd"]
            multiples.append(max(0.0, min(mult, cap)))
        if not multiples:
            return None

        wins = [x for x in multiples if x >= 2.0]
        return WalletStats(
            wallet=wallet,
            tokens_tracked=len(multiples),
            hit_rate=len(wins) / len(multiples),
            median_multiple=statistics.median(multiples),
            best_multiple=max(multiples),
            early_wins=sum(1 for x in multiples if x >= self.cfg.winner_min_multiple),
            first_seen_ts=min(d["first_ts"] for d in real.values()),
            last_trade_ts=max(d["last_ts"] for d in real.values()),
        )

    # ---- BACKTEST support ----

    def token_price_series(self, mint: str, start_ts: float, end_ts: float,
                           max_pages: int = 60) -> tuple:
        """Reconstruct a token's price history (SOL per token) from its on-chain
        swap prints in [start_ts, end_ts]. Helius paginates newest-first, so we
        walk back until a page predates start_ts (or the page cap). Returns
        (series, reached_start): series is time-sorted (ts, price_sol);
        reached_start is False when the cap stopped us before start_ts, meaning
        the earliest part of the window is missing (heavy-volume token), not
        that the token was dead."""
        pages, before, series = 0, None, []
        reached_start = False
        oldest_seen = None
        while pages < max_pages:
            batch = self._address_txs(mint, before=before, tx_type="SWAP", limit=100)
            if not batch:
                reached_start = True
                break
            for tx in batch:
                ts = float(tx.get("timestamp") or 0)
                if start_ts <= ts <= end_ts:
                    p = self._implied_price_sol(tx, mint)
                    if p and p > 0:
                        series.append((ts, p))
            oldest = min((t.get("timestamp") or 0) for t in batch)
            oldest_seen = oldest if oldest_seen is None else min(oldest_seen, oldest)
            before = batch[-1].get("signature")
            pages += 1
            if oldest < start_ts:
                reached_start = True
                break
            if len(batch) < 100:
                # short page: could be end of history, or just the Enhanced
                # API's lookback ceiling. If the oldest tx we ever saw is still
                # well after the window we wanted, it's the ceiling.
                reached_start = oldest_seen <= end_ts
                break
            time.sleep(0.12)
        series.sort()
        return series, reached_start

    def _implied_price_sol(self, tx: dict, mint: str) -> Optional[float]:
        """SOL-per-token implied by one swap tx, from events.swap if present
        else from raw transfers."""
        swap = ((tx.get("events") or {}).get("swap")) if isinstance(tx.get("events"), dict) else None
        if swap:
            def _amt(node):
                raw = (node or {}).get("rawTokenAmount") or {}
                try:
                    return abs(float(raw.get("tokenAmount", 0))) / (10 ** int(raw.get("decimals", 0)))
                except Exception:
                    return 0.0
            sol = (float((swap.get("nativeInput") or {}).get("amount") or 0)
                   + float((swap.get("nativeOutput") or {}).get("amount") or 0)) / 1e9
            tok = 0.0
            for node in (swap.get("tokenInputs") or []) + (swap.get("tokenOutputs") or []):
                if node.get("mint") == mint:
                    tok += _amt(node)
            if sol > 0 and tok > 0:
                return sol / tok
        # fallback: raw transfers
        sol = sum(float(nt.get("amount") or 0) / 1e9 for nt in (tx.get("nativeTransfers") or []))
        tok = sum(float(tt.get("tokenAmount") or 0)
                  for tt in (tx.get("tokenTransfers") or []) if tt.get("mint") == mint)
        return (sol / tok) if sol > 0 and tok > 0 else None

    # ---- LIVE TRACKING ----

    def recent_buys(self, wallet: str, since_ts: float) -> list[SwapEvent]:
        batch = self._address_txs(wallet, tx_type="SWAP", limit=25)
        out = []
        for tx in batch:
            if (tx.get("timestamp") or 0) <= since_ts:
                continue
            ev = self._parse_swap(tx, wallet)
            if ev and ev.action == "buy" and ev.mint not in {self.cfg.sol_mint, self.cfg.usdc_mint}:
                out.append(ev)
        return out

    def token_info(self, mint: str) -> Optional[dict]:
        try:
            results = self._jget(self.cfg.jupiter_token_info_base_url,
                                 {"query": mint}, timeout=10)
            results = results.get("data", results) if isinstance(results, dict) else results
            if not results:
                return None
            info = next((x for x in results if x.get("id") == mint), results[0])
            created = info.get("createdAt") or info.get("firstPool", {}).get("createdAt")
            age_min = None
            if created:
                try:
                    # epoch seconds or ISO8601
                    if isinstance(created, (int, float)):
                        age_min = (time.time() - float(created)) / 60
                    else:
                        import datetime as _dt
                        age_min = (time.time() - _dt.datetime.fromisoformat(
                            created.replace("Z", "+00:00")).timestamp()) / 60
                except Exception:
                    age_min = None
            stats1h = info.get("stats1h") or {}
            stats5m = info.get("stats5m") or {}
            return {
                "symbol": info.get("symbol", "?"),
                "age_minutes": age_min,
                "liquidity_usd": float(info.get("liquidity") or 0.0),
                "holder_count": int(info.get("holderCount") or 0),
                "price_change_1h_pct": float(stats1h.get("priceChange") or 0.0),
                # --- "research the coin" signals ---
                "price_change_5m_pct": float(stats5m.get("priceChange") or 0.0),
                "num_organic_buyers_5m": int(stats5m.get("numOrganicBuyers") or 0),
                "organic_score": float(info.get("organicScore") or 0.0),
                "liquidity_change_1h_pct": float(stats1h.get("liquidityChange") or 0.0),
            }
        except Exception as e:
            print(f"[insider] token info failed for {mint[:6]}…: {e}")
            return None

    def insiders_still_holding(self, mint: str, wallets: list) -> list:
        holding = []
        for w in wallets:
            res = self._rpc("getTokenAccountsByOwner",
                            [w, {"mint": mint}, {"encoding": "jsonParsed"}])
            try:
                accts = (res or {}).get("value") or []
                bal = 0
                for a in accts:
                    bal += int(a["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"])
                if bal > 0:
                    holding.append(w)
            except Exception:
                holding.append(w)  # unknown -> assume still in, don't force-exit on a glitch
            time.sleep(0.1)
        return holding
