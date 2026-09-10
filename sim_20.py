"""
Paper backtest: fake $20 bankroll walked through the REAL dry_run_log.csv
trades (real graduated tokens, real Jupiter prices, simulated fills) in
timestamp order. Reports P&L per day and projects to 3 days.
"""
import csv, datetime, statistics

rows = [r for r in csv.DictReader(open("dry_run_log.csv"))]
trades = [r for r in rows if r["event"] == "SELL"]

START = 20.0
bal = START
low = START
peak = START
by_day = {}
curve = []
wins = losses = 0
fees = 0.0

def f(x):
    try: return float(x)
    except: return 0.0

for r in trades:
    pnl = f(r["pnl_usd"])
    fees += f(r["fee_usd"])
    bal += pnl
    peak = max(peak, bal)
    low = min(low, bal)
    d = r["timestamp"][:10]
    by_day[d] = by_day.get(d, 0.0) + pnl
    curve.append(bal)
    if pnl > 0: wins += 1
    else: losses += 1

t0 = datetime.datetime.strptime(trades[0]["timestamp"], "%Y-%m-%d %H:%M:%S")
t1 = datetime.datetime.strptime(trades[-1]["timestamp"], "%Y-%m-%d %H:%M:%S")
hours = max((t1 - t0).total_seconds() / 3600, 1e-9)
n = len(trades)
if n < 10:
    print(f"Only {n} completed trade(s) so far "
          f"(P&L ${bal - START:+.2f}). Too early — let it run longer.")
    raise SystemExit(0)
pnl_total = bal - START

print("=" * 58)
print(f"FAKE $20 BANKROLL  —  real dry-run trades, simulated fills")
print("=" * 58)
print(f"Window:           {trades[0]['timestamp']}  ->  {trades[-1]['timestamp']}")
print(f"                  = {hours:.1f} hours  ({hours/24:.2f} days), {n} round-trips")
print(f"Trades/day:       {n / (hours/24):.0f}")
print("-" * 58)
print(f"Starting balance: ${START:.2f}")
print(f"Ending balance:   ${bal:.2f}")
print(f"P&L:              ${pnl_total:+.2f}   ({pnl_total/START*100:+.1f}%)")
print(f"Win rate:         {wins}/{n}  ({wins/n*100:.0f}%)")
print(f"Fees paid (sim):  ${fees:.2f}")
print(f"Lowest balance:   ${low:.2f}    highest: ${peak:.2f}")
print("-" * 58)
print("P&L by day:")
for d in sorted(by_day):
    v = by_day[d]
    print(f"  {d}   ${v:+7.2f}")
print("-" * 58)
per_day = pnl_total / (hours / 24)
print(f"Average P&L per day:        ${per_day:+.2f}")
print(f"Projected over 3 days:      ${per_day * 3:+.2f}   "
      f"-> ending ~${START + per_day*3:.2f}")
days_to_zero = (bal / -per_day) if per_day < 0 else None
if days_to_zero:
    print(f"At this rate, $20 -> $0 in about {days_to_zero:.1f} days.")
print("=" * 58)

# the "only take the small wins" fantasy (look-ahead — not achievable live)
tp = [f(r["pnl_usd"]) for r in trades if "take_profit" in r["reason"]]
sl = [f(r["pnl_usd"]) for r in trades if "take_profit" not in r["reason"]]
print("\nIf you could magically take ONLY the winning trades (you can't —")
print("you don't know which is which until after you've bought):")
print(f"  take_profit trades: {len(tp)}   sum ${sum(tp):+.2f}")
print(f"  everything else:    {len(sl)}   sum ${sum(sl):+.2f}")
print(f"  -> the losers are what you'd have to avoid, and nothing in the")
print(f"     entry data separates them in advance (already tested).")
