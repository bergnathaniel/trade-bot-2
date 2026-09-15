"""
Phase 4: three untested, survivorship-free ideas with long post-publication samples.
===================================================================================
Exact rules: PREREG_PHASE4.md.

  H31  dual momentum (Antonacci 2012): the stronger of SPY/EFA over 12 months if it beats T-bills, else AGG
  H32  Halloween / "Sell in May" (Bouman & Jacobsen 2002): SPY November-April, cash May-October
  H33  FOMC-cycle even weeks (Cieslak, Morse & Vissing-Jorgensen 2019): SPY in weeks 0/2/4/6 of cycle time
"""

import random

import engine
import evaluate
import leakage
import sources
import stats
from h_calendar import _sim, cost_of, event_index
from h_common import UNREG_RF, clip, first_index, record, rf_list, yahoo

GEM_START, GEM_OOS = "2004-10-01", "2013-01-01"
HW_START, HW_OOS = "1993-02-01", "2003-01-01"
FC_START, FC_OOS = "1994-02-01", "2016-01-01"
EVEN = frozenset(set(range(-1, 4)) | set(range(9, 14)) | set(range(19, 24)) | set(range(29, 34)))
EVEN_246 = frozenset(set(range(9, 14)) | set(range(19, 24)) | set(range(29, 34)))


def month_ends(dates):
    """Indices of the last session of each COMPLETE calendar month."""
    return [i for i in range(len(dates) - 1) if dates[i + 1][:7] != dates[i][:7]]


def _combine(legs, start):
    """Sum per-date gross/net/turnover of one-asset legs (weights sum to <= 1) on the first leg's calendar."""
    first = next(iter(legs.values()))
    maps = {s: {t: i for i, t in enumerate(r["dates"])} for s, r in legs.items()}
    out = {k: [] for k in ("dates", "gross", "net", "turnover", "rf")}
    for i, t in enumerate(first["dates"]):
        out["dates"].append(t)
        for k in ("gross", "net", "turnover"):
            out[k].append(sum(r[k][maps[s][t]] for s, r in legs.items() if t in maps[s]))
        out["rf"].append(first["rf"][i])
    return clip(out, start)


# ----------------------------------------------------------------------- H31

def gem_decisions(lookback=12, bond="AGG", hurdle="tbill", cut_date=None):
    """[(SPY session index, asset)] decided at each month-end close, using prices dated <= cut_date only."""
    d = yahoo("SPY")["dates"]
    keep = (lambda t: True) if cut_date is None else (lambda t: t <= cut_date)
    closes = {s: {t: c for t, c in zip(yahoo(s)["dates"], yahoo(s)["close"]) if keep(t)}
              for s in ("SPY", "EFA", bond)}
    rf = {t: r for t, r in zip(d, rf_list(d)) if keep(t)}
    ends = month_ends(d)
    out = []
    for j in range(lookback, len(ends)):
        i, i0 = ends[j], ends[j - lookback]
        ret = {}
        for s in ("SPY", "EFA", bond):
            a, b = closes[s].get(d[i0]), closes[s].get(d[i])
            if a and b:
                ret[s] = b / a - 1
        if len(ret) < 3 or any(d[k] not in rf for k in range(i0 + 1, i + 1)):
            continue
        g = 1.0
        for k in range(i0 + 1, i + 1):
            g *= 1 + rf[d[k]]
        bar = g - 1 if hurdle == "tbill" else 0.0
        win = "SPY" if ret["SPY"] >= ret["EFA"] else "EFA"
        out.append((i, win if ret[win] > bar else bond))
    return out


def gem_run(dec, bond="AGG", mult=1.0):
    d = yahoo("SPY")["dates"]
    n = len(d)
    legs = {}
    for s in ("SPY", "EFA", bond):
        wmap = {}
        for j, (i, a) in enumerate(dec):
            stop = dec[j + 1][0] if j + 1 < len(dec) else n
            for t in range(i, stop):
                wmap[d[t]] = 1.0 if a == s else 0.0
        W, last = [], 0.0
        for t in yahoo(s)["dates"]:
            last = wmap.get(t, last if t > d[dec[0][0]] else 0.0)
            W.append(last)
        legs[s] = _sim(s, *engine.next_open_exec(W), cost_of(s) * mult)
    return _combine(legs, GEM_START)


