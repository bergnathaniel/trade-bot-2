"""Phase 9 data: Coinbase daily candles for every USD pair, listed or delisted, from 2022-01-01.

Only collects prices and volumes (the pre-registration's data-availability check). Nothing here computes a return or
a signal. Saves research/data/coinbase_daily/<PRODUCT>.json as [time, open, high, low, close, volume] rows, oldest
first, plus _summary.json with each product's first and last day and row count.
"""
import datetime
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "coinbase_daily")
START = int(datetime.datetime(2022, 1, 1, tzinfo=datetime.timezone.utc).timestamp())
END = int(datetime.datetime(2026, 9, 13, tzinfo=datetime.timezone.utc).timestamp())
DAY = 86400
try:
    import certifi
    CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    CTX = ssl._create_unverified_context()


def get(url):
    for attempt in range(5):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "trade-bot-research"})
            with urllib.request.urlopen(req, timeout=30, context=CTX) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                return None
            time.sleep(1.5 * (attempt + 1))
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return None


def main():
    os.makedirs(OUT, exist_ok=True)
    products = [p for p in get("https://api.exchange.coinbase.com/products") if p.get("quote_currency") == "USD"]
    summary = {}
    for n, p in enumerate(sorted(products, key=lambda p: p["id"])):
        pid, rows, t = p["id"], {}, START
        while t < END:
            stop = min(t + 300 * DAY, END)
            s = datetime.datetime.fromtimestamp(t, datetime.timezone.utc).isoformat()
            e = datetime.datetime.fromtimestamp(stop - DAY, datetime.timezone.utc).isoformat()
            data = get(f"https://api.exchange.coinbase.com/products/{pid}/candles?granularity=86400&start={s}&end={e}")
            for c in data or []:
                if START <= c[0] < END:
                    rows[c[0]] = [c[0], c[3], c[2], c[1], c[4], c[5]]
            t = stop
            time.sleep(0.13)
        ordered = [rows[k] for k in sorted(rows)]
        with open(os.path.join(OUT, f"{pid}.json"), "w") as f:
            json.dump(ordered, f, separators=(",", ":"))
        summary[pid] = {"status": p.get("status"), "rows": len(ordered),
                        "first": time.strftime("%Y-%m-%d", time.gmtime(ordered[0][0])) if ordered else None,
                        "last": time.strftime("%Y-%m-%d", time.gmtime(ordered[-1][0])) if ordered else None}
        if n % 25 == 0:
            print(f"{n + 1}/{len(products)} {pid}: {len(ordered)} days", file=sys.stderr, flush=True)
    with open(os.path.join(OUT, "_summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    have = [k for k, v in summary.items() if v["rows"]]
    print(f"done: {len(have)} of {len(summary)} USD pairs have daily candles", file=sys.stderr)


if __name__ == "__main__":
    main()
