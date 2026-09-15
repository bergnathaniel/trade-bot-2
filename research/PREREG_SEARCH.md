# Pre-Registration: an honest strategy search on the sniper system (config family SR)

**Frozen:** 2026-09-11, before any search result was computed. The data and the sniper rules are
the ones in `PREREG_SNIPER.md`. That test's results (all FAIL) were known when this was written.
Nothing in this search's grid was chosen by looking at those results slice by slice.
**Integrity:** `run_search.py` prints this file's SHA-256 with every result. Never edit this text
after results exist. Changes go in a dated *Amendments* section.

---

## Why this test

After the sniper system failed, the user asked: *"make it win then find strategys that make it
win."*

Tuning a strategy on all the data until the backtest wins is the trap the pasted prompt itself
warns about (its section 34). A search of thousands of settings always finds some that won on the
data they were tuned on. That says nothing about next month.

The honest version:
1. Search only the **first half** of the year.
2. Lock in the best settings.
3. Test them on the **second half**, which the search never saw.
4. Run the identical search on random entry times, which shows how good pure luck looks.

**Prior: very low.** In the SN test the setups were no better than random entry times before fees.

---

## A. Data

- **Crypto (search and test):** BTC-USD, ETH-USD, SOL-USD, XRP-USD, DOGE-USD, exactly as in
  `PREREG_SNIPER.md` A.
  - **Train** is the first half of the evaluation days, 2025-09-25 → 2026-03-18.
  - **Test** is the second half, 2026-03-19 → 2026-09-10. This is the same split as the SN run.
  - A trade belongs to the half of its entry day.
- **Stocks (an extra unseen check for the finalists, reported only):** the 16 names and 19
  sessions of `PREREG_SNIPER.md` A.

---

## B. Candidates

At every eligible 5-minute decision, the SN rules are unchanged: stale data, blackouts, warm-up and
stock hours (`PREREG_SNIPER.md` B). The candidates are:

- **Each of the 8 setups** that fires and passes its regime blocks and stop bounds
  (`PREREG_SNIPER.md` C), not only the best-scoring one. Each carries its own score (D).
- **ALL8:** the best-scoring of the 8 at that decision, which is exactly the SN signal.
- **Two simple families** that aren't from the prompt. They check whether the setups are just a
  worse version of something simple:
  - **MOM (momentum):** long if the last 60 minutes' return is ≥ +2 × σ₁ₘ × √60; short if it is
    ≤ −2 × σ₁ₘ × √60.
  - **REV (short-term reversal):** long if the last 15 minutes' return is ≤ −2 × σ₁ₘ × √15; short
    if it is ≥ +2 × σ₁ₘ × √15.
  - For both: P\* = the 5m close, X = close ∓ 1 × ATR14(5m), and V = X (no separate thesis exit).
  - For the regime-fit part of the score, MOM is scored like BRK and REV like SRR.
  - Both are blocked against a strong trend. REV is blocked on news-driven stock sessions.

σ₁ₘ is the engine's 60-bar stdev of 1-minute returns. Returns are measured over the last 60 or 15
one-minute bars.

---

## C. The grid: 9,504 configurations

**Entry filter (396):**
- family: BRK, RET, SRR, SWP, VWR, PBK, MRV, BOS, ALL8, MOM, REV (11)
- side: long, short, both (3)
- minimum score: 0, 60, 70, 80 (4)
- regime:
  - any
  - with the trend: STRONG / WEAK BULL or BREAKOUT for longs, the mirror for shorts
  - RANGE only

**Exit variant (24):**
- stop: the candidate's stop distance × 1 or × 3, so X_k = c ∓ k × risk (2)
- targets (3):
  - the prompt's scale-out: ⅓ at 1R / 2R / 3R, breakeven after TP1, trailing after TP2
  - a single target at 2R
  - no target
- max hold: 60 or 480 minutes (2)
- thesis invalidation, a 5m close beyond V: on or off (2)

**Everything else is `PREREG_SNIPER.md` E:**
- market entry at the next 1-minute open
- don't chase
- the stop wins a tie; a gap through the stop fills at the open
- blackout and stock-session exits

R = |fill − X_k|. One position per symbol per configuration. There is no sizing, no daily limit
and no cost veto: results are in R, and fees are charged in R.

---

## D. Selection (train half only)

There are two fee tracks:
- **retail:** 0.35% per side. This is the primary track: what an app charges.
- **low:** 0.05% per side.

For each track:
1. Keep configurations with ≥ 200 train trades.
2. Rank them by t = mean R after fees ÷ (sd / √n).
3. The top 10 are the **finalists**. Ties go in grid order.

---

## E. Test (second half, used for nothing above)

For each finalist, on the test half, at its track's fee:
- **W1:** ≥ 100 trades, mean R > 0, the lower end of the one-sided 99.5% day-bootstrap interval > 0,
  and profit factor > 1.10. The bootstrap uses B = 2000 and seed 20260911; 99.5% is Bonferroni for
  10 finalists.
- **W2:** test mean R at zero fees is above the 99.5th percentile of random entry times run through
  the identical exit variant.
  - Each test trade gets 20 random entries: same symbol and side, same stop and invalidation
    distances in ATR units, decision times drawn from the test half.
  - B = 2000.
- **W3:** mean R after fees > 0 on at least 3 of the 5 coins.

**WIN** = W1–W3. The verdict per track is FOUND (at least one winning finalist) or NOT FOUND.
Program rule: a WIN earns only a forward paper log. No live trading.

---

## F. Always reported

- **Luck yardstick.** The identical search runs on a random-entry copy of the candidates.
  - Each candidate is re-entered at one random decision time in its own half, keeping its labels,
    side, score, and stop and invalidation distances in ATR units (seed 20260911).
  - Reported: that search's best train t, and its finalists' test results.
- **Does the first half predict the second?** Spearman rank correlation of train vs test mean R
  across configurations with ≥ 200 train and ≥ 100 test trades. Given at zero fees and for each
  track.
- The share of configurations with positive mean R in train and in test, at each fee level.
- The finalists applied to the 16 stocks (19 sessions) at 0.02% per side: trades and mean R. Not
  gated.
- The full table of 9,504 configurations: train and test at every fee level.

---

## G. G0 integrity (precondition)

- **Exit variants:** hand-built cases for a single 2R target, no target, a 60-minute hold, and a ×3
  stop.
- **All-candidates mode leaves the SN signals unchanged.** The ALL8 candidates equal `run()`'s
  best-mode signals, and `run_sniper.py` reproduces its 2026-09-11 results.
- **Truncation:** all-mode candidates are identical under truncation, on synthetic data and real SPY.
- **Parallel and serial runs** give identical configuration statistics.
- **Five synthetic random-walk coins** (120 days each): no finalist WINS in either track.
- **The same with planted drift 0.30** (the strength calibrated in the SN run): at least one
  finalist WINS in the low track.
- If G0 fails, there is no verdict.

---

## H. Limitations, stated in advance

- 9,504 configurations is a small corner of everything that could be tried, so "not found here"
  doesn't mean "impossible". Bigger searches find bigger lucky winners, though, and the test half
  has to reject those.
- There is one train/test split and six months of test data.
- The search is crypto only. 19 stock sessions are too short to split.
- Results are in R, not dollars: no sizing and no compounding.

**Registry rows:** SR-RETAIL, SR-LOW (the same 9,504-configuration grid on two fee tracks).

---

## Amendments

(none)
