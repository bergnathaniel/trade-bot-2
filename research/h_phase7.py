"""
Phase 7: Internal Bar Strength (IBS) mean reversion in index ETFs.
==================================================================
Exact rules: PREREG_PHASE7.md.

  H42  IBS swing trade on SPY: long after a close near the day's low (IBS < 0.2), flat after a close near the high (IBS > 0.8)
  H43  the same rule on QQQ

IBS = (close - low) / (high - low) of one session, so every decision needs that session's close.
The gated version fills at the next open. The vendor-style "same close" fill is reported only:
a backtest cannot know a close before it prints.
"""

import random

import engine
import evaluate
import leakage
import stats
from h_calendar import _sim, cost_of
from h_common import UNREG_RF, clip, first_index, record, rf_list, yahoo

START = {"SPY": "1993-02-01", "QQQ": "1999-04-01"}
OOS = "2014-01-01"
SELLER_COST = 0.0003
VENDOR_QQQ_CLAIMS = {"trades": 189, "avg_gain_per_trade_pct": 1.6, "win_ratio": 0.80, "profit_factor": 3.1,
                     "cagr_pct": 12.1, "time_in_market": 0.11, "cagr_over_exposure_pct": 110, "max_dd_pct": -19.5,
                     "costs": "0.03% per trade", "rules": "not disclosed (sold)"}


def ibs_values(sym):
    y = yahoo(sym)
    out, clipped = [], 0
    for h, l, c in zip(y["high"], y["low"], y["close"]):
        if h <= l:
            out.append(0.5)
            continue
        v = (c - l) / (h - l)
        clipped += not 0.0 <= v <= 1.0
        out.append(min(1.0, max(0.0, v)))
    return out, clipped


def ibs_weights(sym, entry=0.2, exit_ibs=0.8, exit_rule="ibs", cut=None):
    """Position decided at each close (1 long, 0 flat) from bars up to that close only."""
    y = yahoo(sym)
    h, c = y["high"], y["close"]
    v = ibs_values(sym)[0]
    n = len(c)
    W, pos = [0.0] * n, False
    for t in range(n if cut is None else cut + 1):
        if exit_rule == "one_day" or not pos:
            pos = v[t] < entry
        elif exit_rule == "ibs":
            pos = v[t] <= exit_ibs
        else:                                      # "prior_high"
            pos = not c[t] > h[t - 1]
        W[t] = 1.0 if pos else 0.0
    return W


def ibs_run(sym, W, mult=1.0, same_close=False, cost=None):
    ex = engine.close_exec if same_close else engine.next_open_exec
    return clip(_sim(sym, *ex(W), (cost_of(sym) if cost is None else cost) * mult), START[sym])


def excess_map(sym):
    """{date: close-to-close return over cash}; the G2 benchmark for H43."""
    y = yahoo(sym)
    rf = rf_list(y["dates"])
    return {y["dates"][i]: y["close"][i] / y["close"][i - 1] - 1 - rf[i] for i in range(1, len(y["dates"]))}


# ------------------------------------------------------------ vendor-style numbers (reported)

def _cagr_dd(rets):
    eq = peak = 1.0
    worst = 0.0
    for r in rets:
        eq *= 1 + r
        peak = max(peak, eq)
        worst = min(worst, eq / peak - 1)
    return eq ** (252 / len(rets)) - 1, worst


def _trade_summary(tr):
    rets = [t["ret"] for t in tr]
    if not rets:
        return {"trades": 0}
    wins, losses = [r for r in rets if r > 0], [r for r in rets if r <= 0]
    return {"trades": len(rets), "avg_gain_per_trade_pct": round(100 * stats.mean(rets), 2),
            "win_ratio": round(len(wins) / len(rets), 3),
            "profit_factor": round(sum(wins) / -sum(losses), 2) if sum(losses) < 0 else None}


