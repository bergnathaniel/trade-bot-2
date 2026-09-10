"""
More of other people's strategies, tested candle by candle.
==========================================================

Companion to candle_strats_backtest.py. That file did discrete
candlestick patterns; this one does the well-known *systematic* rule sets
- trend-following breakouts and mean-reversion systems that each have a
published track record. Same honest harness: signal on a closed bar, fill
at the NEXT bar's open (+/- slippage), one long position at a time, daily
Coinbase OHLC, 65/35 in-sample / out-of-sample split, 0.30%/side + 0.05%
slippage. Reuses the data layer + stats from the companion file.

    python more_strats_backtest.py                 # full basket
    python more_strats_backtest.py BTC-USD ETH-USD
    python more_strats_backtest.py --split 0.7

STRATEGIES  (source in brackets)
  donchian_20_10       long > 20-bar high, exit < 10-bar low            [Turtle System 1, Dennis/Eckhardt]
  donchian_55_20       long > 55-bar high, exit < 20-bar low            [Turtle System 2]
  sma_50_200           hold while SMA50 > SMA200 ("golden cross")       [classic]
  ema_10_20            hold while EMA10 > EMA20                          [classic fast MA cross]
  macd_cross           hold while MACD(12,26) > signal(9)               [Appel]
  supertrend_10_3      hold while close > SuperTrend(ATR10, x3)         [Olivier Seban]
  bollinger_breakout   long > upper BB(20,2), exit < mid band          [Bollinger, breakout form]
  abs_momentum_252     hold while price > its level 252 bars ago        [Antonacci, absolute momentum]
  bollinger_reversion  long < lower BB(20,2), exit > mid band          [Bollinger, mean-reversion form]
  connors_double7      px>SMA200; buy at a 7-day low, sell at 7-day high [Connors & Alvarez, "Double Seven"]
  connors_3day_hl      px>SMA200 & <SMA5 & 3 lower lows; exit > prior high [Connors, "3-Day High/Low"]
  rsi14_x30_70         buy on RSI(14) crossing up 30, sell crossing dn 70 [Wilder, classic RSI]
  rsi14_dip_uptrend    px>SMA200 & RSI(14)<30; exit RSI(14)>50          [common "buy the dip in an uptrend"]
  ichimoku_cloud       long above the cloud w/ tenkan>kijun, exit < kijun [Hosoda, Ichimoku Kinko Hyo]
  keltner_breakout     long > upper Keltner (EMA20 + 2xATR10), exit < EMA20 [Keltner / Linda Raschke]
  keltner_reversion    long < lower Keltner, exit > EMA20                [Keltner, mean-reversion form]
  stoch_14_3           %K crosses %D under 25, exit cross over 75        [Lane, stochastic oscillator]
  williams_r           buy crossing up -80, sell crossing down -20      [Larry Williams %R]
  adx_trend            long when ADX>25 & +DI>-DI, exit +DI<-DI         [Wilder, ADX/DMI]
  nr7_breakout         narrowest range in 7 bars, buy break of its high [Toby Crabel, NR7]
  mom_10w              hold while price > its level 70 bars (~10wk) ago  [longer-horizon momentum]
  crsi2_connors        px>SMA200; 2-bar sum of RSI(3) < 35 in, > 130 out [Connors, cumulative RSI]
  rsi4_25_55           px>SMA200; RSI(4) < 25 in, > 55 out              [Connors, RSI-4 pullback]

KNOWN LIMITS  (same as the companion file)
  * Long-only, one position, spot, no shorting, no leverage, no pyramiding.
  * Turtle "skip entry if the last signal won" filter is NOT applied (simplified).
  * Daily bars; fills idealised at the next open. Costs are optimistic on thin alts.
  * Survivorship: basket = pairs Coinbase lists today.
  * A rule that hugs buy-and-hold (e.g. abs_momentum in a bull run) is not an
    "edge" - check the beat-B&H-per-symbol line and both halves.
"""

import argparse
import statistics
from types import SimpleNamespace

from candle_strats_backtest import (
    DEFAULT, FEE, SLIP, fetch_ohlc, O, H, L, C, line, stats,
)


# --------------------------------------------------------------------------
# indicator series  (index-aligned to bars; None where undefined)

def _sma(vals, n):
    out, s = [None] * len(vals), 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        out[i] = s / n if i >= n - 1 else None
    return out


