"""
Phase 1: every pre-registered hypothesis through one honest harness.
====================================================================

    python3 research/run_phase1.py

Prints the SHA-256 of PREREG_PHASE1.md so every result is tied to the exact
rules it was tested against, then for each hypothesis: the full metric set,
the nine gates, regimes, crises, factor exposures, Monte Carlo bands and the
look-ahead test. Writes research/results/phase1.json and refreshes the Phase-1
rows of REGISTRY.csv (legacy rows are never touched).

Descriptive of the past only. Not investment advice.
"""

import collections
import csv
import hashlib
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import evaluate  # noqa: E402
import h_calendar  # noqa: E402
import h_factors  # noqa: E402
import h_vol  # noqa: E402
import sources  # noqa: E402
import stats  # noqa: E402
from h_common import slice_from, spy_excess  # noqa: E402

PREREG = os.path.join(HERE, "PREREG_PHASE1.md")
REGISTRY = os.path.join(HERE, "REGISTRY.csv")
OUT = os.path.join(HERE, "results", "phase1.json")
FF3 = "F-F_Research_Data_Factors_CSV.zip"
N_CLUSTERS, N_BASE = 17, 31
BAR = "=" * 110
FACTORS = ("Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom")
OWN_FACTOR = {"SMB": "SMB", "HML": "HML", "RMW": "RMW", "CMA": "CMA", "UMD": "Mom"}
REGIME_ORDER = ["bull_bear=bull", "bull_bear=bear", "vol=low", "vol=high", "rates=falling",
                "rates=rising", "recession=expansion", "recession=recession", "inflation=low",
                "inflation=high"]
FIELDS = ["id", "date", "phase", "cluster", "strategy", "hypothesis", "data", "test_period",
          "oos_period", "oos_cagr", "oos_sharpe", "max_dd", "costs", "n_configs", "status",
          "file", "notes"]


# ------------------------------------------------------------------ helpers

def pct(x, nd=1):
    return "n/a" if x is None else f"{x * 100:+.{nd}f}%"


def clean(o, nd=6):
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else round(o, nd)
    if isinstance(o, dict):
        return {str(k): clean(v, nd) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v, nd) for v in o]
    return o


def compact(o, limit=1400):
    s = json.dumps(clean(o, 4), separators=(", ", ": "))
    return s if len(s) <= limit else s[:limit] + " ..."


def factor_data():
    daily, monthly = {}, {}
    for store, f5, mom in ((daily, "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip",
                            "F-F_Momentum_Factor_daily_CSV.zip"),
                           (monthly, "F-F_Research_Data_5_Factors_2x3_CSV.zip",
                            "F-F_Momentum_Factor_CSV.zip")):
        for k in FACTORS[:5]:
            store[k] = sources.french_column(f5, k)
        store["Mom"] = sources.french_column(mom, "Mom")
    return daily, monthly


def factor_regression(dates, y, periods, ff, exclude=None):
    names = [k for k in FACTORS if k != exclude]
    keep = [i for i, d in enumerate(dates) if all(d in ff[k] for k in names)]
    if len(keep) < 36:
        return None
    reg = evaluate.ols_nw([y[i] for i in keep], [[ff[k][dates[i]] for i in keep] for k in names])
    return {"n": len(keep), "alpha_ann": reg["coef"][0] * periods, "alpha_t": reg["t"][0],
            "r2": reg["r2"], "betas": {k: [reg["coef"][j + 1], reg["t"][j + 1]]
                                       for j, k in enumerate(names)}}


def monthly_curve(dates, net, bmap, periods):
    if periods == 12:
        return [[d, x, bmap.get(d)] for d, x in zip(dates, net)]
    s = evaluate.period_returns(dates, net)
    bd = [d for d in dates if d in bmap]
    b = evaluate.period_returns(bd, [bmap[d] for d in bd])
    return [[m, s[m], b.get(m)] for m in sorted(s)]


# --------------------------------------------------------------- evaluation

