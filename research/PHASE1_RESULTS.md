# Phase 1 results: NO EDGE FOUND

**Run:** 2026-09-11 · **Reproduce:** `python3 research/selftest.py && python3 research/run_phase1.py`
(about 12 seconds with a warm cache; deterministic, since every random draw is seeded)
**Rules tested against:** `PREREG_PHASE1.md`. Frozen text `sha256 abafdd5b…c1ba63a1`; with amendment A1 `sha256 fcb30bf9…6102f730`
**Raw output:** `results/phase1_run.log` (frozen spec) · `results/phase1_run_A1.log` (with amendment) · `results/phase1.json`

> Descriptive of the past only. Not investment advice, a prediction, or a recommendation to
> buy or sell anything. I am not a licensed advisor.

---

## Verdict

31 pre-registered strategy configurations across 17 hypothesis clusters were tested on
post-publication data only. **0 PASS · 0 WATCH · 0 NI · 31 FAIL. Nothing proceeds to paper
trading.**

The verdict does not rest on the harshest gate. The deflated-Sharpe bar after 93 trials
(luck-bar Sharpe 0.73) is severe, but it isn't what decides this:

- **Every one of the 31 fails G2.** None earns alpha against the market with t ≥ 2.
- **None of the seven directional strategies beat SPY's Sharpe by more than 0.01** over its
  own out-of-sample window. The best, volatility-managed SPY, tied it at 0.74.

Counting neighbouring settings, 116 configurations ran in this phase. With the 76 before it,
the project has now tested **192**.

---

## Scorecard

Out-of-sample, net of costs, excess of cash. "Bench" is SPY over the same days (daily tests)
or the CRSP market (monthly tests). Long-only tilts report an information ratio against the
market instead of a Sharpe ratio.

### Volatility, calendar, industry momentum

| id | strategy | OOS from | yrs | exCAGR | Sharpe | bench | alpha (t) | DSR | maxDD | failed |
|---|---|---|---|---|---|---|---|---|---|---|
| H01 | Put-writing, CBOE PUT index | 2008 | 18.7 | +5.1% | 0.37 | 0.55 | −1.0% (−0.69) | 0.06 | −38% | G2 G3 |
| H01-A1 | same, bad print fixed (amendment) | 2008 | 18.7 | +5.1% | 0.43 | 0.55 | −0.7% (−0.48) | 0.10 | −38% | G2 G3 |
| H02 | SVXY buy & hold (short VIX futures) | 2011 | 14.9 | +10.8% | 0.54 | 0.86 | −0.7% (−0.06) | 0.26 | −95% | G2 G3 G9 |
| H03 | SVXY only when VIX < VIX3M | 2015 | 11.7 | +21.0% | 0.68 | 0.70 | +11.5% (1.23) | 0.44 | −55% | G2 G3 |
| H04 | Pre-FOMC drift | 2012 | 14.7 | +0.6% | 0.22 | 0.83 | +0.2% (0.29) | 0.03 | −9% | G1 G2 G3 G7 |
| H05 | Overnight-only SPY | 2009 | 17.7 | +1.9% | 0.23 | 0.79 | −3.2% (−1.60) | 0.02 | −30% | G1 G2 G3 G4 G6 |
| H06 | Turn of the month | 1993 | 33.6 | +2.8% | 0.39 | 0.51 | +1.4% (1.14) | 0.03 | −19% | G2 G3 |
| H07 | Volatility-managed SPY | 2017 | 9.7 | +10.1% | 0.74 | 0.74 | +0.6% (0.41) | 0.52 | −25% | G2 G3 G7 |
| H10-LS | Industry momentum, long/short | 2000 | 26.6 | +0.9% | 0.15 | 0.48 | +4.6% (1.40) | 0.00 | −58% | G1 G2 G3 G8 |
| H10-LO | Industry momentum, long-only vs EW | 2000 | 26.6 | +0.8% | 0.13 IR | — | +3.6% (1.61) | 0.00 | −39% | G1 G2 G3 |

