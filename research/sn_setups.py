"""
Levels, setups and scores for the sniper-system test (PREREG_SNIPER.md, sections A-D).
=====================================================================================

  catalysts()     scheduled CPI and jobs releases (08:30 ET, BLS archive) and FOMC statements
                  (14:00 ET, federalreserve.gov) -> the blackout windows
  Context         one symbol's bars, the engine's indicator arrays, session levels and the
                  lookups the exit engine needs
  Bench           what the other symbols need from the benchmark (15m trend, 1m closes)
  run(ctx, bench) walks the 5-minute decisions. Skips stale data, blackouts and warm-up,
                  finds the eight setups on the 5m bar that just closed, applies the regime
                  blocks and stop bounds, scores what is left and keeps the best one.
                  mode="all" (PREREG_SEARCH.md B) keeps every setup that fires, flags the best,
                  and adds the MOM and REV families.

Every value a decision uses comes from bars closed by D. selftest_sniper.py and
selftest_search.py hold the whole thing to that with the truncation test.
"""

import bisect
import datetime as dt
import math
import os
import re
from collections import Counter

import certifi
import requests

import data
import eng_core
import eng_ind as ind
import eng_tf
import intraday
import sources

DAY = 86400
SETUPS = ("BRK", "RET", "SRR", "SWP", "VWR", "PBK", "MRV", "BOS")
SETUP_NAMES = {"BRK": "breakout", "RET": "breakout retest", "SRR": "support/resistance rejection",
               "SWP": "liquidity sweep reversal", "VWR": "VWAP reclaim/rejection", "PBK": "trend pullback",
               "MRV": "range mean reversion", "BOS": "structure break", "MOM": "60-minute momentum",
               "REV": "15-minute reversal"}
FADES = ("SRR", "SWP", "MRV")
INDEX_ETFS = ("SPY", "QQQ", "IWM", "DIA")
CATS = ("strong_with", "weak_with", "range", "rev_with", "unknown", "rev_against", "weak_against",
        "strong_against")
_TREND_FIT = (10, 7, 4, 5, 3, 2, 2, 0)
_FADE_FIT = (6, 6, 10, 7, 4, 3, 3, 0)
FIT = {"BRK": (10, 7, 6, 5, 3, 2, 2, 0), "BOS": (10, 7, 6, 5, 3, 2, 2, 0), "RET": _TREND_FIT,
       "VWR": _TREND_FIT, "PBK": _TREND_FIT, "SRR": _FADE_FIT, "SWP": _FADE_FIT, "MRV": _FADE_FIT,
       "MOM": (10, 7, 6, 5, 3, 2, 2, 0), "REV": _FADE_FIT}
PARTS = ("trend", "momentum", "volume", "structure", "liquidity", "entry", "risk_reward", "regime")
BLS = "https://www.bls.gov/bls/news-release/{}.htm"
PULL_DATE = "20260911"


# ------------------------------------------------------------------ catalysts

def _bls_archive(name):
    path = os.path.join(data.CACHE, f"bls_{name}_archive_{PULL_DATE}.html")
    if not os.path.exists(path):
        r = requests.get(BLS.format(name), timeout=60, verify=certifi.where(),
                         headers={**data.UA, "Accept": "text/html", "Accept-Language": "en-US"})
        r.raise_for_status()
        with open(path, "w") as f:
            f.write(r.text)
    with open(path) as f:
        return f.read()


def _et(y, m, d, hh, mm):
    return int(dt.datetime(y, m, d, hh, mm, tzinfo=intraday.ET).timestamp())


def catalysts():
    """Sorted [(epoch, label)]. A release's date is its archive PDF's date."""
    ev = set()
    for name, label in (("cpi", "CPI"), ("empsit", "jobs")):
        for mm, dd, yy in re.findall(rf"/news\.release/archives/{name}_(\d\d)(\d\d)(\d{{4}})\.pdf", _bls_archive(name)):
            ev.add((_et(int(yy), int(mm), int(dd), 8, 30), label))
    for d in sources.fomc_statement_dates(2025)[0]:
        y, m, dd = (int(x) for x in d.split("-"))
        ev.add((_et(y, m, dd, 14, 0), "FOMC"))
    return sorted(ev)


