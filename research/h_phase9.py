"""
Phase 9: crypto trend-following ensemble (Zarattini, Pagani & Barbon 2025).
===========================================================================
Exact rules: PREREG_PHASE9.md.

  H46  each UTC month-end, the 20 most-traded Coinbase USD coins (a year of history, a median daily dollar volume of
       $2M or more over 30 days, stablecoins and wrapped tokens excluded) get a 1/20 slot each. A slot holds the share
       of 9 Donchian breakout models (5 to 360 days, midpoint trailing stops) that are long, sized to 25% yearly
       volatility and capped at twice the slot, with the whole book capped at 100%.
  H47  the same ensemble and sizing on bitcoin alone, capped at 100%.
Weights decided at each daily close earn the next day's close-to-close return. Costs: 0.25% per side on turnover.
"""

import bisect
import collections
import datetime
import functools
import glob
import json
import math
import os
import random

import data
import evaluate
import leakage
import stats
from h_common import record

HERE = os.path.dirname(os.path.abspath(__file__))
COINBASE = os.path.join(HERE, "data", "coinbase_daily")
FIRST_DAY, START, OOS, LAST_DAY = "2022-01-01", "2023-01-01", "2025-04-01", "2026-09-12"
IS_END = "2025-03-31"
LOOKBACKS = (5, 10, 20, 30, 60, 90, 150, 250, 360)
FEE = 0.0025
VOL_DAYS, VOL_TARGET, SLOT_CAP, GROSS_CAP = 90, 0.25, 2.0, 1.0
TOP, MIN_DOLLAR_VOLUME, MIN_HISTORY, VOLUME_DAYS = 20, 2_000_000.0, 365, 30
PERIODS = 365
# stablecoins, tokenized gold, and wrapped or staked copies of other coins: not separate bets on a trend
EXCLUDED = {"USDT", "USDC", "DAI", "PAX", "USDP", "GUSD", "PYUSD", "EURC", "EUROC", "TUSD", "BUSD", "UST", "FDUSD",
            "USDS", "LUSD", "RAI", "GYEN", "MUSD", "FRAX", "USDE", "CUSD", "PAXG", "XAUT", "WBTC", "WETH", "CBETH",
            "CBBTC", "LSETH", "MSOL", "STETH", "WSTETH", "JITOSOL"}


def _day(ts):
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).strftime("%Y-%m-%d")


# ------------------------------------------------------------------------------------------------ data

@functools.lru_cache(maxsize=None)
def market():
    """Every usable Coinbase USD pair on one calendar of UTC days.

    close: forward-filled across days without trades; None before the first candle and after the last one.
    traded: whether the day had a real candle. dollars: close x volume (0 on days without trades).
    """
    first = datetime.date.fromisoformat(FIRST_DAY)
    days = [(first + datetime.timedelta(k)).isoformat()
            for k in range((datetime.date.fromisoformat(LAST_DAY) - first).days + 1)]
    index = {d: i for i, d in enumerate(days)}
    coins = {}
    for path in sorted(glob.glob(os.path.join(COINBASE, "*-USD.json"))):
        pid = os.path.basename(path)[:-5]
        if pid.split("-")[0] in EXCLUDED:
            continue
        with open(path) as f:
            rows = json.load(f)
        raw = {index[_day(r[0])]: r for r in rows if _day(r[0]) in index and r[4] > 0}
        if not raw:
            continue
        close, traded, dollars, last = [None] * len(days), [False] * len(days), [0.0] * len(days), None
        for i in range(min(raw), max(raw) + 1):
            if i in raw:
                last = raw[i][4]
                traded[i], dollars[i] = True, raw[i][4] * raw[i][5]
            close[i] = last
        coins[pid] = {"close": close, "traded": traded, "dollars": dollars}
    return days, coins


@functools.lru_cache(maxsize=None)
def cash():
    """^IRX (13-week T-bill, annualized %) forward-filled across every calendar day, as a daily rate over 365 days."""
    days, _ = market()
    have = {data._ymd(b[0]): b[4] for b in data.fetch("^IRX", quiet=True) or []}
    out, last = [], 0.0
    for d in days:
        if have.get(d) is not None:
            last = have[d]
        out.append(max(0.0, last) / 100.0 / PERIODS)
    return out


def btc_excess():
    """{date: bitcoin's daily return minus cash}, the G2 benchmark."""
    days, coins = market()
    rf, c = cash(), coins["BTC-USD"]["close"]
    return {days[t]: c[t] / c[t - 1] - 1 - rf[t] for t in range(days.index(START), len(days)) if c[t] and c[t - 1]}