def h31():
    dec = gem_decisions()
    base, x2 = gem_run(dec), gem_run(dec, mult=2.0)
    variants = [("6-month lookback", gem_decisions(6), "AGG"), ("9-month lookback", gem_decisions(9), "AGG"),
                ("IEF as the bond", gem_decisions(bond="IEF"), "IEF"),
                ("0% hurdle instead of T-bills", gem_decisions(hurdle="zero"), "AGG")]
    neighbours = [(nm, r["dates"], r["net"]) for nm, dv, b in variants for r in (gem_run(dv, bond=b),)]

    d = yahoo("SPY")["dates"]
    oos = [j for j, (i, _) in enumerate(dec) if d[i] >= "2012-12-31"]
    held = [dec[j][1] for j in oos]
    rng = random.Random(evaluate.SEED_PLACEBO)
    placebo = []
    for _ in range(1000):
        perm = held[:]
        rng.shuffle(perm)
        fake = list(dec)
        for j, a in zip(oos, perm):
            fake[j] = (dec[j][0], a)
        r = gem_run(fake)
        placebo.append(stats.sharpe(r["net"][first_index(r["dates"], GEM_OOS):]))

    def vector(cut):
        v = [None] * len(d)
        for i, a in gem_decisions(cut_date=None if cut is None else d[cut]):
            v[i] = a
        return v

    switches = sum(1 for a, b in zip(held, held[1:]) if a != b)
    extra = {"decisions": len(dec), "first_decision": d[dec[0][0]],
             "oos_share_of_months": {s: round(sum(a == s for a in held) / len(held), 3) for s in ("SPY", "EFA", "AGG")},
             "oos_switches_per_year": round(switches / (len(held) / 12), 2)}
    return [record(
        id="H31", cluster="DUALMOM", name="Dual momentum (SPY vs EFA 12m, AGG below T-bills)", periods=252,
        hypothesis="Holding the stronger of US and non-US stocks over 12 months, and bonds when it trails "
                   "T-bills, beats the market",
        data="Yahoo SPY/EFA/AGG/IEF (adjusted) 2001->, ^IRX", costs="1bp SPY, 2bp EFA/AGG/IEF per side (2x)",
        dates=base["dates"], net=base["net"], gross=base["gross"], net_2x=x2["net"],
        oos_start=GEM_OOS, bench="SPY", implementable=True, survivor_universe=False, neighbours=neighbours,
        placebo=placebo, turnover=base["turnover"], rf=base["rf"],
        leakage=leakage.truncation_test(vector, len(d), lag=0), extra=extra,
        notes=["Decisions use month-end closes and fill at the next open."], unregistered=[UNREG_RF])]


# ----------------------------------------------------------------------- H32

def halloween_windows(dates):
    """[(entry index, exit index, cycle end index)]: hold from close[entry] to close[exit]."""
    ends = month_ends(dates)
    octs = [i for i in ends if dates[i][5:7] == "10"]
    aprs = [i for i in ends if dates[i][5:7] == "04"]
    out = []
    for k, a in enumerate(octs):
        b = next((x for x in aprs if x > a), None)
        if b is None:
            continue
        cycle_end = octs[k + 1] if k + 1 < len(octs) else None
        out.append((a, b, cycle_end))
    return out


def blocks_weights(n, blocks):
    W = [0.0] * n
    for a, b in blocks:
        for t in range(a, b):
            W[t] = 1.0
    return W


def hw_run(sym="SPY", mult=1.0, blocks=None):
    y = yahoo(sym)
    n = len(y["dates"])
    bl = blocks if blocks is not None else [(a, b) for a, b, _ in halloween_windows(y["dates"])]
    return clip(_sim(sym, *engine.close_exec(blocks_weights(n, bl)), cost_of(sym) * mult), HW_START)


def h32():
    base, x2 = hw_run(), hw_run(mult=2.0)
    neighbours = [(s, r["dates"], r["net"]) for s in ("IWM", "DIA", "QQQ", "EFA") for r in (hw_run(s),)]
    y = yahoo("SPY")
    d, c = y["dates"], y["close"]
    n, rf = len(d), rf_list(d)
    wins = halloween_windows(d)
    rng = random.Random(evaluate.SEED_PLACEBO)
    placebo = []
    for _ in range(1000):
        bl = []
        for a, b, e in wins:
            length = b - a
            end = e if e is not None else n - 1  # the last cycle is cut short by the data
            s = rng.randint(a, end - length) if end - length >= a else a
            bl.append((s, s + length))
        r = hw_run(blocks=bl)
        placebo.append(stats.sharpe(r["net"][first_index(r["dates"], HW_OOS):]))
    W = blocks_weights(n, [(a, b) for a, b, _ in wins])

    def block(lo, hi):
        on = [c[i] / c[i - 1] - 1 - rf[i] for i in range(1, n) if lo <= d[i] < hi and W[i - 1]]
        off = [c[i] / c[i - 1] - 1 - rf[i] for i in range(1, n) if lo <= d[i] < hi and not W[i - 1]]
        return {"winter_day_mean_bp": round(stats.mean(on) * 1e4, 2),
                "summer_day_mean_bp": round(stats.mean(off) * 1e4, 2), "days_winter_summer": [len(on), len(off)]}

    return [record(
        id="H32", cluster="HALLOWEEN", name="Halloween: SPY Nov-Apr, cash May-Oct", periods=252,
        hypothesis="Stocks earn their excess return from November to April; summer months earn about nothing",
        data="Yahoo SPY/IWM/DIA/QQQ/EFA (adjusted) 1993->, ^IRX", costs="1bp/side SPY (2x: 2bp)",
        dates=base["dates"], net=base["net"], gross=base["gross"], net_2x=x2["net"],
        oos_start=HW_OOS, bench="SPY", implementable=True, survivor_universe=False, neighbours=neighbours,
        placebo=placebo, trades=engine.trades(base), expo=engine.exposure(base), turnover=base["turnover"],
        rf=base["rf"], leakage=leakage.truncation_test(lambda cut: blocks_weights(n, [(a, b) for a, b, _ in wins]),
                                                        n, lag=1),
        extra={"in_sample_1993_2002": block(HW_START, HW_OOS), "out_of_sample_2003_on": block(HW_OOS, "9999")},
        notes=["Calendar rule public in advance; the truncation test is structurally satisfied and run anyway."],
        unregistered=[UNREG_RF])]


