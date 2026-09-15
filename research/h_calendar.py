"""
Calendar and event hypotheses. Exact rules: PREREG_PHASE1.md.
============================================================

  H04  pre-FOMC announcement drift   (Lucca-Moench)
  H05  overnight return premium      (Cooper-Cliff-Gulen)
  H06  turn of the month             (Ariel; Lakonishok-Smidt)

All three trade on a calendar that is public in advance, so orders at the
close are legitimate - the decision never needs that close's price.
"""

import collections
import random

import engine
import evaluate
import leakage
import sources
import stats
from h_common import UNREG_RF, clip, first_index, live_alpha, record, rf_list, yahoo

ONE_BP = {"SPY", "QQQ", "DIA"}
SECTORS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]


def cost_of(sym):
    return 0.0001 if sym in ONE_BP else 0.0002


def _sim(sym, w_on, w_id, cost):
    y = yahoo(sym)
    return engine.simulate(y["dates"], y["open"], y["close"], w_on, w_id, rf_list(y["dates"]),
                           cost_per_side=cost)


# ----------------------------------------------------------------------- H04

def event_index(dates, events):
    pos = {d: i for i, d in enumerate(dates)}
    return sorted(pos[e] for e in events if e in pos and pos[e] >= 2)


def fomc_weights(n, ev, back=1):
    W = [0.0] * n
    for e in ev:
        for j in range(e - back, e):
            W[j] = 1.0
    return W


def h04():
    events, excluded = sources.fomc_statement_dates(1994)

    def run(sym="SPY", mode="cc", back=1, mult=1.0):
        y = yahoo(sym)
        n = len(y["dates"])
        ev = event_index(y["dates"], events)
        if mode == "cc":
            w_on, w_id = engine.close_exec(fomc_weights(n, ev, back))
        else:
            w_on, w_id = [0.0] * n, [0.0] * n
            for e in ev:
                (w_id if mode == "oc" else w_on)[e] = 1.0
        return clip(_sim(sym, w_on, w_id, cost_of(sym) * mult), "1994-01-01")

    base, x2 = run(), run(mult=2.0)
    neighbours = []
    for nm, kw in [("close[d-2]->close[d]", dict(back=2)), ("open[d]->close[d]", dict(mode="oc")),
                   ("close[d-1]->open[d]", dict(mode="co")), ("QQQ", dict(sym="QQQ")),
                   ("IWM", dict(sym="IWM"))]:
        r = run(**kw)
        neighbours.append((nm, r["dates"], r["net"]))

    y = yahoo("SPY")
    d, c = y["dates"], y["close"]
    n, rf = len(d), rf_list(d)
    ev = event_index(d, events)
    evs = set(ev)
    near = {j for e in ev for j in range(e - 3, e + 4)}
    pool = collections.defaultdict(list)
    for i in range(2, n - 1):
        if i not in near and d[i] >= "2012-01-01":
            pool[d[i][:4]].append(i)
    per_year = collections.Counter(d[e][:4] for e in ev if d[e] >= "2012-01-01")
    r_cc = [0.0] + [c[i] / c[i - 1] - 1 for i in range(1, n)]
    oos0 = first_index(d, "2012-01-01")
    rng = random.Random(evaluate.SEED_PLACEBO)
    placebo = []
    for _ in range(1000):
        net = [0.0] * n
        for yr, k in per_year.items():
            for p in rng.sample(pool[yr], min(k, len(pool[yr]))):
                net[p] += r_cc[p] - rf[p] - 0.0001
                if p + 1 < n:
                    net[p + 1] -= 0.0001
        placebo.append(stats.sharpe(net[oos0:]))

    def ev_stats(lo, hi):
        xs = [r_cc[e] - rf[e] for e in ev if lo <= d[e] < hi]
        other = [r_cc[i] - rf[i] for i in range(1, n) if lo <= d[i] < hi and i not in evs]
        m, s = stats.mean(xs), stats.stdev(xs)
        return {"events": len(xs), "mean_excess_bp": round(m * 1e4, 1),
                "t_stat": round(m / (s / len(xs) ** 0.5), 2) if s else 0.0,
                "hit_rate": round(sum(x > 0 for x in xs) / len(xs), 3),
                "other_days_mean_bp": round(stats.mean(other) * 1e4, 2)}

    return [record(
        id="H04", cluster="FOMC", name="Pre-FOMC drift (SPY close[d-1] -> close[d])", periods=252,
        hypothesis="US equities earn an abnormal return in the 24h before scheduled FOMC "
                   "statements (uncertainty-resolution premium)",
        data="federalreserve.gov calendars 1994->, Yahoo SPY/QQQ/IWM, ^IRX",
        costs="1bp/side SPY (2x: 2bp)",
        dates=base["dates"], net=base["net"], gross=base["gross"], net_2x=x2["net"],
        oos_start="2012-01-01", bench="SPY", implementable=True, neighbours=neighbours,
        placebo=placebo, trades=engine.trades(base), expo=engine.exposure(base),
        turnover=base["turnover"], rf=base["rf"],
        leakage=leakage.truncation_test(lambda cut: fomc_weights(n, ev, 1), n, lag=1),
        extra={"statement_dates_used": len(ev), "entries_excluded": len(excluded),
               "events_pre_2012": ev_stats("1994-01-01", "2012-01-01"),
               "events_post_2012": ev_stats("2012-01-01", "9999")},
        notes=["Decisions depend only on the published FOMC calendar, so the truncation test is "
               "structurally satisfied; it is run anyway."],
        unregistered=[UNREG_RF, "Exit cost is booked on the trading day after the statement "
                                "(engine convention); placebos book it the same way.",
                      "Data fix: the cancelled 2020-03-17/18 meeting (no statement) is excluded.",
                      "Data fix: 2003-09-15 and 2003-09-16, listed as separate sessions, are "
                      "merged to the statement day 2003-09-16."])]