# ------------------------------------------------------------------------------------------------ rules

def month_ends(days):
    return [i for i in range(len(days) - 1) if days[i][:7] != days[i + 1][:7]]


def universes(days, coins, top):
    """{month-end index: the coins picked at that close}, ranked by median 30-day dollar volume."""
    out = {}
    for m in month_ends(days):
        ranked = []
        for pid, c in coins.items():
            close = c["close"]
            if m < max(MIN_HISTORY, VOLUME_DAYS) or close[m] is None or close[m - MIN_HISTORY] is None:
                continue
            if not any(c["traded"][m - k] for k in range(3)):
                continue
            vols = sorted(c["dollars"][m - VOLUME_DAYS + 1:m + 1])
            median = (vols[VOLUME_DAYS // 2 - 1] + vols[VOLUME_DAYS // 2]) / 2
            if median >= MIN_DOLLAR_VOLUME:
                ranked.append((-median, pid))
        out[m] = [pid for _, pid in sorted(ranked)[:top]]
    return out


def _rolling(values, n, pick):
    """max or min of the last n values, including each one (None until n values exist)."""
    out, q = [None] * len(values), collections.deque()
    for i, v in enumerate(values):
        while q and (v >= values[q[-1]] if pick is max else v <= values[q[-1]]):
            q.pop()
        q.append(i)
        if q[0] <= i - n:
            q.popleft()
        if i >= n - 1:
            out[i] = values[q[0]]
    return out


def ensemble(close, lookbacks, a, b):
    """The share of the Donchian models that are long after each close from index a to b (the coin's life)."""
    seg, out = close[a:b + 1], [None] * len(close)
    models = [(L, _rolling(seg, L, max), _rolling(seg, L, min)) for L in lookbacks]
    long_, stop = {L: False for L in lookbacks}, {L: 0.0 for L in lookbacks}
    for k, c in enumerate(seg):
        votes = ready = 0
        for L, hi, lo in models:
            if k < L:   # needs L earlier closes
                continue
            ready += 1
            mid = (hi[k] + lo[k]) / 2
            if long_[L] and c < stop[L]:
                long_[L] = False
            elif not long_[L] and c > hi[k - 1]:
                long_[L], stop[L] = True, mid
            if long_[L]:
                stop[L] = max(stop[L], mid)
                votes += 1
        out[a + k] = votes / len(lookbacks) if ready else None
    return out


def volatility(close, a, b, n=VOL_DAYS):
    """Annualized standard deviation of the last n daily returns (None until there are n)."""
    out, window, s, q = [None] * len(close), collections.deque(), 0.0, 0.0
    for i in range(a + 1, b + 1):
        r = close[i] / close[i - 1] - 1
        window.append(r)
        s, q = s + r, q + r * r
        if len(window) > n:
            old = window.popleft()
            s, q = s - old, q - old * old
        if len(window) == n:
            out[i] = math.sqrt(max(q - s * s / n, 0.0) / (n - 1) * PERIODS)
    return out


def build(top=TOP, lookbacks=LOOKBACKS, only=None, cut=None):
    """Everything the weights need, using no data after day index `cut`."""
    days, coins = market()
    n = len(days) if cut is None else cut + 1
    view = coins if cut is None else {pid: {k: v[:n] for k, v in c.items()} for pid, c in coins.items()}
    if only:
        view = {pid: view[pid] for pid in only if pid in view}
        member = [[pid for pid in only if pid in view and view[pid]["close"][t] is not None] for t in range(n)]
        ever = sorted(view)
    else:
        picks = universes(days[:n], view, top)
        ends, member = sorted(picks), []
        for t in range(n):
            j = bisect.bisect_right(ends, t) - 1
            member.append(picks[ends[j]] if j >= 0 else [])
        ever = sorted({p for v in picks.values() for p in v})
    sig, vol = {}, {}
    for pid in ever:
        close = view[pid]["close"]
        alive = [i for i, c in enumerate(close) if c is not None]
        if alive:
            sig[pid] = ensemble(close, lookbacks, alive[0], alive[-1])
            vol[pid] = volatility(close, alive[0], alive[-1])
    return {"days": days[:n], "view": view, "sig": sig, "vol": vol, "member": member}


def weights(B, slots=TOP, target=VOL_TARGET, slot_cap=SLOT_CAP, gross_cap=GROSS_CAP, sized=True, band=0.0, signals=None):
    """Target weights decided at each close, as a list of {coin: weight}."""
    sig, out, prev = signals or B["sig"], [], {}
    for t, members in enumerate(B["member"]):
        want = {}
        for pid in members:
            s = sig.get(pid, [None] * (t + 1))[t]
            if not s or B["view"][pid]["close"][t] is None:
                continue
            if sized:
                v = B["vol"][pid][t]
                if not v:
                    continue
                want[pid] = s * min(slot_cap, target / v) / slots
            else:
                want[pid] = s / slots
        if band:
            for p in want:
                old = prev.get(p, 0.0)
                if old > 0 and abs(want[p] - old) <= band * max(want[p], old):
                    want[p] = old
        gross = sum(want.values())
        if gross > gross_cap:
            want = {p: w * gross_cap / gross for p, w in want.items()}
        out.append(want)
        prev = want
    return out


def run(B, W, fee=FEE, start=START):
    """Daily excess-of-cash returns from `start`: weights decided at close t earn day t+1's close-to-close return."""
    days, view, rf = B["days"], B["view"], cash()
    i0 = days.index(start)
    dates, gross, net, turnover, expo = [], [], [], [], []
    for t in range(i0 - 1, len(days) - 1):
        w, before = W[t], (W[t - 1] if t > 0 else {})
        g = 0.0
        for pid, x in w.items():
            c0, c1 = view[pid]["close"][t], view[pid]["close"][t + 1]
            if c0 is not None and c1 is not None:   # a coin that stopped trading earns nothing more
                g += x * (c1 / c0 - 1 - rf[t + 1])
        trade = sum(abs(w.get(p, 0.0) - before.get(p, 0.0)) for p in set(w) | set(before))
        dates.append(days[t + 1])
        gross.append(g)
        net.append(g - fee * trade)
        turnover.append(trade)
        expo.append(sum(w.values()))
    return {"dates": dates, "gross": gross, "net": net, "turnover": turnover, "expo": expo, "rf": rf[i0:len(days)]}


def placebo(B, kwargs, draws=1000):
    """Out-of-sample Sharpes of the same book with every coin's signal slid circularly to a random point in that window."""
    days = B["days"]
    o0 = days.index(OOS)
    L = len(days) - o0
    rng, out = random.Random(evaluate.SEED_PLACEBO), []
    for _ in range(draws):
        shifted = {}
        for pid, s in B["sig"].items():
            k = rng.randrange(30, L - 30)
            shifted[pid] = s[:o0] + [s[o0 + (j + k) % L] for j in range(L)]
        r = run(B, weights(B, signals=shifted, **kwargs), start=OOS)
        out.append(stats.sharpe(r["net"], periods=PERIODS))
    return out


def weight_vector(kwargs, build_kwargs, cut):
    W = weights(build(cut=cut, **build_kwargs), **kwargs)
    return [tuple(sorted((p, round(x, 12)) for p, x in w.items())) for w in W]


def _window(r, lo, hi):
    xs = [x for d, x in zip(r["dates"], r["net"]) if lo <= d <= hi]
    return {"excess_cagr": round(stats.ann_return(xs, PERIODS), 4), "sharpe": round(stats.sharpe(xs, periods=PERIODS), 2),
            "days": len(xs)}


def _common_extra(B, r, W):
    oos = [i for i, d in enumerate(r["dates"]) if d >= OOS]
    expo = [r["expo"][i] for i in oos]
    btc = btc_excess()
    bx = [btc[d] for d in r["dates"] if d >= OOS and d in btc]
    return {
        "in_sample_2023_to_2025_03": _window(r, START, IS_END),
        "paper_sharpe_2015_2025": 1.58,
        "oos_sharpe_at_0.10pct": round(stats.sharpe(run(B, W, fee=0.001, start=OOS)["net"], periods=PERIODS), 2),
        "oos_sharpe_at_0.50pct": round(stats.sharpe(run(B, W, fee=0.005, start=OOS)["net"], periods=PERIODS), 2),
        "oos_avg_gross_exposure": round(sum(expo) / len(expo), 3),
        "oos_share_of_days_invested": round(sum(e > 0 for e in expo) / len(expo), 3),
        "btc_oos": {"excess_cagr": round(stats.ann_return(bx, PERIODS), 4), "sharpe": round(stats.sharpe(bx, periods=PERIODS), 2)},
    }


NOTES_COMMON = [
    "Rules follow CXO Advisory's summary of the paper and a public pre-registration of the same strategy; the PDF "
    "couldn't be retrieved. Details neither states are Claude's choices, marked in PREREG_PHASE9.md.",
    "Out-of-sample is only 1.45 years: even a strategy that works as published would probably fail G1 or G2 (see the "
    "power note in PREREG_PHASE9.md).",
]
UNREG = ["Coinbase-only universe; the paper aggregates volume across exchanges and all coins since 2015.",
         "Close-to-close returns on UTC daily candles; weights are daily targets, and drift between days is ignored.",
         "^IRX is forward-filled across weekends and holidays."]


def h46():
    base = {"slots": TOP}
    B = build()
    W = weights(B, **base)
    r, r2 = run(B, W), run(B, W, fee=2 * FEE)
    B10, B20 = build(top=10), build(lookbacks=LOOKBACKS[2:])
    variants = [("gross up to 200% (the paper's cap; not implementable on spot)", B, {"slots": TOP, "gross_cap": 2.0}),
                ("50% volatility target", B, {"slots": TOP, "target": 0.5}),
                ("top 10 coins", B10, {"slots": 10}),
                ("lookbacks 20-360 only", B20, {"slots": TOP}),
                ("no volatility sizing", B, {"slots": TOP, "sized": False}),
                ("10% no-trade band", B, {"slots": TOP, "band": 0.10})]
    neighbours = [(nm, x["dates"], x["net"]) for nm, b, kw in variants for x in (run(b, weights(b, **kw)),)]
    days = B["days"]
    ew = run(B, [{p: 1 / len(m) for p in m if B["view"][p]["close"][t] is not None} if m else {}
                 for t, m in enumerate(B["member"])], fee=0.0)
    held = collections.Counter(p for d, w in zip(days, W) if d >= OOS for p in w)
    n_oos = sum(d >= OOS for d in days)
    extra = _common_extra(B, r, W)
    extra.update({
        "coins_ever_picked": len(B["sig"]),
        "oos_most_held": {p: round(c / n_oos, 3) for p, c in held.most_common(12)},
        "equal_weight_monthly_picks_no_costs_oos": _window(ew, OOS, LAST_DAY),
    })
    return [record(
        id="H46", cluster="CRYPTOTREND", periods=PERIODS,
        name="Crypto trend ensemble: top 20 Coinbase coins, 9 Donchian models, 25% vol target",
        hypothesis="Long-only trend-following on the 20 most-traded coins, sized by volatility, keeps beating holding "
                   "bitcoin after its 2025 publication (Zarattini, Pagani & Barbon)",
        data="Coinbase Exchange daily candles, all USD pairs incl. delisted, 2022-01 -> 2026-09-12; ^IRX",
        costs="0.25%/side (2x: 0.50%)",
        dates=r["dates"], net=r["net"], gross=r["gross"], net_2x=r2["net"], oos_start=OOS, bench="BTC",
        implementable=True, survivor_universe=False, neighbours=neighbours, placebo=placebo(B, base),
        turnover=r["turnover"], rf=r["rf"],
        leakage=leakage.truncation_test(lambda cut: weight_vector(base, {}, cut), len(days), lag=0),
        extra=extra, notes=NOTES_COMMON, unregistered=UNREG)]


def h47():
    base, bk = {"slots": 1}, {"only": ("BTC-USD",)}
    B = build(**bk)
    W = weights(B, **base)
    r, r2 = run(B, W), run(B, W, fee=2 * FEE)
    B20 = build(lookbacks=LOOKBACKS[2:], **bk)
    variants = [("cap 200% (not implementable on spot)", B, {"slots": 1, "gross_cap": 2.0}),
                ("50% volatility target", B, {"slots": 1, "target": 0.5}),
                ("lookbacks 20-360 only", B20, {"slots": 1}),
                ("no volatility sizing", B, {"slots": 1, "sized": False}),
                ("10% no-trade band", B, {"slots": 1, "band": 0.10})]
    neighbours = [(nm, x["dates"], x["net"]) for nm, b, kw in variants for x in (run(b, weights(b, **kw)),)]
    return [record(
        id="H47", cluster="CRYPTOTREND", periods=PERIODS,
        name="Bitcoin trend ensemble: 9 Donchian models, 25% vol target",
        hypothesis="The same long-only trend ensemble on bitcoin alone beats holding bitcoin after publication",
        data="Coinbase Exchange BTC-USD daily candles 2022-01 -> 2026-09-12; ^IRX", costs="0.25%/side (2x: 0.50%)",
        dates=r["dates"], net=r["net"], gross=r["gross"], net_2x=r2["net"], oos_start=OOS, bench="BTC",
        implementable=True, survivor_universe=False, neighbours=neighbours, placebo=placebo(B, base),
        turnover=r["turnover"], rf=r["rf"],
        leakage=leakage.truncation_test(lambda cut: weight_vector(base, bk, cut), len(B["days"]), lag=0),
        extra=_common_extra(B, r, W), notes=NOTES_COMMON, unregistered=UNREG)]
