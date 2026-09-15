"""
Phase 6: the last published calendar ideas with free, survivorship-free data.
=============================================================================
Exact rules: PREREG_PHASE6.md.

  H38  Santa Claus rally (Hirsch 1972): SPY for the last 5 sessions of December and the first 2 of January
  H39  weekend / Monday effect (French 1980): SPY except each calendar week's first session
  H40  January small-cap effect (Rozeff-Kinney 1976, Keim 1983): IWM in January, SPY otherwise
  H41  presidential cycle (Hirsch 1968, Booth-Booth 2003): SPY in years 3-4 of each term, cash in years 1-2
"""

import collections
import datetime as dt
import random

import engine
import evaluate
import leakage
import stats
from h_calendar import _sim, cost_of
from h_common import UNREG_RF, clip, first_index, record, rf_list, yahoo
from h_phase4 import _combine
from h_phase5 import _block_means, sessions_weights

SC_START = WK_START = PR_START = "1993-02-01"
JN_START = "2001-01-01"
PR_OOS = "2004-01-01"


def by_period(dates, key):
    out = collections.defaultdict(list)
    for i, t in enumerate(dates):
        out[key(t)].append(i)
    return out


def cal_run(sym, idx, start, mult=1.0):
    n = len(yahoo(sym)["dates"])
    return clip(_sim(sym, *engine.close_exec(sessions_weights(n, idx)), cost_of(sym) * mult), start)


def _record(**kw):
    base = dict(periods=252, bench="SPY", implementable=True, survivor_universe=False, unregistered=[UNREG_RF],
                notes=["Calendar rule public in advance; the truncation test is structurally satisfied and run anyway."])
    base.update(kw)
    return record(**base)


# ----------------------------------------------------------------------- H38

def santa_sessions(dates, dec=5, jan=2):
    years = by_period(dates, lambda t: t[:4])
    idx = []
    for y in sorted(years):
        decs = [i for i in years[y] if dates[i][5:7] == "12"]
        jans = [i for i in years.get(str(int(y) + 1), []) if dates[i][5:7] == "01"]
        if len(decs) >= dec and len(jans) >= jan and (jan == 0 or jans):
            idx += decs[-dec:] + jans[:jan]
    return sorted(i for i in idx if i >= 1)


def h38():
    d = yahoo("SPY")["dates"]
    real = santa_sessions(d)
    base, x2 = cal_run("SPY", real, SC_START), cal_run("SPY", real, SC_START, mult=2.0)
    neighbours = [(s, r["dates"], r["net"]) for s in ("QQQ", "IWM", "DIA")
                  for r in (cal_run(s, santa_sessions(yahoo(s)["dates"]), SC_START),)]
    r = cal_run("SPY", santa_sessions(d, jan=0), SC_START)
    neighbours.append(("last 5 December sessions only", r["dates"], r["net"]))
    near = {k for j in real for k in range(j - 10, j + 11)}
    years = by_period(d, lambda t: t[:4])
    window_years = sorted({d[j][:4] for j in real if d[j][5:7] == "12"})
    choices = {}
    for y in window_years:
        sess = years[y]
        starts = [k for k in range(len(sess) - 6) if not any(s in near for s in sess[k:k + 7])]
        if starts:
            choices[y] = (sess, starts)
    rng = random.Random(evaluate.SEED_PLACEBO)
    placebo = []
    for _ in range(1000):
        fake = []
        for y, (sess, starts) in sorted(choices.items()):
            k = rng.choice(starts)
            fake += sess[k:k + 7]
        rr = cal_run("SPY", fake, SC_START)
        placebo.append(stats.sharpe(rr["net"]))
    y = yahoo("SPY")
    c, rf, n = y["close"], rf_list(d), len(d)
    held = set(real)
    return [_record(
        id="H38", cluster="SANTA", name="Santa Claus rally: SPY last 5 Dec + first 2 Jan sessions",
        hypothesis="Stocks rise over the last five trading days of December and the first two of January",
        data="Yahoo SPY/QQQ/IWM/DIA (adjusted) 1993->, ^IRX", costs="1bp/side SPY (2x: 2bp)",
        dates=base["dates"], net=base["net"], gross=base["gross"], net_2x=x2["net"], oos_start=SC_START,
        neighbours=neighbours, placebo=placebo, trades=engine.trades(base), expo=engine.exposure(base),
        turnover=base["turnover"], rf=base["rf"],
        leakage=leakage.truncation_test(lambda cut: sessions_weights(n, real), n, lag=1),
        extra={"1993_2009": _block_means(d, c, rf, held, SC_START, "2010-01-01"),
               "2010_on": _block_means(d, c, rf, held, "2010-01-01", "9999")})]


# ----------------------------------------------------------------------- H39

