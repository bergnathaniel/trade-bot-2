# The "Autonomous Trading & Market-Sniping System": tested

**Date:** 2026-09-11 · **Rules frozen before any result:** `PREREG_SNIPER.md` (sha256 `183fa522…f454`)
**Rerun:** `python3 research/run_sniper.py` (about 35 s with cached data)
**Verdict: FAIL.** All 4 configurations fail every gate in both the crypto and the stock group.

---

## In plain English

**What was tested.** This prompt repeats the prediction engine that already failed
(`ENGINE_RESULTS.md`), so that part wasn't run again. The new part is the trading layer on top.
It was written down as fixed rules:
- 8 named entry setups: breakout, breakout retest, support/resistance rejection, liquidity sweep,
  VWAP reclaim, trend pullback, range mean reversion, structure break
- the 8-part score out of 100: trade only at 70+, "high conviction" at 85+
- "don't chase"
- a stop at structure; take ⅓ profit at each of three targets; breakeven and trailing stops
- exit when the reason for the trade disappears
- 0.5–1% account risk per trade, a 2% daily loss limit, no leverage
- skip trades that fees would damage, and stand aside around CPI, jobs and Fed announcements
- a scanner that trades only the best-ranked names (config S3)
- "favor the setups that actually make money" (config S4)

It checked every 5 minutes for a year on Bitcoin, Ethereum, Solana, XRP and Dogecoin, about
100,000 decisions per coin. It also ran on 16 big US stocks and ETFs for the 19 days of free
1-minute data.

**How to read "R".** R is what a trade risks: the distance to its stop. If you risk $50 a trade,
+0.10R means +$5 per trade on average, and −1R is a full $50 loss.

**Did the setups pick better moments than random? No.** The fair test takes the same trades, with
the same stops, targets, trailing stops and exits, but enters at random times.
- **Crypto:** the setups averaged **+0.000R** per trade over 12,418 trades. Random entry times
  through the same exits averaged +0.012R. The setups did worse than 90% of the random draws.
- **Stocks:** the setups averaged −0.008R; random times averaged −0.007R.

**Did the 70/100 score mean anything? No.** On crypto, signals scoring under 70 averaged
+0.024R. Scores of 70–79 averaged +0.016R, 80–84 averaged −0.040R, and "high conviction" 85+ averaged
−0.016R. A higher score did not mean a better trade.

**Would it have made money?**
- **Crypto, zero fees:** about break-even. +1.9% per coin over the year, from about 7 trades a day.
- **Crypto, 0.05% fee per side** (cheaper than any retail app): **−28% per coin**. The watchlist
  version lost **68%**.
- **Crypto, typical app fees (0.35% per side):** the prompt's own cost rule blocked **18,185 of
  18,188** trades. On 5-minute setups the stop is smaller than the fee to get in and out, so the
  rules say don't trade. That's the right call, and it makes $0.
- **Stocks, realistic costs:** lost money. 152 trades averaged −0.17R, and for every $1 won,
  $1.47 was lost.

**Did the risk management help?** It kept each loss small, which is its job. It can't create a
profit. Random entries through these exact exits made about 0R before fees. Stops, targets and
position size decide *how* you win or lose. *Whether* you come out ahead depends only on the
entries, and these entries had no edge.

**Did "favor what works" fix it? No.** On crypto it switched itself off once fees were counted.
Its best-looking result was 22 stock trades at +0.18R, from 19 days of data. That's too few
trades to mean anything: the plausible range of its true average still goes below −0.29R, and it
didn't clear the random-entry bar. Numbers like that turn up by chance when results are sliced
many ways.

**Why it fails.** Same reason as the engine. Over a few minutes, prices move almost randomly, and
the moves are small compared with fees. Every setup is built from what price already did. Being
pickier (the score), exiting smarter (scale-outs, trailing stops) and sizing carefully all happen
*after* the entry decision. None of them can add information the entry didn't have.

---

## One real trade, in the prompt's card format

The first S1 trade on BTC-USD after 14:00 UTC on 2 March 2026. It was picked by that rule, not by
how it turned out. It happened to win; the average of all 12,418 was +0.000R.

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SYMBOL: BTC-USD      2026-03-02 15:05 UTC
PRICE: $67,280.10
MARKET REGIME: BREAKOUT
HIGHER TIMEFRAME: BULLISH      IMMEDIATE TREND: BULLISH
SETUP: liquidity sweep reversal      SETUP SCORE: 78/100
  trend 6.2, momentum 6.7, volume 10.0, structure 7.5, liquidity 10.0, entry 9.3, risk_reward 6.4, regime 6.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ACTION: BUY
ENTRY: $67,286.05  (ideal $67,236.36)
STOP: $66,963.39
TP1: $67,608.71   TP2: $67,931.36   TP3: $68,254.02
RISK/REWARD: 1:3 to TP3      ACCOUNT RISK: 0.5%
POSITION SIZE: 0.148619 units on a $10,000 account
INVALIDATION: a 5-minute close below $67,206.74
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WHAT HAPPENED: exit 'tp3' after 8 min; take-profits hit: 3
RESULT: +2.00R with no fees; blocked by the prompt's own cost rule at retail fees
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

