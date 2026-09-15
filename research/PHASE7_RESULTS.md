# Phase 7 (IBS swing trade on SPY and QQQ, from a strategy vendor's page): tested

**Date:** 2026-09-12 · **Rules frozen before any result:** `PREREG_PHASE7.md` (sha256 `c686fe25…c334d4bd`)
**Rerun:** `python3 research/run_phase7.py` (about 30 s)
**Verdict: FAIL.** 0 of 2 pass. Still the closest anything in this program has come.

---

## In plain English

The pasted page named two strategies.

### 1. The "Nasdaq volatility-based model": can't be tested

Its rules are sold, so there's nothing to run. Here are its advertised numbers next to simply
holding QQQ:

| | trades | average gain | win rate | profit factor | yearly return | time in market | worst drop |
|---|---|---|---|---|---|---|---|
| Vendor's claim (its own backtest) | 189 | 1.6% | 80% | 3.1 | 12.1% | 11% | −19.5% |
| Hold QQQ from 1999 | – | – | – | – | 10.7% | 100% | −83% |
| Hold QQQ from 2006 | – | – | – | – | 15.8% | 100% | −53% |

Three things to know before paying for it:
- **"Risk-adjusted return 110%" isn't a risk measure.** It's 12.1% divided by 11% time in the market:
  what you'd make if the same good days existed the other 89% of the time. They don't. The only way
  to get that number is to borrow about 9× your money, and 9× its own −19.5% drop would wipe out
  the account.
- **Whether it beats QQQ depends on the start date.** Holding QQQ from 1999, through the dot-com
  crash, made 10.7% a year. From 2006 it made 15.8%, more than the model's 12.1%.
- **A company selling many strategies shows its best backtests.** The more rules you try, the better
  the best one looks by luck alone. This program counts 114 tries and raises its bar to match. A
  sales page doesn't.

### 2. IBS swing trade: tested on the S&P 500 (SPY) and the Nasdaq (QQQ)

**The rule.** IBS says where a day closed inside its high-low range: 0 = at the low, 1 = at the high.
- Buy after a close near the low (IBS under 0.2).
- Sell after a close near the high (IBS over 0.8).
- The page gave no rules, so this is the standard published version.

**The pattern is real, and it hasn't faded.** About 65% of trades won. The average trade was about
the same after 2014 as before: SPY +0.34% → +0.29%, QQQ +0.42% → +0.41%. Almost every other effect in
this program shrank once it became known.

**But it didn't beat just holding the index.** Since 2014, after costs, buying at the next morning's
open:

| | yearly return over cash | return per unit of risk (Sharpe) | worst drop |
|---|---|---|---|
| IBS on SPY | +7.9% | 0.72 | −22% |
| Hold SPY | +11.6% | 0.73 | −34% |
| IBS on QQQ | +11.4% | 0.82 | −17% |
| Hold QQQ | +16.7% | 0.83 | −36% |

- **Why a 65% win rate isn't enough.** It's in the market only about half the time, so it earns about
  half the index's return with about half its ups and downs. Return per unit of risk came out the
  same as holding the index.
- **Its extra return is too small to tell from luck.** Over a half-sized index position it added
  +2.4% a year on SPY and +3.5% on QQQ. Over 12.7 years that's within luck: t = 1.14 and 1.28, and
  2.0 is needed.
- **What it did do: shrink the drops.**
  - 2022: −5.7% vs −24.9% on SPY, −13.1% vs −34.4% on QQQ.
  - 2008 on SPY: **+16.3%** while SPY lost 55.7%.
  - Not every crash: whole-history QQQ still fell 52% in 2000–02, because it was in the market half
    the time on the way down.
- **Against random timing:** moving its buy and sell days around at random did as well 8.6% of the
  time on SPY (fail) and 4.8% on QQQ (a narrow pass).
- **Trading at the same close, the seller's assumption, barely mattered.** It changed the yearly
  return by only 0.3–0.9 points.
- **Practical cost the backtest ignores:** about 28 round trips a year. In a taxable account that's
  all short-term gains.

### The seller's way of counting, whole history

Same rule and costs, in the table format sales pages use:

| | trades | average gain | win rate | profit factor | yearly return | time in market | worst drop | hold the ETF |
|---|---|---|---|---|---|---|---|---|
| SPY 1993→, same-close fill, 0.03% | 989 | +0.33% | 67% | 1.67 | 10.7% | 38% | −26% | 10.8%, −55% |
| SPY 1993→, next-open fill, 0.01% | 989 | +0.32% | 65% | 1.67 | 10.4% | 50%* | −27% | 10.8%, −55% |
| QQQ 1999→, same-close fill, 0.03% | 812 | +0.44% | 66% | 1.59 | 13.5% | 39% | −55% | 10.7%, −83% |
| QQQ 1999→, next-open fill, 0.01% | 812 | +0.41% | 66% | 1.55 | 12.6% | 50%* | −52% | 10.7%, −83% |

\*The next-open version counts the part-days at entry and exit, so it looks more exposed. The time
actually held is about the same.

Presented this way, IBS looks like a product: 65%+ wins, a profit factor of 1.6, and the index's
return with half the drawdown on SPY. All true, and it still didn't beat holding the index on risk
since 2014.

---

## Results (out of sample 2014 →, after costs, excess of cash)

| | window | yearly over cash | Sharpe (95% CI) | same ETF held | alpha vs it (t), beta | worst drop | failed gates |
|---|---|---|---|---|---|---|---|
| H42 IBS on SPY | 2014 → 2026 (12.7y) | +7.9% | 0.72 (0.24, 1.23) | +11.6%, SR 0.73 | +2.4%/yr (1.14), 0.47 | −22% | G2, G3, G7 |
| H43 IBS on QQQ | 2014 → 2026 (12.7y) | +11.4% | 0.82 (0.39, 1.29) | +16.7%, SR 0.83 | +3.5%/yr (1.28), 0.47 | −17% | G2, G3 |

- **Deflated Sharpe (G3)** at N = 114: 0.46 and 0.61; 0.95 is needed.
  - At N = 2, as if these were the only strategies ever tried: 0.98 and 0.99.
  - The verdict doesn't rest on the trial count: G2 fails at any N.
- **Placebos (G7):** 8.6% and 4.8% of circularly shifted signals did at least as well.
- **Neighbours (G6):** all 8 positive, Sharpe 0.43–0.85.
- **After Fama-French 5 factors + momentum:** alpha +2.3%/yr (t 1.07) and +4.6%/yr (t 1.65).
- **Passed by both:** G1, double costs (G4: SR 0.67 and 0.78), sub-periods (G5), neighbours (G6),
  implementability (G8), survivorship (G10), and the look-ahead truncation test.

---

## Where the search stands

Phases 4–7 have now tested 13 famous published retail strategies. None passed.

IBS came closest. Its per-trade edge is stable, and on QQQ it beat random timing. But it doesn't add
return per unit of risk over holding the index. What it amounts to is a way to hold an index ETF
about half the time with smaller drops. That's a choice about risk, not an edge. A smaller index
position gives similar risk-adjusted results without 59× turnover a year.

Descriptive of the past only. Not investment advice.

## Files

- `PREREG_PHASE7.md`, `h_phase7.py`, `run_phase7.py`
- `results/phase7.json`, `results/phase7_run.log`
- `REGISTRY.csv` rows P7-H42 and P7-H43
