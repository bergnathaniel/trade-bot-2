"""
Shared plumbing for the Phase-1 hypothesis modules.
==================================================

Every hypothesis function returns RECORDS - plain dicts that run_phase1.py
evaluates identically, so no hypothesis gets a friendlier test than another:

  id, cluster, name, hypothesis, data, costs   descriptive strings
  periods              252 (daily) or 12 (monthly)
  dates, net, gross    full-sample series; net = after costs, excess of cash
  net_2x               the same at double costs (gate G4)
  oos_start            first out-of-sample date (post-publication)
  bench                "SPY" or "MKT" (French Mkt-RF)
  alpha_y              optional series regressed for G2 instead of `net`
  neighbours           [(name, dates, net)]
  placebo              [out-of-sample Sharpe per draw] or None
  implementable, live  gate G8 input; [live fund dicts] for G9
  trades, expo, turnover, rf, leakage, extra, unregistered, notes
"""

import data
import evaluate
import stats

_YAHOO = {}


def yahoo(sym):
    if sym not in _YAHOO:
        bars = data.fetch(sym, quiet=True)
        _YAHOO[sym] = {"dates": [data._ymd(b[0]) for b in bars],
                       "open": [b[1] for b in bars], "high": [b[2] for b in bars],
                       "low": [b[3] for b in bars], "close": [b[4] for b in bars]}
    return _YAHOO[sym]


def closes(sym):
    y = yahoo(sym)
    return dict(zip(y["dates"], y["close"]))


def rf_list(dates):
    lut = data.risk_free_daily(dates)
    return [lut[d] for d in dates]


def first_index(dates, start):
    return next((i for i, d in enumerate(dates) if d >= start), len(dates))


def slice_from(dates, series, start):
    i = first_index(dates, start)
    return dates[i:], series[i:]


def clip(res, start):
    """Slice every per-day list of an engine result to dates >= start."""
    i = first_index(res["dates"], start)
    return {k: (v[i:] if isinstance(v, list) else v) for k, v in res.items()}


def spy_excess():
    y = yahoo("SPY")
    rf = rf_list(y["dates"])
    return {y["dates"][i]: y["close"][i] / y["close"][i - 1] - 1 - rf[i]
            for i in range(1, len(y["dates"]))}


def live_alpha(fund, spy_ex):
    """Full-history alpha of a live fund vs SPY, both excess of cash, Newey-West t."""
    y = yahoo(fund)
    if len(y["dates"]) < 60:
        return {"fund": fund, "years": 0.0, "alpha": 0.0, "t": 0.0, "note": "no data"}
    rf = rf_list(y["dates"])
    ys, xs = [], []
    for i in range(1, len(y["dates"])):
        d = y["dates"][i]
        if d in spy_ex:
            ys.append(y["close"][i] / y["close"][i - 1] - 1 - rf[i])
            xs.append(spy_ex[d])
    reg = evaluate.ols_nw(ys, [xs])
    return {"fund": fund, "years": len(ys) / 252, "alpha": reg["coef"][0] * 252,
            "t": reg["t"][0], "beta": reg["coef"][1], "sharpe": stats.sharpe(ys),
            "spy_sharpe_same_window": stats.sharpe(xs),
            "start": y["dates"][0], "end": y["dates"][-1]}


def by_decade(dates, rets, periods):
    groups = {}
    for d, r in zip(dates, rets):
        groups.setdefault(d[:3] + "0s", []).append(r)
    return {k: round(stats.sharpe(v, periods=periods), 2)
            for k, v in sorted(groups.items()) if len(v) >= 3 * periods}


def record(**kw):
    rec = dict(neighbours=[], placebo=None, live=None, trades=None, expo=None, turnover=None,
               rf=None, alpha_y=None, leakage=None, extra={}, unregistered=[], notes=[])
    rec.update(kw)
    return rec


UNREG_ENGINE = ("Weights are daily-rebalanced targets; turnover cost is charged only when the "
                "target changes (intra-period drift rebalancing ignored).")
UNREG_RF = "^IRX is forward-filled across days it does not print."
