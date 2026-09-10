"""
Backtest for newcoin_bot.py's breakout / pullback setups.

This is the honest test the strategy needs before any real money: replay the
*actual* entry logic (movement_study.classify_setup) and the two-stage exit
over real historical candles, with a realistic cost + latency model, and see
whether it has positive expectancy — split in-sample / out-of-sample so a
consistent sign across both halves separates signal from noise.

Data: GeckoTerminal's free OHLCV API (no key). For young Solana pools it
returns the pool's entire life at 5-minute granularity, which is exactly the
horizon these setups trade on.

    python newcoin_backtest.py --pools 60 --granularity 5

KNOWN LIMITS (read before trusting a positive result):
  * Survivorship bias — the basket is pools currently visible on GeckoTerminal's
    top/trending lists. Pools that already died are gone. This flatters results.
  * Shallow history — usually 1–4 days per pool, so a few dozen trades total.
    A small sample; treat a positive expectancy as "worth forward-testing in
    dry_run", not as proof.
  * No real order flow — the buy/sell-pressure gate is approximated from
    green-vs-red candle volume.
  * Minute OHLCV hides intra-candle wicks; stops are checked against the
    candle low (conservative) but fills are idealised.
"""

import argparse
import statistics
import time
from dataclasses import dataclass

import requests

from newcoin_config import NewCoinConfig
from movement_study import MovementSnapshot, classify_setup

GT = "https://api.geckoterminal.com/api/v2/networks/solana"
SOL = "So11111111111111111111111111111111111111112"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
_SLEEP = 2.3  # GeckoTerminal free tier ~30 req/min


def _get(session, url, params=None, tries=3):
    for a in range(1, tries + 1):
        try:
            r = session.get(url, params=params or {}, timeout=20)
            if r.status_code == 429:
                time.sleep(_SLEEP * 2 * a)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if a == tries:
                print(f"  ! {url.rsplit('/', 2)[-2:]} failed: {e}")
                return None
            time.sleep(_SLEEP)
    return None


def build_basket(session, want: int, min_liq: float, min_vol: float) -> list[dict]:
    """[{pool_id, symbol, mint}] from GeckoTerminal top + trending pools."""
    seen, out = set(), []
    sources = ([(f"{GT}/pools", {"page": p}) for p in range(1, 8)] +
               [(f"{GT}/trending_pools", {"page": p}) for p in range(1, 4)])
    for url, params in sources:
        if len(out) >= want:
            break
        data = _get(session, url, params)
        time.sleep(_SLEEP)
        for row in (data or {}).get("data", []):
            a = row.get("attributes", {})
            pid = row["id"].split("_", 1)[1]
            if pid in seen:
                continue
            liq = float(a.get("reserve_in_usd") or 0)
            vol = float((a.get("volume_usd") or {}).get("h24") or 0)
            if liq < min_liq or vol < min_vol:
                continue
            rel = (row.get("relationships") or {}).get("base_token", {}).get("data", {})
            mint = (rel.get("id") or "").replace("solana_", "")
            if mint in (SOL, USDC):
                rel = (row.get("relationships") or {}).get("quote_token", {}).get("data", {})
                mint = (rel.get("id") or "").replace("solana_", "")
            seen.add(pid)
            out.append({"pool_id": pid, "symbol": a.get("name", "?").split(" / ")[0], "mint": mint})
    return out[:want]


def fetch_candles(session, pool_id: str, granularity: int) -> list[tuple]:
    """Ascending [(ts, open, high, low, close, volume)]."""
    d = _get(session, f"{GT}/pools/{pool_id}/ohlcv/minute",
             {"aggregate": granularity, "limit": 1000})
    time.sleep(_SLEEP)
    rows = (((d or {}).get("data") or {}).get("attributes") or {}).get("ohlcv_list") or []
    return sorted(((int(r[0]), *(float(x) for x in r[1:6])) for r in rows), key=lambda x: x[0])


# --------------------------------------------------------------------------

@dataclass
class Trade:
    setup: str
    entry_i: int
    ret_pct: float          # net of round-trip cost
    bars_held: int
    half: str               # "in" | "out"


