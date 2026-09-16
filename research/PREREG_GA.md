# Pre-Registration: automated mutation/search loop (config family GA)

**Frozen:** 2026-09-15, before any generation ran.
**Integrity:** `run_ga.py` prints this file's SHA-256 with every result. Never edit this text after
results exist. Changes go in a dated *Amendments* section.

---

## Why this test

The user pasted a spec for an automated research loop: generate many strategies, backtest them,
mutate the best ones into new candidates, repeat for many iterations, keep only what survives
completely unseen data. Asked to inspect the codebase first: almost everything in the spec already
exists here in some form (data collection, cost-aware backtesting, out-of-sample gates, saved
results, a paper-only dashboard). The one real gap is automated mutation across many iterations
instead of a single hand-designed search.

That gap is also the dangerous part. `SEARCH_RESULTS.md`'s own conclusion about its one-shot
9,504-config grid: "a search of thousands of settings always finds some that won on the data they
were tuned on. That says nothing about next month." A loop that mutates and re-tests thousands of
times is a bigger version of exactly that search - with enough trials, *something* clears any fixed
bar by chance alone. The user was told this directly and said to build it anyway.

So this test exists to answer the question honestly, with the multiple-comparisons problem treated
as the central risk to guard against, not a footnote:
1. A **fixed, disclosed trial budget** (below), not "keep going until something works."
2. A **final holdout window the loop never sees or selects against**, touched exactly once, at the
   end, for exactly one candidate (or a small pre-declared number of finalists).
3. A **significance bar that scales with how many candidates were actually tried**, so a lucky
   winner among thousands doesn't read as a real one.

**Prior: low**, for the reasons above and because three independently-built search mechanisms in
this project (grid search, scored setups, nearest-neighbor matching) have already failed the same
way. This is a fourth, better-resourced attempt at the same underlying question, not a new idea.

---

## A. Data

BTC-USD, Coinbase Exchange 5-minute candles (same source and cache as `PREREG_NN.md`), 2024-09-11 ->
2026-09-10 (two years).

- **Evolution window:** 2024-09-11 -> 2026-06-10 (21 months). Split inside this window:
  - **Train** (70%): 2024-09-11 -> 2026-01-29. Every candidate's fitness during the loop is
    computed here.
  - **Validation** (30%): 2026-01-30 -> 2026-06-10. Used only to decide which candidates survive to
    reproduce each generation (see D). Still "seen" by the process, so it is not a claim of
    out-of-sample performance - the holdout below is.
- **Holdout (final test):** 2026-06-11 -> 2026-09-10 (3 months). **Never used for fitness,
  selection, or mutation, at any generation.** Looked at exactly once, after evolution stops, for
  the finalists chosen in F.

---

## B. The genome (one candidate strategy)

Nine genes, covering price action, indicators, volatility, trend, momentum, and volume as the user
asked:

| Gene | Range | Meaning |
|---|---|---|
| `entry_type` | one of RSI mean-reversion, moving-average cross, N-bar breakout, Bollinger mean-reversion, momentum | the strategy family |
| `param1` | continuous, meaning depends on `entry_type` | e.g. RSI threshold, fast MA length, breakout lookback |
| `param2` | continuous, meaning depends on `entry_type` | e.g. slow MA length, momentum threshold |
| `side` | long-only, short-only, or both | |
| `trend_filter` | on/off | only trade with a 200-bar moving-average trend |
| `volume_filter` | on/off | only trade when volume is above its 20-bar average |
| `stop_atr` | continuous, 0.5-6 | stop-loss distance, in ATR(14) multiples |
| `target_atr` | continuous, 0 (none) or 0.5-10 | take-profit distance, in ATR(14) multiples |
| `max_hold` | integer, 6-288 bars (30 min - 24 hours) | exits here if neither stop nor target hit |

Entries fill at the next bar's open; exits fill at the open of the bar the stop/target/max-hold
condition is first true on its close (a one-bar-late, conservative fill, not the exact intrabar
stop price). 0.25% per side.

## C. Mutation and reproduction

- **Population:** 60 genomes per generation.
- **Generations:** 40. **Total budget: 2,400 genome evaluations on train, plus one validation-period
  evaluation for each of that generation's survivors** - a fixed, disclosed number, not open-ended.