### Equity factors (Ken French / CRSP, survivorship-free)

| factor | published | L/S Sharpe | L/S alpha (t) | L/S failed | long-only IR | long-only alpha (t) | long-only failed |
|---|---|---|---|---|---|---|---|
| Size (SMB) | 1981 | −0.08 | −2.2% (−1.57) | G1–G6, G8 | −0.07 | −1.7% (−0.87) | G1–G6 |
| Value (HML) | 1985 | 0.11 | +2.1% (0.92) | G1 G2 G3 G8 | 0.23 | +1.7% (0.79) | G1 G2 G3 G9 |
| Momentum (UMD) | 1993 | 0.09 | +4.3% (1.81) | G1–G5, G8 | 0.20 | +1.5% (0.67) | G1 G2 G3 G6 |
| Short-term reversal | 1990 | −0.49 | −8.4% (−4.76) | G1–G6, G8 | −0.25 | −10.0% (−4.85) | G1–G6 |
| Long-term reversal | 1985 | 0.00 | −0.5% (−0.24) | G1–G4, G6, G8 | 0.14 | −0.3% (−0.09) | G1 G2 G3 |
| Profitability (RMW) | 2013 | 0.19 | +1.9% (0.96) | G1 G2 G3 G8 | 0.09 | +0.9% (0.82) | G1–G4, G6, G9 |
| Investment (CMA) | 2004 | −0.11 | −0.1% (−0.03) | G1–G6, G8 | 0.01 | −0.0% (−0.01) | G1–G6 |
| Low accruals | 1996 | 0.12 | +1.1% (0.61) | G1 G2 G3 G8 | 0.22 | +0.8% (0.70) | G1 G2 G3 G6 |
| Low net issuance | 2008 | −0.07 | +3.3% (1.09) | G1–G6, G8 | −0.47 | −1.2% (−0.78) | G1–G6 |
| Low beta | 1972 | −0.19 | +2.4% (1.05) | G1–G6, G8 | −0.13 | +1.5% (1.59) | G1–G6 |
| Low residual variance | 2006 | −0.17 | +4.0% (0.97) | G1–G6, G8 | −0.33 | +0.3% (0.29) | G1–G6 |

---

## What came closest, and why each still fails

**H03, short vol only in contango.** This is the most interesting failure. The timing
information is real: only 0.8% of randomly shifted copies of the signal did as well, all four
neighbouring thresholds were positive, and it cut the Feb-2018 blow-up from −91.5% (SVXY held
throughout) to −21.8%. But it runs at 40% volatility with a market beta of 1.27. Its Sharpe
(0.68) still trails SPY's (0.70) over the same years, and its +11.5%/yr alpha has t = 1.23.
It also decayed: Sharpe 1.02 in 2011–14, 0.68 since. And it lost −28.9% in the 2022 bear,
worse than SPY's −24.9%.

