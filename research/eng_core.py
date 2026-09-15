"""
The prediction engine, config E1 (PREREG_ENGINE.md, section B).
===============================================================

run(market) walks the 5-minute decision times. At each time D it reads only
bars whose `done` <= D, collects the -1/0/+1 votes on each timeframe, classifies
the regime, and produces the three horizon calls plus the trading action.

A decision record is a tuple (see REC_FIELDS). Calls, confidence, stated
probability, target and invalidation are pure functions of S, price and sigma,
so they are derived by `outputs()` instead of stored 100k times.
"""

import math

import eng_ind as ind

HORIZONS = (5, 30, 120)
THETA = 0.25
FAMS = ("mom", "mr", "brk", "cdl")
REGIME_FAMILY_W = {
    "STRONG": {"mom": 1.5, "mr": 0.5, "brk": 1.0, "cdl": 0.5},
    "WEAK": {"mom": 1.0, "mr": 0.75, "brk": 1.0, "cdl": 0.5},
    "RANGE": {"mom": 0.5, "mr": 1.5, "brk": 0.75, "cdl": 0.5},
    "BREAK": {"mom": 1.0, "mr": 0.25, "brk": 1.5, "cdl": 0.5},
    "OTHER": {"mom": 1.0, "mr": 1.0, "brk": 1.0, "cdl": 0.5},
}
REGIME_GROUP = {"STRONG BULL": "STRONG", "STRONG BEAR": "STRONG", "WEAK BULL": "WEAK",
                "WEAK BEAR": "WEAK", "RANGE": "RANGE", "BREAKOUT": "BREAK", "BREAKDOWN": "BREAK",
                "REVERSAL": "OTHER", "UNKNOWN": "OTHER"}
TF_W = {5: {"1m": 1.0, "5m": 1.0, "15m": 0.5, "60m": 0.25},
        30: {"1m": 0.25, "5m": 1.0, "15m": 1.0, "60m": 0.5},
        120: {"1m": 0.0, "5m": 0.5, "15m": 1.0, "60m": 1.0}}
VOLPCT_WINDOW = {"crypto": 720, "stock": 140}

# (D, day, session_close, i1, price, sigma, atr5, regime, vol, action, S5, S30, S120, fam5, fam30, fam120)
REC_FIELDS = ("D", "day", "close_at", "i1", "price", "sigma", "atr5", "regime", "vol", "action",
              "S5", "S30", "S120", "fam5", "fam30", "fam120")


def _sign(x):
    return (x > 0) - (x < 0)


class TF:
    """Indicator arrays for one timeframe."""

    def __init__(self, market, name):
        s = market.tf[name]
        c, h, l, v = s.c, s.h, s.l, s.v
        self.s, self.name = s, name
        self.e9, self.e21, self.e50, self.e200 = ind.ema(c, 9), ind.ema(c, 21), ind.ema(c, 50), ind.ema(c, 200)
        self.rsi, self.hist, self.atr = ind.rsi(c), ind.macd_hist(c), ind.atr(h, l, c)
        self.bbl, self.bbu = ind.bollinger(c)
        self.vsma = ind.sma(v, 20)
        self.ph, self.pl = ind.prior_high(h), ind.prior_low(l)
        self.struct = ind.structure(h, l)
        if name in ("1m", "5m"):
            rows = list(zip(s.t, s.o, h, l, c, v))
            day_of = dict(zip(s.t, s.day))
            self.vwap, self.vsd = ind.anchored_vwap(rows, day_of.__getitem__)
        if name == "1m":
            self.sigma = ind.rolling_logret_sd(c, 60)
        if name == "60m":
            self.adx = ind.adx(h, l, c)
            rel = [a / x if a is not None else None for a, x in zip(self.atr, c)]
            self.volpct = ind.trailing_pct_rank(rel, VOLPCT_WINDOW[market.kind])


def _breakout(tf, i):
    s = tf.s
    if tf.ph[i] is None or tf.vsma[i] is None:
        return None
    if s.v[i] > 1.5 * tf.vsma[i]:
        if s.c[i] > tf.ph[i]:
            return 1
        if s.c[i] < tf.pl[i]:
            return -1
    return 0


