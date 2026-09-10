"""
Signal sources for alpha_bot.py — everything that can say "buy this now",
running as independent push threads onto one queue.

  MockSource        : synthetic, no network. Paper testing.
  HeliusWalletSource: wss logsSubscribe on each watched wallet -> on a swap,
                      pull the enhanced tx, parse the buy, emit in <1s.
  XStreamSource     : X API v2 filtered stream. Sets rules from config, streams
                      matching tweets, extracts a mint (or cashtag), emits.
  WebhookSource     : local HTTP endpoint. Any external alerter POSTs JSON.

Every source reconnects on failure with backoff and never raises into the
process. The api-key for Helius is read out of HELIUS_RPC_URL.
"""

import json
import os
import queue
import re
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional
from urllib.parse import urlparse, parse_qs

import requests

try:
    import certifi
    import websocket  # websocket-client
    _WS_OK = True
except Exception:  # pragma: no cover
    _WS_OK = False

_MINT_RE = re.compile(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b")   # base58, Solana-address length
_CASHTAG_RE = re.compile(r"\$([A-Za-z][A-Za-z0-9]{1,9})\b")
_STABLE = {
    "So11111111111111111111111111111111111111112",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
}


@dataclass
class Signal:
    source: str                    # "onchain" | "x" | "webhook" | "mock"
    ts: float
    mint: Optional[str] = None     # resolved mint, or None if only a ticker/text
    raw_ref: str = ""              # cashtag / url / free text when mint is None
    actor: str = ""               # wallet pubkey or @handle
    insider_price_usd: float = 0.0
    insider_usd: float = 0.0
    note: str = ""


class SignalBus:
    def __init__(self, cfg, get_price: Optional[Callable[[str], Optional[float]]] = None):
        self.cfg = cfg
        self.get_price = get_price or (lambda _m: None)
        self.q: "queue.Queue[Signal]" = queue.Queue()
        self._sources: list = []
        self._stop = threading.Event()

    def emit(self, sig: Signal):
        if not self._stop.is_set():
            self.q.put(sig)

    def start(self):
        c = self.cfg
        if c.enable_mock:
            self._sources.append(MockSource(c, self.emit, self._stop))
        if c.enable_onchain:
            self._sources.append(HeliusWalletSource(c, self.emit, self._stop, self.get_price))
        if c.enable_x:
            self._sources.append(XStreamSource(c, self.emit, self._stop))
        if c.enable_webhook:
            self._sources.append(WebhookSource(c, self.emit, self._stop))
        for s in self._sources:
            s.start()
        names = ", ".join(type(s).__name__ for s in self._sources) or "(none — enable a source in alpha_config)"
        print(f"[bus] started: {names}")

    def get(self, timeout: float) -> Optional[Signal]:
        try:
            return self.q.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self):
        self._stop.set()
        for s in self._sources:
            if hasattr(s, "close"):
                try:
                    s.close()
                except Exception:
                    pass


# --------------------------------------------------------------------------

class MockSource(threading.Thread):
    def __init__(self, cfg, emit, stop):
        super().__init__(daemon=True)
        self.cfg, self.emit, self.stop = cfg, emit, stop
        self._i = 0

    def run(self):
        import random
        rng = random.Random(7)
        mints = list(getattr(self.cfg, "mock_mints", ())) or [None]
        while not self.stop.is_set():
            time.sleep(rng.uniform(2, 6))
            if rng.random() < 0.5:
                self._i += 1
                mint = mints[self._i % len(mints)]
                self.emit(Signal(
                    source="mock", ts=time.time(), mint=mint,
                    raw_ref="" if mint else "BONK",
                    actor=f"MockWallet{rng.randint(1, 6)}",
                    insider_price_usd=0.0,          # 0 = skip the anti-exit-liquidity gate
                    insider_usd=rng.uniform(80, 600),
                    note="synthetic",
                ))


# --------------------------------------------------------------------------

