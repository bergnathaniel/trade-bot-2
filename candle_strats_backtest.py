"""
Test other people's candlestick / price-action strategies, candle by candle.
=========================================================================

These are NOT strategies fitted to this data. They are the standard,
publicly documented retail setups, tested over full daily OHLC history on a
basket of liquid Coinbase USD pairs, split in-sample / out-of-sample so a
consistent sign across both halves separates edge from curve-fit.

    python candle_strats_backtest.py                  # full basket
    python candle_strats_backtest.py BTC-USD ETH-USD  # named pairs
    python candle_strats_backtest.py --split 0.7 --max-bars 15

STRATEGIES  (source in brackets)
  bullish_engulfing     green body engulfs prior red body, in a downtrend      [Bulkowski / Investopedia]
  hammer                long lower wick after a decline                        [Bulkowski / Investopedia]
  piercing_line         gap down then close back above prior midpoint         [Nison, Japanese Candlestick Charting]
  morning_star          big red, small indecision bar, big green recovery     [Nison / Bulkowski, ~70% in his tests]
  bullish_harami        small green body contained inside prior big red       [Bulkowski, ~54%]
  three_white_soldiers  three strong greens, each opening inside prior body   [Nison]
  tweezer_bottom        two equal lows, red then green, in a downtrend        [Bulkowski]
  inside_bar_breakout   mother bar's high broken after an inside bar          [Nial Fuller price-action]
  pin_bar               long-tailed rejection candle at a fresh swing low     [Nial Fuller price-action]
  rsi2_connors          price > SMA200, RSI(2) < 10; exit RSI(2) > 70         [Connors & Alvarez, "Short Term Trading Strategies That Work"]

EXIT MODEL
  Every pattern strategy uses the same generic exit so they compare fairly:
  enter at the NEXT bar's open (+slippage), hard stop 1.0*ATR(14) below entry,
  target 2.0*ATR(14) above, time stop after --max-bars bars. Intrabar the stop
  is checked before the target (conservative). rsi2_connors uses its own
  rule-based exit (RSI(2) > 70 or the time stop), no price stop, as published.

KNOWN LIMITS  (read before trusting any positive line)
  * Long-only, one position per symbol at a time, spot, no shorting.
  * Daily bars hide the intrabar path: a bar that touches both stop and target
    is scored as a stop. Fills are otherwise idealised at the level.
  * Survivorship: the basket is pairs Coinbase lists today.
  * Cost model: 0.30%/side taker + 0.05%/side slippage. Real slippage on the
    thinner alts is worse.
  * ~24 symbols x a few years of daily bars => rare patterns (morning star,
    three white soldiers) may have too few trades to mean anything. Watch n.
"""

import argparse
import datetime as dt
import json
import os
import statistics
import time

import requests

FEE = 0.003        # taker per side
SLIP = 0.0005      # slippage per side
CB = "https://api.exchange.coinbase.com/products/{}/candles"

DEFAULT = ["BTC-USD", "ETH-USD", "SOL-USD", "LINK-USD", "LTC-USD", "BCH-USD",
           "ADA-USD", "XLM-USD", "ETC-USD", "AVAX-USD", "DOT-USD", "ATOM-USD",
           "ALGO-USD", "XTZ-USD", "AAVE-USD", "MKR-USD", "UNI-USD", "DOGE-USD",
           "FIL-USD", "GRT-USD", "SNX-USD", "COMP-USD", "YFI-USD"]


# --------------------------------------------------------------------------
# data: ascending [ts, open, high, low, close, volume]

def fetch_ohlc(sym: str, gran: int = 86400, years: float = 0.0) -> list[list[float]]:
    """Ascending [ts, o, h, l, c, v] at `gran` seconds/bar. years>0 caps history."""
    cache = f".candle_cache_{sym}.json" if gran == 86400 else f".candle_cache_{sym}_{gran}.json"
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < 24 * 3600:
        try:
            return json.load(open(cache))
        except json.JSONDecodeError:
            pass
    span = dt.timedelta(seconds=gran * 300)      # Coinbase caps at 300 bars/request
    floor = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=365.25 * years)) if years else None
    out, end = {}, dt.datetime.now(dt.timezone.utc)
    while True:
        start = end - span
        rows = None
        for attempt in range(4):
            try:
                r = requests.get(CB.format(sym), params={"granularity": gran,
                                 "start": start.isoformat(), "end": end.isoformat()},
                                 headers={"User-Agent": "cs"}, timeout=20)
            except requests.RequestException:
                rows = []
                break
            if r.status_code == 429:
                time.sleep(1.0 + attempt)
                continue
            rows = r.json() if r.status_code == 200 else []   # [time,low,high,open,close,vol]
            break
        if not rows:
            break
        for t, lo, hi, op, cl, v in rows:
            out[int(t)] = [int(t), float(op), float(hi), float(lo), float(cl), float(v)]
        ne = dt.datetime.fromtimestamp(min(x[0] for x in rows), dt.timezone.utc)
        if (floor and ne <= floor) or ne >= end - dt.timedelta(seconds=gran):
            break
        end = ne
        time.sleep(0.2 if gran >= 86400 else 0.25)
    series = [out[k] for k in sorted(out)]
    if floor:
        cut = floor.timestamp()
        series = [b for b in series if b[0] >= cut]
    if series:
        json.dump(series, open(cache, "w"))
    return series


