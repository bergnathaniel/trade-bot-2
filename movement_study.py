"""
Movement study for the meme-coin momentum bot.

newcoin_bot.py registers a candidate, samples its price (plus holder count and
liquidity in real modes) for observation_seconds, then asks this module:
does the price action match one of our setups?

  * breakout  — the coin has coiled near the top of its observed range and
                buy-side flow is expanding. We want the push, not the chase.
  * pullback  — a coin in a strong 1h uptrend has made a shallow, orderly
                retrace and the last stretch is flattening / turning back up.

Rejected implicitly: parabolic (already ran), downtrend, chop. The maths is
plain arithmetic on the samples plus the Jupiter 5m/1h/24h stat aggregates
passed in as `ctx` — no ML here (that's newcoin_model.py's optional job).
"""

import statistics
import time
from dataclasses import dataclass
from typing import Optional

from newcoin_config import NewCoinConfig


@dataclass
class Sample:
    ts: float
    price: float
    holders: Optional[int] = None
    liquidity_usd: Optional[float] = None


class MovementTracker:
    def __init__(self, mint: str, symbol: str):
        self.mint = mint
        self.symbol = symbol
        self.samples: list[Sample] = []

    def add(self, price: float, holders: Optional[int] = None,
            liquidity_usd: Optional[float] = None) -> None:
        if price is None or price <= 0:
            return
        self.samples.append(Sample(time.time(), price, holders, liquidity_usd))

    @property
    def n(self) -> int:
        return len(self.samples)

    @property
    def last_price(self) -> Optional[float]:
        return self.samples[-1].price if self.samples else None

    @property
    def observed_seconds(self) -> float:
        return (self.samples[-1].ts - self.samples[0].ts) if self.n >= 2 else 0.0

    def last_liquidity(self) -> Optional[float]:
        for s in reversed(self.samples):
            if s.liquidity_usd is not None:
                return s.liquidity_usd
        return None


@dataclass
class MovementSnapshot:
    mint: str
    symbol: str
    n_ticks: int
    observed_seconds: float
    return_since_first_pct: float
    drawdown_from_peak_pct: float          # <= 0
    slope_pct_per_min: float
    late_slope_pct_per_min: float          # slope of the last third
    volatility_pct: float
    pct_below_window_high: float           # <= 0
    pct_above_window_low: float            # >= 0
    holder_growth_per_min: Optional[float]
    liquidity_trend_pct: Optional[float]

    def as_features(self) -> dict:
        return {
            "mv_return_pct": round(self.return_since_first_pct, 3),
            "mv_drawdown_pct": round(self.drawdown_from_peak_pct, 3),
            "mv_slope": round(self.slope_pct_per_min, 4),
            "mv_late_slope": round(self.late_slope_pct_per_min, 4),
            "mv_vol_pct": round(self.volatility_pct, 3),
            "mv_below_high_pct": round(self.pct_below_window_high, 3),
            "mv_above_low_pct": round(self.pct_above_window_low, 3),
            "mv_holder_growth": round(self.holder_growth_per_min, 3)
                if self.holder_growth_per_min is not None else 0.0,
            "mv_liq_trend_pct": round(self.liquidity_trend_pct, 3)
                if self.liquidity_trend_pct is not None else 0.0,
        }


def _slope_pct_per_min(pts: list[tuple[float, float]]) -> float:
    if len(pts) < 2:
        return 0.0
    t0 = pts[0][0]
    xs = [(t - t0) / 60.0 for t, _ in pts]
    ys = [p for _, p in pts]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0 or my == 0:
        return 0.0
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    return b / my * 100.0