def blackouts(events, pad=1800):
    return [t - pad for t, _ in events], [t + pad for t, _ in events]


# ------------------------------------------------------------------ data

def load_market(sym, kind):
    if kind == "crypto":
        raw = intraday.coinbase_1m(sym, eng_tf.CRYPTO_START, eng_tf.CRYPTO_END, quiet=True)
        return eng_tf.crypto_from_rows(sym, raw, eng_tf.CRYPTO_START + eng_tf.WARMUP_DAYS * DAY)
    return eng_tf.stock(sym)


def day_of_fn(kind):
    """Day key of an epoch, matching the decisions' day keys (the bar that closed at t)."""
    if kind == "crypto":
        return lambda t: (t - 1) // DAY
    return lambda t: intraday.et(t - 1).date().toordinal()


class Context:
    def __init__(self, market, blk):
        self.market, self.sym, self.kind = market, market.sym, market.kind
        self.tf = {name: eng_core.TF(market, name) for name in ("1m", "5m", "15m", "60m")}
        self.m1 = market.tf["1m"]
        self.blackouts = blk
        s5, s60 = market.tf["5m"], market.tf["60m"]
        self.c5_done = dict(zip(s5.done, s5.c))
        self.h60, self.l60 = ind.rolling_max(s60.h, 20), ind.rolling_min(s60.l, 20)
        n = len(s5)
        self.sess_hi, self.sess_lo = [None] * n, [None] * n
        self.or_hi, self.or_lo = [None] * n, [None] * n
        self.since_anchor = [0] * n
        cur = hi = lo = None
        by_day, opens = {}, {}
        for i in range(n):
            d = s5.day[i]
            if d != cur:
                cur, hi, lo = d, None, None
            self.sess_hi[i], self.sess_lo[i] = hi, lo
            hi = s5.h[i] if hi is None else max(hi, s5.h[i])
            lo = s5.l[i] if lo is None else min(lo, s5.l[i])
            if market.kind == "crypto":
                self.since_anchor[i] = s5.t[i] - d * DAY
            else:
                if d not in opens:
                    opens[d] = intraday.session_bounds(dt.date.fromordinal(d))[0]
                self.since_anchor[i] = s5.t[i] - opens[d]
                by_day.setdefault(d, []).append(i)
        for d, idx in by_day.items():
            o = opens[d]
            first = [i for i in idx if s5.t[i] in (o, o + 300, o + 600)]
            if len(first) == 3:
                ohi, olo = max(s5.h[i] for i in first), min(s5.l[i] for i in first)
                for i in idx:
                    if s5.t[i] >= o + 900:
                        self.or_hi[i], self.or_lo[i] = ohi, olo


class Bench:
    def __init__(self, ctx):
        t15 = ctx.tf["15m"]
        self.done15, self.e9, self.e21, self.atr15 = t15.s.done, t15.e9, t15.e21, t15.atr
        self.c1 = ctx.m1.c
        self.idx1 = {t: i for i, t in enumerate(ctx.m1.t)}


class Signal:
    __slots__ = ("sym", "D", "day", "i1", "close_at", "setup", "side", "score", "scan", "parts", "rs", "price",
                 "A", "P", "X", "V", "risk", "regime", "tr15", "cat", "best", "out", "placebo")

    def __init__(self, **kw):
        self.out = self.placebo = self.cat = None
        self.best = True
        for k, v in kw.items():
            setattr(self, k, v)


# ------------------------------------------------------------------ setups (long written, short mirrored)

def regime_cat(reg, s, rev_dir):
    if reg in ("STRONG BULL", "BREAKOUT"):
        return "strong_with" if s > 0 else "strong_against"
    if reg in ("STRONG BEAR", "BREAKDOWN"):
        return "strong_with" if s < 0 else "strong_against"
    if reg == "WEAK BULL":
        return "weak_with" if s > 0 else "weak_against"
    if reg == "WEAK BEAR":
        return "weak_with" if s < 0 else "weak_against"
    if reg == "RANGE":
        return "range"
    if reg == "REVERSAL":
        return "rev_with" if s == rev_dir else "rev_against"
    return "unknown"


