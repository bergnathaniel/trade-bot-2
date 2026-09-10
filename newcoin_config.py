"""
Config for newcoin_bot.py — the meme-coin momentum bot.

Scope (changed 2026-08-27): the universe is Jupiter's top-traded feed, not
just brand-new pump.fun graduations. Meme coins with real order flow, age
~1h–21d, liquidity / market-cap in a band where you're trading a market
rather than racing a sniper bundle. pump.fun migrations can still be mixed in
as a secondary source via `universe`, but they must clear the same band.

Still a THIRD bot, separate from bot.py and insider_bot.py: own loop, own
logs, own state, own bankroll cap.

Same hard rule as the rest of the project: total bankroll can never exceed
max_bankroll_usd, in any mode. Enforced at startup and every loop.

Default mode is "dry_run" (real data, simulated fills, no wallet). Flip to
"live" only after a stretch of dry-run sessions whose *logged* Net P&L is
actually positive. Nothing here guarantees profit — see the README.
"""

from dataclasses import dataclass, field


@dataclass
class NewCoinConfig:
    # ---- Mode ----
    # "paper"   — no network, synthetic tokens (discovery.MockDiscovery)
    # "dry_run" — REAL Jupiter feeds + REAL on-chain rug checks, simulated fills
    # "live"    — real swaps, real money; type the confirmation phrase
    mode: str = "live"

    # Where candidates come from. "trending" = Jupiter top-traded (primary).
    # Add "migrations" to also drain the pump.fun migration websocket.
    universe: tuple = ("trending",)

    # ---- Capital constraints (hard caps, do not exceed) ----
    # Sized so the flat ~$0.06 round-trip cost is a small % of each position.
    # Lower all of these if you're running a smaller real book.
    max_bankroll_usd: float = 15.00
    starting_balance_usd: float = 15.00
    # LOW-RISK NIGHT MODE 2026-08-27: smaller size, fewer shots, tighter stops.
    max_position_usd: float = 3.00
    max_concurrent_positions: int = 2
    max_new_positions_per_hour: int = 2
    max_trades_per_day: int = 8
    daily_max_loss_usd: float = 1.50          # circuit breaker halts new entries (live only)
    min_trade_usd: float = 1.00

    # ---- Fee model (mirrors config.py; tune to real costs) ----
    dex_swap_fee_pct: float = 0.0025
    platform_fee_flat_usd: float = 0.02
    network_fee_usd: float = 0.01
    est_slippage_pct: float = 0.012          # deeper pools than raw graduations
    max_allowed_slippage_pct: float = 0.03

    # ======================================================================
    # UNIVERSE BAND — a candidate must fall inside all of this to be screened
    # ======================================================================
    # LOOSENED 2026-08-27 so the bot actually reaches the trade stage — the
    # original band + dev_mints hard-fail were rejecting ~100% of the live
    # top-traded feed. Wider net = more trades but lower average quality; the
    # dry-run P&L is what tells you whether that was a good trade-off.
    band_min_liquidity_usd: float = 8_000.0
    band_max_liquidity_usd: float = 3_000_000.0
    band_min_market_cap_usd: float = 25_000.0
    band_max_market_cap_usd: float = 40_000_000.0
    band_min_volume_24h_usd: float = 8_000.0
    band_min_age_minutes: float = 45.0        # let the first hour of chaos pass
    band_max_age_days: float = 60.0           # still a "meme", not an old coin
    band_min_holders: int = 50
    band_min_24h_change_pct: float = -25.0    # don't catch a falling knife
    band_max_24h_change_pct: float = 400.0    # don't buy the top of a blow-off
    rediscover_minutes: float = 6.0          # re-emit the same mint at most this often

    # LiveDataSource (used only if "migrations" in universe) reads this name:
    candidate_evaluation_delay_seconds: float = 45.0

    # ======================================================================
    # REGIME GATE — no new entries when the tape is against longs
    # ======================================================================
    regime_min_sol_1h_pct: float = -3.5       # SOL down more than this on the hour -> stand down
    regime_min_breadth: float = 0.30          # share of the trending list that's green on 1h

    # ======================================================================
    # RUG SCREEN (rug_screen.py) — higher score = safer, 0..100
    # ======================================================================
    rug_min_score_to_trade: float = 62.0
    rug_caution_score: float = 48.0
    trade_on_caution: bool = True             # CAUTION -> half size (or skip if False)

    # Hard-fail thresholds (any one => RUG_RISK, never bought)
    rug_min_liquidity_usd: float = 4_000.0
    rug_max_top1_holder_pct: float = 30.0
    rug_max_top10_holder_pct: float = 70.0
    rug_max_liq_drop_1h_pct: float = -30.0
    # Jupiter's audit.devMints reads high for most pump.fun tokens on the
    # top-traded feed, so as a HARD fail it rejected nearly everything. Raised
    # to effectively-off; live mint/freeze authority + LP + liquidity + sell
    # route are the hard fails that still matter.
    rug_max_dev_prior_mints: int = 500
    rug_require_mint_authority_renounced: bool = True
    rug_require_freeze_authority_renounced: bool = True
    rug_require_lp_locked_or_burned: bool = True
    rug_require_sell_route: bool = True

    # Warning thresholds (dock points, don't hard-fail)
    rug_warn_min_holders: int = 60
    rug_warn_min_organic_score: float = 30.0
    rug_warn_min_organic_buyers_5m: int = 3
    rug_warn_max_sniper_bundle_pct: float = 22.0
    rug_warn_max_price_drop_5m_pct: float = -10.0
    rug_sell_route_probe_usd: float = 40.0
    rug_sell_route_max_impact_pct: float = 12.0

    # ======================================================================
    # OBSERVATION + SETUPS (movement_study.py)
    # ======================================================================
    observation_seconds: float = 150.0
    # Jupiter's price cache (12s TTL) + the shared 1.1s throttle mean we only
    # land ~6-9 price samples per 150s window, not 1/loop. 12 was rejecting
    # almost every candidate as "no_price_data". 5 matches the real sample rate.
    min_observation_ticks: int = 5
    meta_refresh_seconds: float = 25.0
    entry_setups: tuple = ("breakout",)   # pullback lost in the backtest — off for now

    mv_max_volatility_pct: float = 12.0       # tick-to-tick stdev ceiling for both setups
    mv_max_liq_drop_1h_pct: float = -25.0     # liquidity draining -> skip regardless of setup

    # --- breakout: coiled near range highs, buy-side flow expanding ---
    # LOOSENED HARD 2026-08-27: at the strict values almost nothing on the live
    # feed triggered (established coins mostly chop sideways in a 150s window).
    # These values effectively mean "flat-to-up, not dumping, buyers present" —
    # a much weaker bar. The backtest showed this kind of entry does NOT have an
    # edge; the dry-run P&L is the check.
    bo_max_dist_from_high_pct: float = 6.0    # last price within this % of the observed high
    bo_min_window_return_pct: float = 0.0     # net move over the observation window
    bo_min_1h_pct: float = 2.0
    bo_max_1h_pct: float = 55.0              # past this it already ran (PHASEONE was +51%)
    bo_min_5m_pct: float = 0.0
    bo_min_buy_sell_ratio: float = 1.15      # numBuys / numSells over 5m
    bo_min_late_slope_pct_per_min: float = -2.0

    # --- pullback continuation: strong 1h trend, shallow orderly retrace, turning up ---
    pb_min_1h_pct: float = -6.0
    pb_max_1h_pct: float = 250.0
    pb_min_drawdown_pct: float = 0.5         # a real retrace...
    pb_max_drawdown_pct: float = 35.0        # ...but not a trend break
    pb_min_5m_pct: float = -10.0            # not still dumping hard
    pb_min_late_slope_pct_per_min: float = -3.0   # last third flat-to-up
    pb_min_above_window_low_pct: float = 0.0        # didn't just print a new low

    # Expected-move gate: the setup's rough target must clear this multiple of
    # the round-trip cost %, or the trade isn't worth the fees.
    min_edge_vs_cost_multiple: float = 3.0
    assumed_target_move_pct: float = 18.0    # rough per-trade upside used for the gate

    # ======================================================================
    # EXIT — two-stage trailing stop, mode-agnostic (no partial fills needed)
    # ======================================================================
    tp1_multiple: float = 1.10               # at +10% ratchet the stop to breakeven and widen the trail
    breakeven_buffer_pct: float = 1.0        # stop parks this % above entry after tp1
    tight_trail_pct: float = 6.0             # trail from peak before tp1
    runner_trail_pct: float = 24.0           # trail from peak after tp1 (let it run)
    final_tp_multiple: float = 2.6           # hard take-profit
    hard_stop_loss_pct: float = 7.0          # initial stop distance from entry
    max_hold_hours: float = 10.0             # time exit
    reentry_cooldown_minutes: float = 90.0   # don't re-touch a mint for this long after an exit

    # Rug tripwire while holding
    exit_on_liq_drop_pct: float = -25.0      # liquidity fell this much vs entry
    exit_on_single_tick_crash_pct: float = -22.0   # one poll-to-poll price crater
    exit_on_top1_spike_pct: float = 30.0     # a wallet ballooned to this % of supply since entry

    # ======================================================================
    # LEARNED SCORER (newcoin_model.py) — off until you have data
    # ======================================================================
    use_model: bool = True
    model_path: str = "newcoin_model.json"
    model_min_samples: int = 60
    model_min_prob: float = 0.5

    # ---- Loop timing ----
    poll_interval_seconds: float = 3.0        # paper
    live_poll_interval_seconds: float = 6.0   # real modes hit rate-limited APIs

    # ---- Files ----
    trade_log_path: str = "newcoin_trade_log.csv"
    dry_run_log_path: str = "newcoin_dry_run_log.csv"
    state_path: str = "newcoin_state.json"

    # ---- Endpoints ----
    jupiter_swap_base_url: str = "https://api.jup.ag/swap/v2"
    jupiter_price_base_url: str = "https://api.jup.ag/price/v3"
    jupiter_token_info_base_url: str = "https://api.jup.ag/tokens/v2/search"
    jupiter_trending_url: str = "https://api.jup.ag/tokens/v2/toptraded/24h"
    jupiter_quote_url: str = "https://api.jup.ag/swap/v2/quote"
    pumpportal_ws_url: str = "wss://pumpportal.fun/api/data"
    helius_api_base: str = "https://api.helius.xyz/v0"
    sol_mint: str = "So11111111111111111111111111111111111111112"
    usdc_mint: str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

    # ---- Cost helpers ----
    def round_trip_cost_pct(self) -> float:
        return 2 * self.dex_swap_fee_pct + 2 * self.est_slippage_pct

    def round_trip_cost_usd(self, position_size_usd: float) -> float:
        pct_cost = position_size_usd * self.round_trip_cost_pct()
        flat_cost = 2 * self.platform_fee_flat_usd + 2 * self.network_fee_usd
        return pct_cost + flat_cost

    def required_exit_multiplier(self, position_size_usd: float) -> float:
        cost_usd = self.round_trip_cost_usd(position_size_usd)
        return 1 + cost_usd / position_size_usd

    def edge_ok(self, position_size_usd: float) -> bool:
        """Is the assumed target move worth the round-trip cost at this size?"""
        cost_pct = self.round_trip_cost_usd(position_size_usd) / position_size_usd * 100
        return self.assumed_target_move_pct >= self.min_edge_vs_cost_multiple * cost_pct
