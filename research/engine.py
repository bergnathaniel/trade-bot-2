"""
Weight-path backtester with an explicit session model.
=====================================================

Every trading day is two segments:

    overnight  close[i-1] -> open[i]     held at weight w_on[i]
    intraday   open[i]    -> close[i]    held at weight w_id[i]

A strategy only ever produces weights; this module alone turns weights into
P&L. That separation is what lets one weight function drive a backtest, a
paper account and - only after the gates - a live one.

Execution models decide what information a decision may use:

  close_exec(W)      W[i] is held from close i. It may use only information
                     known BEFORE close i: a published calendar, prior closes.
                     Used for FOMC and turn-of-month, scheduled in advance.
  next_open_exec(W)  W[i] is computed with close i in hand and filled at
                     open i+1. Used for anything derived from a closing price.

Accounting, all EXCESS of cash:

  growth   = w * (close/prev_close - 1)                  weight unchanged at the open
           = (1 + w_on*r_on) * (1 + w_id*r_id) - 1       re-sized at the open
  excess   = growth - w_on*rf - max(w_on-1, 0)*financing_spread
  turnover = |w_on[i] - w_id[i-1]| + |w_id[i] - w_on[i]|
  net      = excess - cost_per_side*turnover - drag*|w_on|
"""

from stats import TRADING_DAYS


def close_exec(W):
    """Decision W[i] held from close i to close i+1."""
    w = [0.0] + [W[i - 1] for i in range(1, len(W))]
    return w, list(w)


def next_open_exec(W):
    """Decision W[i], made with close i known, filled at open i+1."""
    n = len(W)
    w_id = [0.0] + [W[i - 1] for i in range(1, n)]
    w_on = ([0.0, 0.0] + [W[i - 2] for i in range(2, n)])[:n]
    return w_on, w_id


def simulate(dates, opens, closes, w_on, w_id, rf, *, cost_per_side=0.0,
             financing_spread=0.015, drag=0.0):
    """
    dates/opens/closes: the instrument's own trading days. `opens` may be None
    (index series with no usable open) as long as no weight changes at the open.
    rf: daily cash rate per date. Returns per-day series for days 1..n-1.
    """
    fin_d, drag_d = financing_spread / TRADING_DAYS, drag / TRADING_DAYS
    keys = ("dates", "gross", "net", "turnover", "w_on", "w_id", "seg_on", "seg_id", "rf")
    res = {k: [] for k in keys}
    for i in range(1, len(dates)):
        c0, c = closes[i - 1], closes[i]
        o = opens[i] if opens is not None else None
        a, b = w_on[i], w_id[i]
        if o is None or o <= 0:
            if abs(a - b) > 1e-12:
                raise ValueError(f"{dates[i]}: no open price but the weight changes at the open")
            r_on, r_id = c / c0 - 1, 0.0
        else:
            r_on, r_id = o / c0 - 1, c / o - 1
        t_on, t_id = abs(a - w_id[i - 1]), abs(b - a)
        carry = a * rf[i] + max(a - 1.0, 0.0) * fin_d
        if t_id < 1e-12:                        # no trade at the open: one position, close to close
            move = a * ((1 + r_on) * (1 + r_id) - 1)
        else:                                   # re-sized at the open
            move = (1 + a * r_on) * (1 + b * r_id) - 1
        gross = move - carry
        net = gross - cost_per_side * (t_on + t_id) - drag_d * abs(a)
        res["dates"].append(dates[i])
        res["gross"].append(gross)
        res["net"].append(net)
        res["turnover"].append(t_on + t_id)
        res["w_on"].append(a)
        res["w_id"].append(b)
        res["rf"].append(rf[i])
        res["seg_on"].append(a * r_on - carry - drag_d * abs(a) - cost_per_side * t_on)
        res["seg_id"].append(b * r_id - cost_per_side * t_id)
    return res


def trades(res):
    """
    Round trips of a long/flat strategy: maximal runs of consecutive segments
    held at weight > 0. Exit costs land on the first flat segment, so they are
    included. `nights` = overnight segments held (0 for an open->close trade).
    """
    out, cur = [], None
    for d, a, b, so, si in zip(res["dates"], res["w_on"], res["w_id"],
                               res["seg_on"], res["seg_id"]):
        for kind, w, r in (("on", a, so), ("id", b, si)):
            if w > 1e-12:
                if cur is None:
                    cur = {"entry": d, "growth": 1.0, "nights": 0}
                cur["growth"] *= 1 + r
                cur["nights"] += kind == "on"
                cur["exit"] = d
            elif cur is not None:
                cur["growth"] *= 1 + r
                out.append({"entry": cur["entry"], "exit": cur["exit"],
                            "ret": cur["growth"] - 1, "nights": cur["nights"]})
                cur = None
    if cur is not None:
        out.append({"entry": cur["entry"], "exit": cur["exit"], "ret": cur["growth"] - 1,
                    "nights": cur["nights"], "open": True})
    return out


def exposure(res):
    """Time-in-market and average long exposure across both segments."""
    n = len(res["w_on"]) or 1
    held = sum(1 for a, b in zip(res["w_on"], res["w_id"]) if a > 1e-12 or b > 1e-12)
    avg = sum((a + b) / 2 for a, b in zip(res["w_on"], res["w_id"])) / n
    return {"time_in_market": held / n, "long_exposure": avg, "short_exposure": 0.0,
            "max_weight": max(max(res["w_on"] or [0]), max(res["w_id"] or [0]))}
