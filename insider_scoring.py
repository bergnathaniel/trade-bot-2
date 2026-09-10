"""
Turn raw WalletStats into a keep/drop decision + a score for ranking.

The score is deliberately simple and legible — no ML, no magic. It rewards
wallets that (a) repeatedly get into big winners, (b) do it early, and
(c) hit often relative to how much they trade. Every rejection is returned
with a reason so `insider_bot.py discover` can print why a wallet didn't
make the cut.
"""

import math
import time
from typing import Optional

from insider_config import InsiderConfig
from insider_sources import WalletStats


def _days_since(ts: float) -> float:
    return (time.time() - ts) / 86400 if ts > 0 else 1e9


def reject_reason(s: WalletStats, cfg: InsiderConfig) -> Optional[str]:
    if s.tokens_tracked < cfg.min_wallet_tokens_tracked:
        return f"too_few_tokens ({s.tokens_tracked} < {cfg.min_wallet_tokens_tracked})"
    if s.tokens_tracked > cfg.max_wallet_tokens_tracked:
        return f"looks_like_a_farm_bot ({s.tokens_tracked} > {cfg.max_wallet_tokens_tracked})"
    if s.early_wins < cfg.min_wallet_early_wins:
        return f"not_enough_early_wins ({s.early_wins} < {cfg.min_wallet_early_wins})"
    if s.hit_rate < cfg.min_wallet_hit_rate:
        return f"hit_rate_too_low ({s.hit_rate:.2f} < {cfg.min_wallet_hit_rate:.2f})"
    if s.median_multiple < cfg.min_wallet_median_multiple:
        return f"median_multiple_too_low ({s.median_multiple:.2f} < {cfg.min_wallet_median_multiple:.2f})"
    if _days_since(s.first_seen_ts) > cfg.max_wallet_age_days:
        return f"wallet_too_old_dormant ({_days_since(s.first_seen_ts):.0f}d > {cfg.max_wallet_age_days:.0f}d)"
    if s.last_trade_ts > 0 and _days_since(s.last_trade_ts) > cfg.max_wallet_days_since_last_trade:
        return f"gone_quiet ({_days_since(s.last_trade_ts):.0f}d since last trade > {cfg.max_wallet_days_since_last_trade:.0f}d)"
    return None


def recency_factor(s: WalletStats) -> float:
    """1.0 for a wallet trading now, decaying toward ~0.4 as its last trade
    ages out to the 21-day cutoff. Keeps a once-hot-now-cold wallet from
    outranking someone hitting today."""
    d = _days_since(s.last_trade_ts)
    return round(max(0.4, math.exp(-d / 14.0)), 3)


def score(s: WalletStats) -> float:
    """Higher is better. Roughly: early-win volume x consistency x edge size,
    time-decayed by how recently the wallet was active, with diminishing
    returns so one lucky 100x doesn't dominate."""
    early = math.log1p(s.early_wins) * 2.0
    consistency = s.hit_rate  # 0..1
    edge = math.log1p(max(0.0, s.median_multiple - 1.0))
    ceiling = math.log1p(max(0.0, s.best_multiple - 1.0)) * 0.25
    # a wallet that trades thousands of tokens and still only hits 35% is noisier
    noise_penalty = math.log1p(max(0, s.tokens_tracked - 150)) * 0.15
    raw = early * (0.5 + consistency) + edge + ceiling - noise_penalty
    return round(raw * recency_factor(s), 4)


def evaluate(stats_list: list[WalletStats], cfg: InsiderConfig):
    """Returns (kept, rejected) where kept is sorted best-first and capped at
    cfg.max_watched_wallets. Mutates .score / .note on the WalletStats."""
    kept, rejected = [], []
    for s in stats_list:
        r = reject_reason(s, cfg)
        if r:
            s.note = r
            rejected.append(s)
        else:
            s.score = score(s)
            kept.append(s)
    kept.sort(key=lambda x: x.score, reverse=True)
    overflow = kept[cfg.max_watched_wallets:]
    for s in overflow:
        s.note = "below_watchlist_cutoff"
    return kept[:cfg.max_watched_wallets], rejected + overflow
