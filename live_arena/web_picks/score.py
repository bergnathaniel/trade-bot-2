"""Web Picks, the scorer (rules: PREREG_WEBPICKS.md). Paper money only.

    python3 live_arena/web_picks/score.py

Scores every locked round whose exit day has arrived, next to the yardstick fund and 1,000 random draws from each round's
hidden control sample, and saves web_picks/RESULTS.md. The verdict gates only apply once 12 rounds are scored.
"""
import datetime
import json
import os
import random
import sys
import time

import lib

RESULTS = os.path.join(lib.HERE, "RESULTS.md")


def pct(x, dp=2):
    return f"{x:+.{dp}f}%"


def open_at(day_opens, target, slack=4):
    """The open on the first candle dated target or later, within a few days; None if there isn't one."""
    for d in sorted(day_opens):
        if d >= target:
            return day_opens[d] if (d - target).days <= slack else None
    return None


def load_rounds():
    ledger = {}
    if os.path.exists(lib.LEDGER):
        with open(lib.LEDGER) as f:
            for line in f:
                row = json.loads(line)
                ledger[row["round"]] = row
    rounds, edited = [], []
    for name in sorted(os.listdir(lib.ROUNDS)) if os.path.isdir(lib.ROUNDS) else []:
        if not name.endswith(".json"):
            continue
        path = os.path.join(lib.ROUNDS, name)
        day = name[:-5]
        if day not in ledger or lib.file_sha(path) != ledger[day]["sha256"]:
            edited.append(day)
            continue
        with open(path) as f:
            rounds.append(json.load(f))
    return rounds, edited


def score_round(rnd, cache):
    """{bucket: {...}} for a round, or None for a bucket whose exit day hasn't come yet."""
    lock_day = datetime.date.fromisoformat(rnd["locked_utc"][:10])
    out = {}
    for bucket, spec in lib.BUCKETS.items():
        def get(symbol):
            key = (bucket, symbol)
            if key not in cache:
                try:
                    cache[key] = lib.opens(bucket, symbol)
                except Exception:
                    cache[key] = {}
                time.sleep(0.15)
            return cache[key]

        ref = get(spec["ref"])
        entry_day, exit_day = lib.fills(ref, lock_day)
        if not entry_day or not exit_day:
            out[bucket] = None
            continue
        fee2 = 2 * spec["fee"]

        def result(symbol):
            series = get(symbol)
            e = open_at(series, entry_day)
            if e is None:
                return None, "no entry candle"
            x, note = open_at(series, exit_day), ""
            if x is None:
                x, note = series[max(series)], "no exit candle, last open used"
            return (x / e - 1) * 100 - fee2, note

        picks = []
        for p in rnd["picks"].get(bucket, []):
            r, note = result(p["symbol"])
            picks.append({"symbol": p["symbol"], "ret": r, "note": note, "reason": p["reason"], "meme": p.get("meme", False)})
        sample = [r for r, _ in (result(s) for s in rnd["sample"].get(bucket, [])) if r is not None]
        ref_e, ref_x = open_at(ref, entry_day), open_at(ref, exit_day)
        out[bucket] = {"entry": entry_day, "exit": exit_day, "picks": picks, "sample": sample,
                       "ref_ret": (ref_x / ref_e - 1) * 100}
    return out


def simulate(per_round, seed):
    """1,000 random draws: the average return per pick if each round's picks had come from its control sample."""
    rng, means = random.Random(seed), []
    for _ in range(lib.SIMS):
        total = n = 0
        for k, values in per_round:
            k = min(k, len(values))
            if k:
                total += sum(rng.sample(values, k))
                n += k
        means.append(total / n if n else 0.0)
    return means


def bucket_summary(bucket, scored):
    rows = [(r["round"], r[bucket]) for r in scored if r[bucket]]
    picks = [(rd, p) for rd, b in rows for p in b["picks"] if p["ret"] is not None]
    rets = [p["ret"] for _, p in picks]
    active = [(rd, b) for rd, b in rows if any(p["ret"] is not None for p in b["picks"])]
    s = {"rounds": len(rows), "active": len(active), "n": len(rets)}
    if not rets:
        return s
    s["mean"] = sum(rets) / len(rets)
    s["ref_mean"] = sum(b["ref_ret"] for _, b in active) / len(active)
    s["random_mean"] = None
    per_round = [(sum(p["ret"] is not None for p in b["picks"]), b["sample"]) for _, b in active]
    sims = simulate(per_round, 20260921)
    s["random_mean"] = sum(sims) / len(sims)
    s["percentile"] = sum(m < s["mean"] for m in sims) / len(sims)
    s["without_best"] = (sum(rets) - max(rets)) / (len(rets) - 1) if len(rets) > 1 else None
    winners = sum(sum(p["ret"] for p in b["picks"] if p["ret"] is not None) > 0 for _, b in active)
    s["winning_rounds"] = winners
    memes = [p["ret"] for _, p in picks if p["meme"]]
    s["memes"] = (len(memes), sum(memes) / len(memes)) if memes else None
    s["gates"] = [
        ("Made money after fees", s["mean"] > 0),
        (f"Beat holding {lib.BUCKETS[bucket]['ref_name']}", s["mean"] > s["ref_mean"]),
        (f"Beat {lib.PERCENTILE:.0%} of random picks", s["percentile"] >= lib.PERCENTILE),
        ("Positive without its best pick", s["without_best"] is not None and s["without_best"] > 0),
        ("Positive in more than half the weeks", winners > len(active) / 2),
    ]
    return s


