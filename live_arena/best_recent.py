"""
"Best Recent": every week, hold whichever (bot, coin) pair has had the best trailing 3-week record in
the live speed test (PREREG_BESTRECENT.md).
====================================================================================================

    python3 live_arena/best_recent.py --update    rebuild best_recent_ledger.json and BESTRECENT_RESULTS.md
    python3 live_arena/best_recent.py --check      just print the integrity checks

Reads live_arena/speed/results/<week>.json (only weeks that have the per-coin breakdown added to
speed_test.js on 2026-09-22 - earlier weeks are skipped, not backfilled: see PREREG_BESTRECENT.md
section G). Makes no network calls and runs no simulation of its own - every return it uses is a
number the speed test itself already published.

The whole ledger is rebuilt from scratch every run (cheap: a few dozen weeks at most), so it can
never drift from what's actually in speed/results/.
"""

import argparse
import glob
import hashlib
import json
import os
import random
import re
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PREREG = os.path.join(HERE, "..", "research", "PREREG_BESTRECENT.md")
RESULTS_DIR = os.path.join(HERE, "speed", "results")
LEDGER = os.path.join(HERE, "best_recent_ledger.json")
REPORT = os.path.join(HERE, "BESTRECENT_RESULTS.md")

GROUP, TF = "crypto", "15"
LOOKBACK_WEEKS = 3
MIN_TRADES_LOOKBACK = 5
MIN_CLOSED_TO_BE_LISTED = 1
N_RANDOM_DRAWS = 5000
RANDOM_SEED = 20260922
G1_MIN_PICKS = 10
G3_PERCENTILE = 0.995


def load_weeks():
    """Every speed/results/<week>.json that has the per-coin breakdown, oldest first, as
    (week_str, crypto_15_group_dict)."""
    out = []
    for path in sorted(glob.glob(os.path.join(RESULTS_DIR, "*.json"))):
        week = os.path.splitext(os.path.basename(path))[0]
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", week):
            continue
        with open(path) as f:
            data = json.load(f)
        group = next((g for g in data.get("groups", []) if g["group"] == GROUP and g["tf"] == TF), None)
        if not group or not group["bots"] or "per" not in group["bots"][0]:
            continue
        out.append((week, group))
    return out


def eligible_pairs(group, min_closed=MIN_CLOSED_TO_BE_LISTED):
    """[(bot_id, bot_name, coin, ret, closed), ...] for every non-control bot x coin that closed at
    least `min_closed` trades that week."""
    out = []
    for b in group["bots"]:
        if b["control"]:
            continue
        for coin, p in b["per"].items():
            if p["closed"] >= min_closed:
                out.append((b["id"], b["name"], coin, p["ret"], p["closed"]))
    return out


def trailing_rank(weeks, upto, lookback=LOOKBACK_WEEKS, min_trades=MIN_TRADES_LOOKBACK):
    """Using only weeks[upto-lookback : upto] (strictly before weeks[upto] - the week being picked
    for), rank (bot, coin) pairs by mean weekly return. None if there aren't `lookback` prior weeks."""
    if upto < lookback:
        return None
    window = weeks[upto - lookback:upto]
    agg = {}
    for _, g in window:
        for bot_id, bot_name, coin, ret, closed in eligible_pairs(g):
            key = (bot_id, coin)
            e = agg.setdefault(key, {"bot_id": bot_id, "bot_name": bot_name, "coin": coin, "rets": [], "trades": 0})
            e["rets"].append(ret)
            e["trades"] += closed
    ranked = [{**e, "mean": sum(e["rets"]) / len(e["rets"])} for e in agg.values() if e["trades"] >= min_trades]
    ranked.sort(key=lambda e: -e["mean"])
    return ranked


def bot_ret(group, bot_id, coin):
    b = next((b for b in group["bots"] if b["id"] == bot_id), None)
    return b["per"].get(coin, {}).get("ret") if b else None


def build_ledger(weeks):
    """One entry per week where a real pick was made (>= LOOKBACK_WEEKS of trailing data existed)."""
    ledger = []
    for i, (week, group) in enumerate(weeks):
        ranked = trailing_rank(weeks, i)
        if not ranked:
            continue
        pick = ranked[0]
        realized = bot_ret(group, pick["bot_id"], pick["coin"])
        if realized is None:   # the picked bot/coin dropped out of the pool that week - skip, rare
            continue
        pool = eligible_pairs(group)
        ledger.append({
            "week": week, "bot_id": pick["bot_id"], "bot_name": pick["bot_name"], "coin": pick["coin"],
            "trailing_mean": pick["mean"], "trailing_trades": pick["trades"], "candidates": len(ranked),
            "realized_ret": realized, "pool_size": len(pool),
        })
    return ledger


