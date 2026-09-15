# Pre-Registration: the "Continuous Market Prediction Engine" (config family EN)

**Frozen:** 2026-09-11, before any engine prediction, hit rate or trade return was computed.
Only data *availability* was probed (bar counts and date ranges).
**Integrity:** `run_engine.py` prints this file's SHA-256 with every result. Never edit this text
after results exist. Changes go in a dated *Amendments* section with the reason and are reported
alongside the original spec.

---

## Why this test

On 2026-09-11 the user pasted a prompt asking Claude to act as a live TradingView "prediction
engine": UP / DOWN / SIDEWAYS calls for the next 1–5, 5–30 and 30–120 minutes, built from EMA
9/21/50/200, VWAP, RSI, MACD, ATR, Bollinger Bands, volume, market structure, breakouts, failed
breakouts, candles, gaps, previous-session and premarket levels, weighted by timeframe and market
regime, then turned into STRONG BUY … STRONG SELL actions with entry, stop and target. It also asks
for a running prediction log, scored against the exact timeframe predicted, never hiding misses.

Claude can't be that live engine. There is no data feed. A live BUY/SELL call with entry, stop and
target is personalized trading advice. And a model's chart "judgment" can't be backtested, because
it can't unsee what happened next. What *can* be tested is the engine the prompt describes, written
down as fixed rules, run at every 5-minute decision point in the free minute data, and scored with
the prompt's own log metrics.

New horizon for this project (everything before used daily/hourly bars, sessions or months), not a
new idea: it combines indicator rules that already failed on daily and hourly crypto bars
(`candle_strats_backtest.py`, `more_strats_backtest.py`). Prior: low.

---

## A. Data

| group | symbols | 1-minute bars | window | 5m / 15m / 60m bars |
|---|---|---|---|---|
| crypto | BTC-USD, ETH-USD | Coinbase Exchange public candles (granularity 60) | 2025-09-11 00:00 → 2026-09-11 00:00 UTC (365 days); first 14 days are indicator warm-up | built from the 1m bars |
| stocks | SPY, QQQ, NVDA, TSLA | Yahoo chart API 1m with pre/post (free limit: last 30 days) | every full regular session in that window through 2026-09-10; the first full session is warm-up | native Yahoo bars, regular session: 5m and 15m (last 59 days), 60m (last 729 days) |

- Bars are `[open_time, open, high, low, close, volume]` stamped at the bar's **open**. A bar is
  usable only once it has closed: open + duration, stock bars capped at 16:00 ET.
- Missing crypto minutes are forward-filled (OHLC = previous close, volume 0) and counted; missing
  regular-session stock minutes likewise.
- Stocks: indicators use regular-session bars (09:30–16:00 ET). The 04:00–09:30 ET bars are used
  only for the premarket high/low. Nothing is held or predicted across the close.
- The 2026-09-11 stock session is excluded (incomplete when the data was pulled).

---

## B. The engine — config E1 (fixed rules)

**Decision times:** every 5 minutes on the clock: crypto at UTC minutes divisible by 5; stocks
09:35 … 15:55 ET. At decision time D the engine sees every bar that has closed by D and nothing
else.

**Indicators** (standard defaults, none fitted): EMA 9/21/50/200 (SMA-seeded) · RSI 14 (Wilder) ·
MACD 12/26/9 · ATR 14 (Wilder) · Bollinger 20 bars, 2σ (population σ) · volume SMA 20 · ADX 14
(Wilder) · VWAP anchored at the session start (crypto 00:00 UTC, stocks 09:30 ET) on typical price,
with ±2σ volume-weighted bands.

**Timeframes:** 1m (timing), 5m (immediate), 15m (trend), 60m (regime).

**Votes** (−1 / 0 / +1), each computed on a timeframe's last closed bar:

| family | vote | +1 when | −1 when | timeframes |
|---|---|---|---|---|
| momentum | ema_cross | EMA9 > EMA21 | EMA9 < EMA21 | 1m 5m 15m 60m |
| momentum | ema_stack | close > EMA50 > EMA200 | close < EMA50 < EMA200 | all |
| momentum | macd | histogram > 0 and rising | histogram < 0 and falling | all |
| momentum | rsi | RSI > 55 | RSI < 45 | all |
| momentum | structure | last 5 bars: higher high AND higher low than the 5 before | lower high AND lower low | all |
| momentum | vwap | close > VWAP | close < VWAP | 1m 5m |
| mean-reversion | bb_rsi | close < lower band and RSI < 30 | close > upper band and RSI > 70 | all |
| mean-reversion | vwap_band | close < VWAP − 2σ | close > VWAP + 2σ | 1m 5m |
| breakout | breakout | close > prior-20-bar high and volume > 1.5 × volume SMA20 | close < prior-20-bar low, same volume rule | 5m 15m 60m |
| breakout | failed_break | previous bar closed below its prior-20 low; this bar closes back above that level | mirror (failed breakout) | 5m 15m |
| breakout | prev_session | close > previous session high | close < previous session low | 5m |
| breakout | premarket (stocks) | close > premarket high | close < premarket low | 5m |
| breakout | gap (stocks) | open gapped ≥ 0.25% from prior close and close > today's open | same gap rule and close < today's open | 5m |
| candle | engulfing | bullish engulfing | bearish engulfing | 5m |
| candle | hammer_star | hammer (lower wick ≥ 2× body, upper wick ≤ body) with low ≤ lower band | shooting star, mirror, high ≥ upper band | 5m |

