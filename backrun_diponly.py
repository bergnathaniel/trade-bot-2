"""Quick backrun: apply the dip-only filter (chg5m<-5 AND chg1h<-10) to the
archived pre-test trades, walk a $20 bankroll, report. Exit P&L is whatever
the log recorded (old ~1.08x take-profit); the tighter TP can't be re-priced
from the log, so read this as the dip-FILTER effect only."""
import csv, re, datetime, statistics

SRC = "dry_run_log.PRE_DIPTEST.csv"
buys, trades = {}, []
for r in csv.DictReader(open(SRC)):
    if r["event"] == "BUY":
        buys[r["mint"]] = r["timestamp"]
    elif r["event"] == "SELL" and r["mint"] in buys:
        bt = buys.pop(r["mint"])
        m = {k: float(v) for k, v in re.findall(r"(\w+)=(-?\d+\.?\d*)", r["reason"])}
        try: pnl = float(r["pnl_usd"])
        except ValueError: continue
        if "chg5m" in m and "chg1h" in m:
            trades.append((r["timestamp"], m["chg5m"], m["chg1h"], pnl,
                           "take_profit" in r["reason"]))

dip = [t for t in trades if t[1] < -5 and t[2] < -10]
allp = [t[3] for t in trades]
dipp = [t[3] for t in dip]

def walk(ts, label):
    bal, low, peak = 20.0, 20.0, 20.0
    for _, _, _, pnl, _ in ts:
        bal += pnl; low = min(low, bal); peak = max(peak, bal)
    return bal, low, peak

t0 = datetime.datetime.strptime(trades[0][0], "%Y-%m-%d %H:%M:%S")
t1 = datetime.datetime.strptime(trades[-1][0], "%Y-%m-%d %H:%M:%S")
days = (t1 - t0).total_seconds() / 86400

print(f"archived window: {days:.2f} days\n")
for label, ts in (("ALL trades (old strategy)", trades), ("DIP-ONLY subset", dip)):
    p = [x[3] for x in ts]
    if not p:
        print(f"{label}: no trades"); continue
    bal, low, peak = walk(ts, label)
    wr = sum(1 for x in p if x > 0) / len(p) * 100
    tp = sum(1 for x in ts if x[4])
    print(f"{label}")
    print(f"  trades: {len(ts)}  ({len(ts)/days:.0f}/day)   win {wr:.0f}%   "
          f"take_profits {tp}")
    print(f"  $20 -> ${bal:.2f}   P&L ${bal-20:+.2f} ({(bal-20)/20*100:+.0f}%)")
    print(f"  low ${low:.2f}  peak ${peak:.2f}")
    print(f"  per day ${(bal-20)/days:+.2f}   -> 3 days ~${20+(bal-20)/days*3:.2f}\n")

print("Caveat: this is the SAME data the dip effect was spotted in — in-sample.")
print("The live forward test (fresh dry_run_log.csv) is the real check.")
