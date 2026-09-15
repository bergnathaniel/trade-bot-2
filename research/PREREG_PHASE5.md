# Pre-Registration: Phase 5, four more survivorship-free ideas (H34–H37)

**Frozen:** 2026-09-12, before any Phase-5 return, signal or placebo was computed. Only data
availability was checked. Yahoo adjusted daily bars, with no zero or missing opens: SPY from 1993,
EFA 2001, IEF/TLT 2002, VNQ 2004-09, DBC 2006-02, SSO 2006-06, UPRO 2009-06.
**Integrity:** `run_phase5.py` prints this file's SHA-256. Changes go in a dated *Amendments* section.

---

## Why these four

The user said "keep going" after Phase 4 failed. The selection rules are the same as in Phase 4:
- not already tested here
- free, survivorship-free data
- retail-implementable
- more than about 10 years after publication (H37 has 9.7)

The four ideas:
- **H34, pre-holiday effect** (Lakonishok & Smidt 1988; Ariel 1990). Phase 1 tested the same
  authors' turn-of-month effect, not this one.
- **H35, options-expiration week** (Stivers & Sun 2013).
- **H36, tactical asset allocation with a 10-month moving average** (Faber 2007). This is a
  portfolio of five asset classes, judged against **holding the same five assets**. That comparison
  is the no-signal control.
- **H37, trend-filtered leverage** (Gayed & Bilello 2016). It is not the same as the failed legacy
  `sma_50_200`, which was unlevered and single-instrument.

**Priors: low.** Every calendar and momentum effect in Phases 1 and 4 decayed after publication.

---

## A. Conventions

- **Engine and accounting:** exactly as in Phase 4: excess of cash (`^IRX`), adjusted bars.
- **Costs** per side: 1 bp for SPY, QQQ and DIA, 2 bp for other ETFs. G4 doubles them.
- **Execution:** calendar rules (H34, H35) use close execution. Price rules (H36, H37) decide at the
  close and fill at the next open.
- **Month end:** the last SPY session of a complete calendar month.

---

## B. Hypotheses

### H34: Pre-holiday effect

- **NYSE holidays by rule, 1993–2026:**
  - New Year's Day. If it falls on a Sunday, the holiday is Monday; a Saturday New Year's Day
    isn't observed.
  - MLK Day, the third Monday of January, from 1998.
  - Presidents Day, the third Monday of February.
  - Good Friday.
  - Memorial Day, the last Monday of May.
  - Juneteenth, from 2022.
  - Independence Day.
  - Labor Day, the first Monday of September.
  - Thanksgiving, the fourth Thursday of November.
  - Christmas.
  - Where the rule applies, a Saturday holiday moves to Friday and a Sunday holiday to Monday.
- **Unscheduled closures** (for example 2001-09-11 and Hurricane Sandy) are not holidays. Nobody
  knew about them in advance.
- **Rule:** hold SPY for the return of the last session before each weekday holiday. That is
  close[d−1] → close[d].
- **Sample:** the whole SPY series, 1993-02 onward. All of it is after publication.
- **Neighbours (4):** QQQ; IWM; DIA; the last two sessions before each holiday.
- **Placebo (G7):** each year, the same number of random sessions, at least 4 sessions from any
  pre-holiday day. 1,000 draws.
- **Reported check:** any rule holiday that SPY actually traded on. This should be none.

### H35: Options-expiration week

- **Rule:** hold SPY for the close-to-close returns of the sessions in the Monday–Friday calendar
  week containing each month's third Friday. Cash otherwise.
- **Out-of-sample:** 2014-01-01 onward. The series starts 1993-02-01.
- **Neighbours (4):** QQQ; IWM; DIA; only the Thursday and Friday of expiration week.
- **Placebo (G7):** each month's week moves by a random −2, −1, +1 or +2 weeks. 1,000 draws.

### H36: Faber tactical asset allocation, 5 ETFs (GTAA5)

- **Assets:** SPY, EFA, IEF, VNQ and DBC, at 20% each.
- **Rule:** at each month-end close, an asset is held next month if its adjusted close is above the
  mean of its last 10 month-end adjusted closes, current one included. Otherwise its 20% sits in
  cash. The fill is at the next open.
- **Sample:** the series starts 2006-12-01 (10 month-ends of DBC). Out-of-sample is 2008-01-01
  onward.
- **G2 benchmark: EW5**, a daily-rebalanced equal-weight holding of the same five ETFs, excess of
  cash, with no costs. Timing has to add alpha over simply owning them.
- **Neighbours (4):** an 8-month average; a 12-month average; SPY, EFA and IEF only at ⅓ each; TLT
  instead of IEF.
- **Placebo (G7):** each asset's out-of-sample monthly in/out decisions, randomly permuted across the
  same months, independently per asset. This keeps each asset's time in the market. 1,000 draws.

### H37: Trend-filtered 2× leverage

- **Rule:** at each close, if SPY's adjusted close is above its 200-session simple moving average
  (current close included), hold SSO (2× S&P 500) from the next open. Otherwise hold cash.
- **Sample:** the series starts 2006-07-01. Out-of-sample is 2017-01-01 onward (published 2016).
- **Neighbours (4):** a 150-session average; a 250-session average; IEF instead of cash below the
  average; UPRO (3×) instead of SSO.
- **Placebo (G7):** the whole daily in/out state series, circularly shifted by a random 63–1,260
  sessions. This keeps its persistence and time in the market. 1,000 draws.
- **Look-ahead check:** truncation recomputes the states with every close after the cut removed.
  It is a real test, lag 0.

---

## C. Gates

G1–G10 as in Phases 1–4, with these specifics:

- **G2:** SPY excess for H34, H35 and H37. EW5 for H36.
- **G3:** N = **108**. That is 76 legacy + 17 Phase-1 + 4 Phase-2 + 3 intraday + TERM + 3 Phase-4
  + these 4.
  - σ_SR = max(0.289, stdev of the four out-of-sample Sharpes).
  - Sensitivity, not gated: N = 4 and N = 200.
- **G8:** PASS for all.
- **G9:** n/a.
- **G10:** PASS for all.
- **Classification:** as in Phase 2. Only a PASS proceeds to a paper log.

**Registry rows:** P5-H34, P5-H35, P5-H36, P5-H37.

---

## D. Reported (never gated)

- **H34:** mean daily excess return on pre-holiday days vs other days, 1993–2009 and 2010 onward;
  any holidays SPY traded on.
- **H35:** mean daily excess return in expiration weeks vs other days, before and after 2014.
- **H36:** the share of out-of-sample months each asset was held.
- **H37:** the share of out-of-sample days in SSO, switches per year, and SSO buy-and-hold's
  out-of-sample Sharpe.

---

## Amendments

(none)
