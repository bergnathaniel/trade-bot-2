# Pre-Registration: Phase 7, IBS mean reversion (H42–H43)

**Frozen:** 2026-09-12, before any Phase-7 return, signal or placebo was computed.
- **Data availability, the only thing checked:** the Yahoo adjusted daily OHLC already cached for
  Phases 4–6. SPY from 1993-01, QQQ from 1999-03.
- **Integrity:** `run_phase7.py` prints this file's SHA-256. Changes go in a dated *Amendments*
  section.

---

## Why these

The user pasted a strategy vendor's marketing and asked to "try those". It named two strategies:

- **A "Nasdaq volatility-based model" on QQQ.** The vendor claims 189 trades, 1.6% average gain,
  80% wins, profit factor 3.1, 12.1% CAGR, 11% time in market and −19.5% max drawdown, after
  0.03% per trade.
  - **It can't be tested.** Its rules are sold, not published.
  - **No stand-in rule is invented.** Trying rules until one matches the advertised numbers would be
    curve-fitting. The vendor's figures are only set against QQQ buy-and-hold (section D).
- **"IBS Swing Trade in the S&P 500."** The paste gave no rules for it. The rule below is the
  standard published one.
  - IBS (internal bar strength) = (close − low) / (high − low).
  - The idea: in equity-index ETFs, a close near the day's low tends to be followed by a rebound.
  - It was discussed on trading blogs from about 2010 and written up by Pagonidis, "The IBS Effect:
    Mean Reversion in Equity ETFs" (NAAIM, c. 2013).
  - Not tested in this project before.
- **H43 applies the public IBS rule to QQQ,** the vendor's instrument. It is **not** the vendor's
  volatility model.

**Prior: low to moderate.** Short-term reversal in index ETFs is one of the better-documented daily
effects. But much of a one-day rebound can happen overnight, before a fill at the next open is
possible. That is exactly what the execution convention below tests.

---

## A. Conventions

- **Engine and accounting:** as in Phases 4–6. Returns are excess of cash (`^IRX`), on adjusted bars.
- **Costs** per side: 1 bp for SPY and QQQ. G4 doubles them.
- **Execution (gated):** the decision needs close t, so the fill is at the open of session t+1
  (PROGRAM.md: anything derived from a closing price).
- **Seller's fills (reported only, never gated):**
  - The same position is held from close t itself, at 3 bp per side ("0.03% per trade").
  - A backtest cannot know a close before it prints, so this version assumes information a trader
    doesn't have when the order goes in.
- **IBS inputs:** the session's adjusted high, low and close. All three are rescaled by the same
  factor, so IBS is unchanged by adjustment.
  - A bar with high = low gives no signal (IBS = 0.5).
  - IBS is clipped to [0, 1]. The number of bars that needed it is reported.

---

## B. Hypotheses

### H42: IBS swing trade, SPY

- **Rule:** long only, all in.
  - Flat → long at a close with IBS < 0.2.
  - Long → flat at a close with IBS > 0.8.
- **Sample:** from 1993-02-01. Out-of-sample is 2014-01-01 onward.
- **G2 benchmark:** SPY excess.
- **Neighbours (4):**
  - entry at IBS < 0.1
  - entry at IBS < 0.3
  - exit at the first close above the previous session's high, instead of IBS > 0.8
  - hold one session only: long for the session after each close with IBS < 0.2
- **Placebo (G7):** the whole daily long/flat series, circularly shifted by a random 63–1,260
  sessions. This keeps time in the market, the number of trades and their lengths. 1,000 draws.
- **Look-ahead check:** truncation recomputes every position with all bars after the cut removed.
  It is a real test, lag 0.

### H43: IBS swing trade, QQQ

- **Rule, neighbours, placebo and look-ahead check:** as H42, on QQQ.
- **Sample:** from 1999-04-01. Out-of-sample is 2014-01-01 onward.
- **G2 benchmark:** QQQ excess. Holding the same ETF is the no-signal control.

---

## C. Gates

G1–G10 as in Phases 1–6, with these specifics:

- **G3 trial count:** N = **114**, which is 112 plus these 2. σ_SR = max(0.289, stdev of the two
  out-of-sample Sharpes). Sensitivity, not gated: N = 2 and N = 200.
- **G8, G9, G10:** G8 PASS; G9 n/a (no live fund runs the rule); G10 PASS.
- **Classification:** as in Phase 2. Only a PASS proceeds to a paper log.

**Registry rows:** P7-H42, P7-H43.

---

## D. Reported (never gated)

- **A vendor-style table** for each ETF over its whole sample, under both fills (seller's same-close
  at 3 bp; next open at 1 bp):
  - trades, average gain per trade, win ratio, profit factor
  - CAGR after costs, with no interest on idle cash
  - time in market
  - CAGR ÷ time in market, the vendor's "risk-adjusted return"
  - max drawdown
  - buy-and-hold CAGR and max drawdown over the same window
- **Before and after 2014** (next-open fills): number of trades, average trade and win ratio.
- **The undisclosed Nasdaq volatility model:** the vendor's figures next to QQQ buy-and-hold from
  1999-04 and from 2006.

---

## Amendments

(none)
