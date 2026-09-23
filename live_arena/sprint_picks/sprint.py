"""Sprint Picks: one round of 10 meme coins + 10 stocks, checked at 1 and 2 weeks (rules: PREREG_SPRINT.md).
Paper money only. Reuses Long Picks' eligibility and price readers.

    python3 live_arena/sprint_picks/sprint.py snapshot
    python3 live_arena/sprint_picks/sprint.py lock live_arena/sprint_picks/incoming.json
    python3 live_arena/sprint_picks/sprint.py score
"""
import datetime
import hashlib
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "long_picks"))
import lib  # noqa: E402  Long Picks' lib: meme_eligible, stock_eligible, cg_prices, daily_opens

PREREG, PREREG_SHA = os.path.join(HERE, "PREREG_SPRINT.md"), os.path.join(HERE, "PREREG.sha256")
SNAP, ROUND, RESULTS = (os.path.join(HERE, f) for f in ("snapshot.json", "round.json", "RESULTS.md"))
BUCKETS = {"memes": {"name": "Meme coins", "cost": 2.0, "ref": "BTC-USD", "ref_name": "Bitcoin", "key": "id"},
           "stocks": {"name": "Stocks", "cost": 0.02, "ref": "SPY", "ref_name": "SPY", "key": "symbol"}}
PICKS, SAMPLE, SIMS, CHECKS = 10, 60, 1000, (7, 14)


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def check_rules():
    if open(PREREG_SHA).read().split()[0] != sha(PREREG):
        sys.exit("PREREG_SPRINT.md doesn't match PREREG.sha256; the rules changed.")


def snapshot():
    check_rules()
    if os.path.exists(ROUND):
        sys.exit("The round is already locked.")
    day = str(lib.now_utc().date())
    snap = {"day": day, "memes": lib.meme_eligible(), "stocks": lib.stock_eligible()}
    snap["sample"] = {}
    for b in BUCKETS:
        pool = sorted(snap[b])
        random.Random(f"sprint-{day}-{b}").shuffle(pool)
        snap["sample"][b] = pool[:SAMPLE]
    json.dump(snap, open(SNAP, "w"))
    print(f"Snapshot {day}: {len(snap['memes'])} eligible meme coins, {len(snap['stocks'])} eligible stocks.")


def lock(path):
    check_rules()
    snap, incoming = json.load(open(SNAP)), json.load(open(path))
    problems, picks = [], {}
    for b, spec in BUCKETS.items():
        chosen = []
        for p in incoming.get(b, []):
            k = str(p.get(spec["key"], "")).strip()
            k = k.lower() if b == "memes" else k.upper()
            if k not in snap[b]:
                problems.append(f"{b} {k}: not on the eligible list")
            elif k in [c["key"] for c in chosen]:
                problems.append(f"{b} {k}: repeated")
            elif len(str(p.get("reason", ""))) < 20 or not p.get("sources"):
                problems.append(f"{b} {k}: needs a 20+ character reason and a source")
            else:
                chosen.append({"key": k, "reason": p["reason"], "sources": p["sources"], **snap[b][k]})
        if len(chosen) != PICKS:
            problems.append(f"{b}: {len(chosen)} valid picks, needs exactly {PICKS}")
        picks[b] = chosen
    if problems:
        print("Not locked:\n  - " + "\n  - ".join(problems))
        sys.exit(1)
    rnd = {"locked_utc": lib.now_utc().strftime("%Y-%m-%dT%H:%M:%SZ"), "prereg_sha256": sha(PREREG),
           "picks": picks, "sample": snap["sample"]}
    json.dump(rnd, open(ROUND, "w"), indent=1)
    open(os.path.join(HERE, "ROUND.sha256"), "w").write(f"{sha(ROUND)}  round.json\n")
    print(f"Locked at {rnd['locked_utc']}:")
    for b in BUCKETS:
        print(f"  {BUCKETS[b]['name']}: " + ", ".join(c.get("symbol", c["key"]) if b == "memes" else c["key"] for c in picks[b]))


def first_on_or_after(series, target, slack=4):
    for d in sorted(series):
        if d >= target:
            return series[d] if (d - target).days <= slack else None
    return None


