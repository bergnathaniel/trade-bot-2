# Phase 2 (earnings drift, earnings surprises, insider buying, Treasury auctions): tested

**Date:** 2026-09-11 · **Rules frozen before any Phase-2 return was computed:** `PREREG_PHASE2.md`.
Amendment A1 was appended after the first run; see below.
**Rerun:** `python3 research/run_phase2.py` (original), `python3 research/run_phase2.py --A1` (amended),
about 80 s each with the cached SEC and price data.
**Verdict: FAIL.** 0 of 8 pass, and 0 reach WATCH, with or without the data fix.

---

## In plain English

**What was tested.** Four published ideas that hold positions for weeks, so fees barely matter:
- **Earnings-reaction drift** (published 2008): stocks that jump on an earnings announcement keep
  outperforming for about 3 months.
- **Earnings-surprise drift** (1989): the same idea, using how far reported earnings beat last
  year's.
- **Insider buying** (2012): stocks that "opportunistic" insiders buy beat the market the next month.
- **Treasury auction cycle** (2013): 10-year Treasury bonds dip before auctions and recover after.

**The data.** Every idea was run on 900 current S&P 500 and MidCap 400 stocks, using SEC filings,
and only on the years after it was published. They faced the same gates as Phase 1.

**Did any work? No.**
- **Earnings reaction, long-only, was the closest.**
  - It beat owning all 900 stocks equally by only +0.6% a year.
  - Against the S&P 500 it was +3.3% a year, but its t-stat was 1.91 (2.0 is needed), it carried
    17% more market risk, and its range of plausible Sharpe ratios included zero.
  - The test universe also only contains companies that are *still* in the index today. That alone
    can create a gap this size.
- **Long/short versions lost.** Earnings reaction lost −4.0% a year (t −2.76): the stocks it bet
  against kept rising.
- **Earnings surprise:** −1.9% a year long-only, and −1.2% long/short.
- **Insider buying:** −10% a year versus owning everything equally. Random stocks, in the same
  numbers each month, beat it about 91% of the time.
- **Treasury auction cycle:** −0.9% a year versus cash. 99% of random dates did better.

**Two bugs were caught before any number was believed.**
1. **A crash** in the insider test's look-ahead check. The full-data pass compared dates against a
   missing cut-off. This was a code fix, not a rule change.
2. **A bad price.** Yahoo's history for Chord Energy (CHRD) joins the bankrupt old Oasis Petroleum
   shares, last $0.07, to the new shares issued on 2020-11-20 at $18.84. That is a fake 258× "gain"
   no shareholder ever got.
   - It produced a −301% day and a −171% drawdown in the insider long/short test, which is
     impossible.
   - It added a fake +30% day to the "own everything equally" benchmark.
   - Amendment A1, written into the pre-registration before the rerun, rescales that one bar. It is
     the only bar in the panel the rule touches.
   - Both runs are reported. The fix didn't change a single verdict.

**What it means.** These are among the best-documented stock anomalies there are, and after
publication they don't beat simply owning the market. Even the near-miss would need data that
includes the companies that later dropped out of the index (paid data) before it could count.

---

## Results (amendment A1; out-of-sample, after costs)

"Yearly vs benchmark" means:
- **LO** (long-only): versus owning all 900 stocks equally.
- **LS** (long/short): long basket minus short basket.
- **Auction:** versus cash.

| version | years | yearly vs benchmark | Sharpe (95% CI) | alpha vs SPY or IEF (t) | failed gates |
|---|---|---|---|---|---|
| Earnings reaction, LO | 17.7 | +0.6% | 0.17 (−0.23, 0.59) | +3.3%/yr (1.91), beta 1.17 | G1, G2, G3, G4, G10 |
| Earnings reaction, LS | 17.7 | −4.0% | −0.69 (−1.17, −0.20) | −3.8%/yr (−2.76) | all except G9 (n/a) |
| Earnings surprise, LO | 15.3 | −1.9% | −0.34 (−0.80, 0.10) | +1.0%/yr (0.61) | G1–G7, G10 |
| Earnings surprise, LS | 15.3 | −1.2% | −0.10 (−0.51, 0.35) | −0.3%/yr (−0.17) | G1–G4, G6–G8, G10 |
| Insider buys, LO | 14.7 | −10.1% | −0.51 (−0.97, −0.08) | −6.1%/yr (−1.29) | G1–G7, G10 |
| Insider buys minus sells, LS | 14.7 | −10.3% | −0.48 (−0.93, −0.06) | −9.6%/yr (−2.13) | all except G9 (n/a) |
| Auction cycle, long IEF after | 12.7 | −0.9% | −0.26 (−0.76, 0.27) | −0.9%/yr (−1.10) | G1–G7 |
| Auction cycle, short before / long after | 12.7 | −0.1% | 0.00 (−0.47, 0.44) | +0.0%/yr (0.01) | G1–G4, G7 |

- **The near-miss, earnings reaction LO**, passed:
  - G5: positive in 2 of 3 sub-periods (+10.9%, +6.2%, −5.3%)
  - G6: its neighbours
  - G7: it beat 99.9% of shuffled-signal placebos
  - G8: retail-implementable
- **What it failed:** the Sharpe interval includes 0 (G1), alpha t below 2 (G2), the deflated
  Sharpe (0.01 vs 0.95 needed, G3), double costs (G4), and survivorship (G10).
- **Registry:** `P2-…-A1` rows. The original run is `P2-…`.

**What the fix changed.** Only series touched by the bad price moved:

| version | original run | amended (A1) |
|---|---|---|
| Earnings reaction, LO | −1.4%/yr, Sharpe −0.12, max drawdown −36% | +0.6%/yr, Sharpe 0.17, max drawdown −8% |
| Earnings surprise, LO | −4.2%/yr | −1.9%/yr |
| Insider buys minus sells, LS | −100%/yr, max drawdown −171%, worst day −301% | −10.3%/yr, max drawdown −86%, worst day −15% |
| Insider buys, LO | −12.4%/yr | −10.1%/yr |

The earnings long/short versions and both auction versions are unchanged.

---

## Caveats

- **Survivorship (G10).** Every stock test uses today's index members. Firms that failed or shrank
  out of the index are missing, which flatters both the baskets and the equal-weight benchmark. No
  stock result here could reach PASS without survivorship-free data.
- **Multiple testing.** The deflated-Sharpe count is the pre-registered N = 97. Tonight's other
  tests add thousands more trials, which would only raise the bar.
- **The insider result is surprisingly bad** next to the 1986–2007 paper. It isn't a price-data
  artifact: the random-stock placebo uses the same prices and still beats it. After factor
  adjustment, most of the gap is exposure to cheap stocks, small stocks and falling-momentum stocks
  (alpha −4.0%/yr, t −0.92).

## Files

- `PREREG_PHASE2.md`: the frozen rules, with amendment A1
- `run_phase2.py`, `h_events.py`, `h_insider.py`, `h_auction.py`, `h_stocks.py`, `basket.py`,
  `p2data.py`
- `results/phase2.json` and `results/phase2_run.log`: original
- `results/phase2_A1.json` and `results/phase2_A1_run.log`: amended
