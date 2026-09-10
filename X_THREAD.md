# X / Twitter thread — Trade Bot post-mortem

Post as a thread. Swap `[CASE_STUDY_URL]` and `[GITHUB]` before posting.
Pin it. Then reference it in the bio and in proposals.

Tone: matter-of-fact, numbers-first, no hype, no "we". The honesty is the
hook — don't undercut it by overselling at the end.

---

**1/**
I spent August building an automated crypto trading system. Six strategies,
real-time on-chain data, a backtester that runs the production code. ~9k
lines of Python.

It lost money. Here's the honest post-mortem: what got built, why there's no
edge, and what the build was actually worth. 🧵

**2/**
The premise: retail crypto moves fast and inefficiently, so maybe a fast,
disciplined, fee-aware bot pulls a small steady edge out of it.

I built the whole apparatus to test that properly instead of guessing. Paper
by default. One real-money run. Every strategy measured against just buying
and holding.

**3/**
The result wasn't "needs tuning." It was structurally negative.

At the position sizes a retail account actually runs, fixed fees + slippage
on thin liquidity + adverse selection against faster bots exceed any edge
these signals carry. Cost of learning that firsthand: $3.48.

**4/**
Example — the scalper. 60% win rate. Still lost money.

Avg win +$0.43. Avg loss −$2.23. Wins get taken at a fixed target; losses
run to a stop that slips through thin liquidity. Expectancy −$0.64/trade.

A positive hit rate is not an edge.

**5/**
The meme-coin momentum bot: a 7-stage gate — liquidity band → SOL regime
filter → on-chain rug screen → live breakout/pullback classifier →
edge-vs-cost gate → learned scorer → trailing exit.

Backtest on real historical data: −3.3%/trade, out-of-sample equity ≈ 0.05×.
Same tokens, bought and held: +34%.

**6/**
The copy-trade bots: find wallets that were early + cheap on past 3×+
winners, copy their next buy in under a second — Helius websockets + an X
filtered stream + a webhook, fused on one async queue.

Pipeline works, sub-second latency. Zero live trades: every candidate came
back `too_crowded`. Faster bots are already there.

**7/**
The part that actually mattered: the backtester replays the *real production
code* over historical OHLCV, with a cost/slippage model and a strict
in-sample / out-of-sample split.

It's what turned "breakout looks amazing" (in-sample +40%/trade) into
"breakout is noise" (OOS net loss) — before any real money moved.

**8/**
One strategy survived honest testing: a 20-day trend basket (BTC/ETH/SOL,
held while price is above its 20-day-ago close, weighted inversely to
volatility).

Beat equal-weight buy-and-hold over ~1.6 years and cut max drawdown by a
third. Sample's short. Running it in paper for weeks before I trust it.

**9/**
What the build demonstrates, regardless of the trading result:

- async multi-source real-time pipelines against flaky third-party APIs
- on-chain data analysis + fraud heuristics on Solana
- backtesting infra that disproves its own strategies
- layered risk controls, fail-closed defaults, fully auditable logs

**10/**
Full write-up — every strategy, in and out of sample, plus the architecture:
[CASE_STUDY_URL]

Code: [GITHUB]

I'm open to contract work on exactly this kind of thing: systems that have
to ingest messy live data and act on it reliably. naberg30@gmail.com

---

## Shorter variant (single post, if you don't want a thread)

I spent August building a 6-strategy automated crypto trading system — ~9k
lines of Python, real-time on-chain data, a backtester that runs the
production code.

It lost money, cleanly and cheaply ($3.48). The honest post-mortem — what I
built, why there's no edge, and the engineering that outlasts the trade:
[CASE_STUDY_URL]

## LinkedIn variant (more context, less thread-y)

In August I built an automated crypto trading system to test a specific
question: at retail scale, can a fast, disciplined, fee-aware bot extract a
small steady edge from inefficient markets?

Six independent strategies on one execution and risk core. ~9,000 lines of
Python, four dependencies. Paper-trading by default, one real-money session,
every strategy benchmarked against buy-and-hold.

The answer came back clean and negative — structurally, not "needs tuning."
Fixed transaction costs, slippage on thin liquidity, and adverse selection
against faster bots exceed any edge these signals carry at the position
sizes a retail account runs. The one real-money run went $7 → $3.52.

What the build demonstrates transfers directly to production data work:
async multi-source real-time ingestion, on-chain analysis and fraud
heuristics, backtesting infrastructure with strict out-of-sample discipline,
and layered risk engineering. Full write-up: [CASE_STUDY_URL]

I'm available for contract work in this area.
