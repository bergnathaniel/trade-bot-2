# Phase 2 Pre-Registration

**Frozen:** 2026-09-11, before any Phase-2 return series was computed.
**Integrity:** `run_phase2.py` prints this file's SHA-256 with every result. Never edit this
text after results exist. Changes go in a dated *Amendments* section with the reason and are
reported alongside the original spec. Choices not pinned down here are made conservatively
and logged per test under `unregistered`.

---

## Scope

Phase 2 takes the Tier-2 hypotheses from `PROGRAM.md` that free data can test out of sample.

| id | hypothesis | why it is testable now |
|---|---|---|
| H11 | Earnings-announcement return drift | SEC 8-K acceptance timestamps give exact information times |
| H12 | Standardized-unexpected-earnings drift | XBRL gives as-first-reported, split-consistent EPS |
| H13 | Opportunistic insider purchases | SEC insider data sets cover every Form 4 since 2006 |
| H14 | Treasury auction cycle | Public auction calendar plus bond ETFs; no survivorship problem |

Deferred, with reasons:
- **H15, month-end pension rebalancing:** published 2024–25, so under two years of
  out-of-sample data exist.
- **H16, intraday momentum:** free intraday bars reach back about two years, which gives no
  statistical power.
- **H17, 10-K "lazy prices":** full-text differencing of every 10-K is a larger build; it's
  next in line.
- **H18, dividend-month premium, and H19, index additions:** free event timestamps are weak and
  the stock universe is survivor-only.
- **H20–H22** (term-premium timing, gap fade, volume-spike reversal): low prior and prone to
  threshold mining; not worth the extra trials.

Phase 1's result (0 of 31, dominated by publication decay) lowers the prior for all four.

---

## A. Conventions

Phase 1 section A applies unless changed here.

| item | rule |
|---|---|
| Stock universe | Current S&P 500 ∪ S&P MidCap 400 constituents from Wikipedia, frozen at first fetch (2026-09-11); one ticker per CIK; CIK from the table, else SEC `company_tickers.json`; Yahoo symbol = ticker with `.` → `-` |
| Calendar | SPY trading days from 2003-01-02 |
| Eligibility | A stock is eligible from 252 sessions after its first Yahoo bar |
| Stock costs | 5 bp/side for S&P 500 names, 10 bp/side for S&P 400 names; ETFs 1 bp/side |
| Shorts | Single-stock short legs pay 0.30%/yr borrow; ETF shorts 0.50%/yr; no interest earned on short proceeds |
| Baskets | Equal-weighted calendar-time baskets (`basket.py`): buy at the open of the entry session, sell at the close of the exit session. Overlapping or back-to-back holdings in one name merge |
| Long/short | Long basket − short basket. On a day one leg is empty, it is replaced by the equal-weighted universe |
| Long-only | Long basket − equal-weighted universe (the no-signal control). G2 uses the long basket's excess return regressed on SPY's |
| Timestamps | SEC `acceptanceDateTime` is UTC and is converted to America/New_York. A time of exactly 00:00:00 ET is treated as date-only, after the close |
| Breakpoints | Percentile cut-offs come only from events whose signal was known before the event's entry session, within the previous 365 calendar days. With fewer than 250 such events, no trade |

---

## B. Gates

G1–G9 apply exactly as in Phase 1, with these specifics:

- **G2 benchmark:** SPY excess for H11–H13; IEF excess for H14.
- **G3:** N = 76 legacy + 17 Phase-1 clusters + 4 Phase-2 clusters = **97**.
  σ_SR = max(Phase-1 dispersion 0.289, stdev of the 8 Phase-2 base-config out-of-sample
  Sharpes). Sensitivity (not gated): N = 4 and N = 200.
- **G7 for H11 and H12 (event placebo).** Statistic: the out-of-sample mean 60-session
  abnormal return of long-side events minus short-side events (LS), or long-side events minus
  all labelled events (LO). An event's abnormal return is C(entry+59)/C(entry) − 1 minus the
  equal-weighted universe over the same closes. Placebo: the signal randomly permuted across the
  same out-of-sample events, each event keeping its own breakpoints, 1000 draws. Events whose
  window runs past the data are excluded.
