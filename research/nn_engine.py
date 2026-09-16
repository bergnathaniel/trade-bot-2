"""
Nearest-neighbor setup matching (PREREG_NN.md).
================================================

For a candle's feature vector, find its K nearest neighbors among candles whose own outcome has
already finished, and vote LONG/SHORT/NO TRADE by what those neighbors did next. Pure stdlib for
everything except the neighbor search itself (scipy.spatial.cKDTree - an exact index over ~200k
points isn't tractable in pure Python at this scale).

Bars are [open_time, open, high, low, close, volume], oldest first.
"""

import math
import random

import numpy as np
from scipy.spatial import cKDTree

H = 12              # outcome/holding horizon, in 5-minute bars (1 hour)
K = 10               # neighbors
CONSENSUS = 7        # of K, needed to agree for a trade
VOTE_R = 0.5         # a neighbor's forward R-multiple needed to count as a LONG/SHORT vote
Z_WINDOW = 2000       # rolling window for feature standardization (bars)
Z_MIN = 100          # minimum bars before a feature is considered warmed up
REBUILD_EVERY = 288   # rebuild the KD-tree this often (one 5-minute trading day)
FEE = 0.0025         # 0.25% per side


def resample_5m(bars1m):
    """1-minute bars, oldest first, into 5-minute bars aligned to :00/:05/.../:55."""
    out = []
    cur = None
    for t, o, h, l, c, v in bars1m:
        bucket = t - t % 300
        if cur is None or cur[0] != bucket:
            if cur is not None:
                out.append(cur)
            cur = [bucket, o, h, l, c, v]
        else:
            cur[2] = max(cur[2], h)
            cur[3] = min(cur[3], l)
            cur[4] = c
            cur[5] += v
    if cur is not None:
        out.append(cur)
    return out


def _rsi(close, n=14):
    out = [None] * len(close)
    if len(close) <= n:
        return out
    g = l = 0.0
    for i in range(1, n + 1):
        d = close[i] - close[i - 1]
        g += max(d, 0.0)
        l += max(-d, 0.0)
    g /= n
    l /= n
    out[n] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    for i in range(n + 1, len(close)):
        d = close[i] - close[i - 1]
        g = (g * (n - 1) + max(d, 0.0)) / n
        l = (l * (n - 1) + max(-d, 0.0)) / n
        out[i] = 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    return out


def _atr(high, low, close, n=14):
    out = [None] * len(close)
    tr = [None] * len(close)
    for i in range(1, len(close)):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    if len(close) <= n:
        return out
    s = sum(tr[1:n + 1])
    out[n] = s / n
    for i in range(n + 1, len(close)):
        out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


def _rolling_mean_std(v, n):
    """Simple rolling mean/std over the last n values (inclusive of the current one)."""
    mean = [None] * len(v)
    std = [None] * len(v)
    s = q = 0.0
    for i, x in enumerate(v):
        s += x
        q += x * x
        if i >= n:
            s -= v[i - n]
            q -= v[i - n] * v[i - n]
        if i >= n - 1:
            m = s / n
            var = max(q / n - m * m, 0.0)
            mean[i] = m
            std[i] = math.sqrt(var)
    return mean, std


def compute_indicators(bars):
    close = [b[4] for b in bars]
    open_ = [b[1] for b in bars]
    high = [b[2] for b in bars]
    low = [b[3] for b in bars]
    vol = [b[5] for b in bars]
    rsi14 = _rsi(close, 14)
    atr14 = _atr(high, low, close, 14)
    bb_mid, bb_std = _rolling_mean_std(close, 20)
    vol_avg, _ = _rolling_mean_std(vol, 20)
    return {"close": close, "open": open_, "high": high, "low": low, "vol": vol,
            "rsi14": rsi14, "atr14": atr14, "bb_mid": bb_mid, "bb_std": bb_std, "vol_avg": vol_avg}


def raw_features(ind):
    """Six raw (unstandardized) features per candle, or None where not yet computable."""
    close, vol = ind["close"], ind["vol"]
    n = len(close)
    feats = [None] * n
    for i in range(n):
        if i < 12 or ind["rsi14"][i] is None or ind["atr14"][i] is None \
                or ind["bb_std"][i] is None or ind["vol_avg"][i] is None or ind["vol_avg"][i] <= 0:
            continue
        r1 = close[i] / close[i - 1] - 1
        r3 = close[i] / close[i - 3] - 1
        r12 = close[i] / close[i - 12] - 1
        bb = 0.0 if ind["bb_std"][i] == 0 else (close[i] - ind["bb_mid"][i]) / (2 * ind["bb_std"][i])
        bb = max(-2.0, min(2.0, bb))
        volr = math.log(max(vol[i], 1e-9) / ind["vol_avg"][i])
        feats[i] = [r1, r3, r12, ind["rsi14"][i], bb, volr]
    return feats


