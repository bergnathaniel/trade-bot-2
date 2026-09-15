"""
Phase 2: SEC-filing events and the Treasury auction cycle.
=========================================================

    python3 research/p2data.py        # build the SEC + Yahoo caches first (~20-30 min cold)
    python3 research/run_phase2.py

Same harness and gates as Phase 1, plus G10 (survivorship-free data). Prints
the SHA-256 of PREREG_PHASE2.md, writes research/results/phase2.json and
refreshes the Phase-2 rows of REGISTRY.csv (other rows are never touched).

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
import h_auction  # noqa: E402
import h_events  # noqa: E402
import h_insider  # noqa: E402
import p2data  # noqa: E402
import run_phase1 as p1  # noqa: E402
import sources  # noqa: E402
import stats  # noqa: E402
from h_common import rf_list, slice_from, spy_excess, yahoo  # noqa: E402

PREREG = os.path.join(HERE, "PREREG_PHASE2.md")
OUT = os.path.join(HERE, "results", "phase2.json")
N_P1_CLUSTERS, N_P2_CLUSTERS, N_BASE = 17, 4, 8


def ief_excess():
    y = yahoo("IEF")
    rf = rf_list(y["dates"])
    return {y["dates"][i]: y["close"][i] / y["close"][i - 1] - 1 - rf[i] for i in range(1, len(y["dates"]))}


def update_registry(rows, results, suffix=""):
    ids = {f"P2-{x['meta']['id']}{suffix}" for x in results}
    keep = [r for r in rows if r["id"] not in ids]
    today = time.strftime("%Y-%m-%d")
    for x in results:
        m, o = x["meta"], x["metrics_oos"]
        keep.append({
            "id": f"P2-{m['id']}{suffix}", "date": today, "phase": "phase2", "cluster": m["cluster"],
            "strategy": m["name"] + (" [amendment A1: splice fix]" if suffix else ""),
            "hypothesis": m["hypothesis"], "data": m["data"],
            "test_period": f"{x['metrics_full']['start']}..{x['metrics_full']['end']}",
            "oos_period": f"{o['start']}..{o['end']}",
            "oos_cagr": f"{o['cagr_excess'] * 100:+.1f}% ex-cash", "oos_sharpe": f"{x['sharpe_oos']:.2f}",
            "max_dd": f"{o['max_dd'] * 100:.0f}%", "costs": m["costs"],
            "n_configs": 1 + x["n_neighbours"], "status": x["status"], "file": "research/run_phase2.py",
            "notes": f"failed {','.join(x['failed'])}" if x["failed"] else "no gate failed"})
    with open(p1.REGISTRY, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=p1.FIELDS)
        w.writeheader()
        w.writerows(keep)
    print(f"updated REGISTRY.csv ({len(results)} Phase-2 rows)")


def main():
    t0 = time.time()
    a1 = "--A1" in sys.argv[1:]
    out_path = os.path.join(HERE, "results", "phase2_A1.json") if a1 else OUT
    if a1:
        import h_stocks
        h_stocks.SPLICE_FIX = True
    digest = hashlib.sha256(open(PREREG, "rb").read()).hexdigest()
    print(p1.BAR)
    print("PHASE 2 - pre-registered SEC-filing event and auction tests" + ("   [AMENDMENT A1: splice fix]" if a1 else ""))
    print(f"PREREG_PHASE2.md sha256 = {digest}")
    print(p1.BAR)

    with open(p1.REGISTRY, newline="") as f:
        rows = list(csv.DictReader(f))
    legacy = sum(int(r["n_configs"]) for r in rows if r["phase"] == "legacy")
    n_trials = legacy + N_P1_CLUSTERS + N_P2_CLUSTERS
    with open(os.path.join(HERE, "results", "phase1.json")) as f:
        p1_disp = json.load(f)["sr_dispersion"]
    print(f"deflated-Sharpe trial count: {legacy} legacy + {N_P1_CLUSTERS} Phase-1 + "
          f"{N_P2_CLUSTERS} Phase-2 clusters = {n_trials}")
    print(f"data coverage: {p2data.coverage()}")

    spy_ex = spy_excess()
    mktrf = sources.french_column(p1.FF3, "Mkt-RF")
    cols, ffd = sources.french_table("F-F_Research_Data_Factors_daily_CSV.zip")
    jm, jr = sources.col_index(cols, "Mkt-RF"), sources.col_index(cols, "RF")
    mkt_total = {d: v[jm] + v[jr] for d, v in ffd.items() if v[jm] is not None and v[jr] is not None}
    regimes = evaluate.Regimes(mkt_total, sources.fred("DGS10"), sources.fred("USREC"),
                               sources.fred("CPIAUCSL"))
    ff_daily, ff_monthly = p1.factor_data()
    bench = {"SPY": spy_ex, "MKT": mktrf, "IEF": ief_excess()}

    records = []
    for label, fn in [("H14", h_auction.h14), ("H11", h_events.h11), ("H12", h_events.h12),
                      ("H13", h_insider.h13)]:
        t = time.time()
        got = fn()
        records += got
        print(f"  built {label:<4} {len(got)} record(s) in {time.time() - t:6.1f}s", flush=True)
    assert len(records) == N_BASE, f"expected {N_BASE} base configs, got {len(records)}"
    if a1:
        import h_stocks
        print(f"A1 splices rescaled (symbol, date, factor): {h_stocks.panel().splices}")

    oos_sr = [stats.sharpe(slice_from(r["dates"], r["net"], r["oos_start"])[1], periods=r["periods"])
              for r in records]
    disp = max(p1_disp, stats.stdev(oos_sr))
    print(f"Sharpe dispersion: Phase-2 base configs {stats.stdev(oos_sr):.3f}, Phase-1 {p1_disp:.3f} "
          f"-> using {disp:.3f}")

    results = []
    for r in records:
        results.append(p1.evaluate_record(r, bench, regimes, ff_daily, ff_monthly, n_trials, disp,
                                          sensitivity=(N_P2_CLUSTERS, 200)))
        p1.print_record(results[-1])
    p1.print_summary(results, n_trials, disp)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(p1.clean({"prereg_sha256": digest, "amendment": "A1" if a1 else None,
                            "run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "n_trials": n_trials, "sr_dispersion": disp, "coverage": p2data.coverage(),
                            "results": results}), f, indent=1)
    print(f"\nwrote {os.path.relpath(out_path, os.path.dirname(HERE))}")
    update_registry(rows, results, suffix="-A1" if a1 else "")
    print(f"wall time {time.time() - t0:.0f}s\n\nDescriptive of the past only. Not investment advice.")


if __name__ == "__main__":
    main()
