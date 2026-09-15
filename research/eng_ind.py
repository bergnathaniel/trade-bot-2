"""
Indicators for the prediction engine (PREREG_ENGINE.md, section B).
===================================================================

TradingView-style definitions, pure stdlib. Every function is causal: value i
uses elements 0..i only, and is None until enough history exists. The engine
test's look-ahead check (leakage.truncation_test) holds all of this to that.
"""

import math
from collections import deque


def sma(xs, n):
    out, s = [None] * len(xs), 0.0
    for i, x in enumerate(xs):
        s += x
        if i >= n:
            s -= xs[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def _smooth(xs, n, alpha, start=0):
    """EMA-family smoother seeded with the SMA of the first n values from `start`."""
    out = [None] * len(xs)
    if len(xs) - start < n:
        return out
    v = sum(xs[start:start + n]) / n
    out[start + n - 1] = v
    for i in range(start + n, len(xs)):
        v += alpha * (xs[i] - v)
        out[i] = v
    return out


def ema(xs, n, start=0):
    return _smooth(xs, n, 2.0 / (n + 1), start)


def rma(xs, n, start=0):
    """Wilder's moving average (TradingView ta.rma)."""
    return _smooth(xs, n, 1.0 / n, start)


def rsi(closes, n=14):
    m = len(closes)
    up, dn = [0.0] * m, [0.0] * m
    for i in range(1, m):
        d = closes[i] - closes[i - 1]
        up[i], dn[i] = max(d, 0.0), max(-d, 0.0)
    au, ad = rma(up, n, start=1), rma(dn, n, start=1)
    out = [None] * m
    for i in range(m):
        if au[i] is not None:
            out[i] = 100.0 if ad[i] == 0 else 100.0 - 100.0 / (1.0 + au[i] / ad[i])
    return out


def macd_hist(closes, fast=12, slow=26, signal=9):
    ef, es = ema(closes, fast), ema(closes, slow)
    line = [a - b if a is not None and b is not None else 0.0 for a, b in zip(ef, es)]
    sig = ema(line, signal, start=slow - 1)
    return [line[i] - sig[i] if sig[i] is not None else None for i in range(len(closes))]


def true_range(highs, lows, closes):
    tr = [highs[0] - lows[0]] if highs else []
    for i in range(1, len(highs)):
        pc = closes[i - 1]
        tr.append(max(highs[i] - lows[i], abs(highs[i] - pc), abs(lows[i] - pc)))
    return tr


def atr(highs, lows, closes, n=14):
    return rma(true_range(highs, lows, closes), n)


def bollinger(closes, n=20, k=2.0):
    """(lower, upper) with population standard deviation, as TradingView uses."""
    m = len(closes)
    lo, hi = [None] * m, [None] * m
    s = s2 = 0.0
    for i, x in enumerate(closes):
        s += x
        s2 += x * x
        if i >= n:
            s -= closes[i - n]
            s2 -= closes[i - n] ** 2
        if i >= n - 1:
            mu = s / n
            sd = math.sqrt(max(s2 / n - mu * mu, 0.0))
            lo[i], hi[i] = mu - k * sd, mu + k * sd
    return lo, hi


def adx(highs, lows, closes, n=14):
    m = len(highs)
    pdm, ndm = [0.0] * m, [0.0] * m
    for i in range(1, m):
        u, d = highs[i] - highs[i - 1], lows[i - 1] - lows[i]
        pdm[i] = u if u > d and u > 0 else 0.0
        ndm[i] = d if d > u and d > 0 else 0.0
    tr = true_range(highs, lows, closes)
    str_, sp, sn = rma(tr, n, start=1), rma(pdm, n, start=1), rma(ndm, n, start=1)
    dx, first = [0.0] * m, None
    for i in range(m):
        if str_[i]:
            p, q = 100.0 * sp[i] / str_[i], 100.0 * sn[i] / str_[i]
            dx[i] = 100.0 * abs(p - q) / (p + q) if p + q > 0 else 0.0
            first = i if first is None else first
    return rma(dx, n, start=first) if first is not None else [None] * m


def rolling_max(xs, n):
    """max(xs[i-n+1 .. i]); None until n values exist."""
    out, q = [None] * len(xs), deque()
    for i, x in enumerate(xs):
        while q and xs[q[-1]] <= x:
            q.pop()
        q.append(i)
        if q[0] <= i - n:
            q.popleft()
        if i >= n - 1:
            out[i] = xs[q[0]]
    return out


def rolling_min(xs, n):
    neg = rolling_max([-x for x in xs], n)
    return [None if v is None else -v for v in neg]


def prior_high(highs, n=20):
    """Highest high of the n bars BEFORE bar i."""
    rm = rolling_max(highs, n)
    return [None] + rm[:-1]


def prior_low(lows, n=20):
    rm = rolling_min(lows, n)
    return [None] + rm[:-1]


def structure(highs, lows, n=5):
    """+1 higher high AND higher low over the last n bars vs the n before; -1 mirror; else 0."""
    hn, ln = rolling_max(highs, n), rolling_min(lows, n)
    out = [None] * len(highs)
    for i in range(2 * n - 1, len(highs)):
        if hn[i] > hn[i - n] and ln[i] > ln[i - n]:
            out[i] = 1
        elif hn[i] < hn[i - n] and ln[i] < ln[i - n]:
            out[i] = -1
        else:
            out[i] = 0
    return out


def anchored_vwap(bars, anchor_of):
    """VWAP of typical price and its volume-weighted sigma, reset whenever anchor_of(t) changes."""
    m = len(bars)
    vw, sd = [None] * m, [None] * m
    key = None
    pv = v_ = p2v = 0.0
    for i, (t, o, h, l, c, v) in enumerate(bars):
        k = anchor_of(t)
        if k != key:
            key, pv, v_, p2v = k, 0.0, 0.0, 0.0
        tp = (h + l + c) / 3.0
        pv += tp * v
        p2v += tp * tp * v
        v_ += v
        if v_ > 0:
            mu = pv / v_
            vw[i], sd[i] = mu, math.sqrt(max(p2v / v_ - mu * mu, 0.0))
    return vw, sd


def rolling_logret_sd(closes, n=60):
    """Sample stdev of the last n one-bar log returns ending at bar i."""
    m = len(closes)
    r = [0.0] + [math.log(closes[i] / closes[i - 1]) for i in range(1, m)]
    out, s, s2 = [None] * m, 0.0, 0.0
    for i in range(1, m):
        s += r[i]
        s2 += r[i] * r[i]
        if i > n:
            s -= r[i - n]
            s2 -= r[i - n] ** 2
        if i >= n:
            out[i] = math.sqrt(max((s2 - s * s / n) / (n - 1), 0.0))
    return out


def trailing_pct_rank(xs, n):
    """Share of the last n values (current included) that are <= the current value."""
    out = [None] * len(xs)
    for i in range(len(xs)):
        if xs[i] is None or i < n - 1:
            continue
        w = [x for x in xs[i - n + 1:i + 1] if x is not None]
        if len(w) >= n // 2:
            out[i] = sum(1 for x in w if x <= xs[i]) / len(w)
    return out
