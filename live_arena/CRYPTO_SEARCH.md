# Crypto strategy search (Live Arena)

**Written:** 2026-09-12, before the crypto baskets were built and before any bot ran on these coin
histories.

## What was asked

Nothing worked on micro-cap stocks (`CONFIRM.md`). He then asked to "try it with crypto coins
instead and keep trying new strategies until one is found".

## Why the search has guard rails

Trying strategies until one wins always "finds" one. With enough tries, luck alone produces a
winner, and that winner then fails with real money. So a strategy only counts as found if it wins
on coins it has never been tested on, under the rules written here first.

## Coins

- **Picked by `make_crypto_basket.py`** (the full rule is in its docstring): coins with a US-dollar
  market on Coinbase, ranked 21–250 by market cap on CoinGecko today.
  - No stablecoins and no wrapped, staked or gold tokens.
  - Daily history back to 2022-01-01, with at most 2% of days missing.
- **Three groups.** The coins are shuffled with seed 20260914 and dealt into three equal groups:
  - **A, discovery:** strategies are tried and chosen here. This is the crypto basket the app shows.
  - **B, confirmation 1:** used once, for round 1's candidates.
  - **C, confirmation 2:** used once, for round 2's candidates.
- **Yardstick:** just holding bitcoin over the same window.

## Settings for every run

- Daily candles from 2022-01-01 to the last full day. The first 60 candles are warm-up.
- Orders fill at the next day's open.
- **0.25% per trade decides pass or fail.** Results at 0.10% are also reported.

## Rounds

- **Round 1:** all 34 existing bots run on group A.
  - Candidates are up to 5 bots with the highest median coin return on A.
  - To qualify, a bot's average on A must beat both Coin Flip's average and A's own buy-and-hold
    average, and its median must be above 0.
  - Candidates get one confirmation run on group B.
- **Round 2,** only if round 1 finds nothing:
  - New strategies, written after seeing round 1, run on group A with the same candidate rule.
  - Candidates get one confirmation run on group C.
- **After group C is used, no unseen coins are left.** The only fresh data after that is the future:
  paper-trading the best idea forward.

## "Found" means all five hold on the confirmation group

1. Its average return beats Coin Flip's average and the group's own buy-and-hold average.
2. Its median coin return is above 0.
3. It makes money on more than half of the coins.
4. Its average return beats just holding bitcoin.
5. Check 1 also holds in each half of the window on its own, split at the middle day, with 60
   candles of warm-up inside each half. That way a bot can't pass just by sitting in cash through
   the 2022 crash.

Passing checks 1–3 and 5 but failing check 4 is reported as "real, but not worth it".

## Limits, stated before the search

- **Today's rankings only.** Coins that died or were delisted since 2022 are missing.
- **The window starts in the 2022 crash.** That's why check 5 exists.
- **Small groups.** About 25–30 coins each is not much.
- **Simplified trading.** Fills and fees are simplified, and big orders in small coins move the
  price.

---

## Round 1 results (run 2026-09-12)

**The coins.**
- 29 coins qualified: 98 were ranked 21–250 and weren't stable or wrapped, and 69 of those were
  listed on Coinbase after 2022-01-01.
- The groups are therefore smaller than the "about 25–30" stated above:

| group | coins |
|---|---|
| A (11) | GRT SNX CHZ QNT CRV ZEN AVAX COMP FET ATOM TRAC |
| B (9) | ALGO DOT LTC AXS AAVE UNI BCH FIL CRO |
| C (9) | XTZ 1INCH ICP DASH MANA ETC JASMY SHIB ENS |

**Group A,** at 0.25% per trade with next-open fills:
- **Yardsticks:** just holding the coins averaged −77.6% (median −87.4%, 0 of 11 up). Holding
  bitcoin made +75.3%. Coin Flip averaged +85.5% (median +18.8%).
- **Only Ichimoku Cloud qualified** (median +15.3%, average +112.8%). Martingale had the best median
  (+26.2%), but its average (+35.8%) was below Coin Flip's.

**Group B, confirmation of Ichimoku:**
- **Yardsticks:** holding the coins averaged −66.2%, Coin Flip +81.7%, bitcoin +75.3%.
- **Ichimoku** averaged −15.0%, with a median of −15.8%, and made money on 3 of 9. It failed all five
  checks. First half of the window: −9.0%. Second half: −5.7%.

**Round 1 verdict: nothing found.**

---

## Amendment A1 (2026-09-12, after round 1, before round 2 was written or run)

**The problem.** The Coin Flip bot uses a fixed random seed, so it follows the same random in/out
calendar on every coin. These coins move together, so "Coin Flip's average" is one random draw, not
a measure of luck. In round 1 that single calendar happened to make +85.5% on group A while the coins
fell 78%. That put the bar at the lucky end of luck.

