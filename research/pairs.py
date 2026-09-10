"""
Pairs trading / statistical arbitrage - Gatev, Goetzmann & Rouwenhorst (2006).
=============================================================================

The classic relative-value rule, and a genuine gap in this project: everything
tested so far has been DIRECTIONAL (own the thing, or don't). Pairs trading is
market-neutral - it makes money from two similar stocks converging, regardless
of where the market goes. If the failure of the other 51 configurations really
is "no persistent directional edge after costs", a market-neutral rule is the
obvious next question, not the 52nd indicator.

Method, exactly as published:

  FORMATION (252d)  normalise each stock to a total-return index starting at 1.
                    For every pair compute the sum of squared deviations between
                    the two normalised series. Keep the `n_pairs` smallest.
                    Record each pair's formation-period spread standard deviation.
  TRADING   (126d)  re-normalise both legs to 1 at the start. OPEN when the
                    spread exceeds `entry_sd` formation SDs - long the laggard,
                    short the leader. CLOSE when the spread crosses zero, or at
                    period end. Windows are sequential and non-overlapping, so
                    every trade is out-of-sample by construction.

Returns are dollar-neutral, so a pair's return is already excess of cash: the
long leg's financing is paid by the short leg's proceeds. Reported two ways -
Gatev's conservative "committed capital" (divide by ALL pairs, traded or not)
and "fully invested" (divide by pairs actually open).

Costs charged: `cost_per_side` on each of the four legs of a round trip, plus
a short borrow fee accrued daily while a position is open.
"""

import math

from stats import TRADING_DAYS

FORM = 252
TRADE = 126


def norm_index(closes, a, b):
    """Total-return index normalised to 1.0 at bar `a`, over [a, b)."""
    base = closes[a]
    if not base or base <= 0:
        return None
    out = []
    for i in range(a, b):
        c = closes[i]
        if c is None or c <= 0:
            return None
        out.append(c / base)
    return out


def select_pairs(panel, syms, a, b, n_pairs):
    """Smallest sum-of-squared-deviations pairs over the formation window."""
    idx = {}
    for s in syms:
        v = norm_index(panel[s], a, b)
        if v is not None:
            idx[s] = v
    names = sorted(idx)
    scored = []
    for i in range(len(names)):
        vi = idx[names[i]]
        for j in range(i + 1, len(names)):
            vj = idx[names[j]]
            ssd = 0.0
            for k in range(len(vi)):
                d = vi[k] - vj[k]
                ssd += d * d
            scored.append((ssd, names[i], names[j]))
    scored.sort()
    out = []
    for ssd, x, y in scored[:n_pairs]:
        sp = [idx[x][k] - idx[y][k] for k in range(len(idx[x]))]
        m = sum(sp) / len(sp)
        sd = math.sqrt(sum((v - m) ** 2 for v in sp) / max(len(sp) - 1, 1))
        out.append((x, y, sd))
    return out


def trade_window(panel, pairs, a, b, entry_sd, cost_per_side, borrow_annual):
    """
    Daily P&L per pair over [a, b). Returns (per_day_total, per_day_open_count,
    n_trades). Each pair contributes (r_long - r_short) while open.
    """
    n = b - a
    tot = [0.0] * n
    opencnt = [0] * n
    trades = 0
    borrow_d = borrow_annual / TRADING_DAYS

    for x, y, sd in pairs:
        vx = norm_index(panel[x], a, b)
        vy = norm_index(panel[y], a, b)
        if vx is None or vy is None or sd <= 0:
            continue
        pos = 0                      # +1 = long x / short y, -1 = the reverse
        for k in range(1, n):
            spread = vx[k] - vy[k]
            if pos != 0:
                rx = vx[k] / vx[k - 1] - 1
                ry = vy[k] / vy[k - 1] - 1
                tot[k] += pos * (rx - ry) - borrow_d
                opencnt[k] += 1
                # close on convergence (sign flip) or at the last bar
                if spread * pos >= 0 or k == n - 1:
                    tot[k] -= 2 * cost_per_side          # closing two legs
                    pos = 0
            elif abs(spread) > entry_sd * sd:
                pos = -1 if spread > 0 else 1            # fade the divergence
                tot[k] -= 2 * cost_per_side              # opening two legs
                opencnt[k] += 1
                trades += 1
    return tot, opencnt, trades


def run(dates, panel, syms, *, n_pairs=20, entry_sd=2.0, form=FORM, trade=TRADE,
        cost_per_side=0.0005, borrow_annual=0.003, min_history=None):
    """
    Sequential non-overlapping formation/trading windows across the sample.
    Returns dict with committed-capital and fully-invested daily return series.
    """
    n = len(dates)
    committed, invested, tdates = [], [], []
    total_trades, windows = 0, 0
    s = form
    while s + trade <= n:
        live = [t for t in syms
                if panel[t][s - form] is not None and panel[t][s + trade - 1] is not None]
        if len(live) < 10:
            s += trade
            continue
        pairs = select_pairs(panel, live, s - form, s, n_pairs)
        tot, oc, tr = trade_window(panel, pairs, s, s + trade,
                                   entry_sd, cost_per_side, borrow_annual)
        for k in range(len(tot)):
            committed.append(tot[k] / max(len(pairs), 1))
            invested.append(tot[k] / oc[k] if oc[k] else 0.0)
            tdates.append(dates[s + k])
        total_trades += tr
        windows += 1
        s += trade
    return {"committed": committed, "invested": invested, "dates": tdates,
            "trades": total_trades, "windows": windows,
            "trades_per_window": total_trades / max(windows, 1)}
