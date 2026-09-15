# Phase 6 (Santa Claus rally, weekend effect, January small caps, presidential cycle): tested

**Date:** 2026-09-12 · **Rules frozen before any result:** `PREREG_PHASE6.md` (sha256 `e3c3ceb0…3f271`)
**Rerun:** `python3 research/run_phase6.py` (about 90 s)
**Verdict: FAIL.** 0 of 4 pass.

---

## In plain English

These are the last published calendar effects that free, survivorship-free data can test. Every
one of them looked real before it was published and faded or reversed afterwards.

**1. Santa Claus rally** (1972). Hold stocks for the last 5 trading days of December and the first
2 of January.
- **1993–2009:** those days earned **14.9** basis points a day, against 2.0 on other days.
- **Since 2010:** **6.3** against 5.3. The effect has mostly faded.
- **The strategy:** +0.7% a year, with the money out of the market 97% of the time. Random 7-day
  blocks did as well 12% of the time.

**2. The Monday / weekend effect** (1980). Skip each week's first trading day, which was supposed
to be the bad one.
- **In this data it wasn't bad.** Week-first days earned 3.6 basis points a day in 1993–2009,
  against 2.0 for other days. Since 2010 it's 4.5 against 5.5.
- **The strategy:** +5.2% a year, against +8.1% for just holding the S&P 500.
- **Random skips:** skipping a random day each week did as well 46% of the time.

**3. January small caps** (1976–83). Hold small-company stocks in January and the S&P 500 the rest
of the year.
- **It ended up exactly equal to the S&P 500:** +7.1% a year for both, with an alpha of +0.01%.
- **Small caps over the S&P 500 in January:** +0.6% a year in 2001–2013, then −0.3% since 2014.

**4. The presidential cycle** (1968; 2003). Hold stocks in years 3–4 of each term and sit in cash
in years 1–2.
- **1993–2003:** years 3–4 earned 14.8% a year, against 2.4% in years 1–2.
- **Since 2004 it flipped:** 8.0% against 12.1%.
- **The strategy:** +3.1% a year, against +9.0% for the S&P 500.

---

## Results (out of sample, after costs, excess of cash)

| | window | yearly over cash | Sharpe (95% CI) | S&P 500, same window | alpha vs SPY (t), beta | worst drop | failed gates |
|---|---|---|---|---|---|---|---|
| H38 Santa Claus | 1993 → 2026 (33.6y) | +0.7% | 0.27 (−0.04, 0.54) | +8.1%, SR 0.51 | +0.5%/yr (1.31), 0.02 | −7% | G1, G2, G3, G7 |
| H39 skip week's first session | 1993 → 2026 (33.6y) | +5.2% | 0.40 (0.09, 0.71) | +8.1%, SR 0.51 | −0.8%/yr (−0.56), 0.75 | −56% | G2, G3, G7 |
| H40 IWM in January | 2001 → 2026 (25.6y) | +7.1% | 0.45 (0.12, 0.85) | +7.1%, SR 0.46 | +0.0%/yr (0.02), 1.01 | −57% | G2, G3, G7 |
| H41 presidential years 3–4 | 2004 → 2026 (22.7y) | +3.1% | 0.28 (−0.05, 0.67) | +9.0%, SR 0.55 | −2.2%/yr (−1.21), 0.61 | −52% | G1, G2, G3, G7 |

- **Deflated Sharpe (G3)** at N = 112: 0.00, 0.02, 0.07 and 0.01. 0.95 is needed.
- **Placebos (G7):** 12.3%, 45.7%, 41.7% and 74.6% of random versions did at least as well.
- **Passed by all four:** double costs (G4), 2 of 3 sub-periods (G5), neighbours (G6),
  implementability (G8), survivorship (G10), and the look-ahead truncation test.

---

## Where the search stands

Phases 4–6 tested 11 famous published retail strategies and calendar effects. They are every one
this project could find that has free, survivorship-free data and a long post-publication record.
**None passed.** Before them came:
- Phase 1: 31 published anomalies
- Phase 2: earnings drift, earnings surprise, insider buying, the Treasury auction cycle
- H20: bond term-premium timing
- the intraday engine and sniper tests
- a 9,504-configuration search

Nothing in the whole program has passed.

Continuing on free data would mean inventing unpublished rules and testing them on data that has
now been searched from every angle. That is data mining: eventually something passes by luck and
then fails with real money.

**The only real next steps are decisions, not more rounds:**
- **Buy better data.** Stock data that includes companies that went bust, or futures and options
  history, would open ideas that can't be tested honestly now.
- **Forward-test your own trading calls.** The Beat the Coin journal records calls before the price
  moves, so they can be checked against a coin flip.
- **Stop searching for an edge.**

## Files

- `PREREG_PHASE6.md`, `h_phase6.py`, `run_phase6.py`
- `results/phase6.json`, `results/phase6_run.log`
- `REGISTRY.csv` rows P6-H38 to P6-H41
