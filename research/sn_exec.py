"""
Execution, exits, risk and books for the sniper-system test (PREREG_SNIPER.md, sections E-H).
============================================================================================

  exit_path()      one trade through the exit engine: fill, R, partial fills, exit time
  attach_outcomes()  exit_path for every signal once; costs are applied afterwards
  s4_flags()       config S4's "favor the setups that make money" filter, one causal pass
  book_symbol()    S1 / S2 / S4 account for one symbol at one cost level
  book_scanner()   S3 shared account for a group
  placebo_values() random entries through the identical exit engine (G2)
  day_bootstrap(), placebo_test(), r_stats(), account_stats()

A trade's price path doesn't depend on the cost level, so it is simulated once. Costs, the
cost veto, sizing and the daily loss limit are applied per book.
"""

import bisect
import math
import random
from collections import Counter

SEED = 20260911
HOLD = 120
TRAIL_ATR = 1.0
DAY = 86400
COSTS = {"free": {"crypto": 0.0, "stock": 0.0},
         "low": {"crypto": 0.0005, "stock": 0.0001},
         "retail": {"crypto": 0.0035, "stock": 0.0002},
         "retail2x": {"crypto": 0.0070, "stock": 0.0004}}
LEVELS = ("free", "low", "retail", "retail2x")
RISK_NORMAL, RISK_STRONG, STRONG_SCORE = 0.005, 0.010, 85
DAILY_LIMIT = 0.02
VETO_SHARE = 0.25
N_PLACEBO = 20
SCAN_MAX_POS, SCAN_MAX_RISK = 2, 0.010
OPEN_EXITS = ("gap_stop", "invalidation", "blackout")


class Trade:
    __slots__ = ("fill", "R", "gpu", "tex", "exit_t", "reason", "stage", "mfe", "mae")

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    def r_after(self, cost):
        """Result in R after `cost` per side on every fill."""
        return (self.gpu - cost * self.tex) / self.R


# ------------------------------------------------------------------ the exit engine

def exit_path(m1, c5_done, k0, side, X, V, A, close_at, blackouts, P=None, hold=HOLD, tp_mode="scale"):
    """
    Enter at the open of 1m bar k0 and walk forward (PREREG_SNIPER section E).
    Returns a Trade, or a string saying why there is no trade ("chase", "beyond_stop",
    "no_data"). `blackouts` = (sorted starts, matching ends). `P` = ideal entry; None skips
    the don't-chase check (placebos have no ideal entry). V = None: no thesis invalidation.
    tp_mode: "scale" (the prompt: 1/3 at 1R/2R/3R, breakeven, trailing), "fixed2" (all at 2R),
    "none" (no target). `hold` = time exit in minutes (PREREG_SEARCH section C).
    """
    t, o, h, l, c = m1.t, m1.o, m1.h, m1.l, m1.c
    n = len(t)
    if k0 >= n:
        return "no_data"
    D, fill = t[k0], o[k0]
    if P is not None and side * (fill - P) > 0.5 * A:
        return "chase"
    if side * (fill - X) <= 0:
        return "beyond_stop"
    R = abs(fill - X)
    scale = tp_mode == "scale"
    if scale:
        tps = (fill + side * R, fill + 2 * side * R, fill + 3 * side * R)
    elif tp_mode == "fixed2":
        tps = (fill + 2 * side * R,)
    else:
        tps = ()
    ntp = len(tps)
    bl_s, bl_e = blackouts
    j = bisect.bisect_left(bl_s, D)
    stop, stage, rem = X, 0, 1.0
    gpu = tex = 0.0
    ext, best, worst = fill, 0.0, 0.0
    inval_next = False
    last = k0 + hold - 1
    k = k0
    while True:
        if k >= n or t[k] != D + 60 * (k - k0):
            return "no_data"
        tk = t[k]
        px = reason = None
        while j < len(bl_s) and bl_e[j] <= tk:
            j += 1
        if j < len(bl_s) and bl_s[j] <= tk < bl_e[j]:
            px, reason = o[k], "blackout"
        elif inval_next:
            px, reason = o[k], "invalidation"
        elif side * (o[k] - stop) <= 0:
            px, reason = o[k], "gap_stop"
        elif (side > 0 and l[k] <= stop) or (side < 0 and h[k] >= stop):
            px, reason = stop, "stop" if stage == 0 else "breakeven" if stage == 1 else "trail"
        fav_px, adv_px = (h[k], l[k]) if side > 0 else (l[k], h[k])
        if px is None or reason in ("stop", "breakeven", "trail"):
            best = max(best, side * (fav_px - fill))
            worst = min(worst, side * (adv_px - fill))
        if px is not None:
            gpu += rem * side * (px - fill)
            tex += rem * px
            break
        while stage < ntp and side * (fav_px - tps[stage]) >= 0:
            q = rem if stage == ntp - 1 else 1.0 / 3.0
            gpu += q * side * (tps[stage] - fill)
            tex += q * tps[stage]
            rem -= q
            stage += 1
        if ntp and stage == ntp:
            reason = "tp3" if scale else "target"
            break
        if scale:
            ext = max(ext, h[k]) if side > 0 else min(ext, l[k])
            if stage >= 1:
                stop = max(stop, fill) if side > 0 else min(stop, fill)
            if stage >= 2:
                lock, trail = fill + side * R, ext - side * TRAIL_ATR * A
                stop = max(stop, lock, trail) if side > 0 else min(stop, lock, trail)
        end = tk + 60
        if k == last or (close_at is not None and end >= close_at):
            gpu += rem * side * (c[k] - fill)
            tex += rem * c[k]
            reason = "time" if k == last else "session"
            break
        if V is not None:
            cl5 = c5_done.get(end)
            if cl5 is not None and side * (cl5 - V) < 0:
                inval_next = True
        k += 1
    exit_t = t[k] if reason in OPEN_EXITS else t[k] + 60
    return Trade(fill=fill, R=R, gpu=gpu, tex=fill + tex, exit_t=exit_t, reason=reason, stage=stage,
                 mfe=best / R, mae=worst / R)


