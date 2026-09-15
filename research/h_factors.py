"""
Equity factor hypotheses on survivorship-free CRSP data (Ken French library).
============================================================================
Exact rules: PREREG_PHASE1.md.

  H08  long/short factor premia   - academic portfolios, gross of real shorting frictions
  H09  long-only tilts            - what a retail account could approximate with ETFs
  H10  industry momentum          - long/short and long-only, plus a sector-ETF version

French forms the H08/H09 portfolios with his own lags (accounting data at least
six months old at the June formation), so there is no weight function of ours
to truncation-test there. H10 forms its own portfolios and is tested.
"""

import math
import random

import engine
import evaluate
import leakage
import sources
import stats
from h_common import by_decade, live_alpha, record, rf_list, yahoo

FF3 = "F-F_Research_Data_Factors_CSV.zip"
FF5 = "F-F_Research_Data_5_Factors_2x3_CSV.zip"
IND = "49_Industry_Portfolios_CSV.zip"
SECTORS = ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]
QUINTILES = ["Lo 20", "Qnt 2", "Qnt 3", "Qnt 4", "Hi 20"]
DECILES = ["Lo PRIOR"] + [f"PRIOR {k}" for k in range(2, 10)] + ["Hi PRIOR"]

# id, publication year, factor-file source (None = quintile spread), L/S drag %/yr,
# sorted-portfolio file, which end is held long, quintile ("q") or decile ("d") file
SPEC = [
    ("SMB", 1981, (FF3, "SMB"), 1.0, "Portfolios_Formed_on_ME_CSV.zip", "lo", "q"),
    ("HML", 1985, (FF3, "HML"), 1.0, "Portfolios_Formed_on_BE-ME_CSV.zip", "hi", "q"),
    ("UMD", 1993, ("F-F_Momentum_Factor_CSV.zip", "Mom"), 3.0, "10_Portfolios_Prior_12_2_CSV.zip", "hi", "d"),
    ("STR", 1990, ("F-F_ST_Reversal_Factor_CSV.zip", "ST_Rev"), 8.0, "10_Portfolios_Prior_1_0_CSV.zip", "lo", "d"),
    ("LTR", 1985, ("F-F_LT_Reversal_Factor_CSV.zip", "LT_Rev"), 1.5, "10_Portfolios_Prior_60_13_CSV.zip", "lo", "d"),
    ("RMW", 2013, (FF5, "RMW"), 1.0, "Portfolios_Formed_on_OP_CSV.zip", "hi", "q"),
    ("CMA", 2004, (FF5, "CMA"), 1.0, "Portfolios_Formed_on_INV_CSV.zip", "lo", "q"),
    ("AC", 1996, None, 1.0, "Portfolios_Formed_on_AC_CSV.zip", "lo", "q"),
    ("NI", 2008, None, 1.0, "Portfolios_Formed_on_NI_CSV.zip", "lo", "q"),
    ("BETA", 1972, None, 1.0, "Portfolios_Formed_on_BETA_CSV.zip", "lo", "q"),
    ("RESVAR", 2006, None, 3.0, "Portfolios_Formed_on_RESVAR_CSV.zip", "lo", "q"),
]

NAMES = {"SMB": "size (small minus big)", "HML": "value (high minus low book-to-market)",
         "UMD": "momentum (12-2)", "STR": "short-term reversal (1-0)",
         "LTR": "long-term reversal (60-13)", "RMW": "profitability (robust minus weak)",
         "CMA": "investment (conservative minus aggressive)", "AC": "accruals (low minus high)",
         "NI": "net share issuance (low minus high)", "BETA": "low beta (low minus high)",
         "RESVAR": "low residual variance (low minus high)"}

LIVE_LO = {"UMD": ["MTUM"], "HML": ["VLUE", "IWD"], "RMW": ["QUAL", "SPHQ"],
           "BETA": ["USMV", "SPLV"], "SMB": ["IWM"]}

