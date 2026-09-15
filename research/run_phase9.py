"""
Phase 9: crypto trend-following ensemble (PREREG_PHASE9.md).
============================================================

    python3 research/p9data.py      (once: Coinbase daily candles)
    python3 research/run_phase9.py

The same gates as Phases 1-8 on a 365-day crypto calendar. Prints the SHA-256 of PREREG_PHASE9.md, writes
research/results/phase9.json and refreshes the P9 rows of REGISTRY.csv (other rows untouched).

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
import h_phase9  # noqa: E402
import run_phase1 as p1  # noqa: E402
import stats  # noqa: E402
from h_common import slice_from  # noqa: E402

PREREG = os.path.join(HERE, "PREREG_PHASE9.md")
OUT = os.path.join(HERE, "results", "phase9.json")
N_TRIALS = 118  # 116 through Phase 8 + these 2
P, BLOCK = h_phase9.PERIODS, 21


def evaluate_record(r, bench, disp):
    start = r["oos_start"]
    od, onet = slice_from(r["dates"], r["net"], start)
    o2 = slice_from(r["dates"], r["net_2x"], start)[1]
    og = slice_from(r["dates"], r["gross"], start)[1]
    keep = [i for i, d in enumerate(od) if d in bench]
    neighbours = [(nm, slice_from(nd, nn, start)[1]) for nm, nd, nn in r["neighbours"]]
    g = evaluate.evaluate_gates(
        oos=onet, periods=P, reg_y=[onet[i] for i in keep], reg_x=[bench[od[i]] for i in keep], oos_2x=o2,
        neighbours=neighbours, placebo=r["placebo"], implementable=r["implementable"], live=None,
        n_trials=N_TRIALS, sr_disp=disp, block=BLOCK, sensitivity=(2, 200),
        survivorship_free=not r["survivor_universe"])
    part = lambda key: slice_from(r["dates"], r[key], start)[1]  # noqa: E731
    bd = [d for d in od if d in bench]
    return dict(
        meta={k: r[k] for k in ("id", "cluster", "name", "hypothesis", "data", "costs", "oos_start", "bench",
                                "implementable")},
        status=g["status"], failed=g["failed"], gates=g["gates"], sharpe_oos=g["sharpe"], ci=g["ci"],
        alpha_ann=g["alpha_ann"], alpha_t=g["alpha_t"], beta=g["beta"], dsr=g["dsr"],
        metrics_full=evaluate.full_metrics(r["dates"], r["net"], gross=r["gross"], periods=P, turnover=r["turnover"],
                                           rf=r["rf"]),
        metrics_oos=evaluate.full_metrics(od, onet, gross=og, periods=P, turnover=part("turnover"), rf=part("rf")),
        bench_oos=evaluate.full_metrics(bd, [bench[d] for d in bd], periods=P),
        regimes_oos={}, regimes_full={},
        crises={"strategy": evaluate.crisis_returns(r["dates"], r["net"]),
                "benchmark": evaluate.crisis_returns(r["dates"], [bench.get(d, 0.0) for d in r["dates"]])},
        mc={"1y": evaluate.mc_horizon(onet, P, block=BLOCK)}, factor=None,
        leakage=r["leakage"], live=None, extra=r["extra"], notes=r["notes"], unregistered=r["unregistered"],
        n_neighbours=len(neighbours))


def update_registry(results):
    with open(p1.REGISTRY, newline="") as f:
        rows = list(csv.DictReader(f))
    ids = {f"P9-{x['meta']['id']}" for x in results}
    keep = [r for r in rows if r["id"] not in ids]
    today = time.strftime("%Y-%m-%d")
    for x in results:
        m, o = x["meta"], x["metrics_oos"]
        keep.append({
            "id": f"P9-{m['id']}", "date": today, "phase": "phase9", "cluster": m["cluster"],
            "strategy": m["name"], "hypothesis": m["hypothesis"], "data": m["data"],
            "test_period": f"{x['metrics_full']['start']}..{x['metrics_full']['end']}",
            "oos_period": f"{o['start']}..{o['end']}",
            "oos_cagr": f"{o['cagr_excess'] * 100:+.1f}% ex-cash", "oos_sharpe": f"{x['sharpe_oos']:.2f}",
            "max_dd": f"{o['max_dd'] * 100:.0f}%", "costs": m["costs"],
            "n_configs": 1 + x["n_neighbours"], "status": x["status"], "file": "research/run_phase9.py",
            "notes": f"failed {','.join(x['failed'])}" if x["failed"] else "no gate failed"})
    with open(p1.REGISTRY, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=p1.FIELDS)
        w.writeheader()
        w.writerows(keep)
    print(f"updated REGISTRY.csv ({len(results)} Phase-9 rows)")


def main():
    t0 = time.time()
    digest = hashlib.sha256(open(PREREG, "rb").read()).hexdigest()
    print(p1.BAR)
    print("PHASE 9 - crypto trend-following ensemble (pre-registered)")
    print(f"PREREG_PHASE9.md sha256 = {digest}")
    print(p1.BAR)
    with open(os.path.join(HERE, "results", "phase1.json")) as f:
        p1_disp = json.load(f)["sr_dispersion"]
    bench = h_phase9.btc_excess()

    records = []
    for label, fn in (("H46", h_phase9.h46), ("H47", h_phase9.h47)):
        t = time.time()
        got = fn()
        records += got
        print(f"  built {label}  {len(got)} record(s) in {time.time() - t:6.1f}s", flush=True)
    oos_sr = [stats.sharpe(slice_from(r["dates"], r["net"], r["oos_start"])[1], periods=P) for r in records]
    disp = max(p1_disp, stats.stdev(oos_sr))
    print(f"deflated-Sharpe trial count N = {N_TRIALS}; SR dispersion: Phase-9 {stats.stdev(oos_sr):.3f}, "
          f"Phase-1 {p1_disp:.3f} -> using {disp:.3f}")

    results = []
    for r in records:
        results.append(evaluate_record(r, bench, disp))
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
