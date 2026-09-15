# Pre-Registration: Phase 4, three untested survivorship-free ideas (H31–H33)

**Frozen:** 2026-09-12, before any Phase-4 return, signal or placebo was computed. Only data
availability was checked:
- Yahoo adjusted daily bars: SPY from 1993-01, DIA 1998, QQQ 1999, IWM 2000, EFA 2001-08, IEF
  2002-07, AGG 2003-09
- scheduled FOMC statement dates from `sources.fomc_statement_dates(1994)`

**Integrity:** `run_phase4.py` prints this file's SHA-256. Changes go in a dated *Amendments* section.

---

## Why these three

After the user said "keep going", the requirements for the next round were:
- not already tested in this project (see `REGISTRY.csv`)
- free, survivorship-free data (ETFs and a published calendar)
- implementable by a retail account
- at least ~10 years after the idea was first circulated

Each hypothesis:
- **H31, dual momentum** (Antonacci, SSRN 2012; book 2014). Probably the most widely followed
  retail rotation strategy. It is tested as a portfolio-level switch between asset classes.
  - Not a duplicate: the legacy `abs_momentum_252` was single-instrument, and TSMOM was
    diversified futures.
- **H32, Halloween / "Sell in May"** (Bouman & Jacobsen, *AER* 2002). A calendar rule on SPY.
  Phase 1 tested turn-of-month and pre-FOMC, not this.
- **H33, the FOMC cycle's even weeks** (Cieslak, Morse & Vissing-Jorgensen, *JF* 2019, circulated
  earlier). Stock returns are concentrated in weeks 0, 2, 4 and 6 of FOMC cycle time. Its week 0
  overlaps Phase 1's pre-FOMC drift (H04), so a weeks-2/4/6-only neighbour is required.

**Priors: low.** Published calendar and momentum effects have mostly decayed in this program's
earlier tests.

---

## A. Conventions

- **Accounting:** Phase 1's engine and accounting, excess of cash (`^IRX`), on Yahoo split- and
  dividend-adjusted bars.
- **Costs:** per side, 1 bp for SPY, QQQ and DIA; 2 bp for other ETFs (`h_calendar.cost_of`).
  G4 doubles them.
- **Execution:**
  - Calendar rules (H32, H33) use close execution: the calendar is public in advance.
  - H31 uses closing prices, so it trades at the next open (`engine.next_open_exec`).
- **Month end:** the last SPY session of a complete calendar month.

---

## B. Hypotheses

### H31: Dual momentum (GEM)

- **Decision:** at each month-end close t, compute 12-month total returns from the month end 12
  months earlier:
  - R_SPY and R_EFA for the two equity ETFs
  - the T-bill hurdle: compounded daily `^IRX` over the same sessions
- **Rule:** the winner is SPY if R_SPY ≥ R_EFA, else EFA. Hold the winner if its return beats the
  T-bill hurdle; otherwise hold AGG. The fill is at the next open; the position is held until the
  next fill.
- **Sample:** the first decision needs 12 month-ends of AGG. The series starts 2004-10-01.
- **Out-of-sample:** 2013-01-01 onward.
- **Neighbours (4):** a 6-month lookback; a 9-month lookback; IEF instead of AGG; a hurdle of 0%
  instead of T-bills.
- **Placebo (G7):** the out-of-sample monthly holdings, randomly permuted across the same months,
  so each asset's share is kept. 1,000 draws.

### H32: Halloween / "Sell in May"

- **Rule:** hold SPY from the close of the last October session to the close of the last April
  session. Cash from May to October.
- **Out-of-sample:** 2003-01-01 onward (published December 2002). The series starts 1993-02-01.
- **Neighbours (4):** IWM, DIA, QQQ and EFA, each with the same rule.
- **Placebo (G7):** in each year's cycle (last October session to the next last October session),
  hold one contiguous block. The block has the same number of sessions as that year's real
  November–April window and starts at a random session such that it fits inside the cycle.
  1,000 draws.

### H33: FOMC cycle, even weeks

- **Cycle time:** cycle day k of trading day t is t minus the most recent scheduled statement day
  e with e ≤ t + 1. The day before a statement is day −1 of its cycle.
- **Even-week days:** k ∈ {−1…3, 9…13, 19…23, 29…33}.
- **Rule:** hold SPY for the close-to-close return of every even-week day; cash otherwise.
- **Out-of-sample:** 2016-01-01 onward, conservatively after the working paper circulated.
  The series starts 1994-02-01.
- **Neighbours (4):** weeks 2/4/6 only (days 9–13, 19–23, 29–33, removing the H04 overlap); QQQ;
  IWM; DIA.
- **Placebo (G7):** every statement date moves independently by a random offset of 3–15 sessions,
  either direction. The even weeks are rebuilt from the moved dates. 1,000 draws.

---

## C. Gates

G1–G10 exactly as in Phases 1–2, with these specifics:

- **G2:** SPY excess for all three.
- **G3:** N = **104**. That is 76 legacy + 17 Phase-1 clusters + 4 Phase-2 + 3 intraday + TERM
  (H20) + these 3. σ_SR = max(Phase-1 dispersion 0.289, stdev of the three out-of-sample Sharpes).
  Sensitivity, not gated: N = 3 and N = 200.
- **G8:** PASS (ETFs, long-only).
- **G9:** n/a.
- **G10:** PASS (no survivorship).
- **Look-ahead truncation:**
  - H31 recomputes decisions with every price and cash rate after the cut removed (lag 0).
  - H32 and H33 are calendar rules: the test is structurally satisfied and run anyway.
- **Classification:** as Phase 2. Only a PASS proceeds to a paper log.

**Registry rows:** P4-H31, P4-H32, P4-H33.

---

## D. Reported (never gated)

- **H31:** the share of out-of-sample months in each asset, and switches per year.
- **H32:** mean daily excess return, winter vs summer, before and after 2003.
- **H33:** mean daily excess return, even-week days vs other days, before and after 2016, and the
  share of days held.

---

## Amendments

(none)