# --------------------------------------------------------------------------
# bar accessors + indicators   (b = [ts, o, h, l, c, v])

def O(b): return b[1]
def H(b): return b[2]
def L(b): return b[3]
def C(b): return b[4]
def body(b): return abs(b[4] - b[1])
def rng(b): return b[2] - b[3]
def upper_wick(b): return b[2] - max(b[1], b[4])
def lower_wick(b): return min(b[1], b[4]) - b[3]
def green(b): return b[4] > b[1]
def red(b): return b[4] < b[1]


def sma(closes: list[float], n: int, i: int) -> float:
    if i + 1 < n:
        return statistics.mean(closes[:i + 1])
    return statistics.mean(closes[i - n + 1:i + 1])


def rsi(closes: list[float], n: int, i: int) -> float:
    """Cutler's (simple-average) RSI at index i. For n=2 this tracks Wilder
    closely enough for the Connors setup and is fully deterministic."""
    if i < n:
        return 50.0
    gain = loss = 0.0
    for k in range(i - n + 1, i + 1):
        ch = closes[k] - closes[k - 1]
        if ch >= 0:
            gain += ch
        else:
            loss -= ch
    if loss == 0:
        return 100.0
    rs = (gain / n) / (loss / n)
    return 100.0 - 100.0 / (1.0 + rs)


def atr(bars: list[list[float]], n: int, i: int) -> float:
    if i < 1:
        return rng(bars[i])
    lo = max(1, i - n + 1)
    trs = []
    for k in range(lo, i + 1):
        pc = C(bars[k - 1])
        trs.append(max(H(bars[k]) - L(bars[k]), abs(H(bars[k]) - pc), abs(L(bars[k]) - pc)))
    return statistics.mean(trs) if trs else rng(bars[i])


def avg_body(bars: list[list[float]], i: int, n: int = 20) -> float:
    lo = max(0, i - n + 1)
    return statistics.mean([body(b) for b in bars[lo:i + 1]]) or 1e-9


# --------------------------------------------------------------------------
# strategies: fn(bars, closes, i) -> bool   (signal fires on the CLOSE of bar i)
# long-only. entry is handled generically at bar i+1's open.

def _downtrend(closes, i):
    return C_at(closes, i) < sma(closes, 20, i)

def C_at(closes, i):
    return closes[i]


def bullish_engulfing(b, cl, i):
    if i < 21:
        return False
    p, c = b[i - 1], b[i]
    return (red(p) and green(c) and C(c) >= O(p) and O(c) <= C(p)
            and body(c) > body(p) and cl[i] < sma(cl, 20, i))


def hammer(b, cl, i):
    if i < 21:
        return False
    c = b[i]
    if body(c) <= 0:
        return False
    return (lower_wick(c) >= 2 * body(c) and upper_wick(c) <= 0.4 * body(c)
            and cl[i - 3] > cl[i] and cl[i] < sma(cl, 20, i))


def piercing_line(b, cl, i):
    if i < 21:
        return False
    p, c = b[i - 1], b[i]
    mid = (O(p) + C(p)) / 2
    return (red(p) and green(c) and body(p) > avg_body(b, i - 1)
            and O(c) < C(p) and mid < C(c) < O(p)          # gap-down open, close back into upper half
            and cl[i] < sma(cl, 20, i))


def morning_star(b, cl, i):
    if i < 21:
        return False
    a, m, c = b[i - 2], b[i - 1], b[i]
    ab = avg_body(b, i - 3)
    return (red(a) and body(a) > 1.2 * ab
            and max(O(m), C(m)) < C(a) and body(m) < 0.5 * body(a)
            and green(c) and C(c) > (O(a) + C(a)) / 2
            and cl[i] < sma(cl, 20, i))


def bullish_harami(b, cl, i):
    if i < 21:
        return False
    p, c = b[i - 1], b[i]
    return (red(p) and body(p) > 1.3 * avg_body(b, i - 1)
            and O(c) > C(p) and C(c) < O(p) and body(c) < 0.6 * body(p)
            and cl[i - 1] < sma(cl, 20, i - 1))