def votes(tf, i, market):
    """[(family, vote)] for bar i; None votes (not computable) are left out."""
    s, name = tf.s, tf.name
    c = s.c[i]
    out = []
    if tf.e200[i] is None or i < 1:
        return out
    out.append(("mom", _sign(tf.e9[i] - tf.e21[i])))
    out.append(("mom", 1 if c > tf.e50[i] > tf.e200[i] else -1 if c < tf.e50[i] < tf.e200[i] else 0))
    hc, hp = tf.hist[i], tf.hist[i - 1]
    if hc is not None and hp is not None:
        out.append(("mom", 1 if hc > 0 and hc > hp else -1 if hc < 0 and hc < hp else 0))
    r = tf.rsi[i]
    out.append(("mom", 1 if r > 55 else -1 if r < 45 else 0))
    if tf.struct[i] is not None:
        out.append(("mom", tf.struct[i]))
    out.append(("mr", 1 if c < tf.bbl[i] and r < 30 else -1 if c > tf.bbu[i] and r > 70 else 0))

    if name in ("1m", "5m") and tf.vwap[i] is not None:
        vw, sd = tf.vwap[i], tf.vsd[i]
        out.append(("mom", _sign(c - vw)))
        out.append(("mr", 1 if c < vw - 2 * sd else -1 if c > vw + 2 * sd else 0))

    if name in ("5m", "15m", "60m"):
        b = _breakout(tf, i)
        if b is not None:
            out.append(("brk", b))
    if name in ("5m", "15m") and tf.pl[i - 1] is not None:
        pc, lo, hi = s.c[i - 1], tf.pl[i - 1], tf.ph[i - 1]
        out.append(("brk", 1 if pc < lo and c > lo else -1 if pc > hi and c < hi else 0))

    if name == "5m":
        lv = market.levels.get(s.day[i])
        if lv and lv["prev_high"] is not None:
            out.append(("brk", 1 if c > lv["prev_high"] else -1 if c < lv["prev_low"] else 0))
        if market.kind == "stock" and lv:
            if lv["pm_high"] is not None:
                out.append(("brk", 1 if c > lv["pm_high"] else -1 if c < lv["pm_low"] else 0))
            if lv["gap"] is not None:
                out.append(("brk", _sign(c - lv["open"]) if abs(lv["gap"]) >= 0.0025 else 0))
        o, o1, c1 = s.o[i], s.o[i - 1], s.c[i - 1]
        if c1 < o1 and c > o and o <= c1 and c >= o1:
            eng = 1
        elif c1 > o1 and c < o and o >= c1 and c <= o1:
            eng = -1
        else:
            eng = 0
        out.append(("cdl", eng))
        body = abs(c - o)
        lw, uw = min(o, c) - s.l[i], s.h[i] - max(o, c)
        if lw >= 2 * body and uw <= body and s.l[i] <= tf.bbl[i]:
            hs = 1
        elif uw >= 2 * body and lw <= body and s.h[i] >= tf.bbu[i]:
            hs = -1
        else:
            hs = 0
        out.append(("cdl", hs))
    return out


def regime(t60, j, t15, k):
    if j is None or j < 5 or t60.e200[j] is None or t60.adx[j] is None:
        return "UNKNOWN"
    if k is not None and t15.e200[k] is not None:
        b = _breakout(t15, k)
        if b == 1:
            return "BREAKOUT"
        if b == -1:
            return "BREAKDOWN"
    c, e50, e200, a = t60.s.c[j], t60.e50[j], t60.e200[j], t60.adx[j]
    up = e50 > t60.e50[j - 5]
    if c > e50 > e200 and up and a >= 25:
        return "STRONG BULL"
    if c < e50 < e200 and not up and a >= 25:
        return "STRONG BEAR"
    if a < 20:
        return "RANGE"
    if c > e200 and e50 > e200:
        return "WEAK BULL"
    if c < e200 and e50 < e200:
        return "WEAK BEAR"
    if (c > e200 > e50 and up) or (c < e200 < e50 and not up):
        return "REVERSAL"
    return "UNKNOWN"


