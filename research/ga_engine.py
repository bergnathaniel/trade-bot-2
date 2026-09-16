"""
Genetic-algorithm strategy search (PREREG_GA.md).
==================================================

A genome is a dict describing one candidate strategy (entry family + params, side, filters,
stop/target in ATR, max hold). `evaluate(genome, W, lo, hi)` backtests it over bars [lo, hi) of a
precomputed indicator bundle W and returns fitness + trade stats. Vectorized with numpy: the entry
signal for the whole window is computed in one pass, then a lean loop walks only the candidate
entry indices (not every bar) to manage the one-position-at-a-time state machine.
"""

import random

import numpy as np
from scipy.ndimage import maximum_filter1d, minimum_filter1d

FEE = 0.0025
MIN_TRADES_FITNESS = 30   # fewer trades than this -> fitness 0, regardless of return

ENTRY_TYPES = ["rsi_meanrev", "ma_cross", "breakout", "bb_meanrev", "momentum"]
SIDES = ["long_only", "short_only", "both"]


def random_genome(rng):
    et = rng.choice(ENTRY_TYPES)
    if et == "rsi_meanrev":
        p1, p2 = rng.uniform(10, 40), rng.uniform(60, 90)
    elif et == "ma_cross":
        p1 = rng.uniform(2, 40)
        p2 = p1 + rng.uniform(5, 150)
    elif et == "breakout":
        p1, p2 = rng.uniform(5, 100), 0.0
    elif et == "bb_meanrev":
        p1, p2 = rng.uniform(10, 50), rng.uniform(1.0, 3.0)
    else:  # momentum
        p1, p2 = rng.uniform(3, 100), rng.uniform(0.002, 0.03)
    return {
        "entry_type": et, "param1": p1, "param2": p2,
        "side": rng.choice(SIDES),
        "trend_filter": rng.random() < 0.5,
        "volume_filter": rng.random() < 0.5,
        "stop_atr": rng.uniform(0.5, 6.0),
        "target_atr": 0.0 if rng.random() < 0.2 else rng.uniform(0.5, 10.0),
        "max_hold": rng.randint(6, 288),
    }


def mutate(parent_a, parent_b, rng):
    child = {}
    for k in ("entry_type", "side"):
        child[k] = rng.choice([parent_a[k], parent_b[k]])
    for k in ("trend_filter", "volume_filter"):
        child[k] = rng.choice([parent_a[k], parent_b[k]])
    for k in ("param1", "param2", "stop_atr", "target_atr", "max_hold"):
        avg = (parent_a[k] + parent_b[k]) / 2
        child[k] = avg
    if rng.random() < 0.1:
        # reset one random gene entirely, from a fresh random genome of the child's own family
        fresh = random_genome(rng)
        gene = rng.choice(list(fresh.keys()))
        child[gene] = fresh[gene]
    for k in ("param1", "param2", "stop_atr", "target_atr"):
        child[k] = max(0.0, child[k] * (1 + rng.gauss(0, 0.05)))
    child["max_hold"] = max(6, min(288, int(round(child["max_hold"] * (1 + rng.gauss(0, 0.05))))))
    if child["entry_type"] == "ma_cross" and child["param2"] <= child["param1"]:
        child["param2"] = child["param1"] + 5
    return child


class Window:
    """Precomputed arrays shared by every genome evaluation, so indicators aren't recomputed per
    genome except the ones whose period is itself a gene (MA cross, breakout, BB, momentum)."""

    def __init__(self, open_, high, low, close, vol):
        self.open = np.asarray(open_, dtype=float)
        self.high = np.asarray(high, dtype=float)
        self.low = np.asarray(low, dtype=float)
        self.close = np.asarray(close, dtype=float)
        self.vol = np.asarray(vol, dtype=float)
        self.n = len(self.close)
        self.rsi14 = _rsi_np(self.close, 14)
        self.atr14 = _atr_np(self.high, self.low, self.close, 14)
        self.ma200 = _sma_np(self.close, 200)
        self.volavg20 = _sma_np(self.vol, 20)


def _sma_np(v, n):
    out = np.full(len(v), np.nan)
    c = np.cumsum(np.insert(v, 0, 0.0))
    out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def _rsi_np(close, n=14):
    d = np.diff(close, prepend=close[0])
    gain = np.where(d > 0, d, 0.0)
    loss = np.where(d < 0, -d, 0.0)
    out = np.full(len(close), np.nan)
    if len(close) <= n:
        return out
    g = gain[1:n + 1].mean()
    l = loss[1:n + 1].mean()
    out[n] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    for i in range(n + 1, len(close)):
        g = (g * (n - 1) + gain[i]) / n
        l = (l * (n - 1) + loss[i]) / n
        out[i] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    return out


def _atr_np(high, low, close, n=14):
    prev_close = np.roll(close, 1)
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev_close), np.abs(low - prev_close)))
    tr[0] = high[0] - low[0]
    out = np.full(len(close), np.nan)
    if len(close) <= n:
        return out
    out[n] = tr[1:n + 1].mean()
    for i in range(n + 1, len(close)):
        out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


def _causal_rolling(v, k, scipy_filter):
    """out[i] = scipy_filter's window-k statistic over v[i-k:i] (the k bars strictly BEFORE i),
    never v[i] itself or anything later. scipy's centered filter needs a parity-dependent shift to
    become causal; the offset (k+1)//2 was verified against a brute-force loop for k=2..8 (both
    parities) before use - see the truncation test in run_ga.py for the same guarantee at runtime."""
    n = len(v)
    out = np.full(n, np.nan)
    if n <= k:
        return out
    M = scipy_filter(v, size=k)
    off = (k + 1) // 2
    idx = np.arange(k, n)
    src = idx - off
    valid = src >= 0
    out[idx[valid]] = M[src[valid]]
    return out


