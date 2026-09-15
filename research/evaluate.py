"""
Evaluation: the full metric set, the "is this real?" statistics, and the gates.
==============================================================================

Every hypothesis is judged by this one module, so none gets a friendlier test:

  full_metrics()      the complete metric set from PROGRAM.md section 5
  ols_nw()            OLS with Newey-West errors - alpha vs repackaged beta
  bootstrap_sharpe()  stationary block bootstrap CI for a Sharpe ratio
  mc_horizon()        bootstrap distribution of 1y / 3y outcomes (later reused
                      as the paper/live drift band)
  Regimes             after-the-fact regime labels - NEVER a trading input
  evaluate_gates()    the pre-registered G1-G9 and PASS / WATCH / FAIL / NI

Pure stdlib.
"""

import bisect
import datetime as dt
import math
import operator
import random

import stats
from stats import mean

SEED_BOOT = 20260910
SEED_PLACEBO = 20260911

CRISES = [("GFC", "2007-10-09", "2009-03-09"),
          ("Volmageddon", "2018-01-26", "2018-02-09"),
          ("COVID crash", "2020-02-19", "2020-03-23"),
          ("2022 bear", "2022-01-03", "2022-10-12")]


# ------------------------------------------------------------------ metrics

def compound(rets):
    eq = 1.0
    for r in rets:
        eq *= 1 + r
    return eq - 1


def sortino(rets, periods):
    if not rets:
        return 0.0
    dd = math.sqrt(sum(min(r, 0.0) ** 2 for r in rets) / len(rets))
    return mean(rets) / dd * math.sqrt(periods) if dd > 0 else 0.0


def cvar(rets, q=0.05):
    s = sorted(rets)
    return mean(s[:max(1, int(len(s) * q))]) if s else 0.0


def autocorr(rets, lag=1):
    return stats.correlation(rets[lag:], rets[:-lag]) if len(rets) > lag + 2 else 0.0


def recovery(rets):
    """(longest peak-to-recovery span in observations, underwater at the end?)."""
    eq = peak = 1.0
    start = longest = 0
    for i, r in enumerate(rets):
        eq *= 1 + r
        if eq >= peak:
            longest = max(longest, i - start)
            peak, start = eq, i
    return max(longest, len(rets) - 1 - start), eq < peak


def period_returns(dates, rets, key_len=7):
    """Compound returns into periods keyed by date prefix (7 = month, 4 = year)."""
    out = {}
    for d, r in zip(dates, rets):
        out[d[:key_len]] = (1 + out.get(d[:key_len], 0.0)) * (1 + r) - 1
    return out


def percentile(xs, q):
    s = sorted(x for x in xs if x is not None)
    if not s:
        return None
    k = (len(s) - 1) * q
    f, c = math.floor(k), math.ceil(k)
    return s[f] + (s[c] - s[f]) * (k - f)


def full_metrics(dates, net, *, gross=None, periods=252, trades=None, expo=None,
                 turnover=None, rf=None):
    m = {"start": dates[0], "end": dates[-1], "years": len(net) / periods, "n_obs": len(net),
         "net_total_excess": compound(net),
         "gross_total_excess": compound(gross) if gross else None,
         "cagr_excess": stats.ann_return(net, periods),
         "gross_cagr_excess": stats.ann_return(gross, periods) if gross else None,
         "vol": stats.ann_vol(net, periods), "sharpe": stats.sharpe(net, periods=periods),
         "sortino": sortino(net, periods), "max_dd": stats.max_drawdown(net),
         "calmar": stats.calmar(net, periods), "skew": stats.skewness(net),
         "kurt": stats.kurtosis(net), "cvar5": cvar(net), "ac1": autocorr(net)}
    if rf:
        m["cagr_total"] = stats.ann_return([a + b for a, b in zip(net, rf)], periods)
    if periods == 252:
        m["worst_day"] = min(net)
        m["worst_month"] = min(period_returns(dates, net).values())
    else:
        m["worst_day"], m["worst_month"] = None, min(net)
    m["recovery_obs"], m["underwater_at_end"] = recovery(net)
    if trades:
        tr = [t["ret"] for t in trades]
        wins, losses = [x for x in tr if x > 0], [x for x in tr if x <= 0]
        m.update(n_trades=len(tr), win_rate=len(wins) / len(tr), avg_trade=mean(tr),
                 median_trade=percentile(tr, 0.5),
                 profit_factor=(sum(wins) / -sum(losses)) if sum(losses) < 0 else None,
                 avg_nights_held=mean([t["nights"] for t in trades]))
    if expo:
        m.update(expo)
    if turnover:
        m["ann_turnover"] = sum(turnover) / len(turnover) * periods
    return m


