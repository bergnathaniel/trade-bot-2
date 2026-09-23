# Pre-Registration: Phase 10, the overnight drift (H48–H49)

**Frozen:** 2026-09-23, before any Phase-10 return, alpha or placebo was computed.
**Integrity:** `run_phase10.py` prints this file's SHA-256. Changes go in a dated *Amendments* section.

---

## Why this one

The user asked Claude to research and find something new worth testing. The search turned up one candidate that
meets Phase 8/9's selection rules (well documented, never tested here, free data, retail-tradeable, a real
post-publication window):

**The overnight drift.** Decades of research (Branch & Ma 2012; Lou, Polk & Skouras "A Tug of War", RFS 2019; the New
York Fed's "Overnight Drift" work) find that almost all of a US index's long-run gain comes from close-to-open, not
from the trading session itself (open-to-close). A 5-year check run before this file was frozen: SPY close-to-open
+47.1% vs. open-to-close +29.9% over the same stretch; QQQ +53.5% vs. +30.3%.

**Why the prior is low despite that:** a 2026 New York Fed paper is titled *"The Disappearing Overnight Drift"* and
reports the effect fading in recent data. More directly: this project already has a live-fund data point against
it - `NightShares`, an ETF built specifically to hold the overnight session and sit in cash during the day, was
liquidated after 14 months (`research/PROGRAM.md`'s Phase 1 live-fund check). A real fund built on this exact idea
already failed. This test exists to check the rule itself, on more history and two instruments, not to relitigate
that fund.

**Selection rules met**, same as Phase 8/9:
- well documented, published, never tested in this project (Phase 1's live-fund check looked at a fund's own
  returns, not the close-to-open rule itself on raw prices);
- free data (Yahoo daily open/close), no survivorship bias (SPY/QQQ, not a stock-picking universe);
- retail-tradeable (hold the ETF overnight, nothing exotic);
- a real out-of-sample window: publication is old enough (2012-2019) that 2015 onward is safely post-publication,
  and the 2026 NY Fed paper gives an even more recent decay checkpoint inside that window.

**Prior: low.** A once-strong, well-published effect with recent decay evidence and one already-failed live fund
built on it. This is exactly the shape of most things tested here - the difference is it hasn't been tested this
way before.

## Rule (H48 SPY, H49 QQQ)

Hold the ETF from close to the next open (`w_on = 1`), flat from open to close (`w_id = 0`), every trading day,
unconditionally - no signal, no filter, the plainest form of the rule. `engine.py`'s session model does the
accounting: overnight segment `close[i-1] -> open[i]`, intraday segment `open[i] -> close[i]`, both excess of cash.

**Neighbours** (the required robustness check, not separate hypotheses):
- **Monday-only overnight** - holds only the Friday-close-to-Monday-open segment, flat every other night and every
  day. Isolates the weekend gap, a known concentration point in the literature.
- **Excluding Monday overnight** - the complement: every overnight except the weekend gap.
- **Half-weight overnight** (`w_on = 0.5`) - a pure leverage check; should scale Sharpe roughly unchanged if the
  rule is what it claims to be.

## Data

Yahoo daily OHLC, SPY from 1993-02-01 and QQQ from 1999-04-01 (same series `h_common.yahoo` already pulls for every
other phase), `^IRX` for the risk-free rate. Costs 1bp/side (2bp at 2x, gate G4), matching Phase 7's SPY/QQQ cost
assumption - one trade in and one out per session, so this rule trades far more often than IBS did (every day
instead of ~150 times over 3 years), which is itself a real cost headwind worth watching in the results.

**Out-of-sample split: 2015-01-01.** Old enough that the anomaly was already well-published (Lou/Polk/Skouras
circulated well before formal 2019 publication; Branch & Ma is 2012), and it captures both the 2015-2020 window and
the very recent decay the 2026 NY Fed paper describes.

## Gates

The standard battery (`PROGRAM.md`, `evaluate.py`), decided before any result exists:
- **G1** net excess Sharpe > 0 and bootstrap 95% CI lower bound > 0.
- **G2** alpha vs. SPY/QQQ (the same instrument's own close-to-close excess return) with t ≥ 2.
- **G3** deflated Sharpe ≥ 0.95 at N = 120 (118 through Phase 9 + these 2).
- **G4** out-of-sample net Sharpe > 0 at 2x costs.
- **G5** compounded net excess return > 0 in ≥ 2 of 3 sub-periods.
- **G6** ≥ 75% of neighbours have out-of-sample net Sharpe > 0, median neighbour Sharpe within 50% of the base.
- **G7** N/A - there's no natural placebo shuffle for "hold every night unconditionally" the way there is for a
  signal-driven rule (nothing to shuffle; the weight is constant). Reported N/A, not skipped.
- **G8** PASS by construction (long the ETF, nothing exotic).
- **G9** the live-fund check: `NightShares` (already known to have been liquidated) plus any other overnight ETF
  still on Yahoo, alpha vs. SPY with Newey-West t.

## Integrity

- **No look-ahead:** `leakage.truncation_test` on the weight path - expected to trivially pass, since the rule is
  constant and reads no data to decide anything. Run anyway, for the same reason every phase runs it even when
  confident: the check should never be skipped because a result seems obvious in advance.
- **Reproduces a known number:** the 5-year close-to-open vs. open-to-close split quoted above (SPY +47.1%/+29.9%)
  is checked against this harness's own segment returns before trusting anything else in the run.

## Limitations, stated in advance

- **Two instruments only.** SPY and QQQ, not a broad cross-section - a pass would say "worth checking elsewhere,"
  not "the effect is general."
- **Costs matter more here than almost anywhere else in this project.** Trading every single session, 252 times a
  year, at even 1bp/side is a real drag a once-a-quarter rule never pays.
- **The G9 live-fund check has one real data point** (NightShares) and it already failed before this file was
  written - not a fresh, blind check the way G9 usually is elsewhere.

**Registry rows** (added with the results): P10-H48, P10-H49.

---

## Amendments

(none)
