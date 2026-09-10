"""
Walk-forward validation of the Connors RSI (CRSI) mean-reversion strategy.
========================================================================

crsi2_connors was the single least-dead of 33 strategies across
candle_strats_backtest.py + more_strats_backtest.py: consistent-sign
positive expectancy, but only ~12/23 symbols positive out-of-sample, a
-58% drawdown, and it was the best of 6 correlated mean-reversion
variants - which is what selection noise looks like. This is the honest
test of whether anything real is there.

  * REAL Connors RSI = mean of [ RSI(3) of close,
                                 RSI(2) of the up/down streak,
                                 PercentRank(1-day return, 100) ]
    (my earlier version was a 2-bar sum of RSI(3) - an approximation.)
  * Anchored WALK-FORWARD: expanding train window, 126-bar (~6 month)
    out-of-sample test blocks. At each roll, re-pick the entry/exit CRSI
    thresholds from a small grid using ONLY data seen so far, then trade
    the next unseen block. Every reported trade is out-of-sample.
  * -20% hard stop + 15-bar time stop, FIXED (never optimised), so the
    tuner cannot curve-fit risk control and to address the -58% DD.
  * Head-to-head vs FIXED params (enter<10 / exit>50) on the same blocks.
    If re-optimising does not beat fixed, the "adaptivity" is worthless
    (the same finding adaptive_backtest.py reached for the scalper).
  * Per symbol, then aggregated. The verdict bar is deliberately high.

    python crsi_walkforward.py
    python crsi_walkforward.py BTC-USD ETH-USD SOL-USD

Costs: 0.30%/side + 0.05%/side slippage. Long-only, one position, daily
Coinbase OHLC (cache shared with the other two backtests). Next-open fills;
the stop is checked intrabar against the low (conservative).
"""

import argparse
import statistics

from candle_strats_backtest import DEFAULT, FEE, SLIP, fetch_ohlc, O, H, L, C
from more_strats_backtest import _wilder_rsi

TEST = 126               # out-of-sample block length, bars
WARM = 260               # 200 (SMA200) + 100 (percentrank) + slack
STOP = 0.20              # hard stop as a fraction from entry (FIXED)
TIMESTOP = 15            # bars (FIXED)
ENTRY_GRID = [5, 10, 15, 20]
EXIT_GRID = [40, 50, 60, 70]
RT = 2 * (FEE + SLIP)    # round-trip cost, fraction


# --------------------------------------------------------------------------

def crsi_series(bars):
    close = [C(b) for b in bars]
    n = len(close)
    streak = [0.0] * n
    for i in range(1, n):
        if close[i] > close[i - 1]:
            streak[i] = streak[i - 1] + 1 if streak[i - 1] > 0 else 1.0
        elif close[i] < close[i - 1]:
            streak[i] = streak[i - 1] - 1 if streak[i - 1] < 0 else -1.0
        else:
            streak[i] = 0.0
    rsi_c = _wilder_rsi(close, 3)
    rsi_s = _wilder_rsi(streak, 2)
    roc1 = [0.0] * n
    for i in range(1, n):
        roc1[i] = (close[i] / close[i - 1] - 1) * 100 if close[i - 1] else 0.0
    crsi = [None] * n
    sma200 = [None] * n
    s = 0.0
    for i in range(n):
        s += close[i]
        if i >= 200:
            s -= close[i - 200]
        if i >= 199:
            sma200[i] = s / 200
        if i >= 101 and rsi_c[i] is not None and rsi_s[i] is not None:
            pr = sum(1 for x in roc1[i - 100:i] if x < roc1[i]) / 100 * 100
            crsi[i] = (rsi_c[i] + rsi_s[i] + pr) / 3
    return crsi, sma200, close


def sim_block(bars, crsi, sma200, close, lo, hi, e_th, x_th):
    """Net returns (fractions) for entries with signal-bar index in [lo, hi)."""
    rets, n, i = [], len(bars), lo
    while i < min(hi, n - 1):
        if (crsi[i] is not None and sma200[i] is not None
                and close[i] > sma200[i] and crsi[i] < e_th):
            entry = O(bars[i + 1]) * (1 + SLIP)
            stop_px = entry * (1 - STOP)
            exit_px, j = None, i + 1
            while j < n:
                if L(bars[j]) <= stop_px:
                    exit_px = min(O(bars[j]), stop_px)
                    break
                if crsi[j] is not None and crsi[j] > x_th:
                    exit_px = C(bars[j])
                    break
                if j - (i + 1) >= TIMESTOP:
                    exit_px = C(bars[j])
                    break
                j += 1
            if exit_px is None:
                exit_px, j = C(bars[-1]), n - 1
            rets.append(exit_px * (1 - SLIP) / entry - 1 - RT)
            i = j + 1
        else:
            i += 1
    return rets


def best_params(bars, crsi, sma200, close, lo, hi):
    best_eq, best_g = None, (10, 50)
    for e in ENTRY_GRID:
        for x in EXIT_GRID:
            r = sim_block(bars, crsi, sma200, close, lo, hi, e, x)
            if len(r) < 5:
                continue
            eq = 1.0
            for v in r:
                eq *= (1 + v)
            if best_eq is None or eq > best_eq:
                best_eq, best_g = eq, (e, x)
    return best_g


