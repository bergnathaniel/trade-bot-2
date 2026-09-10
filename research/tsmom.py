"""
Time-series momentum (trend following), built the way the literature builds it.
==============================================================================

Every earlier backtest in this project was the same shape: ONE instrument,
long-or-flat, unscaled, judged against buy & hold of that same instrument.
That shape structurally cannot find trend following, whose documented value
is (a) diversification across many uncorrelated markets and (b) low
correlation to equities at the PORTFOLIO level. It has never beaten the S&P
on raw return and does not claim to.

Construction follows Moskowitz-Ooi-Pedersen (2012) / Hurst-Ooi-Pedersen
(2017):

  signal_i(t)  = mean of sign(return over 21d, 63d, 252d)     in [-1, +1]
  vol_i(t)     = EWMA stdev of daily returns, 60d halflife, annualised
  position_i(t)= signal_i(t) * (per_instrument_vol_target / vol_i(t))
  portfolio(t) = mean_i position_i(t), then scaled by a TRAILING estimate
                 so total portfolio vol tracks `target_vol`

Deliberately NOT fitted. The lookbacks are the published ones. Nothing in
here is chosen by looking at the result - that is the entire point, given
this project's history of fitting its way into fake edges.

Lookahead control: signals use data through the close of day t; the position
earns the return from t to t+1. Rebalancing happens every `rebal` days.
"""

import math

from stats import TRADING_DAYS, stdev

DEFAULT_LOOKBACKS = (21, 63, 252)


# ------------------------------------------------------------------ plumbing

def build_panel(dates, by_sym):
    """
    {sym: [close or None per date]} on the shared calendar, forward-filled
    across holidays a given market did not trade (but never filled BEFORE an
    instrument's first real print - no back-filling history that didn't exist).
    """
    panel = {}
    for sym, d in by_sym.items():
        col, last = [], None
        for dt in dates:
            b = d.get(dt)
            if b is not None:
                last = b[4]
            col.append(last)
        panel[sym] = col
    return panel


def to_returns(col):
    """Simple returns aligned to `col`; None where undefined."""
    out = [None]
    for i in range(1, len(col)):
        a, b = col[i - 1], col[i]
        out.append(b / a - 1 if (a and b and a > 0) else None)
    return out


def ewma_vol(rets, halflife=60, floor=1e-4):
    """
    Causal EWMA volatility (annualised), one value per bar. Uses only returns
    strictly up to and including that bar.
    """
    lam = 0.5 ** (1.0 / halflife)
    out, var, n = [], None, 0
    for r in rets:
        if r is None:
            out.append(None)
            continue
        if var is None:
            var = r * r
        else:
            var = lam * var + (1 - lam) * r * r
        n += 1
        out.append(math.sqrt(max(var, floor ** 2)) * math.sqrt(TRADING_DAYS) if n >= 20 else None)
    return out


def tsmom_signal(col, i, lookbacks=DEFAULT_LOOKBACKS, binary=True):
    """
    Mean of sign(past return) over each lookback, using closes through i.
    Returns None until the longest lookback has enough history.
    """
    vals = []
    for lb in lookbacks:
        j = i - lb
        if j < 0 or col[j] is None or col[i] is None or col[j] <= 0:
            return None
        m = col[i] / col[j] - 1
        vals.append((1.0 if m > 0 else -1.0) if binary else max(-1.0, min(1.0, m / 0.15)))
    return sum(vals) / len(vals)


# ---------------------------------------------------------------- backtester

