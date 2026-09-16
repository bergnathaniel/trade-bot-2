"""
Runs the genetic-algorithm strategy search (PREREG_GA.md).

  python3 research/run_ga.py            full run: 40 generations x 60, plus random-search control
  python3 research/run_ga.py --quick    5 generations x 12, for a fast sanity pass while developing
"""
import copy
import hashlib
import json
import math
import os
import random
import sys
import time

import numpy as np
from scipy.stats import binom

import ga_engine as G
import intraday
import leakage
import nn_engine as E
import run_nn as NN   # reuses ymd_to_epoch, index_of, synthetic_series pieces

ROOT = os.path.dirname(os.path.abspath(__file__))
PREREG = os.path.join(ROOT, "PREREG_GA.md")

POOL_START = "2024-09-11"
VALID_START = "2026-01-30"
HOLDOUT_START = "2026-06-11"
HOLDOUT_END = "2026-09-10"

POP, GENS = 60, 40
ELITE, VALID_POOL = 8, 15
BUDGET = POP * GENS
FEE = G.FEE
N_SHUFFLE = 200
SEED = 20260915


def prereg_sha256():
    with open(PREREG, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_window():
    start = NN.ymd_to_epoch(POOL_START)
    end = NN.ymd_to_epoch(HOLDOUT_END) + 86400
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
        e = NN.ymd_to_epoch(ymd)
        for i, t in enumerate(times):
            if t >= e:
                return i
        return len(times)

    return W, bars5, idx_of


def summarize(trades):
    n = len(trades)
    if n == 0:
        return {"n": 0, "mean": None, "win_rate": None}
    rets = [t["ret_fee"] for t in trades]
    return {"n": n, "mean": sum(rets) / n, "win_rate": sum(1 for r in rets if r > 0) / n}


def binom_p_one_sided(k, n, p=0.5):
    if n == 0:
        return 1.0
    return float(binom.sf(k - 1, n, p))


def run_generation_loop(W, train_lo, train_hi, valid_lo, valid_hi, seed, evolve=True, gens=GENS, pop=POP):
    """evolve=True: the real GA (selection + mutation). evolve=False: the random-search control
    (same budget, no selection/mutation - generation 0's process repeated `gens` times)."""
    rng = random.Random(seed)
    population = [G.random_genome(rng) for _ in range(pop)]
    log = []
    best_overall = None   # (valid_fitness, genome, train_fitness, train_trades, valid_trades)

    for gen in range(gens):
        scored = []
        for genome in population:
            tf, ttrades = G.fitness(genome, W, train_lo, train_hi)
            scored.append((tf, genome, ttrades))
        scored.sort(key=lambda x: x[0], reverse=True)

        top = scored[:VALID_POOL]
        valid_scored = []
        for tf, genome, ttrades in top:
            vf, vtrades = G.fitness(genome, W, valid_lo, valid_hi)
            valid_scored.append((vf, tf, genome, ttrades, vtrades))
        valid_scored.sort(key=lambda x: x[0], reverse=True)

        for vf, tf, genome, ttrades, vtrades in valid_scored:
            log.append({"gen": gen, "entry_type": genome["entry_type"], "train_fitness": tf,
                        "train_trades": len(ttrades), "valid_fitness": vf, "valid_trades": len(vtrades)})
            if best_overall is None or vf > best_overall[0]:
                best_overall = (vf, copy.deepcopy(genome), tf, len(ttrades), len(vtrades))

        if not evolve:
            population = [G.random_genome(rng) for _ in range(pop)]
            continue

        survivors = [g for _, _, g, _, _ in valid_scored[:ELITE]]
        if not survivors:
            survivors = [scored[0][1]]
        next_pop = list(survivors)
        while len(next_pop) < pop:
            a, b = rng.choice(survivors), rng.choice(survivors)
            next_pop.append(G.mutate(a, b, rng))
        population = next_pop

    return best_overall, log


def shuffled_control(genome, W, lo, hi, seed):
    """Random-entry-timing control, matching PREREG_SEARCH.md's MOM/REV precedent (NOT a
    permutation of this genome's own returns among themselves - permuting a fixed list can never
    change its mean, which made an earlier version of this control mathematically unable to fail,
    found and fixed 2026-09-16 before trusting any holdout result). Same trade COUNT and side mix
    as the real run, entered at uniformly random times instead of this genome's actual signals,
    then run through the identical stop/target/max-hold exit rule - tests whether this genome's
    specific entry timing adds anything over picking the same number of random moments."""
    real_trades = G.backtest(genome, W, lo, hi)
    if not real_trades:
        return []
    rng = random.Random(seed)
    sides = [t["side"] for t in real_trades]
    stop_atr, target_atr, max_hold = genome["stop_atr"], genome["target_atr"], int(genome["max_hold"])
    out = []
    for side in sides:
        tries = 0
        while tries < 20:
            tries += 1
            i = rng.randrange(lo, max(lo + 1, hi - max_hold - 2))
            a = W.atr14[i]
            if a > 0:
                break
        else:
            continue
        entry_bar = i + 1
        entry_px = W.open[entry_bar]
        stop_px = entry_px - side * stop_atr * a
        target_px = None if target_atr <= 0 else entry_px + side * target_atr * a
        end = min(entry_bar + max_hold, hi - 1)
        exit_px = W.open[min(end + 1, hi - 1)]
        for j in range(entry_bar, end):
            c = W.close[j]
            hit_stop = (c <= stop_px) if side == 1 else (c >= stop_px)
            hit_target = target_px is not None and ((c >= target_px) if side == 1 else (c <= target_px))
            if hit_stop or hit_target:
                exit_px = W.open[min(j + 1, hi - 1)]
                break
        ret = (exit_px / entry_px - 1) * side
        ret_fee = (1 + ret) * (1 - FEE) ** 2 - 1
        out.append({"ret_fee": ret_fee})
    return out


def final_test(genome, W, holdout_lo, holdout_hi, budget):
    real_trades = G.backtest(genome, W, holdout_lo, holdout_hi)
    real = summarize(real_trades)

    shuf_means = []
    for s in range(N_SHUFFLE):
        st = shuffled_control(genome, W, holdout_lo, holdout_hi, seed=SEED * 1000 + s)
        summ = summarize(st)
        if summ["n"] > 0:
            shuf_means.append(summ["mean"])
    p95 = float(np.percentile(shuf_means, 95)) if shuf_means else None

    g1 = bool(real["n"] >= 20)
    g2 = bool(g1 and real["mean"] is not None and real["mean"] > 0)
    g3 = bool(g1 and p95 is not None and real["mean"] is not None and real["mean"] > p95)
    p = binom_p_one_sided(round(real["win_rate"] * real["n"]), real["n"]) if g1 else 1.0
    bonferroni_alpha = 0.05 / budget
    g4 = bool(g1 and real["win_rate"] is not None and real["win_rate"] > 0.5 and p < bonferroni_alpha)
    return {"real": real, "shuffled_p95": p95, "win_rate_p": p, "bonferroni_alpha": bonferroni_alpha,
            "gates": {"G1_min_trades": g1, "G2_mean_positive": g2, "G3_beats_shuffle_p95": g3,
                      "G4_bonferroni_win_rate": g4, "PASS": bool(g1 and g2 and g3 and g4)}}


def run_integrity(W, train_lo, train_hi):
    rng = random.Random(42)
    genome = G.random_genome(rng)
    genome["entry_type"] = "breakout"   # the one with a custom vectorized indicator

    window_hi = min(train_hi, train_lo + 4000)

    def decide_fn(cut):
        n = W.n if cut is None else min(cut + 1, W.n)
        if n <= 10:
            return [0] * W.n
        Wc = G.Window(W.open[:n], W.high[:n], W.low[:n], W.close[:n], W.vol[:n])
        long_, short = G._entry_signal(genome, Wc)
        out = [0] * W.n
        for i in range(min(n, window_hi)):
            out[i] = 1 if long_[i] else (-1 if short[i] else 0)
        return out

    return leakage.truncation_test(decide_fn, window_hi, lag=0, n_cuts=6, seed=11)


def run_synthetic_check():
    per_len = 2 * 30 * 288
    passes = 0
    results = []
    for k in range(10):
        bars = NN.synthetic_series(70000 + k, per_len * 2, 0.0012)
        open_ = [b[1] for b in bars]; high = [b[2] for b in bars]; low = [b[3] for b in bars]
        close = [b[4] for b in bars]; vol = [b[5] for b in bars]
        Ws = G.Window(open_, high, low, close, vol)
        train_hi = int(per_len * 0.7)
        best, _ = run_generation_loop(Ws, 0, train_hi, train_hi, per_len, seed=5000 + k, evolve=True, gens=8, pop=20)
        genome = best[1]
        res = final_test(genome, Ws, per_len, per_len * 2 - 2, 160)
        ok = res["gates"]["PASS"]
        passes += int(ok)
        results.append({"seed": k, "pass": ok})
    return {"runs": results, "passes": passes, "ok": passes <= 1}


def main():
    quick = "--quick" in sys.argv
    gens, pop = (5, 12) if quick else (GENS, POP)
    budget = gens * pop
    t0 = time.time()

    print("Loading BTC-USD candles...", flush=True)
    W, bars5, idx_of = load_window()
    train_lo, valid_lo, holdout_lo = 0, idx_of(VALID_START), idx_of(HOLDOUT_START)
    train_hi = valid_lo
    valid_hi = holdout_lo
    holdout_hi = min(idx_of(HOLDOUT_END), W.n - 2)
    print(f"  {W.n} 5-min bars. train [0,{train_hi}) valid [{valid_lo},{valid_hi}) holdout [{holdout_lo},{holdout_hi})", flush=True)

    print("Integrity: truncation (look-ahead) test...", flush=True)
    trunc = run_integrity(W, train_lo, train_hi)
    print(f"  {'OK' if trunc['ok'] else 'FAILED: ' + str(trunc)}", flush=True)

    if quick:
        synth = {"runs": [], "passes": 0, "ok": True, "skipped": "quick mode"}
    else:
        print("Integrity: synthetic random-walk sanity check (10 runs, each an 8-gen/20-pop search)...", flush=True)
        synth = run_synthetic_check()
        print(f"  passes: {synth['passes']} of 10 (need <= 1)  {'OK' if synth['ok'] else 'FAILED'}", flush=True)

    integrity_ok = trunc["ok"] and synth["ok"]

    print(f"Evolved search: {gens} generations x {pop} population ({budget} evaluations)...", flush=True)
    evolved_best, evolved_log = run_generation_loop(W, train_lo, train_hi, valid_lo, valid_hi, seed=SEED, evolve=True, gens=gens, pop=pop)
    print(f"  best: {evolved_best[1]['entry_type']}, valid_fitness={evolved_best[0]:.5f}, train_trades={evolved_best[3]}, valid_trades={evolved_best[4]}", flush=True)

    print(f"Random-search control: {gens} generations x {pop} population ({budget} evaluations)...", flush=True)
    random_best, random_log = run_generation_loop(W, train_lo, train_hi, valid_lo, valid_hi, seed=SEED + 1, evolve=False, gens=gens, pop=pop)
    print(f"  best: {random_best[1]['entry_type']}, valid_fitness={random_best[0]:.5f}, train_trades={random_best[3]}, valid_trades={random_best[4]}", flush=True)

    print("Final holdout test (touched once, for these 2 finalists only)...", flush=True)
    evolved_final = final_test(evolved_best[1], W, holdout_lo, holdout_hi, budget)
    random_final = final_test(random_best[1], W, holdout_lo, holdout_hi, budget)
    print(f"  evolved: n={evolved_final['real']['n']} mean={evolved_final['real']['mean']} PASS={evolved_final['gates']['PASS']}", flush=True)
    print(f"  random : n={random_final['real']['n']} mean={random_final['real']['mean']} PASS={random_final['gates']['PASS']}", flush=True)

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
    with open(os.path.join(ROOT, "results", "ga.json"), "w") as f:
        json.dump(out, f, indent=1, default=str)
    with open(os.path.join(ROOT, "results", "ga_log.json"), "w") as f:
        json.dump({"evolved_log": evolved_log, "random_log": random_log}, f, default=str)

    print("\nINTEGRITY:", "OK" if integrity_ok else "FAILED - no verdict")
    print("VERDICT evolved:", ("PASS" if evolved_final["gates"]["PASS"] else "FAIL") if integrity_ok else "NO VERDICT")
    print("VERDICT random :", ("PASS" if random_final["gates"]["PASS"] else "FAIL") if integrity_ok else "NO VERDICT")


if __name__ == "__main__":
    main()
