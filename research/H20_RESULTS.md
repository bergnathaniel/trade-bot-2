# Bond term-premium timing (H20): tested

**Date:** 2026-09-12 · **Rules frozen before any result:** `PREREG_H20.md` (sha256 `26005385…8ba8`)
**Rerun:** `python3 research/run_h20.py` (about 10 s)
**Verdict: FAIL.** Both versions fail.

---

## In plain English

**The idea.** When 10-year Treasury yields sit far above 3-month bill rates, owning bonds has tended
to pay more. It was published in 1987 and 1991.

**How it was tested.**
- **The forecast.** At each month's end, a forecast built only from past data decides whether to
  hold a 7–10-year Treasury bond fund (IEF) next month or sit in cash. The forecast is trained on
  bond returns rebuilt from Fed yield data going back to 1962.
- **A second version** shorts IEF instead of sitting in cash.
- **The test period** is 24 years of IEF, 2002–2026, all after publication.

**Result: it doesn't beat just holding the bonds.**
- **The hold-or-cash version** earned +1.8% a year over cash. Simply holding IEF the whole time
  earned +1.7%.
  - Its swings were smaller: the worst drop was −23% against −28%, and in the 2022 bond crash it lost
    8.4% against 17.1%.
  - Its month-by-month calls were right **51.6%** of the time, which is a coin flip.
  - Shuffling the same in-and-out months randomly did as well 13% of the time.
  - Its edge over holding bonds, +0.6% a year, can't be told apart from zero (t-stat 1.05).
  - In short, it held bonds 63% of the time and got about the same return. Luck explains that.
- **The long/short version** earned about nothing (+0.2% a year). It lost money shorting bonds right
  before rallies: −6.3% in the COVID crash, when bonds rose 6.3%.

**The test itself checks out.**
- No decision uses future data (the truncation test passes for both versions).
- The rebuilt bond returns track IEF closely (correlation 0.90).
- The rule survives double costs, two of three sub-periods, and all four neighbour variants.
  The idea is stable; it just isn't better than holding bonds by more than luck would give.

---

## Results (out-of-sample 2002-08 → 2026-09, after costs)

| | years | yearly over cash | Sharpe (95% CI) | vs holding IEF: alpha (t), beta | worst drop | failed gates |
|---|---|---|---|---|---|---|
| H20-LO: IEF or cash | 24.1 | +1.8% | 0.35 (−0.03, 0.73) | +0.6%/yr (1.05), 0.67 | −23% | G1, G2, G3, G7 |
| H20-LS: IEF long or short | 24.1 | +0.2% | 0.06 (−0.33, 0.45) | −0.2%/yr (−0.17), 0.33 | −38% | G1, G2, G3, G7 |
| holding IEF | 24.1 | +1.7% | 0.28 | | −28% | |

- **G3 deflated Sharpe:** 0.03 against the 0.95 needed at N = 101. It would clear the bar only if
  this were the only test ever run (0.955 at N = 1).
- **G7 placebo:** the share of random month permutations that did as well was 13% (LO) and 24% (LS).
- **Neighbour Sharpes, all positive (LO):**
  - 10y − 2y spread: 0.31
  - 5y − 3m spread: 0.39
  - TLT instead of IEF: 0.26
  - rolling 20-year window: 0.32
- **Behaviour:** in or out for long stretches. There were 6 round trips in 24 years, and the version
  was long 63% of months.
- **Stock-factor alpha** is +2.8%/yr (t 2.61). That only reflects holding bonds, which stock factors
  don't explain; the gated comparison is against bonds.

---

## Where this leaves the research program

Every hypothesis in `PROGRAM.md` that can be tested with free data, *and could pass*, has now been
tested. None passed:

| round | what | configurations | passed |
|---|---|---|---|
| Phase 1 | 31 published anomalies | 116 incl. neighbours | 0 |
| Phase 2 | 8 filing-event / auction versions | 56 incl. neighbours | 0 |
| H20 | bond term-premium timing | 10 incl. neighbours | 0 |
| intraday | the prediction engine, the sniper system, and a 9,504-configuration search | about 9,500 | 0 |

The rest of the list can't be tested with free data:
- **H23–H30** need paid data.
- **H17–H19** need stock data that includes companies that dropped out of the index.
- **H15 and H16** don't have enough history since publication.

**The crypto confirmation year** (2024-09 → 2025-09) is downloaded and still untouched, because
nothing reached it.

## Files

- `PREREG_H20.md`, `h_term.py`, `run_h20.py`
- `results/h20.json`, `results/h20_run.log`
- `REGISTRY.csv` rows P3-H20-LO and P3-H20-LS
