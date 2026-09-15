# Phase 9 (crypto trend-following ensemble): tested

**Date:** 2026-09-14 · **Rules frozen before any result:** `PREREG_PHASE9.md` (sha256 `79a4c026…105600`)
**Rerun:** `python3 research/p9data.py` once (about 15 minutes of downloads), then `python3 research/run_phase9.py`
(about 40 s)
**Verdict: FAIL.** 0 of 2 pass.

---

## In plain English

The user asked Claude to look deep into the web for any other strategy worth pursuing. The search turned up one
well-documented strategy this project hadn't tested that also had a clean window since its publication:
**"Catching Crypto Trends"** (Zarattini, Pagani & Barbon, 2025).

- **The rule:** hold coins only while they break out to new highs, and size each one by how volatile it is.
- **The paper's result:** 30% a year from 2015 to March 2025, with a Sharpe of 1.58, after fees, beating bitcoin.
- **The test:** the paper's data ended in March 2025, so April 2025 to September 2026 is 17 months it never saw.
- **Checked before the run:** neither version used a price before it existed (the look-ahead truncation test
  passed), and on invented prices the code matched a slow, obvious version of the rules exactly.

### 1. The 20 most-traded coins

- **Since April 2025 it lost a little: −0.7% a year over cash after fees**, and +0.4% before fees.
- **The comparisons, same window:**
  - Bitcoin: −8.0% a year.
  - The same coins held equally with no trend rule: −18.8% a year.
- **It sidestepped most of the fall, but that isn't an edge.**
  - Its worst drop was −10%, against bitcoin's −54%. It got there mostly by sitting in cash: 6.5% of the account was
    invested on average.
  - Measured against bitcoin's risk, it added nothing: alpha −0.6% a year (t −0.16).
- **Its timing was no better than luck.** 20% of versions that held the same amounts at random times did at least as
  well.
- **Every variation lost too,** with Sharpe ratios of −0.08 to −0.15: 200% leverage, a 50% volatility target, the top
  10 coins, only the slower lookbacks, no volatility sizing, and a no-trade band. Taking more risk can't turn a
  negative Sharpe positive.
- **It looked better before publication.** From 2023 to March 2025 the same rules made +7.4% a year (Sharpe 0.94),
  already below the paper's 1.58 on Coinbase's coins. It then faded once the strategy was published, the pattern seen
  in almost every phase.

### 2. Bitcoin alone

- **Since April 2025: −2.9% a year over cash after fees** (Sharpe −0.23), with a worst drop of −17% against bitcoin's
  −54%.
- **From 2023 to March 2025:** +19.7% a year, Sharpe 1.14.
- **Random timing did as well** in 29% of tries.

---

## Results (out of sample, after costs, excess of cash)

| | window | yearly over cash | Sharpe (95% CI) | bitcoin, same window | alpha (t), beta | worst drop | failed gates |
|---|---|---|---|---|---|---|---|
| H46 top-20 trend ensemble | 2025-04 → 2026-09 (1.45y) | −0.7% | −0.12 (−1.89, 1.34) | −8.0%, SR 0.01 | −0.6%/yr (−0.16), 0.06 | −10% | G1, G2, G3, G4, G6, G7 |
| H47 bitcoin trend ensemble | 2025-04 → 2026-09 (1.45y) | −2.9% | −0.23 (−1.61, 1.28) | −8.0%, SR 0.01 | −2.5%/yr (−0.36), 0.15 | −17% | G1, G2, G3, G4, G6, G7 |

- **Deflated Sharpe (G3)** at N = 118: 0.15 and 0.12. 0.95 is needed.
- **At the paper's other fee levels:**
  - 0.10% per side: Sharpe 0.02 and −0.09.
  - 0.50% per side: −0.34 and −0.46.
- **Both passed:**
  - two of three sub-periods (G5);
  - implementability (G8);
  - survivorship-free data (G10), since delisted Coinbase pairs were included;
  - the look-ahead truncation test.
- **Most-held coins since April 2025** (share of days):
  - BTC 73%, ETH 71%, LINK 60%, SOL 60%, LTC 59%, XRP 57%.
  - 66 different coins were picked at some point.

---

## About the short window

The pre-registration warned that 1.45 years is too short for even a strategy that works as published to clear G1
and G2. That isn't why these failed:
- both results are below zero;
- every variation is below zero;
- random timing did as well.

The honest reading is "no sign of an edge since publication", not "unlucky in a short sample".

---

## Where the search stands

**The pre-registered program now stands at 118 trials, and nothing has passed.**
- The deep search found no other untested strategy with published after-cost evidence that free data can test cleanly.
- The rest is already covered here:
  - short volatility, the pre-FOMC drift, industry and time-series momentum, factor tilts, pairs, carry, and calendar
    effects;
  - more than 200 Live Arena bots.
- **What's left that isn't re-searching the same data:**
  - **Forward paper trading:** the Live Arena speed test and year-long paper tests now running.
  - **Paid data.**

Descriptive of the past only. Not investment advice.

## Files

- `PREREG_PHASE9.md`, `p9data.py`, `h_phase9.py`, `run_phase9.py`
- `results/phase9.json`, `results/phase9_run.log`
- `REGISTRY.csv` rows P9-H46 and P9-H47
- `data/coinbase_daily/`: daily candles for 487 Coinbase USD pairs, 2022-01 → 2026-09-12
