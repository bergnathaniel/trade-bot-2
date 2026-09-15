"""
Scoring the engine's calls (PREREG_ENGINE.md, sections C-E).
===========================================================

  label_rows()    outcome of every call, the prompt's log fields (MFE/MAE, invalidation)
  climatology()   no-skill control: the most common recently-resolved outcome
  persistence()   no-skill control: "whatever the last h minutes did"
  learn_filter()  config E2: only issue call types whose resolved track record earns it
  shuffle_test()  the engine's own calls shuffled within each day, exact moments
  day_bootstrap() resample whole days
"""

import math
import random

import eng_ind as ind
from eng_core import HORIZONS, REC_FIELDS, call_of

SEED = 20260911
F = {k: i for i, k in enumerate(REC_FIELDS)}
SKEY = {5: "S5", 30: "S30", 120: "S120"}
DIRS = ("UP", "DOWN")


def label_of(r, band):
    return "UP" if r > band else "DOWN" if r < -band else "SIDEWAYS"


def conf_bucket(S):
    c = round(100 * min(1.0, abs(S) / 0.75))
    return "75-100" if c >= 75 else "60-74" if c >= 60 else "50-59" if c >= 50 else "33-49"


def label_rows(recs, m1, h):
    """
    One dict per record whose outcome window exists: the log row for horizon h.
    The window is the minute bars that open at D .. D+h-60; outcome = close of the last one.
    """
    hi_max, lo_min = ind.rolling_max(m1.h, h), ind.rolling_min(m1.l, h)
    rows = []
    for rec in recs:
        D, i1, price, sigma = rec[F["D"]], rec[F["i1"]], rec[F["price"]], rec[F["sigma"]]
        j = i1 + h
        close_at = rec[F["close_at"]]
        if j >= len(m1.t) or m1.t[j] != D + h * 60 - 60 or (close_at is not None and D + h * 60 > close_at):
            continue
        S = rec[F[SKEY[h]]]
        band = 0.5 * sigma * math.sqrt(h)
        ret = m1.c[j] / price - 1.0
        prev = price / m1.c[i1 - h] - 1.0 if i1 - h >= 0 else 0.0
        call = call_of(S)
        up_hi, dn_lo = hi_max[j] / price - 1.0, lo_min[j] / price - 1.0
        inval = sigma * math.sqrt(h)
        rows.append({
            "D": D, "day": rec[F["day"]], "price": price, "regime": rec[F["regime"]],
            "vol": rec[F["vol"]], "S": S, "call": call, "bucket": conf_bucket(S),
            "fam": rec[F["fam%d" % h]], "ret": ret, "label": label_of(ret, band),
            # persistence baseline: the same band rule applied to the previous h minutes
            "persist": label_of(prev, band),
            "hi": up_hi, "lo": dn_lo,
            "mfe": up_hi if call == "UP" else -dn_lo if call == "DOWN" else max(up_hi, -dn_lo),
            "mae": dn_lo if call == "UP" else -up_hi if call == "DOWN" else min(dn_lo, -up_hi),
            "invalidated": (dn_lo <= -inval) if call == "UP" else (up_hi >= inval) if call == "DOWN" else None,
            "target_err": abs(ret - (0.8 * 2 * band if call == "UP" else -0.8 * 2 * band if call == "DOWN" else 0.0)),
            "nochange_err": abs(ret),
            "rec": rec,
        })
    return rows


def _windowed(rows, h, kind, days_back, on_add, on_remove, on_decide):
    """
    Walk rows in time order. Before deciding row k, every earlier row whose outcome is known
    (D' + h <= D) and still inside the window has been added. Crypto window = trailing
    `days_back` days; stock window = resolved rows from earlier sessions.
    """
    add = rem = 0
    for k, row in enumerate(rows):
        D = row["D"]
        if kind == "crypto":
            while add < k and rows[add]["D"] + h * 60 <= D:
                on_add(rows[add])
                add += 1
            while rem < add and rows[rem]["D"] < D - days_back * 86400:
                on_remove(rows[rem])
                rem += 1
        else:
            while add < k and rows[add]["day"] < row["day"]:
                on_add(rows[add])
                add += 1
        on_decide(row)


