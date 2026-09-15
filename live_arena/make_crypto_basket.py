"""Pick the Live Arena crypto baskets with a fixed rule, before any bot has run on them.

    python3 live_arena/make_crypto_basket.py

The rule, decided before looking at any results:
  - coins with a USD market on Coinbase (online, trading enabled) that rank 21-250 by market cap on CoinGecko today
  - not a stablecoin, wrapped, bridged, staked or gold-backed token, and not a coin whose daily close barely moves
    (spread of daily closes under 3% of their average, which is a stablecoin by behavior)
  - Coinbase daily candles from 2022-01-01 or earlier, with no more than 2% of days missing since then
  - sorted by symbol, shuffled with a fixed seed and dealt into three equal groups (see CRYPTO_SEARCH.md):
      A, discovery       -> crypto_basket.json, the basket the app shows
      B, confirmation 1  -> crypto_confirm_b.json
      C, confirmation 2  -> crypto_confirm_c.json
Daily histories are saved under data/crypto/. BTC-USD is saved too, as the "just hold bitcoin" yardstick.
"""
import datetime as dt
import json
import os
import random
import re
import statistics
import time
import urllib.error

import server

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "crypto")
SEED = 20260914
DAY = 86400
START = int(dt.datetime(2022, 1, 1, tzinfo=dt.timezone.utc).timestamp())
COINBASE = "https://api.exchange.coinbase.com"
GECKO = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250&page=1"
ALIASES = {"CGLD": "CELO", "JUPITER": "JUP", "COSMOSDYDX": "DYDX", "ZETACHAIN": "ZETA", "CORECHAIN": "CORE",
           "MANTLE": "MNT"}   # Coinbase ticker -> CoinGecko symbol where they differ
NOT_A_COIN = re.compile(r"usd|tether|\bdai\b|euro|wrapped|bridged|staked|staking|restaked|\bgold\b|tokenized", re.I)
CAVEAT = ("How the coins were picked matters. They are ranked by today's size, so coins that shrank into this range since "
          "2022 are in, and coins that died or were delisted from Coinbase are out. The window starts in the 2022 crash, "
          "which flatters any bot that spends time in cash. Many exchanges charge small accounts well over 0.1% per trade, "
          "and big orders in small coins move the price.")


