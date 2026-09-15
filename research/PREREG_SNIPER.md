# Pre-Registration: the "Autonomous Trading & Market-Sniping System" (config family SN)

**Frozen:** 2026-09-11, before any setup signal, score, trade outcome or return was computed.
Only data *availability* was probed (bar counts, date ranges, release-calendar pages).
**Integrity:** `run_sniper.py` prints this file's SHA-256 with every result. Never edit this text
after results exist. Changes go in a dated *Amendments* section with the reason and are reported
alongside the original spec.

---

## Why this test

On 2026-09-11, a few hours after the "Continuous Market Prediction Engine" prompt failed
(`ENGINE_RESULTS.md`), the user pasted a longer prompt: Claude as the intelligence layer of an
autonomous trading and "market-sniping" system. Much of it repeats the engine prompt: UP / DOWN /
SIDEWAYS probabilities for 1–5, 5–30 and 30–120 minutes, multi-timeframe regime reading, and the
same indicators. **That part is already tested and failed, so it is not re-tested here.**

What is new is a claim about *trading* rather than *predicting*. It says to optimize expectancy,
not accuracy, and to trade only when the math is favorable. It adds:

1. **Named entry setups** for each regime: breakout, breakout retest, support/resistance
   rejection, VWAP reclaim/rejection, trend pullback, range mean reversion, structure break,
   liquidity sweep reversal. A "don't chase" rule.
2. **Sniper selectivity:** eight 0–10 checks (trend, momentum, volume, structure, liquidity,
   entry quality, risk/reward, regime) summed to /100. Trade only at ≥ 70, high conviction at ≥ 85.
3. **An exit engine:** stop at structure, TP1 / TP2 / TP3, breakeven and trailing stops, thesis
   invalidation, time exit.
4. **A risk engine:** size = risk ÷ stop distance, 0.25–1% account risk, 2% daily loss limit,
   correlated positions counted as one bet.
5. **A scanner:** rank candidates across a watchlist, with relative strength against the market,
   and trade only the best.
6. **Cost, slippage and catalyst rules:** skip trades that costs would damage, and stand aside
   around scheduled events. Don't trade on stale data.
7. **Performance feedback:** measure which setups make money and favor those.

Claude can't run this live. There is no data feed, Claude doesn't place trades, and a live
BUY/SHORT card with entry, stop and size is personalized trading advice. A model's chart judgment
can't be backtested either, because the model can't unsee what happened next. What *can* be tested
is the system the prompt describes, written as fixed rules and run at every 5-minute decision point
in the free minute data. The question is the prompt's own: *"Would repeatedly taking this exact
type of trade have produced positive expectancy after fees, spread and slippage?"*

**Prior: low.** Exits and position sizing cannot create an edge on their own. On a price with no
predictable drift, any stop / target / trailing plan has about zero expected profit before costs
and a loss after them. Any edge has to come from the entries. The entries here are built from
indicator families that already failed on minute, hourly and daily bars. The random-entry control
(G2) isolates exactly this.

---

## A. Data

| group | symbols | 1-minute bars | window | 5m / 15m / 60m bars |
|---|---|---|---|---|
| crypto | BTC-USD, ETH-USD, SOL-USD, XRP-USD, DOGE-USD | Coinbase Exchange public candles | 2025-09-11 00:00 → 2026-09-11 00:00 UTC; first 14 days are warm-up | built from the 1m bars |
| stocks | SPY, QQQ, IWM, DIA, AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, AVGO, AMD, NFLX, JPM, XOM | Yahoo 1m with pre/post, snapshot pulled 2026-09-11 (free limit: last 30 days) | full regular sessions through 2026-09-10; first full session is warm-up | native Yahoo regular-session bars, same snapshot |

- Bar conventions, forward-filling and session handling are exactly `eng_tf.py`'s, as in the engine
  test. A bar is usable only once closed.
- `^VIX` was pulled in the same snapshot. No rule uses it.
- A symbol whose data is missing or has fewer than 15 complete evaluation sessions (stocks) or
  300 days (crypto) is dropped and reported. This rule is set before any result.
- **Stale data:** if any of the last 5 one-minute bars before D is forward-filled (volume 0 and
  O = H = L = C), the decision is "DATA STALE — DO NOT TRADE".