def _ema(vals, n):
    out = [None] * len(vals)
    k = 2 / (n + 1)
    e = None
    for i, v in enumerate(vals):
        e = v if e is None else v * k + e * (1 - k)
        out[i] = e if i >= n - 1 else None
    return out


def _wilder_rsi(closes, n=14):
    out = [None] * len(closes)
    if len(closes) <= n:
        return out
    gains = losses = 0.0
    for i in range(1, n + 1):
        ch = closes[i] - closes[i - 1]
        gains += max(ch, 0.0)
        losses += max(-ch, 0.0)
    ag, al = gains / n, losses / n
    out[n] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(closes)):
        ch = closes[i] - closes[i - 1]
        ag = (ag * (n - 1) + max(ch, 0.0)) / n
        al = (al * (n - 1) + max(-ch, 0.0)) / n
        out[i] = 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def _wilder_atr(bars, n=10):
    out = [None] * len(bars)
    if len(bars) <= n:
        return out
    trs = []
    for i in range(1, len(bars)):
        pc = C(bars[i - 1])
        trs.append(max(H(bars[i]) - L(bars[i]), abs(H(bars[i]) - pc), abs(L(bars[i]) - pc)))
    a = statistics.mean(trs[:n])
    out[n] = a
    for i in range(n + 1, len(bars)):
        a = (a * (n - 1) + trs[i - 1]) / n
        out[i] = a
    return out


def _supertrend(bars, atr, mult=3.0):
    n = len(bars)
    st = [None] * n
    dir_ = [None] * n
    fu = fl = None
    for i in range(n):
        if atr[i] is None:
            continue
        hl2 = (H(bars[i]) + L(bars[i])) / 2
        bu, bl = hl2 + mult * atr[i], hl2 - mult * atr[i]
        pfu = fu if fu is not None else bu
        pfl = fl if fl is not None else bl
        fu = bu if (bu < pfu or C(bars[i - 1]) > pfu) else pfu
        fl = bl if (bl > pfl or C(bars[i - 1]) < pfl) else pfl
        prev = st[i - 1]
        if prev is None or prev == pfu:
            st[i] = fl if C(bars[i]) > fu else fu
        else:
            st[i] = fu if C(bars[i]) < fl else fl
        dir_[i] = 1 if C(bars[i]) >= st[i] else -1
    return st, dir_


def _roll_max(vals, k):
    return [max(vals[i - k:i]) if i >= k else None for i in range(len(vals))]


def _roll_min(vals, k):
    return [min(vals[i - k:i]) if i >= k else None for i in range(len(vals))]


def _stoch(bars, k=14, d=3):
    hi, lo, cl = [H(b) for b in bars], [L(b) for b in bars], [C(b) for b in bars]
    kk = [None] * len(bars)
    for i in range(len(bars)):
        if i < k:
            continue
        hh, ll = max(hi[i - k + 1:i + 1]), min(lo[i - k + 1:i + 1])
        kk[i] = 50.0 if hh == ll else (cl[i] - ll) / (hh - ll) * 100
    dd = [None] * len(bars)
    for i in range(len(bars)):
        w = [x for x in kk[max(0, i - d + 1):i + 1] if x is not None]
        dd[i] = statistics.mean(w) if len(w) == d else None
    return kk, dd


def _williams_r(bars, n=14):
    hi, lo, cl = [H(b) for b in bars], [L(b) for b in bars], [C(b) for b in bars]
    out = [None] * len(bars)
    for i in range(n, len(bars)):
        hh, ll = max(hi[i - n + 1:i + 1]), min(lo[i - n + 1:i + 1])
        out[i] = -50.0 if hh == ll else (hh - cl[i]) / (hh - ll) * -100
    return out


def _adx(bars, n=14):
    m = len(bars)
    adx, pdi, mdi = [None] * m, [None] * m, [None] * m
    if m <= 2 * n:
        return adx, pdi, mdi
    trs, pdm, ndm = [], [], []
    for i in range(1, m):
        up, dn = H(bars[i]) - H(bars[i - 1]), L(bars[i - 1]) - L(bars[i])
        pdm.append(up if (up > dn and up > 0) else 0.0)
        ndm.append(dn if (dn > up and dn > 0) else 0.0)
        pc = C(bars[i - 1])
        trs.append(max(H(bars[i]) - L(bars[i]), abs(H(bars[i]) - pc), abs(L(bars[i]) - pc)))
    atr = sum(trs[:n]); sp = sum(pdm[:n]); sn = sum(ndm[:n])
    dxs = []
    for i in range(n, len(trs)):
        atr = atr - atr / n + trs[i]
        sp = sp - sp / n + pdm[i]
        sn = sn - sn / n + ndm[i]
        p = 100 * sp / atr if atr else 0.0
        q = 100 * sn / atr if atr else 0.0
        pdi[i + 1], mdi[i + 1] = p, q
        dxs.append(100 * abs(p - q) / (p + q) if (p + q) else 0.0)
        if len(dxs) == n:
            a = statistics.mean(dxs)
            adx[i + 1] = a
        elif len(dxs) > n:
            a = (adx[i] * (n - 1) + dxs[-1]) / n
            adx[i + 1] = a
    return adx, pdi, mdi