def compound(rets):
    total = 1.0
    for r in rets:
        total *= 1 + r
    return total - 1


def random_control(weeks, ledger, seed=RANDOM_SEED, n=N_RANDOM_DRAWS):
    """n draws: each week in the ledger, pick one random pair from that week's own trailing-eligible
    pool (the same pool the real pick came from), use its realized return, compound across weeks."""
    rng = random.Random(seed)
    idx = {w: i for i, (w, _) in enumerate(weeks)}
    pools = []
    for entry in ledger:
        i = idx[entry["week"]]
        ranked = trailing_rank(weeks, i)
        _, group = weeks[i]
        options = [bot_ret(group, e["bot_id"], e["coin"]) for e in ranked]
        options = [r for r in options if r is not None]
        pools.append(options)
    draws = []
    for _ in range(n):
        draws.append(compound(rng.choice(pool) for pool in pools if pool))
    draws.sort()
    return draws


def hold_controls(weeks, ledger):
    idx = {w: i for i, (w, _) in enumerate(weeks)}
    btc_rets, pool_rets = [], []
    for entry in ledger:
        _, group = weeks[idx[entry["week"]]]
        btc_rets.append(bot_ret(group, "hold", "BTC-USD"))
        coins = [b for b in group["bots"] if b["id"] == "hold"][0]["per"]
        pool_rets.append(sum(v["ret"] for v in coins.values()) / len(coins))
    return compound(r for r in btc_rets if r is not None), compound(r for r in pool_rets if r is not None)


def spearman(xs, ys):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    n = len(xs)
    if n < 2:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = (sum((x - mx) ** 2 for x in rx)) ** 0.5
    dy = (sum((y - my) ** 2 for y in ry)) ** 0.5
    return num / (dx * dy) if dx > 0 and dy > 0 else None


def persistence(weeks):
    """Rank correlation between a pair's trailing mean and its own next-week return, pooled over
    every (week, pair) where both exist. The always-reported diagnostic from PREREG_PICK's pattern."""
    xs, ys = [], []
    for i in range(LOOKBACK_WEEKS, len(weeks)):
        ranked = trailing_rank(weeks, i)
        if not ranked:
            continue
        _, group = weeks[i]
        for e in ranked:
            r = bot_ret(group, e["bot_id"], e["coin"])
            if r is not None:
                xs.append(e["mean"])
                ys.append(r)
    return spearman(xs, ys), len(xs)


def check_no_lookahead(weeks, ledger):
    """Every ledger pick must be reproducible using only weeks strictly before it - recomputed fresh,
    not just trusted from how build_ledger was written."""
    idx = {w: i for i, (w, _) in enumerate(weeks)}
    for entry in ledger:
        i = idx[entry["week"]]
        ranked = trailing_rank(weeks, i)
        if not ranked or (ranked[0]["bot_id"], ranked[0]["coin"]) != (entry["bot_id"], entry["coin"]):
            return {"ok": False, "week": entry["week"]}
        # truncating everything from this week onward must not change a pick made using only earlier weeks
        ranked_trunc = trailing_rank(weeks[:i + 1], i)
        if not ranked_trunc or (ranked_trunc[0]["bot_id"], ranked_trunc[0]["coin"]) != (entry["bot_id"], entry["coin"]):
            return {"ok": False, "week": entry["week"], "reason": "truncation changed the pick"}
    return {"ok": True, "n_checked": len(ledger)}


def check_reproduces_speed_test(weeks, ledger):
    idx = {w: i for i, (w, _) in enumerate(weeks)}
    for entry in ledger:
        _, group = weeks[idx[entry["week"]]]
        if bot_ret(group, entry["bot_id"], entry["coin"]) != entry["realized_ret"]:
            return {"ok": False, "week": entry["week"]}
    return {"ok": True, "n_checked": len(ledger)}


