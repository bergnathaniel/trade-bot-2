# Automated mutation/search loop: tested

**Date:** 2026-09-16 · **Rules frozen before any result:** `PREREG_GA.md` (sha256 `4241265b…6ebb625`,
amended once - see below - before any holdout result was trusted)
**Rerun:** `python3 research/run_ga.py` (about 40 s: 40 generations x 60 population x 2 searches,
10-run synthetic sanity check, both integrity tests)
**Verdict: FAIL**, for both the evolved finalist and its random-search control.

---

## In plain English

**What was asked.** Build the one piece of a pasted research-loop spec that didn't already exist in
this project: an automated loop that generates strategies, backtests them, mutates the best ones
into new candidates, and repeats for many iterations - rather than a single hand-designed search.
Warned in advance that this is a bigger version of the same multiple-comparisons risk the earlier
9,504-config search (`SEARCH_RESULTS.md`) already ran into. Told to build it anyway.

**What was done.** A genetic algorithm over nine-gene strategies (five entry families - RSI
mean-reversion, moving-average cross, N-bar breakout, Bollinger mean-reversion, momentum - plus
side, trend/volume filters, ATR-based stop and target, and max hold), on two years of BTC-USD
5-minute candles:
- **Train** (2024-09-11 → 2026-01-29, 70% of the evolution window): every genome's fitness.
- **Validation** (2026-01-30 → 2026-06-10, 30%): which genomes survive to reproduce each generation.
- **Holdout** (2026-06-11 → 2026-09-10, 3 months): never seen by the loop at all. Looked at exactly
  once, for exactly two finalists, after evolution finished.
- A fixed, disclosed budget: 2,400 genome evaluations (40 generations x 60), same budget given to a
  **random-search control** with no selection or mutation at all, to see whether evolving anything
  actually beat trying that many random genomes.

**Result.**
- **Neither finalist is profitable on the holdout window**, or even close: the evolved finalist
  averaged −0.50% after fees over 73 trades; the random-search finalist −0.26% over 38 trades.
- **Both did worse than random entry timing** through their own exit rule (the luck yardstick):
  evolved −0.50% vs. a random-timing 95th percentile of −0.35%; random-search −0.26% vs. −0.19%.
  Neither strategy's specific entry timing beat picking the same number of random moments.
- **Zero of 600 logged top candidates, across the entire 40-generation search, ever had a positive
  mean return on the train data** - not the holdout, not validation, *the data it was being fit to*.
  That's as clean a "there's nothing here" as this project has produced.
- **Evolution did work, mechanically** - the population converged from a −0.25% best in generation 0
  to about −0.17% by generation 5 and stayed there, and 570 of the 600 top candidates converged on
  moving-average crossover as the "least bad" family. It found the least-losing corner of the search
  space. There wasn't a more-profitable corner to find.
- **The random-search control did about as well as the evolved one** (−0.26% vs. −0.50% on holdout,
  in the control's favor if anything). 2,400 guesses did roughly as well as 2,400 guesses plus 40
  generations of selection and mutation - evolution had nothing to sharpen.

**Two real bugs found and fixed before trusting any of this** (in keeping with "diagnose and fix,
don't just report failed"):
1. The fitness function scored "too few trades to be meaningful" as exactly `0.0`. Since every
   properly-traded genome scored negative (the finding above), `0.0` looked *better* than a real
   but losing genome, and the search kept selecting genomes that had barely traded at all - a
   completely different bug from "no edge," one that would have invalidated the search rather than
   just failed to find profit. Fixed by scoring under-traded genomes `-inf` instead of `0.0`.
2. The holdout luck-control, as originally specified, compared a finalist's real trades to a
   reshuffling of those same trades' own returns - mathematically guaranteed to have the identical
   mean, so it could never fail or pass. Replaced with the random-entry-timing control already
   established in `SEARCH_RESULTS.md` (real independent randomness, not a same-set reshuffle).

**Why.** Same conclusion as every other phase, arrived at with more machinery: at these trade
frequencies and holding times, fees and the absence of a real edge dominate everything. A search
smart enough to try 2,400 different ideas is still a search over noise if there's no signal in the
data to find - it just gets better at finding the least-bad way to lose.

**What happens next.** Nothing further planned on this shape of idea. Four independently-built
search mechanisms now agree: grid search, scored setups, nearest-neighbor matching, and genetic
search.

---

## Results

| | Genome (entry family) | Holdout trades | Holdout mean, after fees | Random-timing 95th pct | Win rate |
|---|---|---:|---:|---:|---:|
| Evolved finalist | ma_cross (both sides, trend+volume filters) | 73 | −0.501% | −0.350% | 34.2% |
| Random-search finalist | rsi_meanrev (long only) | 38 | −0.256% | −0.192% | 39.5% |

## Gates (holdout window only)

| Gate | Needs | Evolved | Random-search |
|---|---|---|---|
| G1 | ≥ 20 trades | 73 ✓ | 38 ✓ |
| G2 | mean after fees > 0 | −0.50% ✗ | −0.26% ✗ |
| G3 | beats random-timing 95th pct | −0.50% vs −0.35% ✗ | −0.26% vs −0.19% ✗ |
| G4 | win rate > 50%, p < 0.05/2400 (Bonferroni) | 34.2%, p≈0.998 ✗ | 39.5%, p≈0.928 ✗ |

**PASS** needs G1-G4. Result for both: **FAIL** (only G1).

## Integrity

- **Look-ahead (truncation) test:** deleting all data after a cut point changed no entry-signal
  decision at or before that cut, across 6 cuts (run against the breakout entry type specifically,
  since it needed a custom vectorized rolling window that was itself caught and fixed for an
  off-by-one look-ahead bug before this test was trusted - see the Amendments-equivalent note in
  `ga_engine.py`'s `_causal_rolling`). Pass.
- **Synthetic random-walk sanity check:** 10 pure-noise series, each run through its own smaller
  8-generation/20-population search. 0 of 10 cleared G1-G4 (the rule required ≤ 1 of 10). Pass.

Both passed, so the FAIL above is a real verdict.

## Files

- `PREREG_GA.md`: the frozen rules, amended once (the holdout luck-control mechanism, before any
  holdout result was trusted - the fitness bug was caught even earlier, before any result existed
  at all, so it needed no amendment)
- `ga_engine.py`, `run_ga.py`
- `results/ga.json`: full output; `results/ga_log.json`: every one of the 1,200 logged candidates
  (600 evolved, 600 random-search) across all 40 generations
