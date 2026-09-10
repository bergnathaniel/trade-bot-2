"""
Multi-asset daily data: fetch, cache, align.
===========================================

Everything the study needs comes from Yahoo's public chart endpoint. Pure
stdlib + requests, matching the rest of the project (no numpy/pandas here).

Bars are [epoch_seconds, open, high, low, close]. Yahoo's chart API returns
SPLIT+DIVIDEND ADJUSTED closes when adjclose is requested, which matters a
lot for the bond and dividend ETFs - TLT yields ~4%, and an unadjusted TLT
series makes any long-only strategy on it look far worse than reality.
"""

import json
import os
import time

import certifi
import requests

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
CHART = "https://query1.finance.yahoo.com/v8/finance/chart/{}"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
MAX_AGE = 24 * 3600

# ---------------------------------------------------------------- universes

# Retail-tradeable ETF proxies for the four classic trend asset classes, plus
# crypto. Inception years noted: the common window is what actually limits us.
ETF_UNIVERSE = {
    # ---- equity indices
    "SPY":  ("equity", "US large cap", 1993),
    "QQQ":  ("equity", "US tech", 1999),
    "IWM":  ("equity", "US small cap", 2000),
    "EFA":  ("equity", "Developed ex-US", 2001),
    "EEM":  ("equity", "Emerging markets", 2003),
    "EWJ":  ("equity", "Japan", 1996),
    # ---- fixed income
    "TLT":  ("bond", "US 20y+ Treasury", 2002),
    "IEF":  ("bond", "US 7-10y Treasury", 2002),
    "LQD":  ("bond", "US IG credit", 2002),
    "HYG":  ("bond", "US high yield", 2007),
    # ---- commodities
    "GLD":  ("commodity", "Gold", 2004),
    "SLV":  ("commodity", "Silver", 2006),
    "DBC":  ("commodity", "Broad commodity", 2006),
    "USO":  ("commodity", "Crude oil", 2006),
    "DBA":  ("commodity", "Agriculture", 2007),
    # ---- currency / real assets
    "UUP":  ("fx", "US dollar index", 2007),
    "FXE":  ("fx", "Euro", 2005),
    "FXY":  ("fx", "Yen", 2007),
    "VNQ":  ("reit", "US REITs", 2004),
}

CRYPTO_UNIVERSE = {
    "BTC-USD": ("crypto", "Bitcoin", 2014),
    "ETH-USD": ("crypto", "Ethereum", 2017),
}

# Continuous front-month futures. Messier (roll gaps, thinner Yahoo coverage)
# but this is the universe the trend literature actually tests, and it reaches
# back further than the ETFs do.
FUT_UNIVERSE = {
    "ES=F": ("equity", "S&P 500 future", 2000),
    "NQ=F": ("equity", "Nasdaq future", 2000),
    "YM=F": ("equity", "Dow future", 2002),
    "ZN=F": ("bond", "10y Note future", 2000),
    "ZB=F": ("bond", "30y Bond future", 2000),
    "GC=F": ("commodity", "Gold future", 2000),
    "SI=F": ("commodity", "Silver future", 2000),
    "CL=F": ("commodity", "Crude future", 2000),
    "NG=F": ("commodity", "Nat gas future", 2000),
    "HG=F": ("commodity", "Copper future", 2000),
    "ZC=F": ("commodity", "Corn future", 2000),
    "ZS=F": ("commodity", "Soybean future", 2000),
    "ZW=F": ("commodity", "Wheat future", 2000),
    "6E=F": ("fx", "Euro future", 2000),
    "6J=F": ("fx", "Yen future", 2000),
    "6B=F": ("fx", "Sterling future", 2000),
}


