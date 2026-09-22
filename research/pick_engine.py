"""
Walk-forward "pick the stocks the strategy did well on" (PREREG_PICK.md).
==========================================================================

`sim` re-implements the app's two rules exactly (IBS Swing in index.html, Fisher Transform in
extra_bots.js) and its order fills (execute() in index.html): decide on a candle's close, fill at the
next candle's open, 0.0002 slippage each way, a fee per trade, all cash in and all out. run_pick.py
checks this against the app's own basket test before any result counts.

Rows are [time, open, high, low, close, vwap, volume], oldest first.
"""

import math

START_CASH = 10000.0
SLIP = 0.0002
WARMUP = 60


def _fisher(high, low, length=10):
    n = len(high)
    f = [None] * n
    v = prev = 0.0
    for i in range(length - 1, n):
        hi, lo = -math.inf, math.inf
        for j in range(i - length + 1, i + 1):
            mid = (high[j] + low[j]) / 2
            hi, lo = max(hi, mid), min(lo, mid)
        mid = (high[i] + low[i]) / 2
        x = 0.66 * ((mid - lo) / (hi - lo) - 0.5 if hi > lo else 0.0) + 0.67 * v
        v = max(-0.999, min(0.999, x))
        prev = f[i] = 0.5 * math.log((1 + v) / (1 - v)) + 0.5 * prev
    return f


def sim(rows, strat, fee, liquidate=False):
    """Run `strat` ("ibs" or "fisher") over `rows` the way the app's simulateRows does with next-open
    fills: decisions from candle WARMUP to the second-to-last, each filled at the next candle's open.
    Returns (return, closed_trades). liquidate=True sells any open position at the last close (with
    slippage and fee) so the return is what an investor who stopped then would have had; the app's own
    number (liquidate=False) marks it at the last close for free."""
    n = len(rows)
    op = [r[1] for r in rows]
    hi = [r[2] for r in rows]
    lo = [r[3] for r in rows]
    cl = [r[4] for r in rows]
    fish = _fisher(hi, lo) if strat == "fisher" else None
    cash, qty, sells, entry_idx = START_CASH, 0.0, 0, None

    for i in range(WARMUP, n - 1):
        pos = qty > 0
        act = None
        if strat == "ibs":
            rng = hi[i] - lo[i]
            ibs = (cl[i] - lo[i]) / rng if rng > 0 else 0.5
            if not pos and ibs < 0.2:
                act = "buy"
            elif pos and ibs > 0.8:
                act = "sell"
        else:
            f = fish
            if f[i - 2] is None:
                continue
            if pos and f[i - 1] > 1.5 and f[i] < f[i - 1]:
                act = "sell"
            elif pos:
                if i - entry_idx >= 20:
                    act = "sell"
            elif f[i - 1] < -1.5 and f[i] > f[i - 1] and f[i - 1] <= f[i - 2]:
                act = "buy"
                entry_idx = i
        if act == "buy":
            spend = cash
            if spend >= 1:
                fill = op[i + 1] * (1 + SLIP)
                qty += (spend - spend * fee) / fill
                cash -= spend
        elif act == "sell" and qty > 0:
            gross = qty * op[i + 1] * (1 - SLIP)
            cash += gross - gross * fee
            qty = 0.0
            sells += 1

    if liquidate and qty > 0:
        gross = qty * cl[-1] * (1 - SLIP)
        cash += gross - gross * fee
        qty = 0.0
        sells += 1
    return (cash + qty * cl[-1]) / START_CASH - 1, sells


def trailing_return(rows, t, strat, fee):
    """The strategy's return on one stock over the 252 trading days ending at index t (fills from the
    open of t-251 through the open of t, then closed at t's close), after 60 warm-up candles. Uses
    rows[t-312 .. t] only - nothing after t."""
    if t - 312 < 0:
        return None
    return sim(rows[t - 312:t + 1], strat, fee, liquidate=True)[0]


def forward_result(rows, t, strat, fee):
    """The strategy over the 63 trading days after t (fills from the open of t+1 through the open of
    t+63, closed at t+63's close), after 60 warm-up candles. Returns (return, closed_trades)."""
    if t - 60 < 0 or t + 63 >= len(rows):
        return None
    return sim(rows[t - 60:t + 64], strat, fee, liquidate=True)
