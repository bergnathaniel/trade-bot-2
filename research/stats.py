"""
Performance statistics, including the ones that price in how hard we looked.
===========================================================================

The failure mode this whole project keeps hitting is picking the best of N
backtests and reading its Sharpe as if it were the only one we ran. The
Deflated Sharpe Ratio (Bailey & Lopez de Prado 2014) is the correction: it
asks whether the WINNER of N trials is better than what N skill-less trials
would have thrown up by luck alone.

Pure stdlib - math.erf gives us the normal CDF, which is all we need.
"""

import math

TRADING_DAYS = 252


# ------------------------------------------------------------------ moments

def mean(x):
    return sum(x) / len(x) if x else 0.0


def stdev(x, ddof=1):
    n = len(x)
    if n <= ddof:
        return 0.0
    m = mean(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (n - ddof))


def skewness(x):
    n, s = len(x), stdev(x, ddof=0)
    if n < 3 or s == 0:
        return 0.0
    m = mean(x)
    return sum((v - m) ** 3 for v in x) / (n * s ** 3)


def kurtosis(x):
    """Non-excess (normal == 3.0), which is what the DSR formula wants."""
    n, s = len(x), stdev(x, ddof=0)
    if n < 4 or s == 0:
        return 3.0
    m = mean(x)
    return sum((v - m) ** 4 for v in x) / (n * s ** 4)


def norm_cdf(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def norm_ppf(p):
    """Inverse normal CDF (Acklam's rational approximation, ~1e-9 accurate)."""
    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    pl, ph = 0.02425, 1 - 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > ph:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q, r = p - 0.5, (p - 0.5) ** 2
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


# ------------------------------------------------------- headline statistics

def sharpe(rets, rf_daily=0.0, periods=TRADING_DAYS):
    """Annualised Sharpe from a daily return series."""
    ex = [r - rf_daily for r in rets]
    s = stdev(ex)
    if s == 0:
        return 0.0
    return mean(ex) / s * math.sqrt(periods)


def ann_return(rets, periods=TRADING_DAYS):
    """Geometric annualised return."""
    if not rets:
        return 0.0
    eq = 1.0
    for r in rets:
        eq *= (1 + r)
        if eq <= 0:                       # wiped out
            return -1.0
    return eq ** (periods / len(rets)) - 1


def ann_vol(rets, periods=TRADING_DAYS):
    return stdev(rets) * math.sqrt(periods)


def max_drawdown(rets):
    """Worst peak-to-trough on the compounded curve. Negative fraction."""
    eq = peak = 1.0
    worst = 0.0
    for r in rets:
        eq *= (1 + r)
        peak = max(peak, eq)
        worst = min(worst, eq / peak - 1)
    return worst


def calmar(rets, periods=TRADING_DAYS):
    dd = max_drawdown(rets)
    return ann_return(rets, periods) / abs(dd) if dd else 0.0


def correlation(a, b):
    n = min(len(a), len(b))
    if n < 3:
        return 0.0
    a, b = a[-n:], b[-n:]
    ma, mb = mean(a), mean(b)
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    da = math.sqrt(sum((v - ma) ** 2 for v in a))
    db = math.sqrt(sum((v - mb) ** 2 for v in b))
    return num / (da * db) if da and db else 0.0


# --------------------------------------------- multiple-testing corrections

def psr(rets, benchmark_sr=0.0, periods=TRADING_DAYS):
    """
    Probabilistic Sharpe Ratio: P(true SR > benchmark_sr), given the observed
    SR, sample length, skew and kurtosis. Non-normal returns (fat tails,
    negative skew) widen the error bars and push this down.
    """
    n = len(rets)
    if n < 30:
        return 0.0
    sr_d = sharpe(rets, periods=1)                     # per-period SR
    bench_d = benchmark_sr / math.sqrt(periods)
    g, k = skewness(rets), kurtosis(rets)
    denom = 1 - g * sr_d + (k - 1) / 4.0 * sr_d ** 2
    if denom <= 0:
        return 0.0
    return norm_cdf((sr_d - bench_d) * math.sqrt(n - 1) / math.sqrt(denom))


def expected_max_sr(n_trials, trial_sr_stdev, periods=TRADING_DAYS):
    """
    E[max SR] across `n_trials` skill-less strategies whose SRs vary with
    `trial_sr_stdev`. This is the bar the winner must clear. Annualised.
    """
    if n_trials < 2 or trial_sr_stdev <= 0:
        return 0.0
    e = 0.5772156649015329                                   # Euler-Mascheroni
    z = ((1 - e) * norm_ppf(1 - 1.0 / n_trials)
         + e * norm_ppf(1 - 1.0 / (n_trials * math.e)))
    return trial_sr_stdev * z


def deflated_sharpe(rets, n_trials, trial_sr_stdev, periods=TRADING_DAYS):
    """
    P(true SR > 0) for the BEST of n_trials, after subtracting the Sharpe a
    skill-less search of that size would be expected to produce.

    < 0.95 means: we cannot reject "this is the luckiest of our N guesses".
    """
    bench = expected_max_sr(n_trials, trial_sr_stdev, periods)
    return psr(rets, benchmark_sr=bench, periods=periods), bench


def min_track_record_length(rets, benchmark_sr=0.0, conf=0.95, periods=TRADING_DAYS):
    """Days of track record needed for the observed SR to clear benchmark_sr."""
    sr_d = sharpe(rets, periods=1)
    bench_d = benchmark_sr / math.sqrt(periods)
    if sr_d <= bench_d:
        return math.inf
    g, k = skewness(rets), kurtosis(rets)
    denom = 1 - g * sr_d + (k - 1) / 4.0 * sr_d ** 2
    if denom <= 0:
        return math.inf
    return 1 + denom * (norm_ppf(conf) / (sr_d - bench_d)) ** 2


def summary(rets, label="", periods=TRADING_DAYS):
    return {
        "label": label, "n": len(rets),
        "cagr": ann_return(rets, periods), "vol": ann_vol(rets, periods),
        "sharpe": sharpe(rets, periods=periods), "maxdd": max_drawdown(rets),
        "calmar": calmar(rets, periods), "skew": skewness(rets),
        "kurt": kurtosis(rets),
    }


HEADER = (f"{'strategy':<30} {'CAGR':>7} {'vol':>6} {'Sharpe':>7} "
          f"{'maxDD':>7} {'Calmar':>7} {'skew':>6}")


def row(s):
    return (f"{s['label']:<30} {s['cagr']*100:>+6.1f}% {s['vol']*100:>5.1f}% "
            f"{s['sharpe']:>7.2f} {s['maxdd']*100:>+6.0f}% {s['calmar']:>7.2f} "
            f"{s['skew']:>+6.2f}")