- **Scheduled catalysts:** CPI and Employment Situation releases at 08:30 ET, taken from the BLS
  news-release archive (`bls.gov/bls/news-release/cpi.htm`, `empsit.htm`; release date = the
  archive PDF's date). FOMC statements at 14:00 ET, taken from `sources.fomc_statement_dates()`.
  Unpublished releases (the October 2025 shutdown) are not events.

---

## B. Shared machinery

**Decision times:** every 5 minutes on the clock, at the close of 5-minute bar *i*: crypto around
the clock; stocks 09:35 … 15:25 ET (no entries later). At D the system sees only closed bars.

**Indicators:** the engine test's, unchanged (`eng_core.TF`). EMA 9/21/50/200, RSI 14, MACD
histogram, ATR 14, Bollinger 20/2σ, volume SMA 20, prior-20-bar high/low, 5-bar structure, session
VWAP with ±2σ bands, ADX 14 on 60m. **Regime** = the engine's classifier (STRONG / WEAK BULL / BEAR,
RANGE, BREAKOUT, BREAKDOWN, REVERSAL, UNKNOWN), from the last closed 60m and 15m bars. REVERSAL's
direction is the sign of (60m close − 60m EMA200).

Notation for bar *i* on 5m: o, h, l, c, v; A = ATR14(5m) at *i*; PH20 / PL20 = highest high /
lowest low of the 20 bars before *i*; s = +1 long, −1 short. Short rules mirror long rules.

**Key levels at D** (all known at D):
- previous session high / low (crypto: previous UTC day)
- this session's high / low *before* bar *i*
- premarket high / low (stocks)
- opening range high / low = the first three 5m bars of the session (stocks; used only from the
  fourth bar on)
- session VWAP at *i*
- round numbers: the multiples of step = 10^(floor(log10 c) − 1) just below and above c
- 60m high / low = highest high / lowest low of the last 20 closed 60m bars
- 5m PH20 / PL20 (swing levels, used by setups and "room", **not** by the liquidity score)

**Benchmark** (trend check and relative strength): BTC-USD for the other coins, SPY for the other
stocks. BTC-USD and SPY have none.

**News-driven session (stocks):** the opening gap vs the prior close is ≥ 2% (≥ 1% for SPY, QQQ,
IWM, DIA). On those sessions the fade setups (SRR, SWP, MRV) are blocked.

**Catalyst blackout:** no entries from 30 minutes before to 30 minutes after a scheduled catalyst.

---

## C. The eight setups (long; short mirrors)

Every setup yields an ideal entry P\*, a structural stop X, and an invalidation price V. A long
exits early if a 5m bar that closes after entry closes below V. P\*, X and V are fixed at D.

"Long blocked in" regimes are hard blocks, as in the prompt's "strategy selection must depend on
the regime". Shorts are blocked in the mirror regimes.

| code | setup | conditions on bar *i* | P\* | X | V | long blocked in |
|---|---|---|---|---|---|---|
| BRK | breakout | c > PH20; v ≥ 1.5 × vol SMA20; compression: PH20 − PL20 ≤ 5 × ATR14(5m) at *i*−1 | PH20 | min(l, PH20) − 0.1A | PH20 − 0.1A | STRONG BEAR, BREAKDOWN |
| RET | breakout retest | the latest bar *j* in [*i*−12, *i*−2] with c_j > PH20_j and v_j ≥ 1.5 × vol SMA20_j defines K = PH20_j; every close in (*j*, *i*] ≥ K − 0.25A; l ≤ K + 0.25A; c > K; c > o | K | min(l over *j*+1…*i*) − 0.1A | K − 0.25A | STRONG BEAR, BREAKDOWN |
| SRR | support rejection | a support S (key levels below c, or PL20) with S − 0.1A ≤ l ≤ S + 0.25A; close in the top third of the bar's range; lower wick ≥ 1.5 × body. The S closest to l | S | min(l, S) − 0.1A | S − 0.1A | STRONG BEAR, BREAKDOWN, news-driven |
| SWP | liquidity sweep reversal | a level S (same set) with l < S − 0.1A and c > S, plus one confirmation: v ≥ 1.5 × vol SMA20, **or** bullish RSI divergence (l below the lowest low of bars *i*−12…*i*−1, RSI above RSI at that bar). The highest such S | S | l − 0.1A | S − 0.1A | STRONG BEAR, BREAKDOWN, news-driven |
| VWR | VWAP reclaim | c_{i−1} < VWAP_{i−1}; c > VWAP; c > o; bar *i* opens ≥ 25 min after the session anchor; 15m EMA9 ≥ EMA21 | VWAP | min(l over *i*−2…*i*) − 0.1A | VWAP − 0.1A | STRONG BEAR, BREAKDOWN |
| PBK | trend pullback | regime STRONG BULL, WEAK BULL or BREAKOUT; 15m EMA9 > EMA21; l ≤ EMA21 + 0.1A; c > EMA21; c > o; min(l over *i*−5…*i*) ≥ EMA50 − 0.1A; 40 ≤ RSI ≤ 65 (all 5m) | EMA21 | min(l over *i*−5…*i*) − 0.1A | EMA50 − 0.1A | every regime not listed |
| MRV | range mean reversion | regime RANGE; c_{i−1} < lower Bollinger_{i−1}; RSI_{i−1} < 30; c > lower Bollinger; c > o | lower Bollinger | min(l_{i−1}, l) − 0.1A | min(l_{i−1}, l) | every regime but RANGE; news-driven |
| BOS | structure break | at *i*−1: 5m EMA9 < EMA21 or structure = −1; H10 = max(h over *i*−10…*i*−1); c > H10; c > o; v ≥ vol SMA20 | H10 | min(l over *i*−10…*i*) − 0.1A | H10 − 0.1A | STRONG BEAR, BREAKDOWN |

