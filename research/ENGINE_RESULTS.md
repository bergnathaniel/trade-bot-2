# The "Continuous Market Prediction Engine": tested

**Date:** 2026-09-11 · **Rules frozen before any result:** `PREREG_ENGINE.md` (sha256 `e159f210…0035a`)
**Rerun:** `python3 research/run_engine.py` (about 30 s with cached data)
**Verdict: FAIL.** All 6 configurations fail every gate in both the crypto and stock groups.

---

## In plain English

**What was tested.** The pasted prompt, written down as fixed rules. It used the same indicators,
timeframes, regimes, confidence scores and BUY/SELL rules, and it logged every call the way the
prompt demands. It ran every 5 minutes for a full year on Bitcoin and Ethereum, about 100,000
decisions per coin. It also ran on SPY, QQQ, NVDA and TSLA for the 19 trading days of free
1-minute data.

**Was it right more often than guessing? No.** When it called UP or DOWN, the price moved that
way **46% of the time**, on crypto and on stocks. A coin flip gets 50%.

**Did its confidence mean anything? No.** When it said "70–80% likely," it was right **27%** of the
time on crypto and **19%** on stocks. Its most confident stock calls were its worst ones.

**STRONG BUY / STRONG SELL.** Crypto had 5,353 of them. The price moved the called way after 30
minutes 47% of the time. Stocks had 49, and the price moved the called way 41% of the time.

**Would following it have made money?**
- **Crypto, zero fees:** +26% per coin over the year, from about 3,800 trades each. That's
  +0.007% per trade, barely better than entering at random times.
- **Crypto, 0.05% fee per side** (cheaper than any retail app): **−97%**.
- **Crypto, typical app fees:** **−100%**.
- **Stocks:** it lost money even with free trading.

**Did "learning from its own log" fix it? No.** The learning version mostly stopped predicting.
On crypto it called UP or DOWN on 4% of decisions, and those calls were still worse than random.
On stocks, no type of call ever earned the right to be issued, so it made zero calls.

**Why not just do the opposite?** It doesn't help. The average move in the direction of a call was
within ±0.01% for BTC, ETH, SPY and NVDA. That's a tenth of a small fee. *(This is a description
after the fact, not a pre-registered test.)*

**Why it fails.** Over a few minutes, prices move almost randomly, and the moves are smaller than
the fees. Indicators describe what already happened. Anything useful in that is already in the
price. The engine came out slightly *worse* than chance, most likely because very short-term moves
tend to partly reverse, while most of its indicators bet on continuation.

---

## One real call, scored the way the prompt demands

The first STRONG BUY after 14:00 UTC on 2 March 2026. It was picked by that rule, not by how it
turned out.

| BTC-USD at $69,287, regime WEAK BULL, volatility HIGH | 1–5 MIN | 5–30 MIN | 30–120 MIN |
|---|---|---|---|
| call (stated probability, confidence) | UP (74%, 87/100) | UP (70%, 79/100) | UP (69%, 76/100) |
| price at the end of the window | $69,218 | $69,471 | $69,235 |
| result | **PREDICTION FAILED** (went down) | CORRECT | **PREDICTION FAILED** (sideways) |

---

## Results

"Hit" is strict: an UP call is only right if price rose by more than half a normal move for that
window, so a sideways finish counts as a miss. **Shuffled self** is the fair baseline. It uses the
engine's own calls, randomly re-ordered within each day, so it keeps the same mix of UP/DOWN/SIDEWAYS.
"Sign hit" only asks whether price moved the called way at all. Edge = accuracy minus the better of
the two no-skill forecasts ("say what usually happens" and "say what the last h minutes did"),
with a 99.5% day-bootstrap interval.

### Crypto: BTC-USD and ETH-USD, 2025-09-25 → 2026-09-11 (BTC −32.5%, ETH −41.4%)

