"""
Bond term-premium timing (H20, PROGRAM.md). Exact rules: PREREG_H20.md.
======================================================================

When long yields sit far above bill rates, holding duration has paid more (Fama & Bliss 1987,
Campbell & Shiller 1991). Each month-end an expanding-window regression of a constructed
constant-maturity bond's next-month excess return on the yield spread (FRED, 1962->) forecasts
the coming month.

  H20-LO  IEF when the forecast is > 0, cash otherwise
  H20-LS  IEF long when > 0, short otherwise

Every yield a decision uses is dated at least two sessions before the decision close, because
H.15 yields are released the next business day after the close.
"""

import bisect
import math
import random

import engine
import evaluate
import leakage
import sources
import stats
from h_common import UNREG_RF, clip, record, rf_list, yahoo

BORROW = 0.005          # %/yr fee on a short ETF position; no interest earned on the proceeds
START = "2002-08-01"    # IEF's first full month
MIN_MONTHS = 120
ROLLING = 240
_RF = {}


def _series(sid, cut=None):
    s = sources.fred(sid)
    ks = sorted(k for k in s if cut is None or k <= cut)
    return ks, [s[k] / 100.0 for k in ks]


def _asof(ks, vs, date):
    j = bisect.bisect_right(ks, date) - 1
    return vs[j] if j >= 0 else None


def month_ends(dates):
    """Indices of the last session of each COMPLETE calendar month."""
    return [i for i in range(len(dates) - 1) if dates[i + 1][:7] != dates[i][:7]]


def calendar(long_id):
    """[(month, decision day, information cut-off)]: IEF sessions where IEF exists, FRED dates before."""
    fk = sorted(sources.fred(long_id))
    out = {}
    for j in range(2, len(fk) - 1):
        if fk[j + 1][:7] != fk[j][:7]:
            out[fk[j][:7]] = (fk[j], fk[j - 2])
    ief = yahoo("IEF")["dates"]
    for i in month_ends(ief):
        if i >= 2:
            out[ief[i][:7]] = (ief[i], ief[i - 2])
    return [(m,) + out[m] for m in sorted(out)]


def par_return(y0, y1, years):
    """One-month return of a par bond (semiannual coupon y0, fixed maturity) repriced at yield y1."""
    n = int(round(2 * years))
    y1 = max(y1, 1e-6)
    disc = (1 + y1 / 2) ** (-n)
    return (y0 / 2) * (1 - disc) / (y1 / 2) + disc - 1 + y0 / 12


