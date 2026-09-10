"""
Cross-sectional equity anomalies, on their home turf (US large caps).
=====================================================================

`xsectional_backtest.py` tested relative momentum on a 23-coin CRYPTO basket
and it failed. That is not a test of the anomaly - these were all documented on
US stocks, over decades. This runs them where they were found.

Common engine: rank every stock on a signal computed from data through day t,
go long the top `frac` and short the bottom `frac`, equal-weighted, rebalanced
every `rebal` days, held from t+1. Dollar-neutral, so returns are already
excess of cash. A long-only variant is reported too, since shorting single
names is not realistic in a small retail account.

Signals (all published, none fitted here):
  mom_12_1  12-month return skipping the last month  [Jegadeesh-Titman 1993]
  mom_6_1   6-month version
  strev_21  NEGATIVE of last month's return          [Jegadeesh 1990]
  strev_5   NEGATIVE of last week's return
  lowvol    NEGATIVE of 60-day realised volatility   [Haugen-Baker / BAB]
  beta_low  NEGATIVE of 60-day beta to the market    [Frazzini-Pedersen 2014]
"""

import math
from stats import TRADING_DAYS, stdev, mean


def _ret(col, i, back, skip=0):
    a, b = i - back, i - skip
    if a < 0 or b < 0 or col[a] is None or col[b] is None or col[a] <= 0:
        return None
    return col[b] / col[a] - 1


def _vol(rets, i, win):
    if i - win < 0:
        return None
    seg = [r for r in rets[i - win:i] if r is not None]
    if len(seg) < win // 2:
        return None
    return stdev(seg)


def _beta(rets, mkt, i, win):
    if i - win < 0:
        return None
    xs = [(rets[k], mkt[k]) for k in range(i - win, i)
          if rets[k] is not None and mkt[k] is not None]
    if len(xs) < win // 2:
        return None
    my = mean([b for _, b in xs])
    mx = mean([a for a, _ in xs])
    cov = sum((a - mx) * (b - my) for a, b in xs) / len(xs)
    var = sum((b - my) ** 2 for _, b in xs) / len(xs)
    return cov / var if var > 0 else None


SIGNALS = {
    "mom_12_1": lambda c, r, m, i: _ret(c, i, 252, 21),
    "mom_6_1":  lambda c, r, m, i: _ret(c, i, 126, 21),
    "strev_21": lambda c, r, m, i: (lambda v: -v if v is not None else None)(_ret(c, i, 21)),
    "strev_5":  lambda c, r, m, i: (lambda v: -v if v is not None else None)(_ret(c, i, 5)),
    "lowvol":   lambda c, r, m, i: (lambda v: -v if v is not None else None)(_vol(r, i, 60)),
    "beta_low": lambda c, r, m, i: (lambda v: -v if v is not None else None)(_beta(r, m, i, 60)),
}


def run(dates, panel, syms, rets, mkt, signal, *, frac=0.2, rebal=21,
        cost_per_side=0.0005, rf=None):
    """Long top `frac` / short bottom `frac`. Returns dict of daily series."""
    fn = SIGNALS[signal]
    n = len(dates)
    rf_d = [(rf.get(d, 0.0) if rf else 0.0) for d in dates]
    ls, lo, turn_s = [], [], []
    wl, ws = {}, {}
    for i in range(n - 1):
        if i % rebal == 0:
            scored = []
            for s in syms:
                if panel[s][i] is None:
                    continue
                v = fn(panel[s], rets[s], mkt, i)
                if v is not None and not math.isnan(v):
                    scored.append((v, s))
            k = int(len(scored) * frac)
            if k >= 3:
                scored.sort()
                new_s = {s: 1.0 / k for _, s in scored[:k]}        # worst signal
                new_l = {s: 1.0 / k for _, s in scored[-k:]}       # best signal
            else:
                new_s, new_l = {}, {}
            turn = (sum(abs(new_l.get(s, 0) - wl.get(s, 0)) for s in set(new_l) | set(wl))
                    + sum(abs(new_s.get(s, 0) - ws.get(s, 0)) for s in set(new_s) | set(ws)))
            wl, ws = new_l, new_s
        else:
            turn = 0.0
        rl = sum(w * rets[s][i + 1] for s, w in wl.items() if rets[s][i + 1] is not None)
        rs = sum(w * rets[s][i + 1] for s, w in ws.items() if rets[s][i + 1] is not None)
        ls.append(rl - rs - turn * cost_per_side)
        # long-only leg is a real directional bet, so take it excess of cash
        lo.append(rl - rf_d[i + 1] - turn * 0.5 * cost_per_side)
        turn_s.append(turn)
    return {"ls": ls, "long_only": lo, "dates": dates[1:],
            "ann_turnover": sum(turn_s) / max(len(turn_s), 1) * TRADING_DAYS}