The stop was 0.48% away. A round trip at app fees costs 0.70%, which is 1.5R before the trade
even starts.

---

## Results

### Crypto: BTC, ETH, SOL, XRP, DOGE, 2025-09-25 → 2026-09-10

Buy & hold over the same window: BTC −32.5%, ETH −41.4%, SOL −53.5%, XRP −54.5%, DOGE −65.7%.

**Setups vs random entry times** (zero fees, identical exits):

| config | trades | mean R | random entries, mean | random, 99.5th pct | beat this share of random draws |
|---|---|---|---|---|---|
| S1 score ≥ 70 | 12,418 | +0.000 | +0.012 | +0.033 | 10% |
| S2 score ≥ 85 | 2,840 | −0.017 | +0.014 | +0.061 | 4% |
| S3 scanner portfolio | 9,033 | +0.007 | +0.013 | +0.039 | 29% |
| S4 favor what works | 6,220 | +0.006 | +0.020 | +0.054 | 12% |

Both halves look the same. S1's first half was −0.005R against a random 95th percentile of
+0.037R; its second half was +0.005R against +0.029R.

**By fee level.** Each cell shows trades, mean R after fees, and account return. Account return
is averaged per coin; S3 is one shared portfolio.

| config | no fees | 0.05% / side | 0.35% / side (retail) | 0.70% / side |
|---|---|---|---|---|
| S1 | 12,418 · +0.000R · +1.9% | 2,194 · −0.154R · −28.0% | 3 trades (cost rule blocked 18,185) | 3 · −0.101R |
| S2 | 2,840 · −0.017R · −2.3% | 552 · −0.195R · −11.1% | 0 | 0 |
| S3 | 9,033 · +0.007R · +16.4% | 1,727 · −0.147R · −68.4% | 3 | 3 |
| S4 | 6,220 · +0.006R · +2.9% | 81 · −0.302R · −2.6% | 0 | 0 |

- **Max drawdown at 0.05%/side:** S1 −30% per coin, S3 −69%.
- **Long-only with no fees** (what a US cash account can do): S1 −0.017R per trade, −2.6% per coin;
  S3 −8.8%.

**Score buckets.** Every signal simulated on its own, with no fees.

| score | signals | mean R | win rate | profit factor |
|---|---|---|---|---|
| under 70 | 31,666 | +0.024 | 45% | 1.05 |
| 70–79 | 8,609 | +0.016 | 43% | 1.04 |
| 80–84 | 2,482 | −0.040 | 41% | 0.91 |
| 85+ | 3,080 | −0.016 | 41% | 0.96 |

**Setups.** Score ≥ 70, each signal simulated on its own, with no fees. At 0.35% per side the cost
rule blocks every one of them.

| setup | longs: trades, mean R | shorts: trades, mean R |
|---|---|---|
| liquidity sweep reversal | 4,157, −0.026 | 5,064, +0.022 |
| breakout | 1,046, −0.031 | 1,450, −0.027 |
| VWAP reclaim / rejection | 488, +0.040 | 661, +0.080 |
| trend pullback | 207, −0.068 | 373, +0.044 |
| breakout retest | 216, −0.151 | 211, +0.040 |
| support / resistance rejection | 114, +0.001 | 150, +0.038 |
| structure break | 15, −0.158 | 15, +0.081 |
| range mean reversion | 2, +2.000 | 2, −0.333 |

- The best large slice is VWAP-rejection shorts at +0.080R. It is 1 of 16 slices, and it is about
  a seventh of what a 0.05% fee costs on these stops (about 0.56R per trade).
- Shorts did slightly better than longs in a year when every coin fell 32–66%.

**Where S1's trades ended** (no fees; average hold 13 minutes, win rate 42%):

| exit | share of trades |
|---|---|
| thesis invalidated | 29% |
| stop | 28% |
| breakeven stop | 20% |
| trailing stop | 11% |
| third target | 9% |
| gapped through the stop | 2% |
| time or news blackout | under 1% |

**Why S1's qualifying signals weren't traded:**
- No fees: don't chase 3,335; already in a trade 2,380; daily loss limit 56.
- Retail fees: the cost rule, 18,185.

**By market regime** (S1, no fees):

| regime | trades | mean R |
|---|---|---|
| range | 3,976 | −0.014 |
| strong bear | 1,987 | +0.052 |
| weak bear | 1,346 | −0.004 |
| strong bull | 1,210 | −0.020 |
| breakdown | 1,113 | −0.020 |
| reversal | 970 | −0.014 |
| breakout | 950 | −0.002 |
| weak bull | 851 | +0.031 |

The best, +0.052R, is under a third of what a 0.05% fee costs per trade here (about 0.18R).

### Stocks: 16 names, 19 sessions, 2026-08-14 → 2026-09-10

SPY, QQQ, IWM, DIA, AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, AVGO, AMD, NFLX, JPM, XOM.

**Setups vs random entry times** (zero fees, identical exits):

