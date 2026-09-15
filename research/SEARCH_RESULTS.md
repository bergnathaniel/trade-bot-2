# The strategy search ("make it win"): tested

**Date:** 2026-09-11 · **Rules frozen before any result:** `PREREG_SEARCH.md` (sha256 `99f75718…94d0`)
**Rerun:** `python3 research/run_search.py` (about 80 s including the self-test, on 10 cores)
**Verdict: NOT FOUND.** Not at app fees, and not at a 0.05% fee.

---

## In plain English

**What was asked.** "Make it win, then find strategies that make it win."

**What was done.** Picking settings on all the data until the backtest wins would guarantee a fake
win. So the search worked like this:

1. **Try 9,504 versions.** They combine:
   - the 8 sniper setups, the best-of-8, and two simple strategies (60-minute momentum and
     15-minute reversal)
   - long, short, or both
   - a minimum score of 0, 60, 70 or 80
   - any market condition, with-the-trend only, or range only
   - a normal or 3× wider stop
   - scale-out targets, one 2R target, or no target
   - a 1-hour or 8-hour maximum hold
   - a thesis exit on or off
2. **Pick the 10 best** using only the first half of the year (2025-09-25 → 2026-03-18).
3. **Test those 10 on the second half** (2026-03-19 → 2026-09-10), which the search never saw.
4. **Run the same search on random entry times** to see what pure luck looks like.

**Result.**
- **At app fees (0.35% per side):** not one of the 5,235 versions with enough trades made money,
  *even in the half it was picked on*. The 10 "best" lost 1.1R to 2.0R per trade in the second half.
- **At a 0.05% fee:**
  - 1.7% of versions made money in the first half, 0.6% in the second, and **none in both**.
  - All 10 picks were "short after a big 60-minute rally" with wide stops. That bet paid in the
    first half, when the coins fell 35–57%.
  - In the second half the market stopped falling. BTC rose 7%, ETH 11% and SOL 10%. All 10 picks
    lost, −0.22R to −0.37R per trade, and on every one of the 5 coins.
- **Before fees:** about half of all versions were up in each half. But how a version ranked in the
  first half told you *nothing* about the second half (rank correlation −0.005). About 29% were up in
  both halves, which is what coin flips would give (55% × 50%). That is what "no edge" looks like:
  the winners are random.
- **The hindsight trap.** The best low-fee version in the second half (trend pullbacks, 3× stop,
  8-hour hold, +0.24R) ranked #109 of 5,235 in the first half, where it lost money. Nobody could have
  picked it without seeing the future.

**Why.** At these holding times a fee is bigger than the typical move. Before fees, nothing here
repeats from one half-year to the next. A tuned search just finds what happened to work in the
months it looked at. The pasted prompt calls this overfitting and warns against it itself.

**What happens next.**
- There is no winner, so there is nothing to confirm. The untouched 2024–25 year
  (`PREREG_CONFIRM.md`) stays untouched for a future round.
- Next is the program's Phase 2, frozen earlier today: earnings drift, insider buying and the
  Treasury auction cycle. Those trades hold for weeks, so fees matter much less.

---

## Results

### App fees (0.35% per side): the 10 picked on the first half

All 10 use a 3× stop, no target, an 8-hour hold and no thesis exit. That combination makes the fee
smallest in R.

| # | version | first half: trades, mean R | second half: trades, mean R, profit factor | coins up |
|---|---|---|---|---|
| 1 | breakout retest, both, score ≥ 70, any | 203, −0.83 | 179, −1.96, 0.16 | 0/5 |
| 2 | momentum, short, ≥ 80, with trend | 390, −0.43 | 310, −1.33, 0.12 | 0/5 |
| 3 | momentum, short, ≥ 70, with trend | 547, −0.43 | 464, −1.32, 0.15 | 0/5 |
| 4 | breakout retest, long, ≥ 0, with trend | 240, −1.17 | 273, −1.68, 0.22 | 0/5 |
| 5 | reversal, short, ≥ 60, with trend | 237, −0.66 | 168, −1.12, 0.26 | 0/5 |
| 6 | momentum, short, ≥ 80, any | 446, −0.53 | 360, −1.36, 0.12 | 0/5 |
| 7 | breakout retest, long, ≥ 60, any | 266, −1.23 | 295, −2.01, 0.15 | 0/5 |
| 8 | momentum, short, ≥ 60, with trend | 630, −0.49 | 527, −1.36, 0.14 | 0/5 |
| 9 | momentum, short, ≥ 0, with trend | 649, −0.51 | 548, −1.38, 0.14 | 0/5 |
| 10 | breakout retest, short, ≥ 60, with trend | 265, −1.00 | 173, −1.81, 0.13 | 0/5 |

### Low fee (0.05% per side): the 10 picked on the first half

All are 60-minute momentum shorts with a 3× stop and an 8-hour hold. Unless noted, they have no
target and no thesis exit.

