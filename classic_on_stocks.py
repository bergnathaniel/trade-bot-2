"""
Do the classic strategies work on their actual home turf (US equities)?
=====================================================================

Connors RSI2, Turtle/Donchian, golden cross and 12-month absolute momentum
were all designed and documented on stock indices / ETFs / futures - not
crypto. They failed on the 23-coin basket. This checks whether that's
"crypto breaks them" or "they're folklore", by running the same honest
harness (next-open fills, 65/35 in/out split, realistic cost) on index
ETFs and a spread of large-cap stocks.

  connors_rsi2        close>SMA200 & RSI(2)<10 -> long; exit RSI(2)>70   [Connors & Alvarez]
  rsi2_no_trend       same but WITHOUT the SMA200 filter (isolates it)
  donchian_20_10      long > 20-day high, exit < 10-day low             [Turtle System 1]
  sma_50_200          hold while SMA50 > SMA200                          [golden cross]
  abs_momentum_252    hold while price > its level 252 trading days ago  [Antonacci]
  bollinger_reversion long < lower BB(20,2), exit > mid band            [Bollinger]

Data: Yahoo Finance daily (adjusted close via the chart API). Cost:
0.05%/side (liquid-ETF-realistic; commissions are ~0 now, spread isn't).

    python classic_on_stocks.py
    python classic_on_stocks.py SPY QQQ AAPL
"""

import argparse
import json
import os
import statistics
import time

import certifi
import requests

from more_strats_backtest import _sma, _ema, _wilder_rsi

SIDE = 0.0005
TICKERS = ["SPY", "QQQ", "DIA", "IWM", "EEM", "TLT",
           "AAPL", "MSFT", "JNJ", "KO", "XOM", "JPM"]
Y = "https://query1.finance.yahoo.com/v8/finance/chart/{}"


def fetch(sym):
    cache = f".stk_cache_{sym}.json"
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < 24 * 3600:
        try:
            return json.load(open(cache))
        except json.JSONDecodeError:
            pass
    try:
        r = requests.get(Y.format(sym), params={"range": "15y", "interval": "1d"},
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=20, verify=certifi.where())
        res = r.json()["chart"]["result"][0]
        ts = res["timestamp"]
        q = res["indicators"]["quote"][0]
        bars = []
        for i, t in enumerate(ts):
            o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
            if None in (o, h, l, c):
                continue
            bars.append([int(t), float(o), float(h), float(l), float(c)])
        if bars:
            json.dump(bars, open(cache, "w"))
        return bars
    except Exception as e:
        print(f"  {sym}: fetch failed ({e})")
        return []


def O(b): return b[1]
def H(b): return b[2]
def L(b): return b[3]
def C(b): return b[4]


def _roll_max(v, k):
    return [max(v[i - k:i]) if i >= k else None for i in range(len(v))]

def _roll_min(v, k):
    return [min(v[i - k:i]) if i >= k else None for i in range(len(v))]


def signals(bars):
    cl = [C(b) for b in bars]
    hi = [H(b) for b in bars]
    lo = [L(b) for b in bars]
    sd20 = [statistics.pstdev(cl[i - 19:i + 1]) if i >= 19 else None for i in range(len(cl))]
    s20 = _sma(cl, 20)
    return dict(
        cl=cl, sma200=_sma(cl, 200), sma50=_sma(cl, 50), sma20=s20,
        rsi2=_wilder_rsi(cl, 2),
        bb_dn=[(m - 2 * s) if (m is not None and s is not None) else None for m, s in zip(s20, sd20)],
        hh20=_roll_max(hi, 20), ll10=_roll_min(lo, 10),
    )


def _enter_exit(name):
    def trend(s, i):
        return s["sma200"][i] is not None and s["cl"][i] > s["sma200"][i]
    if name == "connors_rsi2":
        return (lambda s, i: trend(s, i) and s["rsi2"][i] is not None and s["rsi2"][i] < 10,
                lambda s, i: s["rsi2"][i] is not None and s["rsi2"][i] > 70)
    if name == "rsi2_no_trend":
        return (lambda s, i: s["rsi2"][i] is not None and s["rsi2"][i] < 10,
                lambda s, i: s["rsi2"][i] is not None and s["rsi2"][i] > 70)
    if name == "donchian_20_10":
        return (lambda s, i: s["hh20"][i] is not None and s["cl"][i] > s["hh20"][i],
                lambda s, i: s["ll10"][i] is not None and s["cl"][i] < s["ll10"][i])
    if name == "sma_50_200":
        return (lambda s, i: s["sma50"][i] is not None and s["sma200"][i] is not None and s["sma50"][i] > s["sma200"][i],
                lambda s, i: s["sma50"][i] is not None and s["sma200"][i] is not None and s["sma50"][i] < s["sma200"][i])
    if name == "abs_momentum_252":
        return (lambda s, i: i >= 252 and s["cl"][i] > s["cl"][i - 252],
                lambda s, i: i >= 252 and s["cl"][i] < s["cl"][i - 252])
    if name == "bollinger_reversion":
        return (lambda s, i: s["bb_dn"][i] is not None and s["cl"][i] < s["bb_dn"][i],
                lambda s, i: s["sma20"][i] is not None and s["cl"][i] > s["sma20"][i])
    raise KeyError(name)