def _shift(vals, k):
    """value plotted at bar i is the raw value from bar i-k (Ichimoku cloud projection)."""
    return [vals[i - k] if i >= k and vals[i - k] is not None else None for i in range(len(vals))]


def make_ctx(bars):
    close = [C(b) for b in bars]
    high = [H(b) for b in bars]
    low = [L(b) for b in bars]
    ema12, ema26 = _ema(close, 12), _ema(close, 26)
    macd = [ (a - b) if (a is not None and b is not None) else None
             for a, b in zip(ema12, ema26) ]
    macd_seed = [m for m in macd if m is not None]
    macd_sig_vals = _ema(macd_seed, 9) if macd_seed else []
    macd_sig = [None] * len(bars)
    j = 0
    for i, m in enumerate(macd):
        if m is not None:
            macd_sig[i] = macd_sig_vals[j]
            j += 1
    sma20 = _sma(close, 20)
    sd20 = [ statistics.pstdev(close[i - 19:i + 1]) if i >= 19 else None
             for i in range(len(close)) ]
    atr10 = _wilder_atr(bars, 10)
    st, st_dir = _supertrend(bars, atr10, 3.0)
    ema20 = _ema(close, 20)
    stoch_k, stoch_d = _stoch(bars, 14, 3)
    adx, pdi, mdi = _adx(bars, 14)
    tenkan = [ (a + b) / 2 if (a is not None and b is not None) else None
               for a, b in zip(_roll_max(high, 9), _roll_min(low, 9)) ]
    kijun = [ (a + b) / 2 if (a is not None and b is not None) else None
              for a, b in zip(_roll_max(high, 26), _roll_min(low, 26)) ]
    senkou_a_raw = [ (a + b) / 2 if (a is not None and b is not None) else None
                     for a, b in zip(tenkan, kijun) ]
    senkou_b_raw = [ (a + b) / 2 if (a is not None and b is not None) else None
                     for a, b in zip(_roll_max(high, 52), _roll_min(low, 52)) ]
    rng = [h - l for h, l in zip(high, low)]
    return SimpleNamespace(
        close=close, high=high, low=low, rng=rng,
        sma5=_sma(close, 5), sma50=_sma(close, 50), sma200=_sma(close, 200),
        sma20=sma20,
        bb_up=[ (m + 2 * s) if (m is not None and s is not None) else None
                for m, s in zip(sma20, sd20) ],
        bb_dn=[ (m - 2 * s) if (m is not None and s is not None) else None
                for m, s in zip(sma20, sd20) ],
        ema10=_ema(close, 10), ema20=ema20,
        macd=macd, macd_sig=macd_sig,
        rsi14=_wilder_rsi(close, 14), rsi4=_wilder_rsi(close, 4), rsi3=_wilder_rsi(close, 3),
        st=st, st_dir=st_dir,
        hh20=_roll_max(high, 20), ll10=_roll_min(low, 10),
        hh55=_roll_max(high, 55), ll20=_roll_min(low, 20), ll5=_roll_min(low, 5),
        atr10=atr10,
        kc_up=[ (e + 2 * a) if (e is not None and a is not None) else None
                for e, a in zip(ema20, atr10) ],
        kc_dn=[ (e - 2 * a) if (e is not None and a is not None) else None
                for e, a in zip(ema20, atr10) ],
        stoch_k=stoch_k, stoch_d=stoch_d,
        wr=_williams_r(bars, 14),
        adx=adx, pdi=pdi, mdi=mdi,
        tenkan=tenkan, kijun=kijun,
        senkou_a=_shift(senkou_a_raw, 26), senkou_b=_shift(senkou_b_raw, 26),
        nr7=[ i >= 6 and rng[i] == min(rng[i - 6:i + 1]) for i in range(len(bars)) ],
    )


