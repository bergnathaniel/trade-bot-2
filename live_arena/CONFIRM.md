# Live Arena micro-cap confirmation test

**Written:** 2026-09-12, after the first basket was tested and before basket B was built or any bot
ran on it.

## Why

Basket A (`basket.json`: 30 random micro-caps, seed 20260912) got 34 bots × 3 settings, plus a rerun
with next-open fills at two fees. That's about 100 results. The best of 100 results always looks
good, whether or not anything real is there. So the leaders get one test on stocks they have never
seen.

## Candidates

Every bot whose median stock return was above 0 in basket A, with next-open fills and 0.50% per
trade:

| bot | median | average |
|---|---|---|
| Martingale Doubler | +21.9% | +18.9% |
| Stochastic Swing | +9.6% | +28.7% |
| Grid Trader | +4.6% | +22.7% |
| Inside Bar Breakout | +4.3% | +20.1% |

## The test

- **Basket B** has 30 different stocks picked by the same rule:
  `python3 make_basket.py --seed 20260913 --exclude basket.json --out basket_b.json`
- Daily candles over the same ~3-year window. The first 60 candles are warm-up.
- Every buy and sell fills at the next candle's open, at 0.50% per trade.

## A candidate "works" only if all four hold on basket B

1. Its average return beats both the Coin Flip bot's average and the basket's own buy-and-hold
   average.
2. Its median stock return is above 0.
3. It makes money on more than 15 of the 30 stocks.
4. Its average return beats simply holding IWC, the micro-cap index fund, over the same window.

Checks 1–3 ask whether the timing is better than luck. Check 4 asks whether it's worth doing instead
of buying the index fund. A candidate that passes 1–3 but fails 4 is reported as "real, but not
worth it".

## Limits, stated before the test

- **Same window as basket A.** A good or bad stretch for micro-cap bounces affects both baskets.
- **Today's micro-caps only.** Companies that shrank into this size are in; ones that went bust are
  out.
- **Small sample.** 30 stocks is not much. A pass means "worth a longer test", not proof.
- **Martingale has no stop-loss.** A 3-year window without a crash can make it look safe.

---

## Results (run 2026-09-12)

**Setup.** Basket B had 30 stocks, none skipped, trading from about January 2024 to September 2026.
Fills at the next open, 0.50% per trade.

**Yardsticks on basket B:**
- Holding IWC, the micro-cap index fund: **+66.8%**
- Holding the 30 stocks themselves: average +14.5%, median −16.9%, 13 of 30 up
- Coin Flip: average −31.8%, median −44.7%, 3 of 30 up

| bot | average | median | made money | 1 beats luck | 2 median > 0 | 3 more than 15 | 4 beats IWC | result |
|---|---|---|---|---|---|---|---|---|
| Martingale Doubler | +29.9% | +21.9% | 23 of 30 | pass | pass | pass | fail | real, but not worth it |
| Grid Trader | +21.6% | −7.9% | 15 of 30 | pass | fail | fail | fail | fails |
| Inside Bar Breakout | −7.8% | −28.1% | 9 of 30 | fail | fail | fail | fail | fails |
| Stochastic Swing | −27.5% | −36.5% | 7 of 30 | fail | fail | fail | fail | fails |

**What it means:**
- **Three of the four leaders failed on new stocks.** Stochastic Swing went from a +9.6% median to
  −36.5%. IBS had been basket A's headline (+167% average with the cheap same-close fills). On basket
  B it had the worst median of all 34 bots, −46.4%.
- **The rankings flipped.** Trend bots near the bottom in basket A had some of the biggest averages
  in basket B: ADX +66.5%, Supertrend +55.7%, MACD +49.1%. One or two huge winners carried each of
  them, such as DFDV (+295% just holding it). That is what luck looks like.
- **Martingale passed the luck checks in both baskets, but made less than half what the index fund
  made** (+29.9% vs +66.8%). Its losers are big because it has no stop-loss: DMRC −82.9%, TTGT −71.2%,
  CMTG −59.9%. The high win count hides that.

**Verdict: nothing works.** By the rule written before this test, no candidate is worth trading
instead of holding IWC. Running more baskets until one passes would just be re-rolling dice.
