"""
Minute bars for the prediction-engine test (PREREG_ENGINE.md).
==============================================================

  coinbase_1m(product, start, end)  Coinbase Exchange public candles, 300 per request,
                                    one cache file per UTC day so a long pull can resume.
  yahoo(sym, interval, prepost)     Yahoo chart API. Free intraday limits: 1m within the
                                    last 30 days, 5m/15m within 60, 60m within 730.
                                    Snapshot-cached per UTC date: the 1m window slides
                                    forward every day, so a run is pinned to a pull date.

Bars are [open_time, open, high, low, close, volume], stamped at the bar OPEN.
Cached under research/.cache/intraday. Pure stdlib + requests.
"""

import datetime as dt
import json
import os
import time
from zoneinfo import ZoneInfo

import certifi
import requests

import data

DIR = os.path.join(data.CACHE, "intraday")
ET = ZoneInfo("America/New_York")
COINBASE = "https://api.exchange.coinbase.com/products/{}/candles"
DAY = 86400
# Yahoo rejects a request that starts even a second outside its window, so stay inside.
YAHOO_DAYS = {"1m": 29.5, "5m": 59, "15m": 59, "60m": 729}
YAHOO_CHUNK = {"1m": 7, "5m": 30, "15m": 30, "60m": 365}


def _get(url, params, tries=8):
    for k in range(tries):
        try:
            r = requests.get(url, params=params, headers=data.UA, timeout=30,
                             verify=certifi.where())
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(2.0 * (k + 1))
                continue
            return r
        except requests.RequestException:
            time.sleep(2.0 * (k + 1))
    raise RuntimeError(f"gave up: {url} {params}")


def _ymd(t):
    return time.strftime("%Y%m%d", time.gmtime(t))


def coinbase_1m(product, start, end, quiet=False):
    """1-minute bars for whole UTC days in [start, end). Gaps are left as gaps."""
    os.makedirs(DIR, exist_ok=True)
    bars, fetched = [], 0
    for day in range(start, end, DAY):
        path = os.path.join(DIR, f"cb_{product}_{_ymd(day)}.json")
        if os.path.exists(path):
            with open(path) as f:
                bars.extend(json.load(f))
            continue
        got = {}
        for s in range(day, day + DAY, 300 * 60):
            # Coinbase's window is inclusive at both ends: 300 minutes = s .. s + 299 min.
            e = min(s + 299 * 60, day + DAY - 60)
            r = _get(COINBASE.format(product), {"granularity": 60, "start": s, "end": e})
            r.raise_for_status()
            for t, lo, hi, op, cl, vol in r.json():
                if day <= t < day + DAY:
                    got[int(t)] = [int(t), float(op), float(hi), float(lo), float(cl), float(vol)]
            time.sleep(0.13)
        rows = [got[t] for t in sorted(got)]
        with open(path, "w") as f:
            json.dump(rows, f)
        bars.extend(rows)
        fetched += 1
        if not quiet and fetched % 30 == 0:
            print(f"  {product}: fetched through {_ymd(day)} ({len(rows)} bars that day)", flush=True)
    return bars


def yahoo(sym, interval, prepost=False, snapshot=None, quiet=False):
    """Everything Yahoo serves for `sym` at `interval`, pinned to a UTC pull date."""
    os.makedirs(DIR, exist_ok=True)
    stamp = snapshot or _ymd(time.time())
    path = os.path.join(DIR, f"yh_{sym}_{interval}{'_pp' if prepost else ''}_{stamp}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    if snapshot and snapshot != _ymd(time.time()):
        raise FileNotFoundError(f"no {stamp} snapshot for {sym} {interval}; it can't be re-pulled")
    now = int(time.time())
    s = now - int(YAHOO_DAYS[interval] * DAY)
    got = {}
    while s < now:
        e = min(s + YAHOO_CHUNK[interval] * DAY, now)
        r = _get(data.CHART.format(sym), {"interval": interval, "period1": s, "period2": e,
                                          "includePrePost": "true" if prepost else "false"})
        res = (r.json().get("chart") or {}).get("result")
        if res:
            ts = res[0].get("timestamp") or []
            q = res[0]["indicators"]["quote"][0]
            for i, t in enumerate(ts):
                o, h, l, c, v = q["open"][i], q["high"][i], q["low"][i], q["close"][i], q["volume"][i]
                if None in (o, h, l, c) or c <= 0:
                    continue
                got[int(t)] = [int(t), float(o), float(h), float(l), float(c), float(v or 0.0)]
        elif not quiet:
            print(f"  {sym} {interval}: empty chunk {_ymd(s)}-{_ymd(e)} ({r.status_code})")
        s = e
        time.sleep(0.3)
    rows = [got[t] for t in sorted(got)]
    with open(path, "w") as f:
        json.dump(rows, f)
    if not quiet and rows:
        print(f"  {sym:<5} {interval:>3}{' +pre/post' if prepost else ''}: {len(rows)} bars "
              f"{et(rows[0][0]):%Y-%m-%d %H:%M} -> {et(rows[-1][0]):%Y-%m-%d %H:%M} ET")
    return rows


# ------------------------------------------------------------------ sessions

def et(t):
    return dt.datetime.fromtimestamp(t, ET)


def session_bounds(date):
    """(09:30, 16:00) ET for a datetime.date, as epoch seconds."""
    o = dt.datetime(date.year, date.month, date.day, 9, 30, tzinfo=ET)
    return int(o.timestamp()), int(o.timestamp()) + 390 * 60


def premarket_start(date):
    return int(dt.datetime(date.year, date.month, date.day, 4, 0, tzinfo=ET).timestamp())


if __name__ == "__main__":
    import sys
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    if what in ("crypto", "all"):
        start = int(dt.datetime(2025, 9, 11, tzinfo=dt.timezone.utc).timestamp())
        end = int(dt.datetime(2026, 9, 11, tzinfo=dt.timezone.utc).timestamp())
        for p in ("BTC-USD", "ETH-USD"):
            b = coinbase_1m(p, start, end)
            print(f"  {p}: {len(b)} bars of {(end - start) // 60} minutes", flush=True)
    if what in ("stocks", "all"):
        for sym in ("SPY", "QQQ", "NVDA", "TSLA"):
            yahoo(sym, "1m", prepost=True)
            for iv in ("5m", "15m", "60m"):
                yahoo(sym, iv)
