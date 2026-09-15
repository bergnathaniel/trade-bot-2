# Phase 5 (pre-holiday, options-expiration week, 10-month rotation, trend-filtered 2× leverage): tested

**Date:** 2026-09-12 · **Rules frozen before any result:** `PREREG_PHASE5.md` (sha256 `736674de…fdbf8`)
**Rerun:** `python3 research/run_phase5.py` (about 2 minutes)
**Verdict: FAIL.** 0 of 4 pass.

---

## In plain English

**1. Pre-holiday effect** (published 1988–90). Hold the S&P 500 only on the trading day before a
market holiday.
- The effect still exists. Since 2010 the pre-holiday day earned 12.5 basis points, against 5.0 on a
  normal day.
- But it happens only about 9 days a year. The strategy made **+0.6% a year**.
- Random days did as well 10% of the time, and passing needs 5% or less. The effect is real but
  small, and not clearly beyond luck.

**2. Options-expiration week** (2013). Hold only during the week monthly options expire.
- **It reversed after publication.** Since 2014, expiration-week days earned 1.7 basis points
  against 5.9 for other days.
- The strategy made **+0.4% a year**.

**3. The 10-month moving-average rotation** (Faber, 2007). US stocks, international stocks, bonds,
real estate and commodities, each held only while above its 10-month average.
- It made **+3.6% a year** over cash. Just holding the same five made **+5.0%**.
- **Its crashes were much smaller:** the worst drop was −16%, against −46%.
- After adjusting for being out of the market more often, its extra return was +1.8% a year. That is
  not significant (t 1.37). Randomly scrambled in/out months did as well 10% of the time.
- **It was smoother, not better.**

**4. Trend-filtered 2× leverage** (2016). Hold a 2× S&P 500 fund while the market is above its
200-day average, and cash otherwise.
- Since 2017 it made **+15.3% a year**, against **+12.5%** for the S&P 500.
- **That gain is leverage, not skill.**
  - Its return per unit of risk was 0.71, against the S&P 500's 0.74.
  - Simply holding the 2× fund the whole time got the same, 0.70.
  - Its worst drop was −36%, against −34%.
  - Randomly shifted in/out timelines did as well 15% of the time.
- **This is the kind of result that fools people.** The higher return came with more risk, and in a
  bad decade leverage cuts both ways.

**The pattern across Phases 4 and 5:**
- Timing rules often **soften crashes** but don't add return beyond luck.
- Leverage **adds return with matching risk**.
- Calendar effects mostly **faded or flipped** after they were published.

---

## Results (out of sample, after costs, excess of cash)

| | window | yearly over cash | Sharpe (95% CI) | benchmark, same window | alpha (t), beta | worst drop | failed gates |
|---|---|---|---|---|---|---|---|
| H34 pre-holiday | 1993 → 2026 (33.6y) | +0.6% | 0.24 (−0.09, 0.55) | SPY +8.1%, SR 0.51 | +0.4%/yr (0.96), 0.02 | −9% | G1, G2, G3, G7 |
| H35 options-expiration week | 2014 → 2026 (12.7y) | +0.4% | 0.10 (−0.39, 0.71) | SPY +11.6%, SR 0.73 | −1.9%/yr (−0.88), 0.21 | −33% | G1, G2, G3, G6, G7 |
| H36 10-month rotation (5 ETFs) | 2008 → 2026 (18.7y) | +3.6% | 0.48 (0.11, 0.89) | same 5 ETFs +5.0%, SR 0.40 | +1.8%/yr (1.37), 0.35 | −16% | G2, G3, G7 |
| H37 trend-filtered 2× | 2017 → 2026 (9.7y) | +15.3% | 0.71 (0.08, 1.33) | SPY +12.5%, SR 0.74 | +5.4%/yr (0.88), 0.88 | −36% | G2, G3, G7 |

- **Deflated Sharpe (G3)** at N = 108: 0.00, 0.01, 0.13 and 0.46, against 0.95 needed.
- **Placebos (G7):** the share that did at least as well was 9.6%, 84.7%, 10.1% and 15.0%.
- **Every look-ahead truncation test passed.** No rule-based NYSE holiday was a day SPY actually
  traded, so the holiday calendar is correct.
- **Neighbour Sharpes:**
  - H36: 8-month average 0.49, 12-month 0.52, SPY/EFA/IEF only 0.54, TLT for IEF 0.49.
  - H37: 150-day average 0.68, 250-day 0.61, IEF below the average 0.67, 3× (UPRO) 0.71.
- **H37 exposure:** 84% of days in the 2× fund, with 5.2 switches a year.
- **H36 months held (out of sample):** SPY 78%, EFA 67%, IEF 66%, VNQ 68%, DBC 53%.

## Files

- `PREREG_PHASE5.md`, `h_phase5.py`, `run_phase5.py`
- `results/phase5.json`, `results/phase5_run.log`
- `REGISTRY.csv` rows P5-H34 to P5-H37
