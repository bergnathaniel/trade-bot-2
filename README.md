# Graduated-Token Scalper Bot

A fee-aware trading bot for buying newly "graduated" micro-cap tokens and
exiting once profit clears round-trip costs. Defaults to **paper-trading
mode** — set `mode="live"` in `config.py` only when you're ready to trade
real money.

## Quick start (paper mode)

```
pip install -r requirements.txt
python bot.py --minutes 10
```

This runs a 10-minute simulated session against synthetic "graduation" events
(`data_sources.py: MockDataSource`), using the real strategy/fee/risk logic
from `config.py` and `bot.py`. At the end you get a session report and a
`trade_log.csv` with every buy, sell, and skipped trade (with reason).

Tune the strategy by editing `config.py` — position size, filters, profit
target, stop loss, circuit breaker, etc. Run several sessions and look at
`trade_log.csv` to see how often trades clear fees vs. get eaten by them.

## Live trading — how it's wired up

- **Graduation feed:** `LiveDataSource` (`data_sources.py`) subscribes to
  PumpPortal's free WebSocket feed (`wss://pumpportal.fun/api/data`,
  `subscribeMigration`) — an unofficial third-party feed since pump.fun has
  no official public API. Verified live: migration events return
  `{"mint": ..., "txType": "migrate", "pool": "pump-amm"}`.
- **Token filters + pricing:** enriched via Jupiter's Token API v2
  (`api.jup.ag/tokens/v2/search?query=<mint>`) for liquidity, holder count,
  and mint/freeze-authority-renounced status, and priced via Jupiter's Price
  API v3 (`api.jup.ag/price/v3`). Both work unauthenticated (rate-limited);
  set `JUPITER_API_KEY` (free at portal.jup.ag) for higher limits.
- **Execution:** `LiveExecutor` (`executors.py`) swaps through Jupiter's
  Swap API v2 (`GET /order` + `POST /execute`), signing transactions with a
  wallet loaded from `SOLANA_PRIVATE_KEY` via `wallet.py`.
- **LP-locked assumption:** pump.fun's own migration mechanism burns the LP
  position automatically, so `lp_locked` is set `True` by protocol design for
  pump.fun-origin graduations specifically — not a general guarantee.
- All endpoints/schemas above were checked against live traffic on
  2026-08-25. These are fast-moving, partly unofficial APIs — if requests
  start failing, that's the first thing to re-check.

### Setup

1. **Wallet.** Copy `.env.example` to `.env` (already done if you're reading
   this after setup) and set `SOLANA_PRIVATE_KEY` to either a BIP39 mnemonic
   phrase (space-separated) or a base58 secret key. **Never commit `.env`** —
   it's already in `.gitignore`. Before funding it, run
   `python -c "from wallet import load_keypair; print(load_keypair().pubkey())"`
   and confirm the printed address matches the wallet you expect (e.g. what
   Phantom/Fomo shows you) — catch a derivation mismatch before money moves,
   not after.
2. **RPC endpoint.** Set `HELIUS_RPC_URL` — free tier from helius.dev is
   enough for this volume of trading.
3. **Jupiter API key** (optional but recommended). Set `JUPITER_API_KEY`
   from portal.jup.ag for higher rate limits.
4. **Fund the wallet** with a small amount of SOL — start with far less than
   your eventual bankroll.
5. **Flip `mode="live"`** in `config.py`, run `python bot.py --minutes 5`,
   and type the confirmation phrase it prompts for. Watch the first several
   sessions closely, and check that fills/fees on Solscan match what the bot
   logs.

I (the assistant that wired this up) did not run this in live mode and never
handled your private key — you hold it, you run it, you're responsible for
what it does with real funds.

## Hard safety limits already built in

- `max_bankroll_usd` in `config.py` — bot refuses to start if configured
  above this.
- `max_position_usd` — caps size per trade.
- `daily_max_loss_usd` — circuit breaker halts new entries once tripped.
- `max_allowed_slippage_pct` — rejects fills with excessive slippage.
- Every skipped/filtered candidate is logged with its reason, so you can see
  *why* the bot passed on a token.

## Insider / "smart money" copy-trade bot (`insider_bot.py`)

