"""
Market series for the prediction engine (PREREG_ENGINE.md, sections A-B).
=========================================================================

A Market holds, for one symbol: the 1-minute base bars, the 5m/15m/60m bars
with the epoch each becomes usable ("done"), per-session levels (previous
session high/low, premarket high/low, opening gap) and the decision times.

Builders take raw rows, so the self-test can feed synthetic data and the
look-ahead test can feed truncated data through exactly the same code.
"""

import datetime as dt

import intraday
from intraday import et

CRYPTO = ("BTC-USD", "ETH-USD")
STOCKS = ("SPY", "QQQ", "NVDA", "TSLA")
CRYPTO_START = int(dt.datetime(2025, 9, 11, tzinfo=dt.timezone.utc).timestamp())
CRYPTO_END = int(dt.datetime(2026, 9, 11, tzinfo=dt.timezone.utc).timestamp())
WARMUP_DAYS = 14
STOCK_LAST_SESSION = dt.date(2026, 9, 10)
STOCK_SNAPSHOT = "20260911"
MIN_SESSION_BARS = 370
DAY = 86400


class Series:
    """Columnar bars plus the epoch each bar becomes usable and its session key."""

    def __init__(self, rows, done, day):
        self.t = [r[0] for r in rows]
        self.o = [r[1] for r in rows]
        self.h = [r[2] for r in rows]
        self.l = [r[3] for r in rows]
        self.c = [r[4] for r in rows]
        self.v = [r[5] for r in rows]
        self.done = done
        self.day = day

    def __len__(self):
        return len(self.t)


class Market:
    def __init__(self, sym, kind, tf, levels, decisions, filled):
        self.sym, self.kind, self.tf, self.levels = sym, kind, tf, levels
        # decisions: (D, day key, session close epoch or None)
        self.decisions = decisions
        self.filled = filled


def _resample(rows, minutes):
    p = minutes * 60
    out = []
    for t, o, h, l, c, v in rows:
        b = t - t % p
        if out and out[-1][0] == b:
            x = out[-1]
            x[2], x[3], x[4], x[5] = max(x[2], h), min(x[3], l), c, x[5] + v
        else:
            out.append([b, o, h, l, c, v])
    return out


# ------------------------------------------------------------------ crypto

