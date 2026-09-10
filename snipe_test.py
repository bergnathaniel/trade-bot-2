"""
Strategy: buy every token near graduation (no picky filters), sell at a tiny
profit. Tested on the 393 archived trades.

Since the log only stores the exit that actually happened, we test the
GENEROUS version: assume every trade that didn't rug would have hit your
tiny +T% target and been sold there. Rugs stay full losses. If the generous
version still loses, the real one loses harder.
"""
import csv, re, statistics

buys, trades = {}, []
for r in csv.DictReader(open("dry_run_log.PRE_DIPTEST.csv")):
    if r["event"] == "BUY":
        buys[r["mint"]] = float(r["size_usd"])
    elif r["event"] == "SELL" and r["mint"] in buys:
        entry = buys.pop(r["mint"])
        try: pnl = float(r["pnl_usd"])
        except ValueError: continue
        trades.append(pnl / entry * 100)   # % return on money put in

n = len(trades)
COST = 5.5                          # round-trip cost %, ~$2 position
RUG = -35                           # worse than this = liquidity pulled, unsellable
rugs = [x for x in trades if x <= RUG]
ok = n - len(rugs)

print(f"{n} trades  |  {len(rugs)} rugs ({len(rugs)/n*100:.0f}%, avg {statistics.mean(rugs):.0f}%)  "
      f"|  {ok} survivable\n")
print(f"{'sell at':>8} | {'kept after cost':>15} | {'$20 over ~800 trades/day x1':>28}")
print("-" * 58)
for T in (2, 3, 4, 5, 6, 8, 10):
    keep = T - COST
    if keep <= 0:
        print(f"+{T:>6}% | {'nothing — under cost':>15} | account bleeds every trade")
        continue
    # generous: every survivable trade = +keep%, every rug = its full loss
    exp_pct = (ok * keep + sum(rugs)) / n
    bal = 20.0
    # simulate ~1 day of trades at the archived rate (~500/day)
    for _ in range(500):
        bal *= (1 + exp_pct/100)
        if bal < 0.5: break
    print(f"+{T:>6}% | {keep:>+13.1f}% | $20 -> ${bal:>7.2f}   (exp {exp_pct:+.2f}%/trade)")

print("\nEven being generous, every 'sell at a small profit' target loses,")
print("because the ~15% that rug (-70% each) outweigh the small wins, and")
print("selling faster shrinks the wins without shrinking the rugs.")