| config | predictions | up/down share | hit | shuffled self | sign hit | accuracy | climatology | persistence | edge (99.5% CI) |
|---|---|---|---|---|---|---|---|---|---|
| E1 5 min | 202,174 | 51.0% | 26.2% | 28.3% (z −18) | 46.9% | 35.9% | 44.9% | 35.7% | −8.9 pp [−9.5, −8.4] |
| E1 30 min | 202,164 | 51.4% | 25.6% | 30.3% (z −41) | 46.1% | 34.5% | 44.0% | 34.3% | −9.6 pp [−10.3, −8.9] |
| E1 120 min | 202,128 | 53.2% | 24.8% | 33.0% (z −78) | 45.7% | 33.8% | 44.5% | 33.3% | −10.8 pp [−12.0, −9.5] |
| E2 5 min | 202,174 | 2.6% | 27.7% | 29.0% (z −2.2) | 46.4% | 44.5% | 44.9% | 35.7% | −0.3 pp [−0.4, −0.3] |
| E2 30 min | 202,164 | 4.0% | 25.8% | 30.7% (z −10) | 45.6% | 43.3% | 44.0% | 34.3% | −0.7 pp [−0.9, −0.5] |
| E2 120 min | 202,128 | 7.3% | 24.2% | 34.3% (z −30) | 44.5% | 43.3% | 44.5% | 33.3% | −1.3 pp [−1.9, −0.8] |

**Trades.** The 30-minute rules: the prompt's BUY/SELL actions, a 1× ATR stop, a 2× ATR target and
a 30-minute time exit. Returns are averaged per coin.

| | trades | mean trade (random-entry 95th pct) | profit factor | zero fees | 0.05%/side | 0.35%/side |
|---|---|---|---|---|---|---|
| E1 long/short | 7,623 | +0.0067% (+0.0064%) | 1.05 | +26.3% | −97.2% | −100% |
| E1 long-only | 3,617 | — | 1.02 / 1.05 | +6.0% | −82.7% | −100% |
| E2 long/short | 764 | +0.0027% (+0.0179%) | 1.02 | +0.8% | — | −92.7% |

The one near-miss: E1's zero-fee mean trade beat 95.8% of random-entry draws. But its profit factor
(1.05) is under the 1.10 bar, and the per-trade edge is 1/15 of even a 0.1% round trip. Both halves
of the year look the same: hit 26.2% vs 31.1% shuffled (95th pct) in the first half, 25.1% vs 30.1%
in the second, profit factor 1.05 and 1.06.

**Stated probability vs reality** (crypto, 30-minute calls):

| engine said | calls | came true |
|---|---|---|
| UP/DOWN, 50–60% | 56,466 | 25.4% |
| UP/DOWN, 60–70% | 31,562 | 25.4% |
| UP/DOWN, 70–80% | 11,599 | 27.0% |
| UP/DOWN, 80–90% | 381 | 29.4% |
| SIDEWAYS, 50–60% | 33,958 | 42.5% |

**Nothing stands out by market condition** (crypto, 30-minute up/down hit):
- By regime: strong bear 26.5%, strong bull 26.4%, breakdown 26.4%, range 25.6%, weak bear 25.4%,
  breakout 25.4%, weak bull 24.4%, reversal 24.1%.
- By volatility: high 26.8%, low 25.7%, normal 25.3%.
- By signal mix: pure-momentum calls, the most common kind, hit 24.9% (UP) and 26.5% (DOWN).

**Targets and excursions** (crypto, 30 minutes):
- The "most likely target" missed the actual price by 0.32% on average. Assuming "no change" missed
  by 0.26%.
- The best move in the called direction averaged +0.32% and the worst −0.29%. That's symmetric,
  which is what no edge looks like.
- 28% of up/down calls touched their invalidation level.

### Stocks: SPY, QQQ, NVDA, TSLA, 19 sessions, 2026-08-14 → 2026-09-10

| config | predictions | up/down share | hit | shuffled self | sign hit | accuracy | climatology | persistence | edge (99.5% CI) |
|---|---|---|---|---|---|---|---|---|---|
| E1 5 min | 5,852 | 53.4% | 25.2% | 29.3% (z −6.8) | 46.9% | 34.2% | 45.0% | 36.4% | −10.9 pp [−15.0, −6.8] |
| E1 30 min | 5,472 | 53.9% | 22.8% | 30.7% (z −15) | 46.4% | 33.4% | 46.8% | 34.4% | −13.5 pp [−16.7, −10.4] |
| E1 120 min | 4,104 | 54.7% | 19.8% | 25.1% (z −13) | 52.3% | 38.5% | 57.9% | 33.5% | −19.4 pp [−28.1, −11.9] |
| E2 (all) | | 0.0% / 0.0% / 0.3% | — | — | — | = climatology | | | no calls at 5 and 30 min; 11 at 120 min, 0 correct |

