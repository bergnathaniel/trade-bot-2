"""
Quick P&L summary for the insider bot's dry-run (or live) trade log.

    python insider_pnl.py                 # reads insider_dry_run_log.csv
    python insider_pnl.py insider_trade_log.csv   # live log

Shows totals plus the last few closed trades. Safe to run anytime while the
bot is still going — it just reads the file.
"""

import csv
import sys
from collections import Counter

path = sys.argv[1] if len(sys.argv) > 1 else "insider_dry_run_log.csv"

rows = []
try:
    with open(path) as f:
        rows = list(csv.DictReader(f))
except FileNotFoundError:
    print(f"No log yet at {path} — the bot hasn't logged anything.")
    raise SystemExit(0)

buys = [r for r in rows if r["event"] == "BUY"]
sells = [r for r in rows if r["event"] == "SELL"]
skips = [r for r in rows if r["event"] == "SKIP"]

def f(x):
    try:
        return float(x)
    except (ValueError, TypeError):
        return 0.0

realized = sum(f(r["pnl_usd"]) for r in sells)
fees = sum(f(r["fee_usd"]) for r in rows)
wins = [r for r in sells if f(r["pnl_usd"]) > 0]
losses = [r for r in sells if f(r["pnl_usd"]) <= 0]
open_positions = len(buys) - len(sells)

print(f"\nlog: {path}")
print("=" * 52)
print(f"Copies opened (BUY):   {len(buys)}")
print(f"Closed (SELL):         {len(sells)}   "
      f"{len(wins)}W / {len(losses)}L"
      f"{f'  ({len(wins)/len(sells)*100:.0f}% win)' if sells else ''}")
print(f"Still open:             {open_positions}")
print(f"Skipped (filtered):    {len(skips)}")
print("-" * 52)
print(f"Realized P&L:          ${realized:+.4f}")
print(f"Total fees in that:    ${fees:.4f}")
print("=" * 52)

if skips:
    print("\nTop skip reasons:")
    for reason, n in Counter(r["reason"].split(" (")[0] for r in skips).most_common(6):
        print(f"  {n:>4}  {reason}")

if sells:
    print("\nLast closed trades:")
    for r in sells[-8:]:
        print(f"  {r['timestamp']}  {r['symbol']:<12} "
              f"${f(r['pnl_usd']):+.4f}   {r['reason'].split(' | ')[0]}")
print()
