"""
Phase 5: four more well-known, survivorship-free ideas with long post-publication samples.
=========================================================================================
Exact rules: PREREG_PHASE5.md.

  H34  pre-holiday effect (Lakonishok-Smidt 1988, Ariel 1990): SPY on the session before NYSE holidays
  H35  options-expiration week (Stivers-Sun 2013): SPY in the week of each month's third Friday
  H36  Faber GTAA5 (2007): 5 ETFs at 20% each, each held only above its 10-month average
  H37  trend-filtered leverage (Gayed-Bilello 2016): SSO (2x S&P 500) above SPY's 200-day average, else cash
"""

import bisect
import collections
import datetime as dt
import random

import engine
import evaluate
import leakage
import stats
from h_calendar import _sim, cost_of
from h_common import UNREG_RF, clip, first_index, record, rf_list, yahoo
from h_phase4 import _combine, month_ends

PH_START = "1993-02-01"
OX_START, OX_OOS = "1993-02-01", "2014-01-01"
GT_ASSETS = ("SPY", "EFA", "IEF", "VNQ", "DBC")
GT_START, GT_OOS = "2006-12-01", "2008-01-01"
LV_START, LV_OOS = "2006-07-01", "2017-01-01"


def sessions_weights(n, idx):
    """close_exec weights that hold the close-to-close return of each session in `idx`."""
    W = [0.0] * n
    for j in idx:
        if j >= 1:
            W[j - 1] = 1.0
    return W


def _block_means(d, c, rf, held, lo, hi):
    on = [c[i] / c[i - 1] - 1 - rf[i] for i in range(1, len(d)) if lo <= d[i] < hi and i in held]
    off = [c[i] / c[i - 1] - 1 - rf[i] for i in range(1, len(d)) if lo <= d[i] < hi and i not in held]
    return {"held_day_mean_bp": round(stats.mean(on) * 1e4, 2), "other_day_mean_bp": round(stats.mean(off) * 1e4, 2),
            "share_days_held": round(len(on) / max(1, len(on) + len(off)), 3)}


# ----------------------------------------------------------------------- H34