def iso(t):
    return dt.datetime.fromtimestamp(t, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(url):
    """server.fetch_json, retried through rate limits, server errors and dropped connections."""
    for attempt in range(6):
        try:
            return server.fetch_json(url)
        except urllib.error.HTTPError as e:
            if (e.code != 429 and e.code < 500) or attempt == 5:
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == 5:
                raise
        time.sleep(2 ** attempt)


def candles(product, start, end):
    """Coinbase daily candles [time, low, high, open, close, volume] from start to end inclusive, oldest first."""
    got, t = {}, start
    while t <= end:
        stop = min(t + 299 * DAY, end)
        for r in fetch(f"{COINBASE}/products/{product}/candles?granularity=86400&start={iso(t)}&end={iso(stop)}"):
            if start <= r[0] <= end:
                got[r[0]] = r
        t = stop + DAY
        time.sleep(0.15)
    return [got[k] for k in sorted(got)]


def path_of(product):
    return os.path.join("data", "crypto", f"{product}.json")


def saved(product, end):
    """Rows an earlier run already saved for `product`, if they run through `end`."""
    path = os.path.join(HERE, path_of(product))
    if not os.path.exists(path):
        return None
    with open(path) as f:
        rows = json.load(f)["result"][product]
    return rows if rows and rows[-1][0] == end else None


def save(product, rows):
    """Kraken's row layout [time, open, high, low, close, vwap, volume], which the app already reads."""
    with open(os.path.join(HERE, path_of(product)), "w") as f:
        json.dump({"error": [], "result": {product: [[r[0], r[3], r[2], r[1], r[4], None, r[5]] for r in rows]}}, f)
    return path_of(product)


def main():
    os.makedirs(DATA, exist_ok=True)
    end = int(time.time()) // DAY * DAY - DAY          # the last finished day
    expected = (end - START) // DAY + 1

    gecko = {}
    for c in fetch(GECKO):
        sym = c["symbol"].upper()
        if c.get("market_cap_rank") and (sym not in gecko or c["market_cap"] > gecko[sym]["market_cap"]):
            gecko[sym] = c
    products = [p for p in fetch(f"{COINBASE}/products")
                if p["quote_currency"] == "USD" and p.get("status") == "online" and not p.get("trading_disabled")]

    ranked, dropped = [], {"not ranked 21-250": 0, "stable/wrapped/staked by name": 0, "listed after 2022-01-01": 0,
                           "too many missing days": 0, "barely moves": 0}
    for p in sorted(products, key=lambda p: p["base_currency"]):
        g = gecko.get(ALIASES.get(p["base_currency"], p["base_currency"]))
        if not g or not 21 <= g["market_cap_rank"] <= 250:
            dropped["not ranked 21-250"] += 1
        elif NOT_A_COIN.search(g["name"]) or NOT_A_COIN.search(g["id"]):
            dropped["stable/wrapped/staked by name"] += 1
        else:
            ranked.append((p["id"], g))

    eligible = []
    for product, g in ranked:
        rows = saved(product, end)          # reuse histories an interrupted run already saved
        fresh = rows is None
        if fresh:
            if not candles(product, START - 30 * DAY, START):
                dropped["listed after 2022-01-01"] += 1
                continue
            rows = candles(product, START, end)
        if len(rows) < 0.98 * expected:
            dropped["too many missing days"] += 1
            continue
        closes = [r[4] for r in rows]       # the close is column 4 in both Coinbase's layout and the saved one
        if statistics.pstdev(closes) < 0.03 * statistics.mean(closes):
            dropped["barely moves"] += 1
            continue
        eligible.append({"symbol": product, "name": g["name"], "marketCap": g["market_cap"], "rank": g["market_cap_rank"],
                         "file": save(product, rows) if fresh else path_of(product)})
        print(f"  kept {product:<12} rank {g['market_cap_rank']:>3}  {len(rows)} days", flush=True)

    index = {"symbol": "BTC-USD", "name": "Bitcoin",
             "file": path_of("BTC-USD") if saved("BTC-USD", end) else save("BTC-USD", candles("BTC-USD", START, end))}
    eligible.sort(key=lambda s: s["symbol"])
    random.Random(SEED).shuffle(eligible)
    size = len(eligible) // 3
    groups = {"A": eligible[:len(eligible) - 2 * size], "B": eligible[len(eligible) - 2 * size:len(eligible) - size],
              "C": eligible[len(eligible) - size:]}
    rule = __doc__.split("The rule, decided before looking at any results:")[1].split("Daily histories")[0].strip()
    for key, file, role in (("A", "crypto_basket.json", "discovery"), ("B", "crypto_confirm_b.json", "confirmation 1"),
                            ("C", "crypto_confirm_c.json", "confirmation 2")):
        out = {"label": f"Crypto coins, group {key} ({role})", "unit": "coins", "source": "Coinbase daily",
               "made": time.strftime("%Y-%m-%d"), "seed": SEED, "window": [iso(START)[:10], iso(end)[:10]],
               "rule": rule, "index": index, "items": sorted(groups[key], key=lambda s: -s["marketCap"]),
               "caveat": CAVEAT}
        with open(os.path.join(HERE, file), "w") as f:
            json.dump(out, f, indent=1)
    print(f"\nCoinbase USD coins {len(products)}; ranked 21-250 and not stable/wrapped {len(ranked)}; eligible {len(eligible)}")
    print("dropped:", dropped)
    for key, g in groups.items():
        print(f"group {key} ({len(g)}): " + " ".join(s["symbol"].replace("-USD", "") for s in g))


if __name__ == "__main__":
    main()