# --------------------------------------------------------------------------
# strategies:  (enter(ctx,i)->bool, exit(ctx,i)->bool),  data through bar i only

def _cross_up(a, b, i):
    return (None not in (a[i - 1], b[i - 1], a[i], b[i])
            and a[i - 1] <= b[i - 1] and a[i] > b[i])

def _cross_dn(a, b, i):
    return (None not in (a[i - 1], b[i - 1], a[i], b[i])
            and a[i - 1] >= b[i - 1] and a[i] < b[i])

def _xu_level(v, lvl, i):
    return v[i - 1] is not None and v[i] is not None and v[i - 1] <= lvl < v[i]

def _xd_level(v, lvl, i):
    return v[i - 1] is not None and v[i] is not None and v[i - 1] >= lvl > v[i]


STRATS = {
    "donchian_20_10": (
        lambda c, i: c.hh20[i] is not None and c.close[i] > c.hh20[i],
        lambda c, i: c.ll10[i] is not None and c.close[i] < c.ll10[i]),
    "donchian_55_20": (
        lambda c, i: c.hh55[i] is not None and c.close[i] > c.hh55[i],
        lambda c, i: c.ll20[i] is not None and c.close[i] < c.ll20[i]),
    "sma_50_200": (
        lambda c, i: c.sma50[i] is not None and c.sma200[i] is not None and c.sma50[i] > c.sma200[i],
        lambda c, i: c.sma50[i] is not None and c.sma200[i] is not None and c.sma50[i] < c.sma200[i]),
    "ema_10_20": (
        lambda c, i: c.ema10[i] > c.ema20[i],
        lambda c, i: c.ema10[i] < c.ema20[i]),
    "macd_cross": (
        lambda c, i: c.macd[i] is not None and c.macd_sig[i] is not None and c.macd[i] > c.macd_sig[i],
        lambda c, i: c.macd[i] is not None and c.macd_sig[i] is not None and c.macd[i] < c.macd_sig[i]),
    "supertrend_10_3": (
        lambda c, i: c.st[i] is not None and c.close[i] > c.st[i],
        lambda c, i: c.st[i] is not None and c.close[i] < c.st[i]),
    "bollinger_breakout": (
        lambda c, i: c.bb_up[i] is not None and c.close[i] > c.bb_up[i],
        lambda c, i: c.sma20[i] is not None and c.close[i] < c.sma20[i]),
    "abs_momentum_252": (
        lambda c, i: i >= 252 and c.close[i] > c.close[i - 252],
        lambda c, i: i >= 252 and c.close[i] < c.close[i - 252]),
    "bollinger_reversion": (
        lambda c, i: c.bb_dn[i] is not None and c.close[i] < c.bb_dn[i],
        lambda c, i: c.sma20[i] is not None and c.close[i] > c.sma20[i]),
    "connors_double7": (
        lambda c, i: (c.sma200[i] is not None and c.close[i] > c.sma200[i]
                      and c.close[i] <= min(c.close[i - 6:i + 1])),
        lambda c, i: c.close[i] >= max(c.close[i - 6:i + 1])),
    "connors_3day_hl": (
        lambda c, i: (c.sma200[i] is not None and c.close[i] > c.sma200[i]
                      and c.sma5[i] is not None and c.close[i] < c.sma5[i]
                      and c.low[i] < c.low[i - 1] < c.low[i - 2] < c.low[i - 3]),
        lambda c, i: c.close[i] > c.high[i - 1]),
    "rsi14_x30_70": (
        lambda c, i: c.rsi14[i] is not None and c.rsi14[i - 1] is not None
                     and c.rsi14[i - 1] <= 30 < c.rsi14[i],
        lambda c, i: c.rsi14[i] is not None and c.rsi14[i - 1] is not None
                     and c.rsi14[i - 1] >= 70 > c.rsi14[i]),
    "rsi14_dip_uptrend": (
        lambda c, i: (c.sma200[i] is not None and c.close[i] > c.sma200[i]
                      and c.rsi14[i] is not None and c.rsi14[i] < 30),
        lambda c, i: c.rsi14[i] is not None and c.rsi14[i] > 50),
    "ichimoku_cloud": (
        lambda c, i: (None not in (c.senkou_a[i], c.senkou_b[i], c.tenkan[i], c.kijun[i])
                      and c.close[i] > max(c.senkou_a[i], c.senkou_b[i]) and c.tenkan[i] > c.kijun[i]),
        lambda c, i: c.kijun[i] is not None and c.close[i] < c.kijun[i]),
    "keltner_breakout": (
        lambda c, i: c.kc_up[i] is not None and c.close[i] > c.kc_up[i],
        lambda c, i: c.ema20[i] is not None and c.close[i] < c.ema20[i]),
    "keltner_reversion": (
        lambda c, i: c.kc_dn[i] is not None and c.close[i] < c.kc_dn[i],
        lambda c, i: c.ema20[i] is not None and c.close[i] > c.ema20[i]),
    "stoch_14_3": (
        lambda c, i: (c.stoch_k[i] is not None and c.stoch_k[i] < 25 and _cross_up(c.stoch_k, c.stoch_d, i)),
        lambda c, i: (c.stoch_k[i] is not None and c.stoch_k[i] > 75 and _cross_dn(c.stoch_k, c.stoch_d, i))),
    "williams_r": (
        lambda c, i: _xu_level(c.wr, -80, i),
        lambda c, i: _xd_level(c.wr, -20, i)),
    "adx_trend": (
        lambda c, i: (None not in (c.adx[i], c.pdi[i], c.mdi[i])
                      and c.adx[i] > 25 and c.pdi[i] > c.mdi[i]),
        lambda c, i: (None not in (c.pdi[i], c.mdi[i]) and c.pdi[i] < c.mdi[i])),
    "nr7_breakout": (
        lambda c, i: c.nr7[i - 1] and c.close[i] > c.high[i - 1],
        lambda c, i: c.ll5[i] is not None and c.close[i] < c.ll5[i]),
    "mom_10w": (
        lambda c, i: i >= 70 and c.close[i] > c.close[i - 70],
        lambda c, i: i >= 70 and c.close[i] < c.close[i - 70]),
    "crsi2_connors": (
        lambda c, i: (c.sma200[i] is not None and c.close[i] > c.sma200[i]
                      and None not in (c.rsi3[i], c.rsi3[i - 1]) and c.rsi3[i] + c.rsi3[i - 1] < 35),
        lambda c, i: (None not in (c.rsi3[i], c.rsi3[i - 1]) and c.rsi3[i] + c.rsi3[i - 1] > 130)),
    "rsi4_25_55": (
        lambda c, i: (c.sma200[i] is not None and c.close[i] > c.sma200[i]
                      and c.rsi4[i] is not None and c.rsi4[i] < 25),
        lambda c, i: c.rsi4[i] is not None and c.rsi4[i] > 55),
}

