"""
Config for the graduated-token scalper bot.

HARD RULE: total bankroll can never exceed MAX_BANKROLL_USD, in either
paper or live mode. This is enforced in bot.py at startup and on every loop.
"""

from dataclasses import dataclass


@dataclass
class Config:
    # ---- Mode ----
    # "paper"   — synthetic data + simulated fills, zero setup
    # "dry_run" — real pump.fun graduations + real Jupiter prices, but simulated fills (no wallet needed)
    # "live"    — real trades, real money. See README before flipping this.
    mode: str = "dry_run"

    # ---- Capital constraints (hard caps, do not exceed) ----
    # max_position_usd/max_concurrent_positions tuned via a 30-seed averaged paper
    # backtest (fewer, bigger positions dilute the flat $0.02+$0.01 per-trade fees,
    # which matter a lot at this bankroll size). Even after tuning, average net P&L
    # across seeds was roughly breakeven, not clearly positive — see conversation/
    # README caveats. This does not reflect real market behavior; MockDataSource is
    # an uncorrelated synthetic random walk, not a predictor of live performance.
    # Per-trade cap raised to $2. Concurrent slots dropped 14->3 to match: 14 slots at $2
    # each would need $28, far past the $7 bankroll, so most of them would've been silently
    # sized down to near-dust anyway. 3 x $2 = $6 of the $7 bankroll, leaving fee buffer.
    max_bankroll_usd: float = 7.00
    starting_balance_usd: float = 7.00
    max_position_usd: float = 2.00
    max_concurrent_positions: int = 3
    max_new_positions_per_hour: int = 30
    daily_max_loss_usd: float = 1.50     # circuit breaker halts new entries after $1.50 of session losses

    # ---- Fee model (tune these to match real Solana/Jupiter costs) ----
    # These are estimates. On real execution, use actual quoted fees from Jupiter
    # instead of these constants.
    dex_swap_fee_pct: float = 0.0025      # ~0.25% typical AMM fee, one side
    platform_fee_flat_usd: float = 0.02   # e.g. Fomo's flat per-trade fee / aggregator fee
    network_fee_usd: float = 0.01         # Solana gas + priority fee, one side
    est_slippage_pct: float = 0.01        # 1% expected slippage on a thin new pool
    max_allowed_slippage_pct: float = 0.03  # reject trade if realized slippage exceeds this

    # ---- Strategy: entry filters ----
    # Back down to moderate levels — "filter more" was a miscommunication (meant "look at
    # more candidates", not "reject more of them"). These keep accepting trades; liquidity/
    # holder-count/concentration are the ones actually shaping acceptance rate.
    min_liquidity_usd_at_entry: float = 1500.0
    # How long a just-graduated token sits in LiveDataSource's buffer before its
    # filters are actually evaluated. At t=0, liquidity is often unindexed (reads
    # as 0) and holder count is near-zero — not because the token is bad, but
    # because nothing has had time to happen yet.
    candidate_evaluation_delay_seconds: float = 60.0
    max_minutes_after_graduation: int = 10
    min_holder_count: int = 15
    max_single_wallet_holding_pct: float = 40.0

    # ---- Real due-diligence signals (not in the original stub) ----
    # Jupiter's Token API computes these directly — using them instead of just liquidity/
    # holder snapshots is actual research on each candidate, not another threshold tweak.
    min_organic_score: float = 35.0          # a real observed "medium" example scored 66.7
    # These two are collected and shown in SKIP/logging for visibility ("look at more data")
    # but set permissive so they don't add extra rejection right now — raise them later if
    # you want them to start actually blocking entries.
    min_organic_buyers_5m: int = 0
    min_price_change_1h_pct: float = -100.0
    min_price_change_5m_pct: float = -15.0   # reject tokens actively dumping right now
                                              # (catching a falling knife), not just noisy dips
    max_dev_mints: int = 8                   # reject serial token-factory wallets — a dev
                                              # who has minted many prior tokens is a real
                                              # repeat-rug-creator signal, not a guess

    # ---- Strategy: exit ----
    min_net_profit_margin_pct: float = 3.0   # required net margin ABOVE round-trip cost
    stop_loss_pct: float = 10.0              # lowered 15->10: caps downside per position tighter, per request
    max_hold_minutes: int = 30               # time-based exit regardless of P&L

    # ---- Loop ----
    poll_interval_seconds: int = 1        # paper mode only
    live_poll_interval_seconds: float = 3.0  # live mode hits rate-limited APIs; don't drop this below ~2s

    # ---- Live trading endpoints ----
    # Requires env vars (see .env.example): HELIUS_RPC_URL, JUPITER_API_KEY, SOLANA_PRIVATE_KEY.
    # Jupiter now requires an API key on every tier, including free — get one at portal.jup.ag.
    # Endpoints current as of Aug 2026 per developers.jup.ag; these APIs change, re-check if calls start failing.
    jupiter_swap_base_url: str = "https://api.jup.ag/swap/v2"
    jupiter_price_base_url: str = "https://api.jup.ag/price/v3"
    jupiter_token_info_base_url: str = "https://api.jup.ag/tokens/v2/search"
    pumpportal_ws_url: str = "wss://pumpportal.fun/api/data"  # free, no key needed for migration events
    sol_mint: str = "So11111111111111111111111111111111111111112"

    def round_trip_cost_pct(self) -> float:
        """Estimated total % cost of buying then selling one position."""
        return (
            2 * self.dex_swap_fee_pct
            + 2 * self.est_slippage_pct
        )

    def round_trip_cost_usd(self, position_size_usd: float) -> float:
        pct_cost = position_size_usd * self.round_trip_cost_pct()
        flat_cost = 2 * self.platform_fee_flat_usd + 2 * self.network_fee_usd
        return pct_cost + flat_cost

    def required_exit_multiplier(self, position_size_usd: float) -> float:
        """
        Price multiple the position needs to hit to clear costs + minimum margin.
        e.g. 1.08 means price needs to rise 8% for a profitable exit.
        """
        cost_usd = self.round_trip_cost_usd(position_size_usd)
        cost_pct = cost_usd / position_size_usd
        return 1 + cost_pct + (self.min_net_profit_margin_pct / 100)