def attach_outcomes(sigs, ctx):
    t = ctx.m1.t
    for sg in sigs:
        k0 = sg.i1 + 1
        sg.out = ("no_data" if k0 >= len(t) or t[k0] != sg.D else
                  exit_path(ctx.m1, ctx.c5_done, k0, sg.side, sg.X, sg.V, sg.A, sg.close_at, ctx.blackouts, P=sg.P))


def vetoed(sg, cost):
    return cost > 0 and 2 * cost * sg.price > VETO_SHARE * sg.risk


# ------------------------------------------------------------------ S4 filter

def s4_flags(group_sigs, kind, level, thr=70, window_days=60, min_n=30):
    """
    {id(signal): allowed} for every signal with score >= thr in the group, in one time-ordered
    pass. The shadow record of a (setup, side) type = qualifying, un-vetoed signals simulated on
    their own whose exit completed by D and whose entry is within the trailing window.
    """
    cost = COSTS[level][kind]
    qual = sorted((sg for sg in group_sigs if sg.score >= thr), key=lambda s: (s.D, s.sym))
    shadow = [(sg.out.exit_t, sg.D, (sg.setup, sg.side), sg.out.r_after(cost))
              for sg in qual if isinstance(sg.out, Trade) and not vetoed(sg, cost)]
    by_exit = sorted(shadow, key=lambda x: (x[0], x[1]))
    by_entry = sorted(shadow, key=lambda x: (x[1], x[0]))
    tally, added, a, r, flags = {}, set(), 0, 0, {}
    for sg in qual:
        D = sg.D
        while a < len(by_exit) and by_exit[a][0] <= D:
            x = by_exit[a]
            s = tally.setdefault(x[2], [0, 0.0])
            s[0] += 1
            s[1] += x[3]
            added.add(id(x))
            a += 1
        while r < len(by_entry) and by_entry[r][1] < D - window_days * DAY:
            x = by_entry[r]
            if id(x) in added:
                s = tally[x[2]]
                s[0] -= 1
                s[1] -= x[3]
                added.discard(id(x))
            r += 1
        n, tot = tally.get((sg.setup, sg.side), (0, 0.0))
        flags[id(sg)] = n >= min_n and tot / n > 0
    return flags


# ------------------------------------------------------------------ books