**The change for round 2.**
- **Luck bar:** everywhere the candidate rule, check 1 or check 5 says "Coin Flip's average", it now
  means the 90th percentile of the averages of 200 Coin Flip bots with different random calendars
  (seeds 1–200). They run on the same coins, window and settings.
- **Candidate pool:** every bot that isn't a yardstick, except Ichimoku, which was already confirmed
  on group B. That means the 7 new bots below plus round 1's bots, rescored under this rule on group
  A. Up to 5 candidates, highest median first, confirmed once on group C.

**Round 1's verdict stands.** Ichimoku also failed checks 2–5 on group B, and those don't involve
Coin Flip.

## Round 2 strategies (written after round 1, before round 2 ran)

1. **Bitcoin Weather:** own the coin only while bitcoin is above its 200-day average.
2. **Beating Bitcoin:** own it only while its price measured in bitcoin is above its 50-day average.
3. **Dual Momentum Coin:** own it while it's up over 30 days *and* up more than bitcoin over those
   30 days.
4. **Volatility-Sized Trend:** own it while it's up over 90 days. Buy 40% ÷ its yearly volatility
   of the cash, at most all of it.
5. **Crash Buyer:** buy when it's at least 70% below its 1-year high and up over the last 7 days.
   Sell at +50% or after 90 days.
6. **Yearly High Breakout:** buy a new 365-day closing high. Sell below the 50-day closing low.
7. **Weekend Holder:** own it only on Saturdays and Sundays (UTC).

---

## Round 2 results (run 2026-09-12)

**Checks before the run:**
- Bitcoin's prices lined up with every coin's days, with 0 mismatches.
- The one-pass simulation matched a candle-by-candle replay for all 41 bots on 600 FET candles.
- On FET, Weekend Holder bought only at Saturday opens and sold only at Monday opens (236 each).

**Group A,** at 0.25% per trade with next-open fills:
- **Luck bar.** Averages across 200 random Coin Flip calendars had a median of −63.1%, a 90th
  percentile of +4.2% and a best of +235.4%. The fixed-seed Coin Flip's +85.5% in round 1 sat near
  the lucky end, as Amendment A1 suspected.
- **Yardsticks:** just holding the coins averaged −77.6%; holding bitcoin made +75.3%.
- **New bots.** Crash Buyer had a median of +56.0% (average +66.8%, 7 of 11 up). The other six had
  medians from −32.6% to −80.7%, and Weekend Holder lost on all 11 coins.
- **Qualified under the amended rule,** highest median first. These three go to group C:

| bot | median | average |
|---|---|---|
| Crash Buyer | +56.0% | +66.8% |
| Martingale Doubler | +26.2% | +35.8% |
| Pyramid Builder | +5.4% | +85.1% |

**Group C, confirmation** (9 coins, at 0.25% per trade with next-open fills):
- **Yardsticks:** just holding the coins averaged −78.4% (median −80.1%, 0 of 9 up), and holding
  bitcoin made +75.3%. The luck bar was +1.3%; the median of the 200 calendars was −64.0%.
- **Halves** (split 2024-05-07): luck bars of +48.1% and +21.2%; holding the coins −37.7% and −48.7%.

| bot | average | median | made money | 1 beats luck & holding | 2 median > 0 | 3 more than half | 4 beats bitcoin | 5 both halves | result |
|---|---|---|---|---|---|---|---|---|---|
| Crash Buyer | +67.5% | +15.0% | 6 of 9 | pass | pass | pass | fail | fail (+43.7%, +15.5%) | fails |
| Martingale Doubler | +35.2% | +71.7% | 6 of 9 | pass | pass | pass | fail | fail (+23.4%, +8.4%) | fails |
| Pyramid Builder | +35.2% | +31.3% | 6 of 9 | pass | pass | pass | fail | fail (+18.4%; the second half's +31.5% passed) | fails |

**What it means:**
- **All three beat luck and beat holding the coins over the full window.** No strategy did that on
  micro-caps. But here it's a low bar: these coins lost 78% on average, so anything that spent time
  in cash beat holding them.
- **None beat just holding bitcoin** (+75.3%). Crash Buyer came closest at +67.5%, carried by three
  coins: DASH +320%, ICP +239% and XTZ +124%.
- **None beat luck in both halves.** One disclosure: Crash Buyer needs a year of prices, so inside
  each half it only trades for about the last 490 days, which makes check 5 harsher for it. Even
  without check 5 it fails check 4, so the most it could be called is "real, but not worth it".
- **Martingale's median looks great (+71.7%), but it lost 94% on MANA.** That's the risk of having
  no stop-loss.

**Verdict: nothing found.**

## What's left

Groups B and C are used up. Testing more strategies on these same coins would be re-rolling dice on
data that has already been searched. The only fresh data left:
- **The future.** Paper-trade Crash Buyer next to just holding bitcoin for months.
- **Better history.** Longer and wider crypto data that includes coins that died.