def study(tr: MovementTracker) -> Optional[MovementSnapshot]:
    if tr.n < 2:
        return None
    s = tr.samples
    prices = [x.price for x in s]
    first, last = prices[0], prices[-1]
    hi, lo = max(prices), min(prices)

    pts = [(x.ts, x.price) for x in s]
    third = max(2, len(pts) // 3)

    rets = [(prices[i] / prices[i - 1] - 1.0) * 100.0
            for i in range(1, len(prices)) if prices[i - 1] > 0]

    hs = [(x.ts, x.holders) for x in s if x.holders is not None]
    hgrow = None
    if len(hs) >= 2 and hs[-1][0] > hs[0][0]:
        hgrow = (hs[-1][1] - hs[0][1]) / ((hs[-1][0] - hs[0][0]) / 60.0)

    ls = [x.liquidity_usd for x in s if x.liquidity_usd is not None]
    ltrend = ((ls[-1] - ls[0]) / ls[0] * 100.0) if len(ls) >= 2 and ls[0] > 0 else None

    return MovementSnapshot(
        mint=tr.mint, symbol=tr.symbol, n_ticks=tr.n,
        observed_seconds=tr.observed_seconds,
        return_since_first_pct=(last - first) / first * 100.0 if first else 0.0,
        drawdown_from_peak_pct=(last - hi) / hi * 100.0 if hi else 0.0,
        slope_pct_per_min=_slope_pct_per_min(pts),
        late_slope_pct_per_min=_slope_pct_per_min(pts[-third:]),
        volatility_pct=statistics.pstdev(rets) if len(rets) >= 2 else 0.0,
        pct_below_window_high=(last - hi) / hi * 100.0 if hi else 0.0,
        pct_above_window_low=(last - lo) / lo * 100.0 if lo else 0.0,
        holder_growth_per_min=hgrow, liquidity_trend_pct=ltrend,
    )


def classify_setup(snap: MovementSnapshot, ctx: dict, cfg: NewCoinConfig) -> tuple[Optional[str], str]:
    """Return (setup_name, reason). setup_name is None when nothing matched;
    reason then names the closest miss for the log."""
    if snap.n_ticks < cfg.min_observation_ticks:
        return None, f"too_few_ticks ({snap.n_ticks})"
    if snap.observed_seconds < cfg.observation_seconds * 0.6:
        return None, f"observed_too_short ({snap.observed_seconds:.0f}s)"
    if snap.volatility_pct > cfg.mv_max_volatility_pct:
        return None, f"too_chaotic (vol {snap.volatility_pct:.1f}%)"
    liq1h = ctx.get("liq_change_1h_pct", 0.0)
    if liq1h is not None and liq1h < cfg.mv_max_liq_drop_1h_pct:
        return None, f"liquidity_draining ({liq1h:.0f}%/1h)"

    chg5m = ctx.get("chg5m_pct", 0.0)
    chg1h = ctx.get("chg1h_pct", 0.0)
    nb, ns = ctx.get("num_buys_5m", 0), ctx.get("num_sells_5m", 0)
    misses: list[str] = []

    if "breakout" in cfg.entry_setups:
        ok = True
        if snap.pct_below_window_high < -cfg.bo_max_dist_from_high_pct:
            ok = False; misses.append(f"bo:not_near_high ({snap.pct_below_window_high:.1f}%)")
        if snap.return_since_first_pct < cfg.bo_min_window_return_pct:
            ok = False; misses.append(f"bo:window_flat ({snap.return_since_first_pct:.1f}%)")
        if not (cfg.bo_min_1h_pct <= chg1h <= cfg.bo_max_1h_pct):
            ok = False; misses.append(f"bo:1h_out_of_band ({chg1h:.0f}%)")
        if chg5m < cfg.bo_min_5m_pct:
            ok = False; misses.append(f"bo:5m_negative ({chg5m:.1f}%)")
        if ns > 0 and nb / max(ns, 1) < cfg.bo_min_buy_sell_ratio:
            ok = False; misses.append(f"bo:flow_weak ({nb}/{ns})")
        if snap.late_slope_pct_per_min < cfg.bo_min_late_slope_pct_per_min:
            ok = False; misses.append(f"bo:late_slope ({snap.late_slope_pct_per_min:.2f})")
        if ok:
            return "breakout", (f"breakout: {snap.pct_below_window_high:.1f}% off high, "
                                f"1h +{chg1h:.0f}%, flow {nb}/{ns}, late slope {snap.late_slope_pct_per_min:.2f}")

    if "pullback" in cfg.entry_setups:
        ok = True
        if not (cfg.pb_min_1h_pct <= chg1h <= cfg.pb_max_1h_pct):
            ok = False; misses.append(f"pb:1h_out_of_band ({chg1h:.0f}%)")
        dd = -snap.drawdown_from_peak_pct
        if not (cfg.pb_min_drawdown_pct <= dd <= cfg.pb_max_drawdown_pct):
            ok = False; misses.append(f"pb:dd_out_of_band ({dd:.1f}%)")
        if chg5m < cfg.pb_min_5m_pct:
            ok = False; misses.append(f"pb:still_dumping ({chg5m:.1f}%)")
        if snap.late_slope_pct_per_min < cfg.pb_min_late_slope_pct_per_min:
            ok = False; misses.append(f"pb:not_turning ({snap.late_slope_pct_per_min:.2f})")
        if snap.pct_above_window_low < cfg.pb_min_above_window_low_pct:
            ok = False; misses.append(f"pb:at_new_low ({snap.pct_above_window_low:.1f}%)")
        if ok:
            return "pullback", (f"pullback: 1h +{chg1h:.0f}%, retrace {dd:.1f}% off peak, "
                                f"5m {chg5m:.1f}%, late slope {snap.late_slope_pct_per_min:.2f}")

    return None, "; ".join(misses[:4]) or "no_setup"