**H06, turn of the month.** The calendar effect is still there. On SPY, turn-of-month days
average 7.0 bp against 3.0 bp for other days, and only 0.9% of random four-day windows match
it. As a strategy it fails, because being in the market 19% of the time costs more than the
concentration earns (Sharpe 0.39 vs SPY's 0.51; alpha t = 1.14). On the 100-year CRSP series
the rule's Sharpe was **1.01 against the market's 0.41 before its 1987 publication, and 0.55
against 0.54 since**.

**H07, volatility-managed SPY.** Its Sharpe matched SPY's (0.74 vs 0.74) with a shallower
drawdown (−25% vs −34%). But 37% of randomly shuffled monthly weight paths did as well, so the
timing adds nothing that holding a little less stock wouldn't. The 1926+ CRSP version gained
+0.06 Sharpe before the 2017 publication and +0.04 after.

**H10-LO, industry momentum long-only.** It beat 96% of random industry picks and was robust
to formation choices, with a raw alpha of +3.6%/yr (t = 1.61). But controlling for the
momentum factor, the alpha is −0.85%/yr (t = −0.52): it's UMD in a sector wrapper. The
tradeable nine-SPDR-sector version since 2000 had a Sharpe of 0.463 against 0.465 for
equal-weighting the same nine ETFs.

**H01, put-writing.** It behaves like 0.6× the S&P 500 with the left tail intact: Sharpe 0.43
vs SPY's 0.55 since 2008, alpha −0.7%/yr. It gives up less in crashes (GFC −36.5% vs −55.7%)
but doesn't pay for it.

---

## The pattern: publication decay

Gross long/short Sharpe ratios, before and after the publishing paper, before any trading costs:

| factor | published | before | after | change in mean return |
|---|---|---|---|---|
| Short-term reversal | 1990 | 0.90 | 0.16 | −82% |
| Low accruals | 1996 | 0.62 | 0.23 | −55% |
| Investment | 2004 | 0.59 | 0.04 | −94% |
| Momentum | 1993 | 0.55 | 0.27 | −49% |
| Low net issuance | 2008 | 0.48 | 0.01 | −99% |
| Value | 1985 | 0.43 | 0.20 | −62% |
| Profitability | 2013 | 0.41 | 0.30 | −21% |
| Long-term reversal | 1985 | 0.35 | 0.16 | −68% |
| Size | 1981 | 0.30 | 0.02 | −95% |
| Low residual variance | 2006 | 0.16 | −0.04 | −126% |
| **average / median** | | **0.48** | **0.13** | **median −75%** |

Low beta is excluded: its raw long/short return was negative both before and after, because
it is short the market.

The same shape shows up outside factors:

- **Pre-FOMC drift:** 32.9 bp per meeting (t = 3.18, 144 meetings) from 1994 to 2011, which
  replicates the published result in-sample. Since then it's 10.4 bp (t = 1.06, 116
  meetings), with a 48% hit rate.
- **Turn of the month:** Sharpe 1.01 vs 0.41 before 1988, 0.55 vs 0.54 after.
- **Diversified trend following** (earlier test): blend gain +0.17 Sharpe before 2012, +0.01 after.
- **Pairs trading** (earlier test): Sharpe 0.70 in the published sample, −0.18 in 2010–17.

---

## Live money agrees

Full-history alpha vs SPY, net of fees, Newey-West t:

| fund | runs | live years | alpha/yr | t |
|---|---|---|---|---|
| MTUM | US momentum | 13.4 | +0.87% | 0.35 |
| VLUE | US value | 13.4 | −0.16% | −0.07 |
| IWD | Russell 1000 Value | 26.2 | +0.21% | 0.20 |
| QUAL | US quality | 13.1 | −0.30% | −0.36 |
| SPHQ | S&P 500 quality | 20.7 | −0.10% | −0.07 |
| USMV | US minimum volatility | 14.8 | +0.49% | 0.30 |
| SPLV | S&P 500 low volatility | 15.3 | +0.10% | 0.05 |
| IWM | Russell 2000 | 26.2 | +0.19% | 0.10 |
| SVXY | short VIX futures | 14.9 | −0.70% | −0.06 |
| NSPY | S&P 500 overnight only | 1.1 (closed 2023) | −13.4% | −1.71 |
| NIWM | Russell 2000 overnight only | 1.1 (closed 2023) | −16.4% | −1.80 |
| BTAL | anti-beta long/short | 15.0 | +4.37% | 1.17 |
| QMNIX | AQR Equity Market Neutral | 11.9 | **+5.83%** | **2.10** |

All eight long-only factor funds have alphas within ±1%/yr of zero, and none is
statistically different from it. The only overnight-return ETFs were liquidated after 14
months. **The single significant live result is QMNIX,** a professionally run market-neutral
fund. Caveats: it's a long/short book across hundreds of stocks, which a retail account can't
replicate; it lost −11.7%, −11.3% and −19.6% in 2018–20 before gaining +17% to +27% a year
since 2021; and it is a survivor of a fund family that has closed others. That's one data
point, not a strategy.

