"""
Phase 5: pre-holiday, options-expiration week, Faber GTAA5, trend-filtered leverage (PREREG_PHASE5.md).
=====================================================================================================

    python3 research/run_phase5.py

Same harness and gates as Phases 1-4. Prints the SHA-256 of PREREG_PHASE5.md, writes
research/results/phase5.json and refreshes the P5 rows of REGISTRY.csv (other rows untouched).

Descriptive of the past only. Not investment advice.
"""

import csv
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import evaluate  # noqa: E402
import h_phase5  # noqa: E402
import run_phase1 as p1  # noqa: E402
import sources  # noqa: E402
import stats  # noqa: E402
from h_common import slice_from, spy_excess  # noqa: E402

PREREG = os.path.join(HERE, "PREREG_PHASE5.md")
OUT = os.path.join(HERE, "results", "phase5.json")
N_TRIALS = 108  # 76 legacy + 17 Phase-1 + 4 Phase-2 + 3 intraday + TERM + 3 Phase-4 + these 4


def update_registry(results):
    with open(p1.REGISTRY, newline="") as f:
        rows = list(csv.DictReader(f))
    ids = {f"P5-{x['meta']['id']}" for x in results}
    keep = [r for r in rows if r["id"] not in ids]
    today = time.strftime("%Y-%m-%d")
    for x in results:
        m, o = x["meta"], x["metrics_oos"]
        keep.append({
            "id": f"P5-{m['id']}", "date": today, "phase": "phase5", "cluster": m["cluster"],
            "strategy": m["name"], "hypothesis": m["hypothesis"], "data": m["data"],
            "test_period": f"{x['metrics_full']['start']}..{x['metrics_full']['end']}",
            "oos_period": f"{o['start']}..{o['end']}",
            "oos_cagr": f"{o['cagr_excess'] * 100:+.1f}% ex-cash", "oos_sharpe": f"{x['sharpe_oos']:.2f}",
            "max_dd": f"{o['max_dd'] * 100:.0f}%", "costs": m["costs"],
            "n_configs": 1 + x["n_neighbours"], "status": x["status"], "file": "research/run_phase5.py",
            "notes": f"failed {','.join(x['failed'])}" if x["failed"] else "no gate failed"})
    with open(p1.REGISTRY, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=p1.FIELDS)
        w.writeheader()
        w.writerows(keep)
    print(f"updated REGISTRY.csv ({len(results)} Phase-5 rows)")


def main():
    t0 = time.time()
    digest = hashlib.sha256(open(PREREG, "rb").read()).hexdigest()
    print(p1.BAR)
    print("PHASE 5 - pre-holiday, options-expiration week, GTAA5, trend-filtered leverage (pre-registered)")
    print(f"PREREG_PHASE5.md sha256 = {digest}")
    print(p1.BAR)
    with open(os.path.join(HERE, "results", "phase1.json")) as f:
        p1_disp = json.load(f)["sr_dispersion"]

    mktrf = sources.french_column(p1.FF3, "Mkt-RF")
    cols, ffd = sources.french_table("F-F_Research_Data_Factors_daily_CSV.zip")
    jm, jr = sources.col_index(cols, "Mkt-RF"), sources.col_index(cols, "RF")
    mkt_total = {d: v[jm] + v[jr] for d, v in ffd.items() if v[jm] is not None and v[jr] is not None}
    regimes = evaluate.Regimes(mkt_total, sources.fred("DGS10"), sources.fred("USREC"),
                               sources.fred("CPIAUCSL"))
    ff_daily, ff_monthly = p1.factor_data()
    bench = {"SPY": spy_excess(), "MKT": mktrf, "EW5": h_phase5.ew5_excess()}

    records = []
    for label, fn in (("H34", h_phase5.h34), ("H35", h_phase5.h35), ("H36", h_phase5.h36), ("H37", h_phase5.h37)):
        t = time.time()
        got = fn()
        records += got
        print(f"  built {label}  {len(got)} record(s) in {time.time() - t:6.1f}s", flush=True)
    oos_sr = [stats.sharpe(slice_from(r["dates"], r["net"], r["oos_start"])[1], periods=r["periods"])
              for r in records]
    disp = max(p1_disp, stats.stdev(oos_sr))
    print(f"deflated-Sharpe trial count N = {N_TRIALS}; SR dispersion: Phase-5 {stats.stdev(oos_sr):.3f}, "
          f"Phase-1 {p1_disp:.3f} -> using {disp:.3f}")

    results = []
    for r in records:
        results.append(p1.evaluate_record(r, bench, regimes, ff_daily, ff_monthly, N_TRIALS, disp,
                                          sensitivity=(4, 200)))
        p1.print_record(results[-1])
    p1.print_summary(results, N_TRIALS, disp)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(p1.clean({"prereg_sha256": digest, "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "n_trials": N_TRIALS, "sr_dispersion": disp, "results": results}), f, indent=1)
    print(f"\nwrote {os.path.relpath(OUT, os.path.dirname(HERE))}")
    update_registry(results)
    print(f"wall time {time.time() - t0:.0f}s\n\nDescriptive of the past only. Not investment advice.")


if __name__ == "__main__":
    main()