def detect(name, s, i, k, A, keys, ph20, pl20, ctx):
    """(P*, X, V) if setup `name` fires on 5m bar i for side s, else None."""
    t5, t15 = ctx.tf["5m"], ctx.tf["15m"]
    s5 = t5.s
    o, h, l, c, v = s5.o[i], s5.h[i], s5.l[i], s5.c[i], s5.v[i]
    adv = l if s > 0 else h
    worst = min if s > 0 else max
    lows = s5.l if s > 0 else s5.h
    tick = s * 0.1 * A

    if name == "BRK":
        L, pa = (ph20 if s > 0 else pl20), t5.atr[i - 1]
        if L is None or pa is None or s * (c - L) <= 0 or v < 1.5 * t5.vsma[i] or ph20 - pl20 > 5 * pa:
            return None
        return L, worst(adv, L) - tick, L - tick

    if name == "RET":
        for j in range(i - 2, i - 13, -1):
            Lj = t5.ph[j] if s > 0 else t5.pl[j]
            if Lj is not None and t5.vsma[j] and s * (s5.c[j] - Lj) > 0 and s5.v[j] >= 1.5 * t5.vsma[j]:
                K = Lj
                break
        else:
            return None
        if any(s * (s5.c[x] - (K - s * 0.25 * A)) < 0 for x in range(j + 1, i + 1)):
            return None
        if s * (adv - (K + s * 0.25 * A)) > 0 or s * (c - K) <= 0 or s * (c - o) <= 0:
            return None
        return K, worst(lows[j + 1:i + 1]) - tick, K - s * 0.25 * A

    if name in ("SRR", "SWP"):
        cands = [x for x in keys if s * (c - x) > 0]
        L20 = pl20 if s > 0 else ph20
        if L20 is not None and s * (c - L20) > 0:
            cands.append(L20)
        if name == "SRR":
            rng = h - l
            body = abs(c - o)
            if rng <= 0:
                return None
            if s > 0 and (c - l < rng * 2 / 3 or min(o, c) - l < 1.5 * body):
                return None
            if s < 0 and (h - c < rng * 2 / 3 or h - max(o, c) < 1.5 * body):
                return None
            ok = [x for x in cands if s * (adv - (x - tick)) >= 0 and s * (adv - (x + s * 0.25 * A)) <= 0]
            if not ok:
                return None
            S = min(ok, key=lambda x: (abs(adv - x), x))
            return S, worst(adv, S) - tick, S - tick
        ok = [x for x in cands if s * (adv - (x - tick)) < 0]
        if not ok:
            return None
        conf = v >= 1.5 * t5.vsma[i]
        if not conf:
            ext = min((s5.l[x], x) for x in range(i - 12, i)) if s > 0 else max((s5.h[x], x) for x in range(i - 12, i))
            r0, rm = t5.rsi[i], t5.rsi[ext[1]]
            conf = s * (adv - ext[0]) < 0 and r0 is not None and rm is not None and s * (r0 - rm) > 0
        if not conf:
            return None
        S = max(ok) if s > 0 else min(ok)
        return S, adv - tick, S - tick

    if name == "VWR":
        vw, vp, e9, e21 = t5.vwap[i], t5.vwap[i - 1], t15.e9[k], t15.e21[k]
        if vw is None or vp is None or e9 is None or e21 is None or ctx.since_anchor[i] < 1500:
            return None
        if s * (s5.c[i - 1] - vp) >= 0 or s * (c - vw) <= 0 or s * (c - o) <= 0 or s * (e9 - e21) < 0:
            return None
        return vw, worst(lows[i - 2:i + 1]) - tick, vw - tick

    if name == "PBK":
        e21, e50, r, f9, f21 = t5.e21[i], t5.e50[i], t5.rsi[i], t15.e9[k], t15.e21[k]
        if f9 is None or f21 is None or s * (f9 - f21) <= 0:
            return None
        if s * (adv - (e21 + tick)) > 0 or s * (c - e21) <= 0 or s * (c - o) <= 0:
            return None
        w = worst(lows[i - 5:i + 1])
        if s * (w - (e50 - tick)) < 0:
            return None
        x = r if s > 0 else 100 - r
        if not 40 <= x <= 65:
            return None
        return e21, w - tick, e50 - tick

    if name == "MRV":
        bp, bn = (t5.bbl[i - 1], t5.bbl[i]) if s > 0 else (t5.bbu[i - 1], t5.bbu[i])
        rp = t5.rsi[i - 1]
        if bp is None or bn is None or rp is None:
            return None
        xr = rp if s > 0 else 100 - rp
        if s * (s5.c[i - 1] - bp) >= 0 or xr >= 30 or s * (c - bn) <= 0 or s * (c - o) <= 0:
            return None
        w = worst(lows[i - 1], lows[i])
        return bn, w - tick, w

    if name == "BOS":
        e9p, e21p, stp = t5.e9[i - 1], t5.e21[i - 1], t5.struct[i - 1]
        if not (s * (e9p - e21p) < 0 or (stp is not None and s * stp < 0)):
            return None
        H = max(s5.h[i - 10:i]) if s > 0 else min(s5.l[i - 10:i])
        if s * (c - H) <= 0 or s * (c - o) <= 0 or v < t5.vsma[i]:
            return None
        return H, worst(lows[i - 10:i + 1]) - tick, H - tick
    raise ValueError(name)


