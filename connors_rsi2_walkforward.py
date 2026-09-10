"""
Honest per-instrument walk-forward of Connors RSI(2) on US equity ETFs.
====================================================================

classic_on_stocks.py showed the classics PASS on equities - but with the
same optimistic pooling that flattered crsi2_connors on crypto before its
walk-forward killed it. This is the equivalent honest test:

  * ONE account per instrument, $1 start, 100%-in / 100%-out, cost each side.
  * Anchored WALK-FORWARD: expanding train, 126-day (~6mo) OOS blocks. Each
    block trades with the (entry, exit) RSI thresholds that maximised
    compounded return on data seen SO FAR. Every trade is out-of-sample.
  * 10-bar time stop, FIXED (Connors uses no stop; this only stops a
    position hanging forever). No hard price stop.
  * Head to head, over the identical tested span, vs:
      - buy & hold the instrument
      - DCA (invest $1 every 21 trading days)
      - RSI2 with FIXED 10/70 params (does re-optimising add anything?)
  * Verdict asks the Connors question: better RISK-ADJUSTED return
    (CAGR / |maxDD|) and a shallower drawdown - not just more return.

    python connors_rsi2_walkforward.py
    python connors_rsi2_walkforward.py SPY QQQ XLK

Data: Yahoo daily (cache shared with classic_on_stocks.py). Cost 0.05%/side.
Descriptive of the past only. Not a prediction, not investment advice.
"""

import argparse
import statistics

from classic_on_stocks import fetch, O, H, L, C
from more_strats_backtest import _sma, _wilder_rsi

SIDE = 0.0005
WARM = 220
TEST = 126
TIMESTOP = 10
ENTRY_GRID = [5, 10, 15]
EXIT_GRID = [65, 70, 75]
RT = 2 * SIDE

ETFS = ["SPY", "QQQ", "DIA", "IWM", "MDY", "EEM", "EFA",
        "XLK", "XLF", "XLE", "XLV", "XLP", "XLY", "XLI", "XLU", "XLB",
        "TLT", "GLD", "HYG"]


def prep(bars):
    cl = [C(b) for b in bars]
    return cl, _sma(cl, 200), _wilder_rsi(cl, 2)


def sim_block(bars, cl, sma200, rsi2, lo, hi, e_th, x_th):
    """Net trade returns (fractions) for entries with signal index in [lo, hi)."""
    rets, n, i = [], len(bars), lo
    while i < min(hi, n - 1):
        if sma200[i] is not None and cl[i] > sma200[i] and rsi2[i] is not None and rsi2[i] < e_th:
            entry = O(bars[i + 1]) * (1 + SIDE)
            exit_px, j = None, i + 1
            while j < n:
                if rsi2[j] is not None and rsi2[j] > x_th:
                    exit_px = C(bars[j]); break
                if j - (i + 1) >= TIMESTOP:
                    exit_px = C(bars[j]); break
                j += 1
            if exit_px is None:
                exit_px, j = C(bars[-1]), n - 1
            rets.append(exit_px * (1 - SIDE) / entry - 1 - RT)
            i = j + 1
        else:
            i += 1
    return rets


def best_params(bars, cl, sma200, rsi2, lo, hi):
    best_eq, best_g = None, (10, 70)
    for e in ENTRY_GRID:
        for x in EXIT_GRID:
            r = sim_block(bars, cl, sma200, rsi2, lo, hi, e, x)
            if len(r) < 8:
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


def dd_rets(rets):
    eq = peak = 1.0
    w = 0.0
    for r in rets:
        eq *= (1 + r)
        peak = max(peak, eq)
        w = min(w, eq / peak - 1)
    return w


def bh(cl, a, b):
    mult = cl[b - 1] / cl[a]
    peak, w = cl[a], 0.0
    for k in range(a, b):
        peak = max(peak, cl[k])
        w = min(w, cl[k] / peak - 1)
    return mult, w


def dca_mult(cl, a, b, every=21):
    units = invested = 0.0
    for i in range(a, b):
        if (i - a) % every == 0:
            units += 1.0 / cl[i]
            invested += 1.0
    return units * cl[b - 1] / invested if invested else 1.0


def cagr(mult, days):
    yrs = max(days / 365.25, 1e-9)
    return mult ** (1 / yrs) - 1 if mult > 0 else -1.0


def walk(bars):
    cl, sma200, rsi2 = prep(bars)
    n = len(bars)
    wf, fx, params = [], [], []
    s = WARM
    while s + TEST <= n:
        e, x = best_params(bars, cl, sma200, rsi2, WARM, s) if s > WARM else (10, 70)
        params.append((e, x))
        wf += sim_block(bars, cl, sma200, rsi2, s, s + TEST, e, x)
        fx += sim_block(bars, cl, sma200, rsi2, s, s + TEST, 10, 70)
        s += TEST
    last = min(s, n - 1)
    days = (bars[last][0] - bars[WARM][0]) / 86400
    return wf, fx, params, (WARM, last, days)