| # | version | first half: trades, mean R, t | second half: trades, mean R, profit factor | coins up |
|---|---|---|---|---|
| 1 | score ≥ 70, with trend | 547, +0.26, +2.74 | 464, −0.32, 0.59 | 0/5 |
| 2 | ≥ 60, with trend | 630, +0.21, +2.42 | 527, −0.34, 0.57 | 0/5 |
| 3 | ≥ 0, with trend | 649, +0.20, +2.38 | 548, −0.33, 0.58 | 0/5 |
| 4 | ≥ 80, with trend | 390, +0.23, +2.16 | 310, −0.37, 0.52 | 0/5 |
| 5 | ≥ 70, any | 673, +0.18, +2.15 | 585, −0.28, 0.64 | 0/5 |
| 6 | ≥ 80, with trend, scale-out targets | 452, +0.10, +1.88 | 329, −0.22, 0.61 | 0/5 |
| 7 | ≥ 80, any | 446, +0.16, +1.68 | 360, −0.36, 0.53 | 0/5 |
| 8 | ≥ 0, any | 914, +0.11, +1.53 | 836, −0.28, 0.65 | 0/5 |
| 9 | ≥ 60, with trend, thesis exit on | 698, +0.10, +1.52 | 573, −0.26, 0.54 | 0/5 |
| 10 | ≥ 60, any | 835, +0.10, +1.42 | 729, −0.30, 0.63 | 0/5 |

None beat random entry times through the same exits. With no fees, their second-half averages were
−0.06R to −0.21R. The random-entry bar (99.5th percentile) was +0.13R to +0.24R.

### Luck, persistence and hindsight

| | no fees | 0.05% / side | 0.35% / side |
|---|---|---|---|
| versions with mean R > 0: first half / second half / both | 55.2% / 50.3% / 29.0% | 1.7% / 0.6% / 0.0% | 0.0% / 0.0% / 0.0% |
| rank correlation, first half vs second half | −0.005 | +0.82 | +0.97 |

- Versions counted: 5,235 with ≥ 200 first-half trades; 5,921 with ≥ 100 second-half trades.
- With fees, the rankings "persist" only because fee drag is predictable: versions that trade more
  or use tighter stops pay more every time. None of them are positive.
- **Luck yardstick** (the same search on random entry times):
  - At 0.05%: the best first-half t was +1.03, against +2.74 for the real search. The random
    search's top 10 averaged −0.34R to +0.02R in the second half.
  - At 0.35%: the best first-half t was −5.82 (random) against −3.33 (real).
- **Hindsight.** The best second-half version at 0.05% was trend pullbacks, both sides, score ≥ 70,
  3× stop, no target, 8 hours (+0.24R). It ranked #109 of 5,235 on the first half, with a mean of
  −0.03R. At 0.35%, the best second-half version (the same one, −1.28R) ranked #13.

### The coins, half by half

| | 2025-09-25 | 2026-03-18 | 2026-09-10 | first half | second half |
|---|---|---|---|---|---|
| BTC-USD | $109,036 | $71,245 | $76,537 | −35% | +7% |
| ETH-USD | $3,876 | $2,203 | $2,437 | −43% | +11% |
| SOL-USD | $192.80 | $90.08 | $98.62 | −53% | +9% |
| XRP-USD | $2.745 | $1.465 | $1.334 | −47% | −9% |
| DOGE-USD | $0.2230 | $0.0953 | $0.0828 | −57% | −13% |

### The 15 finalists on 16 stocks (19 sessions, 0.02% per side; reported, not gated)

- **Every finalist lost.** The largest sample was momentum shorts with any score (95 trades):
  −0.22R per trade, and −0.14R even with no fees.
- **The rest:** breakout retests lost −0.37R to −0.86R (8–13 trades each); the other momentum
  shorts lost −0.22R to −0.41R.

---

## G0 integrity: 11/11

- **New exit variants:** hand-built cases are correct for a single 2R target, no target, a 60-minute
  hold, invalidation off, and a 3× stop.
- **All-candidates mode:** its best-of-8 picks equal the sniper signals exactly (730 of 730 on
  synthetic data). `run_sniper.py` reproduces its earlier results byte-for-byte (gates, verdict and
  both trade logs) after the code changes.
- **No look-ahead:** truncating the data changes no earlier candidate (4 cuts on synthetic data, 6 on
  real SPY).
- **Parallel runs** give exactly the same candidates and statistics as serial runs.
- **Five random-walk coins:** no finalist wins in either track. The best second-half means were
  −1.12R at retail fees and −0.04R at 0.05%.
- **Five coins with planted drift:** the search finds the drift. All 10 finalists win in both
  tracks; the top one is +0.92R per trade on the test half.

## Files

- `PREREG_SEARCH.md`: the frozen rules
- `PREREG_CONFIRM.md`: the confirmation-year rule, frozen during the run before results were read
- `run_search.py`, `selftest_search.py`, `run_confirm.py` (not run: there were no winners)
- `results/search.json`, `results/search_run.log`, and `results/search_configs.csv.gz` (all 9,504
  versions, each half at every fee level, plus the random-entry replica)
