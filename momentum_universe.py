"""
Which assets has the 20-day momentum rule actually worked on?
============================================================

For every symbol given (default: a basket of liquid Coinbase USD pairs with
multi-year history) this runs mom_20 — "hold when price > its level 20 days
ago, else cash" — over the FULL daily history and asks:

  1. Did mom_20 beat buy-and-hold on return?
  2. Did it cut the max drawdown?
  3. Did it do BOTH in the FIRST half AND the SECOND half of the history?
     (consistency — the single most important filter against curve-fit)

It then ranks by a "momentum fitness" score. This is descriptive of the
PAST. It is NOT a prediction and NOT a recommendation to buy anything.

    python momentum_universe.py
    python momentum_universe.py BTC-USD ETH-USD SOL-USD LINK-USD
"""
import sys, time, json, os, statistics
import datetime as dt
import requests

FEE = 0.003
LOOKBACK = 20
CB = "https://api.exchange.coinbase.com/products/{}/candles"

# liquid USD pairs that have several years of daily history on Coinbase
DEFAULT = ["BTC-USD", "ETH-USD", "SOL-USD", "LINK-USD", "LTC-USD", "BCH-USD",
           "ADA-USD", "XLM-USD", "ETC-USD", "AVAX-USD", "DOT-USD", "MATIC-USD",
           "ATOM-USD", "ALGO-USD", "XTZ-USD", "AAVE-USD", "MKR-USD", "UNI-USD",
           "DOGE-USD", "FIL-USD", "GRT-USD", "SNX-USD", "COMP-USD", "YFI-USD"]


def closes(sym):
    cache = f".mu_cache_{sym}.json"
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < 24 * 3600:
        try:
            return json.load(open(cache))
        except json.JSONDecodeError:
            pass
    out, end = {}, dt.datetime.now(dt.timezone.utc)
    while True:
        start = end - dt.timedelta(days=290)
        try:
            r = requests.get(CB.format(sym), params={"granularity": 86400,
                             "start": start.isoformat(), "end": end.isoformat()},
                             headers={"User-Agent": "mu"}, timeout=20)
        except requests.RequestException:
            break
        if r.status_code != 200 or not r.json():
            break
        rows = r.json()
        for t, lo, hi, op, cl, v in rows:
            out[dt.datetime.fromtimestamp(t, dt.timezone.utc).date().isoformat()] = cl
        o = min(x[0] for x in rows)
        ne = dt.datetime.fromtimestamp(o, dt.timezone.utc)
        if ne >= end - dt.timedelta(days=1):
            break
        end = ne
        time.sleep(0.15)
    series = [p for _, p in sorted(out.items())]
    if series:
        json.dump(series, open(cache, "w"))
    return series


def dd(curve):
    peak, worst = curve[0], 0.0
    for v in curve:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    return worst


def mom_curve(P, lo, hi):
    cash, units, inv = 1.0, 0.0, False
    eq = []
    for i in range(lo, hi):
        want = i >= LOOKBACK and P[i] > P[i - LOOKBACK]
        if want and not inv:
            units = cash * (1 - FEE) / P[i]; cash = 0.0; inv = True
        elif not want and inv:
            cash = units * P[i] * (1 - FEE); units = 0.0; inv = False
        eq.append(cash + units * P[i])
    return eq


def hold_curve(P, lo, hi):
    base = P[lo]
    return [P[i] / base for i in range(lo, hi)]


def cagr(curve, days):
    yrs = max(days / 365.25, 1e-9)
    return curve[-1] ** (1 / yrs) - 1 if curve[-1] > 0 else -1.0


def seg(P, lo, hi):
    """momentum vs hold over P[lo:hi] -> (mom_cagr, hold_cagr, mom_dd, hold_dd)"""
    m, h = mom_curve(P, lo, hi), hold_curve(P, lo, hi)
    n = hi - lo
    return cagr(m, n), cagr(h, n), dd(m), dd(h)


def main():
    syms = [s.upper() for s in sys.argv[1:] if not s.startswith("--")] or DEFAULT
    print(f"20-day momentum vs buy-and-hold, full daily history, fee {FEE*100:g}%/side")
    print("consistency = momentum beat hold on BOTH return-or-drawdown in EACH half\n")
    rows = []
    for s in syms:
        P = closes(s)
        if len(P) < 400:
            print(f"  {s:<10} skip ({len(P)} days)")
            continue
        n = len(P)
        mid = n // 2
        fm = seg(P, 0, n)                     # full
        h1 = seg(P, 0, mid + LOOKBACK)        # first half (+lookback warmup)
        h2 = seg(P, mid, n)                   # second half

        def better(x):
            mc, hc, md, hd = x
            return (mc >= hc) or (md > hd + 0.02)   # more return, or ≥2pt less drawdown
        consistent = better(h1) and better(h2)
        edge = fm[0] - fm[1]                  # momentum CAGR minus hold CAGR
        dd_gain = fm[3] - fm[2]               # how much shallower the drawdown (positive = better)
        score = (edge if consistent else edge - 1.0) + 0.5 * dd_gain
        rows.append((s, n / 365.25, fm, edge, dd_gain, consistent, score))

    rows.sort(key=lambda r: r[6], reverse=True)
    print(f"{'symbol':<10} {'yrs':>4} {'mom CAGR':>9} {'hold CAGR':>10} "
          f"{'mom maxDD':>10} {'hold maxDD':>11} {'consistent':>11}")
    print("-" * 72)
    for s, yrs, fm, edge, ddg, cons, sc in rows:
        print(f"{s:<10} {yrs:>4.1f} {fm[0]*100:>+8.1f}% {fm[1]*100:>+9.1f}% "
              f"{fm[2]*100:>+9.0f}% {fm[3]*100:>+10.0f}% {'YES' if cons else 'no':>11}")
    print("-" * 72)
    keep = [r for r in rows if r[5]]
    print(f"\n{len(keep)}/{len(rows)} assets: momentum was consistently at least as good "
          f"as holding, in both halves of history.")
    if keep:
        print("Best-fit (past only, NOT a prediction, NOT advice):")
        for s, yrs, fm, edge, ddg, cons, sc in keep[:5]:
            print(f"  {s:<10} momentum +{edge*100:.0f}pt/yr vs hold, "
                  f"drawdown {ddg*100:+.0f}pt {'shallower' if ddg>0 else 'deeper'}")
    print("\nPast behavior of a rule on an asset does not carry forward. New or "
          "'upcoming' coins have no history to test and are exactly where momentum "
          "rules fail most (no established trend, gappy liquidity).")


if __name__ == "__main__":
    main()
