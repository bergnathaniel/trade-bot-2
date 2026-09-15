"""
Calendar-time basket backtester for event-driven stock strategies.
==================================================================

A position is an interval (symbol, entry_day, exit_day): buy at the OPEN of
entry_day, sell at the CLOSE of exit_day (indices into a shared trading
calendar). Overlapping or back-to-back intervals in one symbol merge into a
single holding - a real account keeps the shares rather than selling at one
close and buying back at the next open.

Each day has the same two segments as engine.py, and the basket is
equal-weighted within each:

  overnight  close[t-1] -> open[t]   names still held from yesterday's close
  intraday   open[t]    -> close[t]  those names plus today's entries

Entries trade at the open and exits at the close, so turnover is charged at
both, per name, at that name's per-side cost. Returns are raw (not excess of
cash); the hypothesis layer turns legs into excess, long/short or active series.

Missing bars: closes are forward-filled, so a day without a print earns zero
for that name rather than inventing a price.
"""


def merge(intervals):
    """Collapse overlapping or back-to-back intervals per symbol."""
    by = {}
    for s, a, b in intervals:
        if b >= a:
            by.setdefault(s, []).append((a, b))
    out = []
    for s, iv in by.items():
        iv.sort()
        ca, cb = iv[0]
        for a, b in iv[1:]:
            if a <= cb + 1:
                cb = max(cb, b)
            else:
                out.append((s, ca, cb))
                ca, cb = a, b
        out.append((s, ca, cb))
    return out


def _ffill(col):
    out, last = [], None
    for v in col:
        if v is not None and v > 0:
            last = v
        out.append(last)
    return out


def simulate(dates, opens, closes, intervals, cost):
    """
    opens/closes: {symbol: [price or None per calendar day]}.
    intervals: [(symbol, entry_idx, exit_idx)]. cost: per-side cost, a float or {symbol: float}.
    Returns per-day lists for days 1..n-1 (aligned like engine.simulate):
    dates, gross, net, n (names held intraday), turnover.
    """
    n = len(dates)
    entries = [[] for _ in range(n)]
    exits = [[] for _ in range(n)]
    syms = set()
    for s, a, b in merge(intervals):
        if 1 <= a < n:
            entries[a].append(s)
            exits[min(b, n - 1)].append(s)
            syms.add(s)
    cf = {s: _ffill(closes[s]) for s in syms}
    flat = isinstance(cost, (int, float))
    c_of = (lambda s: cost) if flat else (lambda s: cost.get(s, 0.0))

    res = {k: [] for k in ("dates", "gross", "net", "n", "turnover")}
    held = set()
    for t in range(1, n):
        on = held
        new = [s for s in entries[t] if s not in on]
        idn = on.union(new) if new else on

        r_on = 0.0
        if on:
            tot = 0.0
            for s in on:
                p0, o, c = cf[s][t - 1], opens[s][t], closes[s][t]
                if p0 and c:
                    tot += (o / p0 - 1) if o else (c / p0 - 1)
            r_on = tot / len(on)
        r_id = 0.0
        if idn:
            tot = 0.0
            for s in idn:
                o, c = opens[s][t], closes[s][t]
                if o and c:
                    tot += c / o - 1
            r_id = tot / len(idn)
        gross = (1 + r_on) * (1 + r_id) - 1

        cost_t = turn = 0.0
        if new or len(idn) != len(on):
            w_on = 1.0 / len(on) if on else 0.0
            w_id = 1.0 / len(idn)
            for s in on:
                d = abs(w_id - w_on)
                turn += d
                cost_t += c_of(s) * d
            for s in new:
                turn += w_id
                cost_t += c_of(s) * w_id
        after = idn
        if exits[t]:
            gone = [s for s in exits[t] if s in idn]
            if gone:
                after = idn.difference(gone)
                w_id = 1.0 / len(idn)
                w_after = 1.0 / len(after) if after else 0.0
                for s in gone:
                    turn += w_id
                    cost_t += c_of(s) * w_id
                for s in after:
                    d = abs(w_after - w_id)
                    turn += d
                    cost_t += c_of(s) * d
        held = after

        res["dates"].append(dates[t])
        res["gross"].append(gross)
        res["net"].append(gross - cost_t)
        res["n"].append(len(idn))
        res["turnover"].append(turn)
    return res


def ew_universe(dates, closes, eligible_from):
    """
    Equal-weight every name with a print today and yesterday, from its eligibility
    index on, rebalanced daily, no costs: the no-signal control for a stock universe.
    Returns (returns for days 1..n-1, names counted per day).
    """
    n = len(dates)
    out, counts = [], []
    for t in range(1, n):
        tot, k = 0.0, 0
        for s, col in closes.items():
            if t >= eligible_from.get(s, n) and col[t] and col[t - 1]:
                tot += col[t] / col[t - 1] - 1
                k += 1
        out.append(tot / k if k else 0.0)
        counts.append(k)
    return out, counts
