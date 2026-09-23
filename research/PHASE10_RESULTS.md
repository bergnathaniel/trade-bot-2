# Phase 10 (the overnight drift): tested

**Date:** 2026-09-23 · **Rules frozen before any result:** `PREREG_PHASE10.md` (sha256 `2a8b36e9…778083`)
**Rerun:** `python3 research/run_phase10.py` (about 1 second)
**Verdict: FAIL.** 0 of 2 pass.

---

## In plain English

The user asked Claude to research and find something new worth adding. The search turned up a real, well-documented
finding: for decades, almost all of a stock index's long-run gain has come from **overnight** (yesterday's close to
today's open), not from the trading day itself. A quick check before building anything backed it up: SPY over the
last 5 years, +47.1% overnight vs. +29.9% during the day.

The honest catch going in: a brand-new 2026 New York Fed paper is literally titled **"The Disappearing Overnight
Drift"**, and this project already has real evidence against it — `NightShares`, an actual ETF built to trade exactly
this idea, was liquidated after 14 months. So the prior was low. It was still worth testing directly, since nothing
here had tested the rule itself, only noticed that one fund built on it had failed.

**The rule tested:** hold SPY (or QQQ) from close to the next open, sit in cash during the trading day, every single
day, no signal, no filter — the plainest version of the idea, 1993/1999 to today, split so 2015 onward counts as the
out-of-sample window.

### It failed, and the numbers explain why

- **SPY:** overnight-only made 1.5%/yr after costs since 2015, against SPY's own 11.5%/yr over the same stretch.
  Sharpe 0.19 vs. SPY's 0.71. Alpha against just holding SPY: **−3.15%/yr** (t −1.22) — negative, not zero.
- **QQQ:** same pattern, less bad: 4.9%/yr vs. QQQ's 16.8%/yr, Sharpe 0.42 vs. 0.82, alpha −1.23%/yr (t −0.41).
- **Costs are the real killer.** This rule trades every single trading day — 2,946 round trips in 11.7 years, versus
  the ~150 trades IBS Swing made testing the same idea a different way (Phase 7). At double the assumed cost, SPY's
  overnight strategy goes **negative** (Sharpe −0.26); QQQ barely survives (0.05).
- **Deflated Sharpe:** 0.03 (SPY) and 0.13 (QQQ) against the 0.95 bar — not close, at either instrument.

### The neighbour check found something worth noting

The three variations tested — Monday-only overnight (isolating the weekend gap), every overnight *except* Monday,
and half-weight overnight — split in an interesting way: **holding every overnight except the weekend gap did
noticeably better** than the full rule (SPY Sharpe 0.35 vs. 0.19 base; QQQ 0.57 vs. 0.42), while **Monday-only was
negative on both** (SPY −0.19, QQQ −0.13). So whatever's left of this effect isn't concentrated in the weekend gap
the way some of the literature suggests — if anything, the weekend gap is actively hurting the rule in this window,
and the ordinary weeknight-to-weeknight sessions are carrying what little the rule has.

### The live-fund check (G9) couldn't run

`NightShares`, the ETF this project already knew had been liquidated, has no usable price history left on Yahoo at
all (0.0 years) — it's gone from the data source entirely, not just underperforming. No fresh alpha check was
possible; the liquidation itself remains the only real-world evidence on this specific fund.

### One thing worth flagging about the source number

The pre-registration quoted an outside source's 5-year split (SPY +47.1% overnight / +29.9% during the day). This
harness's own version of that same check, over its own window and cost assumptions, found overnight +32.1% but the
trading session **actually lost money**, −14.1%, not +29.9%. Different methodology, different window, and a
noticeably different picture — a reminder that even a well-cited number can shift a lot depending on exactly how and
when it's measured, which is itself a small piece of evidence for "this effect isn't as stable as it sounds."

**Bottom line:** a documented, once-strong pattern that's decayed enough by now, and costs enough to trade daily,
that it doesn't clear even the loosest bar here. Consistent with everything else tested in this project — nothing
beats buying and holding the index. N for the next deflated-Sharpe test is 122.
