"""
Runs the round-2 genetic-algorithm search (PREREG_GA2.md) - same engine as round 1 (ga_engine.py,
unchanged), bigger budget (10,000 vs 2,400 evaluations), on a completely disjoint 2022-2024 block
of history that round 1 never touched.

  python3 research/run_ga2.py            full run: 100 generations x 100 population
  python3 research/run_ga2.py --quick    5 generations x 12, for a fast sanity pass
"""
import hashlib
import json
import os
import sys
import time

import numpy as np

import ga_engine as G
import intraday
import leakage
import nn_engine as E
import run_ga as GA1   # reuses run_generation_loop, shuffled_control, final_test, summarize, etc.

ROOT = os.path.dirname(os.path.abspath(__file__))
PREREG = os.path.join(ROOT, "PREREG_GA2.md")

POOL_START = "2022-09-11"
VALID_START = "2024-01-30"
HOLDOUT_START = "2024-06-11"
HOLDOUT_END = "2024-09-10"

POP, GENS = 100, 100
BUDGET = POP * GENS
SEED = 20260916


def prereg_sha256():
    with open(PREREG, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def ymd_to_epoch(s):
    import datetime
    return int(datetime.datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc).timestamp())


def load_window():
    start = ymd_to_epoch(POOL_START)
    end = ymd_to_epoch(HOLDOUT_END) + 86400
    bars1m = intraday.coinbase_1m("BTC-USD", start, end, quiet=True)
    bars5 = E.resample_5m(bars1m)
    open_ = [b[1] for b in bars5]
    high = [b[2] for b in bars5]
    low = [b[3] for b in bars5]
    close = [b[4] for b in bars5]
    vol = [b[5] for b in bars5]
    W = G.Window(open_, high, low, close, vol)
    times = [b[0] for b in bars5]

    def idx_of(ymd):
        e = ymd_to_epoch(ymd)
        for i, t in enumerate(times):
            if t >= e:
                return i
        return len(times)

    return W, len(bars1m), len(bars5), idx_of


def main():
    quick = "--quick" in sys.argv
    gens, pop = (5, 12) if quick else (GENS, POP)
    budget = gens * pop
    t0 = time.time()

    print("Loading BTC-USD candles (2022-09-11 -> 2024-09-10, disjoint from round 1)...", flush=True)
    W, n1m, n5m, idx_of = load_window()
    train_lo, valid_lo, holdout_lo = 0, idx_of(VALID_START), idx_of(HOLDOUT_START)
    train_hi = valid_lo
    valid_hi = holdout_lo
    holdout_hi = min(idx_of(HOLDOUT_END), W.n - 2)
    print(f"  {n1m} 1-min bars -> {n5m} 5-min bars. train [0,{train_hi}) valid [{valid_lo},{valid_hi}) holdout [{holdout_lo},{holdout_hi})", flush=True)

    print("Integrity: truncation (look-ahead) test...", flush=True)
    trunc = GA1.run_integrity(W, train_lo, train_hi)
    print(f"  {'OK' if trunc['ok'] else 'FAILED: ' + str(trunc)}", flush=True)

    if quick:
        synth = {"runs": [], "passes": 0, "ok": True, "skipped": "quick mode"}
    else:
        print("Integrity: synthetic random-walk sanity check (10 runs)...", flush=True)
        synth = GA1.run_synthetic_check()
        print(f"  passes: {synth['passes']} of 10 (need <= 1)  {'OK' if synth['ok'] else 'FAILED'}", flush=True)

    integrity_ok = trunc["ok"] and synth["ok"]

    print(f"Evolved search: {gens} generations x {pop} population ({budget} evaluations)...", flush=True)
    evolved_best, evolved_log = GA1.run_generation_loop(W, train_lo, train_hi, valid_lo, valid_hi, seed=SEED, evolve=True, gens=gens, pop=pop)
    print(f"  best: {evolved_best[1]['entry_type']}, valid_fitness={evolved_best[0]:.5f}, train_trades={evolved_best[3]}, valid_trades={evolved_best[4]}", flush=True)

    print(f"Random-search control: {gens} generations x {pop} population ({budget} evaluations)...", flush=True)
    random_best, random_log = GA1.run_generation_loop(W, train_lo, train_hi, valid_lo, valid_hi, seed=SEED + 1, evolve=False, gens=gens, pop=pop)
    print(f"  best: {random_best[1]['entry_type']}, valid_fitness={random_best[0]:.5f}, train_trades={random_best[3]}, valid_trades={random_best[4]}", flush=True)

    print("Final holdout test (touched once, for these 2 finalists only)...", flush=True)
    evolved_final = GA1.final_test(evolved_best[1], W, holdout_lo, holdout_hi, budget)
    random_final = GA1.final_test(random_best[1], W, holdout_lo, holdout_hi, budget)
    print(f"  evolved: n={evolved_final['real']['n']} mean={evolved_final['real']['mean']} PASS={evolved_final['gates']['PASS']}", flush=True)
    print(f"  random : n={random_final['real']['n']} mean={random_final['real']['mean']} PASS={random_final['gates']['PASS']}", flush=True)

    # sanity: the shuffled control must not be identical to the real mean (the round-1 bug this
    # would catch if it ever regressed)
    for label, f in (("evolved", evolved_final), ("random", random_final)):
        if f["real"]["mean"] is not None and f["shuffled_p95"] is not None and f["real"]["mean"] == f["shuffled_p95"]:
            print(f"  WARNING: {label}'s shuffled_p95 exactly equals its real mean - control may be degenerate again", flush=True)

    out = {
        "prereg_sha256": prereg_sha256(),
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_sec": round(time.time() - t0, 1),
        "budget": budget, "generations": gens, "population": pop,
        "bounds": {"train": [train_lo, train_hi], "valid": [valid_lo, valid_hi], "holdout": [holdout_lo, holdout_hi]},
        "integrity": {"truncation": trunc, "synthetic": synth, "ok": integrity_ok},
        "evolved": {"genome": evolved_best[1], "valid_fitness": evolved_best[0],
                    "train_trades": evolved_best[3], "valid_trades": evolved_best[4], "holdout": evolved_final},
        "random_search": {"genome": random_best[1], "valid_fitness": random_best[0],
                           "train_trades": random_best[3], "valid_trades": random_best[4], "holdout": random_final},
    }
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    with open(os.path.join(ROOT, "results", "ga2.json"), "w") as f:
        json.dump(out, f, indent=1, default=str)
    with open(os.path.join(ROOT, "results", "ga2_log.json"), "w") as f:
        json.dump({"evolved_log": evolved_log, "random_log": random_log}, f, default=str)

    print("\nINTEGRITY:", "OK" if integrity_ok else "FAILED - no verdict")
    print("VERDICT evolved:", ("PASS" if evolved_final["gates"]["PASS"] else "FAIL") if integrity_ok else "NO VERDICT")
    print("VERDICT random :", ("PASS" if random_final["gates"]["PASS"] else "FAIL") if integrity_ok else "NO VERDICT")


if __name__ == "__main__":
    main()