class Account:
    """Closed-trade equity, the day's starting equity and P&L, and the closes (for stats)."""

    def __init__(self, day_of):
        self.E, self.day_of = 1.0, day_of
        self.day_start, self.day_pnl, self.closes = {}, {}, []

    def close(self, exit_t, pnl):
        d = self.day_of(exit_t)
        self.day_start.setdefault(d, self.E)
        self.day_pnl[d] = self.day_pnl.get(d, 0.0) + pnl
        self.E += pnl
        self.closes.append((exit_t, pnl, self.E))

    def halted(self, d):
        return self.day_pnl.get(d, 0.0) <= -DAILY_LIMIT * self.day_start.get(d, self.E)


def _take(sg, tr, cost, E, cash):
    rp = RISK_STRONG if sg.score >= STRONG_SCORE else RISK_NORMAL
    units = min(rp * E / tr.R, cash / tr.fill)
    return {"sym": sg.sym, "D": sg.D, "day": sg.day, "setup": sg.setup, "side": sg.side, "score": sg.score,
            "regime": sg.regime, "risk_pct": rp, "fill": tr.fill, "R": tr.R, "r": tr.r_after(cost),
            "r_gross": tr.r_after(0.0), "pnl": units * (tr.gpu - cost * tr.tex), "notional": units * tr.fill,
            "E_before": E, "exit_t": tr.exit_t, "reason": tr.reason, "stage": tr.stage,
            "hold_min": (tr.exit_t - sg.D) / 60, "mfe": tr.mfe, "mae": tr.mae, "sig": sg}


def book_symbol(sigs, kind, level, thr, day_of, flags=None, long_only=False):
    """One symbol's account (S1, S2, S4). sigs in time order with .out attached."""
    cost = COSTS[level][kind]
    acct, trades, blocked, open_ = Account(day_of), [], Counter(), None
    for sg in sigs:
        if sg.score < thr or (long_only and sg.side < 0):
            continue
        if open_ is not None and open_["exit_t"] <= sg.D:
            acct.close(open_["exit_t"], open_["pnl"])
            open_ = None
        if open_ is not None:
            blocked["busy"] += 1
        elif acct.halted(sg.day):
            blocked["daily_limit"] += 1
        elif vetoed(sg, cost):
            blocked["cost_veto"] += 1
        elif flags is not None and not flags.get(id(sg)):
            blocked["s4_filter"] += 1
        elif not isinstance(sg.out, Trade):
            blocked[sg.out] += 1
        else:
            open_ = _take(sg, sg.out, cost, acct.E, acct.E)
            trades.append(open_)
    if open_ is not None:
        acct.close(open_["exit_t"], open_["pnl"])
    return trades, blocked, acct


def book_scanner(group_sigs, kind, level, day_of, sym_order, thr=70, long_only=False):
    """S3: one account for the group; best scanner score first; <= 2 positions, <= 1% open risk."""
    cost = COSTS[level][kind]
    rank = {s: i for i, s in enumerate(sym_order)}
    qual = sorted((sg for sg in group_sigs if sg.score >= thr and not (long_only and sg.side < 0)),
                  key=lambda s: (s.D, -s.scan, rank[s.sym]))
    acct, trades, blocked, pos = Account(day_of), [], Counter(), []
    for sg in qual:
        for p in sorted((p for p in pos if p["exit_t"] <= sg.D), key=lambda p: p["exit_t"]):
            acct.close(p["exit_t"], p["pnl"])
        pos = [p for p in pos if p["exit_t"] > sg.D]
        rp = RISK_STRONG if sg.score >= STRONG_SCORE else RISK_NORMAL
        cash = acct.E - sum(p["notional"] for p in pos)
        if any(p["sym"] == sg.sym for p in pos):
            blocked["busy"] += 1
        elif len(pos) >= SCAN_MAX_POS:
            blocked["max_positions"] += 1
        elif sum(p["risk_pct"] for p in pos) + rp > SCAN_MAX_RISK + 1e-12:
            blocked["risk_cap"] += 1
        elif acct.halted(sg.day):
            blocked["daily_limit"] += 1
        elif vetoed(sg, cost):
            blocked["cost_veto"] += 1
        elif not isinstance(sg.out, Trade):
            blocked[sg.out] += 1
        elif cash <= 0:
            blocked["no_cash"] += 1
        else:
            p = _take(sg, sg.out, cost, acct.E, cash)
            pos.append(p)
            trades.append(p)
    for p in sorted(pos, key=lambda p: p["exit_t"]):
        acct.close(p["exit_t"], p["pnl"])
    return trades, blocked, acct


