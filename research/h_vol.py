"""
Volatility hypotheses. Exact rules: PREREG_PHASE1.md.
====================================================

  H01  CBOE PutWrite index           - the volatility risk premium via options
  H02  SVXY buy & hold               - the same premium via VIX futures, live ETF
  H03  SVXY only in contango         - term-structure timing of short vol
  H07  volatility-managed SPY        - Moreira-Muir with a causal scaling constant
"""

import math
import random

import engine
import evaluate
import leakage
import sources
import stats
from h_common import (UNREG_ENGINE, UNREG_RF, by_decade, closes, first_index, live_alpha,
                      record, rf_list, yahoo)


def _spy_returns():
    y = yahoo("SPY")
    return {y["dates"][i]: y["close"][i] / y["close"][i - 1] - 1 for i in range(1, len(y["dates"]))}


def clean_index_prints(dates, px, spy_ret):
    """
    Amendment A1 (PREREG_PHASE1.md): neutralise single-bar bad prints in an
    option-strategy index. A close is a bad print when its move dwarfs SPY's
    (|r| > 3|r_SPY| + 5%) AND the next bar reverses at least half of it. It is
    replaced by the geometric midpoint, which preserves the two-day return.
    """
    c, flagged = list(px), []
    for t in range(1, len(c) - 1):
        rs = spy_ret.get(dates[t])
        r0, r1 = c[t] / c[t - 1] - 1, c[t + 1] / c[t] - 1
        if rs is not None and abs(r0) > 3 * abs(rs) + 0.05 and r0 * r1 < 0 and abs(r1) > 0.5 * abs(r0):
            c[t] = c[t - 1] * math.sqrt(c[t + 1] / c[t - 1])
            flagged.append(dates[t])
    return c, flagged


def _hold(sym, *, drag=0.0, cost=0.0, use_open=False, clean=False):
    y = yahoo(sym)
    n = len(y["dates"])
    px = clean_index_prints(y["dates"], y["close"], _spy_returns())[0] if clean else y["close"]
    w_on, w_id = engine.close_exec([1.0] * n)
    return engine.simulate(y["dates"], y["open"] if use_open else None, px, w_on, w_id,
                           rf_list(y["dates"]), cost_per_side=cost, drag=drag)


# ----------------------------------------------------------------------- H01

def h01(amended=False):
    base = _hold("^PUT", drag=0.005, clean=amended)
    x2 = _hold("^PUT", drag=0.010, clean=amended)
    spy_oos = {d for d in yahoo("SPY")["dates"] if d >= "2008-01-01"}
    coverage, avail = {}, []
    for s in ("^BXM", "^BXMD", "^BXY", "^CNDR", "^WPUT", "^PUTY"):
        cov = len(set(yahoo(s)["dates"]) & spy_oos) / len(spy_oos)
        coverage[s] = round(cov, 3)
        if cov >= 0.90:
            r = _hold(s, drag=0.005, clean=amended)
            avail.append((s, r["dates"], r["net"]))
    extra = {
        "neighbour_coverage_vs_spy_oos": coverage,
        "available_neighbours_oos_sharpe": {
            s: round(stats.sharpe([x for dd, x in zip(nd, nn) if dd >= "2008-01-01"]), 3)
            for s, nd, nn in avail},
        "pre_oos_1996_2007_sharpe": round(stats.sharpe(
            [x for d, x in zip(base["dates"], base["net"]) if d < "2008-01-01"]), 3),
        "sharpe_by_decade": by_decade(base["dates"], base["net"], 252),
    }
    if amended:
        spy_ret = _spy_returns()
        extra["amendment_A1_bars_replaced"] = {
            s: clean_index_prints(yahoo(s)["dates"], yahoo(s)["close"], spy_ret)[1]
            for s in ("^PUT", "^BXM")}
    return [record(
        id="H01-A1" if amended else "H01", cluster="VRP",
        name="CBOE PutWrite index (^PUT)" + (" [amendment A1]" if amended else ""), periods=252,
        hypothesis="Systematic at-the-money put-writing earns the volatility risk premium",
        data="Yahoo ^PUT 1996->, ^IRX", costs="0.50%/yr drag (2x: 1.00%)",
        dates=base["dates"], net=base["net"], gross=base["gross"], net_2x=x2["net"],
        oos_start="2008-01-01", bench="SPY", implementable=True,
        neighbours=avail if len(avail) >= 2 else [],
        expo=engine.exposure(base), turnover=base["turnover"], rf=base["rf"], extra=extra,
        notes=["No live corroboration possible: PUTW (WisdomTree PutWrite ETF) history is gone "
               "from Yahoo because the ticker was reused in 2026 - survivorship.",
               f"Only {len(avail)} of 6 candidate CBOE option-strategy neighbours exist on Yahoo; "
               "G6 needs at least 2, so it is N/A."],
        unregistered=[UNREG_RF, "Index opens are unusable (45% of ^PUT bars print open==close), "
                                "so option-strategy indices are simulated close-to-close."])]


# ----------------------------------------------------------------------- H02