def climatology(rows, h, kind):
    counts = {"UP": 0, "DOWN": 0, "SIDEWAYS": 0}

    def add(r):
        counts[r["label"]] += 1

    def rem(r):
        counts[r["label"]] -= 1

    def decide(r):
        # unregistered choice: with no resolved history yet, call SIDEWAYS
        r["clim"] = max(counts, key=lambda c: (counts[c], c == "SIDEWAYS")) if any(counts.values()) else "SIDEWAYS"

    _windowed(rows, h, kind, 7, add, rem, decide)


def learn_filter(rows, h, kind):
    """Config E2. Sets row['e2'] to the E1 call or SIDEWAYS."""
    n_type, hit_type, lab = {}, {}, {"UP": 0, "DOWN": 0, "SIDEWAYS": 0}
    tot = [0]

    def key(r):
        return (r["regime"], r["call"], r["bucket"])

    def add(r):
        lab[r["label"]] += 1
        tot[0] += 1
        if r["call"] in DIRS:
            k = key(r)
            n_type[k] = n_type.get(k, 0) + 1
            hit_type[k] = hit_type.get(k, 0) + (r["label"] == r["call"])

    def rem(r):
        lab[r["label"]] -= 1
        tot[0] -= 1
        if r["call"] in DIRS:
            k = key(r)
            n_type[k] -= 1
            hit_type[k] -= (r["label"] == r["call"])

    def decide(r):
        r["e2"] = "SIDEWAYS"
        if r["call"] in DIRS and tot[0]:
            k = key(r)
            n = n_type.get(k, 0)
            if n >= 50 and hit_type[k] / n >= lab[r["call"]] / tot[0] + 0.05:
                r["e2"] = r["call"]

    _windowed(rows, h, kind, 30, add, rem, decide)


# ------------------------------------------------------------------ statistics

def day_table(rows, pred_key):
    """day -> [n, correct3, dir_calls, dir_hits, sign_hits, dir_outcomes, dir_outcomes_caught, clim_correct, pers_correct]"""
    t = {}
    for r in rows:
        x = t.setdefault(r["day"], [0] * 9)
        p, lab = r[pred_key], r["label"]
        x[0] += 1
        x[1] += p == lab
        if p in DIRS:
            x[2] += 1
            x[3] += p == lab
            x[4] += (r["ret"] > 0) if p == "UP" else (r["ret"] < 0)
        if lab in DIRS:
            x[5] += 1
            x[6] += p == lab
        x[7] += r.get("clim") == lab
        x[8] += r["persist"] == lab
    return t


def summarize(rows, pred_key):
    t = day_table(rows, pred_key)
    s = [sum(x[i] for x in t.values()) for i in range(9)]
    n, dirn = s[0] or 1, s[2] or 1
    return {
        "n": s[0], "days": len(t), "accuracy": s[1] / n, "dir_calls": s[2],
        "dir_call_share": s[2] / n, "dir_hit": s[3] / dirn if s[2] else None,
        "sign_hit": s[4] / dirn if s[2] else None,
        "false_positive": 1 - s[3] / dirn if s[2] else None,
        "false_negative": 1 - s[6] / s[5] if s[5] else None,
        "clim_accuracy": s[7] / n, "persist_accuracy": s[8] / n,
    }


def strata(rows, pred_key):
    """Per day: [n, a_UP, a_DOWN, b_UP, b_DOWN, hits] - all the within-day shuffle needs."""
    t = {}
    for r in rows:
        x = t.setdefault(r["day"], [0] * 6)
        p, lab = r[pred_key], r["label"]
        x[0] += 1
        x[1] += p == "UP"
        x[2] += p == "DOWN"
        x[3] += lab == "UP"
        x[4] += lab == "DOWN"
        x[5] += p in DIRS and p == lab
    return t


