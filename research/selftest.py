"""
Known-answer tests for the engine, statistics and look-ahead detector.
Run before trusting any result:  python3 research/selftest.py
"""

import datetime as dt
import math
import os
import random
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import basket
import engine
import evaluate
import h_events
import h_insider
import h_stocks
import leakage
import p2data
import stats

FAILS = []


def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'}  {name}  {detail}")
    if not cond:
        FAILS.append(name)


def synthetic(n=600, seed=1):
    rng = random.Random(seed)
    closes, opens = [100.0], [100.0]
    for _ in range(1, n):
        o = closes[-1] * (1 + rng.gauss(0.0002, 0.005))
        opens.append(o)
        closes.append(o * (1 + rng.gauss(0.0001, 0.008)))
    return [f"d{i:05d}" for i in range(n)], opens, closes, [0.0001] * n


def main():
    dates, opens, closes, rf = synthetic()
    n = len(dates)

    print("engine")
    w_on, w_id = engine.close_exec([1.0] * n)
    res = engine.simulate(dates, opens, closes, w_on, w_id, rf)
    bh = [closes[i] / closes[i - 1] - 1 - rf[i] for i in range(1, n)]
    check("constant weight == buy & hold excess",
          max(abs(a - b) for a, b in zip(res["gross"], bh)) < 1e-12)

    on = engine.simulate(dates, opens, closes, [0.0] + [1.0] * (n - 1), [0.0] * n, rf)
    exp = [opens[i] / closes[i - 1] - 1 - rf[i] for i in range(1, n)]
    check("overnight-only == open/prev close - rf",
          max(abs(a - b) for a, b in zip(on["gross"][1:], exp[1:])) < 1e-12)

    W = [1.0 if i >= 10 else 0.0 for i in range(n)]
    w_on, w_id = engine.next_open_exec(W)
    r = engine.simulate(dates, opens, closes, w_on, w_id, rf, cost_per_side=0.001)
    d11 = closes[11] / opens[11] - 1 - 0.001               # filled at open 11, pays one side
    d12 = closes[12] / closes[11] - 1 - rf[12]
    check("next_open: first day earns open->close only, pays entry cost", abs(r["net"][10] - d11) < 1e-12)
    check("next_open: following day earns close->close", abs(r["net"][11] - d12) < 1e-12)
    check("next_open: nothing earned before the fill", all(abs(x) < 1e-15 for x in r["net"][:10]))

    W = [1.0 if 10 <= i < 20 else 0.0 for i in range(n)]
    w_on, w_id = engine.close_exec(W)
    tr = engine.trades(engine.simulate(dates, opens, closes, w_on, w_id, rf, cost_per_side=0.001))
    check("close_exec round trip = one trade of 10 nights", len(tr) == 1 and tr[0]["nights"] == 10,
          str(tr))
    gross = closes[20] / closes[10] - 1
    check("trade return ~ gross less two sides and carry",
          abs(tr[0]["ret"] - gross) < 0.004 and tr[0]["ret"] < gross)

    lev = engine.simulate(dates, opens, closes, *engine.close_exec([2.0] * n), rf, financing_spread=0.015)
    exp2 = [2 * (closes[i] / closes[i - 1] - 1) - 2 * rf[i] - 0.015 / 252 for i in range(2, n)]
    check("2x leverage pays rf on 2 units + spread on 1",
          max(abs(a - b) for a, b in zip(lev["gross"][1:], exp2)) < 1e-12)

    print("basket")
    _, oa, ca, _ = synthetic(seed=2)
    _, ob, cb, _ = synthetic(seed=3)
    O, C = {"A": oa, "B": ob}, {"A": ca, "B": cb}
    one = basket.simulate(dates, O, C, [("A", 2, 4)], 0.001)
    exp = [0.0, ca[2] / oa[2] - 1 - 0.001, ca[3] / ca[2] - 1, ca[4] / ca[3] - 1 - 0.001, 0.0]
    check("basket: open entry, close-to-close hold, close exit, one side each",
          max(abs(a - b) for a, b in zip(one["net"][:5], exp)) < 1e-12, str([round(x, 6) for x in one["net"][:5]]))

    two = basket.simulate(dates, O, C, [("A", 1, 5), ("B", 3, 5)], 0.001)
    r_on = oa[3] / ca[2] - 1
    r_id = ((ca[3] / oa[3] - 1) + (cb[3] / ob[3] - 1)) / 2
    check("basket: entry at the open re-weights to equal weight for the session",
          abs(two["gross"][2] - ((1 + r_on) * (1 + r_id) - 1)) < 1e-12)
    check("basket: entry turnover = |1/2 - 1| on the holder + 1/2 on the entrant",
          abs(two["turnover"][2] - 1.0) < 1e-12 and abs(two["gross"][2] - two["net"][2] - 0.001) < 1e-12)

    merged = basket.merge([("A", 2, 5), ("A", 4, 8), ("A", 9, 10), ("A", 12, 13)])
    check("basket: overlapping and back-to-back intervals merge", sorted(merged) == [("A", 2, 10), ("A", 12, 13)],
          str(sorted(merged)))

    ew, k = basket.ew_universe(dates, C, {"A": 0, "B": 10})
    check("basket: EW control counts a name only once it is eligible",
          k[5] == 1 and k[20] == 2 and abs(ew[20] - ((ca[21] / ca[20] - 1) + (cb[21] / cb[20] - 1)) / 2) < 1e-12)

    print("phase-2 timing rules")
    cal = types.SimpleNamespace(dates=["2024-03-07", "2024-03-08", "2024-03-11", "2024-03-12"], n=4)
    rs = h_events.reaction_session
    check("pre-market release reacts that session", rs(cal, "2024-03-08", "07:00:00") == 1)
    check("intraday release reacts that session", rs(cal, "2024-03-08", "11:30:00") == 1)
    check("16:05 release reacts the next session", rs(cal, "2024-03-08", "16:05:00") == 2)
    check("weekend acceptance reacts on Monday", rs(cal, "2024-03-09", "10:00:00") == 2)
    check("date-only time is treated as after the close", rs(cal, "2024-03-08", "00:00:00") == 2)
    check("SEC UTC -> New York in daylight time", p2data.to_et("2026-07-30T20:30:28.000Z") == ("2026-07-30", "16:30:28"))
    check("SEC UTC -> New York in standard time", p2data.to_et("2026-01-29T21:30:05.000Z") == ("2026-01-29", "16:30:05"))
    check("SEC UTC -> New York across midnight", p2data.to_et("2026-03-03T02:10:00.000Z") == ("2026-03-02", "21:10:00"))

    lp = types.SimpleNamespace(dates=[(dt.date(2020, 1, 1) + dt.timedelta(days=i)).isoformat() for i in range(800)],
                               n=800)
    rng2 = random.Random(11)
    evs = [{"sym": f"S{i}", "known": i, "entry": i + 2, "signal": rng2.gauss(0, 1)} for i in range(700)]
    lab = {e["sym"]: e for e in h_stocks.label(lp, evs, min_prior=50)}
    prior = sorted(e["signal"] for e in evs if 35 <= e["known"] < 400)
    e400 = lab["S398"]
    check("cut-offs use only events known before entry and within 365 days",
          abs(e400["p_hi"] - h_stocks._quantile(prior, 0.8)) < 1e-12
          and abs(e400["p_lo"] - h_stocks._quantile(prior, 0.2)) < 1e-12)
    future = [dict(e, signal=99.0) if e["known"] >= 400 else dict(e) for e in evs]
    lab2 = {e["sym"]: e for e in h_stocks.label(lp, future, min_prior=50)}
    check("changing later signals leaves earlier decisions unchanged",
          all(lab[s]["side"] == lab2[s]["side"] for s in lab if lab[s]["entry"] <= 400))

    tx = [["2006-03-02", "2006-03-01", 1, "A", "P", ""], ["2007-03-05", "2007-03-02", 1, "A", "P", ""],
          ["2008-03-04", "2008-03-03", 1, "A", "S", ""],
          ["2006-05-02", "2006-05-01", 1, "B", "P", ""], ["2007-08-06", "2007-08-02", 1, "B", "P", ""],
          ["2008-11-04", "2008-11-03", 1, "B", "S", ""],
          ["2006-05-02", "2006-05-01", 1, "C", "P", ""], ["2008-11-04", "2008-11-03", 1, "C", "S", ""],
          ["2006-02-02", "2006-02-01", 1, "D", "P", ""], ["2007-02-05", "2007-02-02", 1, "D", "P", ""],
          ["2009-01-05", "2008-12-30", 1, "D", "P", ""]]
    cls = h_insider.classifier(tx)
    check("insider trading the same month three years running is routine", cls("A", 1, 2009) == "routine")
    check("insider trading every year on no fixed month is opportunistic", cls("B", 1, 2009) == "opportunistic")
    check("insider missing a year is unclassified", cls("C", 1, 2009) is None)
    check("a trade filed after 1 January can't classify that year", cls("D", 1, 2009) is None)

    print("regression / bootstrap")
    rng = random.Random(7)
    x = [rng.gauss(0, 0.01) for _ in range(5000)]
    y = [0.0004 + 1.5 * v + rng.gauss(0, 0.005) for v in x]
    reg = evaluate.ols_nw(y, [x])
    check("OLS recovers beta 1.5", abs(reg["coef"][1] - 1.5) < 3 * reg["se"][1], f"{reg['coef'][1]:.4f}")
    check("OLS recovers alpha 4bp", abs(reg["coef"][0] - 0.0004) < 3 * reg["se"][0],
          f"{reg['coef'][0] * 1e4:.2f}bp t={reg['t'][0]:.1f}")

    iid = [rng.gauss(0.0005, 0.01) for _ in range(2520)]
    sr = stats.sharpe(iid)
    boot = evaluate.bootstrap_sharpe(iid, 252, B=1000)
    med = evaluate.percentile(boot, 0.5)
    width = evaluate.percentile(boot, 0.975) - evaluate.percentile(boot, 0.025)
    check("bootstrap centred on sample Sharpe", abs(med - sr) < 0.1, f"SR {sr:.2f} median {med:.2f}")
    check("bootstrap CI width ~ 2*1.96/sqrt(years)", abs(width - 2 * 1.96 / math.sqrt(10)) < 0.25,
          f"{width:.2f}")

    mc = evaluate.mc_horizon(iid, 252, B=300)
    check("Monte Carlo horizon runs", mc is not None and 0 <= mc["p_loss"] <= 1, str(mc))

    print("look-ahead detector")

    def clean(cut):
        c = closes if cut is None else closes[:cut + 1]
        return [1.0 if 20 <= i < len(c) and c[i] > c[i - 20] else 0.0 for i in range(n)]

    def leaky(cut):
        c = closes if cut is None else closes[:cut + 1]
        return [1.0 if i + 1 < len(c) and c[i + 1] > c[i] else 0.0 for i in range(n)]

    def close_leak(cut):                                   # uses close i under close execution
        c = closes if cut is None else closes[:cut + 1]
        return [1.0 if 0 < i < len(c) and c[i] > c[i - 1] else 0.0 for i in range(n)]

    check("clean next-open signal passes", leakage.truncation_test(clean, n, lag=0)["ok"])
    check("peeking at tomorrow's close is caught", not leakage.truncation_test(leaky, n, lag=0)["ok"])
    check("using today's close under close-execution is caught",
          not leakage.truncation_test(lambda cut: close_leak(None if cut is None else cut - 1), n,
                                      lag=1)["ok"]
          or not leakage.truncation_test(close_leak, n, lag=1, n_cuts=40)["ok"])

    print("gates plumbing")
    out = evaluate.evaluate_gates(oos=iid, periods=252, reg_y=iid, reg_x=x[:len(iid)], oos_2x=iid,
                                  neighbours=[("a", iid), ("b", [v * 0.5 for v in iid])],
                                  placebo=[0.0, 0.1, 0.2], implementable=True, live=None,
                                  n_trials=93, sr_disp=0.4, block=21)
    check("gate evaluator returns a status", out["status"] in {"PASS", "WATCH", "FAIL", "NI"},
          out["status"])

    print(f"\n{'ALL TESTS PASSED' if not FAILS else 'FAILED: ' + ', '.join(FAILS)}")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
