"""
Test the classic, well-known retail strategies on real large-cap crypto
daily data (Coinbase). These are NOT strategies I searched for in the data —
they're the standard textbook ones, tested over full history, so this is a
fair out-of-sample-by-construction check.

    python classic_strats.py BTC-USD
    python classic_strats.py ETH-USD
    python classic_strats.py SOL-USD

Strategies:
  hold            buy day 1, never sell
  sma_50_200      hold when 50-day avg > 200-day avg ("golden cross"), else cash
  mom_20          hold when price > its level 20 days ago, else cash
  rsi_dip         buy after a 3-day drop, sell after a 3-day rise (mean reversion)
  dca_weekly      invest a fixed slice every 7 days
Fee: 0.30% per buy or sell (Coinbase-ish taker).
"""
import sys, datetime as dt, statistics
import requests

FEE = 0.003
SYM = sys.argv[1] if len(sys.argv) > 1 else "BTC-USD"
CB = f"https://api.exchange.coinbase.com/products/{SYM}/candles"


def closes():
    out = {}
    end = dt.datetime.now(dt.timezone.utc)
    while True:
        start = end - dt.timedelta(days=290)
        r = requests.get(CB, params={"granularity": 86400,
                         "start": start.isoformat(), "end": end.isoformat()},
                         headers={"User-Agent": "x"}, timeout=20)
        if r.status_code != 200 or not r.json():
            break
        rows = r.json()
        for t, lo, hi, op, cl, v in rows:
            out[dt.datetime.fromtimestamp(t, dt.timezone.utc).date()] = cl
        o = min(x[0] for x in rows)
        ne = dt.datetime.fromtimestamp(o, dt.timezone.utc)
        if ne >= end - dt.timedelta(days=1):
            break
        end = ne
    return [p for _, p in sorted(out.items())]


def dd(curve):
    peak = curve[0]; worst = 0
    for v in curve:
        peak = max(peak, v); worst = min(worst, v/peak - 1)
    return worst


def run(prices, signal):
    """signal(i) -> True means be in the asset on day i. Returns equity curve."""
    cash, units, invested = 1.0, 0.0, False
    eq = []
    for i in range(len(prices)):
        want = signal(i)
        if want and not invested:
            units = cash * (1 - FEE) / prices[i]; cash = 0; invested = True
        elif not want and invested:
            cash = units * prices[i] * (1 - FEE); units = 0; invested = False
        eq.append(cash + units * prices[i])
    return eq


def dca(prices, every=7):
    cash_in, units = 0.0, 0.0
    eq = []
    for i, p in enumerate(prices):
        if i % every == 0:
            units += (1 * (1 - FEE)) / p; cash_in += 1
        eq.append(units * p / max(cash_in, 1e-9))  # value per $1 invested
    return eq


def sma(prices, n, i):
    if i < n: return prices[i]
    return statistics.mean(prices[i-n:i])


P = closes()
if len(P) < 300:
    print(f"not enough data for {SYM} ({len(P)} days)"); sys.exit()
yrs = len(P) / 365.25
print(f"{SYM}: {len(P)} days ({yrs:.1f} yr), ${P[0]:,.0f} -> ${P[-1]:,.0f}\n")

strats = {
    "hold":       lambda i: True,
    "sma_50_200": lambda i: sma(P, 50, i) > sma(P, 200, i),
    "mom_20":     lambda i: i >= 20 and P[i] > P[i-20],
    "rsi_dip":    lambda i: i >= 3 and P[i-1] < P[i-2] < P[i-3],
}

print(f"{'strategy':<12} | {'total return':>13} | {'CAGR':>8} | {'max drawdown':>13} | {'trades':>7}")
print("-" * 66)
for name, sig in strats.items():
    eq = run(P, sig)
    tr = eq[-1] - 1
    cagr = eq[-1] ** (1/yrs) - 1
    # count switches
    sw = sum(1 for i in range(1, len(P)) if sig(i) != sig(i-1))
    print(f"{name:<12} | {tr*100:>+12.0f}% | {cagr*100:>+7.1f}% | {dd(eq)*100:>12.0f}% | {sw:>7}")

de = dca(P)
dr = de[-1] - 1
dcagr = de[-1] ** (1/yrs) - 1
print(f"{'dca_weekly':<12} | {dr*100:>+12.0f}% | {dcagr*100:>+7.1f}% | {dd(de)*100:>12.0f}% | {'~'+str(len(P)//7):>7}")
print("\n'hold' is the benchmark. A strategy only 'works' if it beats hold's")
print("return OR gets close to it with a much smaller drawdown. Watch for")
print("strategies that win on ONE coin and lose on the others = curve-fit.")