STRATS = ["connors_rsi2", "rsi2_no_trend", "donchian_20_10",
          "sma_50_200", "abs_momentum_252", "bollinger_reversion"]
WARM = 260


def simulate(bars, name, split):
    s = signals(bars)
    en, ex = _enter_exit(name)
    n = len(bars)
    if n < WARM + 60:
        return None
    split_i = int(n * split)
    rt = 2 * SIDE
    rets = []      # (net_ret_frac, half, entry_i, exit_i)
    pos, entry, ei, in_mkt = False, 0.0, 0, 0
    for i in range(WARM, n - 1):
        if pos:
            in_mkt += 1
            if ex(s, i):
                px = O(bars[i + 1]) * (1 - SIDE)
                rets.append((px / entry - 1 - rt, "in" if ei < split_i else "out", ei, i))
                pos = False
        elif en(s, i):
            entry = O(bars[i + 1]) * (1 + SIDE)
            ei, pos = i + 1, True
    if pos:
        rets.append((C(bars[-1]) * (1 - SIDE) / entry - 1 - rt, "in" if ei < split_i else "out", ei, n - 1))
    return rets, in_mkt / (n - WARM) * 100, split_i


def compound(rs):
    eq = 1.0
    for r in rs:
        eq *= (1 + r)
    return eq


def dd(rs):
    eq = peak = 1.0
    w = 0.0
    for r in rs:
        eq *= (1 + r)
        peak = max(peak, eq)
        w = min(w, eq / peak - 1)
    return w


def bh_stats(bars, a, b):
    p0, p1 = C(bars[a]), C(bars[b - 1])
    yrs = (bars[b - 1][0] - bars[a][0]) / 86400 / 365.25
    cagr = (p1 / p0) ** (1 / max(yrs, 1e-9)) - 1
    peak, w = C(bars[a]), 0.0
    for k in range(a, b):
        peak = max(peak, C(bars[k]))
        w = min(w, C(bars[k]) / peak - 1)
    return cagr, w


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("tickers", nargs="*")
    ap.add_argument("--split", type=float, default=0.65)
    args = ap.parse_args()
    tks = [t.upper() for t in args.tickers] or TICKERS

    print(f"classic strategies on US equities | Yahoo daily | cost {SIDE*100:g}%/side | "
          f"in-sample first {args.split*100:.0f}%\n")

    agg = {k: {"in": [], "out": [], "tim": [], "beat_out": 0} for k in STRATS}
    n_ok = 0
    bh_out_cagrs = []
    for tk in tks:
        bars = fetch(tk)
        if len(bars) < WARM + 60:
            print(f"  {tk:<6} skip ({len(bars)} bars)")
            continue
        n_ok += 1
        r = simulate(bars, STRATS[0], args.split)
        split_i = r[2]
        _, bod = bh_stats(bars, split_i, len(bars))
        boc, _ = bh_stats(bars, split_i, len(bars))
        bh_out_cagrs.append(boc)
        for name in STRATS:
            rr, tim, si = simulate(bars, name, args.split)
            ins = [x[0] for x in rr if x[1] == "in"]
            outs = [x[0] for x in rr if x[1] == "out"]
            agg[name]["in"].extend(ins)
            agg[name]["out"].extend(outs)
            agg[name]["tim"].append(tim)
            oc = compound(outs) - 1
            if oc > boc:
                agg[name]["beat_out"] += 1
    print(f"  {n_ok} instruments | buy & hold out-of-sample CAGR "
          f"median {statistics.median(bh_out_cagrs)*100:+.0f}%\n")

    print(f"{'strategy':<20} {'%mkt':>5} {'IN comp':>8} {'IN PF':>6} {'OUT comp':>9} "
          f"{'OUT PF':>7} {'OUT win%':>8} {'beat B&H':>9}")
    print("-" * 82)
    for name in STRATS:
        a = agg[name]
        ci, co = compound(a["in"]), compound(a["out"])
        pfi = _pf(a["in"]); pfo = _pf(a["out"])
        wo = sum(1 for r in a["out"] if r > 0) / max(len(a["out"]), 1) * 100
        tim = statistics.mean(a["tim"]) if a["tim"] else 0
        print(f"{name:<20} {tim:>4.0f}% {ci:>7.2f}x {pfi:>6} {co:>8.2f}x {pfo:>7} "
              f"{wo:>7.0f}% {a['beat_out']:>4}/{n_ok}")
        vi = ci > 1 and _pfn(a["in"]) > 1.1
        vo = co > 1 and _pfn(a["out"]) > 1.1
        verdict = ("PASSES both halves" if vi and vo else
                   "in-sample only" if vi else "out-sample only" if vo else "no edge")
        print(f"{'':<20} n={len(a['in'])}/{len(a['out'])}  DD in {dd(a['in'])*100:+.0f}% "
              f"out {dd(a['out'])*100:+.0f}%   => {verdict}")

    print("\n" + "-" * 82)
    print("comp = compounded fully-invested equity (pooled across instruments, cost incl).")
    print("Descriptive of the past only. Not a prediction, not advice.")


def _pfn(rs):
    g = sum(r for r in rs if r > 0)
    l = -sum(r for r in rs if r <= 0)
    return (g / l) if l else 999.0

def _pf(rs):
    v = _pfn(rs)
    return "inf" if v >= 999 else f"{v:.2f}"


if __name__ == "__main__":
    main()