def h02(spy_ex):
    base = _hold("SVXY", cost=0.0005, use_open=True)
    x2 = _hold("SVXY", cost=0.0010, use_open=True)
    return [record(
        id="H02", cluster="VRP", name="SVXY buy & hold (short VIX futures)", periods=252,
        hypothesis="Shorting VIX futures earns the roll-down / variance risk premium",
        data="Yahoo SVXY 2011->, ^IRX", costs="5bp entry (2x: 10bp)",
        dates=base["dates"], net=base["net"], gross=base["gross"], net_2x=x2["net"],
        oos_start=base["dates"][0], bench="SPY", implementable=True,
        live=[live_alpha("SVXY", spy_ex)], expo=engine.exposure(base),
        turnover=base["turnover"], rf=base["rf"],
        extra={"post_restructure_2018_03_sharpe": round(stats.sharpe(
            [x for d, x in zip(base["dates"], base["net"]) if d >= "2018-03-01"]), 3)},
        notes=["SVXY cut its exposure from -1x to -0.5x daily VIX futures on 2018-02-27, after "
               "the Feb 2018 volatility spike.",
               "Survivorship: XIV, the larger -1x product, was terminated in Feb 2018 and is "
               "not in the data at all."],
        unregistered=[UNREG_RF])]


# ----------------------------------------------------------------------- H03

def ratio_signal(dates, num, den, thr, cut=None):
    """1 when num/den < thr at that close, else 0; carries the last value over gaps."""
    s, last = [], 0.0
    for i, d in enumerate(dates):
        if cut is None or i <= cut:
            a, b = num.get(d), den.get(d)
            if a is not None and b:
                last = 1.0 if a / b < thr else 0.0
        s.append(last)
    return s


def h03():
    sv = yahoo("SVXY")
    d, o, c = sv["dates"], sv["open"], sv["close"]
    n, rf = len(d), rf_list(d)
    vix, v3m, v9d = closes("^VIX"), closes("^VIX3M"), closes("^VIX9D")

    def run(W, cost=0.0005):
        return engine.simulate(d, o, c, *engine.next_open_exec(W), rf, cost_per_side=cost)

    s = ratio_signal(d, vix, v3m, 1.0)
    base, x2 = run(s), run(s, 0.0010)
    nbs = [(f"VIX/VIX3M<{t:.2f}", ratio_signal(d, vix, v3m, t)) for t in (0.90, 0.95, 1.05)]
    nbs.append(("VIX9D/VIX<1.00", ratio_signal(d, v9d, vix, 1.0)))
    neighbours = [(nm, r["dates"], r["net"]) for nm, w in nbs for r in (run(w),)]

    oos_i = first_index(base["dates"], "2015-01-01")
    rng = random.Random(evaluate.SEED_PLACEBO)
    placebo = []
    for _ in range(1000):
        k = rng.randint(63, n - 63)
        placebo.append(stats.sharpe(run([s[(i - k) % n] for i in range(n)])["net"][oos_i:]))

    hold = _hold("SVXY", cost=0.0005, use_open=True)
    extra = {"share_of_days_signal_on": round(sum(s) / n, 3),
             "svxy_hold_oos_sharpe_same_window": round(stats.sharpe(
                 hold["net"][first_index(hold["dates"], "2015-01-01"):]), 3),
             "in_sample_2011_2014_sharpe": round(stats.sharpe(base["net"][:oos_i]), 3)}
    return [record(
        id="H03", cluster="VRP", name="SVXY only when VIX < VIX3M", periods=252,
        hypothesis="Short vol pays in contango and loses in backwardation, so timing it on the "
                   "VIX term structure keeps the premium and sidesteps the blow-ups",
        data="Yahoo SVXY, ^VIX, ^VIX3M, ^VIX9D 2011->", costs="5bp/side (2x: 10bp)",
        dates=base["dates"], net=base["net"], gross=base["gross"], net_2x=x2["net"],
        oos_start="2015-01-01", bench="SPY", implementable=True, neighbours=neighbours,
        placebo=placebo, trades=engine.trades(base), expo=engine.exposure(base),
        turnover=base["turnover"], rf=base["rf"], extra=extra,
        leakage=leakage.truncation_test(lambda cut: ratio_signal(d, vix, v3m, 1.0, cut), n, lag=0),
        unregistered=[UNREG_RF, "Until VIX and VIX3M first both print, the signal is 0 (cash)."])]


# ----------------------------------------------------------------------- H07

def month_ends(dates):
    """True where the NEXT trading day is in a new month (exchange calendar is known ahead)."""
    return [i + 1 < len(dates) and dates[i + 1][:7] != dates[i][:7] for i in range(len(dates))]