If more than one setup fires at D, the highest score wins. Ties go in table order. Longs are
checked before shorts.

**Stop bounds:** risk at decision = |c − X|. More than 2.0A: no trade (stop too wide). Less than
0.5A: X moves out to c − s × 0.5A.

---

## D. The score (the prompt's section 31)

Eight parts, each 0–10. **Setup score = round(100 × sum / 80).**

1. **Trend alignment** = 10 × mean of four checks (1 / 0.5 / 0):
   (a) 60m: s(c − EMA50) > 0 and s(EMA50 − EMA200) > 0 → 1; one of the two → 0.5; neither → 0.
   (b) 15m EMA9 − EMA21: s × diff > 0.1 × ATR14(15m) → 1; |diff| ≤ that → 0.5; else 0.
   (c) 15m: s(c − EMA50) > 0 → 1, else 0.
   (d) Market: the benchmark's 15m EMA9 − EMA21, scored as in (b). For BTC-USD and SPY, their own
   60m EMA50 slope over 5 bars in direction s → 1, else 0.
2. **Momentum** = 10 × mean of: (a) s(MACD hist_i − hist_{i−1}) > 0 → 1, else 0.
   (b) The last closed 1m bar has s(EMA9 − EMA21) > 0 → 1, else 0. (c) 5m RSI zone. Long:
   50–70 → 1, 40–50 or 70–80 → 0.5, else 0. Short: 30–50 → 1, 50–60 or 20–30 → 0.5, else 0.
3. **Volume** = clip(5 × v / vol SMA20, 0, 10).
4. **Structure** = 10 × mean over 5m and 15m structure of (s × structure = +1 → 1, 0 → 0.5,
   −1 → 0).
5. **Liquidity** (setup at a meaningful level): d = distance from P\* to the nearest key level
   (excluding PH20 / PL20). d ≤ 0.25A → 10; ≤ 0.5A → 7; ≤ 1A → 4; else 0.
6. **Entry quality:** q = s(c − P\*)/A. q ≤ 0.1 → 10; q ≥ 0.75 → 0; linear in between.
7. **Risk/reward:** room = distance from c to the nearest key level or PH20/PL20 beyond
   c + s × 0.1A in the trade direction, capped at 6A. RR = room / risk.
   Score = clip(5 × (RR − 1), 0, 10).
8. **Regime fit:** "with" and "against" are relative to s.

| | strong with (STRONG, BREAKOUT/DOWN) | weak with | RANGE | reversal with | UNKNOWN | reversal against | weak against | strong against |
|---|---|---|---|---|---|---|---|---|
| BRK, BOS | 10 | 7 | 6 | 5 | 3 | 2 | 2 | 0 |
| RET, VWR, PBK | 10 | 7 | 4 | 5 | 3 | 2 | 2 | 0 |
| SRR, SWP, MRV | 6 | 6 | 10 | 7 | 4 | 3 | 3 | 0 |