def score():
    check_rules()
    if open(os.path.join(HERE, "ROUND.sha256")).read().split()[0] != sha(ROUND):
        sys.exit("round.json doesn't match ROUND.sha256; the picks were changed after locking.")
    rnd = json.load(open(ROUND))
    locked = int(datetime.datetime.fromisoformat(rnd["locked_utc"].replace("Z", "+00:00")).timestamp())
    lock_day = datetime.date.fromisoformat(rnd["locked_utc"][:10])
    now = lib.now_utc()
    lines = ["# Sprint Picks: results", "", f"Paper money only. Updated {now:%Y-%m-%d %H:%M} UTC. Rules: `PREREG_SPRINT.md`. "
             "One round over 1-2 weeks is mostly luck, and no result here is a reason to use real money.", ""]
    for b, spec in BUCKETS.items():
        ref = lib.daily_opens(spec["ref"])
        cost2 = 2 * spec["cost"]
        if b == "stocks":
            entry_day = next((d for d in sorted(ref) if d > lock_day), None)
            opens_cache = {}

            def value(k, days, entry_day=entry_day, cache=opens_cache):
                if k not in cache:
                    try:
                        cache[k] = lib.daily_opens(k)
                    except Exception:
                        cache[k] = {}
                s = cache[k]
                e = s.get(entry_day)
                x = first_on_or_after(s, entry_day + datetime.timedelta(days=days))
                return None if e is None or x is None else (x / e - 1) * 100 - cost2
        else:
            entry_ts = (locked // lib.DAY + 1) * lib.DAY
            entry_day = datetime.datetime.fromtimestamp(entry_ts, datetime.timezone.utc).date()
            price_cache = {}

            def value(k, days, cache=price_cache, entry_ts=entry_ts):
                if k not in cache:
                    cache[k] = lib.cg_prices(k, locked)
                s = cache[k]
                if s is None:
                    return -100.0 - cost2
                after = [(t, p) for t, p in s if t >= entry_ts]
                if not after:
                    return None
                t0, p0 = after[0]
                if t0 - entry_ts > lib.DAY:   # no price near the entry time: the coin didn't trade yet
                    return None
                later = [p for t, p in after if t >= t0 + days * lib.DAY]
                return ((later[0] if later else after[-1][1]) / p0 - 1) * 100 - cost2
        lines += [f"## {spec['name']} (cost {spec['cost']}% each way, yardstick {spec['ref_name']})", ""]
        if entry_day is None:
            lines += ["Waiting for the first trading day after the lock.", ""]
            continue
        for days in CHECKS:
            due = datetime.datetime.combine(entry_day + datetime.timedelta(days=days + 1), datetime.time(), datetime.timezone.utc)
            if now < due:
                lines.append(f"- **{days}-day check:** not due until {due.date()}.")
                continue
            vals = [(c.get("symbol", c["key"]), value(c["key"], days)) for c in rnd["picks"][b]]
            got = [v for _, v in vals if v is not None]
            sample = [v for v in (value(k, days) for k in rnd["sample"][b]) if v is not None]
            r0, r1 = first_on_or_after(ref, entry_day), first_on_or_after(ref, entry_day + datetime.timedelta(days=days))
            ref_ret = (r1 / r0 - 1) * 100 if r0 and r1 else None
            rng = random.Random(20260923 + days)
            sims = sorted(sum(rng.sample(sample, min(PICKS, len(sample)))) / min(PICKS, len(sample)) for _ in range(SIMS)) if sample else []
            mean = sum(got) / len(got) if got else None
            p95 = sims[int(0.95 * len(sims)) - 1] if sims else None
            beat_ref = mean is not None and ref_ret is not None and mean > ref_ret
            beat_luck = mean is not None and p95 is not None and mean > p95
            lines += [f"- **{days}-day check:** picks averaged **{mean:+.2f}%** after costs; {spec['ref_name']} {ref_ret:+.2f}%; "
                      f"random 10-pick 95th percentile {p95:+.2f}%. "
                      + ("**Beat both, by the pre-set bar. One round is still mostly luck.**" if beat_ref and beat_luck
                         else "**No better than luck by the pre-set bar.**"),
                      "  " + ", ".join(f"{n} {v:+.1f}%" if v is not None else f"{n} n/a" for n, v in vals)]
        lines.append("")
    lines.append("Descriptive of the past only. Not investment advice.")
    open(RESULTS, "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else ""
    if step == "snapshot":
        snapshot()
    elif step == "lock" and len(sys.argv) > 2:
        lock(sys.argv[2])
    elif step == "score":
        score()
    else:
        sys.exit(__doc__)