WARM = 260


# --------------------------------------------------------------------------

def simulate(bars, enter, exit_, split):
    """[(ret_pct_net, half)] + time-in-market %. One long position, next-open fills."""
    n = len(bars)
    if n < WARM + 40:
        return [], 0.0
    ctx = make_ctx(bars)
    split_i = int(n * split)
    rt = 2 * (FEE + SLIP) * 100
    trades, in_mkt = [], 0
    pos, entry, entry_i = False, 0.0, 0
    for i in range(WARM, n - 1):
        if pos:
            in_mkt += 1
            try:
                done = exit_(ctx, i)
            except TypeError:
                done = False
            if done:
                px = O(bars[i + 1]) * (1 - SLIP)
                trades.append((( px / entry - 1) * 100 - rt,
                               "in" if entry_i < split_i else "out"))
                pos = False
        else:
            try:
                go = enter(ctx, i)
            except TypeError:
                go = False
            if go:
                entry = O(bars[i + 1]) * (1 + SLIP)
                entry_i, pos = i + 1, True
    if pos:
        px = C(bars[-1]) * (1 - SLIP)
        trades.append(((px / entry - 1) * 100 - rt, "in" if entry_i < split_i else "out"))
    return trades, in_mkt / max(n - WARM, 1) * 100


def compound(rets):
    eq = 1.0
    for r in rets:
        eq *= (1 + r / 100)      # fully invested, one position, fees already in r
    return eq


