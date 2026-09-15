# Phase 8 (country momentum and G10 currency carry): tested

**Date:** 2026-09-12 · **Rules frozen before any result:** `PREREG_PHASE8.md` (sha256 `550e63db…6a0e69`)
**Rerun:** `python3 research/run_phase8.py` (about 5 s with a warm cache)
**Verdict: FAIL.** 0 of 2 pass.

---

## In plain English

The user asked to keep looking for something that makes more money than buying and holding. These
are two of the best-known published strategies this project hadn't tried yet. Both were checked
before the run: they never used a price or interest rate before it existed, and a deliberately
planted look-ahead was caught.

### 1. Country momentum

Each month, own the 4 countries (out of 17 iShares single-country funds) whose stock markets rose
most over the past year.

- **It did no better than owning all 17 equally.** Since 2014: +4.0% a year over cash, against
  +4.9% for owning all 17. Both had the same worst drop, −41%.
- **Random picks did as well.** Choosing 4 countries at random each month matched it 46% of the
  time.
- **It fell just as hard in crashes:**

| crash | country momentum | all 17 equally |
|---|---|---|
| 2008 | −61% | −61% |
| 2020 | −34% | −35% |
| 2022 | −25% | −28% |

- **Every variation landed in the same place:** top 3, top 5, 6-month momentum, and no skipped
  month.

### 2. Currency carry

Each month, own the 3 currencies with the highest interest rates and bet against the 3 with the
lowest.

- **The interest gap was real,** 2.8% a year on average. But exchange-rate moves took almost all of
  it back.
- **Since 2008 it lost a little: −0.1% a year after costs.** Before trading costs it made +0.8%,
  about the same as with no broker financing markup at all.
- **It crashes when markets panic:**
  - −10.6% in October 2008.
  - −5.4% in January 2015, when the Swiss franc jumped about 20% in a day. The strategy was betting
    against the franc in every month since 2008.
- **It worked before it became famous.** Over 2002–2026 it averaged +1.7% a year, and that came
  from the years before 2008.
- **The only fund that ran this idea lost money.** DBV ran for 15 years, trailed the stock market
  by 3.2% a year, and shut down in 2023.

---

## Results (out of sample, after costs, excess of cash)

| | window | yearly over cash | Sharpe (95% CI) | benchmark, same window | alpha (t), beta | worst drop | failed gates |
|---|---|---|---|---|---|---|---|
| H44 country momentum | 2014 → 2026 (12.7y) | +4.0% | 0.31 (−0.18, 0.83) | EW17 +4.9%, SR 0.37 | −0.8%/yr (−0.53), 1.00 | −41% | G1, G2, G3, G7 |
| H45 G10 carry | 2008 → 2026 (18.7y) | −0.1% | 0.02 (−0.40, 0.46) | market +9.8%, SR 0.66 | −2.4%/yr (−1.40), 0.23 | −24% | G1–G7, G9 |

- **Deflated Sharpe (G3)** at N = 116: 0.06 and 0.00. 0.95 is needed.
- **Placebos (G7):** 46.0% of random country picks and 7.7% of random currency picks did at least as
  well.
- **H44 passed** double costs (G4), sub-periods (G5), neighbours (G6), implementability (G8),
  survivorship (G10), and the look-ahead truncation test.
- **H45 passed** only G8, G10 and the truncation test.
- **H45's live fund (G9):** DBV, 15.2 years, alpha −3.19% a year (t −1.52).
- **Where H45 put its money:**
  - **Long most often:** NZD 87% of months, NOK 73%, AUD 64%.
  - **Short most often:** CHF 100%, EUR 59%, SEK 57%, JPY 46%.

---

## Where the search stands

**Phases 4–8 have now tested 15 famous published strategies with free data. None passed.** Before
them came:
- Phase 1: 31 published anomalies
- Phase 2: 4 earnings and insider ideas
- H20: bond term-premium timing
- the intraday engine and sniper tests
- the 9,504-configuration search
- Live Arena's micro-cap and crypto basket tests, each confirmed on fresh stocks or coins

Nothing in the program has made more money than buying and holding without taking more risk.

**What's left that isn't re-searching the same data:**
- **Forward paper trading.** The future is the only data nobody has searched.
- **Paid data.** Options and futures history, or stock data that includes companies that went bust.

Descriptive of the past only. Not investment advice.

## Files

- `PREREG_PHASE8.md`, `h_phase8.py`, `run_phase8.py`
- `results/phase8.json`, `results/phase8_run.log`
- `REGISTRY.csv` rows P8-H44 and P8-H45