- **G7 for H13.** The monthly-return Sharpe (gross; open of the month's first session to close
  of its last) of the base vs 1000 draws of the same number of random eligible stocks each
  month. For LS, the random long and short sets are disjoint.
- **G7 for H14.** Sharpe vs the random-date placebo below.
- **G9:** N/A for all four (no live fund mapped).
- **G10 (new), survivorship-free data.** Stock tests on today's index members FAIL G10. H14
  passes it.

**Classification:** FAIL if G1, G2 or G4 fails · else NI if G8 fails · else **WATCH-SB** if G10
fails (would need survivorship-free confirmation before any paper trading) · else WATCH if any
other gate fails · else PASS.

Base configs (8): H11-LS, H11-LO, H12-LS, H12-LO, H13-LS, H13-LO, H14-LO, H14-LS.
Clusters (4): PEAD-EAR, PEAD-SUE, INSIDER, AUCTION.

---

## C. Hypotheses

### H11 — Earnings-announcement return drift (Brandt, Kishore, Santa-Clara & Venkatachalam 2008)
- **Events:** original 8-K filings (amendments excluded) whose items include `2.02` or `12`;
  the first per company in any 45-calendar-day window.
- **Reaction session d0:**
  - If the acceptance date (ET) is not a trading day: the next session.
  - If it is a trading day and the filing was accepted before 16:00 ET: that session.
  - If accepted at or after 16:00 ET, or the time is date-only: the next session.
- **Signal (EAR):** C(d0+1)/C(d0−1) − 1, minus SPY's return over the same closes. Known at
  close d0+1.
- **Trade:** EAR ≥ 80th percentile → long; EAR ≤ 20th → short. Enter at the open of d0+2, exit
  at the close of d0+61 (60 sessions).
- **Out-of-sample:** ≥ 2009-01-01 (the paper circulated in 2008).
- **Neighbours (6):** EAR over one session, C(d0)/C(d0−1); hold 30 sessions; hold 120 sessions;
  deciles (10/90); S&P 500 names only; S&P 400 names only. Subset neighbours take breakpoints
  from the subset's own events.
- **G8:** LS FAIL (single-stock shorting); LO PASS.

### H12 — Standardized unexpected earnings drift (Bernard & Thomas 1989)
- **Data:** SEC XBRL `companyconcept`, us-gaap `EarningsPerShareDiluted`. For a 10-Q with no
  usable diluted pair, `EarningsPerShareBasic`.
- **Per original 10-Q:**
  - Current EPS: the fact in that filing with a duration of 80–100 days and the latest end date.
  - Comparative EPS: a fact in the **same filing**, duration 80–100 days, ending 350–380 days
    earlier (the one closest to 365).
  - ΔEPS = current − comparative. Both numbers come from one filing, so ΔEPS is as first
    reported and split-consistent.
- **SUE:** ΔEPS / stdev of the company's previous 6 ΔEPS (at least 4 required; skip if the
  stdev is 0).
- **Trade:** enter at the open of the first session strictly after the 10-Q's acceptance date
  (ET); exit at the close 60 sessions later. Quintiles as in H11.
- **Q4 is excluded:** 10-Ks don't consistently report the prior-year quarter.
- **Out-of-sample:** the full sample (XBRL starts in 2009; the paper was published in 1989).
- **Neighbours (6):** hold 30 sessions; hold 120 sessions; deciles; basic EPS only; S&P 500
  only; S&P 400 only.
- **G8:** LS FAIL; LO PASS.

### H13 — Opportunistic insider purchases (Cohen, Malloy & Pomorski 2012)
- **Data:** SEC Insider Transactions Data Sets, 2006Q1 on. Original Form 4s (DOCUMENT_TYPE `4`)
  by universe issuers; non-derivative open-market purchases (code `P`, acquired) and sales
  (code `S`, disposed). The information date is FILING_DATE (a date only). Joint filers each
  count.
