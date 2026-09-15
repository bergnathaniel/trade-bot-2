"""
Shared stock-panel plumbing for the Phase-2 event hypotheses (H11-H13).
=====================================================================

Loads the frozen universe into one aligned open/close panel, builds the
equal-weighted no-signal control, labels events with strictly causal
percentile breakpoints, turns labelled events into long/short and long-only
series, and runs the event-level placebo. Rules: PREREG_PHASE2.md.
"""

import array
import bisect
import datetime as dt
import functools
import random
import types

import basket
import data
import evaluate
import p2data
import stats
from h_common import record, rf_list, yahoo

START = "2003-01-01"
COST = {"SP500": 0.0005, "SP400": 0.0010}
BORROW = 0.003
ELIGIBLE_AFTER = 252
MIN_PRIOR = 250
SPLICE_FIX = False  # PREREG_PHASE2.md amendment A1 (run_phase2.py --A1)
SPLICE_JUMP = 10.0

SURVIVOR_NOTE = ("Stock universe = today's S&P 500 and MidCap 400 members: firms that died, were acquired "
                 "or shrank out of the indexes are missing and firms that grew into them are present "
                 "(gate G10).")


def unsplice(o, c):
    """
    Amendment A1: a one-day close-to-close gain above x10 is a splice (e.g. bankrupt shares joined to the
    new equity). Every earlier open and close is multiplied by that day's factor, so earlier returns are
    unchanged and the splice day earns about zero. Declines are never adjusted. Returns [(index, factor)].
    """
    out, prev = [], None
    for i in range(len(c)):
        if c[i] > 0:
            if prev is not None and c[i] / c[prev] > SPLICE_JUMP:
                f = c[i] / c[prev]
                for k in range(i):
                    o[k] *= f
                    c[k] *= f
                out.append((i, f))
            prev = i
    return out


@functools.lru_cache(maxsize=None)
def panel():
    """The whole universe on SPY's calendar from 2003, prices as arrays (0.0 = no print)."""
    spy = yahoo("SPY")
    dates = [d for d in spy["dates"] if d >= START]
    n = len(dates)
    pos = {d: i for i, d in enumerate(dates)}
    spy_close = dict(zip(spy["dates"], spy["close"]))
    O, C, first, cost, index, cik_sym, sym_cik = {}, {}, {}, {}, {}, {}, {}
    splices = []
    for m in p2data.universe()["members"]:
        bars = data.fetch(m["yahoo"], quiet=True)
        if not bars:
            continue
        o, c = array.array("d", bytes(8 * n)), array.array("d", bytes(8 * n))
        got = 0
        for b in bars:
            i = pos.get(data._ymd(b[0]))
            if i is not None and b[1] > 0 and b[4] > 0:
                o[i], c[i] = b[1], b[4]
                got += 1
        if got < ELIGIBLE_AFTER + 60:
            continue
        s = m["yahoo"]
        if SPLICE_FIX:
            splices += [(s, dates[i], round(f, 2)) for i, f in unsplice(o, c)]
        first_day = data._ymd(bars[0][0])
        first[s] = -ELIGIBLE_AFTER if first_day < START else bisect.bisect_left(dates, first_day)
        O[s], C[s] = o, c
        cost[s] = COST[m["index"]]
        index[s] = m["index"]
        cik_sym[int(m["cik"])] = s
        sym_cik[s] = int(m["cik"])
    months = []
    for i, d in enumerate(dates):
        if months and months[-1][0] == d[:7]:
            months[-1][2] = i
        else:
            months.append([d[:7], i, i])
    ew, ew_n = basket.ew_universe(dates, C, {s: max(1, first[s] + ELIGIBLE_AFTER) for s in C})
    ewp = [1.0]
    for x in ew:
        ewp.append(ewp[-1] * (1 + x))
    return types.SimpleNamespace(
        dates=dates, n=n, pos=pos, O=O, C=C, first=first, cost=cost, index=index,
        cik_sym=cik_sym, sym_cik=sym_cik, spy=[spy_close.get(d) for d in dates],
        rf=rf_list(dates), ew=ew, ew_n=ew_n, ewp=ewp, months=months, splices=splices)


def eligible(P, s, i):
    return i >= P.first[s] + ELIGIBLE_AFTER


