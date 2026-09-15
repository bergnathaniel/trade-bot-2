"""
H20: bond term-premium timing (PREREG_H20.md), end to end.
=========================================================

    python3 research/run_h20.py

Same harness and gates as Phases 1-2. Prints the SHA-256 of PREREG_H20.md, writes
research/results/h20.json and refreshes the P3-H20 rows of REGISTRY.csv (other rows untouched).

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
import h_term  # noqa: E402
import run_phase1 as p1  # noqa: E402
import sources  # noqa: E402
from h_common import rf_list, spy_excess, yahoo  # noqa: E402

PREREG = os.path.join(HERE, "PREREG_H20.md")
OUT = os.path.join(HERE, "results", "h20.json")
N_TRIALS = 101  # 76 legacy + 17 Phase-1 + 4 Phase-2 + 3 intraday clusters + TERM


def ief_excess():
    y = yahoo("IEF")
    rf = rf_list(y["dates"])
    return {y["dates"][i]: y["close"][i] / y["close"][i - 1] - 1 - rf[i] for i in range(1, len(y["dates"]))}


def update_registry(results):
    with open(p1.REGISTRY, newline="") as f:
        rows = list(csv.DictReader(f))
    ids = {f"P3-{x['meta']['id']}" for x in results}
    keep = [r for r in rows if r["id"] not in ids]
    today = time.strftime("%Y-%m-%d")
    for x in results:
        m, o = x["meta"], x["metrics_oos"]
        keep.append({
            "id": f"P3-{m['id']}", "date": today, "phase": "phase3", "cluster": m["cluster"],
            "strategy": m["name"], "hypothesis": m["hypothesis"], "data": m["data"],
            "test_period": f"{x['metrics_full']['start']}..{x['metrics_full']['end']}",
            "oos_period": f"{o['start']}..{o['end']}",
            "oos_cagr": f"{o['cagr_excess'] * 100:+.1f}% ex-cash", "oos_sharpe": f"{x['sharpe_oos']:.2f}",
            "max_dd": f"{o['max_dd'] * 100:.0f}%", "costs": m["costs"],
            "n_configs": 1 + x["n_neighbours"], "status": x["status"], "file": "research/run_h20.py",
            "notes": f"failed {','.join(x['failed'])}" if x["failed"] else "no gate failed"})
    with open(p1.REGISTRY, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=p1.FIELDS)
        w.writeheader()
        w.writerows(keep)
    print(f"updated REGISTRY.csv ({len(results)} H20 rows)")


def main():
    t0 = time.time()
    digest = hashlib.sha256(open(PREREG, "rb").read()).hexdigest()
    print(p1.BAR)
    print("H20 - bond term-premium timing (pre-registered)")
    print(f"PREREG_H20.md sha256 = {digest}")
    print(p1.BAR)
    with open(os.path.join(HERE, "results", "phase1.json")) as f:
        disp = json.load(f)["sr_dispersion"]
    print(f"deflated-Sharpe trial count N = {N_TRIALS}; SR dispersion {disp:.3f} (Phase 1)")

    mktrf = sources.french_column(p1.FF3, "Mkt-RF")
    cols, ffd = sources.french_table("F-F_Research_Data_Factors_daily_CSV.zip")
    jm, jr = sources.col_index(cols, "Mkt-RF"), sources.col_index(cols, "RF")
    mkt_total = {d: v[jm] + v[jr] for d, v in ffd.items() if v[jm] is not None and v[jr] is not None}
    regimes = evaluate.Regimes(mkt_total, sources.fred("DGS10"), sources.fred("USREC"),
                               sources.fred("CPIAUCSL"))
    ff_daily, ff_monthly = p1.factor_data()
    bench = {"SPY": spy_excess(), "MKT": mktrf, "IEF": ief_excess()}

    t = time.time()
    records = h_term.h20()
    print(f"  built H20  {len(records)} record(s) in {time.time() - t:6.1f}s", flush=True)
    results = []
    for r in records:
        results.append(p1.evaluate_record(r, bench, regimes, ff_daily, ff_monthly, N_TRIALS, disp,
                                          sensitivity=(1, 200)))
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