def simple(name, s, i1, A, c, s1, sigma):
    """MOM / REV (PREREG_SEARCH.md B): (P*, X, V) or None. V = X: no separate thesis exit."""
    n = 60 if name == "MOM" else 15
    if i1 < n or not sigma:
        return None
    z = (s1.c[i1] / s1.c[i1 - n] - 1.0) / (sigma * math.sqrt(n))
    if (name == "MOM" and s * z >= 2.0) or (name == "REV" and s * z <= -2.0):
        return c, c - s * A, c - s * A
    return None


def _tri(s, diff, thr):
    return 1.0 if s * diff > thr else 0.5 if abs(diff) <= thr else 0.0


def score_parts(name, s, cat, i5, i1, j, k, A, P, risk, keys, ph20, pl20, bench_trend, is_bench, ctx):
    t1, t5, t15, t60 = (ctx.tf[x] for x in ("1m", "5m", "15m", "60m"))
    c = t5.s.c[i5]
    n60 = (s * (t60.s.c[j] - t60.e50[j]) > 0) + (s * (t60.e50[j] - t60.e200[j]) > 0)
    a = 1.0 if n60 == 2 else 0.5 if n60 == 1 else 0.0
    b = _tri(s, t15.e9[k] - t15.e21[k], 0.1 * t15.atr[k])
    c15 = 1.0 if s * (t15.s.c[k] - t15.e50[k]) > 0 else 0.0
    if is_bench:
        d = 1.0 if s * (t60.e50[j] - t60.e50[j - 5]) > 0 else 0.0
    elif bench_trend is None:
        d = 0.5
    else:
        d = _tri(s, bench_trend[0], 0.1 * bench_trend[1])
    trend = 2.5 * (a + b + c15 + d)

    h0, h1 = t5.hist[i5], t5.hist[i5 - 1]
    ma = 1.0 if h0 is not None and h1 is not None and s * (h0 - h1) > 0 else 0.0
    e9, e21 = t1.e9[i1], t1.e21[i1]
    mb = 1.0 if e9 is not None and e21 is not None and s * (e9 - e21) > 0 else 0.0
    x = t5.rsi[i5] if s > 0 else 100 - t5.rsi[i5]
    mc = 1.0 if 50 <= x <= 70 else 0.5 if 40 <= x < 50 or 70 < x <= 80 else 0.0
    momentum = 10.0 * (ma + mb + mc) / 3.0

    volume = min(10.0, max(0.0, 5.0 * t5.s.v[i5] / t5.vsma[i5]))
    structure = 5.0 * sum(0.5 if st is None or st == 0 else 1.0 if s * st > 0 else 0.0
                          for st in (t5.struct[i5], t15.struct[k]))
    dist = min((abs(P - y) for y in keys), default=None)
    liquidity = (0.0 if dist is None else 10.0 if dist <= 0.25 * A else 7.0 if dist <= 0.5 * A
                 else 4.0 if dist <= A else 0.0)
    q = s * (c - P) / A
    entry = 10.0 if q <= 0.1 else 0.0 if q >= 0.75 else 10.0 * (0.75 - q) / 0.65
    beyond = c + s * 0.1 * A
    room = min([s * (y - c) for y in keys + [ph20, pl20] if y is not None and s * (y - beyond) > 0] + [6.0 * A])
    rr = min(10.0, max(0.0, 5.0 * (room / risk - 1.0)))
    return (trend, momentum, volume, structure, liquidity, entry, rr, float(FIT[name][CATS.index(cat)]))


