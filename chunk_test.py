"""Split the archived pre-test trades into time chunks and apply the FIXED
dip-only rule (chg5m<-5 AND chg1h<-10) to each. If dip-only is green in
every chunk it's more likely real; if it's green overall only because of one
lucky hour, this exposes it."""
import csv, re, datetime, statistics

SRC = "dry_run_log.PRE_DIPTEST.csv"
buys, trades = {}, []
for r in csv.DictReader(open(SRC)):
    if r["event"] == "BUY":
        buys[r["mint"]] = 1
    elif r["event"] == "SELL" and r["mint"] in buys:
        buys.pop(r["mint"])
        m = {k: float(v) for k, v in re.findall(r"(\w+)=(-?\d+\.?\d*)", r["reason"])}
        try: pnl = float(r["pnl_usd"])
        except ValueError: continue
        if "chg5m" in m and "chg1h" in m:
            ts = datetime.datetime.strptime(r["timestamp"], "%Y-%m-%d %H:%M:%S")
            trades.append((ts, m["chg5m"], m["chg1h"], pnl))

NCHUNKS = 6
t0, t1 = trades[0][0], trades[-1][0]
span = (t1 - t0).total_seconds()
def is_dip(c5, c1): return c5 < -5 and c1 < -10 and c5 > -60 and c1 > -70

print(f"archived: {len(trades)} trades over {span/3600:.1f}h, split into {NCHUNKS}\n")
print(f"{'chunk (time)':<22} | {'all trades':>18} | {'DIP-ONLY':>20}")
print("-" * 66)
tot_all = tot_dip = 0.0
for i in range(NCHUNKS):
    lo = t0 + datetime.timedelta(seconds=span * i / NCHUNKS)
    hi = t0 + datetime.timedelta(seconds=span * (i + 1) / NCHUNKS)
    ch = [t for t in trades if lo <= t[0] < hi] or [t for t in trades if lo <= t[0] <= hi and i == NCHUNKS-1]
    ap = [t[3] for t in ch]
    dp = [t[3] for t in ch if is_dip(t[1], t[2])]
    tot_all += sum(ap); tot_dip += sum(dp)
    aw = f"n={len(ap):<3} ${sum(ap):+6.2f}"
    dw = f"n={len(dp):<3} ${sum(dp):+6.2f}" if dp else "n=0   —"
    flag = "" if not dp else ("  <-- red" if sum(dp) <= 0 else "  green")
    print(f"{lo:%m-%d %H:%M}-{hi:%H:%M}      | {aw:>18} | {dw:>15}{flag}")
print("-" * 66)
print(f"{'TOTAL':<22} | {'$%+.2f'%tot_all:>18} | {'$%+.2f'%tot_dip:>20}")
print()
greens = 0
for i in range(NCHUNKS):
    lo = t0 + datetime.timedelta(seconds=span * i / NCHUNKS)
    hi = t0 + datetime.timedelta(seconds=span * (i + 1) / NCHUNKS)
    dp = [t[3] for t in trades if lo <= t[0] <= hi and is_dip(t[1], t[2])]
    if dp and sum(dp) > 0: greens += 1
print(f"dip-only was profitable in {greens}/{NCHUNKS} time chunks.")
print("6/6 or 5/6 = worth watching the live test closely.")
print("3/6 or fewer = it's basically a coin flip / one lucky streak.")