**Scanner score** (S3 ranking only) = round(100 × (sum + RS) / 90). RS = clip(5 + 5z, 0, 10),
z = s × (60-min return − benchmark 60-min return) / (σ₁ₘ × √60). σ₁ₘ is the engine's 60-bar
1-minute return stdev. The benchmark itself gets RS = 5.

---

## E. Execution, exits and risk (sections 20–30, 36)

- **Entry:** market order at the open of the 1m bar starting at D.
  - **Don't chase:** skip if s(fill − P\*) > 0.5A.
  - Skip if the fill is at or beyond X.
  - R = |fill − X|.
- **Scale-out:**
  - Sell ⅓ at TP1 = fill + s·1R, ⅓ at TP2 = fill + s·2R, ⅓ at TP3 = fill + s·3R.
  - After TP1, the stop moves to breakeven (the fill).
  - After TP2, the stop = max(fill + s·1R, extreme since entry − s·1.0 × A at entry). This is the
    trailing stop, updated from completed bars.
- **Early exits** close the remaining size:
  - Thesis invalidation (a 5m close beyond V) exits at the next 1m open.
  - Time exit at the close of the 120th minute.
  - Stocks exit at the 16:00 close.
  - A catalyst blackout exits at the open of the first 1m bar inside it.
- **Inside one 1m bar (conservative):**
  - A stop gapped through fills at the open.
  - A take-profit fills at its price, never better.
  - If a bar touches the active stop and a take-profit, the stop wins.
  - A new stop level becomes active on the next bar.
- **Costs** per side, on every fill (entry and each partial exit), as a fraction of notional:

  | level | crypto | stocks |
  |---|---|---|
  | free | 0 | 0 |
  | low | 0.05% | 0.01% |
  | retail | 0.35% | 0.02% |
  | 2× retail | 0.70% | 0.04% |

- **Cost veto** (sections 29–30): at a book's cost level c, skip the trade if 2c × price > 0.25 × risk
  at decision. The veto applies when costs would take more than a quarter of the risk. The free book
  has no veto.
- **Trade result in R** = Σ(fraction × s × (exit − fill)) / R − c × (fill + Σ fraction × exit) / R.
- **Sizing:**
  - units = risk% × equity / R, with risk 0.5% for scores 70–84 and 1.0% for 85+.
  - Notional is capped at 1× equity: a cash account, no leverage.
  - Equity used for sizing counts only closed trades.
- **Daily loss limit:** once closed-trade P&L since the day's start reaches −2% of that day's
  starting equity (UTC day or stock session), no new entries that day. Open positions keep their
  exits.
- **One position per symbol.** Signals are ignored while a position is open. There is no trade-count
  cap; the prompt gives no number.

---

## F. Configurations

- **S1 — prompt-faithful, per symbol.** Trade setups scoring ≥ 70.
- **S2 — high conviction only, per symbol.** Trade setups scoring ≥ 85.
- **S3 — scanner portfolio, per group.** One shared account. At each D, rank every S1-qualifying
  candidate in the group by scanner score (ties go in symbol order). Open the best first while
  fewer than 2 positions are open and total open risk stays ≤ 1.0% of equity. No second position
  per symbol. The daily loss limit applies to the shared account.
- **S4 — "favor the setups that make money", per symbol.** S1, plus a filter. A signal of type
  (setup, side) at D is traded only if its **shadow record** qualifies:
  - The shadow record is every S1-qualifying signal of that type across the group's symbols that
    passes the book's cost veto. Each is simulated on its own, ignoring position overlap.
  - Only signals whose exit completed by D count, within the trailing 60 days.
  - The record needs n ≥ 30 and mean R after the book's costs > 0.

Each configuration is simulated at every cost level (a "book"). The veto, the S4 filter, sizing and
the daily limit all depend on the book's costs. Long-only books are reported, not gated.

---

## G. Controls (always printed)

- **Random entries through the identical exit engine** (for G2): each trade in a config's free
  book gets 20 placebo trades on the same symbol.
  - Placebos keep the same side and the same stop and invalidation distances in ATR units, scaled
    by the placebo's own ATR.
  - They use the same TP1–3, breakeven, trailing, time, session and blackout exits.
  - Entry times are drawn uniformly (seed 20260911) from that symbol's eligible decision times in
    the same half of the window. Eligible means warmed up, not stale, not in a blackout, and within
    stock hours.
  - The placebo distribution of the mean R comes from B = 2000 draws, each picking one of the 20
    placebos for every real trade.
