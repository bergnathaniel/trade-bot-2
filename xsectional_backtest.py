"""
Cross-sectional strategies on the 23-coin basket.
================================================

Everything tested so far has been single-asset *timing* (be in / be out of
one coin). This tests the other big family: *relative* bets across the
basket, rebalanced weekly or monthly so transaction cost stops dominating.

  xmom_R_H_k    every H days, rank coins by trailing R-day return, hold the
                top k equal-weight, cash otherwise      [Jegadeesh & Titman 1993,
                cross-sectional / relative momentum - the most replicated anomaly]
  xrev_H_k      every H days, hold the WORST k of the last H days
                              [Lehmann 1990 / short-term reversal]
  xmom_regime   xmom but only held while >50% of the basket is above its
                own 50-day SMA (ride relative strength only in an up market)

Benchmark = own the whole eligible basket, equal-weight, rebalanced on the
same cadence, same cost. A strategy only "works" if it beats that on
return, or matches it with a materially smaller drawdown, in BOTH the
in-sample and out-of-sample halves of the shared date range.

Data: the daily OHLC caches shared with the other backtests (timestamps
included). Cost: 0.35%/side, charged on turnover at each rebalance.

    python xsectional_backtest.py
    python xsectional_backtest.py --split 0.7
"""

import argparse
import datetime as dt
import statistics

from candle_strats_backtest import DEFAULT, fetch_ohlc

SIDE_FEE = 0.0035


def _iso(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).date().isoformat()


def load_universe(syms):
    """{sym: {date_iso: close}}  and the sorted master date list."""
    px, closes_list = {}, {}
    for s in syms:
        bars = fetch_ohlc(s)
        if len(bars) < 300:
            continue
        d = {_iso(b[0]): b[4] for b in bars}
        px[s] = d
    dates = sorted(set().union(*[set(d) for d in px.values()]))
    return px, dates


def ret(px, s, d0, d1):
    a, b = px[s].get(d0), px[s].get(d1)
    if a and b and a > 0:
        return b / a - 1
    return None


def sma_ok(px, s, dates, di, n=50):
    """close at dates[di] above its own trailing n-day mean."""
    s_map = px[s]
    vals = [s_map[dates[k]] for k in range(max(0, di - n), di) if dates[k] in s_map]
    here = s_map.get(dates[di])
    return here is not None and len(vals) >= n // 2 and here > statistics.mean(vals)


def run(px, dates, lo, hi, rank_days, hold, k, worst=False, regime=False):
    """Equity curve over dates[lo:hi] rebalancing every `hold` steps."""
    eq, curve = 1.0, []
    held = set()
    i = lo
    while i < hi - 1:
        d0 = dates[i]
        j = min(i + hold, hi - 1)
        d1 = dates[j]
        # rank eligible names by trailing return
        elig = []
        if i - rank_days >= 0:
            dr = dates[i - rank_days]
            for s in px:
                r = ret(px, s, dr, d0)
                if r is None:
                    continue
                if regime and not sma_ok(px, s, dates, i):
                    continue
                elig.append((r, s))
        elig.sort(reverse=not worst)
        pick = {s for _, s in elig[:k]} if elig else set()

        if pick:
            fwd = [ret(px, s, d0, d1) for s in pick]
            fwd = [x for x in fwd if x is not None]
            gross = statistics.mean(fwd) if fwd else 0.0
        else:
            gross = 0.0
        turnover = len(pick ^ held) / max(len(pick | held), 1)
        cost = turnover * 2 * SIDE_FEE
        eq *= (1 + gross - cost)
        curve.append(eq)
        held = pick
        i = j
    return curve


def stats(curve, days):
    if len(curve) < 2:
        return 0.0, 0.0
    yrs = max(days / 365.25, 1e-9)
    cagr = curve[-1] ** (1 / yrs) - 1 if curve[-1] > 0 else -1.0
    peak, mdd = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    return cagr, mdd


def bench(px, dates, lo, hi, hold):
    return run(px, dates, lo, hi, rank_days=30, hold=hold, k=10_000)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--split", type=float, default=0.65)
    args = ap.parse_args()

    px, dates = load_universe([s.upper() for s in DEFAULT])
    n = len(dates)
    mid = int(n * args.split)
    span_in = (dt.date.fromisoformat(dates[mid - 1]) - dt.date.fromisoformat(dates[0])).days
    span_out = (dt.date.fromisoformat(dates[-1]) - dt.date.fromisoformat(dates[mid])).days
    print(f"{len(px)} coins | {n} aligned days "
          f"({dates[0]} -> {dates[-1]}) | in-sample first {args.split*100:.0f}%")
    print(f"cost {SIDE_FEE*100:g}%/side on turnover\n")

    configs = []
    for R in (30, 60, 90):
        for H in (7, 30):
            for k in (3, 5):
                configs.append((f"xmom R{R} H{H} k{k}", dict(rank_days=R, hold=H, k=k)))
    for k in (3, 5):
        configs.append((f"xrev H7 k{k}", dict(rank_days=7, hold=7, k=k, worst=True)))
    configs.append(("xmom R60 H30 k5 +regime", dict(rank_days=60, hold=30, k=5, regime=True)))

    for H in (7, 30):
        bc = bench(px, dates, 0, mid, H)
        bo = bench(px, dates, mid, n, H)
        bic, bid = stats(bc, span_in)
        boc, bod = stats(bo, span_out)
        print(f"BENCHMARK own-the-basket (H{H}):  in  CAGR {bic*100:+.0f}%  maxDD {bid*100:+.0f}%"
              f"   |  out  CAGR {boc*100:+.0f}%  maxDD {bod*100:+.0f}%")
    print()

    print(f"{'strategy':<26} {'IN cagr':>8} {'IN dd':>7} {'OUT cagr':>9} {'OUT dd':>7}  verdict")
    print("-" * 88)
    for name, kw in configs:
        H = kw["hold"]
        b_in = stats(bench(px, dates, 0, mid, H), span_in)
        b_out = stats(bench(px, dates, mid, n, H), span_out)
        ci = run(px, dates, 0, mid, **kw)
        co = run(px, dates, mid, n, **kw)
        ic, idd = stats(ci, span_in)
        oc, odd = stats(co, span_out)
        beat_in = ic > b_in[0] or (idd > b_in[1] + 0.10 and ic > b_in[0] - 0.05)
        beat_out = oc > b_out[0] or (odd > b_out[1] + 0.10 and oc > b_out[0] - 0.05)
        v = ("PASSES both halves" if beat_in and beat_out else
             "in-sample only" if beat_in else
             "out-sample only" if beat_out else "no edge")
        print(f"{name:<26} {ic*100:>+7.0f}% {idd*100:>+6.0f}% {oc*100:>+8.0f}% {odd*100:>+6.0f}%  {v}")

    print("\n" + "-" * 88)
    print("PASSES = beat own-the-basket on CAGR (or matched it with >10pt less drawdown) in")
    print("BOTH halves. Descriptive of the past only. Not a prediction, not advice.")


if __name__ == "__main__":
    main()
