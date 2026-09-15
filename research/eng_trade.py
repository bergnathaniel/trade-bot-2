"""
Trading the engine's signals (PREREG_ENGINE.md, B "Execution" and gates G3-G5).
===============================================================================

Enter at the open of the minute bar that starts at D. Stop 1 x ATR14(5m), target
2 x ATR14(5m), time exit at the close of the 30th minute. A bar that touches both
stop and target counts as the stop. A bar that opens beyond the stop fills at that
open. One position per symbol; signals are ignored until it is closed.
"""

import random

from eng_core import REC_FIELDS

F = {k: i for i, k in enumerate(REC_FIELDS)}
COSTS = {"free": {"crypto": 0.0, "stock": 0.0},
         "low": {"crypto": 0.0005, "stock": 0.0001},
         "retail": {"crypto": 0.0035, "stock": 0.0002}}
LONG_ACTS, SHORT_ACTS = ("BUY", "STRONG BUY"), ("SELL", "STRONG SELL")
HOLD = 30
SEED = 20260911


def eligible(rec, m1):
    """A trade can be entered at D: ATR known, 30 full minutes of data, not after 15:25 ET."""
    D, i1, close_at = rec[F["D"]], rec[F["i1"]], rec[F["close_at"]]
    k_end = i1 + HOLD
    return (rec[F["atr5"]] is not None and k_end < len(m1.t) and m1.t[k_end] == D + (HOLD - 1) * 60
            and (close_at is None or D <= close_at - 35 * 60))


def outcome(rec, m1, side):
    """(gross return, epoch the position is closed) or None if the trade can't be entered."""
    if not eligible(rec, m1):
        return None
    i1, atr5 = rec[F["i1"]], rec[F["atr5"]]
    entry = m1.o[i1 + 1]
    stop, target = entry - side * atr5, entry + side * 2 * atr5
    for k in range(i1 + 1, i1 + HOLD + 1):
        o, h, l = m1.o[k], m1.h[k], m1.l[k]
        if side == 1:
            if o <= stop:
                px = o
            elif l <= stop:
                px = stop
            elif h >= target:
                px = target
            else:
                continue
        else:
            if o >= stop:
                px = o
            elif h >= stop:
                px = stop
            elif l <= target:
                px = target
            else:
                continue
        return side * (px / entry - 1.0), m1.t[k] + 60
    k = i1 + HOLD
    return side * (m1.c[k] / entry - 1.0), m1.t[k] + 60


def simulate(recs, m1, side_of, long_only=False):
    """side_of(rec) -> +1 / -1 / 0. Returns gross trades; costs are applied in stats()."""
    trades, busy_until = [], -1
    for rec in recs:
        D = rec[F["D"]]
        if D < busy_until:
            continue
        side = side_of(rec)
        if not side or (long_only and side < 0):
            continue
        res = outcome(rec, m1, side)
        if res is None:
            continue
        trades.append({"D": D, "day": rec[F["day"]], "side": side, "gross": res[0]})
        busy_until = res[1]
    return trades


def stats(trades, cost=0.0):
    rets = [t["gross"] - 2 * cost for t in trades]
    wins, losses = [x for x in rets if x > 0], [x for x in rets if x < 0]
    eq = peak = 1.0
    mdd = 0.0
    for x in rets:
        eq *= 1.0 + x
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1.0)
    return {"trades": len(rets), "win_rate": len(wins) / len(rets) if rets else None,
            "avg_trade": sum(rets) / len(rets) if rets else None,
            "gross_win": sum(wins), "gross_loss": -sum(losses),
            "pf": (sum(wins) / -sum(losses)) if losses else (float("inf") if wins else None),
            "total": eq - 1.0, "max_dd": mdd}


def pooled_pf(stat_list):
    w = sum(s["gross_win"] for s in stat_list)
    l_ = sum(s["gross_loss"] for s in stat_list)
    return w / l_ if l_ else (float("inf") if w else None)


def outcome_tables(recs, m1):
    """Zero-cost result of a long and a short trade at every eligible decision: [(day, gross)]."""
    longs, shorts = [], []
    for rec in recs:
        lo = outcome(rec, m1, 1)
        if lo is None:
            continue
        longs.append((rec[F["day"]], lo[0]))
        shorts.append((rec[F["day"]], outcome(rec, m1, -1)[0]))
    return longs, shorts


def random_entries(groups, engine_mean, B=1000, seed=SEED, days=None):
    """
    Placebo for G3. groups: [(longs, shorts, n_long, n_short)] per symbol. Each draw takes the
    same number of long and short trades per symbol at random decision times (with replacement).
    Returns the engine mean trade's percentile and the 95th percentile of the draws.
    """
    rng = random.Random(seed)
    pools = []
    for longs, shorts, nl, ns in groups:
        L = [g for d, g in longs if days is None or d in days]
        S = [g for d, g in shorts if days is None or d in days]
        pools.append((L, S, nl, ns))
    n = sum(nl + ns for _, _, nl, ns in pools)
    if not n:
        return None
    draws = []
    for _ in range(B):
        tot = 0.0
        for L, S, nl, ns in pools:
            if nl:
                tot += sum(L[rng.randrange(len(L))] for _ in range(nl))
            if ns:
                tot += sum(S[rng.randrange(len(S))] for _ in range(ns))
        draws.append(tot / n)
    draws.sort()
    return {"pct": sum(1 for x in draws if x < engine_mean) / B, "p95": draws[int(0.95 * B)],
            "placebo_mean": sum(draws) / B}


def buy_and_hold(recs, m1):
    if not recs:
        return None
    return m1.c[recs[-1][F["i1"]]] / recs[0][F["price"]] - 1.0
