"""Pick the Live Arena micro-cap basket with a fixed rule, before any bot has run on it.

    python3 live_arena/make_basket.py

The rule, decided before looking at any results:
  - every stock in Nasdaq's US screener (NYSE, Nasdaq, NYSE American) worth $50M-$300M today
  - a US company, a price of at least $1, and at least 50,000 shares traded on the day the list is pulled
  - plain common stock: a letters-only symbol, with warrants, rights, units, preferred and depositary shares left out
  - sorted by symbol, shuffled with a fixed seed, and the first 30 kept that Yahoo has 721 daily candles for
    (about 3 years of trading)
Writes basket.json. The yardstick index fund is IWC (iShares Micro-Cap ETF).

A second, non-overlapping basket (see CONFIRM.md):
    python3 live_arena/make_basket.py --seed 20260913 --exclude basket.json --out basket_b.json
"""
import argparse
import json
import os
import random
import re
import time

import server

HERE = os.path.dirname(os.path.abspath(__file__))
SEED, N, MIN_BARS = 20260912, 30, 721
SCREENER = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&download=true"
NOT_COMMON = re.compile(r"warrant|\bright|\bunits?\b|preferred|depositary|\bnotes?\b|debenture", re.I)
CAVEAT = ("How the list was picked matters. These are today's micro-caps, so the list includes companies that shrank into "
          "this size over the last 3 years and leaves out ones that grew past it, which tilts it toward past losers. "
          "It also leaves out companies that went bust or were delisted, which tilts it the other way. "
          "Real trading costs on stocks this small are often 0.5% or more per trade, from the gap between the buy and "
          "sell price.")


def clean(name):
    return re.sub(r"\s+(Class [A-Z]\s+)?(Common Stock|Ordinary Shares|Common Shares)\b.*$", "", name).strip()


def main():
    ap = argparse.ArgumentParser(description="Pick a random micro-cap basket for Live Arena.")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--exclude", action="append", default=[], help="basket JSON whose stocks must not be reused")
    ap.add_argument("--out", default="basket.json")
    args = ap.parse_args()
    used = set()
    for path in args.exclude:
        with open(os.path.join(HERE, path)) as f:
            used |= {s["symbol"] for s in json.load(f)["stocks"]}

    pool = []
    for r in server.fetch_json(SCREENER)["data"]["rows"]:
        try:
            cap, price, vol = float(r["marketCap"] or 0), float(r["lastsale"].lstrip("$") or 0), float(r["volume"] or 0)
        except ValueError:
            continue
        if (50e6 <= cap < 300e6 and price >= 1 and vol >= 50_000 and r["country"] == "United States"
                and re.fullmatch(r"[A-Z]{1,5}", r["symbol"]) and not NOT_COMMON.search(r["name"])
                and r["symbol"] not in used):
            pool.append({"symbol": r["symbol"], "name": clean(r["name"]), "marketCap": cap, "sector": r["sector"] or "n/a"})
    pool.sort(key=lambda s: s["symbol"])
    random.Random(args.seed).shuffle(pool)

    picked, not_used = [], []
    for s in pool:
        if len(picked) == N:
            break
        try:
            bars = len(server.yahoo_rows(s["symbol"], "1440"))
        except Exception as e:
            not_used.append(f"{s['symbol']} ({e})")
            continue
        (picked if bars >= MIN_BARS else not_used).append(s if bars >= MIN_BARS else f"{s['symbol']} ({bars} candles)")
        time.sleep(0.2)

    out = {"label": "Micro-cap stocks", "made": time.strftime("%Y-%m-%d"), "seed": args.seed,
           "excluded_stocks_from": args.exclude, "pool_size": len(pool),
           "rule": __doc__.split("The rule, decided before looking at any results:")[1].split("Writes basket.json")[0].strip(),
           "index": {"symbol": "IWC", "name": "iShares Micro-Cap ETF"},
           "stocks": sorted(picked, key=lambda s: s["marketCap"]), "checked_but_not_used": not_used, "caveat": CAVEAT}
    with open(os.path.join(HERE, args.out), "w") as f:
        json.dump(out, f, indent=1)
    print(f"pool {len(pool)} stocks; picked {len(picked)}; skipped {len(not_used)} with too little history")
    for s in out["stocks"]:
        print(f"  {s['symbol']:<6} ${s['marketCap'] / 1e6:6.0f}M  {s['sector']:<24} {s['name']}")


if __name__ == "__main__":
    main()
