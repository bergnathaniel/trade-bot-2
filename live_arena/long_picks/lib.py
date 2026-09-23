"""Shared pieces for Long Picks: the two buckets, price fetching and eligibility (rules: PREREG_LONGPICKS.md).

Paper money only. Nothing here can place an order.
"""
import datetime
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import zoneinfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import server  # noqa: E402  the app's fetch_json, Yahoo and Coinbase readers

ROUNDS, PENDING, SCORED = (os.path.join(HERE, d) for d in ("rounds", "pending", "scored"))
LEDGER = os.path.join(HERE, "ledger.jsonl")
PREREG = os.path.join(HERE, "PREREG_LONGPICKS.md")
PREREG_SHA = os.path.join(HERE, "PREREG.sha256")
NEW_YORK = zoneinfo.ZoneInfo("America/New_York")
DAY = 86400

BUCKETS = {
    "moonshots": {"name": "Moonshots: low-cap meme coins", "cost": 2.0, "hold": 30, "sample": 30, "ref_name": "Bitcoin"},
    "holds": {"name": "Holds: US stocks", "cost": 0.02, "hold": 90, "sample": 60, "ref_name": "SPY"},
}
MAX_PICKS, SIMS, ROUNDS_NEEDED, MIN_PICKS, PERCENTILE = 3, 1000, 12, 20, 0.95
MEME_CAP, MEME_MIN_VOLUME = (1e6, 100e6), 100_000
STOCK_MIN_CAP, STOCK_MIN_PRICE, STOCK_MIN_SHARES = 300e6, 5, 250_000
SCREENER = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&download=true"
NOT_COMMON = re.compile(r"warrant|\bright|\bunits?\b|preferred|depositary|\bnotes?\b|debenture", re.I)
CG = "https://api.coingecko.com/api/v3"


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc)


def file_sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def rules_intact():
    with open(PREREG_SHA) as f:
        return f.read().split()[0] == file_sha(PREREG)


def cg_fetch(url, tries=6):
    """CoinGecko's free API allows only a few calls a minute, so wait and retry when it says slow down."""
    for k in range(tries):
        try:
            out = server.fetch_json(url)
            time.sleep(2.5)
            return out
        except urllib.error.HTTPError as e:
            if e.code == 429 and k < tries - 1:
                time.sleep(20 + 10 * k)
                continue
            raise


def meme_eligible():
    """{coingecko id: {symbol, name, cap, volume}} for meme coins worth $1M-$100M with $100k+ traded in 24 hours."""
    out = {}
    for page in range(1, 13):
        rows = cg_fetch(f"{CG}/coins/markets?vs_currency=usd&category=meme-token&order=market_cap_desc&per_page=250&page={page}")
        for r in rows:
            cap, vol = r.get("market_cap") or 0, r.get("total_volume") or 0
            if MEME_CAP[0] <= cap <= MEME_CAP[1] and vol >= MEME_MIN_VOLUME:
                out[r["id"]] = {"symbol": r["symbol"].upper(), "name": r["name"], "cap": cap, "volume": vol}
        if len(rows) < 250 or (rows and (rows[-1].get("market_cap") or 0) < MEME_CAP[0]):
            break
    return out


def stock_eligible():
    """{symbol: {cap, price, volume}} for US common stocks worth $300M+, price $5+, 250,000+ shares traded today."""
    out = {}
    for r in server.fetch_json(SCREENER)["data"]["rows"]:
        try:
            cap, price, vol = float(r["marketCap"] or 0), float(r["lastsale"].lstrip("$") or 0), float(r["volume"] or 0)
        except ValueError:
            continue
        if (r["country"] == "United States" and re.fullmatch(r"[A-Z]{1,5}", r["symbol"]) and not NOT_COMMON.search(r["name"])
                and cap >= STOCK_MIN_CAP and price >= STOCK_MIN_PRICE and vol >= STOCK_MIN_SHARES):
            out[r["symbol"]] = {"cap": cap, "price": price, "volume": vol}
    return out


def cg_prices(coin, since):
    """[(unix seconds, price)] daily from CoinGecko since `since`, or None if CoinGecko no longer has the coin."""
    days = int((now_utc().timestamp() - since) // DAY) + 3
    try:
        j = cg_fetch(f"{CG}/coins/{coin}/market_chart?vs_currency=usd&days={days}&interval=daily")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise
    return [(int(ms // 1000), p) for ms, p in j.get("prices", []) if p]


def daily_opens(symbol):
    """{date: open}: Coinbase for BTC-USD (UTC days), Yahoo for stocks (New York days)."""
    if symbol == "BTC-USD":
        return {datetime.datetime.fromtimestamp(r[0], datetime.timezone.utc).date(): r[1] for r in server.coinbase_rows(symbol)}
    return {datetime.datetime.fromtimestamp(r[0], NEW_YORK).date(): r[1] for r in server.yahoo_rows(symbol, "1440")}
