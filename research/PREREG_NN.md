# Pre-Registration: nearest-neighbor setup matching (config family NN)

**Frozen:** 2026-09-15, before any result was computed.
**Integrity:** `run_nn.py` prints this file's SHA-256 with every result. Never edit this text after
results exist. Changes go in a dated *Amendments* section.

---

## Why this test

The user pasted a pipeline: for the current candle, find the historical candles that looked most
like it, check what those did next, rank them by past win rate, and trade the consensus of the top
10. It includes a step where Claude reads the evidence and a final fork ending in live broker
execution.

Two things happened before writing any code:
1. The live-execution step is out of scope. Nothing built here places or could place a real order;
   every path ends at a paper fill.
2. This is not a new idea in this project. It is close to two already-tested ones:
   - `PREREG_SEARCH.md` (SR): searched thousands of configurations on the first half of a year,
     tested the winners on the second half. NOT FOUND.
   - `SNIPER_RESULTS.md` (SN): setups scored and ranked, same family of prompt. FAIL - setups no
     better than random entry timing through the same exits.
   - `candle_language.py` (the weekly study): candles turned into discrete "words", each word's
     forward return tracked, only words with a strong record traded. Found nothing that persists
     week to week (0 of 1,861 crypto records stayed positive across the sample's two halves).

   What's actually different here from all three: continuous-valued similarity matching (a
   Euclidean nearest-neighbor search in feature space) instead of a parameter grid, a fixed rule
   family, or a small discrete vocabulary. That's the one thing worth testing that hasn't been
   tested. Everything else about the shape of the idea already has a documented answer.

**Prior: low**, given the above. This test exists to check the one genuinely new mechanism, not to
re-ask a question this project has already answered twice.

---

## A. Data

- **BTC-USD**, Coinbase Exchange 1-minute candles via `intraday.coinbase_1m`, already cached
  2024-09-11 -> 2026-09-10 (2 years) from the earlier engine test. Resampled to 5-minute bars
  (open of the first minute, close of the last, high/low/volume aggregated) to match the pasted
  pipeline's stated timeframe.
- One symbol only. The pasted pipeline names BTC/USD 5m specifically; this test doesn't generalize
  beyond that pair, and says so in the limitations below.
- **Pool-only period:** 2024-09-11 -> 2025-09-10 (year 1). Candles here are only ever looked up as
  historical neighbors. No decision is scored in this period.
- **Test period:** 2025-09-11 -> 2026-09-10 (year 2). Every decision scored below falls in this
  window. A decision at candle i may use candle j as a neighbor only if j's full outcome window has
  already closed before i (j + H <= i) - true walk-forward, not a fixed train/test boundary for the
  neighbor pool itself, since the pipeline as described keeps learning from everything already seen.

---

## B. Features (the "setup")

Six standardized features per candle, using only data at or before that candle:
- return over the last 1, 3, and 12 bars (5, 15, 60 minutes)
- RSI(14)
- position in a 20-bar Bollinger channel: (close - mid) / (2 * std), clipped to [-2, 2]
- volume vs. its 20-bar average, log ratio

Each feature is z-scored using the trailing 2,000-bar (about 1 week) mean/std as of that candle -
not fit once on the whole dataset, which would leak the future into the normalization, and not
refit per decision either, since that would make a neighbor's coordinates depend on when it's being
looked up rather than being a fixed point a nearest-neighbor search can index. A rolling window is
still causal (uses only that candle's own past) and gives every candle one stable feature vector.

## C. Outcome (what a neighbor "did next")

Forward return over H = 12 bars (1 hour), in R-multiples: R = forward return / (ATR14 / price) at
the neighbor's own candle. A neighbor "votes" LONG if R >= +0.5, SHORT if R <= -0.5, otherwise it
casts no vote (this is the pipeline's implicit "no trade" case for a setup).

## D. Matching and decision

At each test-period candle i:
1. Compute i's feature vector (as of i, expanding-window z-scored).
2. Find the K = 10 nearest eligible neighbors (Euclidean distance in feature space) among all
   candles j with j + H <= i, searched across both the pool and however much of the test period has
   already elapsed.
3. Count votes among those 10. If >= 7 agree LONG, decision = LONG. If >= 7 agree SHORT, decision =
   SHORT. Otherwise NO TRADE - this matches the pasted pipeline's consensus rule exactly.
4. A LONG/SHORT decision enters at the next bar's open and exits H bars later at that bar's open.
   One position at a time; a new signal while already in a trade is ignored.

No Claude-in-the-loop step: the "Claude analyzes the evidence" node in the pasted pipeline is a
mechanical vote-counting rule here, not a live judgment call, so the test is reproducible and
can't quietly change its mind between runs.

## E. Costs

0.25% per side (0.50% round trip) - the same crypto fee used everywhere else in this project
(Live Arena's crypto group, Phase 9's crypto trend test).

---

## F. Gates (test period only, decided now)

- **G1:** at least 100 closed trades.
- **G2:** mean return after fees > 0.
- **G3:** mean return after fees beats a shuffled-label control (below) at the 95th percentile.
- **G4:** the win rate (share of trades with positive return after fees) is above 50% with a
  one-sided binomial p < 0.05.

**PASS** = G1-G4 all hold. Anything else is FAIL.

## G. The luck yardstick (shuffled-label control)

The identical engine and identical decision points, but every neighbor's vote is replaced by a
random draw from the pool's overall vote distribution (same LONG/SHORT/no-vote base rates,
independent of that neighbor's actual features) - so the similarity search still runs, still finds
"neighbors," but whether they resemble the current candle is severed from their outcome. Same seed
(20260915), same trade count target. 200 runs; report the mean and the 95th percentile.

This isolates the one thing actually being tested: does resemblance in feature space carry
information, or does grouping-and-voting produce a plausible-looking result on its own?

## H. Integrity (must pass before any result counts)

- `leakage.truncation_test` on the decision function: deleting everything after a cut point must
  never change a decision at or before it. lag = 0 (next-open execution).
- Ten synthetic random-walk series, each sized to a 2-month test period (kept shorter than the real
  2-year run so this check stays fast; same pool/test-split shape and same gates otherwise): the
  engine must not find a G2+G3 pass on pure noise more than 1 of the 10 runs (a sanity bound on the
  gate, not a claim about real data).

If either check fails, there is no verdict.

---

## I. Limitations, stated in advance

- One symbol, one timeframe, one holding period, one feature set. A different H or feature list
  might do better or worse; this test doesn't search over that, because searching would just
  recreate the SR test's already-answered question with extra steps.
- Two years of data, one train/test-style split (though the neighbor pool keeps growing through the
  test period, which is different from SR's fixed split).
- R-multiples, no compounding or position sizing.
- The pasted pipeline names Claude as a live decision-maker and ends at broker execution. Neither
  is built. This test only evaluates whether the mechanical version of steps 1-8 has any signal.

**Registry rows:** NN-RETAIL (the test above), NN-SHUFFLE (the control from section G, reported
alongside it).

---

## Amendments

(none)