COST_NOTE = ("Cost drag is an order-of-magnitude assumption (Novy-Marx & Velikov 2016), not "
             "measured here; break_even_drag_pct_yr lets a reader substitute their own.")
NI_NOTE = ("NI quintiles exclude French's '< 0' (net repurchasers) and 'ZERO' groups, so 'Lo 20' "
           "is the lowest POSITIVE-issuance quintile, not buyback firms.")


def vw(name, col):
    return sources.french_column(name, col, "Value Weight")


def ew(name, col):
    return sources.french_column(name, col, "Equal Weight")


def _diff(a, b):
    return {p: a[p] - b[p] for p in a if p in b}


def _ends(kind, side):
    lo = side == "lo"
    if kind == "q":
        return {"long": "Lo 20" if lo else "Hi 20", "short": "Hi 20" if lo else "Lo 20",
                "long_x": "Lo 10" if lo else "Hi 10", "short_x": "Hi 10" if lo else "Lo 10"}
    return {"long": "Lo PRIOR" if lo else "Hi PRIOR", "short": "Hi PRIOR" if lo else "Lo PRIOR",
            "adjacent": "PRIOR 2" if lo else "PRIOR 9"}


def _series(dct, drag):
    ps = sorted(dct)
    return ps, [dct[p] - drag / 12.0 for p in ps], [dct[p] for p in ps]


def _pub_stats(ps, gross, oos):
    pre = [g for p, g in zip(ps, gross) if p < oos]
    post = [g for p, g in zip(ps, gross) if p >= oos]
    m_pre, m_post = (stats.mean(pre) if pre else None), stats.mean(post)
    return {"pre_pub_gross_sharpe": round(stats.sharpe(pre, periods=12), 3) if len(pre) >= 36 else None,
            "pre_pub_gross_pct_yr": round(m_pre * 1200, 2) if pre else None,
            "post_pub_gross_sharpe": round(stats.sharpe(post, periods=12), 3),
            "break_even_drag_pct_yr": round(m_post * 1200, 2),
            "post_vs_pre_mean_change_pct": round((m_post / m_pre - 1) * 100, 0)
            if m_pre and m_pre > 0 else None}


# ----------------------------------------------------------------- H08 / H09

