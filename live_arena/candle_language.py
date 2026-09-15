"""Candle language study for the Live Arena speed test. Paper money only: nothing here can trade.

Reads the saved 5- and 15-minute candles of the speed test's markets (SPEED_TEST.md) as a language.
- **Letters.** Each candle is one of 15 letters: its body against the average candle of the previous 50 (big down,
  down, flat, up, big up) and where it closed in its range (near the low, the middle or the high).
- **Words.** The last 2 or 3 letters.
- **Track records.** Walking forward through time, it keeps each word's record across every market in the group: what
  buying at the next open and selling 1, 4 or 8 hours later made after fees. A trade counts only once it has finished,
  and only if it finished in the last 30 days.
- **Doing what works only.** It trades a word only while that record clears a bar:
    strict: at least 50 finished trades, and the average minus 4 standard errors is still above zero. That bar is high
            enough that the thousands of word-and-horizon records shouldn't clear it by luck.
    loose:  any word that made money on average over at least 30 finished trades. This is the "keep doing what's been
            working" rule, for comparison.
  One trade at a time per market.

The results come from candles the record didn't include yet, compared with buying at every candle. It writes
speed/language.md.

    python3 live_arena/candle_language.py
"""
import collections
import datetime
import heapq
import json
import math
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "speed")
OUT = os.path.join(ROOT, "speed", "language.md")
SLIP = 0.0002
VOL_N, WINDOW_DAYS, WARMUP_DAYS = 50, 30, 14
HORIZONS = (("1 hour", 60), ("4 hours", 240), ("8 hours", 480))
RULES = {"strict": {"min_n": 50, "z": 4.0}, "loose": {"min_n": 30, "z": 0.0}}
BODY = ("big down", "down", "flat", "up", "big up")
PLACE = ("near its low", "mid-range", "near its high")
N_LETTERS, N_WORDS = 15, 15 ** 2 + 15 ** 3   # words of 2 letters take ids 0-224, words of 3 letters 225-3599


def letters(rows):
    """Each candle's letter id (body class × 3 + close location), or None until there are VOL_N earlier moves."""
    out, moves, total = [None] * len(rows), collections.deque(), 0.0
    for i in range(1, len(rows)):
        if len(moves) == VOL_N and total > 0:
            t, o, h, l, c = rows[i][:5]
            z = (c / o - 1) / (total / VOL_N)
            body = 0 if z <= -1 else 1 if z <= -0.25 else 2 if z < 0.25 else 3 if z < 1 else 4
            place = 1 if h == l else 0 if (c - l) / (h - l) < 1 / 3 else 2 if (c - l) / (h - l) > 2 / 3 else 1
            out[i] = body * 3 + place
        move = abs(rows[i][4] / rows[i - 1][4] - 1)
        moves.append(move)
        total += move
        if len(moves) > VOL_N:
            total -= moves.popleft()
    return out


def word_ids(let, i):
    ids = []
    if i >= 1 and let[i] is not None and let[i - 1] is not None:
        ids.append(let[i - 1] * 15 + let[i])
        if i >= 2 and let[i - 2] is not None:
            ids.append(225 + let[i - 2] * 225 + let[i - 1] * 15 + let[i])
    return ids