def main():
    if not lib.rules_intact():
        sys.exit("PREREG_WEBPICKS.md doesn't match PREREG.sha256. The rules changed, so this test has to restart with a new start date.")
    rounds, edited = load_rounds()
    cache, scored, waiting = {}, [], []
    for rnd in rounds:
        res = score_round(rnd, cache)
        if all(v is None for v in res.values()):
            waiting.append(rnd["round"])
            continue
        entry = {"round": rnd["round"], **res}
        if any(v is None for v in res.values()):
            waiting.append(rnd["round"] + " (part)")
        scored.append(entry)
    complete = [r for r in scored if all(r[b] for b in lib.BUCKETS)]

    lines = ["# Web Picks: results", "",
             f"Paper money only. Updated {lib.now_utc():%Y-%m-%d %H:%M} UTC. Rules: `PREREG_WEBPICKS.md`. "
             f"Only the twelfth scored round decides anything; until then these are progress numbers.", ""]
    lines.append(f"Rounds locked: {len(rounds)}. Fully scored: {len(complete)} of {lib.ROUNDS_NEEDED} needed."
                 + (f" Waiting on an exit day: {', '.join(waiting)}." if waiting else ""))
    if edited:
        lines.append(f"**Not scored, because the file doesn't match its fingerprint in ledger.jsonl: {', '.join(edited)}.**")
    lines.append("")
    verdict_ready = len(complete) >= lib.ROUNDS_NEEDED
    summary_lines = []
    for bucket, spec in lib.BUCKETS.items():
        s = bucket_summary(bucket, scored)
        lines += [f"## {spec['name']} (fee {spec['fee']:.2f}% a trade, yardstick {spec['ref_name']})", ""]
        if not s.get("n"):
            lines += ["No scored picks yet.", ""]
            summary_lines.append(f"{spec['name']}: no scored picks yet.")
            continue
        lines += [f"- Picks scored: {s['n']} over {s['active']} weeks. Average per pick after fees: **{pct(s['mean'])}**.",
                  f"- Holding {spec['ref_name']} over the same weeks: {pct(s['ref_mean'])}.",
                  f"- Random picks from the same weeks: {pct(s['random_mean'])} on average. The picks beat {s['percentile']:.0%} of 1,000 random draws (the bar is {lib.PERCENTILE:.0%}).",
                  f"- Without its single best pick: {pct(s['without_best']) if s['without_best'] is not None else 'n/a'}. "
                  f"Weeks in the black: {s['winning_rounds']} of {s['active']}."]
        if s.get("memes"):
            lines.append(f"- Meme-tagged picks (descriptive only): {s['memes'][0]}, average {pct(s['memes'][1])}.")
        lines.append("")
        if verdict_ready and s["n"] >= lib.MIN_PICKS:
            passed = all(ok for _, ok in s["gates"])
            lines += ["| Gate | Result |", "|---|---|"] + [f"| {g} | {'pass' if ok else 'fail'} |" for g, ok in s["gates"]]
            lines += ["", f"**Verdict: {'passes all five gates. A lead, not proof: it needs a fresh 12-round repeat, and it is not a reason to use real money.' if passed else 'fails.'}**", ""]
            summary_lines.append(f"{spec['name']}: {'passes all five gates' if passed else 'fails'}.")
        elif verdict_ready:
            lines += [f"**Verdict: not enough picks ({s['n']} of the {lib.MIN_PICKS} needed).**", ""]
            summary_lines.append(f"{spec['name']}: not enough picks.")
        else:
            summary_lines.append(f"{spec['name']}: {s['n']} picks, average {pct(s['mean'])} after fees vs {pct(s['ref_mean'])} for {spec['ref_name']} "
                                 f"(beat {s['percentile']:.0%} of random draws); too early to judge.")
    lines += ["## Every pick", "", "| Round | Bucket | Pick | Return after fees | Note |", "|---|---|---|---:|---|"]
    for r in scored:
        for bucket in lib.BUCKETS:
            if r[bucket]:
                for p in r[bucket]["picks"]:
                    lines.append(f"| {r['round']} | {bucket} | {p['symbol']}{' (meme)' if p['meme'] else ''} | "
                                 f"{pct(p['ret']) if p['ret'] is not None else 'n/a'} | {p['note']} |")
    lines += ["", "Descriptive of the past only. Not investment advice."]
    with open(RESULTS, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines[:4]))
    print()
    print("\n".join(summary_lines) or "Nothing to score yet.")
    print(f"\nSaved {os.path.relpath(RESULTS)}")


if __name__ == "__main__":
    main()
