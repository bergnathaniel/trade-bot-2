# Pre-Registration: Phase 9, crypto trend-following ensemble (H46–H47)

**Frozen:** 2026-09-14 00:05 UTC, after the data-availability check below and before any Phase-9 return, signal or placebo
was computed.
- **Data availability, the only thing checked:**
  - All 487 USD pairs Coinbase lists, 85 of them delisted, returned daily candles. After the exclusions, 469 are usable.
  - BTC-USD has every day from 2022-01-01 to 2026-09-12, with no gaps.
  - At least 12 coins pass the liquidity rule at every month-end from 2023-01-31 on (median
    35, most 76).
  - At 2022-12-31 no coin has the year of history the rule needs yet, so H46 holds nothing in January 2023. That is
    in-sample only.
- **Integrity:** `run_phase9.py` prints this file's SHA-256. Changes go in a dated *Amendments* section.

---

## Why this one

On 2026-09-13 the user asked Claude to "look deep into the web and if there are any other strategies worth pursuing
then do them". Claude can't place trades or decide what to do with his money. It can keep testing honestly.

**What the search found:**
- Net of trading costs and post-publication decay, the average published stock anomaly earns about 4 bp a month, and
  the strongest about 10 bp (Chen & Velikov, JFQA 2023).
- Several remaining candidates were already tested here and failed:
  - short volatility (P1-H02, P1-H03);
  - the pre-FOMC drift (P1-H04), which also disappeared after 2015 (Kurov, Wolfe & Gilbert 2021);
  - industry momentum (P1-H10) and time-series momentum (L18).
- Two 2026 studies found that popular retail signal families and 14 intraday signal families on futures don't survive
  costs (arXiv 2607.20093, 2605.04004).

**Selection rules:** the same as Phase 8. The strategy has to be:
- well documented and published, and never tested in this project;
- testable on free data without survivorship bias;
- tradeable in a US retail account;
- able to leave a genuine out-of-sample window after its publication.

One candidate met all of them: Zarattini, Pagani & Barbon, "Catching Crypto Trends; A Tactical Approach for Bitcoin and
Altcoins" (SSRN 5209907, first posted 2025-04-08). The paper reports:
- a long-only ensemble of Donchian trend models with volatility-based sizing;
- on a rotational portfolio of the 20 most liquid coins, 2015 to mid-March 2025: CAGR 30%, Sharpe 1.58 and alpha over
  bitcoin of 10.8–14% a year, net of fees of 0.10–0.50%.

Its sample ended in mid-March 2025, so everything from 2025-04-01 on is out of sample.