| config | trades | mean R | random entries, mean | random, 99.5th pct | beat this share of random draws |
|---|---|---|---|---|---|
| S1 | 348 | −0.008 | −0.007 | +0.129 | 49% |
| S2 | 50 | −0.002 | +0.052 | +0.414 | 35% |
| S3 | 210 | +0.017 | −0.006 | +0.163 | 63% |
| S4 | 56 | +0.192 | −0.014 | +0.288 | 95% |

**Retail costs** (0.02% per side):

| config | trades | mean R | 99.5% lower bound | profit factor | account |
|---|---|---|---|---|---|
| S1 | 152 | −0.168 | −0.396 | 0.68 | −0.4% per stock |
| S2 | 23 | −0.130 | −0.709 | 0.73 | −0.0% |
| S3 | 125 | −0.207 | −0.422 | 0.63 | −4.8% (portfolio) |
| S4 | 22 | +0.177 | −0.291 | 1.42 | +0.0% |

- Account percentages are small because each trade risks 0.5% and there are few trades. R is the
  better yardstick.
- S1 lost in both halves: −0.248R over 73 trades, then −0.095R over 79.
- Score buckets (no fees): under 70 −0.037R (1,695); 70–79 −0.017R (279); 80–84 −0.073R (57);
  85+ +0.004R (51).
- Breakouts were the worst S1 setup: −0.32R over 51 trades.

---

## Gates

| | G1 profit at retail costs | G2 entries beat random | G3 survives 2× costs | G4 both halves |
|---|---|---|---|---|
| crypto S1–S4 | fail (≤ 3 trades: the cost rule blocks nearly everything) | fail (4th–29th pct; bar is 99.5th) | fail | fail |
| stocks S1–S4 | fail (S1–S3 lose; S4 has 22 trades, lower bound −0.29R) | fail (35th–95th pct) | fail | fail |

**G0 integrity: 21/21.**
- The exit engine gets 12 hand-built cases right: stop wins a tie, gaps, all three targets,
  breakeven, trailing, time, session close, blackout, invalidation, costs, don't chase.
- The daily loss limit, the sizing cap and the scanner's position cap work.
- On a random walk nothing passes. Random entries through the exits average +0.004R (SE 0.021).
- A planted drift is detected. Strength 0.15 was not: a 60-day synthetic run yields only about 100
  trades. As the pre-registration allows, it was raised to 0.30, which scored +0.73R against a
  random 99.5th percentile of +0.56R.
- Truncating the data never changes an earlier signal (4 cuts on synthetic data, 6 on real SPY).
- The S4 filter only uses trades that had already closed.

## Data notes

- **Catalysts.** The crypto window had 30: 11 CPI, 11 jobs and 8 FOMC.
  - CPI and jobs dates come from the BLS archive (release date = the PDF's date). FOMC dates come
    from the Fed calendar.
  - The October 2025 CPI and jobs reports were never published (government shutdown). September's
    came out on Oct 24 (CPI) and Nov 20 (jobs).
  - 336 decisions per coin fell inside blackout windows.
  - Stocks had none: there was no FOMC meeting in the window, and CPI and jobs land before the open.
- **Stale data.** DOGE-USD had 10,928 decisions skipped, because Coinbase doesn't return minutes
  with no trades. The other coins had 200–260, mostly from the 2026-05-08 Coinbase outage.
- **Stock snapshot.** The 12 extra stocks were pulled at 21:30 UTC on 2026-09-11, the same Yahoo
  snapshot date as SPY/QQQ/NVDA/TSLA. `intraday.yahoo` stamps snapshots by UTC date, so a same-day
  pull has to finish before midnight UTC.
- **Choices made without registration, and after-the-fact descriptions:**
  - The example card uses the no-fee book, because the retail crypto book had only 3 trades.
  - Random entries through these exits earned slightly above zero on crypto (+0.012R). That is a
    description, not a test, and it is about a fifteenth of a 0.05% fee.
  - The "fraction of a fee" comparisons for single slices are also after the fact.

## What this does and doesn't show

- **It shows** that the prompt's trading layer has no edge on five big coins over a year or on 16
  big stocks over 19 days. That layer is the setups, the score, the exits, the sizing, the daily
  limit, the cost and news rules, the ranking and "favor what works".
  - The score doesn't separate good trades from bad ones.
  - The exits and risk rules control how big the losses are. They can't make entries with no edge
    profitable.
- **It doesn't rule out** a person's (or Claude's) chart judgment. That still needs a forward log:
  timestamped calls written *before* the move. The "Beat the Coin" journal does exactly that.
  Nineteen stock sessions is short, so the crypto year carries the weight.
- **Program rule:** a FAIL gets no paper trading and no live signal tool.

## Files

- `PREREG_SNIPER.md`: the frozen rules and gates
- `sn_setups.py`: catalysts, key levels, the 8 setups, the score
- `sn_exec.py`: exit engine, books, random-entry placebo, statistics
- `run_sniper.py`, `selftest_sniper.py`
- Result files:
  - `results/sniper.json`
  - `results/sniper_run.log`
  - `results/sniper_selftest.log`
  - `results/sniper_trades_crypto.csv.gz` and `results/sniper_trades_stocks.csv.gz`: every S1
    trade at no fees and at retail fees, in the prompt's log format