def evaluate_record(r, bench_maps, regimes, ffd, ffm, n_trials, disp, sensitivity=(17, 200)):
    P, start = r["periods"], r["oos_start"]
    block = 21 if P == 252 else 6
    od, onet = slice_from(r["dates"], r["net"], start)
    o2 = slice_from(r["dates"], r["net_2x"], start)[1]
    og = slice_from(r["dates"], r["gross"], start)[1]
    ysrc = slice_from(r["dates"], r["alpha_y"], start)[1] if r["alpha_y"] else onet
    bmap = bench_maps[r["bench"]]
    keep = [i for i, d in enumerate(od) if d in bmap]
    neighbours = [(nm, slice_from(nd, nn, start)[1]) for nm, nd, nn in r["neighbours"]]
    neighbours = [(nm, s) for nm, s in neighbours if len(s) > 24]

    g = evaluate.evaluate_gates(
        oos=onet, periods=P, reg_y=[ysrc[i] for i in keep], reg_x=[bmap[od[i]] for i in keep],
        oos_2x=o2, neighbours=neighbours, placebo=r["placebo"],
        implementable=r["implementable"], live=r["live"], n_trials=n_trials, sr_disp=disp,
        block=block, sensitivity=sensitivity, placebo_actual=r.get("placebo_actual"),
        survivorship_free=None if "survivor_universe" not in r else not r["survivor_universe"])

    trades_oos = [t for t in r["trades"] if t["entry"] >= start] if r["trades"] else None
    part = lambda key: slice_from(r["dates"], r[key], start)[1] if r[key] else None  # noqa: E731
    bd = [d for d in od if d in bmap]
    exclude = OWN_FACTOR.get(r["cluster"]) if r["id"].startswith("H08") else None
    return dict(
        meta={k: r[k] for k in ("id", "cluster", "name", "hypothesis", "data", "costs",
                                "oos_start", "bench", "implementable")},
        status=g["status"], failed=g["failed"], gates=g["gates"], sharpe_oos=g["sharpe"],
        ci=g["ci"], alpha_ann=g["alpha_ann"], alpha_t=g["alpha_t"], beta=g["beta"], dsr=g["dsr"],
        metrics_full=evaluate.full_metrics(r["dates"], r["net"], gross=r["gross"], periods=P,
                                           trades=r["trades"], expo=r["expo"],
                                           turnover=r["turnover"], rf=r["rf"]),
        metrics_oos=evaluate.full_metrics(od, onet, gross=og, periods=P, trades=trades_oos,
                                          turnover=part("turnover"), rf=part("rf")),
        bench_oos=evaluate.full_metrics(bd, [bmap[d] for d in bd], periods=P),
        regimes_oos=evaluate.regime_table(od, onet, P, regimes),
        regimes_full=evaluate.regime_table(r["dates"], r["net"], P, regimes),
        crises={"strategy": evaluate.crisis_returns(r["dates"], r["net"]),
                "benchmark": evaluate.crisis_returns(r["dates"], [bmap.get(d, 0.0) for d in r["dates"]])},
        mc={"1y": evaluate.mc_horizon(onet, P, block=block),
            "3y": evaluate.mc_horizon(onet, 3 * P, block=block)},
        factor=factor_regression(od, ysrc, P, ffd if P == 252 else ffm, exclude),
        leakage=r["leakage"], live=r["live"], extra=r["extra"], notes=r["notes"],
        unregistered=r["unregistered"], n_neighbours=len(neighbours),
        curve=monthly_curve(od, onet, bmap, P))


# ----------------------------------------------------------------- printing

