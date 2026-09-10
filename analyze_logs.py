"""Honest read of a bot's trade log: realized P&L, fees, win rate, streaks,
and P&L bucketed by exit reason and by day. No sugar-coating."""
import csv, sys, statistics
from collections import defaultdict, Counter

path = sys.argv[1] if len(sys.argv) > 1 else "dry_run_log.csv"
rows = list(csv.DictReader(open(path)))

def num(x):
    try: return float(x)
    except: return 0.0

buys  = [r for r in rows if r["event"] == "BUY"]
sells = [r for r in rows if r["event"] == "SELL"]
skips = [r for r in rows if r["event"] == "SKIP"]
errs  = [r for r in rows if r["event"] in ("ERROR", "HALT")]

pnls = [num(r["pnl_usd"]) for r in sells]
fees_on_sells = sum(num(r["fee_usd"]) for r in sells)
fees_on_buys  = sum(num(r["fee_usd"]) for r in buys)
total_fees = fees_on_sells + fees_on_buys
realized = sum(pnls)
wins = [p for p in pnls if p > 0]
losses = [p for p in pnls if p <= 0]

by_reason = defaultdict(list)
for r in sells:
    tag = r["reason"].split(" | ")[0].split(" ")[0]
    by_reason[tag].append(num(r["pnl_usd"]))

by_day = defaultdict(float)
for r in sells:
    by_day[r["timestamp"][:10]] += num(r["pnl_usd"])

# worst losing streak (consecutive losing sells)
streak = worst = 0
for p in pnls:
    streak = streak + 1 if p <= 0 else 0
    worst = max(worst, streak)

print(f"\n=== {path} ===")
span = f"{rows[0]['timestamp'][:16]}  ->  {rows[-1]['timestamp'][:16]}" if rows else "-"
print(f"span: {span}")
print(f"rows: {len(rows)}   buys: {len(buys)}   sells: {len(sells)}   "
      f"skips: {len(skips)}   errors/halts: {len(errs)}")
print("-" * 60)
print(f"Realized P&L (sum of SELL pnl_usd):  ${realized:+.2f}")
print(f"Total fees paid (buys+sells):        ${total_fees:.2f}")
print(f"Gross P&L before fees (approx):      ${realized + total_fees:+.2f}")
print("-" * 60)
if sells:
    print(f"Win rate:        {len(wins)}/{len(sells)}  ({len(wins)/len(sells)*100:.1f}%)")
    print(f"Avg win:         ${statistics.mean(wins):+.4f}" if wins else "Avg win: -")
    print(f"Avg loss:        ${statistics.mean(losses):+.4f}" if losses else "Avg loss: -")
    print(f"Biggest win:     ${max(pnls):+.4f}")
    print(f"Biggest loss:    ${min(pnls):+.4f}")
    print(f"Worst losing streak: {worst} trades")
    exp = statistics.mean(pnls)
    print(f"Expectancy/trade:    ${exp:+.4f}   "
          f"(={'PROFITABLE' if exp>0 else 'LOSING'} per trade after fees)")
print("-" * 60)
print("P&L by exit reason:")
for tag, ps in sorted(by_reason.items(), key=lambda x: sum(x[1])):
    print(f"  {tag:<18} n={len(ps):<4} total ${sum(ps):+.2f}   avg ${statistics.mean(ps):+.4f}")
print("-" * 60)
print("P&L by day:")
for d, v in sorted(by_day.items()):
    bar = "#" * min(40, int(abs(v) * 8))
    print(f"  {d}  ${v:+7.2f}  {'-' if v<0 else '+'}{bar}")
print("-" * 60)
print("Top skip reasons:")
for reason, n in Counter(r["reason"].split(" (")[0] for r in skips).most_common(8):
    print(f"  {n:>5}  {reason}")
tot_days = len(by_day) or 1
print("-" * 60)
print(f"Avg realized P&L per day: ${realized/tot_days:+.2f}   over {tot_days} active day(s)")
print()
