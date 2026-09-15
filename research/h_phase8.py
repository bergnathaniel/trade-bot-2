"""
Phase 8: country momentum rotation and G10 currency carry.
==========================================================
Exact rules: PREREG_PHASE8.md.

  H44  country momentum (Asness, Moskowitz & Pedersen 2013): each month hold the 4 of the 17 original iShares
       country ETFs with the best 12-1 month return, 25% each, filled at the next open
  H45  G10 currency carry (Lustig & Verdelhan 2007; Burnside et al. 2011): each month long the 3 highest-rate and
       short the 3 lowest-rate of 10 currencies against USD, earning the spot move plus the rate gap
"""

import functools
import random

import engine
import evaluate
import leakage
import sources
import stats
from h_calendar import _sim
from h_common import UNREG_RF, live_alpha, record, rf_list, yahoo
from h_phase4 import _combine, month_ends

# ----------------------------------------------------------------------- H44

COUNTRIES = ("EWA", "EWC", "EWD", "EWG", "EWH", "EWI", "EWJ", "EWK", "EWL", "EWM", "EWN", "EWO", "EWP", "EWQ",
             "EWS", "EWU", "EWW")   # the 17 original iShares (WEBS) country ETFs of 1996, all still trading
CM_START, CM_OOS = "1997-04-01", "2014-01-01"
CM_COST = 0.0005


def cm_decisions(top=4, lookback=12, skip=1, cut_date=None):
    """[(SPY month-end index, held tickers)] ranked by close[month-end j-skip] / close[month-end j-lookback]."""
    d = yahoo("SPY")["dates"]
    ends = month_ends(d)
    closes = {s: {t: c for t, c in zip(yahoo(s)["dates"], yahoo(s)["close"]) if cut_date is None or t <= cut_date}
              for s in COUNTRIES}
    out = []
    for j in range(lookback, len(ends)):
        now, a, b = d[ends[j]], d[ends[j - lookback]], d[ends[j - skip]]
        if cut_date is not None and now > cut_date:
            break
        if not all(a in closes[s] and b in closes[s] and now in closes[s] for s in COUNTRIES):
            continue
        mom = {s: closes[s][b] / closes[s][a] - 1 for s in COUNTRIES}
        out.append((ends[j], tuple(sorted(sorted(COUNTRIES, key=lambda s: (-mom[s], s))[:top]))))
    return out


def cm_run(dec, mult=1.0):
    d = yahoo("SPY")["dates"]
    n, weight, first = len(d), 1 / len(dec[0][1]), d[dec[0][0]]
    legs = {}
    for s in COUNTRIES:
        wmap = {}
        for j, (i, held) in enumerate(dec):
            for t in range(i, dec[j + 1][0] if j + 1 < len(dec) else n):
                wmap[d[t]] = weight if s in held else 0.0
        W, last = [], 0.0
        for t in yahoo(s)["dates"]:
            last = wmap.get(t, last if t > first else 0.0)
            W.append(last)
        legs[s] = _sim(s, *engine.next_open_exec(W), CM_COST * mult)
    return _combine(legs, CM_START)


def holding_returns(dec):
    """[(exit date, {ticker: excess return})] from the open after one decision to the open after the next."""
    d = yahoo("SPY")["dates"]
    rf = rf_list(d)
    opens = {s: dict(zip(yahoo(s)["dates"], yahoo(s)["open"])) for s in COUNTRIES}
    rows = []
    for (i, _), (k, _) in zip(dec, dec[1:]):
        if k + 1 >= len(d):
            break
        cash = 1.0
        for t in range(i + 2, k + 2):
            cash *= 1 + rf[t]
        rows.append((d[k + 1], {s: opens[s][d[k + 1]] / opens[s][d[i + 1]] - cash for s in COUNTRIES}))
    return rows