def zscore_features(feats):
    """Rolling Z_WINDOW z-score per feature dimension, causal (each candle uses only its own
    trailing window). Returns an (n, 6) float array with NaN rows where not yet warmed up."""
    n = len(feats)
    n_dims = 6
    raw = np.full((n, n_dims), np.nan)
    for i, f in enumerate(feats):
        if f is not None:
            raw[i] = f
    z = np.full((n, n_dims), np.nan)
    for d in range(n_dims):
        col = raw[:, d]
        valid_idx = np.where(~np.isnan(col))[0]
        # rolling mean/std over the last Z_WINDOW *valid* observations, causal
        for k, i in enumerate(valid_idx):
            lo = max(0, k - Z_WINDOW + 1)
            if k - lo + 1 < Z_MIN:
                continue
            window = col[valid_idx[lo:k + 1]]
            m, s = window.mean(), window.std()
            z[i, d] = 0.0 if s == 0 else (col[i] - m) / s
    return z


def outcomes(close, atr14):
    """R[j] and vote[j] (+1 LONG, -1 SHORT, 0 no vote) for every j with a finished H-bar outcome."""
    n = len(close)
    R = [None] * n
    vote = [0] * n
    for j in range(n - H):
        a = atr14[j]
        if a is None or a <= 0:
            continue
        r = (close[j + H] - close[j]) / a
        R[j] = r
        vote[j] = 1 if r >= VOTE_R else (-1 if r <= -VOTE_R else 0)
    return R, vote


def valid_rows(z):
    """Indices with a complete (no-NaN) feature row."""
    return np.where(~np.isnan(z).any(axis=1))[0]


def run_real(z, vote, open_, close, pool_end, test_start, test_end, seed=20260915):
    """Walk forward through [test_start, test_end). At each eligible decision, find K nearest
    neighbors among candles whose outcome has already finished, vote, and paper-trade the
    consensus: enter at the next bar's open, exit H bars after entry at that bar's open (PREREG_NN
    D.4). Returns closed trades and, per decision, the neighbor indices found (so the shuffled
    control can reuse the same neighbor SETS without re-searching)."""
    valid = valid_rows(z)

    trades = []
    decisions = []   # (i, neighbor_idx_array) for every candle where a vote was tallied
    tree = None
    tree_upto = -1     # neighbors in the tree are valid up to and including this raw index
    tree_pool_idx = None
    in_pos = False
    entry_bar = entry_px = side = None

    for i in range(test_start, min(test_end, len(z) - H - 2)):
        if np.isnan(z[i]).any():
            continue
        cap = i - H   # j eligible as a neighbor iff j <= i - H (its outcome has already finished)
        if cap < 0:
            continue
        if tree is None or i - tree_upto >= REBUILD_EVERY:
            pool_idx = valid[(valid <= cap)]
            if len(pool_idx) < K:
                continue
            tree = cKDTree(z[pool_idx])
            tree_pool_idx = pool_idx
            tree_upto = cap
        # neighbors from a tree built at an earlier (<=) cap are still all eligible now, since
        # eligibility only grows; this is the deliberate staleness described in PREREG_NN.md H.
        dist, idx = tree.query(z[i], k=K)
        idx = np.atleast_1d(idx)
        neigh = tree_pool_idx[idx]
        decisions.append((i, neigh))

        if in_pos:
            if i == entry_bar + H:
                exitpx = open_[i]
                ret = (exitpx / entry_px - 1) * side
                ret_after_fee = (1 + ret) * (1 - FEE) * (1 - FEE) - 1
                trades.append({"entry_bar": entry_bar, "exit_bar": i, "side": side,
                                "ret": ret, "ret_fee": ret_after_fee})
                in_pos = False
            continue

        votes = vote[neigh]
        longs = int((votes == 1).sum())
        shorts = int((votes == -1).sum())
        if longs >= CONSENSUS:
            side_now = 1
        elif shorts >= CONSENSUS:
            side_now = -1
        else:
            continue
        entry_bar, entry_px, side, in_pos = i + 1, open_[i + 1], side_now, True

    return trades, decisions


def run_shuffled(decisions, vote, open_, pool_probs, seed):
    """Same neighbor sets as run_real, but each neighbor's vote is redrawn independently from the
    pool's overall vote distribution - severs whether a neighbor resembles candle i from its
    outcome, while keeping the same mechanism, same entry/exit convention, same fees."""
    rng = random.Random(seed)
    choices, weights = [1, -1, 0], [pool_probs[1], pool_probs[-1], pool_probs[0]]
    trades = []
    in_pos = False
    entry_bar = entry_px = side = None
    for i, neigh in decisions:
        if in_pos:
            if i == entry_bar + H:
                exitpx = open_[i]
                ret = (exitpx / entry_px - 1) * side
                ret_after_fee = (1 + ret) * (1 - FEE) * (1 - FEE) - 1
                trades.append({"ret": ret, "ret_fee": ret_after_fee})
                in_pos = False
            continue
        drawn = [rng.choices(choices, weights)[0] for _ in neigh]
        longs = drawn.count(1)
        shorts = drawn.count(-1)
        if longs >= CONSENSUS:
            side_now = 1
        elif shorts >= CONSENSUS:
            side_now = -1
        else:
            continue
        if i + 1 >= len(open_):
            continue
        entry_bar, entry_px, side, in_pos = i + 1, open_[i + 1], side_now, True
    return trades


def pool_vote_probs(vote, upto):
    v = vote[:upto]
    n = len(v) if len(v) else 1
    longs = sum(1 for x in v if x == 1)
    shorts = sum(1 for x in v if x == -1)
    return {1: longs / n, -1: shorts / n, 0: max(0.0, 1 - (longs + shorts) / n)}