def fetch(sym, interval="1d", quiet=False, since=1993):
    """
    Adjusted daily bars for `sym`, cached for a day. [] on failure.

    Uses explicit period1/period2 epochs rather than range="max": Yahoo
    silently DOWNSAMPLES a "max" request to monthly bars, which quietly
    turns a daily study into a monthly one.
    """
    path = os.path.join(CACHE, f"{sym.replace('=','_').replace('-','_')}_{interval}.json")
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < MAX_AGE:
        try:
            return json.load(open(path))
        except json.JSONDecodeError:
            pass
    p1 = int(time.mktime((since, 1, 1, 0, 0, 0, 0, 1, 0)))
    p2 = int(time.time())
    try:
        r = requests.get(
            CHART.format(sym),
            params={"period1": p1, "period2": p2, "interval": interval,
                    "events": "div,split"},
            headers=UA, timeout=30, verify=certifi.where(),
        )
        res = r.json()["chart"]["result"][0]
        ts = res["timestamp"]
        q = res["indicators"]["quote"][0]
        # adjclose folds in dividends; scale OHL by the same factor so the
        # bar stays internally consistent (open-to-close arithmetic still works).
        adj = None
        ind = res["indicators"]
        if "adjclose" in ind and ind["adjclose"]:
            adj = ind["adjclose"][0].get("adjclose")
        bars = []
        for i, t in enumerate(ts):
            o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
            if None in (o, h, l, c) or c <= 0:
                continue
            f = 1.0
            if adj and i < len(adj) and adj[i]:
                f = adj[i] / c
            bars.append([int(t), float(o) * f, float(h) * f, float(l) * f, float(c) * f])
        if bars:
            json.dump(bars, open(path, "w"))
        if not quiet:
            print(f"  {sym:<8} {len(bars):>5} bars  {_ymd(bars[0][0])} -> {_ymd(bars[-1][0])}"
                  if bars else f"  {sym:<8} EMPTY")
        return bars
    except Exception as e:
        if not quiet:
            print(f"  {sym:<8} fetch failed ({type(e).__name__}: {e})")
        return []


def _ymd(epoch):
    return time.strftime("%Y-%m-%d", time.gmtime(epoch))


def load_universe(universe, min_bars=500, quiet=False):
    """{sym: bars} for everything that came back with enough history."""
    out = {}
    for sym in universe:
        bars = fetch(sym, quiet=quiet)
        if len(bars) >= min_bars:
            out[sym] = bars
    return out


def align(series, start=None):
    """
    Align {sym: bars} onto a shared calendar of trading DAYS (UTC date keys).

    Returns (dates, {sym: {date: bar}}). Symbols are NOT forced to a common
    start - the backtester handles ragged entry, which is the honest thing to
    do when EEM starts in 2003 and HYG in 2007. `start` ("YYYY-MM-DD") clips.
    """
    by_sym, all_dates = {}, set()
    for sym, bars in series.items():
        d = {}
        for b in bars:
            key = _ymd(b[0])
            if start and key < start:
                continue
            d[key] = b
        if d:
            by_sym[sym] = d
            all_dates |= d.keys()
    return sorted(all_dates), by_sym


def returns(bars):
    """Close-to-close simple returns, first element dropped."""
    return [bars[i][4] / bars[i - 1][4] - 1 for i in range(1, len(bars))]


if __name__ == "__main__":
    import sys
    which = sys.argv[1] if len(sys.argv) > 1 else "etf"
    uni = {"etf": ETF_UNIVERSE, "fut": FUT_UNIVERSE, "crypto": CRYPTO_UNIVERSE}[which]
    print(f"fetching {which} universe ({len(uni)} symbols)")
    got = load_universe(uni)
    print(f"\n{len(got)}/{len(uni)} usable")


# --------------------------------------------------------------- data hygiene