A **second, independent bot**. It finds wallets that repeatedly got into
big-winner tokens early and cheap, then copies them when they buy a new young
token. Separate loop, separate logs (`insider_*_log.csv`), separate state
(`insider_state.json`), separate bankroll cap (`insider_config.py`) — so it
runs at the same time as `bot.py`. Same safe defaults: `mode="dry_run"`
(real data, simulated fills), flip to `"live"` only when you mean it.

**Phase 1 — build the watchlist:**

```
python insider_bot.py discover
```

Pulls hard-running tokens (24h change ≥ `winner_min_multiple`, default 3x)
from Jupiter's trending feed — plus any `seed_winner_mints` you set — pages
each one's earliest swaps via Helius' Enhanced Transactions API to get its
first ~25 buyer wallets, then scores every candidate on: how many big
winners it entered early (`early_wins`), its hit-rate on 2x+, its median
multiple, recency (a wallet quiet >21d is cut), and whether it looks like a
farm/wash bot (churns >400 tokens → cut). Survivors are written to
`insider_watchlist.json`, capped at `max_watched_wallets`, each with the
reason it made or missed the cut.

The bar is deliberately strict — a real run typically keeps only a handful
of wallets (≈4–15 on a normal day, since Jupiter's trending list only has
~10 tokens up 3x in 24h to mine). Widen it by lowering thresholds in
`insider_config.py`, adding `seed_winner_mints`, or hand-listing
`manual_wallets` (always followed).

**Phase 2 — follow them live:**

```
python insider_bot.py watch --minutes 120
```

Polls each watched wallet's recent swaps. When at least `min_confirmations`
of them buy the **same** token inside `confirmation_window_minutes`, and that
token is still young/thin enough (`max_token_age_minutes`,
`max_token_holders_at_copy`, `min_token_liquidity_usd`, not already vertical,
and not already run past `max_entry_premium_over_insider`× what the insiders
paid — no being exit liquidity), it copies the buy. Position size scales with
**conviction** (`min_position_usd` → `max_position_usd`, driven by how many
followed wallets bought and their combined watchlist score). Exits on
take-profit (`take_profit_multiple`, 2.5x), a trailing stop from the peak
(`trailing_stop_pct`), a hard stop from entry (`hard_stop_loss_pct`), a time
limit, or when every insider that bought it has fully sold.

**What it needs:** `HELIUS_RPC_URL` (the api-key is read straight out of it)
and ideally `JUPITER_API_KEY` for rate limits. `dry_run` needs no private key.
`live` shares the `SOLANA_PRIVATE_KEY` wallet with `bot.py` — the two bankroll
caps are independent and neither sees the other's positions, so treat the sum
as money you can lose entirely.

**Backtest (`python insider_backtest.py`):** replays the watchlist wallets'
recent buys through the strategy. Limited by data access — Helius' free
Enhanced Transactions API doesn't retain enough history to price exits on
trades more than ~a week old, so it will usually report `INCONCLUSIVE`. It
becomes useful only with a paid historical-price source (Birdeye /
GeckoTerminal Pro / Helius paid). The honest test is the forward dry-run.
`--min-buy N` lowers the insider-buy-size filter to widen the sample;
`--days N` sets the lookback.