def write_report(sha, weeks, ledger, integrity):
    def pc(x):
        return "n/a" if x is None else f"{x * 100:+.1f}%"

    lines = [
        "# Best Recent: results", "",
        f"**Updated:** {time.strftime('%Y-%m-%d %H:%M')}. PREREG_BESTRECENT.md sha256 `{sha}`.", "",
        f"{len(weeks)} week(s) of per-coin speed-test data available "
        f"({weeks[0][0] if weeks else 'none'} to {weeks[-1][0] if weeks else 'none'}). "
        f"Needs {LOOKBACK_WEEKS} trailing weeks before its first pick.", "",
        "## Integrity", "",
        f"- No look-ahead: {'PASS' if integrity['no_lookahead']['ok'] else 'FAIL'}",
        f"- Reproduces the speed test's own numbers: {'PASS' if integrity['reproduce']['ok'] else 'FAIL'}",
        "",
    ]
    if not ledger:
        lines += ["## Status", "", "**Still collecting data - no pick has been made yet.** "
                  f"Needs {LOOKBACK_WEEKS} trailing weeks of per-coin speed-test history; "
                  f"{len(weeks)} available so far.", ""]
        with open(REPORT, "w") as f:
            f.write("\n".join(lines))
        return

    rets = [e["realized_ret"] for e in ledger]
    total = compound(rets)
    draws = random_control(weeks, ledger)
    p99_5 = draws[int(G3_PERCENTILE * len(draws)) - 1] if draws else None
    pct_below = sum(1 for d in draws if d < total) / len(draws) if draws else None
    btc_total, pool_total = hold_controls(weeks, ledger)
    corr, n_pairs = persistence(weeks)
    positive_weeks = sum(1 for r in rets if r > 0)

    g1 = len(ledger) >= G1_MIN_PICKS
    g2 = total > 0
    g3 = p99_5 is not None and total > p99_5
    g4 = btc_total is not None and total > btc_total
    g5 = pool_total is not None and total > pool_total
    passed_1_3 = g1 and g2 and g3
    verdict = ("PASS" if (passed_1_3 and g4 and g5) else
               "real, but not worth it" if (passed_1_3 and (g4 or g5)) else
               "not enough picks yet" if not g1 else "FAIL")

    best_week = max(ledger, key=lambda e: e["realized_ret"])
    lines += [
        "## Status", "",
        f"**{len(ledger)} weekly pick(s) made. Verdict: {verdict}.**", "",
        f"- Cumulative return after fees: **{pc(total)}**",
        f"- Random-pair control, {G3_PERCENTILE * 100:.1f}th percentile of {N_RANDOM_DRAWS} draws: "
        f"{pc(p99_5)} (this result beat {pct_below * 100:.1f}% of random draws)" if p99_5 is not None else
        "- Random-pair control: not enough data yet",
        f"- Holding bitcoin over the same weeks: {pc(btc_total)}",
        f"- Holding the whole pool, equal weight: {pc(pool_total)}",
        f"- Positive in {positive_weeks} of {len(ledger)} weeks",
        f"- Rank correlation, trailing mean vs. next week's return: "
        f"{corr if corr is None else round(corr, 3)} (n={n_pairs})",
        f"- Single best week: {best_week['week']}, {best_week['bot_name']} on {best_week['coin']}, "
        f"{pc(best_week['realized_ret'])}",
        "",
        "| gate | result |", "|---|---|",
        f"| G1 (>= {G1_MIN_PICKS} picks) | {'pass' if g1 else 'fail'} |",
        f"| G2 (positive) | {'pass' if g2 else 'fail'} |",
        f"| G3 (beats random pair, {G3_PERCENTILE * 100:.1f}th pct) | {'pass' if g3 else 'fail'} |",
        f"| G4 (beats holding bitcoin) | {'pass' if g4 else 'fail'} |",
        f"| G5 (beats holding the pool) | {'pass' if g5 else 'fail'} |",
        "", "| week | pick | trailing mean | trades | realized | pool |", "|---|---|---|---|---|---|",
        *(f"| {e['week']} | {e['bot_name']} / {e['coin']} | {pc(e['trailing_mean'])} | {e['trailing_trades']} | "
          f"{pc(e['realized_ret'])} | {e['pool_size']} |" for e in ledger),
        "",
    ]
    with open(REPORT, "w") as f:
        f.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true", help="rebuild the ledger and report")
    ap.add_argument("--check", action="store_true", help="just print integrity checks")
    args = ap.parse_args()

    sha = hashlib.sha256(open(PREREG, "rb").read()).hexdigest()
    print(f"PREREG_BESTRECENT.md sha256 = {sha}")

    weeks = load_weeks()
    print(f"{len(weeks)} week(s) with per-coin data: {[w for w, _ in weeks]}")
    ledger = build_ledger(weeks)
    print(f"{len(ledger)} pick(s) made so far")

    integrity = {"no_lookahead": check_no_lookahead(weeks, ledger), "reproduce": check_reproduces_speed_test(weeks, ledger)}
    print("no-lookahead:", integrity["no_lookahead"])
    print("reproduces speed test:", integrity["reproduce"])

    if args.check and not args.update:
        return

    with open(LEDGER, "w") as f:
        json.dump({"prereg_sha256": sha, "generated": time.strftime("%Y-%m-%d %H:%M"), "picks": ledger}, f, indent=1)
    print(f"wrote {LEDGER}")
    write_report(sha, weeks, ledger, integrity)
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
