"""
Treasury auction cycle (Lou, Yan & Zhang 2013). Exact rules: PREREG_PHASE2.md.
==============================================================================

Primary dealers must absorb each new Treasury issue, so they demand a price
concession: prices sag into an auction and recover after it. The calendar is
published days to months ahead, so trading at the close around it uses no
future information - the decision never needs that day's price.

  H14-LO  hold IEF for the five sessions after each 10-year note auction, cash otherwise
  H14-LS  also short IEF for the five sessions into each auction
"""

import collections
import random
import time

import engine
import evaluate
import leakage
import sources
import stats
from h_common import UNREG_RF, clip, first_index, record, rf_list, yahoo

BORROW = 0.005          # %/yr fee on a short ETF position; no interest earned on the proceeds
START = "2002-08-01"    # IEF's first full month


def auction_days(dates, *, stype="Note", term="10-Year"):
    """Calendar indices of nominal (non-TIPS) auctions of one original term, reopenings included."""
    today = time.strftime("%Y-%m-%d")
    pos = {d: i for i, d in enumerate(dates)}
    return sorted({pos[a["auction_date"]] for a in sources.treasury_auctions()
                   if a["security_type"] == stype and a["original_security_term"] == term
                   and a.get("inflation_index_security") == "No"
                   and a["auction_date"] < today and a["auction_date"] in pos})


def auction_weights(n, ev, post=5, pre=0):
    """
    Close-execution weights: +1 from the auction-day close for `post` sessions,
    -1 from `pre` sessions before it up to the auction-day close. Overlapping
    windows of neighbouring auctions add, then clip to [-1, 1].
    """
    W = [0.0] * n
    for d in ev:
        for j in range(d, min(n, d + post)):
            W[j] += 1.0
        for j in range(max(0, d - pre), d):
            W[j] -= 1.0
    return [max(-1.0, min(1.0, w)) for w in W]


def run(sym, W, mult=1.0):
    y = yahoo(sym)
    d = y["dates"]
    res = engine.simulate(d, y["open"], y["close"], *engine.close_exec(W), rf_list(d),
                          cost_per_side=0.0001 * mult)
    # engine.py credits a short with interest on its proceeds; a retail account
    # earns none and pays a borrow fee instead
    short = [max(-a, 0.0) for a in res["w_on"]]
    res["gross"] = [g - s * r for g, s, r in zip(res["gross"], short, res["rf"])]
    res["net"] = [x - s * (r + BORROW / 252) for x, s, r in zip(res["net"], short, res["rf"])]
    return clip(res, START)


