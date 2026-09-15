# Phase 4 (dual momentum, "Sell in May", the Fed-meeting cycle): tested

**Date:** 2026-09-12 · **Rules frozen before any result:** `PREREG_PHASE4.md` (SHA-256 printed in
`results/phase4_run.log`)
**Rerun:** `python3 research/run_phase4.py` (about 90 s)
**Verdict: FAIL.** 0 of 3 pass.

---

## In plain English

The user said "keep going". So this round took three famous ideas this project hadn't tested. All
three have free, survivorship-free data and more than ten years of history since they were
published.

**1. Dual momentum** (published 2012). This is a popular do-it-yourself strategy. Each month, hold
whichever of US or international stocks rose more over the past year. If that one didn't beat cash,
hold bonds instead.
- Since 2013 it made **+6.7% a year** over cash. Just holding the S&P 500 made **+13.0%**. The worst
  drop was the same for both, −34%.
- It spent 19% of months in international stocks and 12% in bonds. Both lagged US stocks.
- Randomly reshuffling its own monthly picks did at least as well **97% of the time**.

**2. "Sell in May"** (published 2002). Hold stocks November–April and sit in cash May–October.
- Since 2003 it made **+5.6% a year**, against **+9.7%** for the S&P 500. It had smaller swings: its
  worst drop was −37%, against −56%.
- It is out of the market half the time. Adjusted for that, its edge is about zero: +0.5% a year,
  t 0.26.
- **Summer stopped being bad.** Summer days earned 0.3 basis points a day in 1993–2002. Since 2003
  they earned 3.5 basis points a day. Winter days earned about 5 in both periods.
- Random 6-month holding windows did as well 38% of the time.

**3. The Fed-meeting cycle** (circulated around 2015, published 2019). This idea says stocks earn
their gains in alternating weeks after each Fed meeting.
- Since 2016 it made **+3.0% a year**, against **+12.5%** for the S&P 500.
- **The effect flipped after it became known.**
  - Before 2016, the "good" weeks earned +8.7 basis points a day and the other weeks −3.4.
  - Since 2016, the "good" weeks earned +3.2 and the other weeks +7.6.
- Randomly shifted Fed calendars did as well 89% of the time.

**Same story as every earlier round.** The effects looked real before they were published and faded
or reversed after. Nothing beat simply holding the market.

---

## Results (out of sample, after costs, excess of cash)

| | window | yearly over cash | Sharpe (95% CI) | S&P 500, same window | alpha vs SPY (t), beta | worst drop | failed gates |
|---|---|---|---|---|---|---|---|
| H31 dual momentum | 2013 → 2026 (13.7y) | +6.7% | 0.50 (0.05, 1.04) | +13.0%, Sharpe 0.81 | −3.3%/yr (−1.78), 0.80 | −34% | G2, G3, G7 |
| H32 Sell in May | 2003 → 2026 (23.7y) | +5.6% | 0.47 (0.15, 0.88) | +9.7%, Sharpe 0.59 | +0.5%/yr (0.26), 0.54 | −37% | G2, G3, G7 |
| H33 Fed-cycle weeks | 2016 → 2026 (10.7y) | +3.0% | 0.30 (−0.19, 0.87) | +12.5%, Sharpe 0.75 | −3.2%/yr (−1.29), 0.52 | −27% | G1, G2, G3, G7 |

- **Passed by all three:**
  - costs ×2 (G4)
  - 2 of 3 sub-periods (G5)
  - all four neighbour variants positive (G6)
  - retail-implementable (G8)
  - survivorship-free (G10)
  - the look-ahead truncation test
  They are stable rules. They just earn less than holding the market, or about the same after
  adjusting for exposure.
- **Deflated Sharpe (G3)** at N = 104: 0.19, 0.10 and 0.08, against 0.95 needed.
- **Placebos (G7):** the share that did at least as well was 96.7%, 37.9% and 88.7%.
- **Dual momentum's neighbours:**

  | neighbour | Sharpe |
  |---|---|
  | 6-month lookback | 0.39 |
  | 9-month lookback | 0.45 |
  | IEF as the bond | 0.47 |
  | 0% hurdle | 0.54 |

- **Fed-cycle neighbours:**

  | neighbour | Sharpe |
  |---|---|
  | weeks 2/4/6 only | 0.35 |
  | QQQ | 0.44 |
  | IWM | 0.18 |
  | DIA | 0.20 |

## Files

- `PREREG_PHASE4.md`, `h_phase4.py`, `run_phase4.py`
- `results/phase4.json`, `results/phase4_run.log`
- `REGISTRY.csv` rows P4-H31, P4-H32 and P4-H33