def call_of(S):
    return "UP" if S >= THETA else "DOWN" if S <= -THETA else "SIDEWAYS"


def outputs(S, price, sigma, h):
    """Everything the prompt's card shows for one horizon, from the stored score."""
    call = call_of(S)
    a = min(1.0, abs(S) / 0.75)
    conf = round(100 * a)
    prob = 0.34 + 0.46 * a if call != "SIDEWAYS" else 0.34 + 0.26 * (1 - abs(S) / THETA)
    band = sigma * math.sqrt(h)
    sgn = 1 if call == "UP" else -1 if call == "DOWN" else 0
    return {"call": call, "confidence": conf, "prob": prob,
            "target": price * (1 + sgn * 0.8 * band),
            "range": (price * (1 - band), price * (1 + band)),
            "invalidation": price * (1 - sgn * band) if sgn else None}


def action_of(S30, S120, price, ema21_5, atr5, late):
    c30, c120 = call_of(S30), call_of(S120)
    conf = round(100 * min(1.0, abs(S30) / 0.75))
    if late or conf < 60 or c30 == "SIDEWAYS":
        return "NO TRADE"
    if c30 == "UP" and c120 != "DOWN":
        if price - ema21_5 > 1.5 * atr5:
            return "BULLISH - WAIT FOR BETTER ENTRY"
        return "STRONG BUY" if conf >= 75 and c120 == "UP" else "BUY"
    if c30 == "DOWN" and c120 != "UP":
        if ema21_5 - price > 1.5 * atr5:
            return "BEARISH - WAIT FOR BETTER ENTRY"
        return "STRONG SELL" if conf >= 75 and c120 == "DOWN" else "SELL"
    return "NO TRADE"


def run(market):
    tfs = {name: TF(market, name) for name in ("1m", "5m", "15m", "60m")}
    ptr = {name: -1 for name in tfs}
    recs = []
    for D, day, close_at in market.decisions:
        for name, tf in tfs.items():
            done, p = tf.s.done, ptr[name]
            while p + 1 < len(done) and done[p + 1] <= D:
                p += 1
            ptr[name] = p
        i1 = ptr["1m"]
        t1 = tfs["1m"]
        if i1 < 0 or t1.s.t[i1] != D - 60 or t1.sigma[i1] is None:
            continue  # the minute bar ending at D is missing
        j, k, i5 = ptr["60m"], ptr["15m"], ptr["5m"]
        reg = regime(tfs["60m"], j if j >= 0 else None, tfs["15m"], k if k >= 0 else None)
        fw = REGIME_FAMILY_W[REGIME_GROUP[reg]]
        vp = tfs["60m"].volpct[j] if j >= 0 else None
        vol = "HIGH" if vp is not None and vp >= 0.8 else "LOW" if vp is not None and vp <= 0.2 else "NORMAL"
        tv = {name: votes(tf, ptr[name], market) if ptr[name] >= 1 else [] for name, tf in tfs.items()}

        scores, fams = [], []
        for h in HORIZONS:
            num = den = 0.0
            fc = dict.fromkeys(FAMS, 0.0)
            for name, vs in tv.items():
                wt = TF_W[h][name]
                if not wt:
                    continue
                for fam, v in vs:
                    w = wt * fw[fam]
                    num += w * v
                    den += w
                    fc[fam] += w * v
            scores.append(num / den if den else 0.0)
            fams.append(tuple(fc[f] / den if den else 0.0 for f in FAMS))

        price = t1.s.c[i1]
        t5 = tfs["5m"]
        atr5 = t5.atr[i5] if i5 >= 0 else None
        e21 = t5.e21[i5] if i5 >= 0 else None
        late = close_at is not None and D > close_at - 35 * 60
        act = action_of(scores[1], scores[2], price, e21, atr5, late) if atr5 and e21 else "NO TRADE"
        recs.append((D, day, close_at, i1, price, t1.sigma[i1], atr5, reg, vol, act,
                     scores[0], scores[1], scores[2], fams[0], fams[1], fams[2]))
    return recs, tfs["1m"].s