# ------------------------------------------------------------------ placebo (G2)

def placebo_values(sg, ctx, pool, n=N_PLACEBO):
    """
    `n` zero-cost results (in R) of random entries for one real trade: same symbol and side, same
    stop and invalidation distance in ATR units, identical exits. Entry times are drawn from `pool`,
    that symbol's eligible decisions in the trade's half: [(D, i1, close_at, ATR14 5m)].
    """
    if not pool:
        return []
    m1 = ctx.m1
    kx, kv = sg.out.R / sg.A, sg.side * (sg.out.fill - sg.V) / sg.A
    rng = random.Random(f"{SEED}-{sg.sym}-{sg.D}-{sg.side}")
    vals, tries = [], 0
    while len(vals) < n and tries < 20 * n:
        tries += 1
        D, i1, close_at, A = pool[rng.randrange(len(pool))]
        k0 = i1 + 1
        if k0 >= len(m1.t) or m1.t[k0] != D:
            continue
        f = m1.o[k0]
        res = exit_path(m1, ctx.c5_done, k0, sg.side, f - sg.side * kx * A, f - sg.side * kv * A, A, close_at,
                        ctx.blackouts)
        if isinstance(res, Trade):
            vals.append(res.r_after(0.0))
    return vals


def placebo_test(real, pools, B=2000, seed=SEED):
    pools = [p for p in pools if p]
    if not real or not pools:
        return None
    rng = random.Random(seed)
    n = len(pools)
    draws = []
    for _ in range(B):
        s = 0.0
        for p in pools:
            s += p[int(rng.random() * len(p))]
        draws.append(s / n)
    draws.sort()
    m = sum(real) / len(real)
    return {"mean": m, "placebo_mean": sum(draws) / B, "p95": draws[int(0.95 * B)],
            "p995": draws[min(B - 1, int(0.995 * B))], "pct": sum(1 for x in draws if x < m) / B}


# ------------------------------------------------------------------ statistics

def r_stats(rs):
    n = len(rs)
    if not n:
        return {"n": 0, "mean": None, "win_rate": None, "avg_win": None, "avg_loss": None, "pf": None}
    w = [x for x in rs if x > 0]
    ls = [x for x in rs if x < 0]
    gl = -sum(ls)
    return {"n": n, "mean": sum(rs) / n, "win_rate": len(w) / n, "avg_win": sum(w) / len(w) if w else None,
            "avg_loss": -gl / len(ls) if ls else None,
            "pf": sum(w) / gl if gl > 0 else (float("inf") if w else None)}


def day_bootstrap(trades, key="r", B=2000, seed=SEED, lo_q=0.0025):
    by_day = {}
    for t in trades:
        x = by_day.setdefault(t["day"], [0.0, 0])
        x[0] += t[key]
        x[1] += 1
    days = list(by_day.values())
    if not days:
        return None
    rng = random.Random(seed)
    draws = []
    for _ in range(B):
        s = n = 0
        for _ in days:
            x = days[rng.randrange(len(days))]
            s += x[0]
            n += x[1]
        draws.append(s / n)
    draws.sort()
    return {"lo": draws[int(lo_q * B)], "hi": draws[int((1 - lo_q) * B) - 1]}


def account_stats(acct, eval_days, periods_per_year):
    eq, peak, mdd = 1.0, 1.0, 0.0
    for _, _, e in acct.closes:
        peak = max(peak, e)
        mdd = min(mdd, e / peak - 1.0)
    rets = []
    for d in eval_days:
        pnl = acct.day_pnl.get(d, 0.0)
        rets.append(pnl / acct.day_start[d] if d in acct.day_start else 0.0)
    n = len(rets)
    mu = sum(rets) / n if n else 0.0
    sd = math.sqrt(sum((x - mu) ** 2 for x in rets) / (n - 1)) if n > 1 else 0.0
    dn = math.sqrt(sum(min(x, 0.0) ** 2 for x in rets) / n) if n else 0.0
    ann = math.sqrt(periods_per_year)
    return {"return": acct.E - 1.0, "max_dd": mdd, "sharpe": mu / sd * ann if sd > 0 else None,
            "sortino": mu / dn * ann if dn > 0 else None, "halted_days": sum(1 for d in acct.day_pnl if acct.halted(d))}