- **The same setups below the score gate** (setups scoring < 70, each simulated on its own): does
  the score add anything? Reported.
- **Buy-and-hold** of each symbol over its window. Reported.

---

## H. Gates

Evaluated per configuration, separately for the crypto group and the stock group. Returns are per
symbol account and averaged (S3: the one portfolio). They are never concatenated into an account
nobody had.

- **G0 integrity (precondition, not a result):**
  - The exit engine passes hand-built unit cases.
  - On a synthetic random walk, S1 passes neither G1 nor G2, and the random-entry mean R at zero
    cost lies in [−0.05R, mean + 3 SE]: the exits manufacture no edge.
  - On a synthetic series with planted persistent drift (the engine test's generator, drift 0.15),
    S1's free book passes G2. If it does not, the planted drift may be raised to 0.30. That
    calibrates the synthetic check only and is recorded.
  - Truncation shows no look-ahead in signals, synthetic and real SPY.
  - S4's filter ignores shadow outcomes not yet known at D.
  - If G0 fails, the code is wrong and there is no verdict.
- **G1 profitable at retail costs** (retail book):
  - ≥ 30 trades.
  - Mean R after costs > 0, with the lower end of the 99.5% day-bootstrap interval > 0
    (B = 2000, seed 20260911, resampling entry days).
  - Pooled profit factor in R > 1.10.
  - Average account return > 0.
- **G2 entries beat random** (free book): mean R above the 99.5th percentile of the random-entry
  placebo.
- **G3 survives double costs** (2× retail book): ≥ 30 trades, mean R > 0, average account return > 0.
- **G4 holds in both halves** (first and second half of evaluation days; stocks: sessions). In each
  half separately:
  - ≥ 15 retail-book trades, mean R lower 95% bound > 0, and profit factor > 1.10.
  - Free-book mean R above the placebo's 95th percentile.

**PASS** for a configuration = G1–G4 in both groups. There are 8 evaluations (4 configurations ×
2 groups); the 99.5% level is the Bonferroni allowance at 5%. Program rule unchanged: only a PASS
proceeds to a live paper log. A FAIL never gets a live signal tool.

**Registry rows:** SN-S1, SN-S2, SN-S3, SN-S4.

---

## I. Reported, not gated

The prompt's section 33 table, per setup × side, at free and retail costs:
- trades, win rate, average win and loss in R, expectancy, profit factor, average hold, MFE / MAE
  in R
- by regime; by score bucket (< 70 control, 70–79, 80–84, 85+)
- share of signals blocked by each rule (don't chase, stop too wide, cost veto, daily limit, busy,
  blackout, stale)
- per-symbol account return and max drawdown, with Sharpe and Sortino of daily account returns;
  long-only books

**Example card:** the first S1 trade on BTC-USD after 2026-03-02 14:00 UTC, in the prompt's section
38 format, with its real outcome. It is picked by that rule, not by how it turned out.

---

## J. Limitations, stated in advance

- The prompt allows judgment (reading order flow, drawing zones, weighing news). Rules only
  approximate that. A model reading charts can't be backtested without look-ahead. If the rules
  fail, "better judgment" still has to prove itself with a forward log of calls made before the move.
- There is no order book, volume profile or news content in free OHLCV data. Liquidity is
  approximated by price levels.
- Market orders at the next 1-minute open with flat costs. There is no queue position or partial
  fill. Limit-order entries at the level would look better in a backtest and fill worse live.
- The stock group has about 19 sessions (Yahoo's 30-day limit). The crypto year, with five coins,
  carries the statistical weight.
- The crypto year fell (BTC roughly −32%). Shorts are included because the prompt trades both
  directions. A US beginner generally can't short crypto, so long-only books are reported.
- The symbols are today's large, liquid names. That biases toward assets that stayed liquid, not
  toward any intraday direction.
- Eight setups × 2 sides × regimes × score buckets is a lot of slicing. Section I tables are
  descriptive. A good-looking cell there is not a result.

---

## Amendments

(none)
