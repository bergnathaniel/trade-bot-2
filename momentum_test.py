"""
"Only buy the ones that are already going up" — tested on real dry_run_log.csv.

Buckets every trade by its price momentum AT ENTRY (chg5m / chg1h, logged in
the SELL reason) and shows realized P&L per bucket. If "target the ones
pumping" worked, the up-momentum buckets would be clearly profitable.
"""
import csv, re, statistics

buys = {}
trades = []
for r in csv.DictReader(open("dry_run_log.csv")):
    if r["event"] == "BUY":
        buys[r["mint"]] = float(r["size_usd"])
    elif r["event"] == "SELL" and r["mint"] in buys:
        entry = buys.pop(r["mint"])
        m = {k: float(v) for k, v in re.findall(r"(\w+)=(-?\d+\.?\d*)", r["reason"])}
        try:
            pnl = float(r["pnl_usd"])
        except ValueError:
            continue
        if "chg5m" in m and "chg1h" in m:
            trades.append((m["chg5m"], m["chg1h"], pnl, pnl / entry * 100))

def show(label, rows):
    if not rows:
        print(f"  {label:<26} (no trades)"); return
    p = [x[2] for x in rows]
    r = [x[3] for x in rows]
    wr = sum(1 for x in p if x > 0) / len(p) * 100
    print(f"  {label:<26} n={len(rows):<4} P&L ${sum(p):+7.2f}   "
          f"avg {statistics.mean(r):+5.1f}%/trade   win {wr:.0f}%")

print(f"{len(trades)} paired trades\n")
print("By 5-minute momentum at entry:")
show("dumping   (chg5m < -5)",  [t for t in trades if t[0] < -5])
show("flat      (-5..+2)",      [t for t in trades if -5 <= t[0] <= 2])
show("rising    (+2..+8)",      [t for t in trades if 2 < t[0] <= 8])
show("pumping   (chg5m > +8)",  [t for t in trades if t[0] > 8])
print("\nBy 1-hour momentum at entry:")
show("down      (chg1h < -10)", [t for t in trades if t[1] < -10])
show("flat      (-10..+5)",     [t for t in trades if -10 <= t[1] <= 5])
show("up        (+5..+25)",     [t for t in trades if 5 < t[1] <= 25])
show("strong up (chg1h > +25)", [t for t in trades if t[1] > 25])
print("\nBoth rising (chg5m>0 AND chg1h>0):")
show("  up on both timeframes",  [t for t in trades if t[0] > 0 and t[1] > 0])
show("  up5m but down1h",        [t for t in trades if t[0] > 0 and t[1] <= 0])

allp = [t[2] for t in trades]
print(f"\nWhole set: ${sum(allp):+.2f} over {len(trades)} trades "
      f"(avg {statistics.mean([t[3] for t in trades]):+.1f}%/trade)")
print("\nIf any 'going up' bucket were reliably green, that'd be the strategy.\n"
      "Check whether it is — and whether it holds across BOTH days in the log,\n"
      "or just got lucky in one.")