def compound(rets):
    eq = 1.0
    for r in rets:
        eq *= (1 + r)
    return eq


def maxdd(rets):
    eq = peak = 1.0
    worst = 0.0
    for r in rets:
        eq *= (1 + r)
        peak = max(peak, eq)
        worst = min(worst, eq / peak - 1)
    return worst


def walk(bars):
    crsi, sma200, close = crsi_series(bars)
    n = len(bars)
    wf, fx, params = [], [], []
    s = WARM
    while s + TEST <= n:
        e, x = best_params(bars, crsi, sma200, close, WARM, s) if s > WARM else (10, 50)
        params.append((e, x))
        wf += sim_block(bars, crsi, sma200, close, s, s + TEST, e, x)
        fx += sim_block(bars, crsi, sma200, close, s, s + TEST, 10, 50)
        s += TEST
    last = min(s, n - 1)
    bh = close[last] / close[WARM] - 1 if n > WARM else 0.0
    return wf, fx, bh, params


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("symbols", nargs="*")
    args = ap.parse_args()
    syms = [s.upper() for s in args.symbols] or DEFAULT

    print("Walk-forward CRSI mean reversion | REAL Connors RSI | expanding train, "
          f"{TEST}-bar OOS blocks | -{STOP*100:.0f}% stop, {TIMESTOP}-bar time stop (fixed)")
    print(f"grid re-fit each block: entry in {ENTRY_GRID}, exit in {EXIT_GRID} | "
          f"cost {RT*100:.2f}% round-trip\n")

    print(f"{'symbol':<10} {'blocks':>6} {'trades':>7} {'win%':>5} "
          f"{'WF ret':>9} {'WF maxDD':>9} {'FIXED ret':>10} {'B&H ret':>9}")
    print("-" * 78)

    rows = []
    for sym in syms:
        bars = fetch_ohlc(sym)
        if len(bars) < WARM + TEST:
            print(f"{sym:<10} skip ({len(bars)} bars)")
            continue
        wf, fx, bh, params = walk(bars)
        if not wf:
            print(f"{sym:<10} no trades")
            continue
        wr = sum(1 for r in wf if r > 0) / len(wf) * 100
        wf_ret, fx_ret = compound(wf) - 1, compound(fx) - 1
        wf_dd = maxdd(wf)
        rows.append((sym, len(params), len(wf), wr, wf_ret, wf_dd, fx_ret, bh))
        print(f"{sym:<10} {len(params):>6} {len(wf):>7} {wr:>5.0f} "
              f"{wf_ret*100:>+8.0f}% {wf_dd*100:>+8.0f}% {fx_ret*100:>+9.0f}% {bh*100:>+8.0f}%")

    if not rows:
        print("\nno symbols with enough history"); return

    m = len(rows)
    wf_rets = [r[4] for r in rows]
    fx_rets = [r[6] for r in rows]
    wf_dds = [r[5] for r in rows]
    wf_pos = sum(1 for v in wf_rets if v > 0)
    fx_pos = sum(1 for v in fx_rets if v > 0)
    beat_bh = sum(1 for r in rows if r[4] > r[7])
    beat_fx = sum(1 for r in rows if r[4] > r[6])

    print("\n" + "=" * 78)
    print(f"AGGREGATE over {m} symbols  (all out-of-sample)")
    print("=" * 78)
    print(f"  walk-forward:  positive {wf_pos}/{m}   beats B&H {beat_bh}/{m}   "
          f"beats fixed-params {beat_fx}/{m}")
    print(f"  WF return   median {statistics.median(wf_rets)*100:+.0f}%   "
          f"mean {statistics.mean(wf_rets)*100:+.0f}%")
    print(f"  WF maxDD    median {statistics.median(wf_dds)*100:+.0f}%   "
          f"worst {min(wf_dds)*100:+.0f}%")
    print(f"  fixed 10/50 median {statistics.median(fx_rets)*100:+.0f}%   "
          f"(positive {fx_pos}/{m})")
    print(f"  buy & hold  median {statistics.median([r[7] for r in rows])*100:+.0f}%")

    strong = (wf_pos >= 0.65 * m and statistics.median(wf_rets) > 0
              and statistics.median(wf_dds) > -0.40
              and beat_bh >= 0.55 * m and statistics.median(wf_rets) >= statistics.median(fx_rets))
    weak_pos = statistics.median(wf_rets) > 0 and wf_pos >= 0.5 * m

    print("\n" + "-" * 78)
    if strong:
        print("VERDICT: HOLDS UP. Walk-forward is positive on most symbols with a")
        print("         controlled drawdown and the re-fit beats fixed params.")
        print("         Next step: paper-trade it. NOT straight to real money.")
    elif weak_pos:
        print("VERDICT: MARGINAL. Barely positive, not robust across symbols /")
        print("         drawdown too deep / re-fitting doesn't help. Treat as no edge.")
    else:
        print("VERDICT: FAILS. Walk-forward confirms no real out-of-sample edge —")
        print("         consistent with the 33-strategy batch result.")
    print("Descriptive of the past only. Not a prediction, not advice.")


if __name__ == "__main__":
    main()
