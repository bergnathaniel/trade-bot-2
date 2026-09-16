# Nearest-neighbor setup matching: tested

**Date:** 2026-09-15 · **Rules frozen before any result:** `PREREG_NN.md` (sha256 `3ef3a7a4…35cc0d`)
**Rerun:** `python3 research/run_nn.py` (about 90 s, BTC-USD 5-minute candles, 1-minute source data
already cached from the earlier engine test)
**Verdict: FAIL.** Doesn't clear its own bar, and barely distinguishable from its own random control.

---

## In plain English

**What was asked.** A pasted pipeline: for the current candle, find the historical candles that
looked most like it, check what happened next each time, rank by past win rate, and trade the
consensus of the top 10 - plus a live-execution step that was out of scope from the start (nothing
built here places or could place a real order).

**Why test it at all.** The shape of the idea - search history for setups, trust the ones that
looked good - already has two answers on file in this project: the 9,504-config search
(`SEARCH_RESULTS.md`, NOT FOUND) and the sniper system (`SNIPER_RESULTS.md`, FAIL). What was
actually new here was the mechanism: continuous similarity matching (a nearest-neighbor search in
feature space) instead of a parameter grid or a small discrete vocabulary. That's the one piece
worth an honest look.

**What was done.**
1. Two years of BTC-USD 5-minute candles (210,078 bars). The first year is a neighbor pool only;
   the second year is where every decision is scored, walk-forward (a candle only ever uses
   neighbors whose own hour-ahead outcome had already finished).
2. Every candle got six features (short-term returns, RSI, Bollinger position, volume) and, for the
   10 nearest neighbors by Euclidean distance, a vote of LONG/SHORT/no-opinion from what that
   neighbor actually did over the next hour.
3. Traded the consensus (7 of 10 agreeing) at the next candle's open, held one hour, exited at that
   candle's open. 0.25% per side, matching every other crypto test in this project.
4. Compared against a **shuffled-label control**: the identical mechanism, the identical neighbor
   *sets*, but each neighbor's vote redrawn at random - so the search still runs, still finds "10
   neighbors," but whether they resemble the current candle is severed from their outcome. 200
   redraws.

**Result.**
- 4,926 trades over the test year. Mean return after fees: **−0.499% per trade.**
- The shuffled control's 200 runs averaged **−0.500%** per trade, 95th percentile −0.488%. The real
  run's −0.499% sits almost exactly on top of the control - similarity matching added nothing
  measurable over randomly relabeling the same neighbor sets.
- Win rate after fees: 9.5% (452 of 4,926). That sounds damning but is mostly a fee-rounding
  artifact, not a directional problem - see below.
- **Before fees**, the picture is completely different from "broken": win rate 50.6%, mean return
  +0.00028% per trade - a coin flip, exactly what a strategy with zero real edge looks like. The
  typical trade's price move was 0.31%, smaller than the 0.499% round-trip fee. Every trade, right
  direction or wrong, loses to the fee. That's a fee problem sitting on top of a no-signal problem,
  not a bug.

**Why.** The consensus mechanism finds *some* history that resembles right now (it always can, with
enough history) but resemblance in this feature space carries no information about direction - the
shuffled control proves that directly, since randomizing the labels changes nothing. On top of that,
even if it had signal, an hour-long hold on 5-minute crypto candles moves too little on average to
clear a 0.25%-per-side fee. Same failure mode as the search and the sniper system, arrived at a
third way.

**What happens next.** Nothing further planned on this shape of idea - three independent mechanisms
(grid search, scored setups, similarity matching) have now all failed the same way on the same
underlying claim. The live-execution part of the pasted pipeline was never built and never will be,
independent of any of these results.

---

## Results

| | Trades | Mean, after fees | Win rate, after fees | Win rate, before fees |
|---|---:|---:|---:|---:|
| Real (similarity matching) | 4,926 | −0.499% | 9.5% | 50.6% |
| Shuffled-label control (mean of 200) | ~4,900 each | −0.500% | – | – |
| Shuffled-label control, 95th percentile | | −0.488% | | |

## Gates

| Gate | Needs | Result | Pass? |
|---|---|---|---|
| G1 | ≥ 100 trades | 4,926 | yes |
| G2 | mean after fees > 0 | −0.499% | **no** |
| G3 | beats shuffled control's 95th percentile | −0.499% vs −0.488% | **no** |
| G4 | win rate > 50%, one-sided p < 0.05 | 9.5%, p = 1.0 | **no** |

PASS needs G1-G4. Result: **FAIL** (only G1).

## Integrity

- **Look-ahead (truncation) test:** deleting all data after a cut point changed no decision at or
  before that cut, across 6 cuts inside the test window. Pass.
- **Synthetic random-walk sanity check:** 10 pure-noise series (same volatility as real BTC, same
  pool/test split, 2-month test windows). 0 of 10 cleared G2+G3 (the rule required ≤ 1 of 10). Pass.

Both checks passed, so the FAIL above is a real verdict, not an artifact of a broken test.

## Files

- `PREREG_NN.md`: the frozen rules, amended once (rolling- vs. expanding-window normalization,
  before any code ran) and once more (the synthetic-check size, also before any code ran)
- `nn_engine.py`, `run_nn.py`
- `results/nn.json`: full output, including both integrity checks and every gate statistic
- 1-minute BTC-USD source candles: cached from the earlier engine test
  (`research/.cache/intraday/cb_BTC-USD_*.json`, 2024-09-11 → 2026-09-10)