def spell(word):
    if word < 225:
        parts = [word // 15, word % 15]
    else:
        w = word - 225
        parts = [w // 225, (w // 15) % 15, w % 15]
    return " → ".join(f"{BODY[p // 3]} {PLACE[p % 3]}" for p in parts)


def study(group, tf, fee):
    with open(os.path.join(DATA, "manifest.json")) as f:
        symbols = next(g["symbols"] for g in json.load(f)["groups"] if g["id"] == group)
    rows, let = {}, {}
    for s in symbols:
        with open(os.path.join(DATA, group, f"{s}_{tf}.json")) as f:
            rows[s] = json.load(f)["result"][s]
        let[s] = letters(rows[s])
    step, cost = int(tf) * 60, 2 * fee + 2 * SLIP
    hz = [(name, max(1, round(mins / int(tf)))) for name, mins in HORIZONS]
    closes = sorted((r[0] + step, s, i) for s in symbols for i, r in enumerate(rows[s]))
    begin = closes[0][0] + WARMUP_DAYS * 86400
    middle = begin + (closes[-1][0] - begin) / 2
    K = N_WORDS * len(hz)
    n, s1, s2 = [0] * K, [0.0] * K, [0.0] * K
    pending, recorded = [], collections.deque()
    busy = {rule: {s: -1 for s in symbols} for rule in RULES}
    trades = {rule: [[], []] for rule in RULES}              # (net, horizon index, word) per half
    every = {h: [[], []] for h in range(len(hz))}           # buying at every candle, per horizon and half
    halves = {}                                             # (key) -> [[nets first half], [nets second half]] for persistence
    for close_t, sym, i in closes:
        while pending and pending[0][0] <= close_t:
            done, key, net = heapq.heappop(pending)
            n[key] += 1
            s1[key] += net
            s2[key] += net * net
            recorded.append((done, key, net))
        while recorded and recorded[0][0] <= close_t - WINDOW_DAYS * 86400:
            _, key, net = recorded.popleft()
            n[key] -= 1
            s1[key] -= net
            s2[key] -= net * net
        R, words = rows[sym], word_ids(let[sym], i)
        half = 0 if close_t < middle else 1
        outcome = {}
        for h, (_, H) in enumerate(hz):
            j = i + 1 + H
            if j >= len(R):
                continue
            net = R[j][1] / R[i + 1][1] - 1 - cost
            outcome[h] = net
            for w in words:   # the result is known once the exit candle has opened
                heapq.heappush(pending, (R[j][0], w * len(hz) + h, net))
                if close_t >= begin:
                    halves.setdefault(w * len(hz) + h, ([], []))[half].append(net)
            if close_t >= begin:
                every[h][half].append(net)
        if close_t < begin:
            continue
        for rule, p in RULES.items():
            if i <= busy[rule][sym]:
                continue
            best = None
            for h in outcome:
                for w in words:
                    k = w * len(hz) + h
                    if n[k] < p["min_n"]:
                        continue
                    mean = s1[k] / n[k]
                    se = math.sqrt(max(s2[k] / n[k] - mean * mean, 0.0) / (n[k] - 1))
                    bound = mean - p["z"] * se
                    if bound > 0 and (best is None or bound > best[0]):
                        best = (bound, h, w)
            if best:
                _, h, w = best
                trades[rule][half].append((outcome[h], h, w))
                busy[rule][sym] = i + hz[h][1]
    # the dictionary as it stands at the last candle: the best records by their lower bound
    board = []
    for k in range(K):
        if n[k] >= 30:
            mean = s1[k] / n[k]
            se = math.sqrt(max(s2[k] / n[k] - mean * mean, 0.0) / (n[k] - 1))
            board.append((mean - 4 * se, k, n[k], mean, se))
    board.sort(reverse=True)
    # does what worked in the first half keep working in the second? (words with 50+ trades in each half)
    pairs = [(sum(a) / len(a), sum(b) / len(b)) for a, b in halves.values() if len(a) >= 50 and len(b) >= 50]
    kept = sum(1 for a, b in pairs if a > 0 and b > 0)
    first_pos = sum(1 for a, _ in pairs if a > 0)
    return {"group": group, "tf": tf, "fee": fee, "cost": cost, "hz": hz, "trades": trades, "every": every,
            "board": board[:8], "pairs": len(pairs), "first_pos": first_pos, "kept": kept,
            "corr": correlation(pairs), "begin": begin, "end": closes[-1][0], "middle": middle}


def correlation(pairs):
    if len(pairs) < 3:
        return None
    xs, ys = [a for a, _ in pairs], [b for _, b in pairs]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxy = sum((x - mx) * (y - my) for x, y in pairs)
    sxx, syy = sum((x - mx) ** 2 for x in xs), sum((y - my) ** 2 for y in ys)
    return sxy / math.sqrt(sxx * syy) if sxx > 0 and syy > 0 else None


def pct(x, dp=3):
    return "–" if x is None else f"{x * 100:+.{dp}f}%"


def day(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%d")


def report(results):
    lines = ["# Candle language study", "",
             "Paper money only. Every saved speed-test candle is read as a letter (its size against the last 50 candles, "
             "and where it closed in its range), and the last 2 or 3 letters as a word. Walking forward through time, "
             "each word's record is what buying at the next open and selling 1, 4 or 8 hours later made after fees, "
             "counting only trades that had finished in the last 30 days. The study then trades a word only while its "
             "record clears a bar, and scores those trades on candles that weren't in the record yet.", "",
             "- **Strict:** 50 or more finished trades, and the average minus 4 standard errors is still above zero.",
             "- **Loose:** any word that made money on average over 30 or more finished trades.",
             "- **Every candle:** buying at every candle, for comparison.", ""]
    for r in results:
        name = f"{'Crypto' if r['group'] == 'crypto' else 'US stocks and ETFs'}, {r['tf']}-minute candles"
        lines += [f"## {name}", "",
                  f"Tested {day(r['begin'])} to {day(r['end'])} (after a {WARMUP_DAYS}-day warm-up), split at "
                  f"{day(r['middle'])}. A round trip costs {r['cost'] * 100:.2f}%.", "",
                  "| Rule | Trades (1st / 2nd half) | Average after fees (1st / 2nd half) | Won |", "|---|---:|---:|---:|"]
        for rule in RULES:
            a, b = r["trades"][rule]
            avg = lambda xs: sum(x[0] for x in xs) / len(xs) if xs else None  # noqa: E731
            won = sum(1 for x in a + b if x[0] > 0) / len(a + b) if a + b else None
            lines.append(f"| {rule.capitalize()} | {len(a)} / {len(b)} | {pct(avg(a))} / {pct(avg(b))} | "
                         f"{'–' if won is None else f'{won * 100:.0f}%'} |")
        for h, (hname, _) in enumerate(r["hz"]):
            a, b = r["every"][h]
            mean = lambda xs: sum(xs) / len(xs) if xs else None  # noqa: E731
            won = sum(1 for x in a + b if x > 0) / len(a + b) if a + b else None
            lines.append(f"| Every candle, {hname} | {len(a)} / {len(b)} | {pct(mean(a))} / {pct(mean(b))} | "
                         f"{'–' if won is None else f'{won * 100:.0f}%'} |")
        corr = r["corr"]
        lines += ["", f"**Does what worked keep working?** {r['pairs']} word-and-horizon records had 50+ trades in both "
                      f"halves. {r['first_pos']} made money in the first half, and {r['kept']} of those also made money in "
                      f"the second. The correlation between the two halves' averages was "
                      f"{'–' if corr is None else f'{corr:+.2f}'} (0 means the first half says nothing about the second).",
                  "", "**The best records at the last candle** (strict bar in the last column):", "",
                  "| Word | Hold | Trades | Average after fees | Clears the strict bar |", "|---|---|---:|---:|---|"]
        for bound, k, cnt, mean, se in r["board"]:
            word, h = divmod(k, len(r["hz"]))
            lines.append(f"| {spell(word)} | {r['hz'][h][0]} | {cnt} | {pct(mean)} | "
                         f"{'yes' if cnt >= 50 and bound > 0 else 'no'} |")
        lines.append("")
    lines += ["Descriptive of the past only. Not investment advice."]
    return "\n".join(lines) + "\n"


def main():
    with open(os.path.join(DATA, "manifest.json")) as f:
        manifest = json.load(f)
    results = []
    for g in manifest["groups"]:
        for tf in manifest["timeframes"]:
            results.append(study(g["id"], tf, float(g["fee"]) / 100))
            print(f"studied {g['id']} {tf}m", flush=True)
    text = report(results)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        f.write(text)
    print(text)
    print(f"Saved {os.path.relpath(OUT, os.path.dirname(ROOT))}")


if __name__ == "__main__":
    main()
