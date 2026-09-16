"""
Runs the nearest-neighbor setup test (PREREG_NN.md). Prints a report and writes
research/results/nn.json + research/NN_RESULTS.md.

  python3 research/run_nn.py            full run (real + shuffled control + integrity)
  python3 research/run_nn.py --quick    smaller test period, for a fast sanity pass while developing
"""
import hashlib
import json
import math
import os
import random
import sys
import time

import numpy as np

import intraday
import leakage
import nn_engine as E

ROOT = os.path.dirname(os.path.abspath(__file__))
PREREG = os.path.join(ROOT, "PREREG_NN.md")

POOL_START = "2024-09-11"
TEST_START = "2025-09-11"
TEST_END = "2026-09-10"
N_SHUFFLE = 200
SHUFFLE_SEED = 20260915


def ymd_to_epoch(s):
    import datetime
    return int(datetime.datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc).timestamp())


def prereg_sha256():
    with open(PREREG, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load_data(quiet=False):
    """Raw 1-minute bars - callers resample to 5m themselves (kept separate so it's obvious there's
    exactly one resampling step, not an accidental double one)."""
    start, end = ymd_to_epoch(POOL_START), ymd_to_epoch(TEST_END) + 86400
    return intraday.coinbase_1m("BTC-USD", start, end, quiet=quiet)


def build(bars5m):
    ind = E.compute_indicators(bars5m)
    feats = E.raw_features(ind)
    z = E.zscore_features(feats)
    _, vote = E.outcomes(ind["close"], ind["atr14"])
    return ind, z, np.array(vote), ind["close"], ind["open"]


def index_of(bars, epoch):
    times = [b[0] for b in bars]
    for i, t in enumerate(times):
        if t >= epoch:
            return i
    return len(times)


def summarize(trades, key="ret_fee"):
    n = len(trades)
    if n == 0:
        return {"n": 0, "mean": None, "win_rate": None}
    rets = [t[key] for t in trades]
    mean = sum(rets) / n
    wins = sum(1 for r in rets if r > 0)
    return {"n": n, "mean": mean, "win_rate": wins / n}


def binom_p_one_sided(k, n, p=0.5):
    """P(X >= k) under Binomial(n, p) - a one-sided test that the win rate beats a coin flip.
    Raw math.comb(n, x) overflows a float for n in the thousands, so this uses scipy's survival
    function (numerically stable via the incomplete beta function, not raw coefficients)."""
    if n == 0:
        return 1.0
    from scipy.stats import binom
    return float(binom.sf(k - 1, n, p))


def gates(real_summary, shuffled_means):
    g1 = bool(real_summary["n"] >= 100)
    g2 = bool(g1 and real_summary["mean"] is not None and real_summary["mean"] > 0)
    thresh = float(np.percentile(shuffled_means, 95)) if len(shuffled_means) else None
    g3 = bool(g1 and thresh is not None and real_summary["mean"] is not None and real_summary["mean"] > thresh)
    p = binom_p_one_sided(round(real_summary["win_rate"] * real_summary["n"]), real_summary["n"]) if g1 else 1.0
    g4 = bool(g1 and real_summary["win_rate"] is not None and real_summary["win_rate"] > 0.5 and p < 0.05)
    return {"G1_min_trades": g1, "G2_mean_positive": g2, "G3_beats_shuffle_p95": g3,
            "G4_win_rate": g4, "shuffle_p95": thresh, "win_rate_p": float(p),
            "PASS": bool(g1 and g2 and g3 and g4)}


def decide_only(z, vote, test_start, test_end, cut):
    """Stripped-down version of run_real's signal (no trade-state) for the truncation test:
    what side (1/-1/0/None-as-0) would it vote at each i, using only data with index <= cut?"""
    n_cut = (cut + 1) if cut is not None else len(z)
    valid = E.valid_rows(z[:n_cut])
    out = [0] * len(z)
    tree = None
    tree_upto = -1
    tree_pool_idx = None
    for i in range(test_start, min(test_end, n_cut)):
        if i >= len(z) or np.isnan(z[i]).any():
            continue
        cap = i - E.H
        if cap < 0:
            continue
        cap = min(cap, n_cut - 1)
        if tree is None or i - tree_upto >= E.REBUILD_EVERY:
            pool_idx = valid[valid <= cap]
            if len(pool_idx) < E.K:
                continue
            from scipy.spatial import cKDTree
            tree = cKDTree(z[pool_idx])
            tree_pool_idx = pool_idx
            tree_upto = cap
        dist, idx = tree.query(z[i], k=E.K)
        idx = np.atleast_1d(idx)
        neigh = tree_pool_idx[idx]
        votes = vote[neigh]
        longs, shorts = int((votes == 1).sum()), int((votes == -1).sum())
        out[i] = 1 if longs >= E.CONSENSUS else (-1 if shorts >= E.CONSENSUS else 0)
    return out


def run_integrity(z, vote, test_start, test_end):
    n = len(z)
    # keep the truncation test itself tractable: check a bounded window inside the test period
    window_end = min(test_end, test_start + 3000)

    def weights_fn(cut):
        real_cut = None if cut is None else min(cut, n - 1)
        return decide_only(z, vote, test_start, window_end, real_cut)

    return leakage.truncation_test(weights_fn, window_end, lag=0, n_cuts=6, seed=5)


def synthetic_series(seed, bars_len, sigma):
    rng = random.Random(seed)
    price = 60000.0
    bars = []
    t0 = 1700000000
    for i in range(bars_len):
        ret = rng.gauss(0, sigma)
        o = price
        c = price * (1 + ret)
        h = max(o, c) * (1 + abs(rng.gauss(0, sigma / 3)))
        l = min(o, c) * (1 - abs(rng.gauss(0, sigma / 3)))
        v = max(1.0, rng.gauss(100, 30))
        bars.append([t0 + i * 300, o, h, l, c, v])
        price = c
    return bars


def run_synthetic_check(real_bars):
    close = [b[4] for b in real_bars]
    log_rets = [math.log(close[i] / close[i - 1]) for i in range(1, len(close)) if close[i - 1] > 0]
    sigma = (sum(x * x for x in log_rets) / len(log_rets)) ** 0.5 if log_rets else 0.001

    results = []
    per_len = 2 * 30 * 288  # 2 months of 5-min bars
    for k in range(10):
        bars = synthetic_series(90000 + k, per_len * 2, sigma)
        ind, z, vote, close_s, open_s = build(bars)
        pool_end = per_len
        t_start, t_end = per_len, per_len * 2 - E.H - 2
        trades, decisions = E.run_real(z, vote, open_s, close_s, pool_end, t_start, t_end, seed=k)
        probs = E.pool_vote_probs(vote, pool_end)
        shuf_means = []
        for s in range(50):
            st = E.run_shuffled(decisions, vote, open_s, probs, seed=1000 * k + s)
            summ = summarize(st)
            if summ["n"] > 0:
                shuf_means.append(summ["mean"])
        summ = summarize(trades)
        g = gates(summ, shuf_means)
        results.append({"seed": k, "trades": summ["n"], "mean": summ["mean"], "pass": g["PASS"]})
    passes = sum(1 for r in results if r["pass"])
    return {"runs": results, "passes": passes, "ok": passes <= 1}


def main():
    quick = "--quick" in sys.argv
    t0 = time.time()
    print("Loading BTC-USD 1-minute candles (cached where available)...", flush=True)
    bars1m = load_data(quiet=True)
    print(f"  {len(bars1m)} 1-minute bars -> resampling to 5m", flush=True)
    bars5 = E.resample_5m(bars1m)
    print(f"  {len(bars5)} 5-minute bars", flush=True)

    ind, z, vote, close, open_ = build(bars5)

    pool_end = index_of(bars5, ymd_to_epoch(TEST_START))
    test_start = pool_end
    test_end = index_of(bars5, ymd_to_epoch(TEST_END))
    if quick:
        test_end = min(test_end, test_start + 5000)
    print(f"  pool: 0..{pool_end}  test: {test_start}..{test_end}", flush=True)

    print("Integrity: truncation (look-ahead) test...", flush=True)
    trunc = run_integrity(z, vote, test_start, test_end)
    print(f"  {'OK' if trunc['ok'] else 'FAILED: ' + str(trunc)}", flush=True)

    print("Integrity: synthetic random-walk sanity check (10 runs)...", flush=True)
    synth = run_synthetic_check(bars5[:test_start]) if not quick else {"runs": [], "passes": 0, "ok": True, "skipped": "quick mode"}
    print(f"  passes: {synth['passes']} of 10 (need <= 1)  {'OK' if synth['ok'] else 'FAILED'}", flush=True)

    integrity_ok = trunc["ok"] and synth["ok"]

    print("Real run...", flush=True)
    trades, decisions = E.run_real(z, vote, open_, close, pool_end, test_start, test_end, seed=SHUFFLE_SEED)
    real_summary = summarize(trades)
    print(f"  {real_summary['n']} trades, mean {real_summary['mean']}", flush=True)

    print(f"Shuffled-label control ({N_SHUFFLE} runs)...", flush=True)
    probs = E.pool_vote_probs(vote, pool_end)
    shuffled_means = []
    for s in range(N_SHUFFLE):
        st = E.run_shuffled(decisions, vote, open_, probs, seed=SHUFFLE_SEED * 1000 + s)
        summ = summarize(st)
        if summ["n"] > 0:
            shuffled_means.append(summ["mean"])

    g = gates(real_summary, shuffled_means)

    out = {
        "prereg_sha256": prereg_sha256(),
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_sec": round(time.time() - t0, 1),
        "bars_1m": len(bars1m), "bars_5m": len(bars5),
        "pool_end": pool_end, "test_start": test_start, "test_end": test_end,
        "integrity": {"truncation": trunc, "synthetic": synth, "ok": integrity_ok},
        "real": real_summary,
        "shuffled": {"n_runs": len(shuffled_means),
                      "mean_of_means": (sum(shuffled_means) / len(shuffled_means)) if shuffled_means else None,
                      "p95": g["shuffle_p95"]},
        "gates": g,
    }
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    with open(os.path.join(ROOT, "results", "nn.json"), "w") as f:
        json.dump(out, f, indent=1)

    print(json.dumps({k: v for k, v in out.items() if k not in ("integrity",)}, indent=1, default=str))
    print("\nINTEGRITY:", "OK" if integrity_ok else "FAILED - no verdict")
    print("VERDICT:", ("PASS" if g["PASS"] else "FAIL") if integrity_ok else "NO VERDICT (integrity failed)")


if __name__ == "__main__":
    main()