Order flow and volume profile aren't in free OHLCV data and are omitted. Supply/demand and
liquidity are approximated by the prior-high/low levels above.

**Regime** (last closed 60m bar; breakout check on 15m), first match wins:
1. BREAKOUT / BREAKDOWN: 15m `breakout` vote = +1 / −1
2. STRONG BULL: close > EMA50 > EMA200, EMA50 above its value 5 bars earlier, ADX ≥ 25 · STRONG BEAR: mirror
3. RANGE: ADX < 20
4. WEAK BULL: close > EMA200 and EMA50 > EMA200 · WEAK BEAR: mirror
5. REVERSAL: close and EMA50 on opposite sides of EMA200, EMA50 sloping toward the close's side
6. UNKNOWN

**Volatility tag** (reported, not used in votes): ATR14(60m)/close percentile over the trailing 720
(crypto) / 140 (stocks) 60m bars: HIGH ≥ 80th, LOW ≤ 20th, else NORMAL.

**Family weights by regime:**

| regime | momentum | mean-reversion | breakout | candle |
|---|---|---|---|---|
| strong bull / strong bear | 1.5 | 0.5 | 1.0 | 0.5 |
| weak bull / weak bear | 1.0 | 0.75 | 1.0 | 0.5 |
| range | 0.5 | 1.5 | 0.75 | 0.5 |
| breakout / breakdown | 1.0 | 0.25 | 1.5 | 0.5 |
| reversal / unknown | 1.0 | 1.0 | 1.0 | 0.5 |

**Timeframe weights by horizon:**

| horizon h | 1m | 5m | 15m | 60m |
|---|---|---|---|---|
| 5 min (the "1–5 MIN" call) | 1.0 | 1.0 | 0.5 | 0.25 |
| 30 min (the "5–30 MIN" call) | 0.25 | 1.0 | 1.0 | 0.5 |
| 120 min (the "30–120 MIN" call) | 0 | 0.5 | 1.0 | 1.0 |

**Score:** `S_h = Σ(tf weight × family weight × vote) / Σ(tf weight × family weight)` over every vote
that applies to the symbol and timeframe (a 0 vote still counts in the denominator). S ∈ [−1, 1].

**Outputs at D, for each horizon:**
- Call: UP if S ≥ 0.25, DOWN if S ≤ −0.25, else SIDEWAYS.
- Confidence (0–100) = round(100 × min(1, |S| / 0.75)).
- Stated probability of the call: UP/DOWN `0.34 + 0.46 × min(1, |S|/0.75)`; SIDEWAYS `0.34 + 0.26 × (1 − |S|/0.25)`.
- σ = standard deviation of the last 60 one-minute log returns. Expected move = 0.8 σ √h.
  Most likely target = close × (1 ± expected move) in the called direction (SIDEWAYS: close).
  Expected range = close × (1 ± σ√h). Invalidation = close × (1 ∓ σ√h).

**Trading action** (from the 30-minute call; the 120-minute call is the higher-timeframe filter):
- STRONG BUY: 30m call UP, confidence ≥ 75, 120m call UP
- BUY: 30m call UP, confidence ≥ 60, 120m call not DOWN
- SELL / STRONG SELL: mirror
- BULLISH / BEARISH — WAIT FOR BETTER ENTRY: would be BUY/SELL, but close is more than
  1.5 × ATR14(5m) beyond EMA21(5m) in the trade direction → no entry
- HOLD while a position is open; NO TRADE otherwise. Stocks: no entries after 15:25 ET.

**Execution:** enter at the open of the next 1-minute bar (open time D). Stop = entry ∓ 1 × ATR14(5m);
target = entry ± 2 × ATR14(5m) (R/R 1:2); time exit at the close of the 30th minute. If one 1-minute
bar touches both stop and target, the stop counts first. If a bar opens beyond the stop, the fill is
that open. One position per symbol; signals are ignored while it is open. Full notional, no leverage.

**Books:**
- **A (prompt-faithful):** the actions above. Long/short, and long-only (BUY/STRONG BUY only — what a
  cash account can do).
- **B (every call):** every UP/DOWN 30-minute call is a trade, same execution. Used for G3/G4 only
  when Book A has fewer than 100 trades in a group.

**Costs per side** (fraction of price):

| level | crypto | stocks |
|---|---|---|
| free | 0 | 0 |
| low | 0.05% | 0.01% |
| retail | 0.35% (0.30% fee + 0.05% slippage, project convention) | 0.02% |