def three_white_soldiers(b, cl, i):
    if i < 21:
        return False
    x, y, z = b[i - 2], b[i - 1], b[i]
    if not (green(x) and green(y) and green(z)):
        return False
    if not (C(x) < C(y) < C(z)):
        return False
    step = (C(x) < O(y) < C(x) + body(x) + 1e-9) and (C(y) < O(z) < C(y) + body(y) + 1e-9)
    small_wick = upper_wick(y) <= 0.3 * body(y) and upper_wick(z) <= 0.3 * body(z)
    return step and small_wick and cl[i - 2] < sma(cl, 50, i - 2)


def tweezer_bottom(b, cl, i):
    if i < 21:
        return False
    p, c = b[i - 1], b[i]
    same_low = abs(L(p) - L(c)) / max(L(c), 1e-9) < 0.0015
    return same_low and red(p) and green(c) and cl[i] < sma(cl, 20, i)


def inside_bar_breakout(b, cl, i):
    if i < 21:
        return False
    mother, inside, cur = b[i - 2], b[i - 1], b[i]
    is_inside = H(inside) < H(mother) and L(inside) > L(mother)
    return is_inside and H(cur) > H(mother) and green(cur)


def pin_bar(b, cl, i):
    if i < 21:
        return False
    c = b[i]
    r = rng(c)
    if r <= 0:
        return False
    return (lower_wick(c) >= 0.66 * r and body(c) <= 0.25 * r
            and upper_wick(c) <= 0.15 * r
            and L(c) < min(L(b[i - 1]), L(b[i - 2]), L(b[i - 3])))


def rsi2_connors(b, cl, i):
    if i < 201:
        return False
    return cl[i] > sma(cl, 200, i) and rsi(cl, 2, i) < 10.0


STRATS = {
    "bullish_engulfing": bullish_engulfing,
    "hammer": hammer,
    "piercing_line": piercing_line,
    "morning_star": morning_star,
    "bullish_harami": bullish_harami,
    "three_white_soldiers": three_white_soldiers,
    "tweezer_bottom": tweezer_bottom,
    "inside_bar_breakout": inside_bar_breakout,
    "pin_bar": pin_bar,
    "rsi2_connors": rsi2_connors,
}
RSI2_EXIT = {"rsi2_connors"}


# --------------------------------------------------------------------------
# candle-by-candle simulation

def simulate(bars: list[list[float]], name: str, fn, split: float, max_bars: int):
    """Returns [(ret_pct_net, half)]  half in {'in','out'}."""
    cl = [C(x) for x in bars]
    n = len(bars)
    if n < 260:
        return []
    split_i = int(n * split)
    rt_cost = 2 * (FEE + SLIP) * 100
    out = []
    i = 210
    while i < n - 2:
        if not fn(bars, cl, i):
            i += 1
            continue
        entry = O(bars[i + 1]) * (1 + SLIP)
        a = atr(bars, 14, i)
        if a <= 0:
            i += 1
            continue
        stop = entry - 1.0 * a
        target = entry + 2.0 * a
        exit_px = None
        j = i + 1
        while j < n:
            bj = bars[j]
            if name in RSI2_EXIT:
                if j > i + 1 and rsi(cl, 2, j) > 70:
                    exit_px = C(bj)
                    break
                if j - (i + 1) >= max_bars:
                    exit_px = C(bj)
                    break
            else:
                if L(bj) <= stop:                       # stop checked first
                    exit_px = min(O(bj), stop)
                    break
                if H(bj) >= target:
                    exit_px = target
                    break
                if j - (i + 1) >= max_bars:
                    exit_px = C(bj)
                    break
            j += 1
        if exit_px is None:
            exit_px = C(bars[-1])
            j = n - 1
        ret = (exit_px * (1 - SLIP) / entry - 1) * 100 - rt_cost
        out.append((ret, "in" if i < split_i else "out"))
        i = j + 1                                        # flat until this trade closes
    return out


# --------------------------------------------------------------------------
# stats + reporting

def stats(rets: list[float]) -> dict:
    if not rets:
        return {}
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    gp, gl = sum(wins), -sum(losses)
    eq = peak = 1.0
    mdd = 0.0
    for r in rets:
        eq *= (1 + r / 100 * 0.5)          # fixed half-book fractional sizing
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
    return {
        "n": len(rets),
        "win": len(wins) / len(rets) * 100,
        "avg_w": statistics.mean(wins) if wins else 0.0,
        "avg_l": statistics.mean(losses) if losses else 0.0,
        "exp": statistics.mean(rets),
        "pf": (gp / gl) if gl else float("inf"),
        "eq": eq,
        "mdd": mdd * 100,
    }