def ols(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx if sxx > 0 else 0.0
    return b, my - b * mx


def build(long_id="DGS10", spread_short="DTB3", years=10.0, cut=None, window=None):
    """
    {"fc": {month: (forecast, slope, decision day)}, "rex": {month: constructed excess return realized in
    that month}, "spread": {month: spread}}. The forecast made at month M uses only pairs
    (spread of k-1, return of k) with k <= M, all observed before M's decision day.
    """
    lk, lv = _series(long_id, cut)
    sk, sv = _series(spread_short, cut)
    bk, bv = _series("DTB3", cut)
    obs = []
    for m, dday, info in calendar(long_id):
        yl, ys, rf = _asof(lk, lv, info), _asof(sk, sv, info), _asof(bk, bv, info)
        if yl is not None and ys is not None and rf is not None:
            obs.append((m, dday, yl, yl - ys, rf))
    fc, rex, spread, xs, ys_ = {}, {}, {}, [], []
    for k, (m, dday, yl, sp, rf) in enumerate(obs):
        spread[m] = sp
        if k:
            pm = obs[k - 1]
            r = par_return(pm[2], yl, years) - pm[4] / 12
            rex[m] = r
            xs.append(pm[3])
            ys_.append(r)
        ux, uy = (xs, ys_) if window is None else (xs[-window:], ys_[-window:])
        if len(ux) >= MIN_MONTHS:
            b, a = ols(ux, uy)
            fc[m] = (a + b * sp, b, dday)
    return {"fc": fc, "rex": rex, "spread": spread}


def weights(sym, fc, ls=False, override=None):
    """Close-execution weights on `sym`'s calendar. `override` = {month: weight} (placebo)."""
    d = yahoo(sym)["dates"]
    n, ends = len(d), month_ends(d)
    W = [0.0] * n
    for j, i in enumerate(ends):
        m = d[i][:7]
        if override is not None:
            w = override.get(m)
        else:
            f = fc.get(m)
            w = None if f is None else (1.0 if f[0] > 0 else (-1.0 if ls else 0.0))
        if w is None:
            continue
        stop = ends[j + 1] if j + 1 < len(ends) else n
        for t in range(i, stop):
            W[t] = w
    return W


def run(sym, W, mult=1.0):
    y = yahoo(sym)
    d = y["dates"]
    if sym not in _RF:
        _RF[sym] = rf_list(d)
    res = engine.simulate(d, y["open"], y["close"], *engine.close_exec(W), _RF[sym], cost_per_side=0.0001 * mult)
    # engine.py credits a short with interest on its proceeds; a retail account earns none and pays a borrow fee
    short = [max(-a, 0.0) for a in res["w_on"]]
    res["gross"] = [g - s * r for g, s, r in zip(res["gross"], short, res["rf"])]
    res["net"] = [x - s * (r + BORROW / 252) for x, s, r in zip(res["net"], short, res["rf"])]
    return clip(res, START)


def placebo(fc, ls, draws=1000):
    d = yahoo("IEF")["dates"]
    months = [d[i][:7] for i in month_ends(d) if d[i][:7] in fc]
    decided = [1.0 if fc[m][0] > 0 else (-1.0 if ls else 0.0) for m in months]
    rng = random.Random(evaluate.SEED_PLACEBO)
    out = []
    for _ in range(draws):
        perm = decided[:]
        rng.shuffle(perm)
        out.append(stats.sharpe(run("IEF", weights("IEF", fc, override=dict(zip(months, perm))))["net"]))
    return out


def _corr(a, b):
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    va = math.sqrt(sum((x - ma) ** 2 for x in a))
    vb = math.sqrt(sum((y - mb) ** 2 for y in b))
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (va * vb) if va and vb else None


def h20():
    base = build()
    fc = base["fc"]
    ief = yahoo("IEF")
    d, c = ief["dates"], ief["close"]
    n = len(d)
    W_lo, W_ls = weights("IEF", fc), weights("IEF", fc, ls=True)
    lo, lo2 = run("IEF", W_lo), run("IEF", W_lo, 2.0)
    ls, ls2 = run("IEF", W_ls), run("IEF", W_ls, 2.0)
    variants = [("10y minus 2y spread", "IEF", build(spread_short="DGS2")["fc"]),
                ("5y minus 3m spread, 5-year bond", "IEF", build(long_id="DGS5", years=5.0)["fc"]),
                ("TLT instead of IEF", "TLT", fc),
                ("rolling 20-year window", "IEF", build(window=ROLLING)["fc"])]
    nb_lo = [(nm, run(sym, weights(sym, f))) for nm, sym, f in variants]
    nb_ls = [(nm, run(sym, weights(sym, f, ls=True))) for nm, sym, f in variants]
    pl_lo, pl_ls = placebo(fc, False), placebo(fc, True)

    def cut_weights(ls_):
        return lambda cut: weights("IEF", (fc if cut is None else build(cut=d[cut])["fc"]), ls=ls_)

    leak_lo = leakage.truncation_test(cut_weights(False), n, lag=1)
    leak_ls = leakage.truncation_test(cut_weights(True), n, lag=1)

    rf = _RF["IEF"]
    ends = month_ends(d)
    real = {}
    for j in range(1, len(ends)):
        g = 1.0
        for t in range(ends[j - 1] + 1, ends[j] + 1):
            g *= 1 + c[t] / c[t - 1] - 1 - rf[t]
        real[d[ends[j]][:7]] = g - 1
    nxt = {d[ends[j]][:7]: d[ends[j + 1]][:7] for j in range(len(ends) - 1)}
    decided = [(d[i][:7], fc[d[i][:7]][0]) for i in ends if d[i][:7] in fc]
    hits = [(f > 0) == (real[nxt[m]] > 0) for m, f in decided if m in nxt and nxt[m] in real]
    both = [(base["rex"][m], real[m]) for m in sorted(real) if m in base["rex"]]
    latest = max(fc)
    extra = {"months_decided_ief_era": len(decided),
             "share_months_long": round(sum(f > 0 for _, f in decided) / len(decided), 3),
             "sign_hit_rate_vs_ief_next_month": round(sum(hits) / len(hits), 3), "months_scored": len(hits),
             "corr_constructed_10y_vs_ief_monthly_excess": round(_corr(*zip(*both)), 3) if both else None,
             "slope_b_at_december": {m[:4]: round(v[1], 3) for m, v in sorted(fc.items())
                                     if m.endswith("-12") and int(m[:4]) % 5 == 0},
             "latest": {"month": latest, "spread_pct": round(100 * base["spread"][latest], 2),
                        "forecast_pct_per_month": round(100 * fc[latest][0], 3)}}
    common = dict(cluster="TERM", periods=252, oos_start=START, bench="IEF", implementable=True,
                  survivor_universe=False, extra=extra,
                  data="FRED DGS10/DGS5/DGS2/DTB3 (1954/1962->), Yahoo IEF/TLT 2002->, ^IRX",
                  notes=["Forecasts are trained on constructed constant-maturity bond returns from FRED "
                         "yields (1962->); trading is in IEF from 2002-08, all after publication."],
                  unregistered=[UNREG_RF])
    hyp = "An expanding-window forecast from the 10-year minus 3-month yield spread times bond duration"
    return [
        record(id="H20-LO", name="IEF when the term-spread forecast is positive",
               hypothesis=hyp + "; hold IEF only when the forecast next-month excess return is positive",
               costs="1bp/side (2x: 2bp)", dates=lo["dates"], net=lo["net"], gross=lo["gross"],
               net_2x=lo2["net"], neighbours=[(nm, r["dates"], r["net"]) for nm, r in nb_lo], placebo=pl_lo,
               trades=engine.trades(lo), expo=engine.exposure(lo), turnover=lo["turnover"], rf=lo["rf"],
               leakage=leak_lo, **common),
        record(id="H20-LS", name="IEF long/short on the term-spread forecast",
               hypothesis=hyp + "; long IEF when the forecast is positive, short otherwise",
               costs="1bp/side + 0.50%/yr borrow on shorts (2x: 2bp)", dates=ls["dates"], net=ls["net"],
               gross=ls["gross"], net_2x=ls2["net"], neighbours=[(nm, r["dates"], r["net"]) for nm, r in nb_ls],
               placebo=pl_ls, expo=engine.exposure(ls), turnover=ls["turnover"], rf=ls["rf"],
               leakage=leak_ls, **common),
    ]
