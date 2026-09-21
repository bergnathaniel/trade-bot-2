# Candle language study

Paper money only. Every saved speed-test candle is read as a letter (its size against the last 50 candles, and where it closed in its range), and the last 2 or 3 letters as a word. Walking forward through time, each word's record is what buying at the next open and selling 1, 4 or 8 hours later made after fees, counting only trades that had finished in the last 30 days. The study then trades a word only while its record clears a bar, and scores those trades on candles that weren't in the record yet.

- **Strict:** 50 or more finished trades, and the average minus 4 standard errors is still above zero.
- **Loose:** any word that made money on average over 30 or more finished trades.
- **Every candle:** buying at every candle, for comparison.

## Crypto, 5-minute candles

Tested 2026-07-27 to 2026-09-21 (after a 14-day warm-up), split at 2026-08-24. A round trip costs 0.54%.

| Rule | Trades (1st / 2nd half) | Average after fees (1st / 2nd half) | Won |
|---|---:|---:|---:|
| Strict | 0 / 0 | – / – | – |
| Loose | 143 / 876 | +0.106% / -0.497% | 34% |
| Every candle, 1 hour | 96768 / 96612 | -0.508% / -0.525% | 14% |
| Every candle, 4 hours | 96768 / 96180 | -0.413% / -0.478% | 27% |
| Every candle, 8 hours | 96768 / 95604 | -0.288% / -0.416% | 33% |

**Does what worked keep working?** 2109 word-and-horizon records had 50+ trades in both halves. 58 made money in the first half, and 4 of those also made money in the second. The correlation between the two halves' averages was +0.19 (0 means the first half says nothing about the second).

**The best records at the last candle** (strict bar in the last column):

| Word | Hold | Trades | Average after fees | Clears the strict bar |
|---|---|---:|---:|---|
| down mid-range → big down near its low | 8 hours | 1187 | -0.207% | no |
| big down near its low → big down near its low | 8 hours | 2601 | -0.319% | no |
| down near its low → down near its low | 8 hours | 2094 | -0.305% | no |
| flat near its low → down near its low | 8 hours | 864 | -0.228% | no |
| big down near its low → big down near its low | 4 hours | 2588 | -0.385% | no |
| big down near its low → big down near its low | 1 hour | 2588 | -0.441% | no |
| big up near its high → big down near its low | 4 hours | 3669 | -0.411% | no |
| down near its low → up near its high | 8 hours | 1998 | -0.328% | no |

## Crypto, 15-minute candles

Tested 2026-07-27 to 2026-09-21 (after a 14-day warm-up), split at 2026-08-24. A round trip costs 0.54%.

| Rule | Trades (1st / 2nd half) | Average after fees (1st / 2nd half) | Won |
|---|---:|---:|---:|
| Strict | 0 / 0 | – / – | – |
| Loose | 145 / 808 | -0.479% / -0.446% | 33% |
| Every candle, 1 hour | 32256 / 32196 | -0.508% / -0.525% | 14% |
| Every candle, 4 hours | 32256 / 32052 | -0.413% / -0.478% | 27% |
| Every candle, 8 hours | 32256 / 31860 | -0.288% / -0.416% | 33% |

**Does what worked keep working?** 690 word-and-horizon records had 50+ trades in both halves. 26 made money in the first half, and 4 of those also made money in the second. The correlation between the two halves' averages was +0.20 (0 means the first half says nothing about the second).

**The best records at the last candle** (strict bar in the last column):

| Word | Hold | Trades | Average after fees | Clears the strict bar |
|---|---|---:|---:|---|
| down near its low → big down near its low | 8 hours | 627 | -0.002% | no |
| big up near its high → big down mid-range → big down near its low | 4 hours | 47 | +0.227% | no |
| big down mid-range → big down near its low | 4 hours | 174 | -0.007% | no |
| big down mid-range → big down near its low | 1 hour | 175 | -0.197% | no |
| down near its low → big down near its low | 4 hours | 625 | -0.249% | no |
| down near its low → big down near its low | 1 hour | 626 | -0.374% | no |
| big down near its low → down near its low | 4 hours | 494 | -0.265% | no |
| big down mid-range → big down mid-range | 1 hour | 42 | -0.227% | no |