**Where the rules come from:** the paper's PDF couldn't be retrieved (SSRN refused automated downloads). The rules
below follow CXO Advisory's summary of the paper and a public pre-registration of the same strategy (GitHub
zebadee2kk/DeFi-TraderStack-Agent issue #137). The two agree on lookbacks, entry, trailing stop, volatility target and
liquidity filter. Details neither states are fixed here by Claude and marked **(Claude's choice)**.

**Priors: low.**
- Crypto momentum was weak or failed in L09, L10 and L15.
- The Live Arena crypto basket searches found nothing.
- Published effects have usually decayed after publication in this project.

**Power, stated before any result:**
- The out-of-sample window is 2025-04-01 → 2026-09-12: 530 days, or 1.45 years.
- The standard error of an annualized Sharpe over 1.45 years is about 0.83. G1's 95% interval excludes zero only for an
  out-of-sample Sharpe of roughly 1.65 or more, and the block bootstrap is usually wider.
- G2 needs alpha over bitcoin with t ≥ 2 in the same short window.

So even a strategy that works exactly as published would probably FAIL G1 or G2 here. A FAIL means "not shown in
1.45 years", not "shown not to work". What this test can show is whether the record since publication resembles the
paper's.

---

## A. Conventions

- **Data:**
  - Coinbase Exchange daily candles (UTC days) for every USD pair Coinbase lists, including 85 delisted ones, from
    2022-01-01 through 2026-09-12, the last complete day (`p9data.py`).
  - ^IRX for cash.
  - A day without trades keeps the last close. A pair counts as not trading before its first candle and after its last.
- **Excluded from the universe (Claude's choice):** stablecoins, tokenized gold, and wrapped or staked copies of other
  coins. The list is in `h_phase9.EXCLUDED`. They aren't separate bets on a trend.
- **Calendar and execution:**
  - Every UTC day; Sharpe and CAGR use a 365-day year.
  - Weights decided at a day's close earn the next day's close-to-close return. Crypto trades around the clock, so the
    next day's open is the same as this close.
- **Cash:** ^IRX, the annualized %, forward-filled across every calendar day and divided by 365. Returns are excess of
  cash: Σ w · (coin return − cash) − costs.
- **Costs:**
  - 0.25% per side on every change in target weight (the paper's middle scenario). Drift between days is ignored, as in
    earlier phases.
  - G4 doubles it to 0.50%, the paper's highest.
  - A coin that stops trading while held earns nothing more and is sold at its last close.
- **Record:** 2023-01-01 → 2026-09-12. The first year of data only warms up the 360-day models and the one-year
  listing rule.
  - Before 2025-04-01 is in-sample and reported as a replication check.
  - 2025-04-01 onward is out of sample and gated.

---

## B. Hypotheses

### H46: rotational top-20 ensemble

- **Universe (monthly, Claude's choice of month-end timing).** At each UTC month-end close, a pair is eligible if all of
  these hold:
  1. it had a close 365 days earlier (at least a year of history);
  2. it traded in the last 3 days;
  3. its median daily dollar volume (close × volume, 0 on days without trades) over the last 30 days is at least $2M.

  The 20 eligible pairs with the highest median dollar volume are held through the next month-end. Ties break
  alphabetically.
- **Signals, for each coin and each lookback L in {5, 10, 20, 30, 60, 90, 150, 250, 360} days:**
  - **Entry:** go long at a close above the highest of the previous L closes.
  - **Stop:** starts at the midpoint of the highest and lowest of the last L closes, including today. Each day it rises
    to that day's midpoint if higher, and never falls.
  - **Exit:** a close below the previous day's stop.
  - **Timing:** exiting and entering on the same day isn't possible. A model needs L earlier closes before it can act.
- **Ensemble:** the coin's signal is the share of the 9 models that are long, from 0 to 1. Models not yet able to act
  count as flat.
- **Sizing:**
  - A coin's weight = signal × min(2, 25% ÷ its annualized volatility) ÷ 20, where volatility is the standard deviation
    of its last 90 daily returns.
  - No weight until 90 returns exist.
  - The 2× cap and 25% target are the paper's.
  - The 1/20 slots are Claude's choice.
- **Gross cap (Claude's choice, for G8):** if the weights add up to more than 100% of the account, all are scaled down
  to 100%. Coinbase spot accounts can't borrow. The paper's 200% is a neighbour.
- **G2 benchmark:** bitcoin held, excess of cash, no costs. The paper reports alpha against bitcoin.
- **Neighbours (6):**
  1. gross up to 200%;
  2. a 50% volatility target;
  3. the top 10 coins (1/10 slots);
  4. lookbacks 20–360 only;
  5. no volatility sizing (weight = signal ÷ 20);
  6. a 10% no-trade band, where a held weight within 10% of its new target isn't traded.
- **Placebo (G7):**
  - 1,000 draws. In each draw, every coin's signal series over the out-of-sample window is slid circularly by its own
    random offset of 30 to 500 days.
  - This keeps how often and how much each coin is held, and moves only when.
  - Universe, volatility and costs are unchanged.
  - The statistic is the out-of-sample Sharpe after costs. The real book has to beat the 95th percentile.
- **Look-ahead check:** truncation. Every weight is recomputed with all data after the cut removed. It is a real test,
  lag 0.

### H47: bitcoin alone

- **Universe:** BTC-USD only.
- **Signals and ensemble:** as H46.
- **Weight:** signal × min(2, 25% ÷ volatility), capped at 100% of the account.
- **G2 benchmark:** bitcoin held, excess of cash.
- **Neighbours (5):**
  1. cap 200%;
  2. a 50% volatility target;
  3. lookbacks 20–360 only;
  4. no volatility sizing (weight = signal);
  5. a 10% no-trade band.
- **Placebo and look-ahead check:** as H46, on bitcoin's signal alone.

---

## C. Gates

G1–G10 as in Phases 1–8, with these specifics:

- **Periods:** 365 a year. The block bootstrap uses 21-day blocks.
- **G3 trial count:** N = **118**, which is 116 plus these 2. σ_SR = max(the Phase-1 dispersion, the stdev of the two
  out-of-sample Sharpes). Sensitivity, not gated: N = 2 and N = 200.
- **G8: PASS for both** at the 100% cap. The 200% neighbours are disclosed as not implementable on Coinbase spot.
- **G9:** n/a. No live fund has run this exact rule for 4 or more years.
- **G10: PASS for both.** Delisted Coinbase pairs are included. Coins never listed on Coinbase are a venue limit, not
  survivorship.
- **Classification:** as in Phase 2. Only a PASS proceeds to a paper log.

**Registry rows:** P9-H46, P9-H47.

---

## D. Reported (never gated)

- In-sample (2023-01-01 → 2025-03-31) excess CAGR and Sharpe, next to the paper's Sharpe of 1.58.
- Out-of-sample Sharpe at 0.10% and 0.50% costs, the paper's other scenarios.
- Average gross exposure and the share of out-of-sample days with any position.
- For H46:
  - the coins held most often;
  - how many different coins were picked;
  - an equal-weight, no-signal control that holds the same monthly picks with no costs.
- Bitcoin's out-of-sample excess CAGR and Sharpe.

---

## Amendments

(none)