def line(tag: str, rets: list[float]) -> str:
    s = stats(rets)
    if not s:
        return f"    {tag:<10} no trades"
    pf = "inf" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    return (f"    {tag:<10} n={s['n']:<4} win={s['win']:4.0f}%  "
            f"exp={s['exp']:+6.2f}%/trade  PF={pf:<5} "
            f"avgW={s['avg_w']:+.1f}% avgL={s['avg_l']:+.1f}%  "
            f"eq={s['eq']:.2f}x  maxDD={s['mdd']:.0f}%")


def verdict(ins: list[float], outs: list[float]) -> str:
    si, so = stats(ins), stats(outs)
    if not si or not so:
        return "INSUFFICIENT DATA"
    pos_in = si["exp"] > 0 and si["pf"] > 1.1
    pos_out = so["exp"] > 0 and so["pf"] > 1.1
    thin = si["n"] < 30 or so["n"] < 30
    if pos_in and pos_out and not thin:
        return "PASSES both halves -> forward-test in paper next, do NOT go live"
    if pos_in and pos_out and thin:
        return "positive both halves BUT n<30 in a half -> too few trades to trust"
    if pos_out and not pos_in:
        return "out-of-sample only (in-sample weak) -> likely noise"
    if pos_in and not pos_out:
        return "in-sample only -> curve-fit, no out-of-sample edge"
    return "no edge in either half"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("symbols", nargs="*", help="Coinbase pairs (default: full basket)")
    ap.add_argument("--split", type=float, default=0.65, help="in-sample fraction")
    ap.add_argument("--granularity", type=int, default=86400, choices=[3600, 86400],
                    help="seconds per candle: 3600 hourly, 86400 daily")
    ap.add_argument("--years", type=float, default=0.0,
                    help="cap history to N years (0 = all; auto 2.0 for hourly)")
    ap.add_argument("--max-bars", type=int, default=0,
                    help="time stop in bars (0 = auto: 12 daily / 36 hourly)")
    args = ap.parse_args()

    gran = args.granularity
    years = args.years or (0.0 if gran == 86400 else 2.0)
    max_bars = args.max_bars or (12 if gran == 86400 else 36)
    tf = "daily" if gran == 86400 else "hourly"
    syms = [s.upper() for s in args.symbols] or DEFAULT
    print(f"candle-by-candle test of {len(STRATS)} published strategies | {tf} candles"
          f"{f' / last {years:g}yr' if years else ''} | fee {FEE*100:g}%/side + slip "
          f"{SLIP*100:g}%/side | in-sample first {args.split*100:.0f}%\n")

    agg: dict[str, list[tuple]] = {k: [] for k in STRATS}
    bh_in, bh_out = [], []
    for k, sym in enumerate(syms, 1):
        bars = fetch_ohlc(sym, gran, years)
        if len(bars) < 260:
            print(f"  [{k:>2}/{len(syms)}] {sym:<10} skip ({len(bars)} bars)")
            continue
        split_i = int(len(bars) * args.split)
        bh_in.append((C(bars[split_i - 1]) / C(bars[210]) - 1) * 100)
        bh_out.append((C(bars[-1]) / C(bars[split_i]) - 1) * 100)
        cnt = 0
        for name, fn in STRATS.items():
            tr = simulate(bars, name, fn, args.split, max_bars)
            agg[name].extend(tr)
            cnt += len(tr)
        yrs = len(bars) * gran / 86400 / 365.25
        print(f"  [{k:>2}/{len(syms)}] {sym:<10} {len(bars):>6} bars / {yrs:>4.1f}yr  -> {cnt} trades")

    print("\n" + "=" * 82)
    print("RESULTS  (trades pooled across the whole basket)")
    print("=" * 82)
    ranked = sorted(STRATS, key=lambda nm: stats([r for r, h in agg[nm] if h == "out"]).get("exp", -99),
                    reverse=True)
    for name in ranked:
        allr = [r for r, _ in agg[name]]
        ins = [r for r, h in agg[name] if h == "in"]
        outs = [r for r, h in agg[name] if h == "out"]
        print(f"\n{name}")
        print(line("all", allr))
        print(line("in-samp", ins))
        print(line("out-samp", outs))
        print(f"    => {verdict(ins, outs)}")

    print("\n" + "-" * 82)
    if bh_in:
        print(f"BUY & HOLD basket   in-sample mean {statistics.mean(bh_in):+.0f}%   "
              f"out-of-sample mean {statistics.mean(bh_out):+.0f}%   (n={len(bh_in)} pairs)")
    print("Descriptive of the past only. Not a prediction, not advice. A 'PASSES' line "
          "means run it in paper mode next — never straight to real money.")


if __name__ == "__main__":
    main()
