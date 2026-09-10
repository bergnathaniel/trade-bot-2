"""
The study: does diversified time-series momentum survive an honest test?
=======================================================================

Asks the questions the earlier backtests in this project could not ask,
because they were all single-instrument long/flat tests judged against buy &
hold of that same instrument:

  1. Standalone, net of costs, how does a diversified trend portfolio look?
  2. What is its correlation to equities, and how did it behave in 2008 /
     2020 / 2022 - the periods a diversifier has to earn its keep?
  3. Does ADDING it to an equity or 60/40 portfolio improve that portfolio?
     (This is the real question. Trend has never beaten the S&P outright.)
  4. Is the result stable across sub-periods, or one lucky decade?
  5. After pricing in how many configurations were tried, is the Sharpe
     distinguishable from the luckiest of that many coin flips?

Nothing here is fitted. Lookbacks are the published 21/63/252. The parameter
grid at the end exists only to MEASURE dispersion for the deflated Sharpe -
the headline number is always the untouched base configuration.

    python research/run_study.py            # ETFs (tradeable)
    python research/run_study.py fut        # futures (longer history)
    python research/run_study.py etf --long-only
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import data
import stats
import tsmom

BAR = "=" * 92


def eval_window(res, min_active):
    """First index at which enough markets are live for the test to be fair."""
    for i, k in enumerate(res["nactive"]):
        if k >= min_active and i >= res["warm"]:
            return i
    return res["warm"]


def sub(series, a, b=None):
    return series[a:b] if b else series[a:]


def crisis_table(dates, curves, windows):
    print(f"\n{'window':<26}" + "".join(f"{n:>16}" for n in curves))
    print("-" * (26 + 16 * len(curves)))
    for label, lo, hi in windows:
        idx = [i for i, d in enumerate(dates) if lo <= d <= hi]
        if len(idx) < 20:
            continue
        cells = []
        for name in curves:
            seg = curves[name][idx[0]:idx[-1] + 1]
            eq = 1.0
            for r in seg:
                eq *= (1 + r)
            cells.append(f"{(eq-1)*100:>+14.1f}% ")
        print(f"{label:<26}" + "".join(cells))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("universe", nargs="?", default="etf", choices=["etf", "fut", "all"])
    ap.add_argument("--long-only", action="store_true",
                    help="no shorting, gross capped at 1.0 (cash brokerage account)")
    ap.add_argument("--target-vol", type=float, default=0.10)
    ap.add_argument("--cost", type=float, default=0.0005, help="cost per side, fraction")
    ap.add_argument("--rebal", type=int, default=21)
    ap.add_argument("--no-leverage", action="store_true",
                    help="forbid the vol scaler from levering above 1.0x capital")
    args = ap.parse_args()

    uni = {"etf": data.ETF_UNIVERSE, "fut": data.FUT_UNIVERSE,
           "all": {**data.ETF_UNIVERSE, **data.FUT_UNIVERSE}}[args.universe]

    print(BAR)
    print(f"DIVERSIFIED TIME-SERIES MOMENTUM - honest evaluation  [{args.universe} universe]")
    print(BAR)
    series = data.load_universe_clean(uni, quiet=False)
    # benchmarks always come from the clean ETF series
    bench_src = data.load_universe_clean({"SPY": None, "IEF": None}, quiet=True) \
        if args.universe == "fut" else {}
    dates, by = data.align({**series, **bench_src})

    rf = data.risk_free_daily(dates)
    kw = dict(target_vol=args.target_vol, rebal=args.rebal, cost_per_side=args.cost, rf=rf)
    if args.long_only:
        kw.update(long_only=True, max_gross=1.0)
    if args.no_leverage:
        kw.update(max_scalar=1.0)

    kw["trade_syms"] = list(series)          # never trade the benchmark series
    res = tsmom.run(dates, by, **kw)
    min_active = max(6, int(0.6 * len(series)))
    a = eval_window(res, min_active)
    d = res["dates"][a:]
    trend = res["scaled"][a:]

    trend_tot = res["total"][a:]
    rf_slice = res["rf"][a:]
    spy = tsmom.benchmark(dates, by, "SPY", rf)[a:]
    ief = tsmom.benchmark(dates, by, "IEF", rf)[a:]
    p6040 = tsmom.blend(spy, ief, 0.6) if ief else spy

    print(f"\nwindow {d[0]} -> {d[-1]}  ({len(d)} trading days, {len(d)/252:.1f} years)")
    eg = res["eff_gross"][a:]
    eg_sorted = sorted(eg)
    print(f"markets: {len(res['syms'])}   annual turnover {res['ann_turnover']:.1f}x   "
          f"cost {args.cost*1e4:.0f}bp/side   rebalance every {args.rebal}d"
          + ("   LONG-ONLY" if args.long_only else "   long/short")
          + ("   NO LEVERAGE" if args.no_leverage else ""))
    print(f"effective gross exposure: mean {stats.mean(eg):.2f}x  median "
          f"{eg_sorted[len(eg_sorted)//2]:.2f}x  p95 {eg_sorted[int(0.95*len(eg_sorted))]:.2f}x  "
          f"max {max(eg):.2f}x")
    print(f"cash rate over window: {stats.mean(rf_slice)*252*100:.2f}%/yr average")
    print("\nALL Sharpe figures below are EXCESS of cash. 'CAGR' columns are excess")
    print("of cash too; total return adds the cash rate back on the capital base.")

    # ---------------------------------------------------------------- 1. standalone
    print(f"\n{BAR}\n1. STANDALONE (all net of costs)\n{BAR}")
    print(stats.HEADER)
    rows = [stats.summary(trend, "TSMOM diversified"),
            stats.summary(spy, "SPY buy & hold")]
    if ief:
        rows.append(stats.summary(p6040, "60/40 SPY/IEF"))
    for r in rows:
        print(stats.row(r))
    print(f"\n  total (not excess) CAGR:  TSMOM {stats.ann_return(trend_tot)*100:+.1f}%   "
          f"SPY {stats.ann_return([spy[i]+rf_slice[i] for i in range(len(spy))])*100:+.1f}%")

    # ---------------------------------------------------------------- 2. diversification
    print(f"\n{BAR}\n2. IS IT A DIVERSIFIER?\n{BAR}")
    c = stats.correlation(trend, spy)
    print(f"  correlation to SPY (daily): {c:+.3f}")
    down = [i for i, r in enumerate(spy) if r < -0.02]
    if down:
        avg_t = stats.mean([trend[i] for i in down])
        print(f"  SPY days worse than -2% ({len(down)} of them): "
              f"SPY avg {stats.mean([spy[i] for i in down])*100:+.2f}%, "
              f"trend avg {avg_t*100:+.2f}%")
    crisis_table(d, {"TSMOM": trend, "SPY": spy, "60/40": p6040}, [
        ("GFC 2007-10..2009-03", "2007-10-01", "2009-03-31"),
        ("Euro crisis 2011", "2011-05-01", "2011-10-31"),
        ("Q4 2018", "2018-10-01", "2018-12-31"),
        ("COVID crash 2020", "2020-02-15", "2020-03-31"),
        ("2022 stocks+bonds", "2022-01-01", "2022-10-31"),
        ("2011-2019 (trend's bad decade)", "2011-01-01", "2019-12-31"),
        ("2020-01..today", "2020-01-01", "2099-01-01"),
    ])

    # ---------------------------------------------------------------- 3. as an addition
    print(f"\n{BAR}\n3. DOES ADDING IT IMPROVE A REAL PORTFOLIO?\n{BAR}")
    print(stats.HEADER)
    print(stats.row(stats.summary(spy, "100% SPY")))
    for w in (0.10, 0.20, 0.30, 0.40):
        mix = tsmom.blend(trend, spy, w)
        print(stats.row(stats.summary(mix, f"{int(w*100)}% trend / {100-int(w*100)}% SPY")))
    if ief:
        print()
        print(stats.row(stats.summary(p6040, "60/40 baseline")))
        for w in (0.10, 0.20, 0.30):
            mix = tsmom.blend(trend, p6040, w)
            print(stats.row(stats.summary(mix, f"{int(w*100)}% trend / {100-int(w*100)}% 60-40")))

    # ---------------------------------------------------------------- 4. stability
    print(f"\n{BAR}\n4. SUB-PERIOD STABILITY (is it one lucky decade?)\n{BAR}")
    print(f"{'period':<14} {'TSMOM CAGR':>11} {'TSMOM SR':>9} {'SPY CAGR':>9} {'SPY SR':>8}")
    print("-" * 56)
    years = sorted({x[:4] for x in d})
    for i in range(0, len(years), 3):
        blk = years[i:i + 3]
        idx = [j for j, x in enumerate(d) if x[:4] in blk]
        if len(idx) < 250:
            continue
        t, s_ = trend[idx[0]:idx[-1] + 1], spy[idx[0]:idx[-1] + 1]
        print(f"{blk[0]}-{blk[-1]:<9} {stats.ann_return(t)*100:>+10.1f}% "
              f"{stats.sharpe(t):>9.2f} {stats.ann_return(s_)*100:>+8.1f}% "
              f"{stats.sharpe(s_):>8.2f}")

    # ---------------------------------------------------------------- 5. deflated Sharpe
    print(f"\n{BAR}\n5. PRICING IN HOW HARD WE LOOKED\n{BAR}")
    grid, srs = [], []
    for lbs in [(21, 63, 252), (21, 63, 126), (63, 126, 252), (10, 40, 120),
                (42, 126, 252), (252,), (63,), (21,), (126, 252), (5, 21, 63)]:
        for rb in (5, 21, 63):
            for iv in (0.10, 0.20, 0.40):
                r2 = tsmom.run(dates, by, lookbacks=lbs, rebal=rb, inst_vol_target=iv,
                               target_vol=args.target_vol, cost_per_side=args.cost,
                               rf=rf, trade_syms=list(series),
                               **({"long_only": True, "max_gross": 1.0} if args.long_only else {}))
                s2 = r2["scaled"][a:]
                if len(s2) > 500:
                    sr = stats.sharpe(s2)
                    grid.append((lbs, rb, iv, sr))
                    srs.append(sr)
    n_trials = len(grid)
    disp = stats.stdev(srs)
    base_sr = stats.sharpe(trend)
    print(f"  configurations actually run here: {n_trials}   "
          f"Sharpe dispersion across them: {disp:.3f}")
    print(f"  grid Sharpe: min {min(srs):.2f}  median {sorted(srs)[len(srs)//2]:.2f}  "
          f"max {max(srs):.2f}   |   base config: {base_sr:.2f}")
    print(f"  base config's rank in the grid: "
          f"{sum(1 for s_ in srs if s_ > base_sr)+1} of {n_trials} "
          f"(low rank = we did NOT pick the winner)")
    print(f"\n  {'trials assumed':>16} {'luck bar (SR)':>14} {'DSR':>8}   interpretation")
    print("  " + "-" * 74)
    for nt in (n_trials, 50, 200, 1000):
        dsr, bar = stats.deflated_sharpe(trend, nt, disp)
        verdict = ("survives" if dsr > 0.95 else
                   "marginal" if dsr > 0.80 else "not distinguishable from luck")
        print(f"  {nt:>16} {bar:>14.2f} {dsr:>8.3f}   {verdict}")
    mtrl = stats.min_track_record_length(trend, stats.expected_max_sr(n_trials, disp), 0.95)
    print(f"\n  PSR vs zero: {stats.psr(trend):.3f}")
    print(f"  days of track record needed to clear the {n_trials}-trial luck bar at 95%: "
          + (f"{mtrl:,.0f} ({mtrl/252:.1f}y) - have {len(trend):,} ({len(trend)/252:.1f}y)"
             if mtrl != float('inf') else "never at this Sharpe"))

    # ------------------------------------------- 6. post-publication decay
    print(f"\n{BAR}\n6. DID IT DECAY AFTER PUBLICATION?\n{BAR}")
    print("  Moskowitz-Ooi-Pedersen published the 21/63/252 construction in 2012 on")
    print("  1985-2009 data. Everything from 2012 on is therefore genuinely out of")
    print("  sample for these exact parameters - the cleanest test available.\n")
    print(f"  {'era':<18} {'yrs':>5} {'trend SR':>9} {'trend CAGR':>11} {'SPY SR':>8}   "
          f"{'best blend gain vs 60/40':>26}")
    print("  " + "-" * 84)
    for lbl, lo, hi in [("pre-pub  ..2011", "0000", "2011-12-31"),
                        ("post-pub 2012..", "2012-01-01", "9999")]:
        idx = [i for i, x in enumerate(d) if lo <= x <= hi]
        if len(idx) < 250:
            continue
        t = trend[idx[0]:idx[-1] + 1]
        sp = spy[idx[0]:idx[-1] + 1]
        base = p6040[idx[0]:idx[-1] + 1]
        gains = [(w, stats.sharpe(tsmom.blend(t, base, w)) - stats.sharpe(base))
                 for w in (0.1, 0.2, 0.3, 0.4)]
        bw, bg = max(gains, key=lambda x: x[1])
        print(f"  {lbl:<18} {len(t)/252:>4.1f}y {stats.sharpe(t):>9.2f} "
              f"{stats.ann_return(t)*100:>+10.1f}% {stats.sharpe(sp):>8.2f}   "
              f"{f'+{bg:.2f} SR at {int(bw*100)}% weight':>26}")
    print("\n  A benefit that is large before publication and ~zero after it is the")
    print("  signature of an effect that was arbitraged away, or was never there.")

    # ---------------------------------------------------------------- verdict
    print(f"\n{BAR}\nVERDICT\n{BAR}")
    sr_t, sr_s = stats.sharpe(trend), stats.sharpe(spy)
    best_mix = max(((w, stats.sharpe(tsmom.blend(trend, spy, w)))
                    for w in (0.0, 0.1, 0.2, 0.3, 0.4)), key=lambda x: x[1])
    dsr_main, _ = stats.deflated_sharpe(trend, max(n_trials, 200), disp)
    beats_alone = sr_t > sr_s
    helps_mix = best_mix[0] > 0 and best_mix[1] > sr_s + 0.05
    lowcorr = abs(c) < 0.3
    stands_alone = beats_alone and dsr_main > 0.90
    print(f"  standalone Sharpe {sr_t:.2f} vs SPY {sr_s:.2f}  -> "
          f"{'beats' if beats_alone else 'LOSES to'} equities alone")
    print(f"  correlation {c:+.2f} -> {'genuinely uncorrelated' if lowcorr else 'NOT independent'}")
    print(f"  best blend: {int(best_mix[0]*100)}% trend, Sharpe {best_mix[1]:.2f} "
          f"({'improves' if helps_mix else 'does NOT meaningfully improve'} on 100% SPY)")
    print(f"  deflated Sharpe (>=200 trials assumed): {dsr_main:.3f}")
    print()
    if stands_alone:
        print("  CLEARS THE BAR STANDALONE. Beats equities on risk-adjusted terms AND")
        print("  survives the multiple-testing correction. Rare - re-check the cost and")
        print("  financing assumptions before believing it.")
    elif helps_mix and lowcorr:
        print("  USEFUL AS A DIVERSIFIER, NOT AS A RETURN ENGINE. It does not beat stocks")
        print("  and is not supposed to; it earns its keep by being uncorrelated and by")
        print("  paying during equity crises. The standalone Sharpe does NOT clear the")
        print("  multiple-testing bar, so any claim rests on the diversification, which is")
        print("  a structural property (not a fitted one) - and on it continuing to hold.")
        print("  A modest sleeve beside index holdings is the defensible use. As a")
        print("  standalone money-maker it is not.")
    elif helps_mix:
        print("  MARGINAL. Blending helps a little, but correlation is high enough that")
        print("  most of the benefit is just holding less equity risk - which you can get")
        print("  for free by holding less equity.")
    else:
        print("  DOES NOT HOLD UP on this universe/window. Do not build it.")
    print("\n  Descriptive of the past only. Not a prediction, not investment advice.")


if __name__ == "__main__":
    main()
