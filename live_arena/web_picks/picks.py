"""Web Picks, step 1 and 3 of a round (rules: PREREG_WEBPICKS.md). Paper money only.

    python3 live_arena/web_picks/picks.py snapshot
        Pulls today's eligible stocks, micro-caps and Coinbase coins, draws the hidden random control sample, and prints
        the rules to pick under. Saves pending/<date>.json.
    python3 live_arena/web_picks/picks.py lock live_arena/web_picks/incoming.json
        Checks every pick against the rules, then saves rounds/<date>.json and its fingerprint in ledger.jsonl.
        Picks can't be changed afterwards.

The picks file: {"stocks": [{"symbol": "AAPL", "reason": "...", "sources": ["https://..."]}], "micro": [...], "crypto": [...]}
with 0 to 3 picks in each bucket.
"""
import argparse
import json
import os
import random
import sys
import time

import lib


def build_sample(bucket, snap, seed):
    rng = random.Random(f"webpicks-{seed}-{bucket}")
    if bucket == "crypto":
        pool = list(snap["crypto"])
    else:
        pool = sorted(snap[bucket])
    rng.shuffle(pool)
    sample = []
    for symbol in pool:
        if len(sample) == lib.SAMPLE:
            break
        try:
            if bucket == "crypto":
                rows = lib.coin_rows(symbol)
                ok = len(rows) >= 14 and lib.dollar_volume(rows) >= lib.MIN_DOLLAR_VOLUME and not lib.stable_like(rows)
            else:
                ok = len(lib.stock_rows(symbol)) >= 30
        except Exception:
            ok = False
        if ok:
            sample.append(symbol)
        time.sleep(0.15)
    return sample


def snapshot():
    if not lib.rules_intact():
        sys.exit("PREREG_WEBPICKS.md doesn't match PREREG.sha256. The rules changed, so this test has to restart with a new start date.")
    day = str(lib.today())
    os.makedirs(lib.PENDING, exist_ok=True)
    path = os.path.join(lib.PENDING, f"{day}.json")
    if os.path.exists(os.path.join(lib.ROUNDS, f"{day}.json")):
        sys.exit(f"A round for {day} is already locked.")
    snap = lib.screener_rows()
    snap["crypto"] = lib.coinbase_products()
    snap["sample"] = {b: build_sample(b, snap, day) for b in lib.BUCKETS}
    snap["made_utc"] = lib.now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(path, "w") as f:
        json.dump(snap, f)
    print(f"Snapshot for {day} saved. Pick from these buckets, 0 to {lib.MAX_PICKS} long picks each:")
    print(f"  stocks: {len(snap['stocks'])} US stocks worth $2B or more (price $5+, 500,000+ shares a day). Fee 0.02%.")
    print(f"  micro:  {len(snap['micro'])} US stocks worth $50M to under $300M (price $1+, 50,000+ shares a day). Fee 0.50%.")
    print(f"  crypto: {len(snap['crypto'])} Coinbase USD coins, minus stablecoins (the $250,000+ traded a day rule is checked when you lock). Fee 0.25%.")
    print(f"Each pick is bought at the next daily open and sold at the open 7 days later. Paper money only.")
    print(f"Saved {os.path.relpath(path)}")


def lock(picks_path):
    if not lib.rules_intact():
        sys.exit("PREREG_WEBPICKS.md doesn't match PREREG.sha256. The rules changed, so this test has to restart with a new start date.")
    day = str(lib.today())
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
            symbol = str(p.get("symbol", "")).upper().strip()
            reason, sources = str(p.get("reason", "")).strip(), p.get("sources") or []
            if bucket == "crypto":
                symbol = lib.coin_id(symbol)
            if not symbol or symbol in seen:
                problems.append(f"{bucket}: '{symbol}' is missing or repeated")
                continue
            seen.add(symbol)
            if len(reason) < 20:
                problems.append(f"{bucket} {symbol}: the reason needs at least 20 characters")
            if not sources or not all(str(s).startswith("http") for s in sources):
                problems.append(f"{bucket} {symbol}: needs at least one source URL")
            try:
                if bucket == "crypto":
                    if symbol not in snap["crypto"]:
                        problems.append(f"{bucket} {symbol}: not an online, open Coinbase USD market that isn't a stablecoin")
                        continue
                    rows = lib.coin_rows(symbol)
                    if lib.dollar_volume(rows) < lib.MIN_DOLLAR_VOLUME:
                        problems.append(f"{bucket} {symbol}: under $250,000 traded a day")
                        continue
                    if lib.stable_like(rows):
                        problems.append(f"{bucket} {symbol}: barely moves, so it's treated as a stablecoin")
                        continue
                else:
                    if symbol not in snap[bucket]:
                        problems.append(f"{bucket} {symbol}: not eligible in this bucket today (see PREREG_WEBPICKS.md)")
                        continue
                    rows = lib.stock_rows(symbol)
                if not rows:
                    problems.append(f"{bucket} {symbol}: no daily prices")
                    continue
            except Exception as e:
                problems.append(f"{bucket} {symbol}: price check failed ({e})")
                continue
            entry = {"symbol": symbol, "reason": reason, "sources": sources, "last_close": rows[-1][4]}
            if bucket == "crypto":
                entry["meme"] = symbol.split("-")[0] in lib.MEMES
            chosen.append(entry)
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
        names = ", ".join(e["symbol"] for e in entries) or "no picks"
        print(f"  {lib.BUCKETS[bucket]['name']}: {names}")
    print(f"Saved {os.path.relpath(path)}. Paper money only.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("step", choices=["snapshot", "lock"])
    ap.add_argument("picks", nargs="?", help="for lock: the picks JSON file")
    a = ap.parse_args()
    if a.step == "snapshot":
        snapshot()
    elif a.picks:
        lock(a.picks)
    else:
        sys.exit("lock needs the picks file, e.g. live_arena/web_picks/incoming.json")