def print_record(x):
    m, f, o, b = x["meta"], x["metrics_full"], x["metrics_oos"], x["bench_oos"]
    print(f"\n{BAR}\n{m['id']}  {m['name']}   ->  {x['status']}"
          + (f"   (failed {', '.join(x['failed'])})" if x["failed"] else ""))
    print(BAR)
    print(f"  {m['hypothesis']}")
    print(f"  data: {m['data']}   costs: {m['costs']}")
    print(f"  full    {f['start']}..{f['end']} ({f['years']:.1f}y)  exCAGR {pct(f['cagr_excess'])}  "
          f"vol {f['vol'] * 100:.1f}%  SR {f['sharpe']:.2f}  maxDD {pct(f['max_dd'], 0)}")
    print(f"  OOS     {o['start']}..{o['end']} ({o['years']:.1f}y)  exCAGR {pct(o['cagr_excess'])} "
          f"(gross {pct(o['gross_cagr_excess'])})  vol {o['vol'] * 100:.1f}%  SR {o['sharpe']:.2f}  "
          f"Sortino {o['sortino']:.2f}  maxDD {pct(o['max_dd'], 0)}  Calmar {o['calmar']:.2f}")
    print(f"  bench   {m['bench']} same window  exCAGR {pct(b['cagr_excess'])}  vol {b['vol'] * 100:.1f}%  "
          f"SR {b['sharpe']:.2f}  maxDD {pct(b['max_dd'], 0)}")
    print(f"  tails   skew {o['skew']:+.2f}  kurt {o['kurt']:.1f}  CVaR5 {pct(o['cvar5'], 2)}  "
          f"worst day {pct(o['worst_day'])}  worst month {pct(o['worst_month'])}  "
          f"longest recovery {o['recovery_obs']} obs{' (still underwater)' if o['underwater_at_end'] else ''}  "
          f"AC1 {o['ac1']:+.2f}")
    if "n_trades" in o:
        pf = o["profit_factor"]
        print(f"  trades  {o['n_trades']}  win {o['win_rate'] * 100:.0f}%  avg {pct(o['avg_trade'], 2)}  "
              f"median {pct(o['median_trade'], 2)}  PF {pf if pf is None else round(pf, 2)}  "
              f"avg nights held {o['avg_nights_held']:.1f}")
    if f.get("time_in_market") is not None:
        print(f"  expo    time in market {f['time_in_market'] * 100:.0f}%  avg long {f['long_exposure']:.2f}  "
              f"max weight {f['max_weight']:.2f}  turnover {f.get('ann_turnover', 0):.0f}x/yr")
    for gid, v in x["gates"].items():
        flag = "PASS" if v["pass"] else ("FAIL" if v["pass"] is False else " n/a")
        print(f"  {gid} {flag}  {v['detail']}")
    cells = [f"{k.split('=')[1]} {x['regimes_oos'][k]['sharpe']:+.2f} ({x['regimes_oos'][k]['share'] * 100:.0f}%)"
             for k in REGIME_ORDER if k in x["regimes_oos"] and x["regimes_oos"][k]["sharpe"] is not None]
    print("  regimes (OOS Sharpe, share of obs): " + "  ".join(cells))
    cr = x["crises"]
    print("  crises  " + "  ".join(f"{k} {pct(cr['strategy'][k])} vs {pct(cr['benchmark'][k])}"
                                   for k in cr["strategy"] if cr["strategy"][k] is not None))
    for h, mc in x["mc"].items():
        if mc:
            print(f"  MC {h}   P(loss) {mc['p_loss'] * 100:.0f}%  p5 {pct(mc['p5_return'])}  "
                  f"median {pct(mc['median_return'])}  p95 {pct(mc['p95_return'])}  p5 maxDD {pct(mc['p5_max_dd'], 0)}")
    fr = x["factor"]
    if fr:
        print(f"  factors alpha {pct(fr['alpha_ann'], 2)}/yr t {fr['alpha_t']:.2f}  R2 {fr['r2']:.2f}  "
              + "  ".join(f"{k} {v[0]:+.2f}({v[1]:+.1f})" for k, v in fr["betas"].items()))
    lk = x["leakage"]
    print("  look-ahead truncation test: " + ("n/a (portfolios formed by the data provider)" if lk is None
                                             else "PASS" if lk["ok"] else f"FAIL {lk}"))
    if x["extra"]:
        print(f"  extra   {compact(x['extra'])}")
    for note in x["notes"]:
        print(f"  note    {note}")
    for u in x["unregistered"]:
        print(f"  unreg   {u}")


def print_summary(results, n_trials, disp):
    print(f"\n{BAR}\nSUMMARY - out-of-sample, net of costs, excess of cash   "
          f"(deflated-Sharpe trials N={n_trials}, SR dispersion {disp:.2f})\n{BAR}")
    print(f"{'id':<10} {'name':<46} {'yrs':>5} {'exCAGR':>7} {'SR':>5} {'CI lo':>6} {'bench':>6} "
          f"{'alpha':>7} {'t':>5} {'DSR':>5} {'maxDD':>6}  {'status':<6} failed")
    print("-" * 132)
    for x in results:
        o, b = x["metrics_oos"], x["bench_oos"]
        print(f"{x['meta']['id']:<10} {x['meta']['name'][:46]:<46} {o['years']:>5.1f} "
              f"{o['cagr_excess'] * 100:>+6.1f}% {x['sharpe_oos']:>5.2f} {x['ci'][0]:>6.2f} "
              f"{b['sharpe']:>6.2f} {x['alpha_ann'] * 100:>+6.1f}% {x['alpha_t']:>5.2f} "
              f"{x['dsr']:>5.2f} {o['max_dd'] * 100:>+5.0f}%  {x['status']:<6} {','.join(x['failed'])}")
    counts = collections.Counter(x["status"] for x in results)
    print("-" * 132)
    print("  " + "   ".join(f"{k}: {counts.get(k, 0)}" for k in ("PASS", "WATCH", "NI", "FAIL")))


# ------------------------------------------------------------------ outputs

def save(results, amendments, digest, n_trials, disp):
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(clean({"prereg_sha256": digest, "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                         "n_trials": n_trials, "sr_dispersion": disp, "results": results,
                         "amendments": amendments}), f, indent=1)
    print(f"\nwrote {os.path.relpath(OUT, os.path.dirname(HERE))}")