def week_first_sessions(dates, monday_only=False):
    idx, prev = [], None
    for i, t in enumerate(dates):
        day = dt.date.fromisoformat(t)
        wk = day - dt.timedelta(days=day.weekday())
        if wk != prev:
            if not monday_only or day.weekday() == 0:
                idx.append(i)
            prev = wk
    return idx


def all_but(n, skip):
    s = set(skip)
    return [i for i in range(1, n) if i not in s]


def h39():
    d = yahoo("SPY")["dates"]
    n = len(d)
    real = all_but(n, week_first_sessions(d))
    base, x2 = cal_run("SPY", real, WK_START), cal_run("SPY", real, WK_START, mult=2.0)
    neighbours = []
    for s in ("QQQ", "IWM", "DIA"):
        ds = yahoo(s)["dates"]
        r = cal_run(s, all_but(len(ds), week_first_sessions(ds)), WK_START)
        neighbours.append((s, r["dates"], r["net"]))
    r = cal_run("SPY", all_but(n, week_first_sessions(d, monday_only=True)), WK_START)
    neighbours.append(("skip actual Mondays only", r["dates"], r["net"]))
    weeks = by_period(d, lambda t: (dt.date.fromisoformat(t) - dt.timedelta(days=dt.date.fromisoformat(t).weekday())))
    wk_lists = [v for _, v in sorted(weeks.items())]
    rng = random.Random(evaluate.SEED_PLACEBO)
    placebo = []
    for _ in range(1000):
        rr = cal_run("SPY", all_but(n, [rng.choice(v) for v in wk_lists]), WK_START)
        placebo.append(stats.sharpe(rr["net"]))
    y = yahoo("SPY")
    c, rf = y["close"], rf_list(d)
    first = set(week_first_sessions(d))
    return [_record(
        id="H39", cluster="WEEKEND", name="Weekend effect: SPY except each week's first session",
        hypothesis="The return spanning the weekend (each week's first session) is below other days, so "
                   "skipping it beats holding throughout",
        data="Yahoo SPY/QQQ/IWM/DIA (adjusted) 1993->, ^IRX", costs="1bp/side SPY (2x: 2bp)",
        dates=base["dates"], net=base["net"], gross=base["gross"], net_2x=x2["net"], oos_start=WK_START,
        neighbours=neighbours, placebo=placebo, trades=engine.trades(base), expo=engine.exposure(base),
        turnover=base["turnover"], rf=base["rf"],
        leakage=leakage.truncation_test(lambda cut: sessions_weights(n, real), n, lag=1),
        extra={"week_first_session_1993_2009": _block_means(d, c, rf, first, WK_START, "2010-01-01"),
               "week_first_session_2010_on": _block_means(d, c, rf, first, "2010-01-01", "9999")})]


# ----------------------------------------------------------------------- H40

def jan_sessions(dates, first_n=None, turn=None):
    months = by_period(dates, lambda t: t[:7])
    idx = []
    for m, sess in sorted(months.items()):
        if m[5:7] == "01":
            idx += sess[:first_n] if first_n else sess
            if turn:
                idx += months.get(f"{int(m[:4]) - 1}-12", [])[-turn:]
    return sorted({i for i in idx if i >= 1})


def tilt_run(small, idx_small, mult=1.0):
    """IWM-type leg on `idx_small` sessions (SPY calendar), SPY on every other session."""
    d = yahoo("SPY")["dates"]
    n = len(d)
    held = set(idx_small)
    legs = {}
    for sym, idx in (("SPY", [i for i in range(1, n) if i not in held]), (small, idx_small)):
        wmap = dict(zip(d, sessions_weights(n, idx)))
        W = [wmap.get(t, 0.0) for t in yahoo(sym)["dates"]]
        legs[sym] = _sim(sym, *engine.close_exec(W), cost_of(sym) * mult)
    return _combine(legs, JN_START)