**Trades**, E1, 30-minute rules. There were 155 trades across the 4 stocks. The profit factor was
0.88 with zero fees. The mean trade was −0.013%, while random entries averaged +0.006%, so the
engine sat at the 20th percentile. Per stock:

| | trades | zero fees | 0.02%/side | buy & hold, same 19 days |
|---|---|---|---|---|
| SPY | 38 | −0.6% | −2.1% | −2.6% |
| QQQ | 31 | −0.1% | −1.4% | −3.3% |
| NVDA | 45 | −1.1% | −2.8% | −3.6% |
| TSLA | 41 | −0.3% | −1.9% | +5.2% |

Of 16 book × stock combinations, 2 were positive after costs. Both were TSLA long-only, in a window
where TSLA itself rose 5.2%. That's about what chance produces.

**Stated probability vs reality** (stocks, 30-minute calls): 55% stated → 24% came true,
64% → 21%, 73% → 19%. By confidence bucket, the 75–100 calls hit 18.4%. The 33–49 calls hit 24.6%.

---

## Gates

| | G1 beats shuffled self | G2 beats no-skill | G3 profit, zero fees | G4 profit, retail fees | G5 both halves |
|---|---|---|---|---|---|
| crypto E1 / E2, every horizon | fail | fail | fail (PF 1.05 / 1.02) | fail | fail |
| stocks E1 / E2, every horizon | fail | fail | fail (PF 0.88 / no trades) | fail | fail |

**G0 integrity: 9/9.**
- Indicators return textbook values.
- A synthetic random walk passes no gate at any horizon.
- A synthetic series with planted drift is detected: hit 50.7% vs 44.6% at the shuffled 99.5th
  percentile, profit factor 2.03 on 416 trades.
- The shuffle placebo's exact moments match Monte Carlo.
- Truncating the data never changes an earlier decision (4 cuts on synthetic crypto, 6 on real SPY).
- The learning filter and the climatology control only use outcomes that were already known.

## Data notes

- BTC is missing 831 minutes and ETH 835 (0.16%), all forward-filled. The largest gap is a real
  Coinbase outage, 2026-05-08 01:16–07:48 UTC, re-fetched and confirmed.
- Stocks are missing 1 minute each.
- The crypto year fell hard. The result doesn't depend on that: strong-bull and strong-bear regimes
  score the same.
- **Choices made without registration:**
  - With no resolved history yet, the climatology control calls SIDEWAYS.
  - The persistence control at a stock's 09:35 decision reaches back into the prior session.
  - The example call was picked by the "first STRONG BUY after a timestamp" rule.
  - The "do the opposite" numbers are after the fact.
- **Data catches worth reusing:**
  - Yahoo 1m requests must *start* strictly inside the last 30 days (5m/15m: 60), or Yahoo returns 422.
  - Coinbase's candle window includes both ends (300 bars = s … s+299 min).
  - `urllib` fails SSL on this machine's Python 3.14; use `requests` + `certifi`.

## What this does and doesn't show

- **It shows** that this engine can't predict the next 5, 30 or 120 minutes on these six markets.
  The engine means the prompt's rules, written down. Its stated probabilities are made up: about
  70% claimed, about 25% real.
- **It doesn't rule out** every chart-reading approach. It does put the burden of proof on any
  "better judgment" version. The honest test is a forward log: timestamped calls written *before*
  the move, scored with `eng_score.py`'s rules. A few hundred calls would show whether it beats 50%.
- **Program rule:** a FAIL gets no live signal tool and no paper trading.

## Files

- `PREREG_ENGINE.md`: the frozen rules and gates
- `intraday.py` (data), `eng_tf.py` (timeframes), `eng_ind.py` (indicators), `eng_core.py` (the engine),
  `eng_score.py` (scoring, controls, placebo, bootstrap), `eng_trade.py` (execution), `run_engine.py`,
  `selftest_engine.py`
- `results/engine.json`, `results/engine_run.log`, and `results/engine_log_<SYM>.csv.gz`: the
  prompt's full prediction log, with every call, its outcome, and its best and worst excursion