def _snapshot(win: list[tuple], gran_min: int) -> MovementSnapshot:
    closes = [c[4] for c in win]
    highs = [c[2] for c in win]
    lows = [c[3] for c in win]
    first, last = closes[0], closes[-1]
    hi, lo = max(highs), min(lows)
    n = len(closes)

    def slope_per_min(seq: list[float]) -> float:
        m = len(seq)
        if m < 2:
            return 0.0
        xs = list(range(m))
        mx, my = sum(xs) / m, sum(seq) / m
        den = sum((x - mx) ** 2 for x in xs)
        if den == 0 or my == 0:
            return 0.0
        b = sum((x - mx) * (y - my) for x, y in zip(xs, seq)) / den
        return b / my * 100 / gran_min

    rets = [(closes[i] / closes[i - 1] - 1) * 100 for i in range(1, n) if closes[i - 1] > 0]
    third = max(2, n // 3)
    return MovementSnapshot(
        mint="", symbol="", n_ticks=n, observed_seconds=n * gran_min * 60,
        return_since_first_pct=(last - first) / first * 100 if first else 0.0,
        drawdown_from_peak_pct=(last - hi) / hi * 100 if hi else 0.0,
        slope_pct_per_min=slope_per_min(closes),
        late_slope_pct_per_min=slope_per_min(closes[-third:]),
        volatility_pct=statistics.pstdev(rets) if len(rets) >= 2 else 0.0,
        pct_below_window_high=(last - hi) / hi * 100 if hi else 0.0,
        pct_above_window_low=(last - lo) / lo * 100 if lo else 0.0,
        holder_growth_per_min=None, liquidity_trend_pct=None,
    )


def _ctx(win: list[tuple], gran_min: int) -> dict:
    closes = [c[4] for c in win]
    vols = [c[5] for c in win]
    bars_1h = max(1, 60 // gran_min)
    green = sum(v for c, v in zip(win, vols) if c[4] >= c[1])
    red = sum(v for c, v in zip(win, vols) if c[4] < c[1]) or 1e-9
    look = win[-bars_1h:] if len(win) > bars_1h else win
    g2 = sum(v for c, v in zip(look, [x[5] for x in look]) if c[4] >= c[1])
    r2 = sum(v for c, v in zip(look, [x[5] for x in look]) if c[4] < c[1]) or 1e-9
    return {
        "chg5m_pct": (closes[-1] / closes[-2] - 1) * 100 if len(closes) > 1 and closes[-2] else 0.0,
        "chg1h_pct": (closes[-1] / closes[-1 - bars_1h] - 1) * 100
        if len(closes) > bars_1h and closes[-1 - bars_1h] else 0.0,
        "chg24h_pct": (closes[-1] / closes[0] - 1) * 100 if closes[0] else 0.0,
        # order-flow proxy: scale to counts classify_setup will divide
        "num_buys_5m": int(round(g2 / (g2 + r2) * 100)),
        "num_sells_5m": int(round(r2 / (g2 + r2) * 100)),
        "liq_change_1h_pct": 0.0,
    }


def simulate(candles: list[tuple], cfg: NewCoinConfig, gran_min: int) -> list[Trade]:
    W = max(cfg.min_observation_ticks, 18)
    bars_1h = max(1, 60 // gran_min)
    need = W + bars_1h + 1
    if len(candles) < need + 6:
        return []
    split = int(len(candles) * 0.6)
    cost_pct = cfg.round_trip_cost_pct() * 100 + (2 * cfg.platform_fee_flat_usd + 2 * cfg.network_fee_usd) \
        / max(cfg.max_position_usd, 1) * 100
    max_hold_bars = int(cfg.max_hold_hours * 60 / gran_min)
    cooldown_bars = int(cfg.reentry_cooldown_minutes / gran_min)

    trades: list[Trade] = []
    i = need
    while i < len(candles) - 2:
        win = candles[i - W:i]
        setup, _ = classify_setup(_snapshot(win, gran_min), _ctx(candles[i - W - bars_1h:i], gran_min), cfg)
        if not setup:
            i += 1
            continue

        entry = candles[i + 1][1] * (1 + cfg.est_slippage_pct)      # next-bar open + slippage
        stop = entry * (1 - cfg.hard_stop_loss_pct / 100)
        trail = cfg.tight_trail_pct
        tp1_done = False
        peak = entry
        exit_px = None
        j = i + 2
        while j < len(candles):
            o, h, l, c = candles[j][1:5]
            peak = max(peak, h)
            if l <= stop:                                            # stop first (conservative)
                exit_px = min(o, stop)
                break
            if not tp1_done and h >= entry * cfg.tp1_multiple:
                tp1_done = True
                stop = max(stop, entry * (1 + cfg.breakeven_buffer_pct / 100))
                trail = cfg.runner_trail_pct
            if l <= peak * (1 - trail / 100) and c > entry:
                exit_px = peak * (1 - trail / 100)
                break
            if h >= entry * cfg.final_tp_multiple:
                exit_px = entry * cfg.final_tp_multiple
                break
            if j - (i + 1) >= max_hold_bars:
                exit_px = c
                break
            j += 1
        if exit_px is None:
            exit_px = candles[-1][4]
            j = len(candles) - 1

        ret = (exit_px / entry - 1) * 100 - cost_pct
        trades.append(Trade(setup, i, ret, j - (i + 1),
                            "in" if i < split else "out"))
        i = j + cooldown_bars
    return trades


# --------------------------------------------------------------------------

def _stats(rets: list[float]) -> dict:
    if not rets:
        return {}
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    gp = sum(wins)
    gl = -sum(losses)
    eq, peak, mdd = 1.0, 1.0, 0.0
    for r in rets:
        eq *= (1 + r / 100 * 0.5)   # fixed 50%-of-book fractional sizing for the curve
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
    return {
        "n": len(rets),
        "win_rate": len(wins) / len(rets) * 100,
        "avg_win": statistics.mean(wins) if wins else 0.0,
        "avg_loss": statistics.mean(losses) if losses else 0.0,
        "expectancy": statistics.mean(rets),
        "profit_factor": (gp / gl) if gl else float("inf"),
        "total_eq_x": eq,
        "max_dd_pct": mdd * 100,
    }


def _print_block(title: str, rets: list[float]):
    s = _stats(rets)
    if not s:
        print(f"  {title:<22} no trades")
        return
    pf = "inf" if s["profit_factor"] == float("inf") else f"{s['profit_factor']:.2f}"
    print(f"  {title:<22} n={s['n']:<4} win={s['win_rate']:4.0f}%  "
          f"exp={s['expectancy']:+6.2f}%/trade  PF={pf:<5} "
          f"avgW={s['avg_win']:+.1f}% avgL={s['avg_loss']:+.1f}%  "
          f"eq={s['total_eq_x']:.2f}x  maxDD={s['max_dd_pct']:.0f}%")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--pools", type=int, default=50)
    ap.add_argument("--granularity", type=int, default=5, help="candle minutes (5/15)")
    ap.add_argument("--min-liq", type=float, default=15_000.0)
    ap.add_argument("--min-vol", type=float, default=40_000.0)
    args = ap.parse_args()

    cfg = NewCoinConfig()
    session = requests.Session()
    session.headers["accept"] = "application/json"

    print(f"building basket (target {args.pools} pools)…")
    basket = build_basket(session, args.pools, args.min_liq, args.min_vol)
    print(f"  {len(basket)} pools\n")

    all_trades: list[Trade] = []
    bh_rets: list[float] = []
    for k, tok in enumerate(basket, 1):
        candles = fetch_candles(session, tok["pool_id"], args.granularity)
        if len(candles) < 30:
            continue
        span_h = (candles[-1][0] - candles[0][0]) / 3600
        bh_rets.append((candles[-1][4] / candles[0][4] - 1) * 100)
        tr = simulate(candles, cfg, args.granularity)
        all_trades.extend(tr)
        print(f"  [{k:>2}/{len(basket)}] {tok['symbol'][:16]:<16} "
              f"{len(candles):>4} bars / {span_h:>4.0f}h  -> {len(tr)} trades")

    print("\n" + "=" * 78)
    print(f"RESULTS  ({len(all_trades)} trades across {len(bh_rets)} pools, "
          f"{args.granularity}m candles)")
    print("=" * 78)
    for setup in ("breakout", "pullback"):
        rs = [t.ret_pct for t in all_trades if t.setup == setup]
        print(f"\n{setup.upper()}")
        _print_block("all", rs)
        _print_block("in-sample (first 60%)", [t.ret_pct for t in all_trades
                                               if t.setup == setup and t.half == "in"])
        _print_block("out-sample (last 40%)", [t.ret_pct for t in all_trades
                                               if t.setup == setup and t.half == "out"])
    print("\nBOTH SETUPS")
    _print_block("all", [t.ret_pct for t in all_trades])

    if bh_rets:
        print(f"\nBUY & HOLD the basket over the same window: "
              f"mean {statistics.mean(bh_rets):+.1f}%  median {statistics.median(bh_rets):+.1f}%  "
              f"(n={len(bh_rets)})")

    print("\n" + "-" * 78)
    print("Read the KNOWN LIMITS block at the top of this file before acting on the above.")
    print("A positive out-of-sample expectancy here = run it in dry_run next, not go live.")


if __name__ == "__main__":
    main()
