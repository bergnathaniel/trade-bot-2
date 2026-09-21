"""Shared pieces for Web Picks: the buckets, price fetching and the eligibility checks (rules: PREREG_WEBPICKS.md).

Paper money only. Nothing here can place an order.
"""
import datetime
import hashlib
import json
import os
import re
import sys
import zoneinfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import server  # noqa: E402  the app's fetch_json, Yahoo and Coinbase readers

ROUNDS = os.path.join(HERE, "rounds")
PENDING = os.path.join(HERE, "pending")
LEDGER = os.path.join(HERE, "ledger.jsonl")
PREREG = os.path.join(HERE, "PREREG_WEBPICKS.md")
PREREG_SHA = os.path.join(HERE, "PREREG.sha256")
NEW_YORK = zoneinfo.ZoneInfo("America/New_York")

BUCKETS = {
    "stocks": {"name": "US stocks", "fee": 0.02, "ref": "SPY", "ref_name": "SPY"},
    "micro": {"name": "Micro-cap stocks", "fee": 0.50, "ref": "IWC", "ref_name": "IWC"},
    "crypto": {"name": "Crypto and meme coins", "fee": 0.25, "ref": "BTC-USD", "ref_name": "Bitcoin"},
}
MAX_PICKS, HOLD_DAYS, SAMPLE, SIMS = 3, 7, 60, 1000
ROUNDS_NEEDED, MIN_PICKS, PERCENTILE = 12, 20, 0.95
MIN_DOLLAR_VOLUME = 250_000
SCREENER = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&download=true"
NOT_COMMON = re.compile(r"warrant|\bright|\bunits?\b|preferred|depositary|\bnotes?\b|debenture", re.I)
STABLES = {"USDT", "USDC", "DAI", "PYUSD", "USDS", "GUSD", "PAX", "USDP", "TUSD", "FDUSD", "EURC", "RLUSD", "USD1", "UST"}
MEMES = {"DOGE", "SHIB", "PEPE", "BONK", "WIF", "FLOKI", "TRUMP", "PENGU", "POPCAT", "MOG", "BRETT", "TURBO", "FARTCOIN",
         "PNUT", "MEW", "MOODENG", "GOAT", "SPX", "MEME", "NEIRO", "BOME", "DOGS", "HMSTR"}
STOCK_RULES = {   # bucket: (min market cap, max market cap, min price, min shares traded)
    "stocks": (2e9, float("inf"), 5, 500_000),
    "micro": (50e6, 300e6, 1, 50_000),
}


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def today():
    return now_utc().date()


def file_sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def rules_intact():
    with open(PREREG_SHA) as f:
        return f.read().split()[0] == file_sha(PREREG)


def screener_rows():
    """Every stock Nasdaq's screener lists that meets a bucket's rule today: {bucket: {symbol: {cap, price, volume}}}."""
    out = {b: {} for b in STOCK_RULES}
    for r in server.fetch_json(SCREENER)["data"]["rows"]:
        try:
            cap, price, vol = float(r["marketCap"] or 0), float(r["lastsale"].lstrip("$") or 0), float(r["volume"] or 0)
        except ValueError:
            continue
        if r["country"] != "United States" or not re.fullmatch(r"[A-Z]{1,5}", r["symbol"]) or NOT_COMMON.search(r["name"]):
            continue
        for bucket, (lo, hi, min_price, min_vol) in STOCK_RULES.items():
            if lo <= cap < hi and price >= min_price and vol >= min_vol:
                out[bucket][r["symbol"]] = {"cap": cap, "price": price, "volume": vol}
    return out


def coinbase_products():
    """USD markets that are online and open, minus stablecoins."""
    out = []
    for p in server.fetch_json("https://api.exchange.coinbase.com/products"):
        base = p.get("base_currency", "")
        if (p.get("quote_currency") == "USD" and p.get("status") == "online" and not p.get("trading_disabled")
                and not p.get("fx_stablecoin") and base not in STABLES):
            out.append(p["id"])
    return sorted(out)


def coin_id(symbol):
    symbol = symbol.upper().strip()
    return symbol if symbol.endswith("-USD") else symbol + "-USD"


def coin_rows(product):
    return server.coinbase_rows(product)


def dollar_volume(rows):
    """Average dollars traded per day over the last 7 finished days."""
    last = rows[-7:]
    return sum(r[4] * r[6] for r in last) / len(last) if last else 0.0


def stable_like(rows):
    closes = [r[4] for r in rows[-30:]]
    return len(closes) >= 10 and (max(closes) - min(closes)) / (sum(closes) / len(closes)) < 0.03


def stock_rows(symbol):
    return server.yahoo_rows(symbol, "1440")


def bar_date(bucket, t):
    """The trading day a daily candle belongs to: New York's date for stocks, UTC's for coins."""
    if bucket == "crypto":
        return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).date()
    return datetime.datetime.fromtimestamp(t, NEW_YORK).date()


def opens(bucket, symbol):
    """{date: open price} from the daily candles. Stocks come from Yahoo, coins from Coinbase (finished days only)."""
    rows = coin_rows(coin_id(symbol)) if bucket == "crypto" else stock_rows(symbol)
    return {bar_date(bucket, r[0]): r[1] for r in rows}


def fills(day_opens, lock_day):
    """(entry_date, exit_date) following the fill rules, or None for a side that has no candle yet."""
    dates = sorted(day_opens)
    entry = next((d for d in dates if d > lock_day), None)
    if entry is None:
        return None, None
    exit_ = next((d for d in dates if d >= entry + datetime.timedelta(days=HOLD_DAYS)), None)
    return entry, exit_