**Caveats specific to this bot:** early-buyer detection is a heuristic (it
can't perfectly tell a real buyer from an LP/router account), a wallet that
was early on past winners is not guaranteed to stay good, and Jupiter often
has no `createdAt` for a brand-new token so the "age" filter degrades to the
holder/liquidity checks. It re-uses the same fee model and slippage guard as
the scalper. Tune everything in `insider_config.py`.

## Meme-coin momentum bot (`newcoin_bot.py`)

A **third, independent bot**. Own loop, own logs (`newcoin_*_log.csv`), own
state (`newcoin_state.json`), own bankroll cap (`newcoin_config.py`) — runs
alongside `bot.py` and `insider_bot.py`.

**Universe (changed 2026-08-27):** it trades meme coins off **Jupiter's
top-traded feed**, not just brand-new pump.fun graduations. Candidates must sit
inside a band — liquidity `$15k–$3M`, market cap `$50k–$30M`, 24h volume
`≥ $40k`, age `1h–21d`, `≥ 150` holders, 24h change between `-25%` and `+400%`
(no knives, no blow-off tops). Add `"migrations"` to `universe` in the config to
also mix in the pump.fun migration websocket; those must clear the same band.

Per candidate: **(1)** band filter → **(2)** regime gate (skip new entries while
SOL is down > `regime_min_sol_1h_pct` on the hour or fewer than
`regime_min_breadth` of the trending list is green) → **(3)** hard **rug-pull
screen** → **(4)** observe price for `observation_seconds`, then
`movement_study.classify_setup` must return **breakout** or **pullback** →
**(5)** edge gate (assumed target move must clear `min_edge_vs_cost_multiple`×
the round-trip cost %) → **(6)** optional learned scorer → **(7)** buy.

```
python newcoin_bot.py run --minutes 240     # trading session (default cmd)
python newcoin_bot.py train                  # fit the optional scorer on your logs
```

Safe default: `mode="dry_run"` (real Jupiter feeds + real on-chain rug checks,
simulated fills, no private key). Flip to `"live"` only after a run of dry-run
sessions whose logged **Net P&L** is actually positive, and type the
confirmation phrase it prompts for.

**The two setups (`movement_study.py`).** During `observation_seconds` the bot
samples price (plus holder count + liquidity in real modes) and combines that
with Jupiter's 5m/1h/24h stats:

- **breakout** — last price within `bo_max_dist_from_high_pct` of the observed
  high, 1h change in `[bo_min_1h_pct, bo_max_1h_pct]`, 5m change positive, 5m
  buys/sells ratio ≥ `bo_min_buy_sell_ratio`, last-third slope rising. Take the
  push, don't chase what already ran.
- **pullback** — 1h change strongly positive (`pb_min_1h_pct`+), a real but
  shallow retrace (`pb_min_drawdown_pct`–`pb_max_drawdown_pct` off the peak), 5m
  change not still dumping, last third flattening / turning up, not printing a
  new low.

Parabolic, downtrend and chop match neither and are skipped, with the closest
miss written to the log.

**Exit.** Two-stage trailing stop, no partial fills needed: a tight
`tight_trail_pct` trail from the peak until price hits `tp1_multiple`, at which
point the hard stop ratchets up to breakeven and the trail widens to
`runner_trail_pct` to let a runner run. Plus a hard `final_tp_multiple`
take-profit, a `max_hold_hours` time exit, an `reentry_cooldown_minutes`
cooldown per mint after any exit, and a **rug tripwire** that dumps the position
immediately on a liquidity collapse (`exit_on_liq_drop_pct` vs entry), a
one-poll price crater (`exit_on_single_tick_crash_pct`), or a holder-
concentration spike (`exit_on_top1_spike_pct`).

**The rug screen (`rug_screen.py`).** Any one HARD FAIL ⇒ verdict `RUG_RISK`,
never bought:

- mint authority still active (dev can mint infinite supply)
- freeze authority still active (dev can freeze your tokens)
- LP not locked/burned (dev can pull liquidity) — pump.fun migration burns it,
  so this normally passes for pump-origin tokens
- liquidity below `rug_min_liquidity_usd` (a single sell craters it)
- one wallet holds > `rug_max_top1_holder_pct` of supply, or top-10 hold
  > `rug_max_top10_holder_pct` (checked on-chain via `getTokenLargestAccounts`;
  falls back to Jupiter's top-holders %)
- liquidity fell more than `rug_max_liq_drop_1h_pct` in the last hour (LP being
  drained gradually)
- serial dev: more than `rug_max_dev_prior_mints` prior tokens minted
- no token→SOL route, or absurd price impact on a probe sell (honeypot-shaped)

Weaker signals (few holders, low Jupiter organic score, a sniper bundle
grabbing the float in the first 15 s, a fresh dip, sell-heavy 5-minute order
flow) **dock points** instead of hard-failing. Score ≥ `rug_min_score_to_trade`
⇒ `SAFE`; between that and `rug_caution_score` ⇒ `CAUTION` (traded at half
size, or skipped if `trade_on_caution=False`); below ⇒ `RUG_RISK`. Data it
can't verify (Helius down / not indexed yet) becomes a warning, not a silent
pass. Every check and its result is written to the log so you can see exactly
why a coin was skipped.

**What the screen cannot catch:** a *soft* rug — a dev who slow-bleeds sells
over hours — or a token that just quietly dies. That's what the band, the small
position size, the setup filter, and the exit tripwires are for.

**The optional learned scorer (`newcoin_model.py`).** A tiny logistic
regression, pure stdlib, trained **only on this bot's own closed trades**
(entry features, including which setup fired → did it clear fees?). Until you
have `model_min_samples` (60) closed trades it is ignored and the bot runs on
the rules alone. `python newcoin_bot.py train` fits it and reports sample count,
class balance, and in-sample accuracy — which on a few hundred noisy trades is a
*sanity check that the fit ran*, not evidence of edge.

**Sizing / fees.** Defaults are `$15` bankroll, `$5` per trade, 3 concurrent —
sized so the flat ~$0.06 round-trip cost is a small % of each position. Drop
`max_bankroll_usd` / `max_position_usd` / `starting_balance_usd` together if
you're running a smaller real book, but note the edge gate will refuse trades
once positions get small enough that fees eat the assumed move.

**Rate limits.** Real modes lean on Jupiter's top-traded / token / price APIs
(and Helius for the deep on-chain rug checks). Set `JUPITER_API_KEY` and a full
`HELIUS_RPC_URL` (`…/?api-key=XXX`) in `.env` — without Helius the authority /
holder-concentration / sniper-bundle checks degrade to "unverified" (a warning,
not a pass). `live_poll_interval_seconds`, `meta_refresh_seconds` and the shared
1.1 s throttle in `discovery.py` are conservative; raise them if you see 429s.

### Backtest (`newcoin_backtest.py`)

Replays the *actual* `classify_setup` + two-stage-exit logic over real
historical 5-minute candles (GeckoTerminal's free OHLCV — for young Solana
pools that's the pool's whole life), with a cost/slippage model, split
in-sample (first 60 %) / out-of-sample (last 40 %).

```
python newcoin_backtest.py --pools 60 --granularity 5
```

**First run (111 trades / 44 pools, 2026-08-27):** breakout looked great
in-sample (+40 %/trade, PF 9) and **collapsed out-of-sample to +0.2 %/trade,
PF 1.02, a net loss** — textbook in-sample luck. Pullback lost in both halves
(−5 %/trade). Buy-and-hold the same basket: median +16 %. Read the KNOWN LIMITS
block in the file (survivorship bias, shallow history, ~dozens of trades). Bottom
line: no demonstrated edge — the setups need real forward dry-run evidence
before they mean anything.

## Real-time signal / copy-trade bot (`alpha_bot.py`)

**Fourth, independent bot.** Successor to `insider_bot.py`'s `watch` loop,
which polled wallets every ~20 s (that lag is why it copied nothing). This one
**subscribes** — signals are pushed onto one queue and acted on in well under a
second:

- **`HeliusWalletSource`** — a Helius websocket `logsSubscribe` on each watched
  wallet; on a swap it pulls the enhanced tx, parses the buy, emits.
- **`XStreamSource`** — X API v2 filtered stream. Sets rules from
  `x_tracked_accounts` / `x_cashtags` / `x_keywords`, streams matching tweets,
  extracts a mint (or cashtag), filters by author follower count. Needs
  `X_BEARER_TOKEN` (any tier that grants filtered-stream access).
- **`WebhookSource`** — a local HTTP endpoint; any external alerter (Telegram
  bridge, TradingView, a paid alpha service, Helius webhooks) POSTs
  `{mint | ticker | text}`.

```
python alpha_bot.py run --minutes 180
```

Per signal: resolve to a concrete mint (ticker → highest-liquidity match, with
a thin-liquidity guard) → **fusion** (`fusion_mode="first"` acts on the fastest
source; `"confirm"` needs `confirm_n` distinct sources on the same mint inside
`confirm_window_seconds`) → rug screen (thresholds loosened vs `newcoin_bot`
because copied wallets also trade established coins where CEX/LP wallets hold big
chunks) → **anti-exit-liquidity** check (skip if price already ran
`max_entry_premium_over_insider_pct` past the insider's fill) → size → buy →
two-stage trailing-stop exit + rug tripwire + "exit when every source wallet has
sold" (`exit_when_sources_exit`). Each `BUY` row logs the signal-to-fill latency.

Config in `alpha_config.py`. Enable sources with `enable_onchain` / `enable_x` /
`enable_webhook`. `watched_wallets` is merged with `insider_watchlist.json` if
present. `mode="dry_run"` default (real signals, simulated fills). The
`priority_fee_microlamports` / `use_dynamic_slippage` knobs are declared for a
fast live-exec path but **not yet wired into `executors.py`** — live currently
uses the shared executor as-is.

**What this changes and what it doesn't.** It removes *your* latency — you now
react in <1 s instead of ~1 min. It does not remove adverse selection (the
wallets worth copying are copied by faster bots too, and they know it), and it
can't help that tweet-driven moves are usually gone before a retail order lands
($TRUMP was −68 % two weeks after it was actionable). Speed is necessary, not
sufficient. Verified 2026-08-27: full pipeline runs in `paper` (signal → resolve
→ screen → buy → manage) with sub-second logged latency.

## 20-day momentum basket (`momentum_basket.py`)

The multi-asset version of `momentum_bot.py` — the one approach in this repo
that survived honest out-of-sample testing. BTC / ETH / SOL, re-checked on an
interval:

- each asset is "on" when its close is above its close `lookback_days` (20) ago
  (with an optional `signal_deadband_pct` whipsaw guard, default off)
- "on" assets are weighted **inversely to recent volatility**, capped at
  `max_weight` (60 %) each; the rest sits in USDC
- it only trades when a target weight has drifted past `rebalance_threshold`

```
python momentum_basket.py backtest      # sim vs equal-weight buy-and-hold
python momentum_basket.py status
python momentum_basket.py run --minutes 1440
```

**Backtest (2026-08-27, ~1.6 yr — all the daily history Coinbase would page):**
momentum basket **+25 % / +15 % CAGR / −39 % max drawdown** vs equal-weight hold
**−23 % / −65 % max drawdown**. So over this window it beat buy-and-hold *and*
cut the drawdown by a third. Caveats that matter: 1.6 years is short and covers
a chop/drawdown regime that flatters a trend filter; ~30 signal flips per asset
per year is real churn (fees are modelled, thin wrapped-BTC/ETH slippage on
Solana is not); the `signal_deadband_pct` sweep was non-monotonic (0 %→+24 %,
3 %→+9 %, 5 %→+27 %) which is the fingerprint of a too-short sample — **don't
optimise that knob on this data.** Run it in paper for weeks.

`paper` default (tracks what it would do). `live` swaps USDC↔asset through
Jupiter with the confirmation phrase; **only assets with a Solana `mint` in
`ASSET_MINTS` trade live — by default just SOL**, because wrapped BTC/ETH
liquidity on Solana is thin and a real exchange is the better venue for those.

## Realistic expectations

Fee-drag is real and visible in the paper sessions — check the "Total fees
paid" line in the report versus "Gross profit." With a $20 bankroll and
$2-4 positions, fixed per-trade costs are a meaningful percentage of each
trade. This strategy can lose money even with a positive win rate if the
average winning trade isn't big enough relative to fees, and graduated
micro-cap tokens are volatile enough that stop-losses will get hit. Nothing
here guarantees profit — treat the $20 as money you can afford to lose
entirely while testing.

**`newcoin_bot.py` specifically.** Trading meme coins off the top-traded feed
with breakout / pullback setups is a more defensible bet than sniping raw
graduations — you're in a real market with continuation structure instead of
racing sniper bundles — but it is still speculation on assets with no
fundamentals, and my honest expectation is negative return. The rug screen,
regime gate, edge gate and fee-aware sizing attack the specific ways the old
version bled; none of them manufacture an edge. Soft rugs and slow deaths still
pass every automated check. Treat a long, genuinely positive Net-P&L dry-run
(not one lucky session) as the *minimum* bar before risking a cent — every
other strategy in this repo has been net-negative so far, including a real live
run.
