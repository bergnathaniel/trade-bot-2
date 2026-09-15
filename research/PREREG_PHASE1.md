# Phase 1 Pre-Registration

**Frozen:** 2026-09-10, before any Phase-1 return series was computed.
**Integrity:** `run_phase1.py` prints this file's SHA-256 with every result. **Never edit
this text after results exist.** Changes go in a dated *Amendments* section at the bottom,
with the reason, and results are then reported under both the original and amended specs.
Any choice not pinned down here is made conservatively at build time and logged in the
results under `unregistered_choices`.

---

## A. Global conventions

| item | rule |
|---|---|
| Dates | Session date, YYYY-MM-DD |
| Cash rate | Yahoo-based tests: `^IRX` (annualized % → /100/252). French-based tests: French `RF` |
| Returns | **Excess of cash**. Long/short factor returns are self-financing (no rf subtracted) |
| Annualization | √252 daily, √12 monthly |
| Leverage | Borrowed fraction pays rf + 1.50%/yr |
| Costs per side on \|Δweight\| | SPY, QQQ, DIA **1 bp** · IWM, XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY **2 bp** · SVXY **5 bp** |
| Cost drags (%/yr, applied pro-rata) | CBOE option-strategy indices **0.50** · factor L/S: SMB, HML, RMW, CMA, AC, NI, BETA **1.0**; LTR **1.5**; UMD, RESVAR **3.0**; STR **8.0** · factor long-only = ½ of L/S · EW-weighted neighbours = 2× their base · industry momentum L/S **2.0**, long-only **1.0** |
| Cost stress (G4) | All costs and drags ×2 (financing spread not doubled) |
| Bootstrap | Stationary bootstrap, mean block 21 days / 6 months, B = 2000, seed 20260910, percentile 95% CI |
| Newey-West lags | floor(4·(T/100)^(2/9)) |
| Placebos | B = 1000, seed 20260911 |
| Sub-periods (G5) | Out-of-sample series split into 3 contiguous blocks of equal observation count |

The factor cost drags are **order-of-magnitude assumptions** informed by Novy-Marx & Velikov
(2016). They are not measured here. The results report the break-even drag so the reader can
substitute their own.

## B. Gates (evaluated on the out-of-sample window of each base configuration)

- **G1** Net excess Sharpe > 0 **and** bootstrap 95% CI lower bound > 0.
- **G2** Alpha from regressing net excess returns on the benchmark's excess returns > 0 with
  Newey-West t ≥ 2.0. Benchmark: SPY excess (Yahoo tests), Mkt-RF (French tests).
- **G3** Deflated Sharpe ≥ 0.95. N = legacy configurations in `REGISTRY.csv` (**76**) + Phase-1
  hypothesis clusters (**17**) = **93**. σ_SR = sample stdev of the out-of-sample net Sharpe
  across all **31** Phase-1 base configurations. Sensitivity (not gated): N = 17 and N = 200.
- **G4** Out-of-sample net Sharpe > 0 at 2× costs.
- **G5** Compounded net excess return > 0 in ≥ 2 of 3 sub-periods.
- **G6** ≥ 75% of neighbours have out-of-sample net Sharpe > 0 **and** median neighbour Sharpe
  ≥ 0.5 × base. Automatically fails if base Sharpe ≤ 0. N/A if no neighbours are available.
- **G7** Base out-of-sample net Sharpe > 95th percentile of placebo Sharpes. N/A where no
  placebo is defined.
- **G8** Implementable in a US retail account: long-only or index options/ETFs, no single-stock
  shorting, leverage ≤ 2× and disclosed.
- **G9** Every mapped live fund with ≥ 4.0 years of daily history has alpha vs SPY
  (Newey-West) point estimate > 0 over its full history. N/A if none is mapped.