def vendor_style(res):
    """The vendor's table: CAGR has no interest on idle cash, so cash carry is added back to `net`."""
    total = [n + a * f for n, a, f in zip(res["net"], res["w_on"], res["rf"])]
    cagr, dd = _cagr_dd(total)
    expo = engine.exposure(res)["time_in_market"]
    out = _trade_summary([t for t in engine.trades(res) if not t.get("open")])
    out.update({"cagr_pct": round(100 * cagr, 1), "time_in_market": round(expo, 3),
                "cagr_over_exposure_pct": round(100 * cagr / expo) if expo else None,
                "max_dd_pct": round(100 * dd, 1), "window": f"{res['dates'][0]}..{res['dates'][-1]}"})
    return out


def buy_hold(sym, start):
    y = yahoo(sym)
    d, c = y["dates"], y["close"]
    rets = [c[i] / c[i - 1] - 1 for i in range(1, len(d)) if d[i] >= start]
    cagr, dd = _cagr_dd(rets)
    return {"cagr_pct": round(100 * cagr, 1), "max_dd_pct": round(100 * dd, 1), "from": start}


# ----------------------------------------------------------------------- H42 / H43

NEIGHBOURS = [("entry IBS < 0.1", dict(entry=0.1)), ("entry IBS < 0.3", dict(entry=0.3)),
              ("exit on a close above the prior high", dict(exit_rule="prior_high")),
              ("hold one session only", dict(exit_rule="one_day"))]


def _placebo(sym, W):
    i0 = first_index(yahoo(sym)["dates"], START[sym])
    core = W[i0:]
    rng = random.Random(evaluate.SEED_PLACEBO)
    out = []
    for _ in range(1000):
        k = rng.randint(63, 1260)
        r = ibs_run(sym, W[:i0] + core[-k:] + core[:-k])
        out.append(stats.sharpe(r["net"][first_index(r["dates"], OOS):]))
    return out


def _ibs_record(hid, sym, bench, extra=None):
    W = ibs_weights(sym)
    base, x2 = ibs_run(sym, W), ibs_run(sym, W, mult=2.0)
    neighbours = [(nm, r["dates"], r["net"]) for nm, kw in NEIGHBOURS for r in (ibs_run(sym, ibs_weights(sym, **kw)),)]
    trades = engine.trades(base)
    done = [t for t in trades if not t.get("open")]
    n = len(W)
    return record(
        id=hid, cluster="IBS", name=f"IBS swing trade: {sym} long below 0.2, flat above 0.8", periods=252,
        hypothesis=f"After a {sym} close near the day's low (IBS < 0.2), holding until a close near the high "
                   "(IBS > 0.8) beats holding the ETF",
        data=f"Yahoo {sym} OHLC (adjusted) {START[sym][:4]}->, ^IRX", costs="1bp/side (2x: 2bp)",
        dates=base["dates"], net=base["net"], gross=base["gross"], net_2x=x2["net"], oos_start=OOS,
        bench=bench, implementable=True, survivor_universe=False, neighbours=neighbours, placebo=_placebo(sym, W),
        trades=trades, expo=engine.exposure(base), turnover=base["turnover"], rf=base["rf"],
        leakage=leakage.truncation_test(lambda cut: ibs_weights(sym, cut=cut), n, lag=0),
        extra={"vendor_style_same_close_3bp": vendor_style(ibs_run(sym, W, same_close=True, cost=SELLER_COST)),
               "vendor_style_next_open_1bp": vendor_style(base),
               "buy_and_hold": buy_hold(sym, START[sym]),
               "trades_before_2014": _trade_summary([t for t in done if t["entry"] < OOS]),
               "trades_2014_on": _trade_summary([t for t in done if t["entry"] >= OOS]),
               "bars_ibs_clipped": ibs_values(sym)[1], **(extra or {})},
        notes=["Gated fills are at the next open; the vendor-style same-close version is reported only."],
        unregistered=[UNREG_RF, "Yahoo's open is used as the next-open fill; the official opening-auction "
                                "print can differ."])


def h42():
    return [_ibs_record("H42", "SPY", "SPY")]


def h43():
    return [_ibs_record("H43", "QQQ", "QQQ", extra={"undisclosed_volatility_model": {
        "vendor_claims": VENDOR_QQQ_CLAIMS, "qqq_buy_and_hold_1999_on": buy_hold("QQQ", START["QQQ"]),
        "qqq_buy_and_hold_2006_on": buy_hold("QQQ", "2006-01-01")}})]
