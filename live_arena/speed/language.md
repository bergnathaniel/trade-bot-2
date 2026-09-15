# Candle language study

Paper money only. Every saved speed-test candle is read as a letter (its size against the last 50 candles, and where it closed in its range), and the last 2 or 3 letters as a word. Walking forward through time, each word's record is what buying at the next open and selling 1, 4 or 8 hours later made after fees, counting only trades that had finished in the last 30 days. The study then trades a word only while its record clears a bar, and scores those trades on candles that weren't in the record yet.

- **Strict:** 50 or more finished trades, and the average minus 4 standard errors is still above zero.
- **Loose:** any word that made money on average over 30 or more finished trades.
- **Every candle:** buying at every candle, for comparison.

## Crypto, 5-minute candles

Tested 2026-07-27 to 2026-09-14 (after a 14-day warm-up), split at 2026-08-20. A round trip costs 0.54%.

| Rule | Trades (1st / 2nd half) | Average after fees (1st / 2nd half) | Won |
|---|---:|---:|---:|
| Strict | 0 / 0 | – / – | – |
| Loose | 49 / 750 | -0.337% / -0.544% | 30% |
| Every candle, 1 hour | 84672 / 84516 | -0.527% / -0.523% | 13% |
| Every candle, 4 hours | 84672 / 84084 | -0.480% / -0.470% | 25% |
| Every candle, 8 hours | 84672 / 83508 | -0.407% / -0.410% | 31% |

**Does what worked keep working?** 1861 word-and-horizon records had 50+ trades in both halves. 9 made money in the first half, and 0 of those also made money in the second. The correlation between the two halves' averages was +0.15 (0 means the first half says nothing about the second).

**The best records at the last candle** (strict bar in the last column):

| Word | Hold | Trades | Average after fees | Clears the strict bar |
|---|---|---:|---:|---|
| big down near its low → big down near its low | 8 hours | 2482 | -0.184% | no |
| down near its low → down near its low | 8 hours | 2076 | -0.209% | no |
| down mid-range → big down near its low | 8 hours | 1151 | -0.144% | no |
| big down near its low → down near its low | 8 hours | 1843 | -0.219% | no |
| up near its high → down near its low | 8 hours | 1959 | -0.224% | no |
| flat mid-range → down near its low | 8 hours | 1129 | -0.165% | no |
| up near its high → down mid-range | 8 hours | 1060 | -0.144% | no |
| down near its low → up near its high | 8 hours | 2013 | -0.255% | no |

## Crypto, 15-minute candles

Tested 2026-07-27 to 2026-09-14 (after a 14-day warm-up), split at 2026-08-20. A round trip costs 0.54%.

| Rule | Trades (1st / 2nd half) | Average after fees (1st / 2nd half) | Won |
|---|---:|---:|---:|
| Strict | 0 / 0 | – / – | – |
| Loose | 68 / 667 | -0.879% / -0.536% | 30% |
| Every candle, 1 hour | 28224 / 28164 | -0.527% / -0.523% | 13% |
| Every candle, 4 hours | 28224 / 28020 | -0.479% / -0.470% | 25% |
| Every candle, 8 hours | 28224 / 27828 | -0.406% / -0.410% | 31% |

**Does what worked keep working?** 585 word-and-horizon records had 50+ trades in both halves. 1 made money in the first half, and 0 of those also made money in the second. The correlation between the two halves' averages was +0.12 (0 means the first half says nothing about the second).

**The best records at the last candle** (strict bar in the last column):

| Word | Hold | Trades | Average after fees | Clears the strict bar |
|---|---|---:|---:|---|
| down near its low → big down near its low | 8 hours | 624 | +0.046% | no |
| big down near its low → down near its low | 8 hours | 510 | -0.020% | no |
| big down near its low → down near its low → big down near its low | 4 hours | 78 | +0.066% | no |
| big up near its high → down near its low | 8 hours | 704 | -0.102% | no |
| big down near its low → down near its low → big down near its low | 8 hours | 79 | +0.216% | no |
| down near its low → big down near its low | 4 hours | 626 | -0.235% | no |
| up near its high → up near its high | 8 hours | 594 | -0.091% | no |
| big down mid-range → big down near its low | 1 hour | 175 | -0.229% | no |