def h08_h09(mktrf, rf, spy_ex):
    qmnix, btal = live_alpha("QMNIX", spy_ex), live_alpha("BTAL", spy_ex)
    live_lo = {f: live_alpha(f, spy_ex) for fs in LIVE_LO.values() for f in fs}
    ls_out, lo_out = [], []
    for fid, pub, src, drag_pct, fname, side, kind in SPEC:
        oos, e, dr = f"{pub + 1}-01", _ends(kind, side), drag_pct / 100.0
        short_name = fname.replace("_CSV.zip", "")
        unreg = [COST_NOTE] + ([NI_NOTE] if fid == "NI" else [])

        # ---- H08 long/short
        ls = sources.french_column(*src) if src else _diff(vw(fname, e["long"]), vw(fname, e["short"]))
        ps, net, gross = _series(ls, dr)
        net2 = _series(ls, 2 * dr)[1]
        if kind == "q":
            nb = [("VW decile spread", _diff(vw(fname, e["long_x"]), vw(fname, e["short_x"])), dr),
                  ("EW quintile spread", _diff(ew(fname, e["long"]), ew(fname, e["short"])), 2 * dr)]
        else:
            nb = [("VW decile spread", _diff(vw(fname, e["long"]), vw(fname, e["short"])), dr),
                  ("EW decile spread", _diff(ew(fname, e["long"]), ew(fname, e["short"])), 2 * dr)]
        ls_out.append(record(
            id=f"H08-{fid}", cluster=fid, name=f"L/S {NAMES[fid]}", periods=12,
            hypothesis=f"The {NAMES[fid]} premium survives publication and trading costs",
            data=f"Ken French library, CRSP ({src[1] if src else short_name})",
            costs=f"{drag_pct:.1f}%/yr drag (2x: {2 * drag_pct:.1f}%)",
            dates=ps, net=net, gross=gross, net_2x=net2, oos_start=oos, bench="MKT",
            neighbours=[(nm,) + _series(dct, d_)[:2] for nm, dct, d_ in nb],
            implementable=False, live=[qmnix] + ([btal] if fid == "BETA" else []),
            extra=dict(_pub_stats(ps, gross, oos), publication_year=pub,
                       gross_sharpe_by_decade=by_decade(ps, gross, 12)),
            notes=["Academic long/short portfolio: value-weighted, NYSE breakpoints, gross of "
                   "borrow fees, recalls and short-sale constraints."],
            unregistered=unreg))

        # ---- H09 long-only tilt
        dl = dr / 2
        leg = vw(fname, e["long"])
        pl = [p for p in sorted(leg) if p in mktrf and p in rf]
        gross_a = [leg[p] - mktrf[p] - rf[p] for p in pl]
        if kind == "q":
            nb_legs = [("VW extreme decile", vw(fname, e["long_x"]), dl),
                       ("EW same quintile", ew(fname, e["long"]), 2 * dl)]
        else:
            nb_legs = [("VW adjacent decile", vw(fname, e["adjacent"]), dl),
                       ("EW same decile", ew(fname, e["long"]), 2 * dl)]
        lo_nb = []
        for nm, dct, d_ in nb_legs:
            pp = [p for p in sorted(dct) if p in mktrf and p in rf]
            lo_nb.append((nm, pp, [dct[p] - mktrf[p] - rf[p] - d_ / 12 for p in pp]))
        ctrl = [vw(fname, c) for c in (QUINTILES if kind == "q" else DECILES)]
        cp = [p for p in pl if p >= oos and all(p in c for c in ctrl)]
        ctrl_active = [leg[p] - sum(c[p] for c in ctrl) / len(ctrl) for p in cp]
        pubs = {k.replace("gross", "active"): v for k, v in _pub_stats(pl, gross_a, oos).items()}
        lo_out.append(record(
            id=f"H09-{fid}", cluster=fid, name=f"long-only {NAMES[fid]} tilt", periods=12,
            hypothesis=f"A long-only tilt toward {NAMES[fid].split(' (')[0]} beats the market after costs",
            data=f"Ken French library, CRSP ({short_name}, VW {e['long']}); live ETFs",
            costs=f"{drag_pct / 2:.2f}%/yr drag (2x: {drag_pct:.2f}%)",
            dates=pl, net=[g - dl / 12 for g in gross_a], gross=gross_a,
            net_2x=[g - 2 * dl / 12 for g in gross_a], oos_start=oos, bench="MKT",
            alpha_y=[leg[p] - rf[p] - dl / 12 for p in pl], neighbours=lo_nb, implementable=True,
            live=[live_lo[f] for f in LIVE_LO.get(fid, [])] or None,
            extra=dict(pubs, publication_year=pub,
                       oos_active_vs_ew_of_sorted_portfolios_pct_yr=round(stats.mean(ctrl_active) * 1200, 2),
                       oos_ir_vs_ew_of_sorted_portfolios=round(stats.sharpe(ctrl_active, periods=12), 3)),
            notes=["G1 and G3-G6 use ACTIVE return vs the CRSP value-weighted market; G2 is the "
                   "CAPM alpha of the long leg itself."],
            unregistered=unreg))
    return ls_out + lo_out


# ----------------------------------------------------------------------- H10

def indmom_select(R, i, L=12, s=1, frac=0.2):
    """(long, short, eligible) industry indices decided at the end of month i, or None."""
    a, b = i - (L - 1), i - s
    if a < 0:
        return None
    scores = []
    for j in range(len(R[i])):
        prod = 1.0
        for t in range(a, b + 1):
            v = R[t][j]
            if v is None:
                break
            prod *= 1 + v
        else:
            scores.append((prod - 1, j))
    if len(scores) < 20:
        return None
    k = int(math.floor(frac * len(scores)))
    scores.sort()
    return (tuple(sorted(j for _, j in scores[-k:])), tuple(sorted(j for _, j in scores[:k])),
            tuple(sorted(j for _, j in scores)))