def _entry_signal(genome, W):
    """Boolean long/short entry arrays for the WHOLE window (vectorized), before filters."""
    n = W.n
    long_ = np.zeros(n, dtype=bool)
    short = np.zeros(n, dtype=bool)
    et, p1, p2 = genome["entry_type"], genome["param1"], genome["param2"]

    if et == "rsi_meanrev":
        long_ = W.rsi14 < p1
        short = W.rsi14 > p2
    elif et == "ma_cross":
        fast = _sma_np(W.close, max(2, int(round(p1))))
        slow = _sma_np(W.close, max(3, int(round(p2))))
        up = fast > slow
        prev_up = np.roll(up, 1)
        prev_up[0] = up[0]
        cross_up = up & ~prev_up
        cross_down = ~up & prev_up
        valid = ~np.isnan(fast) & ~np.isnan(slow)
        long_ = cross_up & valid
        short = cross_down & valid
    elif et == "breakout":
        k = max(2, int(round(p1)))
        hi_roll = np.full(n, np.nan)
        lo_roll = np.full(n, np.nan)
        if n > k:
            hi_roll[k:] = _causal_rolling(W.high, k, maximum_filter1d)[k:]
            lo_roll[k:] = _causal_rolling(W.low, k, minimum_filter1d)[k:]
        long_ = W.close > hi_roll
        short = W.close < lo_roll
    elif et == "bb_meanrev":
        period = max(5, int(round(p1)))
        mid = _sma_np(W.close, period)
        sq = _sma_np(W.close ** 2, period)
        var = np.maximum(sq - mid ** 2, 0.0)
        std = np.sqrt(var)
        z = p2
        long_ = W.close <= (mid - z * std)
        short = W.close >= (mid + z * std)
    else:  # momentum
        k = max(1, int(round(p1)))
        ret = np.full(n, np.nan)
        ret[k:] = W.close[k:] / W.close[:-k] - 1
        long_ = ret > p2
        short = ret < -p2

    if genome["trend_filter"]:
        up_trend = W.close > W.ma200
        long_ = long_ & up_trend
        short = short & ~up_trend
    if genome["volume_filter"]:
        vol_ok = W.vol > W.volavg20
        long_ = long_ & vol_ok
        short = short & vol_ok

    if genome["side"] == "long_only":
        short = np.zeros(n, dtype=bool)
    elif genome["side"] == "short_only":
        long_ = np.zeros(n, dtype=bool)

    long_ = np.nan_to_num(long_, nan=False).astype(bool)
    short = np.nan_to_num(short, nan=False).astype(bool)
    return long_, short


def backtest(genome, W, lo, hi):
    """Trades entirely within [lo, hi) of W's bars. Entries/exits never reference data outside
    this range (lo acts as the earliest possible entry; the scan for an exit is capped at hi-1, so
    a trade opened near hi that hasn't resolved by hi-1 is closed at hi-1's open - never peeking
    past hi)."""
    long_sig, short_sig = _entry_signal(genome, W)
    n = W.n
    hi = min(hi, n - 1)
    idx = np.nonzero((long_sig[lo:hi] | short_sig[lo:hi]))[0] + lo
    trades = []
    pos_until = lo - 1   # no new entry may start at or before this index (still in a position)
    stop_atr, target_atr, max_hold = genome["stop_atr"], genome["target_atr"], int(genome["max_hold"])

    for i in idx:
        if i <= pos_until or i + 1 >= hi:
            continue
        side = 1 if long_sig[i] else -1
        a = W.atr14[i]
        if not (a > 0):
            continue
        entry_bar = i + 1
        entry_px = W.open[entry_bar]
        stop_px = entry_px - side * stop_atr * a
        target_px = None if target_atr <= 0 else entry_px + side * target_atr * a
        end = min(entry_bar + max_hold, hi - 1)
        exit_bar, exit_px = end, W.open[min(end + 1, hi - 1)]
        for j in range(entry_bar, end):
            c = W.close[j]
            hit_stop = (c <= stop_px) if side == 1 else (c >= stop_px)
            hit_target = target_px is not None and ((c >= target_px) if side == 1 else (c <= target_px))
            if hit_stop or hit_target:
                exit_bar = min(j + 1, hi - 1)
                exit_px = W.open[exit_bar]
                break
        else:
            exit_bar = min(end + 1, hi - 1)
            exit_px = W.open[exit_bar]
        ret = (exit_px / entry_px - 1) * side
        ret_fee = (1 + ret) * (1 - FEE) ** 2 - 1
        trades.append({"entry_bar": entry_bar, "exit_bar": exit_bar, "side": side, "ret": ret, "ret_fee": ret_fee})
        pos_until = exit_bar

    return trades


def fitness(genome, W, lo, hi):
    """Mean return after fees, or -inf if it didn't trade enough to mean anything. -inf, not 0:
    real strategies here mostly lose money (fees dominate a small edge, same finding as every
    other test in this project), so a 0.0 for "too few trades" would rank ABOVE a genuine but
    slightly-losing strategy and the search would systematically prefer barely trading at all -
    found and fixed 2026-09-15 after a run where every logged genome had fitness <= 0 and 0-trade
    genomes kept winning selection."""
    trades = backtest(genome, W, lo, hi)
    if len(trades) < MIN_TRADES_FITNESS:
        return float("-inf"), trades
    mean_ret = sum(t["ret_fee"] for t in trades) / len(trades)
    return mean_ret, trades
