"""
Six published equity anomalies, tested on US large caps with the honest harness.

    python3 research/run_anomalies.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data, stats, tsmom, anomalies

BAR = "=" * 100

def era(d, ser, lo, hi):
    idx = [i for i, x in enumerate(d) if lo <= x <= hi]
    if len(idx) < 250: return None
    return ser[idx[0]:idx[-1] + 1]

def main():
    print(BAR); print("CROSS-SECTIONAL EQUITY ANOMALIES - long/short deciles, US large caps"); print(BAR)
    uni = {k: v for k, v in data.STOCK_UNIVERSE.items() if k.isupper()}
    series = {s: b for s in uni if len(b := data.fetch(s, quiet=True)) >= 3000}
    dates, by = data.align(series)
    panel = tsmom.build_panel(dates, by)
    syms = sorted(panel)
    rets = {s: tsmom.to_returns(panel[s]) for s in syms}
    rf = data.risk_free_daily(dates)
    spy_bars = data.fetch("SPY", quiet=True)
    spyd = {data._ymd(b[0]): b[4] for b in spy_bars}
    spycol = [spyd.get(d) for d in dates]
    mkt = tsmom.to_returns(spycol)
    spy_ex = [(mkt[i] if mkt[i] is not None else 0.0) - rf.get(dates[i], 0.0)
              for i in range(1, len(dates))]

    # CONTROL: equal-weight every stock in the universe. Any long-only "anomaly"
    # portfolio must beat THIS, not the cap-weighted index - otherwise the result
    # is just equal-weighting a set of survivors, which is not a strategy.
    ew = []
    for i in range(len(dates) - 1):
        live = [s for s in syms if panel[s][i] is not None and rets[s][i + 1] is not None]
        r = sum(rets[s][i + 1] for s in live) / len(live) if live else 0.0
        ew.append(r - rf.get(dates[i + 1], 0.0) - (0.00005 if i % 21 == 0 else 0.0))

    print(f"universe {len(syms)} stocks | {dates[0]} -> {dates[-1]} "
          f"({len(dates)/252:.1f}y) | top/bottom 20% | monthly rebalance | 5bp/side\n")

    print(f"{'signal':<11} {'turn':>5} | {'--- LONG/SHORT (dollar-neutral) ---':^38} | {'-- LONG-ONLY, excess of cash --':^30}")
    print(f"{'':<11} {'x/yr':>5} | {'CAGR':>7} {'vol':>6} {'SR':>6} {'maxDD':>7} {'corr':>6} | {'CAGR':>7} {'vol':>6} {'SR':>6} {'maxDD':>6}")
    print("-" * 100)
    results = {}
    for sig in anomalies.SIGNALS:
        r = anomalies.run(dates, panel, syms, rets, mkt, sig, rf=rf)
        results[sig] = r
        ls, lo, d = r["ls"], r["long_only"], r["dates"]
        n = min(len(ls), len(spy_ex))
        print(f"{sig:<11} {r['ann_turnover']:>5.1f} | "
              f"{stats.ann_return(ls)*100:>+6.1f}% {stats.ann_vol(ls)*100:>5.1f}% "
              f"{stats.sharpe(ls):>6.2f} {stats.max_drawdown(ls)*100:>+6.0f}% "
              f"{stats.correlation(ls[-n:], spy_ex[-n:]):>+6.2f} | "
              f"{stats.ann_return(lo)*100:>+6.1f}% {stats.ann_vol(lo)*100:>5.1f}% "
              f"{stats.sharpe(lo):>6.2f} {stats.max_drawdown(lo)*100:>+5.0f}%")
    print("-" * 100)
    print(f"{'SPY B&H':<11} {'--':>5} | {'':>38} | {stats.ann_return(spy_ex)*100:>+6.1f}% "
          f"{stats.ann_vol(spy_ex)*100:>5.1f}% {stats.sharpe(spy_ex):>6.2f} "
          f"{stats.max_drawdown(spy_ex)*100:>+5.0f}%")
    print(f"{'EW CONTROL':<11} {'--':>5} | {'':>38} | {stats.ann_return(ew)*100:>+6.1f}% "
          f"{stats.ann_vol(ew)*100:>5.1f}% {stats.sharpe(ew):>6.2f} "
          f"{stats.max_drawdown(ew)*100:>+5.0f}%   <-- the bar to beat")

    print(f"\n{BAR}\nTHE CONTROL: does the SIGNAL add anything, or is it just equal-weighting?\n{BAR}")
    ew_sr = stats.sharpe(ew)
    print(f"  Equal-weighting all {len(syms)} stocks scores {ew_sr:.2f} with no signal at all.")
    print(f"  A long-only anomaly portfolio has to beat THAT, not SPY's {stats.sharpe(spy_ex):.2f}.\n")
    print(f"  {'signal':<12} {'long-only SR':>13} {'vs EW control':>15}")
    print("  " + "-" * 42)
    beat = 0
    for sig, r in results.items():
        sr = stats.sharpe(r["long_only"]); d_ = sr - ew_sr
        if d_ > 0.05: beat += 1
        print(f"  {sig:<12} {sr:>13.2f} {d_:>+15.2f}")
    print(f"\n  signals beating the no-signal control by >0.05 Sharpe: {beat} of {len(results)}")

    print(f"\n{BAR}\nDECAY BY ERA (long/short Sharpe)\n{BAR}")
    eras = [("1994-2002", "0000", "2002-12-31"), ("2003-2009", "2003-01-01", "2009-12-31"),
            ("2010-2017", "2010-01-01", "2017-12-31"), ("2018-2026", "2018-01-01", "9999")]
    print(f"{'signal':<11}" + "".join(f"{e[0]:>12}" for e in eras))
    print("-" * (11 + 12 * len(eras)))
    for sig, r in results.items():
        cells = []
        for _, lo_, hi_ in eras:
            seg = era(r["dates"], r["ls"], lo_, hi_)
            cells.append(f"{stats.sharpe(seg):>12.2f}" if seg else f"{'-':>12}")
        print(f"{sig:<11}" + "".join(cells))

    print(f"\n{BAR}\nMULTIPLE TESTING\n{BAR}")
    srs = [stats.sharpe(r["ls"]) for r in results.values()]
    disp = stats.stdev(srs)
    best = max(results, key=lambda k: stats.sharpe(results[k]["ls"]))
    bser = results[best]["ls"]
    print(f"  6 signals tried, Sharpe dispersion {disp:.3f}. Best = {best} "
          f"(SR {stats.sharpe(bser):.2f}).")
    for nt in (6, 50, 200):
        dsr, bar = stats.deflated_sharpe(bser, nt, disp)
        print(f"    vs {nt:>4} trials: luck bar {bar:.2f}, DSR {dsr:.3f}  "
              f"{'survives' if dsr > 0.95 else 'not distinguishable from luck'}")
    print("\n  Survivorship bias: all 106 names still exist in 2026. That flatters")
    print("  momentum and low-vol (no bankruptcies in the short book). Upper bound.")
    print("  Descriptive of the past only. Not investment advice.")

if __name__ == "__main__":
    main()