- **Generation 0:** random genomes, uniform over each gene's range.
- **Each later generation:**
  1. Evaluate every genome's fitness on **train** (D).
  2. Genomes with fewer than 30 train trades are discarded outright, whatever their return (this is
     inside the loop too, not only at the final gate).
  3. The top 15 by train fitness are evaluated once more on **validation**. The top 8 of those by
     validation fitness survive to reproduce.
  4. The next generation: the 8 survivors carried over unchanged (elitism), plus 52 children made by
     picking two survivors at random, averaging their continuous genes, taking a random parent's
     categorical genes, then applying Gaussian mutation (10% of children get one gene randomly
     reset; every child's continuous genes get +/- 5% Gaussian noise).
- **Fitness:** mean return after fees, with a linear penalty below 30 trades (fitness = 0 under 30
  trades) so the search can't reward a strategy for barely trading.

## D. Selection uses train + validation only

No genome, at any generation, is ever evaluated on the holdout window. The code path that can see
holdout dates is only reachable from `run_ga.py`'s final step (F), not from the generation loop.

## E. Random-search control

The identical budget (2,400 genomes), drawn uniformly at random with no selection, mutation, or
elitism - i.e., generation 0's process repeated 40 times with no evolution. Same gates, same
holdout look. This answers: did evolution find something selection alone wouldn't have, or would
2,400 random tries have done just as well?

## F. Final holdout test (touched once)

- **Finalists:** the single best genome by validation fitness at the end of generation 40, from
  both the evolved run and the random-search control (2 finalists total, fixed in advance).
- Each finalist trades the holdout window once, at the same fee.
- **Shuffled-label luck yardstick**, matching `PREREG_NN.md` G: the same finalist's entry signals
  on the holdout window, but exits paired to a randomly chosen *other* signal's outcome instead of
  its own (200 draws, seed 20260915) - severs the strategy's specific logic from its trade outcomes
  while keeping the same trade count and cadence.

## G. Gates (holdout window only, decided now)

- **G1:** at least 20 trades on the holdout window (3 months, so a lower bar than NN's full year).
- **G2:** mean return after fees > 0.
- **G3:** beats the shuffled-label control's 95th percentile.
- **G4:** beats a Bonferroni-corrected significance bar: the one-sided binomial win-rate test from
  `PREREG_NN.md` F, but at p < 0.05 / 2,400 (the trial budget) instead of p < 0.05, since this
  finalist was picked as the best of 2,400 tries, not tested on its own.

**PASS** = G1-G4 all hold, for either finalist independently.

## H. Integrity (must pass before any result counts)

- `leakage.truncation_test` on a fixed genome's decision function: deleting future data must never
  change a past decision. lag = 0.
- Ten synthetic random-walk series (same setup as `PREREG_NN.md` H, 2-month holdout windows): the
  full generation-40 loop must not produce a G1-G4 PASS on more than 1 of 10 pure-noise runs.
- **No-leakage-through-selection check:** confirm by code inspection and a unit test that
  `holdout_start` is never passed to the fitness or selection functions, only to the final-test
  function.

If any check fails, there is no verdict.

---

## I. Limitations, stated in advance

- One symbol, one data source, one genome design. A different search space might do better or
  worse - this doesn't search over search spaces, which would just recreate the same problem one
  level up.
- 2,400 evaluations is a real but bounded budget. "Not found in 2,400 tries" isn't "impossible in
  any search."
- The 3-month holdout is shorter than NN's full year, because it has to be carved out of the same
  2-year dataset alongside a train/validation split large enough to actually run a 40-generation
  search. A shorter holdout means less power to detect a real but modest edge.
- Fills are one-bar-late on stops/targets (conservative, not exact intrabar), same simplification
  as every other bar-close-driven test in this project.

**Registry rows:** GA-EVOLVED (the evolved finalist), GA-RANDOM (the random-search control
finalist).

---

## Amendments

- **2026-09-16, before any holdout result was trusted:** Section F's shuffled-label control as
  originally written ("exits paired to a randomly chosen other signal's outcome") was implemented
  as a permutation of the finalist's own trade returns. A permutation of a fixed list of numbers
  cannot change its mean - so the control's 95th percentile was mathematically guaranteed to equal
  the real result exactly, making G3 unable to ever fail or pass meaningfully. A first full run
  surfaced this (both finalists' `shuffled_p95` was byte-identical to their real mean). Replaced
  with the random-entry-timing control already established in `PREREG_SEARCH.md` (same trade count
  and side mix, entered at uniformly random times in the holdout window instead of the genome's
  actual signals, then run through the same stop/target/max-hold exit rule) - genuine independent
  randomness, not a same-set reshuffle. The full run was repeated after this fix; only the F/G3
  mechanism changed, nothing about the genome search, data, or other gates.