def h14():
    y = yahoo("IEF")
    d, c = y["dates"], y["close"]
    n, rf = len(d), rf_list(d)
    ev = auction_days(d)
    ty = yahoo("TLT")
    tn, tev = len(ty["dates"]), auction_days(ty["dates"], stype="Bond", term="30-Year")
    ev7 = auction_days(d, term="7-Year")

    lo, lo2 = run("IEF", auction_weights(n, ev)), run("IEF", auction_weights(n, ev), 2.0)
    ls, ls2 = run("IEF", auction_weights(n, ev, pre=5)), run("IEF", auction_weights(n, ev, pre=5), 2.0)
    nb_lo = [("post 3 sessions", run("IEF", auction_weights(n, ev, post=3))),
             ("post 7 sessions", run("IEF", auction_weights(n, ev, post=7))),
             ("TLT, 30-year bond auctions", run("TLT", auction_weights(tn, tev))),
             ("IEF, 7-year note auctions", run("IEF", auction_weights(n, ev7)))]
    nb_ls = [("3-session windows", run("IEF", auction_weights(n, ev, post=3, pre=3))),
             ("7-session windows", run("IEF", auction_weights(n, ev, post=7, pre=7))),
             ("TLT, 30-year bond auctions", run("TLT", auction_weights(tn, tev, pre=5))),
             ("IEF, 7-year note auctions", run("IEF", auction_weights(n, ev7, pre=5)))]

    near = {j for e in ev for j in range(e - 6, e + 7)}
    pool = collections.defaultdict(list)
    for i, day in enumerate(d):
        if i not in near and 6 <= i < n - 8:
            pool[day[:7]].append(i)
    oos_i = first_index(lo["dates"], "2014-01-01")
    rng = random.Random(evaluate.SEED_PLACEBO)
    pl_lo, pl_ls = [], []
    for _ in range(1000):
        fake = sorted(rng.choice(pool[d[e][:7]]) for e in ev if pool.get(d[e][:7]))
        pl_lo.append(stats.sharpe(run("IEF", auction_weights(n, fake))["net"][oos_i:]))
        pl_ls.append(stats.sharpe(run("IEF", auction_weights(n, fake, pre=5))["net"][oos_i:]))

    r_ex = [0.0] + [c[i] / c[i - 1] - 1 - rf[i] for i in range(1, n)]
    post_days = {j + 1 for e in ev for j in range(e, e + 5) if j + 1 < n}
    pre_days = {j + 1 for e in ev for j in range(e - 5, e) if j + 1 < n}

    def bp(sel, lo_, hi_):
        xs = [r_ex[i] for i in sel if lo_ <= d[i] < hi_]
        return {"sessions": len(xs), "mean_excess_bp_per_session": round(stats.mean(xs) * 1e4, 2)}

    others = set(range(1, n)) - post_days - pre_days
    extra = {"auctions_used": len(ev),
             "auctions_per_year": dict(sorted(collections.Counter(d[e][:4] for e in ev).items())),
             "in_sample_2002_2013": {"pre": bp(pre_days, START, "2014-01-01"),
                                     "post": bp(post_days, START, "2014-01-01"),
                                     "other": bp(others, START, "2014-01-01")},
             "out_of_sample_2014_on": {"pre": bp(pre_days, "2014-01-01", "9999"),
                                       "post": bp(post_days, "2014-01-01", "9999"),
                                       "other": bp(others, "2014-01-01", "9999")}}
    common = dict(cluster="AUCTION", periods=252, oos_start="2014-01-01", bench="IEF",
                  implementable=True, survivor_universe=False, extra=extra,
                  data="fiscaldata.treasury.gov auctions, Yahoo IEF/TLT 2002->, ^IRX",
                  notes=["Auction dates are public in advance, so close execution around them is "
                         "legitimate; the truncation test is structurally satisfied and run anyway."],
                  unregistered=[UNREG_RF])
    return [
        record(id="H14-LO", name="IEF after 10-year note auctions",
               hypothesis="Treasury prices recover in the sessions after an auction as dealers "
                          "distribute the new supply",
               costs="1bp/side (2x: 2bp)", dates=lo["dates"], net=lo["net"], gross=lo["gross"],
               net_2x=lo2["net"], neighbours=[(nm, r["dates"], r["net"]) for nm, r in nb_lo],
               placebo=pl_lo, trades=engine.trades(lo), expo=engine.exposure(lo),
               turnover=lo["turnover"], rf=lo["rf"],
               leakage=leakage.truncation_test(lambda cut: auction_weights(n, ev), n, lag=1),
               **common),
        record(id="H14-LS", name="IEF short into, long out of 10-year auctions",
               hypothesis="Prices sag into an auction and recover after it, so short the five "
                          "sessions before and hold the five after",
               costs="1bp/side + 0.50%/yr borrow on shorts (2x: 2bp)", dates=ls["dates"],
               net=ls["net"], gross=ls["gross"], net_2x=ls2["net"],
               neighbours=[(nm, r["dates"], r["net"]) for nm, r in nb_ls], placebo=pl_ls,
               expo=engine.exposure(ls), turnover=ls["turnover"], rf=ls["rf"],
               leakage=leakage.truncation_test(lambda cut: auction_weights(n, ev, pre=5), n, lag=1),
               **common),
    ]