def crypto_from_rows(sym, raw, eval_start, end=None):
    """Dense UTC minute grid (gaps forward-filled), 5m/15m/60m resampled on the clock."""
    rows, filled = [], 0
    for r in raw:
        if end is not None and r[0] >= end:
            break
        if rows:
            t = rows[-1][0] + 60
            while t < r[0]:
                pc = rows[-1][4]
                rows.append([t, pc, pc, pc, pc, 0.0])
                filled += 1
                t += 60
        rows.append(list(r))
    tf = {"1m": Series(rows, [r[0] + 60 for r in rows], [r[0] // DAY for r in rows])}
    for name, m in (("5m", 5), ("15m", 15), ("60m", 60)):
        rs = _resample(rows, m)
        tf[name] = Series(rs, [r[0] + m * 60 for r in rs], [r[0] // DAY for r in rs])

    days = {}
    for t, o, h, l, c, v in rows:
        x = days.get(t // DAY)
        if x is None:
            days[t // DAY] = [o, h, l, c]
        else:
            x[1], x[2], x[3] = max(x[1], h), min(x[2], l), c
    levels, prev = {}, None
    for d in sorted(days):
        levels[d] = {"prev_high": prev[1] if prev else None, "prev_low": prev[2] if prev else None,
                     "pm_high": None, "pm_low": None, "open": days[d][0], "gap": None}
        prev = days[d]

    last_close = rows[-1][0] + 60
    decisions = [(d, (d - 1) // DAY, None) for d in range(eval_start + 300, last_close + 1, 300)]
    return Market(sym, "crypto", tf, levels, decisions, filled)


def crypto(sym):
    raw = intraday.coinbase_1m(sym, CRYPTO_START, CRYPTO_END, quiet=True)
    return crypto_from_rows(sym, raw, CRYPTO_START + WARMUP_DAYS * DAY)


# ------------------------------------------------------------------ stocks

def _minutes_et(t):
    e = et(t)
    return e.date(), e.hour * 60 + e.minute


def stock_from_rows(sym, pp_rows, htf_rows, cut=None):
    """
    pp_rows: 1m bars with pre/post. htf_rows: {"5m"|"15m"|"60m": regular-session rows}.
    `cut` (epoch) drops every bar opening at or after it - used by the look-ahead test.
    """
    by_date = {}
    for r in pp_rows:
        if cut is not None and r[0] >= cut:
            break
        d, mins = _minutes_et(r[0])
        if d > STOCK_LAST_SESSION:
            continue
        slot = by_date.setdefault(d, {"reg": {}, "pre": []})
        if 570 <= mins < 960:
            slot["reg"][r[0]] = r
        elif 240 <= mins < 570:
            slot["pre"].append(r)
    # A session counts if it is complete; under a cut only the session being cut may be partial.
    last = max(by_date) if by_date else None
    sessions = [d for d in sorted(by_date)
                if len(by_date[d]["reg"]) >= MIN_SESSION_BARS
                or (cut is not None and d == last and by_date[d]["reg"])]

    rows, day1, filled = [], [], 0
    for d in sessions:
        o, c = intraday.session_bounds(d)
        got = by_date[d]["reg"]
        for t in range(o, c, 60):
            if cut is not None and t >= cut:
                break
            if t in got:
                rows.append(list(got[t]))
            elif rows:
                pc = rows[-1][4]
                rows.append([t, pc, pc, pc, pc, 0.0])
                filled += 1
            else:
                continue
            day1.append(d.toordinal())
    tf = {"1m": Series(rows, [r[0] + 60 for r in rows], day1)}

    for name, m in (("5m", 5), ("15m", 15), ("60m", 60)):
        rs, done, day = [], [], []
        for r in htf_rows[name]:
            if cut is not None and r[0] >= cut:
                break
            d, mins = _minutes_et(r[0])
            if d > STOCK_LAST_SESSION or not 570 <= mins < 960:
                continue
            rs.append(list(r))
            done.append(min(r[0] + m * 60, intraday.session_bounds(d)[1]))
            day.append(d.toordinal())
        tf[name] = Series(rs, done, day)

    # Session levels from the 5m regular bars (they reach further back than the 1m data).
    s5 = tf["5m"]
    days = {}
    for i in range(len(s5)):
        k = s5.day[i]
        x = days.get(k)
        if x is None:
            days[k] = [s5.o[i], s5.h[i], s5.l[i], s5.c[i]]
        else:
            x[1], x[2], x[3] = max(x[1], s5.h[i]), min(x[2], s5.l[i]), s5.c[i]
    levels, prev = {}, None
    for k in sorted(days):
        pre = by_date.get(dt.date.fromordinal(k), {}).get("pre") or []
        levels[k] = {
            "prev_high": prev[1] if prev else None,
            "prev_low": prev[2] if prev else None,
            "pm_high": max(r[2] for r in pre) if pre else None,
            "pm_low": min(r[3] for r in pre) if pre else None,
            "open": days[k][0],
            "gap": days[k][0] / prev[3] - 1.0 if prev else None,
        }
        prev = days[k]

    decisions = []
    for d in sessions[1:]:  # first full session = 1m warm-up
        o, c = intraday.session_bounds(d)
        for D in range(o + 300, c, 300):
            if cut is None or D <= cut:
                decisions.append((D, d.toordinal(), c))
    return Market(sym, "stock", tf, levels, decisions, filled)


def stock(sym, snapshot=STOCK_SNAPSHOT):
    pp = intraday.yahoo(sym, "1m", prepost=True, snapshot=snapshot, quiet=True)
    htf = {iv: intraday.yahoo(sym, iv, snapshot=snapshot, quiet=True) for iv in ("5m", "15m", "60m")}
    return stock_from_rows(sym, pp, htf)


def load(sym):
    return crypto(sym) if sym in CRYPTO else stock(sym)