## US stocks and ETFs, 5-minute candles

Tested 2026-07-01 to 2026-09-21 (after a 14-day warm-up), split at 2026-08-11. A round trip costs 0.08%.

| Rule | Trades (1st / 2nd half) | Average after fees (1st / 2nd half) | Won |
|---|---:|---:|---:|
| Strict | 18 / 209 | -0.039% / +0.137% | 41% |
| Loose | 638 / 530 | +0.068% / +0.141% | 49% |
| Every candle, 1 hour | 43760 / 43540 | -0.048% / -0.049% | 41% |
| Every candle, 4 hours | 43760 / 42820 | +0.020% / +0.026% | 46% |
| Every candle, 8 hours | 43760 / 41860 | +0.103% / +0.123% | 48% |

**Does what worked keep working?** 1075 word-and-horizon records had 50+ trades in both halves. 518 made money in the first half, and 298 of those also made money in the second. The correlation between the two halves' averages was +0.10 (0 means the first half says nothing about the second).

**The best records at the last candle** (strict bar in the last column):

| Word | Hold | Trades | Average after fees | Clears the strict bar |
|---|---|---:|---:|---|
| big down near its low → big down near its low | 8 hours | 793 | +0.529% | yes |
| big up near its high → big down near its low | 8 hours | 863 | +0.331% | no |
| big up near its high → big down near its low | 4 hours | 869 | +0.170% | no |
| big down near its low → big down near its low | 1 hour | 801 | +0.043% | no |
| big up near its high → up near its high | 1 hour | 453 | +0.093% | no |
| big down near its low → big up near its high | 1 hour | 832 | +0.033% | no |
| big down near its low → up near its high | 4 hours | 523 | +0.175% | no |
| big down near its low → big down near its low → big down near its low | 8 hours | 179 | +0.676% | no |

## US stocks and ETFs, 15-minute candles

Tested 2026-07-01 to 2026-09-21 (after a 14-day warm-up), split at 2026-08-11. A round trip costs 0.08%.

| Rule | Trades (1st / 2nd half) | Average after fees (1st / 2nd half) | Won |
|---|---:|---:|---:|
| Strict | 0 / 4 | – / +0.100% | 25% |
| Loose | 579 / 518 | +0.080% / +0.130% | 48% |
| Every candle, 1 hour | 14580 / 14500 | -0.049% / -0.050% | 41% |
| Every candle, 4 hours | 14580 / 14260 | +0.019% / +0.025% | 46% |
| Every candle, 8 hours | 14580 / 13940 | +0.103% / +0.121% | 49% |

**Does what worked keep working?** 301 word-and-horizon records had 50+ trades in both halves. 143 made money in the first half, and 69 of those also made money in the second. The correlation between the two halves' averages was +0.12 (0 means the first half says nothing about the second).

**The best records at the last candle** (strict bar in the last column):

| Word | Hold | Trades | Average after fees | Clears the strict bar |
|---|---|---:|---:|---|
| big down near its low → big down near its low | 1 hour | 215 | +0.095% | no |
| big up mid-range → big down near its low | 1 hour | 36 | +0.259% | no |
| big down near its low → up mid-range | 1 hour | 113 | +0.025% | no |
| down near its low → big down near its low | 1 hour | 158 | +0.078% | no |
| big up near its high → big down near its low | 1 hour | 254 | +0.014% | no |
| big down near its low → flat mid-range | 1 hour | 112 | +0.044% | no |
| big up near its high → big up near its high | 4 hours | 257 | +0.148% | no |
| big up near its high → big up near its high | 1 hour | 256 | -0.006% | no |

Descriptive of the past only. Not investment advice.