def before_date(P, cut):
    """Truncation boundary: information dated strictly before the session after `cut`."""
    return None if cut is None else (P.dates[cut + 1] if cut + 1 < P.n else "9999-12-31")


# ------------------------------------------------------------------ labelling

def _quantile(vals, q):
    k = (len(vals) - 1) * q
    f = int(k)
    c = min(f + 1, len(vals) - 1)
    return vals[f] + (vals[c] - vals[f]) * (k - f)


def label(P, events, lo=0.2, hi=0.8, days=365, min_prior=MIN_PRIOR):
    """
    Copy of `events` with side in {long, short, mid, None}. Each event's cut-offs
    use ONLY events known before its entry session and within `days` calendar days.
    """
    events = [dict(e) for e in events]
    by_known = sorted(events, key=lambda e: e["known"])
    window, add, drop = [], 0, 0
    for e in sorted(events, key=lambda e: (e["entry"], e["sym"])):
        cutoff = (dt.date.fromisoformat(P.dates[e["entry"]]) - dt.timedelta(days=days)).isoformat()
        while add < len(by_known) and by_known[add]["known"] < e["entry"]:
            bisect.insort(window, by_known[add]["signal"])
            add += 1
        while drop < add and P.dates[by_known[drop]["known"]] < cutoff:
            window.pop(bisect.bisect_left(window, by_known[drop]["signal"]))
            drop += 1
        if len(window) >= min_prior:
            e["p_lo"], e["p_hi"] = _quantile(window, lo), _quantile(window, hi)
            e["side"] = ("long" if e["signal"] >= e["p_hi"] else
                         "short" if e["signal"] <= e["p_lo"] else "mid")
        else:
            e["side"] = None
    return events


def intervals(P, events, side, hold):
    return [(e["sym"], e["entry"], min(e["entry"] + hold - 1, P.n - 1))
            for e in events if e.get("side") == side]


def entry_vector(P, labelled):
    """Per session, the (symbol, side) decisions taken at its open - for the truncation test."""
    by = {}
    for e in labelled:
        if e.get("side") in ("long", "short"):
            by.setdefault(e["entry"], []).append((e["sym"], e["side"]))
    W = [None] * P.n
    for i, v in by.items():
        W[i] = tuple(sorted(v))
    return W


# --------------------------------------------------------------------- series

def series(P, long_iv, short_iv):
    """Long/short and long-only daily series (see PREREG_PHASE2.md section A)."""
    L = basket.simulate(P.dates, P.O, P.C, long_iv, P.cost)
    S = basket.simulate(P.dates, P.O, P.C, short_iv, P.cost)
    D, ew, rf = L["dates"], P.ew, P.rf[1:]
    begin = next((i for i, (a, b) in enumerate(zip(L["n"], S["n"])) if a and b), len(D))
    lo_begin = next((i for i, a in enumerate(L["n"]) if a), len(D))
    ls_net, ls_gross, ls_2x = [], [], []
    for i in range(begin, len(D)):
        has_l, has_s = L["n"][i] > 0, S["n"][i] > 0
        lg, lc = (L["gross"][i], L["gross"][i] - L["net"][i]) if has_l else (ew[i], 0.0)
        sg, sc = (S["gross"][i], S["gross"][i] - S["net"][i]) if has_s else (ew[i], 0.0)
        borrow = BORROW / 252 if has_s else 0.0
        ls_gross.append(lg - sg)
        ls_net.append(lg - sg - lc - sc - borrow)
        ls_2x.append(lg - sg - 2 * (lc + sc) - borrow)
    rng = range(lo_begin, len(D))
    return {
        "ls_dates": D[begin:], "ls_net": ls_net, "ls_gross": ls_gross, "ls_2x": ls_2x,
        "lo_dates": D[lo_begin:],
        "lo_net": [L["net"][i] - ew[i] for i in rng],
        "lo_gross": [L["gross"][i] - ew[i] for i in rng],
        "lo_2x": [2 * L["net"][i] - L["gross"][i] - ew[i] for i in rng],
        "alpha_y": [L["net"][i] - rf[i] for i in rng],
        "lo_rf": rf[lo_begin:], "lo_turnover": L["turnover"][lo_begin:],
        "avg_long_names": stats.mean(L["n"][lo_begin:]) if rng else 0.0,
        "avg_short_names": stats.mean(S["n"][begin:]) if begin < len(D) else 0.0,
    }