**Classification:** PASS = no gate fails (N/A doesn't count as a failure) → eligible for
paper trading · FAIL = G1, G2 or G4 fails · NI = only G8 fails among G1/G2/G4/G8, so it
would pass but can't be implemented · WATCH = G1, G2, G4, G8 pass but another gate fails.

The 17 clusters are: VRP, FOMC, OVERNIGHT, TOM, VOLMGD, SMB, HML, UMD, STR, LTR, RMW, CMA,
AC, NI, BETA, RESVAR, INDMOM.
The 31 base configs are: H01, H02, H03, H04, H05, H06, H07, H08×11, H09×11, H10-LS, H10-LO.

---

## C. Hypotheses

### H01 — Volatility risk premium: CBOE S&P 500 PutWrite index
- **Series:** Yahoo `^PUT` close-to-close returns. Net excess = r − rf − 0.50%/252.
- **Out-of-sample:** ≥ 2008-01-01 (index launched 2007; earlier data is backfilled). Earlier data shown, not gated.
- **Benchmark:** SPY. **Neighbours:** those of `^BXM ^BXMD ^BXY ^CNDR ^WPUT ^PUTY` with ≥ 90% out-of-sample date coverage vs SPY, same drag; G6 = N/A if fewer than 2.
- **G7** N/A · **G8** PASS (cash-secured index puts / ETFs) · **G9** N/A (the only put-write ETF with history, PUTW, is no longer on Yahoo — its ticker was reused in 2026 — a survivorship note).

### H02 — Volatility risk premium: short VIX futures via SVXY (live ETF)
- **Series:** SVXY adjusted close returns, buy & hold. Net excess = r − rf; 5 bp on day 1.
- **Out-of-sample:** full history (2011-10-04 →) — it's a live product. Note: leverage changed from −1× to −0.5× on 2018-02-27.
- **Benchmark:** SPY · **G6** N/A · **G7** N/A · **G8** PASS · **G9** SVXY itself.

### H03 — Short vol only in contango
- **Signal:** s_t = 1 if `^VIX` close_t < `^VIX3M` close_t, else 0 (carry the last value if either is missing). Decision at close t, **filled at the next open**, on SVXY. 5 bp/side.
- **Out-of-sample:** ≥ 2015-01-01 (Simon & Campasano 2014). Sample starts 2011-10-04.
- **Neighbours (4):** VIX/VIX3M < 0.90, < 0.95, < 1.05; `^VIX9D`/`^VIX` < 1.00.
- **Placebo:** circular shift of the whole s series by k ~ U{63, n−63}, recompute, keep the out-of-sample Sharpe.
- **Benchmark:** SPY · **G8** PASS · **G9** N/A.

### H04 — Pre-FOMC announcement drift
- **Events:** scheduled FOMC meetings 1994-01-01 → present, from federalreserve.gov. Statement date d = last calendar day of the meeting. Exclude conference calls, unscheduled meetings, notation votes, and any d that isn't a SPY trading day.
- **Base:** long SPY close(d−1) → close(d) (d−1 = previous trading day); MOC both sides, allowed because the calendar is public in advance. 1 bp/side.
- **Out-of-sample:** ≥ 2012-01-01 (NY Fed Staff Report 512, Sept 2011).
- **Neighbours (5):** close(d−2)→close(d); open(d)→close(d); close(d−1)→open(d); base on QQQ; base on IWM.
- **Placebo:** for each year, draw as many days as that year has events, uniformly without replacement from SPY trading days more than 3 trading days from any statement date; hold close(p−1)→close(p).
- **Benchmark:** SPY · **G8** PASS · **G9** N/A.

### H05 — Overnight return premium
- **Base:** SPY, hold close(t) → open(t+1) every day, flat intraday. 1 bp/side, 2 sides/day. The rf charge applies to the overnight weight.
- **Out-of-sample:** ≥ 2009-01-01 (Cooper, Cliff & Gulen 2008). Sample starts 1993-02-01.
- **Neighbours (12):** QQQ, DIA (1 bp); IWM, XLB, XLE, XLF, XLI, XLK, XLP, XLU, XLV, XLY (2 bp).
- **Reported control:** intraday-only (open → close).
- **Data QC (reported, flag if > 1% of out-of-sample bars):** open equal to the previous close (|o/c₋₁ − 1| < 1e-6); open outside [low, high].
- **Benchmark:** SPY · **G7** N/A · **G8** PASS (MOC/MOO orders) · **G9** NSPY (NIWM reported, not gated).

### H06 — Turn of the month
- **Base:** SPY. Day −1 = last trading day of month m; +1..+3 = first three trading days of m+1. Hold the daily returns of days {−1, +1, +2, +3}: buy MOC at close of day −2, sell MOC at close of day +3. 1 bp/side. Skip windows that run past the data.
- **Out-of-sample:** the whole SPY history (1993 →) is post-publication (Ariel 1987; Lakonishok-Smidt 1988).
- **Reported, not gated:** French CRSP value-weighted market 1926-07 →, pre < 1988-01-01 vs post, zero cost.
- **Neighbours (8):** SPY windows {−1..+2}, {−1..+4}, {−2..+3}, {−2..+4}, {−3..+3}; base window on QQQ, IWM, DIA.
- **Placebo:** each month, hold one block of 4 consecutive trading days starting uniformly at trading day s ∈ [5, N_m − 5] of that month.
- **Benchmark:** SPY · **G8** PASS · **G9** N/A.

### H07 — Volatility-managed equity (Moreira-Muir)
- **Base:** SPY. RV_m = Σ r_d² over trading days in month m. RVbar_m = expanding mean of RV_1..RV_m. w_{m+1} = min(1.0, RVbar_m / RV_m), decided at the month-end close, **filled at the next open**; the rest earns cash. First 12 complete months: w = 1. 1 bp/side on |Δw|.
- **Out-of-sample:** ≥ 2017-01-01 (Journal of Finance 2017). Sample starts 1993.
- **Neighbours (4):** cap 2.0 with financing; w = min(1, √(RVbar/RV)); RV over the trailing 63 trading days scaled by 21/63; base with a no-trade band (rebalance only if |Δw| ≥ 0.10).
- **Placebo:** permute the out-of-sample monthly weights (pre-OOS weights unchanged).
- **Reported, not gated:** French market 1926 →, 1-day lag, zero cost, pre/post 2017.
- **Benchmark:** SPY · **G8** PASS · **G9** N/A.

### H08 — Equity factors, long/short (French, monthly)
Out-of-sample starts in January of the year after publication. Missing values (≤ −99.99) are dropped.

| id | series | publication | OOS from | neighbours (VW decile spread; EW quintile spread) |
|---|---|---|---|---|
| SMB | F-F 3-factor `SMB` | 1981 | 1982-01 | ME file Lo−Hi |
| HML | F-F 3-factor `HML` | 1985 | 1986-01 | BE-ME file Hi−Lo |
| UMD | F-F momentum factor | 1993 | 1994-01 | Prior_12_2 Hi−Lo (VW & EW deciles) |
| STR | F-F ST reversal factor | 1990 | 1991-01 | Prior_1_0 Lo−Hi (VW & EW deciles) |
| LTR | F-F LT reversal factor | 1985 | 1986-01 | Prior_60_13 Lo−Hi (VW & EW deciles) |
| RMW | F-F 5-factor `RMW` | 2013 | 2014-01 | OP file Hi−Lo |
| CMA | F-F 5-factor `CMA` | 2004 | 2005-01 | INV file Lo−Hi |
| AC | AC file VW Lo 20 − Hi 20 | 1996 | 1997-01 | Lo10−Hi10 VW; Lo20−Hi20 EW |
| NI | NI file VW Lo 20 − Hi 20 | 2008 | 2009-01 | Lo10−Hi10 VW; Lo20−Hi20 EW |
| BETA | BETA file VW Lo 20 − Hi 20 | 1972 | 1973-01 | Lo10−Hi10 VW; Lo20−Hi20 EW |
| RESVAR | RESVAR file VW Lo 20 − Hi 20 | 2006 | 2007-01 | Lo10−Hi10 VW; Lo20−Hi20 EW |

- **Net** = gross − drag/12 · **Benchmark** Mkt-RF (CAPM alpha gated; FF5+UMD alpha reported)
- **G7** N/A · **G8** FAIL (not implementable retail) · **G9** QMNIX; BETA also BTAL.

### H09 — Equity factors, long-only tilts (French, monthly)
- **Long leg (VW):** SMB → ME Lo 20 · HML → BE-ME Hi 20 · UMD → Prior_12_2 Hi PRIOR · STR → Prior_1_0 Lo PRIOR · LTR → Prior_60_13 Lo PRIOR · RMW → OP Hi 20 · CMA → INV Lo 20 · AC, NI, BETA, RESVAR → Lo 20.
- **Strategy series for G1/G3-G6:** active = long leg − market total return (Mkt-RF + RF) − drag/12.
- **G2:** CAPM alpha of (long leg − RF − drag/12) on Mkt-RF.
- **Neighbours (2):** quintile bases → VW extreme decile + EW same quintile; decile bases → VW adjacent decile + EW same decile.
- **Reported:** active return vs the EW average of all quintiles (construction control).
- **G7** N/A · **G8** PASS · **G9** UMD → MTUM · HML → VLUE, IWD · RMW → QUAL, SPHQ · BETA → USMV, SPLV · SMB → IWM · others N/A.

### H10 — Industry momentum (French 49 industries, VW, monthly)
- At the end of month m, formation return F_i = Π(1+r) over months m−11..m−1 (all 11 must be valid). n = eligible industries (no position if n < 20); k = floor(0.2·n). Long the top k, short the bottom k, equal-weighted, hold m+1. A missing holding-month return counts as 0.
- **H10-LS** net = long − short − 2.0%/12 · **H10-LO** active = long − EW(all eligible) − 1.0%/12.
- **G2:** CAPM alpha vs Mkt-RF (LO: long − RF − drag). **Out-of-sample:** ≥ 2000-01 (Moskowitz-Grinblatt 1999).
- **Neighbours (4):** formation 6-1, 12-0, 6-0; k = floor(0.1·n).
- **Placebo:** each month, random k long and k disjoint short from the eligible set.
- **G8:** LS FAIL, LO PASS · **G9** N/A.
- **Reported, not gated:** 9 SPDR sectors, top 3 by 12-1 return, month-end decision, next-open fill, 2 bp/side, active vs EW-9.

---

## D. Also reported for every base config (descriptive, never gated)
Full metric table · regimes (bull/bear, vol, rates, recession, inflation) · crisis windows
(GFC 2007-10-09→2009-03-09, Volmageddon 2018-01-26→2018-02-09, COVID 2020-02-19→2020-03-23,
2022 bear 2022-01-03→2022-10-12) · Monte Carlo 1y/3y P(loss), 5th-percentile return and max
DD · factor regressions · look-ahead truncation test result.

## Amendments

The original frozen text above hashed to
`sha256 abafdd5bcb9fbbd484f3577214a982946edc81c7d394af2401a0dac4c1ba63a1` when the first
Phase-1 run used it (log: `results/phase1_run.log`). Anything below was added after that run.

### A1 — 2026-09-11: bad-print hygiene for option-strategy index closes (data fix, not a strategy change)

**What was seen.** The first run showed H01 with a −28.4% worst day, kurtosis 350 and
lag-1 autocorrelation −0.35, which is impossible for a put-writing index. Yahoo's `^PUT`
close for 2020-03-13 (2050.28) is a bad print: +35.3% that day while SPY rose 8.6% and
`^BXM` 9.4%, then −28.4% the next session. The two-day move (−3.1%) matches SPY (−3.3%).
`^BXM` has two more: 2004-06-28 and 2010-01-11, −7.6% and −9.0% with SPY flat, each fully
reversed the next day.

**Rule.** For option-strategy index series only (`^PUT`, `^BXM`): close c_t is a bad print
when |r_t| > 3·|r_SPY,t| + 5% **and** r_{t+1} has the opposite sign **and**
|r_{t+1}| > 0.5·|r_t|. It is replaced by the geometric midpoint c_{t−1}·√(c_{t+1}/c_{t−1}),
which preserves the two-day return exactly.

**Disclosure.** This rule was written *after* seeing the anomaly, which is why it is an
amendment rather than part of the frozen spec. It replaces 1 bar in `^PUT` and 2 in
`^BXM` and touches nothing else, since all other moves above 7% in either index track
SPY. It can only affect H01 and its reported `^BXM` neighbour. The fix removes a variance
spike, so it can only *help* H01. H01 is therefore reported under both specs, the original
stays the headline, and the trial count and Sharpe dispersion stay at the original run's
values.