def shuffle_from_strata(strata_list, days=None):
    """
    Directional hits if the calls were randomly permuted within each symbol-day.
    Hits in class c ~ hypergeometric(n, a_c, b_c); the UP and DOWN counts covary by
    a_U b_U a_D b_D / (n^2 (n-1)). Symbol-days are independent strata.
    """
    mean = var = hits = calls = 0.0
    for t in strata_list:
        for d, (n, aU, aD, bU, bD, hh) in t.items():
            if n < 2 or (days is not None and d not in days):
                continue
            calls += aU + aD
            hits += hh
            mean += (aU * bU + aD * bD) / n
            var += (aU * bU * (n - aU) * (n - bU) + aD * bD * (n - aD) * (n - bD)
                    + 2 * aU * bU * aD * bD) / (n * n * (n - 1))
    if not calls:
        return None
    sd = math.sqrt(var) if var > 0 else 1e-12
    z = (hits - mean) / sd
    return {"hit": hits / calls, "placebo_mean": mean / calls, "placebo_sd": sd / calls, "z": z,
            "pct": 0.5 * (1 + math.erf(z / math.sqrt(2))),
            "p95": (mean + 1.6449 * sd) / calls, "p995": (mean + 2.5758 * sd) / calls}


def shuffle_test(rows, pred_key):
    return shuffle_from_strata([strata(rows, pred_key)])


def shuffle_monte_carlo(rows, pred_key, B=300, seed=SEED):
    """Brute-force check of shuffle_test's moments (self-test only)."""
    rng = random.Random(seed)
    by_day = {}
    for r in rows:
        by_day.setdefault(r["day"], []).append((r[pred_key], r["label"]))
    calls = sum(1 for r in rows if r[pred_key] in DIRS)
    out = []
    for _ in range(B):
        hits = 0
        for pairs in by_day.values():
            preds = [p for p, _ in pairs]
            rng.shuffle(preds)
            hits += sum(1 for p, (_, lab) in zip(preds, pairs) if p in DIRS and p == lab)
        out.append(hits / calls)
    mu = sum(out) / B
    return mu, math.sqrt(sum((x - mu) ** 2 for x in out) / (B - 1))


def day_bootstrap_edge(tables, B=2000, seed=SEED, lo_q=0.0025):
    """
    G2: accuracy minus the better no-skill control, resampling whole days.
    `tables` = list of day_table() outputs (one per symbol); a resampled day brings
    every symbol's rows for that day.
    """
    days = sorted({d for t in tables for d in t})
    agg = {d: [0, 0, 0, 0] for d in days}  # n, engine correct, clim correct, persist correct
    for t in tables:
        for d, x in t.items():
            a = agg[d]
            a[0] += x[0]
            a[1] += x[1]
            a[2] += x[7]
            a[3] += x[8]
    rows = [agg[d] for d in days]

    def edge(sample):
        n = sum(x[0] for x in sample) or 1
        e, c, p = (sum(x[i] for x in sample) / n for i in (1, 2, 3))
        return e - max(c, p)

    point = edge(rows)
    rng = random.Random(seed)
    draws = sorted(edge([rows[rng.randrange(len(rows))] for _ in rows]) for _ in range(B))
    return {"edge": point, "lo": draws[int(lo_q * B)], "hi": draws[int((1 - lo_q) * B) - 1]}


def calibration(rows):
    """E1's stated probability (10-point buckets) vs how often the call came true: raw [n, hits, sum p]."""
    from eng_core import outputs
    out = {}
    for r in rows:
        p = outputs(r["S"], 1.0, 0.0, 1)["prob"]
        k = "%s %d-%d%%" % ("SIDEWAYS" if r["call"] == "SIDEWAYS" else "UP/DOWN",
                            10 * int(p * 10), 10 * int(p * 10) + 10)
        x = out.setdefault(k, [0, 0, 0.0])
        x[0] += 1
        x[1] += r["call"] == r["label"]
        x[2] += p
    return out


def breakdown(rows, field, pred_key="call"):
    """Raw [n, correct, dir_calls, dir_hits] by regime / vol / bucket / family-sign pattern."""
    out = {}
    for r in rows:
        if field == "fam":
            k = " ".join(n + ("+" if v > 1e-9 else "-" if v < -1e-9 else "0") for n, v in zip("MRBC", r["fam"]))
        else:
            k = r[field]
        x = out.setdefault(k, [0, 0, 0, 0])
        x[0] += 1
        x[1] += r[pred_key] == r["label"]
        if r[pred_key] in DIRS:
            x[2] += 1
            x[3] += r[pred_key] == r["label"]
    return out


def merge_counts(dicts):
    out = {}
    for d in dicts:
        for k, v in d.items():
            x = out.setdefault(k, [0] * len(v))
            for i, a in enumerate(v):
                x[i] += a
    return out