# -------------------------------------------------------------------- placebo

def event_return(P, e, hold):
    """60-session abnormal return used by the event placebo: stock close-to-close minus EW universe."""
    s, a = e["sym"], e["entry"]
    b = a + hold - 1
    if b >= P.n:
        return None
    ca, cb = P.C[s][a], P.C[s][b]
    if not ca or not cb:
        return None
    return cb / ca - 1 - (P.ewp[b] / P.ewp[a] - 1)


def event_placebo(P, labelled, oos, hold, draws=1000):
    rows = []
    for e in labelled:
        if e.get("side") and P.dates[e["entry"]] >= oos:
            x = event_return(P, e, hold)
            if x is not None:
                rows.append((e["signal"], e["p_lo"], e["p_hi"], x))
    if len(rows) < 100:
        return None

    def spread(signals):
        hi = lo = tot = 0.0
        nh = nl = 0
        for sig, (_, p_lo, p_hi, x) in zip(signals, rows):
            tot += x
            if sig >= p_hi:
                hi += x
                nh += 1
            elif sig <= p_lo:
                lo += x
                nl += 1
        if not nh or not nl:
            return 0.0, 0.0
        return hi / nh - lo / nl, hi / nh - tot / len(rows)

    actual = spread([r[0] for r in rows])
    sig = [r[0] for r in rows]
    rng = random.Random(evaluate.SEED_PLACEBO)
    ls_draws, lo_draws = [], []
    for _ in range(draws):
        rng.shuffle(sig)
        a, b = spread(sig)
        ls_draws.append(a)
        lo_draws.append(b)
    buckets = {}
    for side in ("long", "mid", "short"):
        xs = [x for (s_, p_lo, p_hi, x) in rows
              if (side == "long" and s_ >= p_hi) or (side == "short" and s_ <= p_lo)
              or (side == "mid" and p_lo < s_ < p_hi)]
        buckets[side] = {"events": len(xs), "mean_abnormal_return_pct": round(stats.mean(xs) * 100, 3) if xs else None}
    return {"ls_actual": actual[0], "lo_actual": actual[1], "ls": ls_draws, "lo": lo_draws,
            "events": len(rows), "oos_buckets": buckets}


# -------------------------------------------------------------------- records

def pair_records(P, *, hid, cluster, base, neighbours, placebo, oos, texts, leak, extra,
                 notes, unregistered):
    """The -LS and -LO records for one stock hypothesis."""
    ext = dict(extra, avg_long_names=round(base["avg_long_names"], 1),
               avg_short_names=round(base["avg_short_names"], 1))
    common = dict(cluster=cluster, periods=252, oos_start=oos, bench="SPY",
                  survivor_universe=True, leakage=leak, data=texts["data"],
                  notes=[SURVIVOR_NOTE] + notes, unregistered=unregistered)
    ls = record(id=f"{hid}-LS", name=texts["ls_name"], hypothesis=texts["ls_hyp"], costs=texts["ls_costs"],
                dates=base["ls_dates"], net=base["ls_net"], gross=base["ls_gross"], net_2x=base["ls_2x"],
                neighbours=[(nm, s["ls_dates"], s["ls_net"]) for nm, s in neighbours],
                placebo=placebo["ls"], placebo_actual=placebo["ls_actual"], implementable=False,
                extra=dict(ext, placebo=placebo.get("describe", "")), **common)
    lo = record(id=f"{hid}-LO", name=texts["lo_name"], hypothesis=texts["lo_hyp"], costs=texts["lo_costs"],
                dates=base["lo_dates"], net=base["lo_net"], gross=base["lo_gross"], net_2x=base["lo_2x"],
                alpha_y=base["alpha_y"], rf=base["lo_rf"], turnover=base["lo_turnover"],
                neighbours=[(nm, s["lo_dates"], s["lo_net"]) for nm, s in neighbours],
                placebo=placebo["lo"], placebo_actual=placebo["lo_actual"], implementable=True,
                extra=dict(ext, placebo=placebo.get("describe", "")), **common)
    return [ls, lo]