## US stocks and ETFs, 5-minute candles

Tested 2026-07-01 to 2026-09-14 (after a 14-day warm-up), split at 2026-08-08. A round trip costs 0.08%.

| Rule | Trades (1st / 2nd half) | Average after fees (1st / 2nd half) | Won |
|---|---:|---:|---:|
| Strict | 18 / 185 | -0.039% / -0.074% | 41% |
| Loose | 621 / 462 | +0.083% / +0.059% | 49% |
| Every candle, 1 hour | 42120 / 38760 | -0.047% / -0.062% | 41% |
| Every candle, 4 hours | 42120 / 38040 | +0.033% / -0.006% | 46% |
| Every candle, 8 hours | 42120 / 37080 | +0.131% / +0.058% | 48% |

**Does what worked keep working?** 966 word-and-horizon records had 50+ trades in both halves. 499 made money in the first half, and 240 of those also made money in the second. The correlation between the two halves' averages was +0.06 (0 means the first half says nothing about the second).

**The best records at the last candle** (strict bar in the last column):

| Word | Hold | Trades | Average after fees | Clears the strict bar |
|---|---|---:|---:|---|
| big down near its low → big down near its low | 8 hours | 801 | +0.394% | yes |
| big up near its high → big down near its low | 8 hours | 954 | +0.364% | no |
| big down near its low → big up near its high | 1 hour | 913 | +0.045% | no |
| big up near its high → big up near its high | 1 hour | 815 | +0.058% | no |
| big up near its high → big down near its low | 1 hour | 957 | +0.049% | no |
| big up near its high → big down near its low | 4 hours | 955 | +0.125% | no |
| up near its high → big up near its high | 8 hours | 514 | +0.439% | no |
| down near its low → down near its low | 1 hour | 720 | -0.053% | no |

## US stocks and ETFs, 15-minute candles

Tested 2026-07-01 to 2026-09-14 (after a 14-day warm-up), split at 2026-08-08. A round trip costs 0.08%.

| Rule | Trades (1st / 2nd half) | Average after fees (1st / 2nd half) | Won |
|---|---:|---:|---:|
| Strict | 0 / 4 | – / +0.100% | 25% |
| Loose | 560 / 455 | +0.090% / +0.066% | 48% |
| Every candle, 1 hour | 14040 / 12900 | -0.048% / -0.063% | 41% |
| Every candle, 4 hours | 14040 / 12660 | +0.032% / -0.007% | 46% |
| Every candle, 8 hours | 14040 / 12340 | +0.131% / +0.056% | 48% |

**Does what worked keep working?** 275 word-and-horizon records had 50+ trades in both halves. 135 made money in the first half, and 45 of those also made money in the second. The correlation between the two halves' averages was +0.04 (0 means the first half says nothing about the second).

**The best records at the last candle** (strict bar in the last column):

| Word | Hold | Trades | Average after fees | Clears the strict bar |
|---|---|---:|---:|---|
| big down near its low → flat mid-range | 1 hour | 128 | +0.068% | no |
| big up near its high → big up near its high | 1 hour | 285 | +0.091% | no |
| down near its low → big down near its low | 1 hour | 179 | +0.077% | no |
| big down near its low → big down near its low | 1 hour | 246 | -0.016% | no |
| big up near its high → big down near its low | 1 hour | 276 | +0.013% | no |
| big up mid-range → big down near its low | 1 hour | 42 | +0.203% | no |
| big down near its low → big up near its high | 1 hour | 265 | +0.004% | no |
| big up near its high → big up near its high | 4 hours | 286 | +0.122% | no |

Descriptive of the past only. Not investment advice.