- **Classification:** per (insider, issuer) pair for calendar year Y, using only trades filed
  before 1 January of Y. A pair that traded in each of Y−3, Y−2 and Y−1 is **routine** if some
  calendar month was traded in all three years, otherwise **opportunistic**. Any other pair is
  unclassified. The first classifiable year is 2009.
- **Signal month m:**
  - B = stocks with at least one opportunistic purchase filed in m.
  - S = stocks with at least one opportunistic sale filed in m.
  - A stock in both is dropped from both.
- **Trade:** hold every B name (long) and S name (short) for calendar month m+1, buying at the
  open of its first session and selling at the close of its last.
- **H13-LO:** the B basket vs the EW universe. **H13-LS:** B − S.
- **Out-of-sample:** ≥ 2012-01-01. The sample starts in February 2009.
- **Neighbours (6):**
  - all open-market purchases and sales, unclassified (holding from March 2006)
  - at least 2 distinct opportunistic insiders
  - hold 3 months
  - officers only (relationship contains "Officer")
  - S&P 500 only
  - S&P 400 only
- **G8:** LS FAIL; LO PASS.

### H14 — Treasury auction cycle (Lou, Yan & Zhang 2013)
- **Events:** auction dates of nominal 10-year notes before today, from fiscaldata.treasury.gov
  (security type Note, original term 10-Year, TIPS excluded, reopenings included). Dates that
  aren't IEF trading days are dropped.
- **H14-LO:** hold IEF from the close of the auction day for 5 sessions (returns of d+1..d+5);
  cash otherwise.
- **H14-LS:** the same, plus short IEF from the close of d−5 to the close of d (returns of
  d−4..d).
- **Mechanics:** overlapping windows add and are clipped to ±1. Orders execute at the close,
  since the calendar is published in advance. Costs 1 bp/side; ETF short borrow 0.50%/yr, with
  no interest on the proceeds.
- **Out-of-sample:** ≥ 2014-01-01 (published in the Review of Financial Studies, 2013). The
  sample starts in August 2002.
- **Benchmark (G2):** IEF excess.
- **Neighbours (4 each):** 3-session windows; 7-session windows; TLT around 30-year bond
  auctions; IEF around 7-year note auctions.
- **Placebo:** each auction moved to a random session in the same calendar month, at least 7
  sessions from any actual 10-year auction; 1000 draws.
- **G8:** PASS. **G10:** PASS.

---

## D. Reported for every base config (never gated)

Everything Phase 1 reports, plus:
- universe and data coverage
- events per year
- out-of-sample mean abnormal return by signal bucket
- average basket sizes
- the look-ahead truncation test; for H11–H13 it recomputes events and labels with every price
  and filing after the cut removed

## Amendments

### A1 (2026-09-11): price splices from bankruptcy relistings

**Found after the first full run** (`results/phase2.json`, `results/phase2_run.log`). H13-LS showed a
−301% day and a −171% maximum drawdown. No basket can produce either.

**Cause.**
- Yahoo's CHRD history (Oasis Petroleum, now Chord Energy) joins two different securities:
  - the bankrupt old shares, closing at $0.0729 on 2020-11-19
  - the new equity issued out of Chapter 11, closing at $18.84 on 2020-11-20
- That is a ×258 "gain" no holder ever earned.
- It entered the H13 short leg as a +300% basket day.
- It entered the equal-weighted universe control as about +30% that day, so it also distorts every
  long-only series and every long/short day where a leg is empty.

**Rule (mechanical).**
- A one-day close-to-close gain above +900% (×10) is a splice.
- Every earlier open and close of that symbol is multiplied by that day's close-to-close factor.
  Returns before the splice are unchanged, and the splice day earns about zero.
- Declines are never adjusted: bankruptcy losses are real.
- A scan of the whole panel before the rerun found exactly one bar that qualifies: CHRD, 2020-11-20.

**Reporting.**
- Both runs are reported: `results/phase2.json` (original) and `results/phase2_A1.json` (amended,
  via `run_phase2.py --A1`), with separate registry rows `P2-…` and `P2-…-A1`.
- The original stays on record. Because it contains an impossible return, the amended run is the
  one to read.
