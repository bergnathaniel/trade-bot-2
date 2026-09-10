# Trade Bot — a trading research project that concluded "don't"

This started as a Solana scalping bot and ended as a research harness. Roughly
**51 strategy configurations** were tested across crypto and US equities —
patterns, systematic rules, cross-sectional, mean-reversion, and finally
diversified trend following. Every one that was tested honestly failed to beat
buying an index fund.

That conclusion is the deliverable. The code here is kept so the conclusion can
be checked, not so the bots can be rerun.

> Descriptive of the past only. Nothing here is investment advice, a prediction,
> or a recommendation to buy or sell anything.

---

## `research/` — the part worth keeping

An honest-by-construction backtesting harness. Pure stdlib + `requests`; no
numpy or pandas.

```bash
python3 research/run_study.py etf          # 19 ETFs, 2004-2026
python3 research/run_study.py fut          # 16 futures, 2001-2026
python3 research/run_study.py etf --long-only --no-leverage
```

| file | what it does |
|---|---|
| `data.py` | Yahoo daily bars, dividend-adjusted, cached. ETF / futures / crypto universes, `^IRX` risk-free series, futures splice cleaning. |
| `stats.py` | Sharpe, drawdown, Calmar, skew/kurtosis, Probabilistic Sharpe, **Deflated Sharpe**, minimum track record length. |
| `tsmom.py` | Time-series momentum engine: 21/63/252 signals, EWMA vol targeting, portfolio construction, costs. |
| `run_study.py` | Six-part evaluation: standalone, diversification, portfolio blend, sub-period stability, multiple-testing correction, post-publication decay. |

**Why it exists.** The previous 50 backtests all shared one shape — single
instrument, long-or-flat, judged against buy & hold of that same instrument —
which structurally cannot evaluate a portfolio-level strategy. This harness
fixes that and adds the statistics that price in how many configurations were
tried.

Four things it does that the earlier backtests did not, each of which had been
silently manufacturing edge:

1. **Returns are excess of cash.** Without subtracting the risk-free rate, a
   "Sharpe" is just return over volatility, which badly flatters a low-vol
   levered book. Adding this took one variant from 0.69 to 0.45.
2. **Futures splices are cleaned.** Yahoo's `XX=F` series are spliced, not
   back-adjusted — `6J=F` prints −90% then +904% on consecutive days in 2001.
3. **Benchmarks are never traded.** `trade_syms` separates what the strategy
   may trade from what is only carried for comparison.
4. **The Deflated Sharpe Ratio is reported.** It asks whether a result beats
   what N skill-less attempts would produce by luck. Gaussian noise with a
   Sharpe of 0.75 scores 0.99 alone and 0.11 against 50 trials.

Read **[`research/FINDINGS.md`](research/FINDINGS.md)** for the full write-up.

---

## What survived testing

**20-day momentum** is the only approach that ever held up, and only weakly.

### `momentum_bot.py` — single asset
### `momentum_basket.py` — BTC / ETH / SOL

Each asset is "on" when its close is above its close 20 days ago. "On" assets
are weighted inversely to recent volatility, capped at 60% each; the rest sits
in USDC. It only trades when a target weight drifts past a threshold.

```bash
python3 momentum_basket.py backtest
python3 momentum_basket.py status
python3 momentum_basket.py run --minutes 1440
```

Backtest (~1.6 yr, all the daily history Coinbase would page): **+15% CAGR,
−39% max drawdown** vs equal-weight hold **−23%, −65% drawdown**. Caveats that
matter: 1.6 years is short and covers a regime that flatters a trend filter;
~30 signal flips per asset per year is real churn; the `signal_deadband_pct`
sweep was non-monotonic (0%→+24%, 3%→+9%, 5%→+27%), the fingerprint of a
too-short sample — **do not tune that knob on this data.**

Both default to `paper`. Live mode swaps through Jupiter behind a confirmation
phrase, and only trades assets with a Solana mint in `ASSET_MINTS` — by default
just SOL, because wrapped BTC/ETH liquidity on Solana is thin.

### `dca_bot.py` — dollar-cost averaging

Not a trading strategy; an accumulation schedule. +109% over 5yr on SOL, but
negative on every window starting in the last ~2.5 years.

---

## The evidence base

Standalone backtests, each testing *published* strategies rather than a bot:

| file | what it tested | result |
|---|---|---|
| `candle_strats_backtest.py` | 10 candlestick patterns | none passed |
| `more_strats_backtest.py` | 23 systematic strategies | none passed |
| `crsi_walkforward.py` | Connors RSI, walk-forward | 6/23 symbols positive |
| `classic_on_stocks.py` | 6 classics on US equities | passed — but see below |
| `connors_rsi2_walkforward.py` | the same, per-instrument | **pooling artifact** |
| `xsectional_backtest.py` | cross-sectional momentum | all 15 configs failed |
| `dca_backtest.py`, `momentum_universe.py` | the two survivors | weak |

The `classic_on_stocks.py` → `connors_rsi2_walkforward.py` pair is the most
instructive: pooling trades across many instruments produced a 6.07x "result"
that no single account could have earned. Per-instrument walk-forward gave
+1.1% median CAGR against +10.1% for buy & hold.

`dashboard.py` reads the logs for P&L.

---

## What was removed

Four Solana bots — the scalper, two copy-traders and a meme-momentum bot — were
deleted along with their configs, logs and state. All four were tested to
destruction: the scalper showed +$1.02/trade in-sample and −$0.12 out, the meme
breakout +40%/trade in and +0.2% out, the copy-traders never beat the ~1-minute
latency wall, and one real live run finished **down 50%**.

They are in git history if they are ever needed:

```bash
git log --diff-filter=D --name-only    # find the commit that removed them
git show <commit>^:bot.py              # read a deleted file
```

---

## Setup

Only needed to run the surviving bots live; `research/` needs nothing but
`requests`.

```bash
pip install -r requirements.txt
cp .env.example .env      # then fill it in
```

`.env` holds `SOLANA_PRIVATE_KEY` (a BIP39 mnemonic or base58 key),
`HELIUS_RPC_URL` and `JUPITER_API_KEY`. It is gitignored and must stay that
way. Before funding anything, confirm the derived address matches what your
wallet app shows:

```bash
python3 -c "from wallet import load_keypair; print(load_keypair().pubkey())"
```

I never ran any of this in live mode and never handled the private key — you
hold it, you run it, you are responsible for what it does with real money.

---

## Realistic expectations

Every strategy in this repo has been net-negative out-of-sample, including a
real live run that lost half its capital. Fee drag is visible in every paper
session — compare "Total fees paid" against "Gross profit" in the report. A
positive win rate is not enough if the average winner does not clear costs.

The honest summary after 51 configurations: **nothing here beat holding an
index fund or dollar-cost averaging.** The failure is structural — round-trip
costs plus no persistent daily-bar edge in liquid markets — not a missing
indicator, so searching for a 52nd rule will keep producing this result.