def verdict(ins, outs):
    """Honest gate: the strategy must actually COMPOUND positive in both halves
    (pooled, fully invested), with PF>1.1 and a positive median trade so that a
    handful of fat-tail winners can't carry a losing distribution. Beating a
    buy & hold that was itself down is not a bar worth passing."""
    si, so = stats(ins), stats(outs)
    if not si or not so or si["n"] < 30 or so["n"] < 30:
        return "INSUFFICIENT DATA (need >=30 trades per half)"
    ci, co = compound(ins), compound(outs)
    mi, mo = statistics.median(ins), statistics.median(outs)
    ok_in = ci > 1.0 and si["pf"] > 1.1 and mi > 0
    ok_out = co > 1.0 and so["pf"] > 1.1 and mo > 0
    if ok_in and ok_out:
        return f"PASSES both halves (pooled {ci:.2f}x / {co:.2f}x) -> paper-test, NOT live"
    if ok_out and not ok_in:
        return f"out-of-sample only ({co:.2f}x) -> likely noise"
    if ok_in and not ok_out:
        return f"in-sample only (out {co:.2f}x) -> curve-fit / fat-tail luck"
    return f"no edge (compounds {ci:.2f}x in / {co:.2f}x out)"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("symbols", nargs="*")
    ap.add_argument("--split", type=float, default=0.65)
    args = ap.parse_args()
    syms = [s.upper() for s in args.symbols] or DEFAULT

    print(f"candle-by-candle test of {len(STRATS)} systematic strategies | daily candles | "
          f"fee {FEE*100:g}%/side + slip {SLIP*100:g}%/side | in-sample first {args.split*100:.0f}%\n")

    agg = {k: {"in": [], "out": [], "beat_in": 0, "beat_out": 0,
               "pos_in": 0, "pos_out": 0, "tim": []} for k in STRATS}
    n_sym = 0
    bh_in_all, bh_out_all = [], []
    for k, sym in enumerate(syms, 1):
        bars = fetch_ohlc(sym)
        if len(bars) < WARM + 60:
            print(f"  [{k:>2}/{len(syms)}] {sym:<10} skip ({len(bars)} bars)")
            continue
        n_sym += 1
        n = len(bars)
        split_i = int(n * args.split)
        bh_in = C(bars[split_i - 1]) / C(bars[WARM]) - 1
        bh_out = C(bars[-1]) / C(bars[split_i]) - 1
        bh_in_all.append(bh_in * 100)
        bh_out_all.append(bh_out * 100)
        tot = 0
        for name, (en, ex) in STRATS.items():
            tr, tim = simulate(bars, en, ex, args.split)
            ins = [r for r, h in tr if h == "in"]
            outs = [r for r, h in tr if h == "out"]
            agg[name]["in"].extend(ins)
            agg[name]["out"].extend(outs)
            agg[name]["tim"].append(tim)
            if compound(ins) - 1 > bh_in:
                agg[name]["beat_in"] += 1
            if compound(outs) - 1 > bh_out:
                agg[name]["beat_out"] += 1
            if len(ins) >= 3 and compound(ins) > 1.0:
                agg[name]["pos_in"] += 1
            if len(outs) >= 3 and compound(outs) > 1.0:
                agg[name]["pos_out"] += 1
            tot += len(tr)
        print(f"  [{k:>2}/{len(syms)}] {sym:<10} {n:>5} bars  -> {tot} trades")

    print("\n" + "=" * 88)
    print(f"RESULTS  (trades pooled across {n_sym} symbols)")
    print("=" * 88)
    ranked = sorted(STRATS, key=lambda nm: stats(agg[nm]["out"]).get("exp", -99), reverse=True)
    for name in ranked:
        a = agg[name]
        tim = statistics.mean(a["tim"]) if a["tim"] else 0.0
        med_in = statistics.median(a["in"]) if a["in"] else 0.0
        med_out = statistics.median(a["out"]) if a["out"] else 0.0
        print(f"\n{name}   (avg {tim:.0f}% time in market)")
        print(line("in-samp", a["in"]))
        print(line("out-samp", a["out"]))
        print(f"    pooled fully-invested equity:  in {compound(a['in']):.2f}x   "
              f"out {compound(a['out']):.2f}x   |  median trade  in {med_in:+.1f}%  out {med_out:+.1f}%")
        print(f"    made money per-symbol:  in-sample {a['pos_in']}/{n_sym}   "
              f"out-of-sample {a['pos_out']}/{n_sym}   "
              f"(beats B&H out: {a['beat_out']}/{n_sym})")
        print(f"    => {verdict(a['in'], a['out'])}")

    print("\n" + "-" * 88)
    if bh_in_all:
        print(f"BUY & HOLD per symbol   in-sample mean {statistics.mean(bh_in_all):+.0f}%   "
              f"out-of-sample mean {statistics.mean(bh_out_all):+.0f}%   (n={n_sym})")
    print("Descriptive of the past only. Not a prediction, not advice. 'PASSES' = paper-test, never straight to live.")


if __name__ == "__main__":
    main()