# ----------------------------------------------------------------------- H05

def _overnight(sym, mult=1.0, intraday=False):
    n = len(yahoo(sym)["dates"])
    ones = [0.0] + [1.0] * (n - 1)
    w_on, w_id = ([0.0] * n, ones) if intraday else (ones, [0.0] * n)
    return clip(_sim(sym, w_on, w_id, cost_of(sym) * mult), "1993-02-01")


def _qc(sym, start="2009-01-01"):
    y = yahoo(sym)
    d, o, h, l, c = y["dates"], y["open"], y["high"], y["low"], y["close"]
    idx = [i for i in range(1, len(d)) if d[i] >= start]
    return {"stale_open": round(sum(abs(o[i] / c[i - 1] - 1) < 1e-6 for i in idx) / len(idx), 4),
            "open_outside_range": round(sum(o[i] > h[i] * (1 + 1e-6) or o[i] < l[i] * (1 - 1e-6)
                                            for i in idx) / len(idx), 4)}


def h05(spy_ex):
    base, x2 = _overnight("SPY"), _overnight("SPY", 2.0)
    neighbours = [(s, r["dates"], r["net"])
                  for s in ["QQQ", "DIA", "IWM"] + SECTORS for r in (_overnight(s),)]
    intraday = _overnight("SPY", intraday=True)
    oos = first_index(base["dates"], "2009-01-01")
    g = base["gross"][oos:]
    qc = {s: _qc(s) for s in ["SPY", "QQQ", "DIA", "IWM"] + SECTORS}
    return [record(
        id="H05", cluster="OVERNIGHT", name="Overnight-only SPY (close -> next open)", periods=252,
        hypothesis="The equity premium accrues overnight; holding only close-to-open keeps it "
                   "with half the time in the market",
        data="Yahoo SPY/QQQ/DIA/IWM/sector SPDR OHLC 1993->, ^IRX; NSPY/NIWM live",
        costs="1bp/side SPY, 2 sides/day (2x: 2bp)",
        dates=base["dates"], net=base["net"], gross=base["gross"], net_2x=x2["net"],
        oos_start="2009-01-01", bench="SPY", implementable=True, neighbours=neighbours,
        live=[live_alpha("NSPY", spy_ex)], expo=engine.exposure(base),
        turnover=base["turnover"], rf=base["rf"],
        extra={"gross_oos_mean_bp_per_day": round(stats.mean(g) * 1e4, 3),
               "break_even_cost_bp_per_side": round(stats.mean(g) / 2 * 1e4, 3),
               "gross_oos_sharpe": round(stats.sharpe(g), 3),
               "intraday_only_oos_net_sharpe": round(stats.sharpe(
                   intraday["net"][first_index(intraday["dates"], "2009-01-01"):]), 3),
               "data_qc_oos": qc,
               "qc_flags_over_1pct": [s for s, q in qc.items()
                                      if q["stale_open"] > 0.01 or q["open_outside_range"] > 0.01],
               "live_NIWM_not_gated": live_alpha("NIWM", spy_ex)},
        notes=["The only live overnight ETFs (NightShares NSPY / NIWM) launched 2022-06 and were "
               "liquidated 2023-08 after 14 months - too short for G9, and a survivorship fact."],
        unregistered=[UNREG_RF, "Yahoo's open is used as the market-on-open fill; the official "
                                "opening-auction print can differ."])]


# ----------------------------------------------------------------------- H06

def months(dates):
    out = {}
    for i, d in enumerate(dates):
        out.setdefault(d[:7], []).append(i)
    return [out[k] for k in sorted(out)]