# ----------------------------------------------------------------------- H33

def cycle_weights(n, ev, days=EVEN):
    """close_exec: W[t-1] = 1 when session t is an even-week day of FOMC cycle time."""
    W = [0.0] * n
    j = 0
    for t in range(1, n):
        while j + 1 < len(ev) and ev[j + 1] <= t + 1:
            j += 1
        if ev and ev[j] <= t + 1 and (t - ev[j]) in days:
            W[t - 1] = 1.0
    return W


def fc_run(events, sym="SPY", days=EVEN, mult=1.0, ev=None):
    y = yahoo(sym)
    n = len(y["dates"])
    idx = ev if ev is not None else event_index(y["dates"], events)
    return clip(_sim(sym, *engine.close_exec(cycle_weights(n, idx, days)), cost_of(sym) * mult), FC_START)


def h33():
    events, excluded = sources.fomc_statement_dates(1994)
    base, x2 = fc_run(events), fc_run(events, mult=2.0)
    neighbours = [("weeks 2/4/6 only", *(lambda r: (r["dates"], r["net"]))(fc_run(events, days=EVEN_246)))]
    neighbours += [(s, r["dates"], r["net"]) for s in ("QQQ", "IWM", "DIA") for r in (fc_run(events, sym=s),)]
    y = yahoo("SPY")
    d, c = y["dates"], y["close"]
    n, rf = len(d), rf_list(d)
    ev = event_index(d, events)
    rng = random.Random(evaluate.SEED_PLACEBO)
    placebo = []
    for _ in range(1000):
        moved = sorted(min(n - 2, max(2, e + rng.choice((-1, 1)) * rng.randint(3, 15))) for e in ev)
        r = fc_run(events, ev=moved)
        placebo.append(stats.sharpe(r["net"][first_index(r["dates"], FC_OOS):]))
    W = cycle_weights(n, ev)

    def block(lo, hi):
        on = [c[i] / c[i - 1] - 1 - rf[i] for i in range(1, n) if lo <= d[i] < hi and W[i - 1]]
        off = [c[i] / c[i - 1] - 1 - rf[i] for i in range(1, n) if lo <= d[i] < hi and not W[i - 1]]
        return {"even_week_day_mean_bp": round(stats.mean(on) * 1e4, 2),
                "other_day_mean_bp": round(stats.mean(off) * 1e4, 2),
                "share_days_held": round(len(on) / (len(on) + len(off)), 3)}

    return [record(
        id="H33", cluster="FOMCCYCLE", name="FOMC cycle: SPY in even weeks (days -1..3, 9..13, 19..23, 29..33)",
        periods=252,
        hypothesis="US stock returns concentrate in even weeks of FOMC cycle time (Fed policy news cycle)",
        data="federalreserve.gov calendars 1994->, Yahoo SPY/QQQ/IWM/DIA (adjusted), ^IRX",
        costs="1bp/side SPY (2x: 2bp)", dates=base["dates"], net=base["net"], gross=base["gross"],
        net_2x=x2["net"], oos_start=FC_OOS, bench="SPY", implementable=True, survivor_universe=False,
        neighbours=neighbours, placebo=placebo, trades=engine.trades(base), expo=engine.exposure(base),
        turnover=base["turnover"], rf=base["rf"],
        leakage=leakage.truncation_test(lambda cut: cycle_weights(n, ev), n, lag=1),
        extra={"statement_dates_used": len(ev), "pre_2016": block(FC_START, FC_OOS),
               "post_2016": block(FC_OOS, "9999")},
        notes=["Scheduled statement dates are public in advance; the truncation test is structurally "
               "satisfied and run anyway."],
        unregistered=[UNREG_RF, "FOMC calendar fixes inherited from sources.fomc_statement_dates "
                                "(cancelled 2020-03 meeting excluded; 2003-09 sessions merged)."])]