# ---------------------------------------------------------------- regression

def nw_lags(n):
    return int(math.floor(4 * (n / 100.0) ** (2.0 / 9.0)))


def _inverse(A):
    n = len(A)
    M = [list(row) + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(A)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-300:
            raise ZeroDivisionError("singular design matrix")
        M[c], M[p] = M[p], M[c]
        piv = M[c][c]
        M[c] = [v / piv for v in M[c]]
        for r in range(n):
            if r != c and M[r][c]:
                f = M[r][c]
                M[r] = [x - f * y for x, y in zip(M[r], M[c])]
    return [row[n:] for row in M]


def _matmul(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(len(B))) for j in range(len(B[0]))]
            for i in range(len(A))]


def ols_nw(y, xcols, lags=None):
    """
    y ~ const + xcols with Newey-West (Bartlett) standard errors.
    coef[0] is alpha per period; t[0] its HAC t-stat.
    """
    n, k = len(y), len(xcols) + 1
    mul = operator.mul
    cols = [[1.0] * n] + [list(c) for c in xcols]
    xtx = [[sum(map(mul, cols[a], cols[b])) for b in range(k)] for a in range(k)]
    xty = [sum(map(mul, cols[a], y)) for a in range(k)]
    inv = _inverse(xtx)
    beta = [sum(inv[a][b] * xty[b] for b in range(k)) for a in range(k)]
    fitted = [0.0] * n
    for a in range(k):
        fitted = [f + beta[a] * x for f, x in zip(fitted, cols[a])]
    e = [yy - f for yy, f in zip(y, fitted)]
    L = nw_lags(n) if lags is None else lags
    g = [[x * ee for x, ee in zip(cols[a], e)] for a in range(k)]
    S = [[0.0] * k for _ in range(k)]
    for lag in range(L + 1):
        w = 1.0 if lag == 0 else 1.0 - lag / (L + 1.0)
        for a in range(k):
            for b in range(k):
                s = sum(map(mul, g[a][lag:], g[b][:n - lag]))
                S[a][b] += w * s
                if lag:
                    S[b][a] += w * s
    V = _matmul(_matmul(inv, S), inv)
    se = [math.sqrt(max(V[a][a], 0.0)) for a in range(k)]
    ybar = mean(y)
    sst = sum((v - ybar) ** 2 for v in y)
    return {"coef": beta, "se": se, "n": n, "lags": L,
            "t": [beta[a] / se[a] if se[a] > 0 else 0.0 for a in range(k)],
            "r2": 1 - sum(v * v for v in e) / sst if sst else 0.0}


# ----------------------------------------------------------------- bootstrap

def _prefix(xs):
    p = [0.0]
    for v in xs:
        p.append(p[-1] + v)
    return p


def _seg_sum(P, i, L, n):
    total, pos = 0.0, i
    while L > 0:
        take = min(L, n - pos)
        total += P[pos + take] - P[pos]
        L -= take
        pos = 0
    return total


def _geom(rng, log_q):
    u = rng.random()
    while u <= 0.0:
        u = rng.random()
    return max(1, int(math.ceil(math.log(u) / log_q)))


def bootstrap_sharpe(rets, periods, B=2000, block=21, seed=SEED_BOOT):
    """Stationary (Politis-Romano) bootstrap distribution of the annualised Sharpe."""
    n = len(rets)
    if n < 10:
        return []
    P1, P2 = _prefix(rets), _prefix([r * r for r in rets])
    rng, log_q = random.Random(seed), math.log(1.0 - 1.0 / block)
    out = []
    for _ in range(B):
        s1 = s2 = 0.0
        got = 0
        while got < n:
            L = min(_geom(rng, log_q), n - got)
            i = rng.randrange(n)
            s1 += _seg_sum(P1, i, L, n)
            s2 += _seg_sum(P2, i, L, n)
            got += L
        m = s1 / n
        var = (s2 - n * m * m) / (n - 1)
        out.append(m / math.sqrt(var) * math.sqrt(periods) if var > 1e-18 else 0.0)
    return out