def picks_sharpe(rows, picks):
    """Annualized Sharpe of monthly holding returns of the given picks, after the cost of changing names."""
    rets, prev = [], set()
    for (_, R), held in zip(rows, picks):
        held = set(held)
        rets.append(sum(R[s] for s in held) / len(held) - CM_COST * len(held ^ prev) / len(held))
        prev = held
    return stats.sharpe(rets, periods=12)


def h44():
    dec = cm_decisions()
    base, x2 = cm_run(dec), cm_run(dec, mult=2.0)
    variants = [("top 3", cm_decisions(top=3)), ("top 5", cm_decisions(top=5)),
                ("6-1 month momentum", cm_decisions(lookback=6)),
                ("12-month momentum, no skipped month", cm_decisions(skip=0))]
    neighbours = [(nm, r["dates"], r["net"]) for nm, dv in variants for r in (cm_run(dv),)]

    rows = holding_returns(dec)
    oos = [j for j, (t, _) in enumerate(rows) if t >= CM_OOS]
    oos_rows, oos_picks = [rows[j] for j in oos], [dec[j][1] for j in oos]
    rng = random.Random(evaluate.SEED_PLACEBO)
    placebo = [picks_sharpe(oos_rows, [rng.sample(COUNTRIES, 4) for _ in oos_rows]) for _ in range(1000)]

    d = yahoo("SPY")["dates"]

    def vector(cut):
        v = [None] * len(d)
        for i, held in cm_decisions(cut_date=None if cut is None else d[cut]):
            v[i] = held
        return v

    held_oos = [h for i, h in dec if d[i] >= CM_OOS]
    efa = yahoo("EFA")
    efa_rf = rf_list(efa["dates"])
    efa_ex = [efa["close"][i] / efa["close"][i - 1] - 1 - efa_rf[i]
              for i in range(1, len(efa["dates"])) if efa["dates"][i] >= CM_OOS]
    return [record(
        id="H44", cluster="CTRYMOM", name="Country momentum: top 4 of 17 iShares country ETFs by 12-1 month return",
        periods=252,
        hypothesis="Countries whose stock markets rose most over the past year (skipping the last month) keep "
                   "beating the other countries",
        data="Yahoo 17 iShares country ETFs + EFA (adjusted) 1996->, ^IRX", costs="5bp/side (2x: 10bp)",
        dates=base["dates"], net=base["net"], gross=base["gross"], net_2x=x2["net"], oos_start=CM_OOS,
        bench="EW17", implementable=True, survivor_universe=False, neighbours=neighbours, placebo=placebo,
        placebo_actual=picks_sharpe(oos_rows, oos_picks), turnover=base["turnover"], rf=base["rf"],
        leakage=leakage.truncation_test(vector, len(d), lag=0),
        extra={"decisions": len(dec), "first_decision": d[dec[0][0]],
               "oos_share_of_months_held": {s: round(sum(s in h for h in held_oos) / len(held_oos), 3)
                                            for s in COUNTRIES},
               "oos_names_changed_per_month": round(sum(len(set(a) ^ set(b)) / 2 for a, b in zip(held_oos, held_oos[1:]))
                                                    / max(1, len(held_oos) - 1), 2),
               "efa_oos_excess_cagr": round(stats.ann_return(efa_ex, 252), 4)},
        notes=["G2 benchmark EW17 = daily-rebalanced equal weight of the same 17 ETFs (no-signal control).",
               "G7 compares the annualized Sharpe of monthly open-to-open holding returns (after costs, excess of "
               "cash) of the real picks with 1,000 random 4-of-17 picks per month."],
        unregistered=[UNREG_RF, "Yahoo's open is used as the next-open fill; the official opening-auction "
                                "print can differ."])]


# ----------------------------------------------------------------------- H45

CURRENCIES = {   # FRED H.10 series; True when quoted as US dollars per unit of the currency
    "EUR": ("DEXUSEU", True), "JPY": ("DEXJPUS", False), "GBP": ("DEXUSUK", True), "CHF": ("DEXSZUS", False),
    "CAD": ("DEXCAUS", False), "AUD": ("DEXUSAL", True), "NZD": ("DEXUSNZ", True), "SEK": ("DEXSDUS", False),
    "NOK": ("DEXNOUS", False)}
