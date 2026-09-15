# Pre-Registration: H20, bond term-premium timing (cluster TERM)

**Frozen:** 2026-09-11, before any H20 return or forecast was computed. Only data availability was
checked: FRED DGS10 and DGS5 from 1962, DGS2 from 1976, DTB3 from 1954; IEF and TLT from
2002-07-30.
**Integrity:** `run_h20.py` prints this file's SHA-256. Changes go in a dated *Amendments* section.

---

## Why this test

The user asked to keep searching until something works. After Phases 1–2, the intraday tests and
the 9,504-configuration search all failed, this is the last hypothesis in `PROGRAM.md` that meets
three conditions:
- it can be tested with free data;
- it is survivorship-free, so G10 can pass;
- it has decades of post-publication data.

The other free-data candidates are ruled out:
- **H15** (month-end pension rebalancing): under 2 years since publication.
- **H16** (intraday momentum): about 2 years of free intraday bars.
- **H17–H19**: stock universes built from today's index members, so they can't pass G10.
- **H21–H22**: folklore-level evidence with thresholds that invite mining.

**The idea.** When long-term yields sit far above bill rates, holding bond duration has earned
more. Fama & Bliss 1987 and Campbell & Shiller 1991 show this in-sample. Out of sample, the
evidence is mixed: Thornton & Valente (2012) find little economic value, while Gargano,
Pettenuzzo & Timmermann (2019) find some. **Prior: low.**

---

## A. Data

- **Yields:** FRED DGS10, DGS5, DGS2 and DTB3, in percent, daily.
- **Instruments:** Yahoo IEF (7–10 year Treasuries; the base instrument) and TLT (20+ year,
  neighbour only). Cash is the project's `^IRX` rate, as in every other test.
- **Decision day for month M:** the last IEF trading day of M. Before IEF existed (training data
  only), it is the last DGS10 date of M.
- **Information cut-off for month M:**
  - Each yield value is the latest one dated on or before the session **two** trading days before
    the decision day.
  - H.15 yields are released the next business day at about 16:15 ET. A value dated the day before
    the decision would not be public by that day's close, so it can't be used.

---

## B. Signal and trade

1. **Constructed monthly excess return** of a constant-maturity par bond, from month M−1's
   observation to month M's:
   - The bond pays a semiannual coupon equal to y₍M−1₎.
   - It is repriced at y₍M₎ with the maturity held fixed (10 years; no roll-down).
   - Accrued coupon y₍M−1₎/12 is added.
   - The bill rate DTB3₍M−1₎/12 is subtracted.
2. **Spread:** DGS10 − DTB3, from month M's observation.
3. **Forecast at M's decision day.** An expanding-window OLS of the excess return for month k on the
   spread at month k−1. It uses every pair whose month-k return was already known at M's decision,
   so k ≤ M, starting from 1962. At least 120 pairs are required. The forecast is a + b × spread₍M₎.
4. **Trade.** Close execution: the decision is held from the close of M's decision day to the close
   of M+1's.
   - **H20-LO:** hold IEF when the forecast > 0; otherwise hold cash.
   - **H20-LS:** long IEF when the forecast > 0; otherwise short IEF.
5. **Costs:**
   - 1 bp per side (2 bp for G4).
   - Shorts pay a 0.50%/yr borrow fee and earn no interest on the proceeds, as in H14.

- **Out-of-sample:** the whole IEF era, 2002-08-01 onward. That is entirely after publication
  (1987, 1991).
- **Neighbours (4 each, LO and LS):**
  - a 10-year minus 2-year spread
  - a 5-year minus 3-month spread with a constructed 5-year bond
  - TLT instead of IEF, with the same signal
  - a rolling 20-year training window instead of an expanding one

---

## C. Gates

G1–G10 exactly as in Phases 1–2, with these specifics:

- **G2 benchmark:** IEF excess. The timing has to add alpha over simply holding the bonds.
- **G3:** N = 101. That is 76 legacy + 17 Phase-1 clusters + 4 Phase-2 clusters + the 3 intraday
  clusters tested since (engine, sniper, search) + this one. σ_SR is Phase 1's dispersion, 0.289.
  Sensitivity, not gated: N = 1 and N = 200.
- **G7 (placebo):** the IEF-era monthly decisions, randomly permuted across the same months, so the
  share of months long (or short) is kept. 1,000 draws. The statistic is the out-of-sample Sharpe.
- **G8:** PASS (ETF; retail can short an ETF in a margin account).
- **G9:** n/a (no live fund mapped).
- **G10:** PASS (no survivorship).
- **Classification:** as in Phase 2. Only a PASS proceeds to a paper log.

---

## D. Reported (never gated)

- the share of months long
- the sign hit rate of the forecast against IEF's realized next-month excess return
- the correlation of constructed 10-year monthly excess returns with IEF's (a check on the
  construction)
- the slope b at each year end
- the latest spread and forecast
- the look-ahead truncation test, with every FRED value after the cut removed

**Registry rows:** P3-H20-LO, P3-H20-LS.

---

## Amendments

(none)