---

## When things failed (regimes, labelled after the fact)

- **Short vol breaks in stress.** SVXY buy & hold: recession-regime Sharpe −2.36, bear −0.89,
  Feb 2018 −91.5%, COVID −55%. Put-writing: bear −0.40, recession −0.45.
- **Volatility management fails in bear regimes** (Sharpe −1.81). It cuts exposure after the
  crash and then misses the rebound.
- **Momentum crashes.** UMD's worst month was −34.6%; its Sharpe was +0.64 in low-volatility
  regimes and −0.02 in high.
- **Defensive tilts are insurance, not alpha.** The low-beta long-only tilt had Sharpe +0.51
  in bear markets and −0.27 in bull markets. Low residual variance and low net issuance show
  the same pattern.

---

## Seven errors caught this phase

Each of these could have faked an edge or hidden one. They are why the harness has a
known-answer test suite, a data audit and a truncation test.

1. **The Fed's 2011–2020 pages use `<h5 class=…>`.** The FOMC parser silently skipped them, so
   the pre-FOMC test would have run on 2021–26 alone instead of 116 events since 2012.
2. **The cancelled 17–18 March 2020 FOMC meeting is still listed.** Kept, it would have booked
   a day the S&P fell about 5% as a statement day.
3. **September 2003 lists sessions on the 15th and 16th separately**, creating one phantom
   event. Consecutive-day sessions now collapse to the statement day.
4. **The backtester re-sized positions at every open.** At any weight other than 1× that adds
   compounding no account earns. A 2×-leverage known-answer test caught it before any strategy
   ran.
5. **A bad print in `^PUT`:** +35.3% on 2020-03-13 (SPY +8.6%), −28.4% the next session. It
   inflated H01's volatility by a quarter and flipped its skew from −0.7 to +3.1, disguising a
   crash-prone strategy as a lottery ticket. It was fixed by amendment A1 with a mechanical
   rule (1 bar in `^PUT`, 2 in `^BXM`, nothing else), and H01 is reported both ways.
6. **Dead funds are invisible to a live check.** NightShares NSPY/NIWM were liquidated in 2023,
   the PutWrite ETF's ticker (PUTW) was reused in 2026 so its history is gone, and XIV
   vanished in 2018. A live check can only ever see survivors.
7. **Stale opens.** Since 2009, 1.0–3.4% of sector-ETF bars print an open equal to the
   previous close, which books zero overnight return. This is flagged in H05's data-quality
   report.

Choices not pinned down by the pre-registration were made conservatively and are listed per
test in the log (`unreg` lines).

---

## What this does not show

- **Factor trading costs are assumptions**, order-of-magnitude figures from Novy-Marx &
  Velikov (2016). `phase1.json` has each factor's break-even cost. The academic long/short
  portfolios also ignore borrow fees and recalls, which only makes them look better.
- **Only published ideas were tested**, deliberately: a publication date is what splits
  in-sample from out-of-sample. A new idea has no such date and needs genuinely new data.
- **No intraday, options-surface, order-flow or paid alternative data.** Those hypotheses
  (Tier 3 in `PROGRAM.md`) can't be tested with free sources.
- **Regimes are labelled after the fact** (recession dates arrive months late), so they describe
  when strategies failed; they can't time anything.
- **I knew the literature going in**, including some post-publication evidence. The
  pre-registration stopped me tuning to this data, but it can't erase that prior.

---

## Next

The program's rule is that nothing is paper-traded before a PASS, and there were none.

Phase 2 is specified in `PROGRAM.md`: SEC-filing events such as post-earnings drift keyed to
8-K timestamps, and insider cluster buying from Form 4. Its prior is **lower** than Phase 1's.
The same publication decay applies, published work (Martineau 2022) finds post-earnings drift
gone in large caps, and the price data available for free leaves out delisted companies.
If it's run, it needs its own pre-registration, and the trial count carries forward from
`REGISTRY.csv`.
