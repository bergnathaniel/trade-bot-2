# Pre-Registration: Phase 6, the last published calendar ideas (H38–H41)

**Frozen:** 2026-09-12, before any Phase-6 return, signal or placebo was computed.
- **Data availability, the only thing checked:** Yahoo adjusted daily bars with no zero or missing
  opens. SPY from 1993-01, MDY 1995-05, DIA 1998, QQQ 1999, IWM and IJR from 2000-05.
- **Integrity:** `run_phase6.py` prints this file's SHA-256. Changes go in a dated *Amendments*
  section.

---

## Why these four

The user said "keep going" after Phases 4 and 5 failed. These are the remaining published calendar
effects that meet all of these conditions:
- testable with free, survivorship-free data
- a retail account can trade them
- a clear rule and a long post-publication sample
- not already tested in this project

The four effects:
- **H38, Santa Claus rally.** Hirsch, *Stock Trader's Almanac*, 1972.
- **H39, weekend/Monday effect.** French 1980; Gibbons & Hess 1981.
- **H40, January small-cap effect.** Rozeff & Kinney 1976; Keim 1983.
- **H41, presidential cycle.** Hirsch 1968; Booth & Booth 2003.

**Priors: very low.** Every calendar effect tested in Phases 1, 4 and 5 decayed or reversed after
publication. H41 also has only about 5 post-publication cycles.

---

## A. Conventions

Exactly as in Phase 5:
- The engine books returns in excess of cash (`^IRX`) on adjusted bars.
- Costs per side: 1 bp for SPY, QQQ and DIA; 2 bp for other ETFs. G4 doubles them.
- All four are calendar rules, so they use close execution.
- "Session j held" means holding its close[j−1] → close[j] return.

---

## B. Hypotheses

### H38: Santa Claus rally

- **Rule:** hold SPY for the last 5 sessions of each December and the first 2 sessions of the
  following January. Cash otherwise.
- **Sample:** the whole SPY series, from 1993-02. All of it is after publication.
- **Neighbours (4):** QQQ; IWM; DIA; the last 5 December sessions only.
- **Placebo (G7):** 1,000 draws. For each year with a real window, hold one random contiguous
  7-session block from that calendar year. No session of the block may be within 10 sessions of a
  real window session.

### H39: Weekend / Monday effect

- **Rule:** hold SPY for every session's return **except the first session of each calendar week**.
  That session's return spans the weekend. After a Monday holiday, Tuesday is the first session.
- **Sample:** the whole SPY series. All of it is after publication.
- **Neighbours (4):** QQQ; IWM; DIA; skip only sessions that fall on an actual Monday.
- **Placebo (G7):** 1,000 draws. Each week, skip one randomly chosen session of that week instead,
  so the same number of sessions is skipped.

### H40: January small-cap effect

- **Rule:** hold IWM for every January session and SPY for every other session. The account is
  always fully invested.
- **Sample:** from 2001-01-01, the first full January of IWM. All of it is after publication.
- **G2 benchmark:** SPY. Does the January tilt add alpha over just holding SPY?
- **Neighbours (4):**
  - IJR (S&P 600) instead of IWM
  - MDY (S&P 400) instead of IWM
  - IWM for only the first 10 January sessions
  - turn of the year: IWM for the last 10 December sessions plus the first 10 January sessions
- **Placebo (G7):** 1,000 draws. Each year, IWM is held in a random calendar month other than
  January.

### H41: Presidential cycle

- **Rule:** hold SPY for every session in years 3 and 4 of each presidential term, calendar years
  with y mod 4 ∈ {3, 0}; for example 2023–2024. Cash in years 1 and 2 (y mod 4 ∈ {1, 2}).
- **Out-of-sample:** 2004-01-01 onward. The series starts 1993-02-01.
- **Neighbours (4):** QQQ; IWM; DIA; year 3 only.
- **Placebo (G7):** 1,000 draws.
  - A cycle is the four calendar years starting with a y mod 4 = 1 year.
  - In each cycle, hold one random contiguous block with the same number of sessions as that
    cycle's real years 3–4.
  - The block must fit inside the cycle. The last cycle is cut short by the data.

---

## C. Gates

G1–G10 as in Phases 1–5, with these specifics:

- **G2 benchmark:** SPY excess for all four.
- **G3 trial count:** N = **112**, which is 108 plus these 4. σ_SR = max(0.289, stdev of the four
  out-of-sample Sharpes). Sensitivity, not gated: N = 4 and N = 200.
- **G8, G9, G10:** G8 PASS; G9 n/a; G10 PASS.
- **Look-ahead:** truncation is structurally satisfied for calendar rules and run anyway.
- **Classification:** as in Phase 2. Only a PASS proceeds to a paper log.

**Registry rows:** P6-H38, P6-H39, P6-H40, P6-H41.

---

## D. Reported (never gated)

- **H38:** mean daily excess return in the window vs other days, 1993–2009 and 2010 on.
- **H39:** mean daily excess return of week-first sessions vs other sessions, 1993–2009 and 2010 on.
- **H40:** mean January IWM − SPY return per year, and the share of years it was positive, before
  2014 and 2014 on.
- **H41:** mean yearly SPY excess return in years 3–4 vs years 1–2, before 2004 and 2004 on.

---

## Amendments

(none)