def _easter(y):
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    g = (b - (b + 8) // 25 + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    return dt.date(y, (h + l_ - 7 * m + 114) // 31, (h + l_ - 7 * m + 114) % 31 + 1)


def _nth_weekday(y, month, wd, nth):
    """nth (1..5, or -1 = last) weekday `wd` (Mon=0) of a month."""
    if nth > 0:
        first = dt.date(y, month, 1)
        return first + dt.timedelta(days=(wd - first.weekday()) % 7 + 7 * (nth - 1))
    last = dt.date(y + (month == 12), month % 12 + 1, 1) - dt.timedelta(days=1)
    return last - dt.timedelta(days=(last.weekday() - wd) % 7)


def _observed(day, saturday_to_friday=True):
    if day.weekday() == 5:
        return day - dt.timedelta(days=1) if saturday_to_friday else None
    if day.weekday() == 6:
        return day + dt.timedelta(days=1)
    return day


def nyse_holidays(y):
    days = [_observed(dt.date(y, 1, 1), saturday_to_friday=False)]
    if y >= 1998:
        days.append(_nth_weekday(y, 1, 0, 3))
    days += [_nth_weekday(y, 2, 0, 3), _easter(y) - dt.timedelta(days=2), _nth_weekday(y, 5, 0, -1)]
    if y >= 2022:
        days.append(_observed(dt.date(y, 6, 19)))
    days += [_observed(dt.date(y, 7, 4)), _nth_weekday(y, 9, 0, 1), _nth_weekday(y, 11, 3, 4),
             _observed(dt.date(y, 12, 25))]
    return sorted(x.isoformat() for x in days if x is not None)


def preholiday_sessions(dates, back=1):
    """(indices of the `back` sessions before each weekday NYSE holiday, holidays SPY traded on)."""
    pos = {t: i for i, t in enumerate(dates)}
    hol = [h for y in range(int(dates[0][:4]), int(dates[-1][:4]) + 1) for h in nyse_holidays(y)
           if dates[0] < h < dates[-1]]
    idx, traded = set(), []
    for h in hol:
        if h in pos:
            traded.append(h)
            continue
        j = bisect.bisect_left(dates, h) - 1
        for k in range(back):
            if j - k >= 1:
                idx.add(j - k)
    return sorted(idx), traded


def ph_run(sym="SPY", back=1, mult=1.0, idx=None):
    y = yahoo(sym)
    d = y["dates"]
    ix = idx if idx is not None else preholiday_sessions(d, back)[0]
    return clip(_sim(sym, *engine.close_exec(sessions_weights(len(d), ix)), cost_of(sym) * mult), PH_START)


def h34():
    base, x2 = ph_run(), ph_run(mult=2.0)
    neighbours = [(s, r["dates"], r["net"]) for s in ("QQQ", "IWM", "DIA") for r in (ph_run(s),)]
    r2 = ph_run(back=2)
    neighbours.append(("last two sessions before", r2["dates"], r2["net"]))
    y = yahoo("SPY")
    d, c = y["dates"], y["close"]
    n, rf = len(d), rf_list(d)
    ix, traded = preholiday_sessions(d)
    near = {j for e in ix for j in range(e - 3, e + 4)}
    pool = collections.defaultdict(list)
    for i in range(1, n):
        if i not in near:
            pool[d[i][:4]].append(i)
    per_year = collections.Counter(d[e][:4] for e in ix)
    rng = random.Random(evaluate.SEED_PLACEBO)
    placebo = []
    for _ in range(1000):
        fake = sorted(p for yr, k in sorted(per_year.items()) for p in rng.sample(pool[yr], min(k, len(pool[yr]))))
        r = ph_run(idx=fake)
        placebo.append(stats.sharpe(r["net"][first_index(r["dates"], PH_START):]))
    held = set(ix)
    return [record(
        id="H34", cluster="PREHOLIDAY", name="Pre-holiday: SPY on the session before NYSE holidays", periods=252,
        hypothesis="Stocks earn an abnormal return on the last trading day before a market holiday",
        data="NYSE holiday rules 1993->, Yahoo SPY/QQQ/IWM/DIA (adjusted), ^IRX", costs="1bp/side SPY (2x: 2bp)",
        dates=base["dates"], net=base["net"], gross=base["gross"], net_2x=x2["net"], oos_start=PH_START,
        bench="SPY", implementable=True, survivor_universe=False, neighbours=neighbours, placebo=placebo,
        trades=engine.trades(base), expo=engine.exposure(base), turnover=base["turnover"], rf=base["rf"],
        leakage=leakage.truncation_test(lambda cut: sessions_weights(n, ix), n, lag=1),
        extra={"preholiday_sessions": len(ix), "rule_holidays_spy_traded_on": traded,
               "1993_2009": _block_means(d, c, rf, held, PH_START, "2010-01-01"),
               "2010_on": _block_means(d, c, rf, held, "2010-01-01", "9999")},
        notes=["Holiday calendar is rule-based and public in advance; truncation is structurally satisfied."],
        unregistered=[UNREG_RF])]


# ----------------------------------------------------------------------- H35

def _weeks(dates):
    by_week = collections.defaultdict(list)
    for i, t in enumerate(dates):
        day = dt.date.fromisoformat(t)
        by_week[day - dt.timedelta(days=day.weekday())].append((day.weekday(), i))
    months = sorted({t[:7] for t in dates})
    mondays = {m: _nth_weekday(int(m[:4]), int(m[5:7]), 4, 3) - dt.timedelta(days=4) for m in months}
    return by_week, mondays


def opex_sessions(dates, weekdays=(0, 1, 2, 3, 4), shifts=None, cache=None):
    by_week, mondays = cache if cache is not None else _weeks(dates)
    idx = []
    for m, monday in mondays.items():
        k = shifts.get(m, 0) if shifts else 0
        idx += [i for wd, i in by_week.get(monday + dt.timedelta(weeks=k), []) if wd in weekdays]
    return sorted(set(idx))


def ox_run(sym="SPY", weekdays=(0, 1, 2, 3, 4), mult=1.0, idx=None):
    y = yahoo(sym)
    d = y["dates"]
    ix = idx if idx is not None else opex_sessions(d, weekdays)
    return clip(_sim(sym, *engine.close_exec(sessions_weights(len(d), ix)), cost_of(sym) * mult), OX_START)


def h35():
    base, x2 = ox_run(), ox_run(mult=2.0)
    neighbours = [(s, r["dates"], r["net"]) for s in ("QQQ", "IWM", "DIA") for r in (ox_run(s),)]
    r = ox_run(weekdays=(3, 4))
    neighbours.append(("Thursday-Friday only", r["dates"], r["net"]))
    y = yahoo("SPY")
    d, c = y["dates"], y["close"]
    n, rf = len(d), rf_list(d)
    cache = _weeks(d)
    months = sorted(cache[1])
    rng = random.Random(evaluate.SEED_PLACEBO)
    placebo = []
    for _ in range(1000):
        shifts = {m: rng.choice((-2, -1, 1, 2)) for m in months}
        rr = ox_run(idx=opex_sessions(d, shifts=shifts, cache=cache))
        placebo.append(stats.sharpe(rr["net"][first_index(rr["dates"], OX_OOS):]))
    ix = opex_sessions(d, cache=cache)
    held = set(ix)
    return [record(
        id="H35", cluster="OPEX", name="Options-expiration week: SPY in the week of the third Friday", periods=252,
        hypothesis="Stock returns are higher in the week monthly options expire (hedge rebalancing)",
        data="Third-Friday calendar, Yahoo SPY/QQQ/IWM/DIA (adjusted), ^IRX", costs="1bp/side SPY (2x: 2bp)",
        dates=base["dates"], net=base["net"], gross=base["gross"], net_2x=x2["net"], oos_start=OX_OOS,
        bench="SPY", implementable=True, survivor_universe=False, neighbours=neighbours, placebo=placebo,
        trades=engine.trades(base), expo=engine.exposure(base), turnover=base["turnover"], rf=base["rf"],
        leakage=leakage.truncation_test(lambda cut: sessions_weights(n, ix), n, lag=1),
        extra={"pre_2014": _block_means(d, c, rf, held, OX_START, OX_OOS),
               "2014_on": _block_means(d, c, rf, held, OX_OOS, "9999")},
        notes=["Expiration calendar is public in advance; truncation is structurally satisfied."],
        unregistered=[UNREG_RF])]


# ----------------------------------------------------------------------- H36

def gtaa_decisions(assets=GT_ASSETS, months_n=10, cut_date=None):
    """{asset: [(SPY month-end index, held?)]} from adjusted month-end closes dated <= cut_date."""
    d = yahoo("SPY")["dates"]
    ends = month_ends(d)
    out = {}
    for s in assets:
        y = yahoo(s)
        cl = {t: v for t, v in zip(y["dates"], y["close"]) if cut_date is None or t <= cut_date}
        seq, hist = [], []
        for i in ends:
            v = cl.get(d[i])
            if v is None:
                continue
            hist.append(v)
            if len(hist) >= months_n:
                seq.append((i, v > sum(hist[-months_n:]) / months_n))
        out[s] = seq
    return out


def gtaa_run(dec, weight, mult=1.0):
    d = yahoo("SPY")["dates"]
    n = len(d)
    legs = {}
    for s, seq in dec.items():
        if not seq:
            continue
        wmap = {}
        for j, (i, on) in enumerate(seq):
            stop = seq[j + 1][0] if j + 1 < len(seq) else n
            for t in range(i, stop):
                wmap[d[t]] = weight if on else 0.0
        first = d[seq[0][0]]
        W, last = [], 0.0
        for t in yahoo(s)["dates"]:
            last = wmap.get(t, last if t > first else 0.0)
            W.append(last)
        legs[s] = _sim(s, *engine.next_open_exec(W), cost_of(s) * mult)
    return _combine(legs, GT_START)


def ew5_excess(assets=GT_ASSETS):
    """G2 benchmark for H36: daily-rebalanced equal weight of the same ETFs, excess of cash, no costs."""
    d = yahoo("SPY")["dates"]
    rf = dict(zip(d, rf_list(d)))
    cl = {s: dict(zip(yahoo(s)["dates"], yahoo(s)["close"])) for s in assets}
    out = {}
    for a, b in zip(d, d[1:]):
        rs = [cl[s][b] / cl[s][a] - 1 for s in assets if a in cl[s] and b in cl[s]]
        if len(rs) == len(assets):
            out[b] = sum(rs) / len(rs) - rf[b]
    return out


def h36():
    dec = gtaa_decisions()
    base, x2 = gtaa_run(dec, 0.2), gtaa_run(dec, 0.2, mult=2.0)
    variants = [("8-month average", gtaa_decisions(months_n=8), 0.2),
                ("12-month average", gtaa_decisions(months_n=12), 0.2),
                ("SPY/EFA/IEF only", gtaa_decisions(assets=("SPY", "EFA", "IEF")), 1 / 3),
                ("TLT instead of IEF", gtaa_decisions(assets=("SPY", "EFA", "TLT", "VNQ", "DBC")), 0.2)]
    neighbours = [(nm, r["dates"], r["net"]) for nm, dv, w in variants for r in (gtaa_run(dv, w),)]
    d = yahoo("SPY")["dates"]
    oos_j = {s: [j for j, (i, _) in enumerate(seq) if d[i] >= "2007-12-31"] for s, seq in dec.items()}
    rng = random.Random(evaluate.SEED_PLACEBO)
    placebo = []
    for _ in range(1000):
        fake = {}
        for s, seq in dec.items():
            vals = [seq[j][1] for j in oos_j[s]]
            rng.shuffle(vals)
            f = list(seq)
            for j, v in zip(oos_j[s], vals):
                f[j] = (seq[j][0], v)
            fake[s] = f
        r = gtaa_run(fake, 0.2)
        placebo.append(stats.sharpe(r["net"][first_index(r["dates"], GT_OOS):]))

    def vector(cut):
        v = [None] * len(d)
        for s, seq in gtaa_decisions(cut_date=None if cut is None else d[cut]).items():
            for i, on in seq:
                v[i] = (v[i] or ()) + ((s, on),)
        return v

    share = {s: round(sum(on for j, (i, on) in enumerate(seq) if j in set(oos_j[s])) / max(1, len(oos_j[s])), 3)
             for s, seq in dec.items()}
    return [record(
        id="H36", cluster="GTAA", name="Faber GTAA5: 5 ETFs held above their 10-month average", periods=252,
        hypothesis="Holding each asset class only above its 10-month moving average beats holding the same "
                   "assets throughout",
        data="Yahoo SPY/EFA/IEF/VNQ/DBC/TLT (adjusted) 2001->, ^IRX", costs="1bp SPY, 2bp other ETFs per side (2x)",
        dates=base["dates"], net=base["net"], gross=base["gross"], net_2x=x2["net"], oos_start=GT_OOS,
        bench="EW5", implementable=True, survivor_universe=False, neighbours=neighbours, placebo=placebo,
        turnover=base["turnover"], rf=base["rf"], leakage=leakage.truncation_test(vector, len(d), lag=0),
        extra={"oos_share_of_months_held": share},
        notes=["G2 benchmark EW5 = daily-rebalanced equal weight of the same five ETFs (no-signal control)."],
        unregistered=[UNREG_RF])]


# ----------------------------------------------------------------------- H37

def trend_states(sma_n=200, cut_date=None):
    """Per SPY session: adjusted close > SMA(sma_n) including that close; None before defined or after cut."""
    y = yahoo("SPY")
    d, c = y["dates"], y["close"]
    out = [None] * len(d)
    s = 0.0
    for i in range(len(d)):
        if cut_date is not None and d[i] > cut_date:
            break
        s += c[i]
        if i >= sma_n:
            s -= c[i - sma_n]
        if i >= sma_n - 1:
            out[i] = c[i] > s / sma_n
    return out


def lev_run(states, sym="SSO", off=None, mult=1.0):
    d = yahoo("SPY")["dates"]
    smap = dict(zip(d, states))
    legs = {}
    for leg, want in ((sym, True),) + (((off, False),) if off else ()):
        W, last = [], 0.0
        for t in yahoo(leg)["dates"]:
            st = smap.get(t)
            if st is not None:
                last = 1.0 if st == want else 0.0
            W.append(last)
        legs[leg] = _sim(leg, *engine.next_open_exec(W), cost_of(leg) * mult)
    return _combine(legs, LV_START)


def h37():
    states = trend_states()
    base, x2 = lev_run(states), lev_run(states, mult=2.0)
    variants = [("150-session average", trend_states(150), "SSO", None),
                ("250-session average", trend_states(250), "SSO", None),
                ("IEF instead of cash below the average", states, "SSO", "IEF"),
                ("UPRO (3x) instead of SSO", states, "UPRO", None)]
    neighbours = [(nm, r["dates"], r["net"]) for nm, st, sym, off in variants for r in (lev_run(st, sym, off),)]
    d = yahoo("SPY")["dates"]
    i0 = next(i for i, s in enumerate(states) if s is not None)
    core = states[i0:]
    rng = random.Random(evaluate.SEED_PLACEBO)
    placebo = []
    for _ in range(1000):
        k = rng.randint(63, 1260)
        r = lev_run([None] * i0 + core[-k:] + core[:-k])
        placebo.append(stats.sharpe(r["net"][first_index(r["dates"], LV_OOS):]))
    oos_states = [s for t, s in zip(d, states) if t >= LV_OOS and s is not None]
    sso_bh = lev_run([True if s is not None else None for s in states])
    return [record(
        id="H37", cluster="LEVTREND", name="Trend-filtered 2x: SSO above SPY's 200-day average, else cash",
        periods=252,
        hypothesis="Leverage held only in uptrends (above the 200-day average) beats the market after costs",
        data="Yahoo SPY/SSO/UPRO/IEF (adjusted) 2006->, ^IRX", costs="2bp/side SSO/UPRO/IEF (2x: 4bp)",
        dates=base["dates"], net=base["net"], gross=base["gross"], net_2x=x2["net"], oos_start=LV_OOS,
        bench="SPY", implementable=True, survivor_universe=False, neighbours=neighbours, placebo=placebo,
        turnover=base["turnover"], rf=base["rf"],
        leakage=leakage.truncation_test(lambda cut: trend_states(cut_date=None if cut is None else d[cut]),
                                        len(d), lag=0),
        extra={"oos_share_days_in_sso": round(sum(oos_states) / len(oos_states), 3),
               "oos_switches_per_year": round(sum(1 for a, b in zip(oos_states, oos_states[1:]) if a != b)
                                              / (len(oos_states) / 252), 2),
               "sso_buy_and_hold_oos_sharpe": round(stats.sharpe(
                   sso_bh["net"][first_index(sso_bh["dates"], LV_OOS):]), 3)},
        notes=["Leveraged-ETF fees and financing are inside SSO/UPRO prices."],
        unregistered=[UNREG_RF])]
