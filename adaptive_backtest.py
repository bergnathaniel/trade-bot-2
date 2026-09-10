"""
"Make the scalper learn from its mistakes."

This does exactly that, walk-forward, on the real dry_run_log.csv trades:

  1. Start after a warm-up of `WARMUP` trades.
  2. For every following block of `STEP` trades:
       - look back at everything seen so far,
       - find the entry-filter rules that would have avoided the most
         losers while keeping the most winners  (learning from mistakes),
       - shrink position size if the recent win-rate is poor  (risk memory),
       - apply that to the *next* block it hasn't seen,
       - record the result, then re-learn and roll forward.
  3. Compare the adaptive strategy's cumulative P&L to the baseline
     (take every trade, fixed size).

Everything is out-of-sample: each block is scored with rules fitted only on
earlier data. That is the only honest way to test "it learns."

Note: the log only records the outcome of the exit that was actually used,
so this can adapt ENTRIES and SIZE, not the stop-loss/take-profit levels.
"""
import csv, re, statistics

WARMUP = 120
STEP = 15
TRAIN_WINDOW = 250      # trailing trades used to re-learn each step
STAKE = 2.0             # fixed $ per trade, both strategies, for a fair compare
FEATS = ["liq", "holders", "top_pct", "organic", "chg5m", "chg1h",
         "organic_buyers5m", "dev_mints"]

rows = []
for r in csv.DictReader(open("dry_run_log.csv")):
    if r["event"] != "SELL":
        continue
    m = {k: float(v) for k, v in re.findall(r"(\w+)=(-?\d+\.?\d*)", r["reason"])}
    try:
        size = float(r["size_usd"]); pnl = float(r["pnl_usd"])
    except ValueError:
        continue
    if not all(k in m for k in FEATS) or size <= 0:
        continue
    m["ret"] = pnl / size          # return per $1 staked
    rows.append(m)

print(f"{len(rows)} closed trades with full features\n")


def apply_rules(data, rules):
    out = []
    for d in data:
        if all((d[f] <= t) if op == "<=" else (d[f] >= t) for f, op, t in rules):
            out.append(d)
    return out


def learn_rules(train):
    """Greedily add up to 3 threshold rules that raise mean return on `train`,
    always keeping at least 35% of the trades."""
    rules = []
    for _ in range(3):
        cur = apply_rules(train, rules)
        best, best_m = None, statistics.mean([d["ret"] for d in cur]) if cur else -9
        for f in FEATS:
            vals = sorted(set(d[f] for d in cur))
            if len(vals) < 5:
                continue
            for q in (.1, .2, .3, .4, .5, .6, .7, .8, .9):
                t = vals[int(len(vals) * q)]
                for op in ("<=", ">="):
                    kept = apply_rules(train, rules + [(f, op, t)])
                    if len(kept) < max(15, len(train) * 0.35):
                        continue
                    mu = statistics.mean([d["ret"] for d in kept])
                    if mu > best_m + 1e-9:
                        best_m, best = mu, (f, op, t)
        if not best:
            break
        rules.append(best)
    return rules


base_cum, adapt_cum = 0.0, 0.0
base_curve, adapt_curve = [], []
blocks = []
i = WARMUP
while i < len(rows):
    train = rows[max(0, i - TRAIN_WINDOW):i]
    test = rows[i:i + STEP]
    rules = learn_rules(train)

    # risk memory: scale size by recent win-rate (0.5x .. 1.0x)
    recent = train[-40:]
    wr = sum(1 for d in recent if d["ret"] > 0) / len(recent) if recent else 0.5
    size_mult = max(0.5, min(1.0, wr / 0.55))

    for d in test:
        base_cum += STAKE * d["ret"]
        base_curve.append(base_cum)
        took = all((d[f] <= t) if op == "<=" else (d[f] >= t) for f, op, t in rules)
        adapt_cum += (STAKE * size_mult * d["ret"]) if took else 0.0
        adapt_curve.append(adapt_cum)
    blocks.append((i, rules, size_mult,
                   sum(STAKE * d["ret"] for d in test),
                   sum(STAKE * size_mult * d["ret"] for d in test
                       if all((d[f] <= t) if op == "<=" else (d[f] >= t)
                              for f, op, t in rules))))
    i += STEP

print(f"{'after trade':>11} | {'learned rules':<44} | {'sizeX':>5} | "
      f"{'block base':>10} | {'block adapt':>11}")
print("-" * 96)
for idx, rules, sm, b, a in blocks:
    rr = " ".join(f"{f}{op}{t:g}" for f, op, t in rules) or "(none)"
    print(f"{idx:>11} | {rr[:44]:<44} | {sm:>5.2f} | ${b:>8.2f} | ${a:>9.2f}")

print("\n" + "=" * 60)
print(f"Trades scored out-of-sample: {len(base_curve)}")
print(f"BASELINE  (take every trade, ${STAKE:g} each):   ${base_cum:+.2f}")
print(f"ADAPTIVE  (learns rules + sizing each {STEP}):   ${adapt_cum:+.2f}")
print("=" * 60)

# did it actually improve over time? compare first half vs second half of the
# out-of-sample period
half = len(adapt_curve) // 2
a1 = adapt_curve[half] - adapt_curve[0]
a2 = adapt_curve[-1] - adapt_curve[half]
print(f"Adaptive P&L, 1st half of live period: ${a1:+.2f}")
print(f"Adaptive P&L, 2nd half of live period: ${a2:+.2f}")
trend = "improving" if a2 > a1 + 0.5 else ("degrading" if a2 < a1 - 0.5 else "flat / no learning")
print(f"=> the 'learning' is: {trend}")
print()
if adapt_cum <= 0:
    print("VERDICT: adapting to its own mistakes did NOT make it profitable.")
elif adapt_cum <= base_cum:
    print("VERDICT: adaptive beat nothing — it's above baseline only by trading less.")
else:
    print("VERDICT: adaptive is positive AND beats baseline out-of-sample. Worth a look\n"
          "         — but confirm on a fresh, longer log before trusting it.")