class HeliusWalletSource(threading.Thread):
    def __init__(self, cfg, emit, stop, get_price):
        super().__init__(daemon=True)
        self.cfg, self.emit, self.stop, self.get_price = cfg, emit, stop, get_price
        self.key = self._helius_key()
        # standard RPC endpoint — much higher free-tier limits than the
        # enhanced /v0/transactions API (which 429s constantly on free).
        self.rpc_url = os.environ.get("HELIUS_RPC_URL") or (
            f"https://mainnet.helius-rpc.com/?api-key={self.key}" if self.key else None)
        self.wallets = self._resolve_wallets()
        self._sub_to_wallet: dict[int, str] = {}
        self._session = requests.Session()
        self._sol_px = (0.0, 0.0)

    @staticmethod
    def _helius_key() -> Optional[str]:
        try:
            q = parse_qs(urlparse(os.environ.get("HELIUS_RPC_URL", "")).query)
            return (q.get("api-key") or q.get("api_key") or [None])[0]
        except Exception:
            return None

    def _resolve_wallets(self) -> list[str]:
        out = list(self.cfg.watched_wallets)
        path = self.cfg.load_watchlist_json
        if path and os.path.exists(path):
            try:
                data = json.load(open(path))
                rows = data if isinstance(data, list) else data.get("wallets", data.get("kept", []))
                for r in rows:
                    w = r.get("wallet") if isinstance(r, dict) else r
                    if w:
                        out.append(w)
            except Exception as e:
                print(f"[onchain] could not read {path}: {e}")
        seen, uniq = set(), []
        for w in out:
            if w and w not in seen:
                seen.add(w)
                uniq.append(w)
        return uniq[: self.cfg.max_watched_wallets]

    def _sol_usd(self) -> float:
        if time.time() - self._sol_px[1] < 60 and self._sol_px[0]:
            return self._sol_px[0]
        p = self.get_price(self.cfg.sol_mint) or self._sol_px[0] or 150.0
        self._sol_px = (p, time.time())
        return p

    def run(self):
        if not _WS_OK:
            print("[onchain] websocket-client/certifi missing — source disabled")
            return
        if not self.key:
            print("[onchain] no api-key in HELIUS_RPC_URL — source disabled")
            return
        if not self.wallets:
            print("[onchain] no watched wallets — source disabled")
            return
        url = f"wss://mainnet.helius-rpc.com/?api-key={self.key}"
        print(f"[onchain] subscribing to {len(self.wallets)} wallet(s) via Helius ws")
        backoff = 2
        while not self.stop.is_set():
            try:
                ws = websocket.create_connection(url, sslopt={"ca_certs": certifi.where()}, timeout=20)
                self._sub_to_wallet.clear()
                for i, w in enumerate(self.wallets, start=1):
                    ws.send(json.dumps({
                        "jsonrpc": "2.0", "id": i, "method": "logsSubscribe",
                        "params": [{"mentions": [w]}, {"commitment": "processed"}],
                    }))
                    time.sleep(0.03)
                backoff = 2
                while not self.stop.is_set():
                    msg = ws.recv()
                    if not msg:
                        continue
                    self._handle(json.loads(msg))
            except Exception as e:
                if self.stop.is_set():
                    return
                print(f"[onchain] ws error ({e}); reconnecting in {backoff}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)

    def _handle(self, data: dict):
        # subscription-id -> wallet map from the ack responses
        if "result" in data and isinstance(data.get("id"), int):
            self._sub_to_wallet[data["result"]] = self.wallets[data["id"] - 1]
            return
        if data.get("method") != "logsNotification":
            return
        params = data.get("params") or {}
        sub = params.get("subscription")
        wallet = self._sub_to_wallet.get(sub, "?")
        val = (params.get("result") or {}).get("value") or {}
        sig = val.get("signature")
        if not sig or val.get("err"):
            return
        threading.Thread(target=self._on_signature, args=(sig, wallet), daemon=True).start()

    def _on_signature(self, sig: str, wallet: str):
        ev = None
        # Primary path: standard RPC getTransaction. The wss push already gave
        # us the signature; one RPC lookup per swap is well inside the free
        # tier, unlike the enhanced /v0/transactions endpoint.
        if self.rpc_url:
            for attempt in range(3):
                try:
                    r = self._session.post(self.rpc_url, json={
                        "jsonrpc": "2.0", "id": 1, "method": "getTransaction",
                        "params": [sig, {"encoding": "jsonParsed",
                                         "maxSupportedTransactionVersion": 0,
                                         "commitment": "confirmed"}]}, timeout=12)
                    if r.status_code == 429:
                        time.sleep(0.6 * (attempt + 1)); continue
                    r.raise_for_status()
                    res = (r.json() or {}).get("result")
                    if res:
                        ev = _parse_rpc_swap(res, wallet, self._sol_usd())
                    break
                except Exception as e:
                    if attempt == 2:
                        print(f"[onchain] rpc getTransaction failed for {sig[:8]}…: {e}")
                    else:
                        time.sleep(0.5)
        # Fallback: enhanced API, only if RPC produced nothing.
        if ev is None:
            try:
                r = self._session.post(
                    f"{self.cfg.helius_api_base}/transactions",
                    params={"api-key": self.key},
                    json={"transactions": [sig]}, timeout=12,
                )
                if r.status_code != 429:
                    r.raise_for_status()
                    txs = r.json()
                    if txs:
                        ev = _parse_helius_swap(txs[0], wallet, self._sol_usd())
            except Exception as e:
                print(f"[onchain] enhanced tx parse failed for {sig[:8]}…: {e}")
        if not ev or ev["action"] != "buy":
            return
        if ev["mint"] in _STABLE or ev["usd"] < self.cfg.min_insider_buy_usd:
            return
        self.emit(Signal(
            source="onchain", ts=time.time(), mint=ev["mint"], actor=wallet,
            insider_price_usd=ev["price"], insider_usd=ev["usd"],
            note=f"copy {wallet[:4]}… ${ev['usd']:.0f}",
        ))


def _parse_rpc_swap(result: dict, wallet: str, sol_usd: float) -> Optional[dict]:
    """Buy/sell extractor from a standard getTransaction (jsonParsed) result,
    by diffing this wallet's native-SOL and SPL-token balances pre vs post."""
    USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    SOL = "So11111111111111111111111111111111111111112"
    meta = (result or {}).get("meta") or {}
    if meta.get("err"):
        return None
    msg = ((result or {}).get("transaction") or {}).get("message") or {}
    keys = msg.get("accountKeys") or []

    def _pk(k):
        return k.get("pubkey") if isinstance(k, dict) else k

    sol_delta = 0.0
    pre_b, post_b = meta.get("preBalances") or [], meta.get("postBalances") or []
    for i, k in enumerate(keys):
        if _pk(k) == wallet and i < len(pre_b) and i < len(post_b):
            sol_delta += (post_b[i] - pre_b[i]) / 1e9
            break

    def _tokmap(bals):
        m = {}
        for b in bals or []:
            if b.get("owner") != wallet:
                continue
            ui = b.get("uiTokenAmount") or {}
            amt = ui.get("uiAmount")
            if amt is None:
                a, d = ui.get("amount"), ui.get("decimals") or 0
                amt = float(a) / (10 ** d) if a is not None else 0.0
            m[b.get("mint")] = m.get(b.get("mint"), 0.0) + float(amt or 0)
        return m

    pre_t, post_t = _tokmap(meta.get("preTokenBalances")), _tokmap(meta.get("postTokenBalances"))
    recv, sent, usdc_delta = {}, {}, 0.0
    for mint in set(pre_t) | set(post_t):
        d = post_t.get(mint, 0.0) - pre_t.get(mint, 0.0)
        if abs(d) < 1e-12:
            continue
        if mint == USDC:
            usdc_delta += d
        elif mint == SOL:
            sol_delta += d
        elif d > 0:
            recv[mint] = recv.get(mint, 0.0) + d
        else:
            sent[mint] = sent.get(mint, 0.0) - d

    paid = max(0.0, -sol_delta) * sol_usd + max(0.0, -usdc_delta)
    got = max(0.0, sol_delta) * sol_usd + max(0.0, usdc_delta)
    ts = float(result.get("blockTime") or 0)
    if recv and paid > got:
        m = max(recv, key=recv.get)
        return {"action": "buy", "mint": m, "amount": recv[m], "usd": paid,
                "price": paid / recv[m] if recv[m] else 0.0, "ts": ts}
    if sent and got > paid:
        m = max(sent, key=sent.get)
        return {"action": "sell", "mint": m, "amount": sent[m], "usd": got,
                "price": got / sent[m] if sent[m] else 0.0, "ts": ts}
    return None


def _parse_helius_swap(tx: dict, wallet: str, sol_usd: float) -> Optional[dict]:
    """Compact buy/sell extractor for one Helius enhanced tx and one wallet."""
    ts = float(tx.get("timestamp") or 0)
    recv: dict[str, float] = {}
    sent: dict[str, float] = {}
    sol_delta = usdc_delta = 0.0
    USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    SOL = "So11111111111111111111111111111111111111112"
    for tt in tx.get("tokenTransfers") or []:
        mint, amt = tt.get("mint"), float(tt.get("tokenAmount") or 0)
        if not mint or amt == 0:
            continue
        if tt.get("toUserAccount") == wallet:
            if mint == SOL:
                sol_delta += amt
            elif mint == USDC:
                usdc_delta += amt
            else:
                recv[mint] = recv.get(mint, 0) + amt
        if tt.get("fromUserAccount") == wallet:
            if mint == SOL:
                sol_delta -= amt
            elif mint == USDC:
                usdc_delta -= amt
            else:
                sent[mint] = sent.get(mint, 0) + amt
    for nt in tx.get("nativeTransfers") or []:
        lam = float(nt.get("amount") or 0) / 1e9
        if nt.get("toUserAccount") == wallet:
            sol_delta += lam
        if nt.get("fromUserAccount") == wallet:
            sol_delta -= lam
    paid = max(0.0, -sol_delta) * sol_usd + max(0.0, -usdc_delta)
    got = max(0.0, sol_delta) * sol_usd + max(0.0, usdc_delta)
    if recv and paid > got:
        m = max(recv, key=recv.get)
        return {"action": "buy", "mint": m, "amount": recv[m], "usd": paid,
                "price": paid / recv[m] if recv[m] else 0.0, "ts": ts}
    if sent and got > paid:
        m = max(sent, key=sent.get)
        return {"action": "sell", "mint": m, "amount": sent[m], "usd": got,
                "price": got / sent[m] if sent[m] else 0.0, "ts": ts}
    return None


# --------------------------------------------------------------------------

class XStreamSource(threading.Thread):
    def __init__(self, cfg, emit, stop):
        super().__init__(daemon=True)
        self.cfg, self.emit, self.stop = cfg, emit, stop
        self.token = os.environ.get("X_BEARER_TOKEN") or os.environ.get("TWITTER_BEARER_TOKEN")

    def _auth(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def _sync_rules(self):
        cur = requests.get(self.cfg.x_rules_url, headers=self._auth(), timeout=15).json()
        ids = [r["id"] for r in cur.get("data", [])]
        if ids:
            requests.post(self.cfg.x_rules_url, headers=self._auth(),
                          json={"delete": {"ids": ids}}, timeout=15)
        clauses = []
        if self.cfg.x_tracked_accounts:
            clauses.append("(" + " OR ".join(f"from:{h}" for h in self.cfg.x_tracked_accounts) + ")")
        if self.cfg.x_cashtags:
            clauses.append("(" + " OR ".join(f"${t}" for t in self.cfg.x_cashtags) + ")")
        if self.cfg.x_keywords:
            clauses.append("(" + " OR ".join(f'"{k}"' for k in self.cfg.x_keywords) + ")")
        value = " OR ".join(clauses) if clauses else "$SOL"
        value = value[:1024]
        requests.post(self.cfg.x_rules_url, headers=self._auth(),
                      json={"add": [{"value": value, "tag": "alpha_bot"}]}, timeout=15)
        print(f"[x] stream rule: {value}")

    def run(self):
        if not self.token:
            print("[x] X_BEARER_TOKEN not set — source disabled")
            return
        try:
            self._sync_rules()
        except Exception as e:
            print(f"[x] rule sync failed ({e}); streaming with whatever rules exist")
        params = {
            "tweet.fields": "author_id,created_at,entities",
            "expansions": "author_id",
            "user.fields": "public_metrics,username",
        }
        backoff = 3
        while not self.stop.is_set():
            try:
                with requests.get(self.cfg.x_stream_url, headers=self._auth(),
                                  params=params, stream=True, timeout=(15, 90)) as resp:
                    if resp.status_code != 200:
                        raise RuntimeError(f"stream HTTP {resp.status_code}: {resp.text[:200]}")
                    backoff = 3
                    for line in resp.iter_lines():
                        if self.stop.is_set():
                            return
                        if not line:
                            continue
                        try:
                            self._handle(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                if self.stop.is_set():
                    return
                print(f"[x] stream error ({e}); reconnecting in {backoff}s")
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)

    def _handle(self, payload: dict):
        tw = payload.get("data") or {}
        text = tw.get("text", "")
        users = {u["id"]: u for u in (payload.get("includes", {}) or {}).get("users", [])}
        author = users.get(tw.get("author_id"), {})
        followers = (author.get("public_metrics") or {}).get("followers_count", 0)
        if followers < self.cfg.x_min_author_followers:
            return
        handle = author.get("username", "?")
        mints = [m for m in _MINT_RE.findall(text) if m not in _STABLE]
        if mints:
            self.emit(Signal(source="x", ts=time.time(), mint=mints[0], actor=f"@{handle}",
                             raw_ref=text[:120], note=f"tweet by @{handle} ({followers} followers)"))
            return
        if self.cfg.x_require_contract_address:
            return
        tags = _CASHTAG_RE.findall(text)
        if tags:
            self.emit(Signal(source="x", ts=time.time(), mint=None, raw_ref=tags[0].upper(),
                             actor=f"@{handle}", note=f"cashtag ${tags[0].upper()} by @{handle}"))


# --------------------------------------------------------------------------

class WebhookSource(threading.Thread):
    def __init__(self, cfg, emit, stop):
        super().__init__(daemon=True)
        self.cfg, self.emit, self.stop = cfg, emit, stop
        self._httpd: Optional[ThreadingHTTPServer] = None

    def run(self):
        cfg, emit = self.cfg, self.emit

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):  # silence default stderr logging
                pass

            def do_POST(self):
                try:
                    if cfg.webhook_secret:
                        q = parse_qs(urlparse(self.path).query)
                        supplied = self.headers.get("X-Secret") or (q.get("secret") or [""])[0]
                        if supplied != cfg.webhook_secret:
                            self.send_response(403); self.end_headers(); return
                    n = int(self.headers.get("Content-Length") or 0)
                    body = json.loads(self.rfile.read(n) or b"{}")
                    mint = body.get("mint") or body.get("ca") or body.get("address")
                    ref = body.get("ticker") or body.get("symbol") or body.get("text") or ""
                    if not mint and not ref:
                        self.send_response(400); self.end_headers(); return
                    emit(Signal(source="webhook", ts=time.time(),
                                mint=mint, raw_ref=str(ref)[:120],
                                actor=str(body.get("source") or "webhook"),
                                note=str(body.get("note") or "")[:120]))
                    self.send_response(202); self.end_headers()
                    self.wfile.write(b'{"ok":true}')
                except Exception:
                    self.send_response(500); self.end_headers()

        try:
            self._httpd = ThreadingHTTPServer((self.cfg.webhook_host, self.cfg.webhook_port), Handler)
        except Exception as e:
            print(f"[webhook] could not bind {self.cfg.webhook_host}:{self.cfg.webhook_port} — {e}")
            return
        print(f"[webhook] listening on http://{self.cfg.webhook_host}:{self.cfg.webhook_port} "
              f"(POST JSON {{mint|ticker|text}})")
        self._httpd.timeout = 1
        while not self.stop.is_set():
            self._httpd.handle_request()

    def close(self):
        if self._httpd:
            self._httpd.server_close()