def update_registry(rows, results):
    keep = [r for r in rows if r["phase"] != "phase1"]
    today = time.strftime("%Y-%m-%d")
    for x in results:
        m, o = x["meta"], x["metrics_oos"]
        keep.append({
            "id": f"P1-{m['id']}", "date": today, "phase": "phase1", "cluster": m["cluster"],
            "strategy": m["name"], "hypothesis": m["hypothesis"], "data": m["data"],
            "test_period": f"{x['metrics_full']['start']}..{x['metrics_full']['end']}",
            "oos_period": f"{o['start']}..{o['end']}",
            "oos_cagr": f"{o['cagr_excess'] * 100:+.1f}% ex-cash", "oos_sharpe": f"{x['sharpe_oos']:.2f}",
            "max_dd": f"{o['max_dd'] * 100:.0f}%", "costs": m["costs"],
            "n_configs": 1 + x["n_neighbours"], "status": x["status"],
            "file": "research/run_phase1.py",
            "notes": ("amendment A1 (index bad-print fix), reported alongside P1-H01; "
                      if m["id"].endswith("-A1") else "")
                     + (f"failed {','.join(x['failed'])}" if x["failed"] else "no gate failed")})
    with open(REGISTRY, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(keep)
    print(f"updated REGISTRY.csv ({len(results)} Phase-1 rows)")


# --------------------------------------------------------------------- main

def main():
    t0 = time.time()
    digest = hashlib.sha256(open(PREREG, "rb").read()).hexdigest()
    print(BAR)
    print("PHASE 1 - pre-registered edge tests")
    print(f"PREREG_PHASE1.md sha256 = {digest}")
    print(BAR)

    with open(REGISTRY, newline="") as f:
        rows = list(csv.DictReader(f))
    legacy = sum(int(r["n_configs"]) for r in rows if r["phase"] == "legacy")
    n_trials = legacy + N_CLUSTERS
    print(f"deflated-Sharpe trial count: {legacy} legacy configs + {N_CLUSTERS} Phase-1 clusters = {n_trials}")

    spy_ex = spy_excess()
    mktrf, rf_m = sources.french_column(FF3, "Mkt-RF"), sources.french_column(FF3, "RF")
    cols, ffd = sources.french_table("F-F_Research_Data_Factors_daily_CSV.zip")
    jm, jr = sources.col_index(cols, "Mkt-RF"), sources.col_index(cols, "RF")
    mkt_total = {d: v[jm] + v[jr] for d, v in ffd.items() if v[jm] is not None and v[jr] is not None}
    regimes = evaluate.Regimes(mkt_total, sources.fred("DGS10"), sources.fred("USREC"),
                               sources.fred("CPIAUCSL"))
    ff_daily, ff_monthly = factor_data()

    builders = [("H01", h_vol.h01), ("H02", lambda: h_vol.h02(spy_ex)), ("H03", h_vol.h03),
                ("H04", h_calendar.h04), ("H05", lambda: h_calendar.h05(spy_ex)),
                ("H06", h_calendar.h06), ("H07", h_vol.h07),
                ("H08/H09", lambda: h_factors.h08_h09(mktrf, rf_m, spy_ex)),
                ("H10", lambda: h_factors.h10(mktrf, rf_m))]
    records = []
    for label, fn in builders:
        t = time.time()
        got = fn()
        records += got
        print(f"  built {label:<8} {len(got):>2} record(s) in {time.time() - t:5.1f}s")
    assert len(records) == N_BASE, f"expected {N_BASE} base configs, got {len(records)}"

    oos_sr = [stats.sharpe(slice_from(r["dates"], r["net"], r["oos_start"])[1], periods=r["periods"])
              for r in records]
    disp = stats.stdev(oos_sr)
    print(f"out-of-sample Sharpe dispersion across the {N_BASE} base configs: {disp:.3f}")

    bench = {"SPY": spy_ex, "MKT": mktrf}
    results = []
    for r in records:
        results.append(evaluate_record(r, bench, regimes, ff_daily, ff_monthly, n_trials, disp))
        print_record(results[-1])
    print_summary(results, n_trials, disp)

    # Amendments are reported ALONGSIDE the frozen spec, never instead of it, and
    # never feed the trial count or the dispersion (PREREG_PHASE1.md, Amendments).
    print(f"\n{BAR}\nAMENDMENTS - reported alongside the original; the original spec stays the headline\n{BAR}")
    amendments = [evaluate_record(r, bench, regimes, ff_daily, ff_monthly, n_trials, disp)
                  for r in h_vol.h01(amended=True)]
    for x in amendments:
        print_record(x)
    save(results, amendments, digest, n_trials, disp)
    update_registry(rows, results + amendments)
    print(f"wall time {time.time() - t0:.0f}s\n\nDescriptive of the past only. Not investment advice.")


if __name__ == "__main__":
    main()