def volmgd_weights(dates, px, *, cap=1.0, sqrt_scale=False, rv63=False, band=0.0,
                   cut=None, warm=12):
    """
    Month-end decision w = min(cap, RVbar / RV) using prices through `cut` only.
    RVbar is the EXPANDING mean of past monthly RVs - never the full-sample
    constant that is the documented look-ahead in the original paper.
    """
    n = len(dates)
    me = month_ends(dates)
    avail = n if cut is None else min(n, cut + 1)
    r = [0.0] + [px[i] / px[i - 1] - 1 for i in range(1, avail)]
    W, w, hist, ss, done = [1.0] * n, 1.0, [], 0.0, 0
    for i in range(avail):
        if i:
            ss += r[i] * r[i]
        if me[i]:
            if dates[i][:7] != dates[0][:7]:            # first month is partial: skip it
                rv = (21.0 / 63.0) * sum(x * x for x in r[max(1, i - 62):i + 1]) if rv63 else ss
                hist.append(rv)
                done += 1
                if done > warm and rv > 0:
                    ratio = (sum(hist) / len(hist)) / rv
                    new = min(cap, math.sqrt(ratio) if sqrt_scale else ratio)
                    if abs(new - w) >= band:
                        w = new
            ss = 0.0
        W[i] = w
    for i in range(avail, n):
        W[i] = w
    return W


def h07():
    y = yahoo("SPY")
    d, o, c = y["dates"], y["open"], y["close"]
    n, rf = len(d), rf_list(d)

    def run(W, cost=0.0001):
        return engine.simulate(d, o, c, *engine.next_open_exec(W), rf, cost_per_side=cost)

    W = volmgd_weights(d, c)
    base, x2 = run(W), run(W, 0.0002)
    nb_w = [("cap 2.0 (levered)", volmgd_weights(d, c, cap=2.0)),
            ("1/vol scaling", volmgd_weights(d, c, sqrt_scale=True)),
            ("RV over 63d", volmgd_weights(d, c, rv63=True)),
            ("no-trade band 0.10", volmgd_weights(d, c, band=0.10))]
    neighbours = [(nm, r["dates"], r["net"]) for nm, w in nb_w for r in (run(w),)]

    me = month_ends(d)
    dec = [i for i in range(n) if me[i] and d[i][:7] >= "2016-12"]
    s0 = max(0, dec[0] - 5)
    ws = [W[i] for i in dec]
    rng = random.Random(evaluate.SEED_PLACEBO)
    placebo = []
    for _ in range(1000):
        perm = ws[:]
        rng.shuffle(perm)
        Wp = W[:]
        for j, i in enumerate(dec):
            for k in range(i, dec[j + 1] if j + 1 < len(dec) else n):
                Wp[k] = perm[j]
        r = engine.simulate(d[s0:], o[s0:], c[s0:], *engine.next_open_exec(Wp[s0:]), rf[s0:],
                            cost_per_side=0.0001)
        placebo.append(stats.sharpe(r["net"][first_index(r["dates"], "2017-01-01"):]))

    # the long history, reported only: French CRSP market, 1-day lag, zero cost
    cols, rows = sources.french_table("F-F_Research_Data_Factors_daily_CSV.zip")
    jm, jr = sources.col_index(cols, "Mkt-RF"), sources.col_index(cols, "RF")
    fd = sorted(p for p in rows if rows[p][jm] is not None and rows[p][jr] is not None)
    ex = [rows[p][jm] for p in fd]
    level = [1.0]
    for p in fd[1:]:
        level.append(level[-1] * (1 + rows[p][jm] + rows[p][jr]))
    Wf = volmgd_weights(fd, level)
    managed = [Wf[i - 2] * ex[i] if i >= 2 else 0.0 for i in range(len(fd))]

    def sr(lo, hi, series):
        return round(stats.sharpe([x for p, x in zip(fd, series) if lo <= p < hi]), 3)

    extra = {
        "avg_weight_oos": round(stats.mean(base["w_id"][first_index(base["dates"], "2017-01-01"):]), 3),
        "french_market_1926": {
            "pre_2017": {"managed_sharpe": sr("1927-08", "2017-01-01", managed),
                         "market_sharpe": sr("1927-08", "2017-01-01", ex)},
            "post_2017": {"managed_sharpe": sr("2017-01-01", "9999", managed),
                          "market_sharpe": sr("2017-01-01", "9999", ex)}},
    }
    return [record(
        id="H07", cluster="VOLMGD", name="Volatility-managed SPY (cap 1.0)", periods=252,
        hypothesis="Cutting equity exposure when last month's realised variance is high raises "
                   "the Sharpe ratio, because expected returns do not rise with volatility",
        data="Yahoo SPY 1993->, ^IRX; French CRSP market 1926-> (reported)",
        costs="1bp/side on |dw| (2x: 2bp)",
        dates=base["dates"], net=base["net"], gross=base["gross"], net_2x=x2["net"],
        oos_start="2017-01-01", bench="SPY", implementable=True, neighbours=neighbours,
        placebo=placebo, expo=engine.exposure(base), turnover=base["turnover"], rf=base["rf"],
        leakage=leakage.truncation_test(lambda cut: volmgd_weights(d, c, cut=cut), n, lag=0),
        extra=extra,
        unregistered=[UNREG_RF, UNREG_ENGINE,
                      "The first (partial) month of data is excluded from the RV history."])]