def tom_weights(dates, lo=-1, hi=3):
    """Hold the returns of the last -lo trading days of each month and the first hi of the next."""
    W = [0.0] * len(dates)
    ms = months(dates)
    for a, b in zip(ms, ms[1:]):
        if len(a) < -lo or len(b) < hi:
            continue
        held = a[lo:] + b[:hi]
        for j in range(max(0, held[0] - 1), held[-1]):
            W[j] = 1.0
    return W


def h06():
    def run(sym="SPY", lo=-1, hi=3, mult=1.0):
        y = yahoo(sym)
        w_on, w_id = engine.close_exec(tom_weights(y["dates"], lo, hi))
        return clip(_sim(sym, w_on, w_id, cost_of(sym) * mult), "1993-02-01")

    base, x2 = run(), run(mult=2.0)
    neighbours = [(f"SPY {lo:+d}..{hi:+d}", r["dates"], r["net"])
                  for lo, hi in [(-1, 2), (-1, 4), (-2, 3), (-2, 4), (-3, 3)]
                  for r in (run("SPY", lo, hi),)]
    neighbours += [(s, r["dates"], r["net"]) for s in ("QQQ", "IWM", "DIA") for r in (run(s),)]

    y = yahoo("SPY")
    d, c = y["dates"], y["close"]
    n, rf = len(d), rf_list(d)
    r_cc = [0.0] + [c[i] / c[i - 1] - 1 for i in range(1, n)]
    ms = months(d)
    rng = random.Random(evaluate.SEED_PLACEBO)
    placebo = []
    for _ in range(1000):
        net = [0.0] * n
        for m in ms:
            if len(m) < 10:
                continue
            s = rng.randint(5, len(m) - 5)
            held = m[s - 1:s + 3]
            net[held[0]] -= 0.0001
            for j in held:
                net[j] += r_cc[j] - rf[j]
            if held[-1] + 1 < n:
                net[held[-1] + 1] -= 0.0001
        placebo.append(stats.sharpe(net[1:]))

    cols, rows = sources.french_table("F-F_Research_Data_Factors_daily_CSV.zip")
    jm = sources.col_index(cols, "Mkt-RF")
    fd = sorted(p for p in rows if rows[p][jm] is not None)
    ex = [rows[p][jm] for p in fd]
    Wf = tom_weights(fd)

    def block(lo, hi):
        idx = [i for i in range(1, len(fd)) if lo <= fd[i] < hi]
        on = [ex[i] for i in idx if Wf[i - 1]]
        off = [ex[i] for i in idx if not Wf[i - 1]]
        return {"tom_sharpe": round(stats.sharpe([ex[i] * Wf[i - 1] for i in idx]), 3),
                "market_sharpe": round(stats.sharpe([ex[i] for i in idx]), 3),
                "tom_day_mean_bp": round(stats.mean(on) * 1e4, 2),
                "other_day_mean_bp": round(stats.mean(off) * 1e4, 2),
                "share_of_days_held": round(len(on) / len(idx), 3)}

    Ws = tom_weights(d)
    return [record(
        id="H06", cluster="TOM", name="Turn of the month (SPY days -1..+3)", periods=252,
        hypothesis="Equity returns concentrate in the last trading day and first three of each "
                   "month (payroll and pension inflows)",
        data="Yahoo SPY/QQQ/IWM/DIA 1993->, ^IRX; French CRSP market 1926-> (reported)",
        costs="1bp/side SPY (2x: 2bp)",
        dates=base["dates"], net=base["net"], gross=base["gross"], net_2x=x2["net"],
        oos_start="1993-02-01", bench="SPY", implementable=True, neighbours=neighbours,
        placebo=placebo, trades=engine.trades(base), expo=engine.exposure(base),
        turnover=base["turnover"], rf=base["rf"],
        leakage=leakage.truncation_test(lambda cut: tom_weights(d), n, lag=1),
        extra={"french_market_pre_1988": block("1926-07-01", "1988-01-01"),
               "french_market_post_1988": block("1988-01-01", "9999"),
               "spy_tom_day_mean_bp": round(stats.mean(
                   [r_cc[i] - rf[i] for i in range(1, n) if Ws[i - 1]]) * 1e4, 2),
               "spy_other_day_mean_bp": round(stats.mean(
                   [r_cc[i] - rf[i] for i in range(1, n) if not Ws[i - 1]]) * 1e4, 2)},
        notes=["The whole SPY history is post-publication (1987/88), so the gated window is all "
               "of it; the French 1926-> split shows the pre/post-publication comparison."],
        unregistered=[UNREG_RF, "Windows that would run past the data are skipped."])]