def indmom_path(R, L=12, s=1, frac=0.2, cut=None):
    if cut is not None:
        R = R[:cut + 1] + [[None] * len(R[0])] * (len(R) - cut - 1)
    return [indmom_select(R, i, L, s, frac) for i in range(len(R))]


def _avg(row, js):
    return sum(row[j] if row[j] is not None else 0.0 for j in js) / len(js)


def indmom_returns(months, R, sel, rf):
    out = {k: [] for k in ("dates", "ls", "ls_gross", "ls2", "lo", "lo_gross", "lo2", "alpha_y")}
    for i in range(len(months) - 1):
        x, p = sel[i], months[i + 1]
        if x is None or p not in rf:
            continue
        longs, shorts, elig = x
        row = R[i + 1]
        rl, rs, re_ = _avg(row, longs), _avg(row, shorts), _avg(row, elig)
        out["dates"].append(p)
        out["ls_gross"].append(rl - rs)
        out["ls"].append(rl - rs - 0.02 / 12)
        out["ls2"].append(rl - rs - 0.04 / 12)
        out["lo_gross"].append(rl - re_)
        out["lo"].append(rl - re_ - 0.01 / 12)
        out["lo2"].append(rl - re_ - 0.02 / 12)
        out["alpha_y"].append(rl - rf[p] - 0.01 / 12)
    return out


def sector_etf_momentum():
    """Reported, not gated: the tradeable version on the 9 original SPDR sectors."""
    ys = {s: yahoo(s) for s in SECTORS}
    common = sorted(set.intersection(*(set(y["dates"]) for y in ys.values())))
    n = len(common)
    pos = {s: {d: i for i, d in enumerate(ys[s]["dates"])} for s in SECTORS}
    C = {s: [ys[s]["close"][pos[s][d]] for d in common] for s in SECTORS}
    O = {s: [ys[s]["open"][pos[s][d]] for d in common] for s in SECTORS}
    me = [i for i in range(n - 1) if common[i + 1][:7] != common[i][:7]]
    W = {s: [0.0] * n for s in SECTORS}
    for k in range(12, len(me)):
        ranked = sorted(((C[s][me[k - 1]] / C[s][me[k - 12]] - 1, s) for s in SECTORS), reverse=True)
        top = {s for _, s in ranked[:3]}
        for s in SECTORS:
            for j in range(me[k], me[k + 1] if k + 1 < len(me) else n):
                W[s][j] = 1.0 / 3 if s in top else 0.0
    rf = rf_list(common)
    strat, ew9 = [0.0] * (n - 1), [0.0] * (n - 1)
    for s in SECTORS:
        a = engine.simulate(common, O[s], C[s], *engine.next_open_exec(W[s]), rf, cost_per_side=0.0002)
        b = engine.simulate(common, O[s], C[s], *engine.close_exec([1.0 / 9] * n), rf)
        strat = [x + y for x, y in zip(strat, a["net"])]
        ew9 = [x + y for x, y in zip(ew9, b["net"])]
    start = me[12]
    s_, e_ = strat[start:], ew9[start:]
    act = [x - y for x, y in zip(s_, e_)]
    return {"start": common[start + 1], "end": common[-1],
            "strategy_sharpe": round(stats.sharpe(s_), 3), "ew9_sharpe": round(stats.sharpe(e_), 3),
            "strategy_cagr_excess": round(stats.ann_return(s_), 4),
            "ew9_cagr_excess": round(stats.ann_return(e_), 4),
            "active_pct_yr": round(stats.mean(act) * 25200, 2), "active_ir": round(stats.sharpe(act), 3),
            "strategy_max_dd": round(stats.max_drawdown(s_), 3),
            "ew9_max_dd": round(stats.max_drawdown(e_), 3)}


