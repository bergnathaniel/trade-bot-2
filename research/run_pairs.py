"""
Pairs trading, tested with the same honesty as everything else in research/.

    python3 research/run_pairs.py
    python3 research/run_pairs.py --n-pairs 5 --entry-sd 1.5
"""
import argparse, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data, stats, tsmom, pairs

BAR = "=" * 92

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-pairs", type=int, default=20)
    ap.add_argument("--entry-sd", type=float, default=2.0)
    ap.add_argument("--cost", type=float, default=0.0005)
    ap.add_argument("--borrow", type=float, default=0.003)
    a = ap.parse_args()

    print(BAR); print("PAIRS TRADING - Gatev/Goetzmann/Rouwenhorst distance method"); print(BAR)
    uni = {k: v for k, v in data.STOCK_UNIVERSE.items() if k.isupper()}
    series = {}
    for s in uni:
        b = data.fetch(s, quiet=True)
        if len(b) >= 3000:
            series[s] = b
    print(f"universe: {len(series)} US large caps")
    dates, by = data.align(series)
    panel = tsmom.build_panel(dates, by)
    syms = sorted(panel)
    rf = data.risk_free_daily(dates)

    r = pairs.run(dates, panel, syms, n_pairs=a.n_pairs, entry_sd=a.entry_sd,
                  cost_per_side=a.cost, borrow_annual=a.borrow)
    d = r["dates"]
    print(f"window {d[0]} -> {d[-1]}  ({len(d)} days, {len(d)/252:.1f}y)  "
          f"{r['windows']} formation/trading cycles")
    print(f"top {a.n_pairs} pairs per cycle, entry at {a.entry_sd} SD, "
          f"{r['trades']} trades ({r['trades_per_window']:.0f}/cycle), "
          f"cost {a.cost*1e4:.0f}bp/leg + {a.borrow*100:.1f}%/yr borrow\n")

    spy = tsmom.benchmark(dates, by, "SPY", rf)
    # align SPY to the traded window
    off = dates.index(d[0]) - 1
    spy = spy[off:off + len(d)]

    print(stats.HEADER)
    for label, ser in (("Pairs (committed capital)", r["committed"]),
                       ("Pairs (fully invested)", r["invested"])):
        print(stats.row(stats.summary(ser, label)))
    if spy:
        print(stats.row(stats.summary(spy, "SPY buy & hold")))

    print(f"\n  correlation to SPY: {stats.correlation(r['committed'], spy):+.3f}")

    # sub-periods: has it decayed? Gatev's sample ended 2002.
    print(f"\n{BAR}\nHAS IT DECAYED? (Gatev's published sample ends 2002)\n{BAR}")
    print(f"  {'era':<22} {'yrs':>5} {'CAGR':>8} {'Sharpe':>8} {'maxDD':>7}")
    print("  " + "-" * 54)
    for lbl, lo, hi in [("in Gatev's sample", "0000", "2002-12-31"),
                        ("2003-2009", "2003-01-01", "2009-12-31"),
                        ("2010-2017", "2010-01-01", "2017-12-31"),
                        ("2018-today", "2018-01-01", "9999")]:
        idx = [i for i, x in enumerate(d) if lo <= x <= hi]
        if len(idx) < 250: continue
        seg = r["committed"][idx[0]:idx[-1] + 1]
        print(f"  {lbl:<22} {len(seg)/252:>4.1f}y {stats.ann_return(seg)*100:>+7.1f}% "
              f"{stats.sharpe(seg):>8.2f} {stats.max_drawdown(seg)*100:>+6.0f}%")

    # multiple testing
    print(f"\n{BAR}\nPRICING IN THE SEARCH\n{BAR}")
    srs, grid = [], []
    for npr in (5, 10, 20, 40):
        for esd in (1.0, 1.5, 2.0, 2.5):
            g = pairs.run(dates, panel, syms, n_pairs=npr, entry_sd=esd,
                          cost_per_side=a.cost, borrow_annual=a.borrow)
            sr = stats.sharpe(g["committed"]); srs.append(sr); grid.append((npr, esd, sr))
    disp = stats.stdev(srs); base = stats.sharpe(r["committed"])
    print(f"  {len(grid)} configs | Sharpe min {min(srs):.2f} median "
          f"{sorted(srs)[len(srs)//2]:.2f} max {max(srs):.2f} | dispersion {disp:.3f}")
    print(f"  base config Sharpe {base:.2f}, rank {sum(1 for x in srs if x > base)+1} of {len(grid)}")
    print(f"\n  {'trials':>8} {'luck bar':>10} {'DSR':>8}")
    for nt in (len(grid), 50, 200):
        dsr, bar = stats.deflated_sharpe(r["committed"], nt, disp)
        print(f"  {nt:>8} {bar:>10.2f} {dsr:>8.3f}   "
              f"{'survives' if dsr > 0.95 else 'not distinguishable from luck'}")
    print("\n  NOTE: the universe is 106 stocks that still exist in 2026. Survivorship")
    print("  bias FLATTERS pairs trading - a pair where one leg went bankrupt never")
    print("  converges, and those legs are absent here. Treat this as an upper bound.")
    print("\n  Descriptive of the past only. Not investment advice.")

if __name__ == "__main__":
    main()
