"""
Phase 10: the overnight drift.
===============================
Exact rules: PREREG_PHASE10.md.

  H48  hold SPY overnight (close -> next open), flat during the session, every day, unconditionally
  H49  the same rule on QQQ

engine.py's session model does the accounting: no signal, no filter, w_on = 1 always, w_id = 0 always. The only
"decision" is which nights count, which is what the neighbours vary (every night / Monday only / not Monday /
half-weight), so there's nothing for a signal-based placebo (G7) to shuffle - it's reported N/A.
"""

import datetime

import engine
import evaluate
import leakage
import stats
from h_calendar import cost_of
from h_common import UNREG_RF, clip, first_index, record, rf_list, yahoo

START = {"SPY": "1993-02-01", "QQQ": "1999-04-01"}
OOS = "2015-01-01"
FIVE_YEAR_CHECK_START = "2020-09-01"   # the number quoted in PREREG_PHASE10.md, checked against this harness below
LIVE_FUNDS = ["NightShares"]           # NSPY/NQQQ-style overnight ETF ticker(s) still on Yahoo, if any


def _sim(sym, w_on, w_id, cost):
    y = yahoo(sym)
    return engine.simulate(y["dates"], y["open"], y["close"], w_on, w_id, rf_list(y["dates"]), cost_per_side=cost)


def overnight_weights(sym, mult=1.0, only=None):
    """only: None (every night), "monday" (Friday close -> Monday open only), "not_monday" (every other night).
    w_on[i] belongs to the session ending at open[i], so `only` filters on that open's weekday."""
    y = yahoo(sym)
    n = len(y["dates"])
    w_on, w_id = [0.0] * n, [0.0] * n
    for i in range(1, n):
        is_monday = datetime.date.fromisoformat(y["dates"][i]).weekday() == 0
        if only == "monday" and not is_monday:
            continue
        if only == "not_monday" and is_monday:
            continue
        w_on[i] = mult
    return w_on, w_id


def overnight_run(sym, only=None, mult=1.0, cost=None):
    w_on, w_id = overnight_weights(sym, mult=mult, only=only)
    return clip(_sim(sym, w_on, w_id, cost_of(sym) if cost is None else cost), START[sym])


def check_five_year_split(sym):
    """The number PREREG_PHASE10.md quotes before this file was written, reproduced from this harness's own
    segment returns (close-to-open vs open-to-close), not taken on faith."""
    res = clip(_sim(sym, *overnight_weights(sym), cost_of(sym)), FIVE_YEAR_CHECK_START)
    co = 1.0
    for r in res["seg_on"]:
        co *= 1 + r
    oc = 1.0
    for r in res["seg_id"]:
        oc *= 1 + r
    return {"close_to_open_pct": round(100 * (co - 1), 1), "open_to_close_pct": round(100 * (oc - 1), 1)}


NEIGHBOURS = [("Monday overnight only", dict(only="monday")),
              ("every overnight except Monday", dict(only="not_monday")),
              ("half-weight overnight", dict(mult=0.5))]


def _live_alpha_check(spy_ex):
    import h_common
    out = []
    for fund in LIVE_FUNDS:
        try:
            out.append(h_common.live_alpha(fund, spy_ex))
        except Exception as e:
            out.append({"fund": fund, "note": f"not available: {e}"})
    return out


def _overnight_record(hid, sym, bench, spy_ex):
    base = overnight_run(sym)
    x2 = overnight_run(sym, cost=2 * cost_of(sym))
    neighbours = [(nm, r["dates"], r["net"]) for nm, kw in NEIGHBOURS for r in (overnight_run(sym, **kw),)]
    trades = engine.trades(base)
    n = len(yahoo(sym)["dates"])
    return record(
        id=hid, cluster="OVERNIGHT", name=f"Overnight drift: hold {sym} close-to-open only, flat during the day",
        periods=252, hypothesis=f"Holding {sym} only overnight (close to next open), flat during the trading "
                                 "session, beats holding the ETF continuously",
        data=f"Yahoo {sym} OHLC (adjusted) {START[sym][:4]}->, ^IRX", costs="1bp/side (2x: 2bp)",
        dates=base["dates"], net=base["net"], gross=base["gross"], net_2x=x2["net"], oos_start=OOS,
        bench=bench, implementable=True, survivor_universe=False, neighbours=neighbours, placebo=None,
        trades=trades, expo=engine.exposure(base), turnover=base["turnover"], rf=base["rf"],
        leakage=leakage.truncation_test(lambda cut: overnight_weights(sym)[0], n, lag=0),
        live=_live_alpha_check(spy_ex),
        extra={"five_year_close_to_open_vs_open_to_close": check_five_year_split(sym),
               "trades_before_2015": len([t for t in trades if not t.get("open") and t["entry"] < OOS]),
               "trades_2015_on": len([t for t in trades if not t.get("open") and t["entry"] >= OOS])},
        notes=["No G7 placebo: the rule is constant (no signal to shuffle), reported N/A not skipped.",
               "G9's NightShares was already known to have been liquidated before this test was built - see "
               "PREREG_PHASE10.md."],
        unregistered=[UNREG_RF])


def h48(spy_ex):
    return [_overnight_record("H48", "SPY", "SPY", spy_ex)]


def h49(spy_ex):
    return [_overnight_record("H49", "QQQ", "QQQ", spy_ex)]
