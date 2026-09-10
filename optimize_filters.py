"""
Can the scalper be made profitable by filtering entries harder?

Reads dry_run_log.csv SELL rows (each carries the entry features AND the
outcome), splits chronologically into TRAIN (first 60%) and TEST (last 40%),
greedily finds up to 4 feature thresholds that maximise TRAIN expectancy,
then reports the OUT-OF-SAMPLE result on TEST. Out-of-sample is the only
number that matters — in-sample improvement is just overfitting.
"""
import csv, re, statistics

FEATS = ["liq", "holders", "top_pct", "organic", "chg5m", "chg1h",
         "organic_buyers5m", "dev_mints"]

rows = []
for r in csv.DictReader(open("dry_run_log.csv")):
    if r["event"] != "SELL":
        continue
    m = {k: float(v) for k, v in re.findall(r"(\w+)=(-?\d+\.?\d*)", r["reason"])}
    if not all(k in m for k in FEATS):
        continue
    m["pnl"] = float(r["pnl_usd"])
    rows.append(m)

split = int(len(rows) * 0.6)
train, test = rows[:split], rows[split:]

def stats(data, label):
    if not data:
        print(f"  {label}: (empty)")
        return 0.0
    p = [d["pnl"] for d in data]
    exp = statistics.mean(p)
    wr = sum(1 for x in p if x > 0) / len(p) * 100
    print(f"  {label}: n={len(data):<4} total ${sum(p):+8.2f}  "
          f"exp ${exp:+.4f}  win {wr:.0f}%")
    return exp

print(f"total closed trades with full features: {len(rows)}  "
      f"(train {len(train)} / test {len(test)})\n")
print("BASELINE (no extra filter):")
stats(train, "train")
base_test_exp = stats(test, "test ")

# candidate thresholds per feature, both directions
def candidates(data, feat):
    vals = sorted(set(d[feat] for d in data))
    qs = [vals[int(len(vals) * q)] for q in (.1, .2, .3, .4, .5, .6, .7, .8, .9)]
    out = []
    for t in qs:
        out.append((feat, "<=", t))
        out.append((feat, ">=", t))
    return out

def apply(data, rules):
    out = []
    for d in data:
        ok = True
        for f, op, t in rules:
            if op == "<=" and not d[f] <= t: ok = False; break
            if op == ">=" and not d[f] >= t: ok = False; break
        if ok:
            out.append(d)
    return out

rules = []
for step in range(4):
    best, best_exp = None, None
    cur = apply(train, rules)
    for feat in FEATS:
        for cand in candidates(cur, feat):
            kept = apply(train, rules + [cand])
            if len(kept) < max(20, len(train) * 0.15):   # keep a meaningful sample
                continue
            e = statistics.mean([d["pnl"] for d in kept])
            if best_exp is None or e > best_exp:
                best_exp, best = e, cand
    if not best:
        break
    rules.append(best)
    k_tr = apply(train, rules)
    print(f"\nrule {step+1}: {best[0]} {best[1]} {best[2]:g}")
    stats(k_tr, "train kept")

print("\n" + "=" * 60)
print("RULES:", " AND ".join(f"{f}{op}{t:g}" for f, op, t in rules))
print("=" * 60)
print("OUT-OF-SAMPLE (test set, the honest number):")
stats(test, "test all ")
kept_test = apply(test, rules)
oos_exp = stats(kept_test, "test kept")
dropped = len(test) - len(kept_test)
print(f"\n  filter drops {dropped}/{len(test)} test trades "
      f"({dropped/len(test)*100:.0f}%)")
verdict = ("STILL LOSING — filtering doesn't save it"
           if oos_exp <= 0 else
           "positive out-of-sample, but tiny sample — treat with suspicion")
print(f"  verdict: {verdict}")
print(f"  baseline test exp ${base_test_exp:+.4f}  ->  filtered ${oos_exp:+.4f}")