RATE_CODE = {"USD": "US", "EUR": "EZ", "JPY": "JP", "GBP": "GB", "CHF": "CH", "CAD": "CA", "AUD": "AU", "NZD": "NZ",
             "SEK": "SE", "NOK": "NO"}
FX_START, FX_OOS = "2002-07", "2008-01"     # first return month; first out-of-sample return month
FX_COST, FX_MARKUP = 0.0003, 0.005          # per side per unit of turnover; per year per unit of notional


def shift(ym, k):
    m = int(ym[:4]) * 12 + int(ym[5:7]) - 1 + k
    return f"{m // 12:04d}-{m % 12 + 1:02d}"


@functools.lru_cache(maxsize=None)
def month_end_spots():
    """{currency: {YYYY-MM: US dollars per unit at the month's last print}}, complete months only."""
    out = {}
    for cur, (sid, usd_per_unit) in CURRENCIES.items():
        s = sources.fred(sid)
        last = {}
        for day in sorted(s):
            last[day[:7]] = s[day] if usd_per_unit else 1 / s[day]
        out[cur] = last
    latest = max(max(v) for v in out.values())
    return {cur: {m: x for m, x in v.items() if m < latest} for cur, v in out.items()}


@functools.lru_cache(maxsize=None)
def rate_values():
    return {cur: {day[:7]: v for day, v in sources.fred(f"IR3TIB01{code}M156N").items()}
            for cur, code in RATE_CODE.items()}


@functools.lru_cache(maxsize=None)
def formation_rates(m, lag=2, published_through=None):
    """{currency: % a year} known when forming at the end of month m: the value for month m-lag, or the latest
    earlier one up to 12 months older. `published_through` drops values for later months (truncation test)."""
    target, out = shift(m, -lag), {}
    for cur, vals in rate_values().items():
        for k in range(13):
            ym = shift(target, -k)
            if ym in vals and (published_through is None or ym <= published_through):
                out[cur] = vals[ym]
                break
    return out


def carry_decisions(k=3, lag=2, long_only=False, cut=None):
    """[(formation month, longs, shorts)] at each month-end with all 10 rates known; `cut` keeps data through it."""
    out = []
    for m in sorted(month_end_spots()["EUR"]):
        if m < shift(FX_START, -1) or (cut is not None and m > cut):
            continue
        r = formation_rates(m, lag, None if cut is None else shift(cut, -lag))
        if len(r) < len(RATE_CODE):
            continue
        ranked = sorted(r, key=lambda c: (-r[c], c))
        out.append((m, tuple(ranked[:k]), () if long_only else tuple(ranked[-k:])))
    return out


def carry_run(dec, lag=2, cost=FX_COST, markup=FX_MARKUP):
    """Monthly returns of the positions formed at each month-end: spot move plus the rate gap, less costs."""
    spots = month_end_spots()
    out = {"dates": [], "gross": [], "net": [], "turnover": []}
    prev = {}
    for m, longs, shorts in dec:
        nxt = shift(m, 1)
        if nxt not in spots["EUR"]:
            continue
        rates = formation_rates(m, lag)
        w = {c: 1 / len(longs) for c in longs}
        w.update({c: -1 / len(shorts) for c in shorts})

        def leg(c):
            if c == "USD":
                return 0.0
            return spots[c][nxt] / spots[c][m] - 1 + (rates[c] - rates["USD"]) / 1200

        gross = sum(x * leg(c) for c, x in w.items())
        turnover = sum(abs(w.get(c, 0.0) - prev.get(c, 0.0)) for c in set(w) | set(prev) if c != "USD")
        notional = sum(abs(x) for c, x in w.items() if c != "USD")
        out["dates"].append(nxt)
        out["gross"].append(gross)
        out["turnover"].append(turnover)
        out["net"].append(gross - cost * turnover - markup / 12 * notional)
        prev = w
    return out