def mc_horizon(rets, horizon, B=1000, block=21, seed=SEED_BOOT):
    """Bootstrap paths of `horizon` observations: P(loss), return and drawdown bands."""
    n = len(rets)
    if n < 2 * block:
        return None
    rng, log_q = random.Random(seed + horizon), math.log(1.0 - 1.0 / block)
    finals, dds = [], []
    for _ in range(B):
        path = []
        while len(path) < horizon:
            L = min(_geom(rng, log_q), horizon - len(path))
            i = rng.randrange(n)
            while L > 0:
                seg = rets[i:i + L]
                path.extend(seg)
                L -= len(seg)
                i = 0
        finals.append(compound(path))
        dds.append(stats.max_drawdown(path))
    return {"p_loss": sum(f < 0 for f in finals) / B, "p5_return": percentile(finals, 0.05),
            "median_return": percentile(finals, 0.5), "p95_return": percentile(finals, 0.95),
            "p5_max_dd": percentile(dds, 0.05)}


# ------------------------------------------------------------------- regimes

class Regimes:
    """
    After-the-fact regime labels, for showing WHEN a strategy works and fails.
    Never a trading input: NBER dates are announced months later, CPI weeks later.

      bull_bear   market total-return index > 20% below its running peak = bear
      vol         63d realised vol above/below the expanding median of past values
      rates       10y yield vs one year earlier: rising / falling
      recession   NBER USREC
      inflation   CPI YoY >= 4% = high
    """

    def __init__(self, mkt, dgs10, usrec, cpi):
        rate_dates = sorted(dgs10)
        cpi_m = {k[:7]: v for k, v in cpi.items()}
        self.by_date, self.month_end = {}, {}
        eq = peak = 1.0
        window, past_vols = [], []
        for d in sorted(mkt):
            r = mkt[d]
            eq *= 1 + r
            peak = max(peak, eq)
            window.append(r)
            if len(window) > 63:
                window.pop(0)
            lab = {"bull_bear": "bear" if eq / peak - 1 <= -0.20 else "bull"}
            if len(window) == 63:
                v = stats.stdev(window)
                if past_vols:
                    lab["vol"] = "high" if v > past_vols[len(past_vols) // 2] else "low"
                bisect.insort(past_vols, v)
            j = bisect.bisect_right(rate_dates, d) - 1
            prior = (dt.date.fromisoformat(d) - dt.timedelta(days=365)).isoformat()
            k = bisect.bisect_right(rate_dates, prior) - 1
            if j >= 0 and k >= 0 and rate_dates[k] >= "1962":
                lab["rates"] = "rising" if dgs10[rate_dates[j]] > dgs10[rate_dates[k]] else "falling"
            rec = usrec.get(d[:7] + "-01")
            if rec is not None:
                lab["recession"] = "recession" if rec >= 1 else "expansion"
            y0 = f"{int(d[:4]) - 1:04d}{d[4:7]}"
            if d[:7] in cpi_m and y0 in cpi_m:
                lab["inflation"] = "high" if cpi_m[d[:7]] / cpi_m[y0] - 1 >= 0.04 else "low"
            self.by_date[d] = lab
            self.month_end[d[:7]] = lab

    def label(self, d):
        return self.month_end.get(d) if len(d) == 7 else self.by_date.get(d)


def regime_table(dates, rets, periods, regimes):
    groups = {}
    for d, r in zip(dates, rets):
        for key, val in (regimes.label(d) or {}).items():
            groups.setdefault(f"{key}={val}", []).append(r)
    n = len(rets) or 1
    return {k: {"share": len(x) / n, "ann_mean": mean(x) * periods,
                "sharpe": stats.sharpe(x, periods=periods) if len(x) > 20 else None}
            for k, x in sorted(groups.items())}


def crisis_returns(dates, rets):
    out = {}
    for name, lo, hi in CRISES:
        if len(dates[0]) == 7:
            lo, hi = lo[:7], hi[:7]
        seg = [r for d, r in zip(dates, rets) if lo <= d <= hi]
        out[name] = compound(seg) if seg else None
    return out


# --------------------------------------------------------------------- gates

def thirds(rets):
    k = len(rets) // 3
    return [rets[:k], rets[k:2 * k], rets[2 * k:]]


def evaluate_gates(*, oos, periods, reg_y, reg_x, oos_2x, neighbours, placebo, implementable,
                   live, n_trials, sr_disp, block, sensitivity=(17, 200), placebo_actual=None,
                   survivorship_free=None):
    """
    The pre-registered G1-G9 on an out-of-sample net excess series.
    reg_y/reg_x: the G2 regression, already date-aligned to the benchmark.
    neighbours: [(name, series)]; placebo: [sharpe] or None; live: [dict] or None.
    """
    g = {}
    sr = stats.sharpe(oos, periods=periods)
    boot = bootstrap_sharpe(oos, periods, block=block)
    lo, hi = percentile(boot, 0.025), percentile(boot, 0.975)
    g["G1"] = {"pass": sr > 0 and lo is not None and lo > 0,
               "detail": f"SR {sr:.2f}, 95% CI [{lo:.2f}, {hi:.2f}]"}

    reg = ols_nw(reg_y, [reg_x])
    a, t = reg["coef"][0], reg["t"][0]
    g["G2"] = {"pass": a > 0 and t >= 2.0,
               "detail": f"alpha {a * periods * 100:+.2f}%/yr, NW t {t:.2f}, beta {reg['coef'][1]:.2f}"}

    dsr, bar = stats.deflated_sharpe(oos, n_trials, sr_disp, periods)
    sens = ", ".join(f"N={n}: {stats.deflated_sharpe(oos, n, sr_disp, periods)[0]:.3f}"
                     for n in sensitivity)
    g["G3"] = {"pass": dsr >= 0.95,
               "detail": f"DSR {dsr:.3f} vs luck bar SR {bar:.2f} (N={n_trials}, "
                         f"disp {sr_disp:.2f}); {sens}"}

    sr2 = stats.sharpe(oos_2x, periods=periods)
    g["G4"] = {"pass": sr2 > 0, "detail": f"SR at 2x costs {sr2:.2f}"}

    parts = [compound(p) for p in thirds(oos)]
    g["G5"] = {"pass": sum(p > 0 for p in parts) >= 2,
               "detail": "thirds " + " / ".join(f"{p * 100:+.1f}%" for p in parts)}

    if neighbours:
        nsr = [(nm, stats.sharpe(s, periods=periods)) for nm, s in neighbours]
        pos = sum(s > 0 for _, s in nsr) / len(nsr)
        med = percentile([s for _, s in nsr], 0.5)
        g["G6"] = {"pass": sr > 0 and pos >= 0.75 and med >= 0.5 * sr,
                   "detail": f"{pos * 100:.0f}% positive, median SR {med:.2f} vs base {sr:.2f}: "
                             + ", ".join(f"{nm} {s:.2f}" for nm, s in nsr)}
    else:
        g["G6"] = {"pass": None, "detail": "no neighbours available"}

    if placebo and placebo_actual is None:
        p95 = percentile(placebo, 0.95)
        rank = sum(p >= sr for p in placebo) / len(placebo)
        g["G7"] = {"pass": sr > p95,
                   "detail": f"placebo p95 SR {p95:.2f}, median {percentile(placebo, 0.5):.2f}; "
                             f"share of placebos >= base {rank * 100:.1f}%"}
    elif placebo:
        # hypothesis-specific placebo statistic (e.g. an event-return spread), not the Sharpe
        p95 = percentile(placebo, 0.95)
        rank = sum(p >= placebo_actual for p in placebo) / len(placebo)
        g["G7"] = {"pass": placebo_actual > p95,
                   "detail": f"statistic {placebo_actual:.4f} vs placebo p95 {p95:.4f}, median "
                             f"{percentile(placebo, 0.5):.4f}; share of placebos >= actual {rank * 100:.1f}%"}
    else:
        g["G7"] = {"pass": None, "detail": "no placebo defined"}

    g["G8"] = {"pass": implementable, "detail": "retail-implementable" if implementable
               else "not implementable in a retail account"}

    eligible = [x for x in (live or []) if x.get("years", 0) >= 4.0]
    if eligible:
        g["G9"] = {"pass": all(x["alpha"] > 0 for x in eligible),
                   "detail": "; ".join(f"{x['fund']} {x['years']:.1f}y alpha {x['alpha'] * 100:+.2f}%/yr "
                                       f"t {x['t']:.2f}" for x in live)}
    else:
        g["G9"] = {"pass": None, "detail": "no live fund with >= 4y" +
                   (": " + "; ".join(f"{x['fund']} {x['years']:.1f}y" for x in live) if live else "")}

    if survivorship_free is not None:
        g["G10"] = {"pass": survivorship_free,
                    "detail": "survivorship-free data" if survivorship_free else
                    "stock universe is today's index members (survivorship bias)"}

    fails = {k for k, v in g.items() if v["pass"] is False}
    if fails & {"G1", "G2", "G4"}:
        status = "FAIL"
    elif "G8" in fails:
        status = "NI"
    elif "G10" in fails:
        status = "WATCH-SB"
    elif fails:
        status = "WATCH"
    else:
        status = "PASS"
    return {"gates": g, "status": status, "failed": sorted(fails), "sharpe": sr,
            "ci": (lo, hi), "alpha_ann": a * periods, "alpha_t": t, "beta": reg["coef"][1],
            "dsr": dsr}
