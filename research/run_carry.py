"""
Cash-and-carry basis trade on CME bitcoin futures vs spot.

Buy spot, short the front-month future, hold to settlement. Futures converge to
spot at expiry, so the return locked in at entry is exactly (F/S - 1), less
costs. One trade per contract month, rolled. The benchmark is T-bills, because
this is a market-neutral trade whose whole purpose is to beat cash.

    python3 research/run_carry.py
    python3 research/run_carry.py --entry-dte 20 --cost 0.002
"""
import argparse, sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import data, stats, funding

BAR = "=" * 88

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry-dte", type=int, default=28, help="days to expiry at entry")
    ap.add_argument("--exit-dte", type=int, default=2, help="unwind this many days before expiry")
    ap.add_argument("--cost", type=float, default=0.0015,
                    help="all-in round-trip cost per cycle (spot+futures, both legs, in+out)")
    a = ap.parse_args()

    print(BAR); print("CASH-AND-CARRY BASIS TRADE - CME bitcoin futures vs spot"); print(BAR)
    fut = data.fetch("BTC=F", quiet=True); spot = data.fetch("BTC-USD", quiet=True)
    f = {funding._ymd(b[0]*1000): b[4] for b in fut}
    s = {funding._ymd(b[0]*1000): b[4] for b in spot}
    days = sorted(set(f) & set(s))
    rf = data.risk_free_daily(days)

    # one trade per contract month: enter nearest to entry_dte, exit at exit_dte
    by_exp = collections.defaultdict(list)
    for d in days:
        dte = funding.days_to_expiry(d)
        by_exp[(d[:7] if dte > 0 else d[:7])].append((d, dte))

    trades = []
    for key in sorted(by_exp):
        rows = by_exp[key]
        entry = min((r for r in rows if r[1] >= a.exit_dte),
                    key=lambda r: abs(r[1] - a.entry_dte), default=None)
        if entry is None: continue
        ed, edte = entry
        if abs(edte - a.entry_dte) > 8: continue
        held = edte - a.exit_dte
        if held < 5: continue
        gross = f[ed] / s[ed] - 1                      # locked in at entry
        net = gross - a.cost
        # cash return over the same holding period, for a like-for-like comparison
        cash = sum(rf.get(d, 0.0) for d in days if ed <= d) and 0.0
        idx = days.index(ed)
        cash = sum(rf.get(days[k], 0.0) for k in range(idx, min(idx + held, len(days))))
        trades.append((ed, edte, held, gross, net, cash))

    if not trades:
        print("no trades"); return
    print(f"{len(trades)} monthly cycles, {trades[0][0]} -> {trades[-1][0]}")
    print(f"entry ~{a.entry_dte}d to expiry, unwind at {a.exit_dte}d, "
          f"all-in cost {a.cost*100:.2f}%/cycle\n")

    print(f"{'year':<6}{'cycles':>7}{'gross/cyc':>11}{'net/cyc':>10}{'net ann.':>10}"
          f"{'T-bill ann.':>12}{'beat cash?':>11}")
    print("-" * 68)
    byyr = collections.defaultdict(list)
    for t in trades: byyr[t[0][:4]].append(t)
    for y in sorted(byyr):
        ts = byyr[y]
        g = stats.mean([t[3] for t in ts]); n = stats.mean([t[4] for t in ts])
        hd = stats.mean([t[2] for t in ts])
        nann = n * 365 / hd; cann = stats.mean([t[5] for t in ts]) * 365 / hd
        print(f"{y:<6}{len(ts):>7}{g*100:>10.2f}%{n*100:>9.2f}%{nann*100:>9.1f}%"
              f"{cann*100:>11.1f}%{'  yes' if nann > cann else '   no':>11}")

    g = stats.mean([t[3] for t in trades]); n = stats.mean([t[4] for t in trades])
    hd = stats.mean([t[2] for t in trades])
    nann = n * 365 / hd; cann = stats.mean([t[5] for t in trades]) * 365 / hd
    print("-" * 68)
    print(f"{'ALL':<6}{len(trades):>7}{g*100:>10.2f}%{n*100:>9.2f}%{nann*100:>9.1f}%"
          f"{cann*100:>11.1f}%{'  yes' if nann > cann else '   no':>11}")

    wins = sum(1 for t in trades if t[4] > t[5])
    print(f"\n  cycles where the trade beat cash: {wins}/{len(trades)} ({wins/len(trades)*100:.0f}%)")
    print(f"  cycles with a negative net return: "
          f"{sum(1 for t in trades if t[4] < 0)}/{len(trades)}")

    # the modern era on its own - the 2017-19 backwardation is a different market
    mod = [t for t in trades if t[0] >= "2023-01-01"]
    if mod:
        n2 = stats.mean([t[4] for t in mod]); h2 = stats.mean([t[2] for t in mod])
        c2 = stats.mean([t[5] for t in mod]) * 365 / h2
        print(f"\n  2023-2026 only ({len(mod)} cycles): net {n2*365/h2*100:+.1f}%/yr "
              f"vs T-bills {c2*100:+.1f}%/yr  ->  "
              f"{'beats cash' if n2*365/h2 > c2 else 'LOSES to cash'}")

    print(f"\n{BAR}")
    print("  Cost note: 0.15%/cycle is optimistic - it assumes cheap spot execution")
    print("  and CME commissions. Retail spot fees alone (0.4%/side on Coinbase)")
    print("  would roughly triple it. Rerun with --cost to see.")
    print("  Not investment advice. US retail access to offshore perps is separate.")

if __name__ == "__main__":
    main()
