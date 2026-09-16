# Pre-Registration: genetic-algorithm search, round 2, bigger budget (config family GA2)

**Frozen:** 2026-09-16, before any generation ran.
**Integrity:** `run_ga2.py` prints this file's SHA-256 with every result. Never edit this text after
results exist. Changes go in a dated *Amendments* section.

---

## Why this test

After `PREREG_GA.md` (2,400 genome evaluations, FAIL - see `GA_RESULTS.md`), the user asked for more
generations. Re-running a bigger search against the *same* holdout window would break the one
thing that made round 1 trustworthy: that window was meant to be looked at exactly once. Checking
it again after seeing round 1 fail turns "pre-registered test" into "keep re-testing against the
same answer key until something passes" - exactly what pre-registration exists to prevent.

So this is a genuinely new, separately pre-registered round: a bigger budget, on a **completely
disjoint block of history that round 1's evolution, selection, and holdout never touched at all**,
not a re-run against spent data. Same genome design, same gates, same entry-signal code
(`ga_engine.py`, unchanged) - only the data window and the budget are different, so this cleanly
answers "does more search effort find something round 1 didn't," not a different question.

**Prior: still low.** Round 1's population plateaued after about 5 generations and never found a
single genome with positive fitness even on its own training data, across the whole search space.
A bigger budget over the same five strategy families and gene ranges is unlikely to behave
differently - this round exists to check that honestly rather than assume it.

---

## A. Data

BTC-USD, Coinbase Exchange 5-minute candles (same source/pipeline as round 1), **2022-09-11 ->
2024-09-10** - a full 21+3-month block ending the day before round 1's data begins (2024-09-11).
Zero overlap, zero gap, entirely unseen by anything in round 1.

- **Evolution window:** 2022-09-11 -> 2024-06-10 (21 months).
  - **Train** (70%): 2022-09-11 -> 2024-01-29.
  - **Validation** (30%): 2024-01-30 -> 2024-06-10.
- **Holdout:** 2024-06-11 -> 2024-09-10 (3 months). Never used for fitness, selection, or mutation,
  at any generation. Looked at exactly once, after evolution stops.

## B. The genome

Unchanged from `PREREG_GA.md` B: the same nine genes, same five entry families (RSI mean-reversion,
moving-average cross, N-bar breakout, Bollinger mean-reversion, momentum), same ranges, same
0.25%-per-side cost, same entry/exit fill convention. Reuses `ga_engine.py` without modification -
the file's own integrity (the truncation test and the breakout indicator's verified causal offset)
carries over unchanged.

## C. Mutation and reproduction

- **Population:** 100 genomes per generation (up from 60).
- **Generations:** 100 (up from 40). **Total budget: 10,000 genome evaluations on train** (up from
  2,400) - about 4.2x round 1, a real increase, fixed and disclosed here rather than open-ended.
- Selection, elitism (top 8), reproduction and mutation rates: unchanged from `PREREG_GA.md` C.

## D. Selection uses train + validation only

Same rule as round 1: no genome at any generation is evaluated on the holdout window.

## E. Random-search control

Same mechanism as round 1 (`PREREG_GA.md` E), same new 10,000-evaluation budget, no selection or
mutation.

## F. Final holdout test (touched once)

Same mechanism as `PREREG_GA.md` F **as amended** (the random-entry-timing control, not a
same-set reshuffle - that fix is in the shared code, not re-derived here). Two finalists: the best
evolved genome and the best random-search genome by validation fitness after generation 100.

## G. Gates (holdout window only, decided now)

Same as `PREREG_GA.md` G, with the Bonferroni correction recalculated for the new budget: G4's
one-sided win-rate test needs p < 0.05 / 10,000 instead of p < 0.05 / 2,400 - a stricter bar,
because a bigger search gets more chances to clear any fixed one by luck alone.

**PASS** = G1-G4 all hold, for either finalist independently.

## H. Integrity (must pass before any result counts)

Same two checks as `PREREG_GA.md` H, run fresh on this round's data and budget:
- `leakage.truncation_test` on the breakout entry type's decision function.
- Ten synthetic random-walk series, 2-month holdout windows, each run through its own smaller
  search: must not clear G1-G4 on more than 1 of 10.

If either fails, there is no verdict.

---

## I. Limitations, stated in advance

Same as `PREREG_GA.md` I, plus: this is BTC's 2022-2024 period specifically, which includes the
2022 bear market and 2023-2024 recovery - a different regime mix than round 1's 2024-2026 window.
A result here doesn't transfer to round 1's period or vice versa; each stands on its own data.

**Registry rows:** GA2-EVOLVED, GA2-RANDOM.

---

## Amendments

(none)
