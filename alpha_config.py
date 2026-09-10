"""
Config for alpha_bot.py — the real-time signal / copy-trade bot.

This is the successor to insider_bot.py's `watch` loop. The difference that
matters: insider_bot POLLS each watched wallet every ~20s (that's the ~1-minute
lag that made it copy nothing). alpha_bot SUBSCRIBES — a Helius websocket pushes
a watched wallet's swaps as they land, an X filtered-stream pushes tweets as
they post, and a webhook endpoint accepts pushes from anything else. All three
land on one queue and are acted on in well under a second.

FOURTH independent bot: own loop, own logs, own state, own bankroll cap. Runs
alongside bot.py / insider_bot.py / newcoin_bot.py.

Safe default: mode="dry_run" (real signals, real prices, real rug checks,
simulated fills, no private key). "live" places real swaps and makes you type a
confirmation phrase. Sub-second execution removes YOUR lag; it does not remove
adverse selection or the fact that tweet-driven moves are usually already gone
by the time a retail-sized order can land. Nothing here guarantees profit.
"""

from dataclasses import dataclass, field


@dataclass
class AlphaConfig:
    # ---- Mode ----
    mode: str = "live"           # "paper" | "dry_run" | "live"

    # ---- Capital constraints (hard caps) ----
    max_bankroll_usd: float = 15.00
    starting_balance_usd: float = 15.00
    max_position_usd: float = 5.00
    max_concurrent_positions: int = 3
    max_new_positions_per_hour: int = 8
    max_trades_per_day: int = 20
    daily_max_loss_usd: float = 4.00
    min_trade_usd: float = 1.00

    # ---- Fee / execution model ----
    dex_swap_fee_pct: float = 0.0025
    platform_fee_flat_usd: float = 0.02
    network_fee_usd: float = 0.01
    est_slippage_pct: float = 0.015
    max_allowed_slippage_pct: float = 0.04
    # Live execution speed knobs (see fast path in alpha_bot / executors).
    priority_fee_microlamports: int = 200_000   # ~0.0002 SOL tip; raise to win landing races
    use_dynamic_slippage: bool = True
    buy_timeout_seconds: float = 8.0

    # ======================================================================
    # SIGNAL SOURCES — turn on the ones you have data for
    # ======================================================================
    enable_onchain: bool = True     # Helius websocket on watched wallets
    enable_x: bool = False          # X API v2 filtered stream (needs X_BEARER_TOKEN)
    enable_webhook: bool = False    # local HTTP endpoint for external pushes
    enable_mock: bool = False       # synthetic signals (paper testing)
    mock_mints: tuple = (           # MockSource cycles these real mints so the
        "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",   # BONK
        "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",   # WIF
    )

    # --- on-chain: wallets to copy (base58 pubkeys). Seed from
    #     insider_watchlist.json or hand-list your best. ---
    watched_wallets: tuple = ()
    load_watchlist_json: str = "insider_watchlist.json"   # merged in if present
    max_watched_wallets: int = 60
    onchain_only_buys: bool = True
    min_insider_buy_usd: float = 60.0       # ignore their dust / test buys
    max_entry_premium_over_insider_pct: float = 25.0   # don't be exit liquidity

    # --- X filtered stream ---
    x_tracked_accounts: tuple = ()         # handles without '@'
    x_cashtags: tuple = ()                 # e.g. ("SOL","BONK") -> matches "$BONK"
    x_keywords: tuple = ()                 # raw phrases
    x_require_contract_address: bool = True  # only act on a tweet that contains a mint
    x_min_author_followers: int = 25_000

    # --- webhook ---
    webhook_host: str = "127.0.0.1"
    webhook_port: int = 8787
    webhook_secret: str = ""              # require ?secret= or X-Secret header if set

    # ======================================================================
    # SIGNAL FUSION
    # ======================================================================
    fusion_mode: str = "first"           # "first" = act on the fastest source
                                         # "confirm" = need N sources on the same mint
    confirm_n: int = 2
    confirm_window_seconds: float = 90.0
    signal_dedupe_seconds: float = 600.0  # ignore repeat signals for a mint this long

    # ======================================================================
    # RESOLUTION + SCREEN (before any buy)
    # ======================================================================
    resolve_min_liquidity_usd: float = 12_000.0
    resolve_max_token_age_minutes: float = 0.0   # 0 = no age cap (copy established coins too)
    resolve_max_holders: int = 0                 # 0 = no cap
    require_rug_pass: bool = True                 # RUG_RISK verdict -> never buy
    trade_on_caution: bool = True                 # CAUTION -> half size

    # ======================================================================
    # EXIT — two-stage trailing stop (mode-agnostic, no partial fills)
    # ======================================================================
    tp1_multiple: float = 1.20
    breakeven_buffer_pct: float = 1.0
    tight_trail_pct: float = 12.0
    runner_trail_pct: float = 30.0
    final_tp_multiple: float = 3.0
    hard_stop_loss_pct: float = 16.0
    max_hold_hours: float = 8.0
    reentry_cooldown_minutes: float = 60.0
    exit_on_liq_drop_pct: float = -28.0
    exit_on_single_tick_crash_pct: float = -24.0
    # copy-specific: bail if every source wallet that bought it has fully sold
    exit_when_sources_exit: bool = True

    # ---- Loop timing ----
    manage_interval_seconds: float = 4.0   # position-management poll (signals are push)

    # ---- Files ----
    trade_log_path: str = "alpha_trade_log.csv"
    dry_run_log_path: str = "alpha_dry_run_log.csv"
    state_path: str = "alpha_state.json"

    # ---- Endpoints ----
    jupiter_swap_base_url: str = "https://api.jup.ag/swap/v2"
    jupiter_price_base_url: str = "https://api.jup.ag/price/v3"
    jupiter_token_info_base_url: str = "https://api.jup.ag/tokens/v2/search"
    jupiter_quote_url: str = "https://api.jup.ag/swap/v2/quote"
    helius_api_base: str = "https://api.helius.xyz/v0"
    x_stream_url: str = "https://api.twitter.com/2/tweets/search/stream"
    x_rules_url: str = "https://api.twitter.com/2/tweets/search/stream/rules"
    sol_mint: str = "So11111111111111111111111111111111111111112"
    usdc_mint: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

    # ---- Cost helpers ----
    def round_trip_cost_pct(self) -> float:
        return 2 * self.dex_swap_fee_pct + 2 * self.est_slippage_pct

    def round_trip_cost_usd(self, size_usd: float) -> float:
        return size_usd * self.round_trip_cost_pct() + 2 * self.platform_fee_flat_usd + 2 * self.network_fee_usd

    def required_exit_multiplier(self, size_usd: float) -> float:
        return 1 + self.round_trip_cost_usd(size_usd) / size_usd