def run(dates, by_sym, *, lookbacks=DEFAULT_LOOKBACKS, inst_vol_target=0.20,
        target_vol=0.10, rebal=21, long_only=False, max_inst_leverage=3.0,
        max_gross=None, cost_per_side=0.0005, vol_halflife=60,
        binary_signal=True, scale_halflife=60, rf=None, max_scalar=3.0,
        trade_syms=None):
    """
    Returns dict with the net daily return series and diagnostics.

    inst_vol_target : annualised vol each instrument's position is scaled to
    target_vol      : annualised vol the whole portfolio is scaled to
    rebal           : trading days between position updates (21 ~ monthly)
    long_only       : clamp negative signals to 0 (cash-account realistic)
    max_gross       : cap on summed |position| (set 1.0 for an unlevered
                      long-only ETF account; None = uncapped, futures-style)
    cost_per_side   : charged on |change in position| at each rebalance
    max_scalar      : cap on the portfolio vol scalar. 3.0 is futures-like;
                      set 1.0 to forbid leverage entirely (cash account)
    trade_syms      : which symbols the strategy may TRADE. Benchmark series
                      are carried in `by_sym` so they share the calendar, and
                      must be excluded here - otherwise the strategy trades
                      its own benchmark, which silently flatters the result.
    rf              : {date: daily risk-free}. Everything is computed in
                      EXCESS-of-cash space, which is the only way a levered,
                      vol-targeted book compares honestly to buy & hold:
                      exposure above 1.0 pays cash to finance, exposure below
                      1.0 earns it, and futures collateral earns it too.
    """
    panel = build_panel(dates, by_sym)
    syms = sorted(panel if trade_syms is None else [s for s in panel if s in set(trade_syms)])
    rets = {s: to_returns(panel[s]) for s in syms}
    vols = {s: ewma_vol(rets[s], vol_halflife) for s in syms}

    rf_d = [(rf.get(d, 0.0) if rf else 0.0) for d in dates]
    n = len(dates)
    pos = {s: 0.0 for s in syms}
    gross_raw, net_raw = [], []          # pre-portfolio-scaling EXCESS returns
    turnover_series, nactive, gross_series = [], [], []

    for i in range(n - 1):
        if i % rebal == 0:
            new = {}
            for s in syms:
                sig = tsmom_signal(panel[s], i, lookbacks, binary_signal)
                v = vols[s][i]
                if sig is None or v is None or v <= 0:
                    new[s] = 0.0
                    continue
                if long_only:
                    sig = max(0.0, sig)
                p = sig * (inst_vol_target / v)
                new[s] = max(-max_inst_leverage, min(max_inst_leverage, p))
            live = [s for s in syms if new[s] != 0.0 or panel[s][i] is not None]
            k = max(len([s for s in syms if panel[s][i] is not None]), 1)
            for s in syms:
                new[s] /= k                      # equal-weight across live markets
            if max_gross is not None:
                g = sum(abs(v) for v in new.values())
                if g > max_gross and g > 0:
                    for s in new:
                        new[s] *= max_gross / g
            turn = sum(abs(new[s] - pos[s]) for s in syms)
            pos = new
        else:
            turn = 0.0

        # excess-of-cash: each unit of exposure earns (asset return - cash)
        rfx = rf_d[i + 1]
        r = 0.0
        for s in syms:
            if pos[s] and rets[s][i + 1] is not None:
                r += pos[s] * (rets[s][i + 1] - rfx)
        gross_raw.append(r)
        net_raw.append(r - turn * cost_per_side)
        turnover_series.append(turn)
        gross_series.append(sum(abs(v) for v in pos.values()))
        nactive.append(sum(1 for s in syms if panel[s][i] is not None))

    # ---- portfolio vol scaling, using ONLY trailing information
    scaled, scalars = [], []
    lam = 0.5 ** (1.0 / scale_halflife)
    var = None
    for i, r in enumerate(net_raw):
        sc = 1.0
        if var is not None and var > 0:
            realised = math.sqrt(var) * math.sqrt(TRADING_DAYS)
            sc = min(max_scalar, target_vol / realised) if realised > 0 else 1.0
        scalars.append(sc)
        scaled.append(sc * r)
        var = r * r if var is None else lam * var + (1 - lam) * r * r

    warm = _first_live(scaled, 60)
    # total return = excess + cash earned on the whole capital base
    total = [scaled[i] + rf_d[i + 1] for i in range(len(scaled))]
    eff_gross = [gross_series[i] * scalars[i] for i in range(len(scaled))]
    return {
        "dates": dates[1:], "net": net_raw, "gross": gross_raw,
        "scaled": scaled, "total": total, "scalars": scalars,
        "turnover": turnover_series, "eff_gross": eff_gross,
        "nactive": nactive, "warm": warm, "syms": syms,
        "rf": [rf_d[i + 1] for i in range(len(scaled))],
        "ann_turnover": sum(turnover_series) / max(len(turnover_series), 1) * TRADING_DAYS,
    }


def _first_live(series, need):
    """Index of the first bar after `need` consecutive non-zero returns exist."""
    run_ = 0
    for i, v in enumerate(series):
        run_ = run_ + 1 if v != 0 else 0
        if run_ >= need:
            return i - need + 1
    return 0


def benchmark(dates, by_sym, sym, rf=None):
    """
    Buy-and-hold daily returns for one symbol on the shared calendar.
    With `rf`, returns EXCESS-of-cash returns so it is comparable to run().
    """
    panel = build_panel(dates, by_sym)
    if sym not in panel:
        return []
    r = [x if x is not None else 0.0 for x in to_returns(panel[sym])[1:]]
    if rf is None:
        return r
    rf_d = [rf.get(d, 0.0) for d in dates[1:]]
    return [r[i] - rf_d[i] for i in range(len(r))]


def blend(a, b, w):
    """w in a, (1-w) in b, rebalanced daily. Series must be same length."""
    n = min(len(a), len(b))
    return [w * a[-n:][i] + (1 - w) * b[-n:][i] for i in range(n)]
