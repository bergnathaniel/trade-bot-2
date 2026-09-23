"""Long Picks, steps 1 and 3 of a round (rules: PREREG_LONGPICKS.md). Paper money only.

    python3 live_arena/long_picks/picks.py snapshot
        Saves today's eligible meme coins and US stocks and draws the hidden random control samples (pending/<date>.json).
    python3 live_arena/long_picks/picks.py lock live_arena/long_picks/incoming.json
        Checks every pick against that snapshot, then saves rounds/<date>.json and its fingerprint in ledger.jsonl.

The picks file: {"moonshots": [{"id": "<coingecko id>", "reason": "...", "sources": ["https://..."]}],
                 "holds": [{"symbol": "AAPL", "reason": "...", "sources": ["https://..."]}]}
with 0 to 3 picks in each bucket.
"""
import argparse
import json
import os
import random
import sys

import lib


def check_rules():
    if not lib.rules_intact():
        sys.exit("PREREG_LONGPICKS.md doesn't match PREREG.sha256. The rules changed, so this test restarts with a new start date.")


def snapshot():
    check_rules()
    day = str(lib.now_utc().date())
    if os.path.exists(os.path.join(lib.ROUNDS, f"{day}.json")):
        sys.exit(f"A round for {day} is already locked.")
    snap = {"moonshots": lib.meme_eligible(), "holds": lib.stock_eligible(),
            "made_utc": lib.now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")}
    snap["sample"] = {}
    for b, spec in lib.BUCKETS.items():
        pool = sorted(snap[b])
        random.Random(f"longpicks-{day}-{b}").shuffle(pool)
        snap["sample"][b] = pool[:spec["sample"]]
    os.makedirs(lib.PENDING, exist_ok=True)
    path = os.path.join(lib.PENDING, f"{day}.json")
    with open(path, "w") as f:
        json.dump(snap, f)
    print(f"Snapshot for {day}. Pick 0 to {lib.MAX_PICKS} in each bucket:")
    print(f"  moonshots: {len(snap['moonshots'])} meme coins worth $1M-$100M with $100k+ traded in 24h (give the CoinGecko id). "
          f"Held 30 days, 2% cost each way.")
    print(f"  holds: {len(snap['holds'])} US stocks worth $300M+, price $5+, 250,000+ shares today. Held 90 days.")
    print(f"Saved {os.path.relpath(path)}. Paper money only.")


def lock(picks_path):
    check_rules()
    day = str(lib.now_utc().date())
    pending = os.path.join(lib.PENDING, f"{day}.json")
    if not os.path.exists(pending):
        sys.exit(f"No snapshot for {day}. Run the snapshot step first, on the same UTC day as the lock.")
    with open(pending) as f:
        snap = json.load(f)
    with open(picks_path) as f:
        incoming = json.load(f)
    problems, locked = [], {}
    for bucket in lib.BUCKETS:
        chosen, seen = [], set()
        for p in incoming.get(bucket, []):
            key = str(p.get("id" if bucket == "moonshots" else "symbol", "")).strip()
            key = key.lower() if bucket == "moonshots" else key.upper()
            reason, sources = str(p.get("reason", "")).strip(), p.get("sources") or []
            if not key or key in seen:
                problems.append(f"{bucket}: '{key}' is missing or repeated")
                continue
            seen.add(key)
            if key not in snap[bucket]:
                problems.append(f"{bucket} {key}: not on today's eligible list (see PREREG_LONGPICKS.md)")
                continue
            if len(reason) < 20:
                problems.append(f"{bucket} {key}: the reason needs at least 20 characters")
            if not sources or not all(str(s).startswith("http") for s in sources):
                problems.append(f"{bucket} {key}: needs at least one source URL")
            chosen.append({"key": key, "reason": reason, "sources": sources, **snap[bucket][key]})
        if len(chosen) > lib.MAX_PICKS:
            problems.append(f"{bucket}: {len(chosen)} picks, the most allowed is {lib.MAX_PICKS}")
        locked[bucket] = chosen
    if problems:
        print("Not locked. Fix these and lock again:")
        for line in problems:
            print("  -", line)
        sys.exit(1)
    locked_at = lib.now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")
    rnd = {"round": day, "locked_utc": locked_at, "prereg_sha256": lib.file_sha(lib.PREREG), "picks": locked,
           "sample": snap["sample"], "pool_sizes": {b: len(snap[b]) for b in lib.BUCKETS}}
    os.makedirs(lib.ROUNDS, exist_ok=True)
    path = os.path.join(lib.ROUNDS, f"{day}.json")
    with open(path, "w") as f:
        json.dump(rnd, f, indent=1)
    with open(lib.LEDGER, "a") as f:
        f.write(json.dumps({"round": day, "locked_utc": locked_at, "sha256": lib.file_sha(path)}) + "\n")
    os.remove(pending)
    print(f"Locked round {day} at {locked_at}:")
    for bucket, entries in locked.items():
        names = ", ".join(e.get("symbol", e["key"]) if bucket == "moonshots" else e["key"] for e in entries) or "no picks"
        print(f"  {lib.BUCKETS[bucket]['name']}: {names}")
    print(f"Saved {os.path.relpath(path)}. Paper money only.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("step", choices=["snapshot", "lock"])
    ap.add_argument("picks", nargs="?")
    a = ap.parse_args()
    if a.step == "snapshot":
        snapshot()
    elif a.picks:
        lock(a.picks)
    else:
        sys.exit("lock needs the picks file, e.g. live_arena/long_picks/incoming.json")