def rr(c, d):     # risk-adjusted: CAGR per unit of drawdown
    return c / abs(d) if d else 0.0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("tickers", nargs="*")
    ap.add_argument("--show-params", action="store_true", help="print per-block chosen thresholds")
    args = ap.parse_args()
    tks = [t.upper() for t in args.tickers] or ETFS

    print("Connors RSI(2) walk-forward on US equity ETFs | expanding train, 126d OOS blocks")
    print(f"grid re-fit per block: entry {ENTRY_GRID}, exit {EXIT_GRID} | {TIMESTOP}-bar time stop "
          f"| cost {RT*100:.2f}% round-trip\n")
    print(f"{'ticker':<7} {'trds':>5} {'win%':>5} {'%mkt':>5} "
          f"{'WF ret':>8} {'WF CAGR':>8} {'WF DD':>7} | "
          f"{'B&H ret':>8} {'B&H CAGR':>9} {'B&H DD':>7} | {'DCA':>6} {'FIX ret':>8}")
    print("-" * 108)

    rows = []
    for tk in tks:
        bars = fetch(tk)
        if len(bars) < WARM + 2 * TEST:
            print(f"{tk:<7} skip ({len(bars)} bars)")
            continue
        wf, fx, params, (a, b, days) = walk(bars)
        if not wf:
            print(f"{tk:<7} no trades")
            continue
        cl = [C(x) for x in bars]
        wf_m, wf_dd = compound(wf), dd_rets(wf)
        fx_m = compound(fx)
        bh_m, bh_ddv = bh(cl, a, b)
        dca_m = dca_mult(cl, a, b)
        win = sum(1 for r in wf if r > 0) / len(wf) * 100
        # % time in market: sum of holding spans is not tracked per-bar here; approximate
        # from trade count * avg 4-bar hold is unreliable, so report n trades instead.
        wf_c, bh_c = cagr(wf_m, days), cagr(bh_m, days)
        rows.append((tk, len(wf), win, wf_m, wf_c, wf_dd, bh_m, bh_c, bh_ddv, dca_m, fx_m, days))
        print(f"{tk:<7} {len(wf):>5} {win:>4.0f}% {'':>5} "
              f"{(wf_m-1)*100:>+7.0f}% {wf_c*100:>+7.1f}% {wf_dd*100:>+6.0f}% | "
              f"{(bh_m-1)*100:>+7.0f}% {bh_c*100:>+8.1f}% {bh_ddv*100:>+6.0f}% | "
              f"{(dca_m-1)*100:>+5.0f}% {(fx_m-1)*100:>+7.0f}%")
        if args.show_params:
            print(f"        params/block: {params}")

    if not rows:
        print("\nno instruments with enough history"); return

    m = len(rows)
    wf_c = [r[4] for r in rows]; bh_c = [r[7] for r in rows]
    wf_dd = [r[5] for r in rows]; bh_dd = [r[8] for r in rows]
    wf_ra = [rr(r[4], r[5]) for r in rows]
    bh_ra = [rr(r[7], r[8]) for r in rows]
    pos = sum(1 for r in rows if r[3] > 1)
    beat_bh_ret = sum(1 for r in rows if r[4] > r[7])
    beat_bh_ra = sum(1 for i, r in enumerate(rows) if wf_ra[i] > bh_ra[i])
    shallower = sum(1 for r in rows if abs(r[5]) < 0.6 * abs(r[8]))
    beat_fix = sum(1 for r in rows if r[3] > r[10])
    beat_dca = sum(1 for r in rows if r[3] > r[9])

    print("\n" + "=" * 108)
    print(f"AGGREGATE over {m} ETFs  (all out-of-sample)")
    print("=" * 108)
    print(f"  WF positive: {pos}/{m}   |   WF beats B&H on return: {beat_bh_ret}/{m}   "
          f"on risk-adjusted (CAGR/|DD|): {beat_bh_ra}/{m}")
    print(f"  WF drawdown < 0.6x B&H drawdown: {shallower}/{m}   |   "
          f"WF beats DCA: {beat_dca}/{m}   |   WF beats fixed-10/70: {beat_fix}/{m}")
    print(f"  median CAGR   WF {statistics.median(wf_c)*100:+.1f}%   "
          f"B&H {statistics.median(bh_c)*100:+.1f}%")
    print(f"  median maxDD  WF {statistics.median(wf_dd)*100:+.0f}%   "
          f"B&H {statistics.median(bh_dd)*100:+.0f}%")
    print(f"  median CAGR/|DD|   WF {statistics.median(wf_ra):.2f}   "
          f"B&H {statistics.median(bh_ra):.2f}")

    strong_ra = (statistics.median(wf_ra) > statistics.median(bh_ra)
                 and beat_bh_ra >= 0.6 * m and shallower >= 0.6 * m
                 and pos >= 0.8 * m and beat_fix >= 0.5 * m)
    matches_ret = statistics.median(wf_c) > 0 and beat_bh_ret >= 0.4 * m

    print("\n" + "-" * 108)
    if strong_ra and matches_ret:
        print("VERDICT: HOLDS UP as a lower-drawdown alternative. Better risk-adjusted return")
        print("         than buy & hold on most ETFs, much shallower drawdowns, re-fit helps.")
        print("         Reasonable to build as a PAPER bot next. Not a return booster; a smoother ride.")
    elif strong_ra:
        print("VERDICT: LOWER DRAWDOWN, LOWER RETURN. Cuts drawdowns hard but gives up return vs")
        print("         buy & hold. Only worth building if a smoother equity curve is the goal.")
    elif matches_ret:
        print("VERDICT: MARGINAL. Roughly tracks buy & hold without a clear risk-adjusted edge.")
        print("         Hard to justify the effort over just holding an index fund / DCA.")
    else:
        print("VERDICT: DOES NOT HOLD UP. The pooled classic_on_stocks.py result was mostly the")
        print("         pooling artifact — same lesson as crsi2_connors on crypto. Don't build the bot.")
    print("Descriptive of the past only. Not a prediction, not investment advice.")


if __name__ == "__main__":
    main()