def h10(mktrf, rf):
    _, rows = sources.french_table(IND, "Value Weight")
    months = sorted(rows)
    R = [rows[m] for m in months]
    base_sel = indmom_path(R)
    base = indmom_returns(months, R, base_sel, rf)
    nb = [(nm, indmom_returns(months, R, indmom_path(R, **kw), rf))
          for nm, kw in [("6-1 formation", dict(L=6, s=1)), ("12-0 formation", dict(L=12, s=0)),
                         ("6-0 formation", dict(L=6, s=0)), ("top/bottom 10%", dict(frac=0.1))]]
    leak = leakage.truncation_test(lambda cut: indmom_path(R, cut=cut), len(months), lag=0)

    oos_i = [i for i in range(len(months) - 1)
             if months[i + 1] >= "2000-01" and base_sel[i] is not None and months[i + 1] in rf]
    ew_elig = {i: _avg(R[i + 1], base_sel[i][2]) for i in oos_i}
    rng = random.Random(evaluate.SEED_PLACEBO)
    pl_ls, pl_lo = [], []
    for _ in range(1000):
        ls_r, lo_r = [], []
        for i in oos_i:
            longs, _, elig = base_sel[i]
            k = len(longs)
            pick = rng.sample(elig, 2 * k)
            rl = _avg(R[i + 1], pick[:k])
            ls_r.append(rl - _avg(R[i + 1], pick[k:]) - 0.02 / 12)
            lo_r.append(rl - ew_elig[i] - 0.01 / 12)
        pl_ls.append(stats.sharpe(ls_r, periods=12))
        pl_lo.append(stats.sharpe(lo_r, periods=12))

    ps = base["dates"]
    unreg = ["Months before the first valid 12-month formation are dropped rather than booked "
             "as zero-return months (pre-sample only)."]
    common = dict(pre_2000_gross_sharpe_ls=round(stats.sharpe(
                      [g for p, g in zip(ps, base["ls_gross"]) if p < "2000-01"], periods=12), 3),
                  gross_sharpe_by_decade_ls=by_decade(ps, base["ls_gross"], 12),
                  gross_sharpe_by_decade_lo=by_decade(ps, base["lo_gross"], 12))
    ls_rec = record(
        id="H10-LS", cluster="INDMOM", name="L/S industry momentum (49 industries, 12-1)",
        periods=12, hypothesis="Industries that outperformed over the past year (skipping the "
                               "last month) keep outperforming next month",
        data="Ken French 49 industry portfolios (VW), CRSP 1926->", costs="2.0%/yr drag (2x: 4.0%)",
        dates=ps, net=base["ls"], gross=base["ls_gross"], net_2x=base["ls2"], oos_start="2000-01",
        bench="MKT", neighbours=[(nm, x["dates"], x["ls"]) for nm, x in nb], placebo=pl_ls,
        implementable=False, leakage=leak, extra=common, unregistered=unreg)
    lo_rec = record(
        id="H10-LO", cluster="INDMOM", name="Long-only industry momentum vs EW industries",
        periods=12, hypothesis="Holding only last year's winning industries beats holding all "
                               "industries equally",
        data="Ken French 49 industry portfolios (VW), CRSP 1926->; SPDR sector ETFs (reported)",
        costs="1.0%/yr drag (2x: 2.0%)",
        dates=ps, net=base["lo"], gross=base["lo_gross"], net_2x=base["lo2"], oos_start="2000-01",
        bench="MKT", alpha_y=base["alpha_y"], neighbours=[(nm, x["dates"], x["lo"]) for nm, x in nb],
        placebo=pl_lo, implementable=True, leakage=leak,
        extra=dict(common, sector_etf_implementation=sector_etf_momentum()),
        notes=["G1 and G3-G6 use active return vs equal-weighting every eligible industry - the "
               "no-signal control."],
        unregistered=unreg)
    return [ls_rec, lo_rec]