def _candidate(name, s, cat, got, c, A, i5, i1, j, k, keys, ph20, pl20, bench_trend, is_bench, ctx, counts):
    """Stop bounds and score for one fired setup: (score, name, side, cat, P*, X, V, risk, parts) or None."""
    P, X, V = got
    risk = s * (c - X)
    if risk > 2.0 * A or risk <= 0:
        counts["stop_too_wide"] += 1
        return None
    if risk < 0.5 * A:
        X, risk = c - s * 0.5 * A, 0.5 * A
    parts = score_parts(name, s, cat, i5, i1, j, k, A, P, risk, keys, ph20, pl20, bench_trend, is_bench, ctx)
    return int(100.0 * sum(parts) / 80.0 + 0.5), name, s, cat, P, X, V, risk, parts


# ------------------------------------------------------------------ the decision walk

def run(ctx, bench=None, trace=None, mode="best"):
    """
    -> (signals, eligible, counts, fired). `eligible` = every decision that passed the data,
    warm-up, stale and blackout checks: (D, day, i1, close_at, ATR14 5m), the placebo's entry pool.
    mode "best": one signal per decision (the SN test). mode "all": every candidate (PREREG_SEARCH B).
    `trace`, if a list, receives (D, signal tuple(s) or None) per eligible decision (look-ahead test).
    """
    m, tfs = ctx.market, ctx.tf
    t1, t5, t15, t60 = tfs["1m"], tfs["5m"], tfs["15m"], tfs["60m"]
    s1, s5 = t1.s, t5.s
    bl_s, bl_e = ctx.blackouts
    is_bench = bench is None
    ptr = {name: -1 for name in tfs}
    bp = -1
    sigs, eligible, counts, fired = [], [], Counter(), Counter()
    for D, day, close_at in m.decisions:
        for name, tf in tfs.items():
            done, p = tf.s.done, ptr[name]
            while p + 1 < len(done) and done[p + 1] <= D:
                p += 1
            ptr[name] = p
        i1, i5, k, j = ptr["1m"], ptr["5m"], ptr["15m"], ptr["60m"]
        if close_at is not None and D > close_at - 35 * 60:
            counts["after_15:25"] += 1
            continue
        if i1 < 60 or s1.t[i1] != D - 60 or t1.sigma[i1] is None or i5 < 12 or s5.done[i5] != D or j < 5 or k < 1:
            counts["missing_or_warmup"] += 1
            continue
        A = t5.atr[i5]
        if (not A or t5.e200[i5] is None or not t5.vsma[i5] or t5.hist[i5 - 1] is None or t5.atr[i5 - 1] is None
                or t60.e200[j] is None or t60.adx[j] is None or t15.e50[k] is None or not t15.atr[k]
                or t15.e21[k] is None):
            counts["missing_or_warmup"] += 1
            continue
        if any(s1.v[x] == 0 and s1.o[x] == s1.h[x] == s1.l[x] == s1.c[x] for x in range(i1 - 4, i1 + 1)):
            counts["stale"] += 1
            continue
        b = bisect.bisect_right(bl_s, D) - 1
        if b >= 0 and D < bl_e[b]:
            counts["blackout"] += 1
            continue
        eligible.append((D, day, i1, close_at, A))

        c = s5.c[i5]
        bench_trend = rs_ret = None
        if not is_bench:
            while bp + 1 < len(bench.done15) and bench.done15[bp + 1] <= D:
                bp += 1
            if bp >= 0 and bench.e9[bp] is not None and bench.e21[bp] is not None and bench.atr15[bp]:
                bench_trend = (bench.e9[bp] - bench.e21[bp], bench.atr15[bp])
            bi = bench.idx1.get(D - 60)
            if bi is not None and bi >= 60:
                rs_ret = (s1.c[i1] / s1.c[i1 - 60] - 1.0) - (bench.c1[bi] / bench.c1[bi - 60] - 1.0)

        reg = eng_core.regime(t60, j, t15, k)
        rev_dir = 1 if t60.s.c[j] > t60.e200[j] else -1
        lv = m.levels.get(s5.day[i5]) or {}
        news = (m.kind == "stock" and lv.get("gap") is not None
                and abs(lv["gap"]) >= (0.01 if ctx.sym in INDEX_ETFS else 0.02))
        step = 10.0 ** (math.floor(math.log10(c)) - 1)
        rn = math.floor(c / step) * step
        keys = [y for y in (lv.get("prev_high"), lv.get("prev_low"), ctx.sess_hi[i5], ctx.sess_lo[i5],
                            lv.get("pm_high"), lv.get("pm_low"), ctx.or_hi[i5], ctx.or_lo[i5], t5.vwap[i5],
                            rn, rn + step, ctx.h60[j], ctx.l60[j]) if y is not None]
        ph20, pl20 = t5.ph[i5], t5.pl[i5]
        sig1 = t1.sigma[i1]

        best, items = None, []
        for s in (1, -1):
            cat = regime_cat(reg, s, rev_dir)
            if cat == "strong_against":
                continue
            for name in SETUPS:
                if (name in FADES and news) or (name == "PBK" and cat not in ("strong_with", "weak_with")) \
                        or (name == "MRV" and reg != "RANGE"):
                    continue
                got = detect(name, s, i5, k, A, keys, ph20, pl20, ctx)
                if got is None:
                    continue
                fired[name] += 1
                item = _candidate(name, s, cat, got, c, A, i5, i1, j, k, keys, ph20, pl20, bench_trend, is_bench,
                                  ctx, counts)
                if item is None:
                    continue
                if best is None or item[0] > best[0]:
                    best = item
                if mode == "all":
                    items.append(item)
            if mode == "all":
                for name in ("MOM", "REV"):
                    got = None if (name == "REV" and news) else simple(name, s, i1, A, c, s1, sig1)
                    if got is None:
                        continue
                    fired[name] += 1
                    item = _candidate(name, s, cat, got, c, A, i5, i1, j, k, keys, ph20, pl20, bench_trend,
                                      is_bench, ctx, counts)
                    if item is not None:
                        items.append(item)
        if mode == "best":
            items = [best] if best is not None else []
        if not items:
            if trace is not None:
                trace.append((D, None))
            continue
        f9, f21 = t15.e9[k], t15.e21[k]
        made = []
        for item in items:
            score, name, s, cat, P, X, V, risk, parts = item
            if is_bench or rs_ret is None or not sig1:
                rs = 5.0
            else:
                rs = min(10.0, max(0.0, 5.0 + 5.0 * s * rs_ret / (sig1 * math.sqrt(60))))
            sg = Signal(sym=ctx.sym, D=D, day=day, i1=i1, close_at=close_at, setup=name, side=s, score=score,
                        scan=int(100.0 * (sum(parts) + rs) / 90.0 + 0.5), parts=parts, rs=rs, price=c, A=A, P=P,
                        X=X, V=V, risk=risk, regime=reg, tr15=(f9 > f21) - (f9 < f21), cat=cat, best=item is best)
            sigs.append(sg)
            made.append((name, s, score, sg.scan, P, X, V, risk, parts))
        if trace is not None:
            trace.append((D, made[0] if mode == "best" else tuple(made)))
    counts["eligible"] = len(eligible)
    return sigs, eligible, counts, fired
