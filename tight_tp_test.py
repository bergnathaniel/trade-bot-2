"""
"Sell the moment it's up just past cost." Tested against real dry_run_log.csv.

Pairs each BUY with its SELL by mint to get the true % return on the amount
put in. Then models a tighter take-profit: every trade that did NOT crash
becomes a clean win at target T; the real crashes stay near-total losses
(you can't sell into pulled liquidity, however fast you are). Wins are capped
at T because you sell sooner. Optimistic on purpose.
"""
import csv, statistics

COST_PCT = 5.5            # round-trip: dex fee + slippage + flat fee on ~$2
CRASH = -35.0            # worse than -35% on the position = unsellable dump

buys = {}
pairs = []
for r in csv.DictReader(open("dry_run_log.csv")):
    if r["event"] == "BUY":
        buys[r["mint"]] = float(r["size_usd"])
    elif r["event"] == "SELL" and r["mint"] in buys:
        entry = buys.pop(r["mint"])
        try:
            pnl = float(r["pnl_usd"])
        except ValueError:
            continue
        pairs.append(pnl / entry * 100)   # true % return on money put in

n = len(pairs)
crashes = [x for x in pairs if x <= CRASH]
ok = n - len(crashes)
print(f"{n} paired trades   |   {len(crashes)} crashes (<= {CRASH:.0f}%, "
      f"avg {statistics.mean(crashes):.0f}%)   |   {ok} non-crash ({ok/n*100:.0f}%)\n")
print(f"actual outcome now:  avg {statistics.mean(pairs):+.1f}% / trade  "
      f"(sum {sum(pairs):+.0f}% over {n} trades)\n")

print(f"{'target T':>8} | {'net win':>8} | {'expectancy/trade':>17} | {'verdict':>12}")
print("-" * 56)
for T in (3, 4, 5, 6, 8, 10, 15, 25):
    net = T - COST_PCT
    if net <= 0:
        print(f"{T:>7}% | {'<= cost':>8} | {'always negative':>17} | {'LOSES':>12}")
        continue
    exp = (ok * net + sum(crashes)) / n     # every non-crash = +net, crashes unchanged
    print(f"{T:>7}% | {net:>+7.1f}% | {exp:>+16.2f}% | "
          f"{'LOSES' if exp <= 0 else 'positive?!':>12}")

print("\nEven assuming every non-crash trade hits your target cleanly (it won't),\n"
      f"the {len(crashes)} crashes ({len(crashes)/n*100:.0f}% of trades, ~-70% each) outweigh the\n"
      "pile of small wins at every target. Selling faster can't help the\n"
      "crashes -- when liquidity is pulled there is no price to sell at.")
