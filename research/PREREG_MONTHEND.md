# Pre-Registration: Month-End Rebalancing (forward paper test, SPY vs. TLT)

**Frozen:** 2026-09-23, before the September 2026 window and every window after it.
**Integrity:** `MONTHEND.sha256` holds this file's SHA-256. `month_end_rebalance.py` refuses to record a position
if it doesn't match. **Paper only.** Nothing here places, or can place, a real order.

---

## The question

Harvey, Mazzoleni & Melone (2025) find that large stock/bond rebalancers (pensions, target-date funds) tend to
trade in the last few days of each month, and which way they trade is predictable from that month's stock-vs-bond
performance so far: if stocks beat bonds that month, rebalancers have to sell stocks to get back to target weights
(and buy them if bonds won). They report this predictability "peaks in the last four days of the month." Does that
same signal, on the simplest instruments a retail account can actually trade, predict SPY's return over those days?

## Why forward-only, not a backtest

This paper was published in 2025 - about a year of real out-of-sample time exists, nowhere near enough to test
(the same problem flagged and set aside when this candidate was first found). Backtesting further back than that
would just repeat the pattern seen in nearly every earlier test here: a rule that looked great before it was known
and faded after. **The only fair test left is forward**, exactly like Web Picks: lock the rule, then watch it on
days that haven't happened yet.

## Prior

**Low**, and stated for three reasons:
1. Everything else tested in this project that looked for a beatable, non-trivial return has failed - 122 configs,
   0 passes.
2. A closely related idea, PREREG_PHASE10.md's overnight drift, also traded on a predictable, mechanical-sounding
   pattern and failed once costs and a real out-of-sample window were applied.
3. Published, mechanical-flow-based predictability specifically is exactly the kind of finding that gets arbitraged
   away fastest once it's public, since (unlike a slow-moving anomaly) it names an exact, short window other
   traders can front-run just as easily.

## The rule

- **Instruments:** SPY (stocks) and TLT (20+ year Treasury bonds) - the simplest, most liquid, free-data proxies
  for "stocks" and "bonds." **Claude's choice**: a real fund's bond sleeve is mixed-duration, not just long
  Treasuries, so this is a simplification, not a replication of any specific fund's book.
- **The window:** the last 4 trading days of each calendar month, using SPY's own trading calendar (from the
  saved daily candles, not a hand-built calendar - the kind of date-arithmetic mistake this project has made
  before, e.g. the epoch-timestamp error in the GA round-2 build).
- **The signal**, locked using only data through the close of the trading day *before* the window starts (never a
  day inside the window itself): month-to-date total return of SPY vs. month-to-date total return of TLT, from
  each instrument's first close of the month through that decision-day close.
  - SPY month-to-date > TLT month-to-date -> rebalancers are predicted to **sell** stocks -> **short SPY** for the
    window.
  - TLT month-to-date > SPY month-to-date -> rebalancers are predicted to **buy** stocks -> **long SPY** for the
    window.
  - Exact tie (should not happen with real prices) -> flat.
- **Fills:** enter at the **open** of the window's first trading day, exit at the **close** of the window's last
  trading day. 0.01% per side (SPY's cost elsewhere in this project), 2 trades a month.
- **September 2026 is explicitly skipped.** This file was written 2026-09-23, and September's own last-4-day
  window starts 2026-09-25 - two trading days away. Trading it would mean locking a rule days before acting on it
  in the same month it was found, which is too close to "pick the window after seeing how the month already
  looks" for comfort even though the rule doesn't use any day inside the window. **The first live window is
  October 2026's.**

## Stopping point

**12 completed windows** (about a year, since this is a monthly signal - most of this project's forward tests run
weekly, so this one is deliberately slower and needs to run longer before saying anything). First window: October
2026. Expected review: around 2027-10. No conclusion before then. Never move the stopping point or the gates to
rescue a result.

## The gates (all four needed)

1. **Made money:** total return after fees, compounded across all 12 windows, is above zero.
2. **Beat doing nothing:** beats simply holding SPY flat (no position) over the same 48-ish days.
3. **Beat a coin flip:** beats the 95th percentile of 2,000 draws of the same rule with the direction picked at
   random each month instead of from the signal (same window, same fees, same exposure - just the direction
   randomized).
4. **Not one lucky month:** positive in more than half of the 12 windows.

Failing only gate 2 while passing the rest is reported as "real, but not worth it" - the same split every other
test in this project uses.

## What could still be wrong, said up front

- **Low power.** 12 monthly observations is a small sample; a real small edge could easily be missed, and a
  fluke could easily pass 3 of 4 gates by chance. This is explicitly a lower-confidence test than the weekly ones.
- **TLT is one bond proxy** among many a real rebalancer might hold; a different proxy (AGG, a blend) could give a
  different signal in a given month. Not tested here - trying several until one works would be exactly the kind
  of re-rolling this project avoids.
- **Short SPY** is simulated directly (a plain short position, not through an inverse ETF like SH, which has its
  own daily-reset costs). A real retail short would likely do slightly worse than this.
- **One live-fund-style check, already stated in advance:** if TLT itself is a bad bond proxy, the signal could
  point the wrong way in specific months for reasons that have nothing to do with rebalancing flows (e.g. a
  Treasury-specific move unrelated to pension allocations). No adjustment will be made mid-test.

**Registry:** tracked as a live paper test, like Web Picks - see `live_arena/MONTHEND_RESULTS.md`, refreshed by
`live_arena/month_end_rebalance.py --update`, wired into the existing weekly check.

---

## Amendments

(none)