def h45(spy_ex):
    dec = carry_decisions()
    base, x2 = carry_run(dec), carry_run(dec, cost=2 * FX_COST, markup=2 * FX_MARKUP)
    variants = [("top/bottom 2", carry_decisions(k=2), 2), ("top/bottom 4", carry_decisions(k=4), 2),
                ("long the top 3 only, against USD", carry_decisions(long_only=True), 2),
                ("rates lagged 1 month", carry_decisions(lag=1), 1)]
    neighbours = [(nm, r["dates"], r["net"]) for nm, dv, lag in variants for r in (carry_run(dv, lag=lag),)]

    oos = [(m, longs, shorts) for m, longs, shorts in dec if shift(m, 1) >= FX_OOS]
    currencies = tuple(RATE_CODE)
    rng = random.Random(evaluate.SEED_PLACEBO)
    placebo = []
    for _ in range(1000):
        fake = []
        for m, _, _ in oos:
            pick = rng.sample(currencies, 6)
            fake.append((m, tuple(pick[:3]), tuple(pick[3:])))
        placebo.append(stats.sharpe(carry_run(fake)["net"], periods=12))

    months = sorted(month_end_spots()["EUR"])

    def vector(cut):
        v = [None] * len(months)
        for m, longs, shorts in carry_decisions(cut=None if cut is None else months[cut]):
            v[months.index(m)] = (longs, shorts)
        return v

    no_markup = carry_run(dec, markup=0.0)
    gap = [sum(formation_rates(m)[c] for c in longs) / len(longs) - sum(formation_rates(m)[c] for c in shorts) / len(shorts)
           for m, longs, shorts in oos]
    oos_net = [(t, x) for t, x in zip(base["dates"], base["net"]) if t >= FX_OOS]
    return [record(
        id="H45", cluster="FXCARRY", name="G10 carry: long top 3 / short bottom 3 of 10 currencies by 3-month rate",
        periods=12,
        hypothesis="High-interest-rate currencies earn more than their exchange rates give back, so long high-rate / "
                   "short low-rate currencies earns a positive excess return",
        data="FRED H.10 daily FX + OECD 3-month interbank rates (2-month lag) 2002->, French Mkt-RF; Yahoo DBV (live)",
        costs="3bp/side x turnover + 0.5%/yr rollover markup x notional (2x both)",
        dates=base["dates"], net=base["net"], gross=base["gross"], net_2x=x2["net"], oos_start=FX_OOS,
        bench="MKT", implementable=True, survivor_universe=False, neighbours=neighbours, placebo=placebo,
        live=[live_alpha("DBV", spy_ex)], turnover=base["turnover"],
        leakage=leakage.truncation_test(vector, len(months), lag=0),
        extra={"oos_net_excess_cagr_without_rollover_markup": round(stats.ann_return(
                   [x for t, x in zip(no_markup["dates"], no_markup["net"]) if t >= FX_OOS], 12), 4),
               "oos_avg_rate_gap_pct_per_year": round(stats.mean(gap), 2),
               "oos_share_long": {c: round(sum(c in lg for _, lg, _ in oos) / len(oos), 3) for c in currencies},
               "oos_share_short": {c: round(sum(c in sh for _, _, sh in oos) / len(oos), 3) for c in currencies},
               "oos_worst_months": [(t, round(x, 4)) for t, x in sorted(oos_net, key=lambda p: p[1])[:3]]},
        notes=["Monthly returns: spot move plus the formation-month rate gap (covered interest parity), 1/3 per "
               "currency on each side.",
               "G9: DBV (Invesco DB G10 Currency Harvest) ran this idea with futures and was liquidated in 2023."],
        unregistered=["OECD monthly-average 3-month interbank rates stand in for forward points.",
                      "FRED New York noon buying rates stand in for dealer month-end fixes."])]
