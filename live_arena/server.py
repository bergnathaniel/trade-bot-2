"""Live Arena - local server.

Serves the app and passes price requests through to free public price APIs that the browser can't
call directly: Kraken for live crypto, Coinbase for recent daily crypto candles, Yahoo Finance for
stocks. It also saves the paper tests' results: a daily snapshot appended to paper_ledger.jsonl, and
the latest full update, trades included, in paper_latest.json for weekly_check.py. Paper trading
only - this never places a real order and holds no keys.

Run:  python3 live_arena/server.py   then open http://127.0.0.1:8765
"""
import http.server
import json
import os
import re
import ssl
import threading
import time
import urllib.parse
import urllib.request
import webbrowser

try:  # python.org builds on macOS ship without CA certs
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl.create_default_context(
        cafile="/etc/ssl/cert.pem" if os.path.exists("/etc/ssl/cert.pem") else None)

PORT = int(os.environ.get("PORT", "8765"))
ROOT = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(ROOT, "paper_ledger.jsonl")
LATEST = os.path.join(ROOT, "paper_latest.json")
LATEST_PRACTICE = os.path.join(ROOT, "paper_latest_practice.json")   # runs from a pretend start date
KRAKEN_PAIR = re.compile(r"^[A-Z0-9]{2,10}USD$")
INTERVALS = {"1", "5", "15", "60", "240", "1440"}
HISTORY_CANDLES = 2000   # how much history the live/replay chart loads on open (was 720, Kraken's single-page max)
# arena interval in minutes -> (Yahoo interval, days of history Yahoo serves for it)
YAHOO_INTERVALS = {"5": ("5m", 59), "15": ("15m", 59), "60": ("60m", 729), "1440": ("1d", 1100)}
SYMBOL = re.compile(r"^[A-Z0-9^][A-Z0-9.\-=^]{0,11}$")   # AAPL, BRK-B, BTC-USD, ^GSPC, GC=F
PRODUCT = re.compile(r"^[A-Z0-9]{1,12}-USD$")
CACHE_SECONDS = 900
_cache, _cache_lock = {}, threading.Lock()


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15, context=SSL_CTX) as r:
        return json.load(r)


def cached(key, load):
    """load() at most once per CACHE_SECONDS per key, so reopening a panel doesn't refetch everything."""
    with _cache_lock:
        hit = _cache.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    value = load()
    with _cache_lock:
        _cache[key] = (time.time(), value)
    return value


def yahoo_rows(symbol, interval):
    """Yahoo bars in Kraken's row layout [time, open, high, low, close, vwap, volume]; broken bars dropped."""
    name, days = YAHOO_INTERVALS[interval]
    end = int(time.time())
    j = fetch_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
                   f"?period1={end - days * 86400}&period2={end}&interval={name}&includePrePost=false")
    result = (j.get("chart") or {}).get("result")
    if not result:
        raise ValueError(f"no data for {symbol}")
    quote = result[0]["indicators"]["quote"][0]
    rows = []
    for k, t in enumerate(result[0].get("timestamp") or []):
        o, h, l, c, v = (quote[f][k] for f in ("open", "high", "low", "close", "volume"))
        if None in (o, h, l, c) or min(o, h, l, c) <= 0 or h < l:
            continue
        rows.append([t, o, h, l, c, None, v or 0])
    return rows[-(HISTORY_CANDLES + 1):]


def kraken_rows(pair, interval):
    """Kraken's OHLC candles. Its public endpoint only ever serves its own most recent ~720, regardless of `since`
    (tried paginating past that with `since`; Kraken silently ignores it and returns the same 720 every time) - so
    unlike yahoo_rows, this doesn't reach HISTORY_CANDLES. Left as a real ceiling of that free endpoint."""
    return fetch_json(f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval={interval}")


def coinbase_rows(product):
    """Coinbase's latest 300 daily candles, finished days only, oldest first, in Kraken's row layout."""
    today = int(time.time()) // 86400 * 86400
    rows = fetch_json(f"https://api.exchange.coinbase.com/products/{product}/candles?granularity=86400")
    return [[r[0], r[3], r[2], r[1], r[4], None, r[5]] for r in sorted(rows) if r[0] < today]


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        interval = q.get("interval", "")
        try:
            if url.path == "/api/ohlc":
                pair = q.get("pair", "")
                if not KRAKEN_PAIR.match(pair) or interval not in INTERVALS:
                    return self._send(400, {"error": ["bad pair or interval"]})
                return self._send(200, cached(("kraken", pair, interval), lambda: kraken_rows(pair, interval)))
            if url.path == "/api/yahoo":
                symbol = q.get("symbol", "")
                if not SYMBOL.match(symbol) or interval not in YAHOO_INTERVALS:
                    return self._send(400, {"error": ["bad symbol or interval"]})
                rows = cached(("yahoo", symbol, interval), lambda: yahoo_rows(symbol, interval))
                return self._send(200, {"error": [], "result": {symbol: rows, "last": 0}})
            if url.path == "/api/coinbase":
                product = q.get("product", "")
                if not PRODUCT.match(product):
                    return self._send(400, {"error": ["bad product"]})
                rows = cached(("coinbase", product), lambda: coinbase_rows(product))
                return self._send(200, {"error": [], "result": {product: rows, "last": 0}})
        except Exception as e:
            return self._send(502, {"error": [str(e)]})
        return super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/speedresult":
            return self._save_speed_result()
        if path not in ("/api/paperlog", "/api/paperlatest"):
            return self._send(404, {"error": ["not found"]})
        size = int(self.headers.get("Content-Length") or 0)
        if not 0 < size <= (200_000 if path == "/api/paperlog" else 20_000_000):
            return self._send(400, {"error": ["bad size"]})
        try:
            entry = json.loads(self.rfile.read(size))
        except ValueError:
            return self._send(400, {"error": ["bad json"]})
        if not isinstance(entry, dict):
            return self._send(400, {"error": ["bad json"]})
        entry["recorded_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if path == "/api/paperlog":
            with open(LEDGER, "a") as f:
                f.write(json.dumps(entry) + "\n")
        else:
            target = LATEST_PRACTICE if entry.get("practice") else LATEST
            with open(target + ".tmp", "w") as f:
                json.dump(entry, f)
            os.replace(target + ".tmp", target)   # readers never see a half-written file
        return self._send(200, {"error": [], "ok": True})

    def _save_speed_result(self):
        """One week's speed test results from the app (speed_test.js), saved as speed/results/<week>.json."""
        size = int(self.headers.get("Content-Length") or 0)
        if not 0 < size <= 50_000_000:
            return self._send(400, {"error": ["bad size"]})
        try:
            result = json.loads(self.rfile.read(size))
        except ValueError:
            return self._send(400, {"error": ["bad json"]})
        if not isinstance(result, dict) or not re.match(r"^\d{4}-\d{2}-\d{2}$", str(result.get("week", ""))):
            return self._send(400, {"error": ["bad week"]})
        folder = os.path.join(ROOT, "speed", "results")
        os.makedirs(folder, exist_ok=True)
        target = os.path.join(folder, f"{result['week']}.json")
        with open(target + ".tmp", "w") as f:
            json.dump(result, f)
        os.replace(target + ".tmp", target)
        return self._send(200, {"error": [], "ok": True})

    def _send(self, code, obj):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(obj).encode())

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Live Arena running at http://127.0.0.1:{PORT}  (Ctrl+C to stop)")
    if os.environ.get("NO_BROWSER") != "1":
        webbrowser.open(f"http://127.0.0.1:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