def clean_bars(bars, gap_floor=0.06, range_mult=4.0, lookback=60):
    """
    Neutralise contract-splice artefacts in continuous futures series.

    Yahoo's `XX=F` series splice front-month contracts together WITHOUT
    back-adjusting, so every roll can print a large close-to-close "return"
    that no trader could have earned. 6J=F, for instance, prints -90% on
    2001-12-17 and +904% the next day.

    The tell: a real move of that size drags the bar's own high-low range with
    it, whereas a splice is a jump BETWEEN bars that leaves each bar's internal
    range normal. So a gap is treated as an artefact when it is both
    (a) larger than `gap_floor` in absolute terms and (b) more than
    `range_mult` times the typical recent intraday range.

    Flagged bars get their whole series rebased so the jump disappears and the
    later history stays continuous - the same effect as back-adjusting the roll.
    Returns (cleaned_bars, n_flagged).
    """
    if len(bars) < 5:
        return list(bars), 0
    out = [list(b) for b in bars]
    ranges, flagged, adj = [], 0, 1.0
    for i in range(len(out)):
        o, h, l, c = out[i][1], out[i][2], out[i][3], out[i][4]
        rng = (h - l) / c if c > 0 else 0.0
        if i > 0:
            prev = bars[i - 1][4]
            gap = abs(c / prev - 1) if prev > 0 else 0.0
            typ = sorted(ranges[-lookback:])[len(ranges[-lookback:]) // 2] if ranges else rng
            if gap > gap_floor and gap > range_mult * max(typ, rng, 1e-6):
                adj *= prev / c                # rebase: splice the level back
                flagged += 1
        ranges.append(rng)
        for k in (1, 2, 3, 4):
            out[i][k] *= adj
    return out, flagged


def load_universe_clean(universe, min_bars=500, quiet=False, clean=True):
    """load_universe + splice cleaning. Reports what it touched."""
    out, total = {}, 0
    for sym in universe:
        bars = fetch(sym, quiet=True)
        if len(bars) < min_bars:
            continue
        if clean:
            bars, n = clean_bars(bars)
            total += n
            if n and not quiet:
                print(f"  {sym:<8} rebased {n} splice(s)")
        out[sym] = bars
    if not quiet:
        print(f"  cleaned {len(out)} series, {total} splice(s) neutralised")
    return out


def risk_free_daily(dates):
    """
    Daily risk-free rate aligned to `dates`, from ^IRX (13-week T-bill).

    ^IRX quotes an ANNUALISED discount rate in percent. Without this, every
    Sharpe in the study is really just return/vol, which flatters a low-vol
    strategy enormously - and a vol-targeted book financed at cash rates is
    exactly the kind of strategy that flattery would mislead us about.
    """
    bars = fetch("^IRX", quiet=True)
    if not bars:
        return {d: 0.0 for d in dates}
    lut, last = {}, 0.0
    have = {_ymd(b[0]): b[4] for b in bars}
    for d in dates:
        if d in have and have[d] is not None:
            last = have[d]
        lut[d] = max(0.0, last) / 100.0 / 252.0
    return lut


# Liquid US large caps with deep history, spread across sectors so that
# same-industry pairs can form. NOTE: these are companies that still exist in
# 2026, which is survivorship bias - see pairs.py for what that does to the
# result.
STOCK_UNIVERSE = {s: ("stock", s, 2000) for s in [
    # tech
    "AAPL","MSFT","INTC","CSCO","ORCL","IBM","TXN","QCOM","ADBE","AMD","MU","HPQ","ADI","AMAT",
    # comms / media
    "T","VZ","CMCSA","DIS","NFLX",
    # financials
    "JPM","BAC","WFC","C","GS","MS","USB","PNC","AXP","BK","SCHW","TRV","ALL","MMC","AIG",
    # health
    "JNJ","PFE","MRK","ABT","BMY","LLY","AMGN","GILD","UNH","CI","HUM","CAH","MCK","BDX","SYK",
    # staples
    "PG","KO","PEP","WMT","COST","CL","KMB","GIS","K","SYY","gis","gis",
    # energy / materials
    "XOM","CVX","COP","SLB","HAL","OXY","PSX","VLO","NEM","FCX","DD","DOW","LIN","APD","SHW",
    # industrials
    "GE","BA","CAT","DE","MMM","HON","UPS","UNP","CSX","NSC","LMT","NOC","RTX","EMR","ITW",
    # utilities / reits
    "NEE","DUK","SO","D","AEP","EXC","XEL","PSA","SPG","O","AMT",
    # discretionary
    "HD","LOW","MCD","SBUX","NKE","TGT","F","GM","TJX","YUM",
]}
