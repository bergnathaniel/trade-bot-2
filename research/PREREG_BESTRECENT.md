# Pre-registration: "Best Recent" — trade whichever (bot, coin) pair has been winning lately

**Frozen:** 2026-09-22, before this bot had made a single real pick.
**Integrity:** the run script prints this file's SHA-256 with every report. Never edit this text after
results exist. Changes go in a dated *Amendments* section.

---

## Why this test

The user asked for a bot that "knows what to buy for the most profit." Nothing in this project has
found a strategy that reliably beats holding an index (`research/REGISTRY.csv`). Track Record
(`live_arena/track_record_bot.js`) already does half of the idea: it weights *signals* by their own
recent hit rate, but only on one fixed asset at a time.

This test does the other half honestly: every week, look at how every existing bot has actually been
doing, live, on every coin it's traded (the speed test already runs 234 bots on 12 coins every week -
`live_arena/SPEED_TEST.md`), and hold whichever single (bot, coin) pair has had the best trailing
record. Re-check every week. This is the same "chase recent winners" idea as `PREREG_PICK.md`, which
just failed - so the honest expectation here is also failure. The difference worth testing is scale:
PICK searched 2 strategies x 60 stocks. This searches roughly 200 bots x 12 coins, a search space
about 200x bigger - which mostly means it is 200x more likely to find something that *looks* good by
chance, not 200x more likely to find something real. The bar below is set accordingly.

**Prior: very low**, for the same reason PICK's was: nothing in this project has shown that a
strategy's past winners keep winning.

## A. The pool

Every non-control bot in the live speed test's **crypto group, 15-minute candles** (12 coins, listed
in `live_arena/speed_test.py`'s `RULES`). Stocks are left out: market hours make "hold whatever won
last week" a different, choppier problem, and crypto is where the speed test already has the most
data. 5-minute candles are left out to keep the search to one pool instead of two (searching both and
keeping whichever looked better would be exactly the re-rolling this project avoids).

A (bot, coin) pair is in the pool for a given week only if that bot closed at least 1 trade on that
coin that week (`per[coin].closed >= 1` in that week's `speed/results/<week>.json`, a field added to
the speed test on 2026-09-22 specifically for this - **weeks before that date have no per-coin
breakdown and are not used**; this test starts from zero history, not a backfill).

## B. The rule (walk-forward, same shape as PICK)

Every week, once at least **3** trailing weeks of per-coin data exist:
1. For every (bot, coin) pair with at least **5** total closed trades over the trailing 3 weeks,
   compute its mean weekly return over those 3 weeks.
2. Pick the single pair with the highest trailing mean.
3. Hold it for the next week. Its "return" for that week is that bot's **actual, already-graded**
   speed-test return on that coin that week (`per[coin].ret`) - no new simulation, the same audited
   number the speed test itself produced.
4. Repeat.

Fills, fees and slippage are whatever the speed test already used that week (0.25% crypto, next-open
fills) - identical mechanics to every other live Arena bot, not a separate engine.

## C. Controls

Computed over the same weeks, same pool:

| control | what it shows |
|---|---|
| **Random pair** | one random eligible pair each week, 5,000 draws. Beating this only at the ordinary 95th percentile would prove nothing, given the pool size - see gate G3. |
| **Hold bitcoin** | the simplest alternative. |
| **Hold the pool, equal weight** | trading every eligible pair a tiny bit, no picking. |

## D. Gates (decided now, before any pick exists)

A pass needs all five:
1. **G1:** at least 10 weekly picks made (about 2.5 months of real weeks - this is a slow test by
   nature, since it needs 3 trailing weeks before its first pick).
2. **G2:** cumulative return after fees > 0.
3. **G3:** beats the **99.5th percentile** of the random-pair control's 5,000 draws (not 95th - the
   pool is roughly 200x bigger than PICK's, so the bar is set far tighter, not just "beat luck").
4. **G4:** beats holding bitcoin over the same weeks.
5. **G5:** beats holding the pool, equal weight.

Failing only G4 or G5 (but passing G1-G3) is reported as "real, but not worth it" - the same split
`CONFIRM.md` and `PREREG_PICK.md` use.

## E. Always reported

- Which bot and coin were picked each week, and what actually happened.
- The rank correlation between a pair's trailing mean and its next-week return - the same
  persistence check PICK used, and the same number that would explain a failure.
- How much of any positive result came from a single lucky week (the "one lucky week" check).

## F. Integrity

- **No look-ahead:** a week's pick only ever reads `speed/results/` files dated strictly before that
  week - checked mechanically the same way as `leakage.truncation_test`, not just by code review.
- **Reproduces the speed test:** Best Recent's own reported return for a picked pair must equal that
  week's already-published `per[coin].ret` exactly, since it's the same number, not a re-derivation.
- No synthetic-noise or planted-persistence check this time: those need many independent whole
  histories to run on, and there is only one real speed test, generating one real week of data at a
  time. Integrity here rests on G3's much stricter random-pair bar instead.

## G. Limitations, stated in advance

- **Starts from zero.** No backfill (the speed test's own Kronos-forecast files aren't kept per week,
  so an old week can't be faithfully replayed - see the amendment below). The first pick is roughly 3
  real weeks after this is turned on; G1 needs 10 picks, so no verdict is possible before roughly
  2027-01, and it needs to keep running past that to mean anything.
- **A moving pool.** Bots get added to the speed test over time; new bots enter this pool as soon as
  they have speed-test history, which is a form of the same "added after the fact" issue
  `SPEED_TEST.md` already tracks for its own streaks.
- **Crypto only, 15-minute only.** A pass here says nothing about stocks or other candle sizes.
- **Real trading costs, especially in less liquid coins, are often above the speed test's 0.25%.**

**Registry:** tracked as a live paper test, not a one-shot REGISTRY.csv row (like Web Picks) - see
`live_arena/BESTRECENT_RESULTS.md`, refreshed weekly by `live_arena/best_recent.py --update`.

---

## Amendments

(none)
