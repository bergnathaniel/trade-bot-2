# Genetic-algorithm search, round 2 (bigger budget, disjoint data): tested

**Date:** 2026-09-16 · **Rules frozen before any result:** `PREREG_GA2.md` (sha256 printed with
every result by `run_ga2.py`)
**Rerun:** `python3 research/run_ga2.py` (about 3 min; the 2022-09-11 → 2024-09-10 1-minute BTC-USD
data was fetched fresh for this round, ~19 minutes, cached under `research/.cache/intraday/`)
**Verdict: FAIL**, for both finalists - but a more instructive failure than round 1's.

---

## In plain English

**What was asked.** After round 1 (`GA_RESULTS.md`, FAIL, 2,400 evaluations), the user asked for
more generations. Running a bigger search against the *same* holdout would have broken the "touched
once" rule that made round 1 trustworthy, so this is a separately pre-registered round instead: 4.2x
the budget (10,000 evaluations vs. 2,400), on a completely disjoint block of BTC history
(2022-09-11 → 2024-09-10) that round 1 never touched - ending the day before round 1's data begins,
zero overlap.

**Result.**
- **Both finalists failed on the untouched holdout** - evolved: −0.48% mean over 29 trades;
  random-search: −0.17% over 17 trades (which also fails the minimum-trade gate outright).
- **But this time the search did find things that looked genuinely good** during evolution: 1 of
  1,500 logged top candidates had positive fitness on train (round 1: 0 of 600), and the population
  climbed steadily from −0.15% fitness at generation 0 to +0.23% by generation 90 - real,
  gradual improvement, not noise. The winning genome (RSI mean-reversion, short-only, wide stop and
  target) had positive fitness on *both* train and validation.
- **All of that improvement evaporated on the holdout.** The genome that looked like a genuine
  discovery through 100 generations of selection went from +0.23% (validation) to −0.48% (holdout)
  the moment it hit data the search had never influenced its own selection against. That's the
  textbook shape of overfitting through repeated selection: validation data gets "seen" a little
  more with every generation that selects against it, even though no single genome trains on it
  directly, and 100 generations is enough exposure for the search to start fitting its noise.
- **The search converged on a different family this round** - 1,380 of 1,500 top candidates were
  RSI mean-reversion (round 1: moving-average crossover dominated). Consistent with the round using
  a different market regime (2022's bear market into 2023-2024's recovery, vs. round 1's 2024-2026
  window) - a different "least bad" answer for different data, not a more reliable one.

**Why this is a better lesson than round 1, not a worse result.** Round 1 never even convinced
itself - nothing beat break-even on the data it was fit to. Round 2 *did* convince itself, cleanly
and gradually, right up until the one look at data it hadn't touched. That is exactly the failure
mode pre-registration and held-out data exist to catch, and it's a more concrete demonstration of
why "it looked good during the search" was never going to be enough of a bar on its own.

**What happens next.** Two independently-run, disjoint-data rounds of the same search design now
agree there's nothing durable here. A third round wouldn't test a new question - it would just be
asking the same one a third time. This closes the genetic-algorithm search.

---

## Results

| | Genome | Holdout trades | Holdout mean | Validation fitness | Random-timing 95th pct |
|---|---|---:|---:|---:|---:|
| Evolved finalist | rsi_meanrev, short-only, trend+volume filters | 29 | −0.484% | +0.234% | +0.029% |
| Random-search finalist | momentum, long-only, volume filter | 17 | −0.166% | +0.432% | +0.409% |

## Gates (holdout window only)

| Gate | Needs | Evolved | Random-search |
|---|---|---|---|
| G1 | ≥ 20 trades | 29 ✓ | 17 ✗ |
| G2 | mean after fees > 0 | −0.48% ✗ | −0.17% ✗ |
| G3 | beats random-timing 95th pct | −0.48% vs +0.03% ✗ | −0.17% vs +0.41% ✗ |
| G4 | win rate > 50%, p < 0.05/10,000 (Bonferroni) | 41.4%, fails on win rate alone ✗ | 52.9%, p=1.0 ✗ |

**PASS** needs G1-G4. Result for both: **FAIL**.

## Integrity

- **Look-ahead (truncation) test:** pass, same mechanism as round 1, run fresh on this round's data.
- **Synthetic random-walk sanity check:** 0 of 10 pure-noise series cleared G1-G4. Pass.
- **Shuffled-control sanity check:** confirmed `shuffled_p95` differs from the real mean for both
  finalists (0.00029 vs −0.00484, and 0.00409 vs −0.00166) - the round-1 degenerate-control bug did
  not resurface.

## Files

- `PREREG_GA2.md`: the frozen rules for this round
- `run_ga2.py` (reuses `ga_engine.py` and `run_ga.py`'s search/control/test functions unchanged)
- `results/ga2.json`, `results/ga2_log.json` (all 3,000 logged candidates: 1,500 evolved, 1,500
  random-search, across 100 generations each)
