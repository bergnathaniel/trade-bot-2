"""Long Picks, the scorer (rules: PREREG_LONGPICKS.md). Paper money only.

    python3 live_arena/long_picks/score.py

Scores every round-bucket whose hold has ended, next to its yardstick and 1,000 random draws from the round's hidden
control sample. Each scored round-bucket is frozen in scored/<round>-<bucket>.json and never re-fetched, so a coin that
disappears later can't change an old result. Saves long_picks/RESULTS.md. The gates apply only after 12 scored rounds.
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
        path, day = os.path.join(lib.ROUNDS, name), name[:-5]
        if day not in ledger or lib.file_sha(path) != ledger[day]["sha256"]:
            edited.append(day)
            continue
        with open(path) as f:
            rounds.append(json.load(f))
    return rounds, edited


def first_on_or_after(day_opens, target, slack=4):
    for d in sorted(day_opens):
        if d >= target:
            return (d, day_opens[d]) if (d - target).days <= slack else (None, None)
    return None, None


def score_holds(rnd, spy):
    """Stocks: enter at the first open after the lock day, exit at the first open 90+ days later."""
    lock_day = datetime.date.fromisoformat(rnd["locked_utc"][:10])
    entry_day = next((d for d in sorted(spy) if d > lock_day), None)
    if entry_day is None:
        return None
    exit_day, spy_exit = first_on_or_after(spy, entry_day + datetime.timedelta(days=lib.BUCKETS["holds"]["hold"]))
    if exit_day is None:
        return None
    cost2 = 2 * lib.BUCKETS["holds"]["cost"]

    def result(symbol):
        try:
            series = lib.daily_opens(symbol)
        except Exception:
            return None, "no prices"
        time.sleep(0.15)
        e = series.get(entry_day)
        if e is None:
            return None, "no entry candle"
        _, x = first_on_or_after(series, exit_day)
        note = ""
        if x is None:
            x, note = series[max(series)], "no exit candle, last open used"
        return (x / e - 1) * 100 - cost2, note

    picks = [dict(key=p["key"], reason=p["reason"], **dict(zip(("ret", "note"), result(p["key"])))) for p in rnd["picks"]["holds"]]
    sample = [r for r, _ in (result(s) for s in rnd["sample"]["holds"]) if r is not None]
    return {"entry": str(entry_day), "exit": str(exit_day), "picks": picks, "sample": sample,
            "ref_ret": (spy_exit / spy[entry_day] - 1) * 100}


def score_moonshots(rnd, btc):
    """Meme coins: enter at the first CoinGecko daily price after the lock time, exit at the first one 30+ days later.
    A coin CoinGecko no longer has counts as -100%."""
    locked = int(datetime.datetime.fromisoformat(rnd["locked_utc"].replace("Z", "+00:00")).timestamp())
    hold = lib.BUCKETS["moonshots"]["hold"] * lib.DAY
    entry_target = (locked // lib.DAY + 1) * lib.DAY      # the next 00:00 UTC stamp
    if lib.now_utc().timestamp() < entry_target + hold + lib.DAY:
        return None
    cost2 = 2 * lib.BUCKETS["moonshots"]["cost"]

    def result(coin):
        prices = lib.cg_prices(coin, locked)
        if prices is None:
            return -100.0 - cost2, "no longer on CoinGecko: counted as -100%"
        after = [(t, p) for t, p in prices if t > locked]
        if not after:
            return None, "no price after the lock"
        t0, p0 = after[0]
        if t0 - entry_target > lib.DAY:   # no price near the entry time: the coin didn't trade yet
            return None, "no price near the entry date"
        later = [(t, p) for t, p in after if t >= t0 + hold]
        note = ""
        if later:
            p1 = later[0][1]
        else:
            p1, note = after[-1][1], "no price at the exit date, last price used"
        return (p1 / p0 - 1) * 100 - cost2, note

    picks = [dict(key=p["key"], symbol=p.get("symbol", ""), reason=p["reason"],
                  **dict(zip(("ret", "note"), result(p["key"])))) for p in rnd["picks"]["moonshots"]]
    sample = [r for r, _ in (result(c) for c in rnd["sample"]["moonshots"]) if r is not None]
    entry_day = datetime.datetime.fromtimestamp(entry_target, datetime.timezone.utc).date()
    _, b0 = first_on_or_after(btc, entry_day)
    _, b1 = first_on_or_after(btc, entry_day + datetime.timedelta(days=lib.BUCKETS["moonshots"]["hold"]))
    return {"entry": str(entry_day), "exit": str(entry_day + datetime.timedelta(days=lib.BUCKETS["moonshots"]["hold"])),
            "picks": picks, "sample": sample, "ref_ret": (b1 / b0 - 1) * 100 if b0 and b1 else None}


def simulate(per_round, seed):
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


def summary(bucket, scored):
    rows = [(rd, b) for rd, b in scored if b]
    picks = [p for _, b in rows for p in b["picks"] if p.get("ret") is not None]
    rets = [p["ret"] for p in picks]
    active = [(rd, b) for rd, b in rows if any(p.get("ret") is not None for p in b["picks"])]
    s = {"rounds": len(rows), "active": len(active), "n": len(rets)}
    if not rets:
        return s
    s["mean"] = sum(rets) / len(rets)
    refs = [b["ref_ret"] for _, b in active if b["ref_ret"] is not None]
    s["ref_mean"] = sum(refs) / len(refs) if refs else None
    sims = simulate([(sum(p.get("ret") is not None for p in b["picks"]), b["sample"]) for _, b in active], 20260923)
    s["random_mean"], s["percentile"] = sum(sims) / len(sims), sum(m < s["mean"] for m in sims) / len(sims)
    s["without_best"] = (sum(rets) - max(rets)) / (len(rets) - 1) if len(rets) > 1 else None
    s["winning"] = sum(sum(p["ret"] for p in b["picks"] if p.get("ret") is not None) > 0 for _, b in active)
    s["gates"] = [("Made money after costs", s["mean"] > 0),
                  (f"Beat holding {lib.BUCKETS[bucket]['ref_name']}", s["ref_mean"] is not None and s["mean"] > s["ref_mean"]),
                  (f"Beat {lib.PERCENTILE:.0%} of random picks", s["percentile"] >= lib.PERCENTILE),
                  ("Positive without its best pick", s["without_best"] is not None and s["without_best"] > 0),
                  ("Positive in more than half the rounds", s["winning"] > len(active) / 2)]
    return s


def main():
    if not lib.rules_intact():
        sys.exit("PREREG_LONGPICKS.md doesn't match PREREG.sha256. The rules changed, so this test restarts with a new start date.")
    rounds, edited = load_rounds()
    os.makedirs(lib.SCORED, exist_ok=True)
    spy = btc = None
    scored = {b: [] for b in lib.BUCKETS}
    waiting = {b: [] for b in lib.BUCKETS}
    for rnd in rounds:
        for bucket in lib.BUCKETS:
            path = os.path.join(lib.SCORED, f"{rnd['round']}-{bucket}.json")
            if os.path.exists(path):
                with open(path) as f:
                    res = json.load(f)
            else:
                if bucket == "holds":
                    spy = spy or lib.daily_opens("SPY")
                    res = score_holds(rnd, spy)
                else:
                    btc = btc or lib.daily_opens("BTC-USD")
                    res = score_moonshots(rnd, btc)
                if res is None:
                    waiting[bucket].append(rnd["round"])
                    continue
                with open(path, "w") as f:
                    json.dump(res, f, indent=1)
            scored[bucket].append((rnd["round"], res))

    lines = ["# Long Picks: results", "",
             f"Paper money only. Updated {lib.now_utc():%Y-%m-%d %H:%M} UTC. Rules: `PREREG_LONGPICKS.md`. Nothing here is a "
             "recommendation to buy anything. Only the twelfth scored round of a bucket decides anything.", "",
             f"Rounds locked: {len(rounds)}."]
    if edited:
        lines.append(f"**Not scored, because the file doesn't match its fingerprint in ledger.jsonl: {', '.join(edited)}.**")
    out_summary = []
    for bucket, spec in lib.BUCKETS.items():
        s = summary(bucket, scored[bucket])
        lines += ["", f"## {spec['name']} (held {spec['hold']} days, {spec['cost']:.2f}% cost each way, yardstick {spec['ref_name']})", "",
                  f"Scored rounds: {len(scored[bucket])} of {lib.ROUNDS_NEEDED}."
                  + (f" Still holding: {', '.join(waiting[bucket])}." if waiting[bucket] else "")]
        if not s.get("n"):
            lines.append("No scored picks yet.")
            out_summary.append(f"{spec['name']}: no scored picks yet ({len(waiting[bucket])} round(s) still holding).")
            continue
        ref = pct(s["ref_mean"]) if s["ref_mean"] is not None else "n/a"
        lines += ["", f"- Picks scored: {s['n']}. Average per pick after costs: **{pct(s['mean'])}**.",
                  f"- Holding {spec['ref_name']} over the same periods: {ref}.",
                  f"- Random picks from the same rounds: {pct(s['random_mean'])}. The picks beat {s['percentile']:.0%} of 1,000 random draws (bar {lib.PERCENTILE:.0%}).",
                  f"- Without the best pick: {pct(s['without_best']) if s['without_best'] is not None else 'n/a'}. Rounds in the black: {s['winning']} of {s['active']}."]
        if len(scored[bucket]) >= lib.ROUNDS_NEEDED and s["n"] >= lib.MIN_PICKS:
            ok = all(g for _, g in s["gates"])
            lines += ["", "| Gate | Result |", "|---|---|"] + [f"| {g} | {'pass' if v else 'fail'} |" for g, v in s["gates"]]
            lines += ["", f"**Verdict: {'passes all five gates. A lead, not proof, and not a reason to use real money.' if ok else 'fails.'}**"]
        out_summary.append(f"{spec['name']}: {s['n']} picks, {pct(s['mean'])} average vs {ref} for {spec['ref_name']}, "
                           f"beat {s['percentile']:.0%} of random draws.")
    lines += ["", "## Every pick", "", "| Round | Bucket | Pick | Return after costs | Note |", "|---|---|---|---:|---|"]
    for bucket in lib.BUCKETS:
        for rd, b in scored[bucket]:
            for p in b["picks"]:
                name = f"{p.get('symbol', '')} ({p['key']})" if bucket == "moonshots" else p["key"]
                lines.append(f"| {rd} | {bucket} | {name} | {pct(p['ret']) if p.get('ret') is not None else 'n/a'} | {p.get('note', '')} |")
    lines += ["", "Descriptive of the past only. Not investment advice."]
    with open(RESULTS, "w") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(out_summary))
    print(f"Saved {os.path.relpath(RESULTS)}")


if __name__ == "__main__":
    main()