def h40():
    d = yahoo("SPY")["dates"]
    real = jan_sessions(d)
    base, x2 = tilt_run("IWM", real), tilt_run("IWM", real, mult=2.0)
    variants = [("IJR instead of IWM", "IJR", real), ("MDY instead of IWM", "MDY", real),
                ("first 10 January sessions only", "IWM", jan_sessions(d, first_n=10)),
                ("turn of year: last 10 Dec + first 10 Jan", "IWM", jan_sessions(d, first_n=10, turn=10))]
    neighbours = [(nm, r["dates"], r["net"]) for nm, s, ix in variants for r in (tilt_run(s, ix),)]
    months = by_period(d, lambda t: t[:7])
    years = sorted({t[:4] for t in d if t >= JN_START})
    rng = random.Random(evaluate.SEED_PLACEBO)
    placebo = []
    for _ in range(1000):
        fake = sorted(i for y in years for i in months.get(f"{y}-{rng.randint(2, 12):02d}", []) if i >= 1)
        r = tilt_run("IWM", fake)
        placebo.append(stats.sharpe(r["net"]))
    iwm = dict(zip(yahoo("IWM")["dates"], yahoo("IWM")["close"]))
    spy = dict(zip(d, yahoo("SPY")["close"]))
    spread = {}
    for y in years:
        jan = months.get(f"{y}-01", [])
        dec = months.get(f"{int(y) - 1}-12", [])
        if jan and dec:
            a, b = d[dec[-1]], d[jan[-1]]
            if a in iwm and b in iwm:
                spread[y] = (iwm[b] / iwm[a] - 1) - (spy[b] / spy[a] - 1)

    def summary(lo, hi):
        xs = [v for y, v in spread.items() if lo <= y < hi]
        return {"years": len(xs), "mean_jan_iwm_minus_spy_pct": round(100 * stats.mean(xs), 2),
                "share_positive": round(sum(x > 0 for x in xs) / len(xs), 2)} if xs else {}

    n = len(d)
    return [_record(
        id="H40", cluster="JANUARY", name="January small caps: IWM in January, SPY otherwise",
        hypothesis="Small caps beat large caps in January, so tilting to IWM each January beats holding SPY",
        data="Yahoo SPY/IWM/IJR/MDY (adjusted) 1995->, ^IRX", costs="1bp SPY, 2bp IWM/IJR/MDY per side (2x)",
        dates=base["dates"], net=base["net"], gross=base["gross"], net_2x=x2["net"], oos_start=JN_START,
        neighbours=neighbours, placebo=placebo, turnover=base["turnover"], rf=base["rf"],
        leakage=leakage.truncation_test(lambda cut: sessions_weights(n, real), n, lag=1),
        extra={"jan_spread_2001_2013": summary("2001", "2014"), "jan_spread_2014_on": summary("2014", "9999")})]


# ----------------------------------------------------------------------- H41

def term_sessions(dates, mods=(3, 0)):
    return [i for i, t in enumerate(dates) if i >= 1 and int(t[:4]) % 4 in mods]


def h41():
    d = yahoo("SPY")["dates"]
    n = len(d)
    real = term_sessions(d)
    base, x2 = cal_run("SPY", real, PR_START), cal_run("SPY", real, PR_START, mult=2.0)
    neighbours = [(s, r["dates"], r["net"]) for s in ("QQQ", "IWM", "DIA")
                  for r in (cal_run(s, term_sessions(yahoo(s)["dates"]), PR_START),)]
    r = cal_run("SPY", term_sessions(d, mods=(3,)), PR_START)
    neighbours.append(("year 3 only", r["dates"], r["net"]))
    cycles = by_period(d, lambda t: int(t[:4]) - (int(t[:4]) - 1) % 4)
    held = set(real)
    plan = [(sess, sum(1 for i in sess if i in held)) for _, sess in sorted(cycles.items())]
    rng = random.Random(evaluate.SEED_PLACEBO)
    placebo = []
    for _ in range(1000):
        fake = []
        for sess, length in plan:
            if length:
                s = rng.randint(0, len(sess) - length)
                fake += sess[s:s + length]
        rr = cal_run("SPY", [i for i in fake if i >= 1], PR_START)
        placebo.append(stats.sharpe(rr["net"][first_index(rr["dates"], PR_OOS):]))
    y = yahoo("SPY")
    c, rf = y["close"], rf_list(d)
    yearly = collections.defaultdict(lambda: 1.0)
    for i in range(1, n):
        yearly[int(d[i][:4])] *= 1 + c[i] / c[i - 1] - 1 - rf[i]

    def summary(lo, hi):
        late = [v - 1 for yr, v in yearly.items() if lo <= yr < hi and yr % 4 in (3, 0)]
        early = [v - 1 for yr, v in yearly.items() if lo <= yr < hi and yr % 4 in (1, 2)]
        return {"years_3_4_mean_excess_pct": round(100 * stats.mean(late), 2) if late else None,
                "years_1_2_mean_excess_pct": round(100 * stats.mean(early), 2) if early else None,
                "n_years": [len(late), len(early)]}

    return [_record(
        id="H41", cluster="PRESCYCLE", name="Presidential cycle: SPY in years 3-4, cash in years 1-2",
        hypothesis="Stocks earn their excess return in the second half of each presidential term",
        data="Yahoo SPY/QQQ/IWM/DIA (adjusted) 1993->, ^IRX", costs="1bp/side SPY (2x: 2bp)",
        dates=base["dates"], net=base["net"], gross=base["gross"], net_2x=x2["net"], oos_start=PR_OOS,
        neighbours=neighbours, placebo=placebo, trades=engine.trades(base), expo=engine.exposure(base),
        turnover=base["turnover"], rf=base["rf"],
        leakage=leakage.truncation_test(lambda cut: sessions_weights(n, real), n, lag=1),
        extra={"1993_2003": summary(1993, 2004), "2004_on": summary(2004, 9999)})]