---

## C. The learning variant — config E2

The prompt's CONTINUOUS LEARNING section. E2 = E1 plus a filter, per symbol. A directional call of
type (horizon, regime, direction, confidence bucket 33–49 / 50–59 / 60–74 / 75–100) is issued only
if, among E1's earlier calls of that type whose outcome was already known at D (call time + h ≤ D),
within the trailing 30 days (crypto) / all prior sessions (stocks):
**n ≥ 50 and hit rate ≥ (how often that outcome happened across all resolved calls in the same window) + 5 percentage points.**
Otherwise the call becomes SIDEWAYS and any trade action becomes NO TRADE.

---

## D. Scoring — the prompt's prediction log

**Outcome** of a call at D: `r = close(D + h) / close(D) − 1`. UP if r > 0.5 σ √h, DOWN if
r < −0.5 σ √h, else SIDEWAYS (σ known at D). Stocks: calls only when D + h ≤ 16:00 ET.

**Log fields:** timestamp, symbol, price, regime, volatility tag, horizon, call, confidence, stated
probability, target, invalidation, S, family contributions, price at D + h, outcome, result
(CORRECT / WRONG), maximum favorable and adverse excursion inside the window, invalidation touched.

**Metrics:** 3-class accuracy · directional hit rate (UP/DOWN calls whose outcome matches) · sign hit
rate (UP/DOWN calls whose return has the called sign) · false-positive rate = 1 − directional hit
rate · false-negative rate = share of UP/DOWN outcomes not called correctly · target error
|actual − target| / price vs a "no change" target · average MFE, MAE · accuracy by regime, volatility
tag, confidence bucket (calibration: stated probability vs realized) and family-sign combination ·
trades, win rate, average trade, profit factor, compounded return per symbol, max drawdown ·
buy-and-hold over the same window.

**No-skill controls (always printed):**
- *Climatology:* always call the outcome that was most common among outcomes resolved in the
  trailing 7 days (crypto) / prior sessions (stocks).
- *Persistence:* call the outcome of the previous h minutes (same band rule).
- *Shuffled self:* the engine's own calls randomly permuted within each day. Exact mean and variance
  of the hit count, normal approximation; checked against Monte Carlo in the self-test.
- *Random entries:* same number of trades, same long/short mix, same exits, entry times drawn at
  random from all decision times, B = 1000.

**Statistics:** bootstrap resampling whole days, B = 2000, seed 20260911. Halves: crypto first/second
half of evaluation days; stocks first/second half of sessions.

---

## E. Gates

Evaluated per variant × horizon, separately for the crypto group and the stock group. Hit counts
are pooled across a group's symbols. Trade returns are computed per symbol and averaged, never
concatenated into one account.

- **G0 integrity (precondition, not a result).** The truncation look-ahead test passes. On a
  synthetic random walk, G1–G3 do not pass. On a synthetic series with planted persistent drift,
  G1 and G3 do pass. If G0 fails, the code is wrong and the run is invalid.
- **G1 beats its own shuffled calls:** directional hit rate above the 99.5th percentile of the
  shuffled-self placebo.
- **G2 beats no-skill forecasts:** 3-class accuracy minus the better of climatology and persistence
  is > 0, with the lower end of the 99.5% day-bootstrap interval > 0.
- **G3 profitable with free trading:** long/short at zero cost: average per-symbol return > 0, pooled
  profit factor > 1.10, mean trade above the 95th percentile of random entries.
- **G4 survives retail costs:** long/short at retail cost: average per-symbol return > 0 and pooled
  profit factor > 1.0.
- **G5 holds in both halves:** G1 (at the 95th percentile) and G3 hold in each half separately.

**PASS** for a variant × horizon = G1–G5 in both groups. G3–G5 use the 30-minute trade books for
every horizon's row (there is one trading rule). Program rule unchanged: only a PASS proceeds to a
live paper prediction log. A FAIL never gets a live signal tool.

The 99.5% thresholds in G1/G2 are a Bonferroni-style allowance for 12 evaluations
(2 variants × 3 horizons × 2 groups) at 5%.

**Registry rows:** EN-E1-H5, EN-E1-H30, EN-E1-H120, EN-E2-H5, EN-E2-H30, EN-E2-H120.

---

## F. Limitations, stated in advance

- The prompt allows judgment (drawing zones, reading order flow). Rules only approximate that. A
  model reading charts can't be backtested without look-ahead. If the rules fail, "better judgment"
  still has to prove itself with its own forward log.
- About 19 stock sessions (Yahoo's 30-day limit) means wide intervals for stocks. The crypto year,
  about 100k decisions per symbol per horizon, carries the statistical weight.
- The crypto year was a falling market (BTC roughly $114k → $77k). Results are broken out by
  regime to show whether that matters.
- The symbols are today's popular ones. That biases toward assets that stayed liquid, not toward
  any short-term direction.

---

## Amendments

(none)
