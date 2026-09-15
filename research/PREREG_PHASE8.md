# Pre-Registration: Phase 8, country momentum and G10 currency carry (H44–H45)

**Frozen:** 2026-09-12, before any Phase-8 return, signal or placebo was computed.
- **Data availability, the only thing checked:**
  - Yahoo adjusted daily bars for the 17 original iShares country ETFs, from 1996-03, with no zero
    or missing opens. EFA from 2001.
  - FRED H.10 daily exchange rates for 9 currencies, from 1971 (EUR from 1999) to 2026-09-04. Every
    month has a print within 5 days of its end.
  - FRED/OECD monthly 3-month interbank rates for 10 currencies. JPY starts 2002-04; EUR and GBP
    currently end 2026-01, the others 2026-05/06.
  - Yahoo DBV daily bars, 2008-01 → 2023-03.
- **Integrity:** `run_phase8.py` prints this file's SHA-256. Changes go in a dated *Amendments*
  section.

---

## Why these two

The user asked to "keep looking for more strategies and do whatever makes me the most money besides
buying and holding". Claude can't place trades or decide what to do with his money. It can keep
testing honestly.

**Selection rules:** well-documented published strategies that this project has never tested, can
be tested on free data with no survivorship bias, and a retail account can trade. The only carry
test so far was bitcoin's futures basis (L21), a different thing.

- **H44, country momentum.** Asness, Moskowitz & Pedersen, "Value and Momentum Everywhere" (2013);
  also Richards 1997 and Balvers & Wu 2006.
- **H45, G10 currency carry.** Lustig & Verdelhan 2007; Burnside, Eichenbaum & Rebelo 2008/2011;
  Koijen, Moskowitz, Pedersen & Vrugt 2018.

**Priors:**
- **H44: low.** Every momentum and calendar effect tested in Phases 1 and 4–6 decayed after
  publication.
- **H45: low.** Carry crashed in 2008 and is widely reported as weak since. Retail rollover spreads
  also take a bite.

---

## A. Conventions

- **Engine and accounting:** as in Phases 4–7, excess of cash.
  - H44 is a daily record on adjusted bars (`^IRX` cash).
  - H45 is a monthly record: long/short currency returns are already excess returns.
- **Costs:**
  - **H44:** 5 bp per side. That's above the usual 2 bp for "other ETFs", because several single-country
    ETFs trade with wide spreads. G4 doubles it.
  - **H45:** 3 bp per side per unit of turnover, plus a rollover markup of 0.5% a year per unit of
    currency notional. That markup is the extra US retail FX dealers charge on overnight financing,
    at the low end. G4 doubles both.
- **Execution:**
  - **H44** decides at the month-end close and fills at the next open.
  - **H45** forms positions at each month-end and holds them through the next month-end.

---

## B. Hypotheses

### H44: Country momentum rotation

- **Universe:** the 17 original iShares country ETFs of 1996, all still trading today: EWA, EWC,
  EWD, EWG, EWH, EWI, EWJ, EWK, EWL, EWM, EWN, EWO, EWP, EWQ, EWS, EWU, EWW.
- **Rule.** At each month-end close (the last SPY session of a complete month), rank all 17 by
  their "12-1" return: the close one month-end ago divided by the close twelve month-ends ago. The
  most recent month is skipped. Hold the top 4 at 25% each from the next open until the next
  decision. Ties break alphabetically.
- **Sample:** from 1997-04-01. Out-of-sample is 2014-01-01 onward, after the 2013 publication.
- **G2 benchmark: EW17**, a daily-rebalanced equal weight of the same 17 ETFs, excess of cash, no
  costs. Picking countries has to add alpha over owning all of them.
- **Neighbours (4):** top 3; top 5; 6-1 month momentum; 12-month momentum without the skipped month.
- **Placebo (G7).**
  - Each out-of-sample month, 4 of the 17 are chosen at random. 1,000 draws.
  - The statistic is the annualized Sharpe of monthly open-to-open holding returns, after costs and
    excess of cash. The real picks are computed the same way.
- **Look-ahead check:** truncation recomputes every decision with all closes after the cut removed.
  It is a real test, lag 0.

### H45: G10 currency carry

- **Currencies:** USD, EUR, JPY, GBP, CHF, CAD, AUD, NZD, SEK, NOK.
- **Spot:** FRED H.10 noon rates, turned into US dollars per unit. The month-end value is the last
  print in the calendar month. The latest calendar month is dropped as incomplete.
- **Rates.**
  - OECD 3-month interbank rate, a monthly average in % a year.
  - These are published with a lag, so a position formed at the end of month *m* uses the value for
    month *m*−2.
  - If that value is missing, the latest earlier value up to 12 months older is used.
  - A month with any of the 10 rates missing is skipped.
- **Rule.**
  - At each month-end, go long the 3 highest-rate currencies at 1/3 each, and short the 3
    lowest-rate at 1/3 each (gross exposure 2).
  - Each currency's return over the next month is its spot change against USD, plus (its rate −
    the US rate) ÷ 12, using the rates known at formation (covered interest parity). USD's own
    return is 0.
  - Ties break alphabetically.
- **Sample:** return months from 2002-07 (the first month-end with all 10 lagged rates is 2002-06).
  Out-of-sample is 2008-01 onward, after the 2007–2008 publications.
- **G2 benchmark:** MKT (French Mkt-RF). This tests whether carry is repackaged equity risk.
- **Neighbours (4):** top/bottom 2; top/bottom 4; long the top 3 only (against USD); rates lagged 1
  month.
- **Placebo (G7):** each out-of-sample month, 6 of the 10 currencies are chosen at random, 3 long and
  3 short. 1,000 draws. The statistic is the monthly Sharpe.
- **G9:** DBV (Invesco DB G10 Currency Harvest) ran this idea with futures and was liquidated. It is
  judged on its Yahoo history, 2008-01 → 2023-03, which is at least 4 years.
- **Look-ahead check.** Truncation keeps spot prints through the cut month and only rate values for
  months up to the cut − 2, the ones already published. A decision that used a rate before it was
  published would change. It is a real test, lag 0.

---

## C. Gates

G1–G10 as in Phases 1–7, with these specifics:

- **G3 trial count:** N = **116**, which is 114 plus these 2. σ_SR = max(0.289, stdev of the two
  out-of-sample Sharpes). Sensitivity, not gated: N = 2 and N = 200.
- **G8: PASS for both.** H45's gross leverage of 2 is disclosed; US retail FX accounts allow it.
- **G9:** H44 n/a; H45 judged on DBV's live alpha, as above.
- **G10:** PASS for both. ETFs and currencies have no delisting survivorship.
- **Classification:** as in Phase 2. Only a PASS proceeds to a paper log.

**Registry rows:** P8-H44, P8-H45.

---

## D. Reported (never gated)

- **H44:**
  - share of out-of-sample months each ETF was held
  - names changed per month
  - EFA's out-of-sample excess CAGR
- **H45:**
  - out-of-sample net excess CAGR without the rollover markup
  - average long-minus-short rate gap
  - share of months each currency was long or short
  - the three worst out-of-sample months

---

## Amendments

(none)
