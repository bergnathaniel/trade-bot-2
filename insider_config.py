"""
Config for the insider / "smart money" copy-trade bot (insider_bot.py).

This bot is SEPARATE from bot.py's scalper. It runs its own loop, its own
logs, its own state file and its own bankroll cap, so the two can run at the
same time without stepping on each other.

Same hard rule as the scalper: total bankroll can never exceed
max_bankroll_usd, in paper or live mode. Enforced at startup.

In LIVE mode both bots sign with the SAME wallet (SOLANA_PRIVATE_KEY). Their
bankroll caps are independent and neither knows about the other's open
positions, so size them so the two caps together are still money you can
afford to lose entirely.
"""

from dataclasses import dataclass, field


@dataclass
class InsiderConfig:
    # ---- Mode ----
    # "paper"   — no network, synthetic wallets/tokens, simulated fills
    # "dry_run" — REAL wallet discovery + REAL on-chain tracking + REAL prices,
    #             but simulated fills (no SOLANA_PRIVATE_KEY needed)
    # "live"    — real swaps, real money. Read the README section first.
    mode: str = "dry_run"

    # ---- Capital constraints (hard caps) ----
    max_bankroll_usd: float = 5.00
    starting_balance_usd: float = 5.00
    max_position_usd: float = 1.50
    max_concurrent_positions: int = 3
    max_new_positions_per_hour: int = 12
    daily_max_loss_usd: float = 1.25          # circuit breaker halts new entries

    # ---- Fee model (mirrors config.py; tune to real costs) ----
    dex_swap_fee_pct: float = 0.0025
    platform_fee_flat_usd: float = 0.02
    network_fee_usd: float = 0.01
    est_slippage_pct: float = 0.015
    max_allowed_slippage_pct: float = 0.04

    # ======================================================================
    # DISCOVERY — how we decide a wallet is an "insider" / smart-money wallet
    # ======================================================================
    # We look at tokens that already pumped hard, find the wallets that got in
    # very early and very cheap, then check whether those wallets do that
    # *repeatedly* (skill) rather than once (luck).

    watchlist_path: str = "insider_watchlist.json"

    # A "winner" token, for the purpose of mining early buyers, is one whose
    # 24h price change clears this multiple. Kept lower than the scoring bar on
    # purpose: this only decides which tokens are worth mining for early
    # buyers — the wallet-quality bar below is what actually filters.
    winner_min_multiple: float = 3.0
    max_winner_tokens: int = 15            # cap discovery cost / candidate blast radius

    # When scanning a winner token's history, take its first N distinct buyer
    # wallets (they are the earliest — history is walked oldest-first), as long
    # as they land within early_window_minutes of the very first trade.
    early_window_minutes: float = 30.0
    early_first_n_buyers: int = 25

    # Per winner token, don't page more than this many transactions back
    # (Helius enhanced-tx pages are 100 each; keep discovery bounded/cheap).
    max_tx_pages_per_token: int = 6
    wallet_history_pages: int = 8          # pages of a candidate's own swap history

    # ---- Wallet scoring thresholds (a wallet must clear ALL of these) ----
    min_wallet_early_wins: int = 2      # early entries into >=winner_min_multiple tokens
    min_wallet_hit_rate: float = 0.30  # fraction of its scored token buys that went >=2x
    min_wallet_median_multiple: float = 1.5
    max_wallet_tokens_tracked: int = 400   # farm/wash bots churn thousands; skip them
    min_wallet_tokens_tracked: int = 3
    max_wallet_age_days: float = 400.0     # ignore ancient dormant wallets
    max_wallet_days_since_last_trade: float = 21.0  # a wallet that's gone quiet isn't useful

    # ---- Multiple-calculation hygiene (a real run without these produced
    #      medians of 1e16 from tiny "dust" buys — $0.0001 in, $50 out). ----
    min_buy_usd_for_stats: float = 3.0     # ignore a wallet's sub-$3 buys when scoring
    per_token_multiple_cap: float = 100.0  # clamp one token's result so a single
                                           # bogus/lucky 500x can't dominate the median
    # Cap how many wallets we actually follow. More wallets = more noise and
    # more of your bankroll chasing weak signals.
    max_watched_wallets: int = 25

    # Optional: wallets you already trust, always followed, skip scoring.
    # (base58 pubkeys)
    manual_wallets: list = field(default_factory=list)
    # Optional: seed winner-token mints for discovery when the trending feed
    # is unavailable or you want to mine specific runners.
    seed_winner_mints: list = field(default_factory=list)

    # ======================================================================
    # LIVE TRACKING — when a followed wallet buys, should we copy it?
    # ======================================================================
    # "Do what they do if they're buying a new token super early":
    copy_only_new_tokens: bool = True
    max_token_age_minutes: float = 360.0   # loosened 120 -> 360 (was skipping too many)
    max_token_holders_at_copy: int = 8000  # loosened 1500 -> 8000; the "research"
                                           # health checks below now do the quality
                                           # filtering instead of a raw holder cap
    min_token_liquidity_usd: float = 1000.0
    max_token_price_change_1h_pct: float = 600.0  # loosened 300 -> 600

    # --- "research the coin" health checks (real-data modes only) ---
    require_coin_health: bool = True
    min_coin_chg5m_pct: float = -12.0        # skip if it's dumping right now
    min_coin_liq_change_1h_pct: float = -35.0  # skip if liquidity is draining out
    min_coin_organic_score: float = 30.0     # Jupiter anti-wash score (0 = unknown, skip check)
    min_coin_organic_buyers_5m: int = 2      # need some real recent demand
    min_insider_buy_usd: float = 50.0      # ignore their dust / test buys
    # How many DIFFERENT followed wallets must buy the same token within
    # confirmation_window_minutes before we copy. 1 = copy the first mover.
    min_confirmations: int = 1
    confirmation_window_minutes: float = 45.0
    # Don't be exit liquidity: skip the copy if the token has already run past
    # this multiple of what the insiders paid — the early move we wanted is gone.
    max_entry_premium_over_insider: float = 1.8

    # ---- Conviction-weighted sizing ----
    # Position size scales from min_position_usd up to max_position_usd with
    # conviction = (# confirming wallets) and their combined watchlist score.
    min_position_usd: float = 0.60
    conviction_full_size_score: float = 60.0  # combined insider score that earns full size

    # ---- Exit strategy for copied positions ----
    take_profit_multiple: float = 2.5     # sell into strength at 2.5x
    trailing_stop_pct: float = 35.0       # give runners room; trail from peak
    hard_stop_loss_pct: float = 40.0      # absolute floor from entry
    max_hold_minutes: float = 720.0       # 12h time exit
    # Also bail if EVERY followed wallet that bought this token has fully sold.
    exit_when_insiders_exit: bool = True

    # ---- Loop timing ----
    poll_interval_seconds: float = 5.0        # paper mode
    live_poll_interval_seconds: float = 20.0  # per-wallet Helius calls add up

    # ---- Backtest (insider_backtest.py) ----
    backtest_lookback_days: int = 30
    # Modelled delay between the insider's on-chain buy and our fill (indexing +
    # poll + quote + confirm). We enter at the token's price this many minutes
    # after their buy, not at their price.
    latency_minutes: float = 3.0

    # ---- Endpoints (Jupiter ones mirror config.py) ----
    jupiter_swap_base_url: str = "https://api.jup.ag/swap/v2"
    jupiter_price_base_url: str = "https://api.jup.ag/price/v3"
    jupiter_token_info_base_url: str = "https://api.jup.ag/tokens/v2/search"
    jupiter_trending_url: str = "https://api.jup.ag/tokens/v2/toptraded/24h"
    # Helius enhanced-transactions REST base. The api-key is read out of
    # HELIUS_RPC_URL (…/?api-key=XXX) so you only configure the RPC URL once.
    helius_api_base: str = "https://api.helius.xyz/v0"
    sol_mint: str = "So11111111111111111111111111111111111111112"
    usdc_mint: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

    def round_trip_cost_pct(self) -> float:
        return 2 * self.dex_swap_fee_pct + 2 * self.est_slippage_pct

    def round_trip_cost_usd(self, position_size_usd: float) -> float:
        pct_cost = position_size_usd * self.round_trip_cost_pct()
        flat_cost = 2 * self.platform_fee_flat_usd + 2 * self.network_fee_usd
        return pct_cost + flat_cost
