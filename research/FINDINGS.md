# Diversified trend following: the honest result

**Run date:** 2026-09-10 · **Reproduce:** `python3 research/run_study.py etf`

## Why this test was worth running when ~50 others had already failed

Every earlier backtest in this project had the same shape: **one instrument,
long-or-flat, unscaled, judged against buy & hold of that same instrument.**

That shape structurally *cannot* find trend following. Trend following has
never beaten the S&P on raw return and does not claim to — its documented
value is portfolio-level: many uncorrelated markets, volatility-scaled, low
correlation to equities. Testing it one asset at a time against that asset is
like testing a seatbelt by checking whether it makes the car faster.

So this was a real gap, not a re-run. Diversified time-series momentum is
also the single best-documented systematic strategy in the literature —
Moskowitz-Ooi-Pedersen (2012), Hurst-Ooi-Pedersen (2017), positive in every
decade since 1880 across 67 markets. If anything was going to survive, this
was it.

**It did not survive.**

## What was built

| file | what it does |
|---|---|
| `data.py` | Yahoo daily bars, dividend-adjusted, cached. Universes: 19 ETFs, 16 futures, crypto. Splice cleaner for continuous futures. `^IRX` risk-free series. |
| `stats.py` | Sharpe, drawdown, Calmar, skew/kurtosis, **Probabilistic Sharpe**, **Deflated Sharpe**, minimum track record length. |
| `tsmom.py` | The strategy engine: 21/63/252 signals, EWMA vol targeting, portfolio construction, costs, causal vol scaling. |
| `run_study.py` | The six-part evaluation below. |

Pure stdlib + `requests` — no numpy/pandas, matching the rest of the project.

### Four bugs caught during the build, each of which manufactured fake edge

1. **`range=max` silently returns monthly bars.** Yahoo downsamples without
   warning. The first run was quietly a monthly study wearing a daily label.
2. **Yahoo's continuous futures are spliced, not back-adjusted.** `6J=F`
   prints −90% then +904% on consecutive days in Dec 2001. `clean_bars()`
   detects the signature — a large close-to-close gap *not* matched by a
   large intraday range — and rebases. 54 splices across 16 markets.
3. **The strategy was trading its own benchmark.** On the futures universe,
   `run_study.py` loaded SPY and IEF so the benchmarks would share a calendar —
   and passed them straight into the traded universe. Adding an equity sleeve
   to a diversifier during a 25-year bull market lifted the futures Sharpe from
   **0.27 to 0.31**. `trade_syms` now separates what is traded from what is
   merely carried for comparison.
4. **No risk-free rate anywhere.** This was the big one. Every Sharpe was
   really just return/vol, which massively flatters a low-vol, levered book.
   The long-only variant scored **0.69 and passed** the deflated-Sharpe test.
   Corrected to excess-of-cash it scores **0.45 and fails.** A 0.24 Sharpe
   swing from one missing line.

Also worth stating plainly: the "long-only, cash-account-realistic" variant
was running at **2.05× average leverage**, because the portfolio vol-scaler
sat on top of the `gross ≤ 1.0` cap. It was never implementable as described.

## The results — everything excess of cash, net of 5bp/side

### 1. Standalone (ETF universe, 19 markets, 2004–2026, 21.8 years)

| strategy | exCAGR | vol | **Sharpe** | maxDD |
|---|---|---|---|---|
| TSMOM long/short | +2.6% | 10.1% | **0.30** | −24% |
| TSMOM long-only | +4.1% | 10.0% | **0.45** | −21% |
| TSMOM futures universe (25.2y) | +2.2% | 10.2% | **0.27** | −28% |
| SPY buy & hold | +9.0% | 18.9% | **0.55** | −56% |
| 60/40 SPY/IEF | +6.4% | 10.9% | **0.63** | −33% |

**Nothing beats just holding an index fund, or 60/40.**

### 2. The diversification is real

Correlation to SPY: **+0.016.** On the 211 days SPY fell more than 2%, SPY
averaged −3.20% and trend averaged **+0.01%.** In the GFC it made **+18.5%**
while SPY lost 47%; in 2022 it made **+12.7%** while SPY lost 19%.

This part is genuine and structural, not fitted.

### 3. …but it does not clear the multiple-testing bar

90 configurations were run to *measure dispersion* (not to pick a winner —
the base config ranked 76th of 90). Deflated Sharpe, which asks whether the
result beats what N skill-less tries would produce by luck:

| trials assumed | luck bar (SR) | **DSR** |
|---|---|---|
| 90 | 0.63 | **0.067** |
| 200 | 0.69 | **0.035** |
| 1000 | 0.82 | **0.008** |

Anything under 0.95 means *not distinguishable from luck*. Days of track
record needed to clear the bar: **never, at this Sharpe.**

For calibration: pure Gaussian noise with Sharpe 0.75 scores PSR 0.99 alone
but DSR 0.11 against 50 trials. That is this project's entire history.

### 4. It decayed after publication — and so did the only surviving claim

MOP published the 21/63/252 construction in 2012 on 1985–2009 data.
Everything from 2012 on is true out-of-sample for these exact parameters.

| era | years | trend SR | SPY SR | **blend gain vs 60/40** |
|---|---|---|---|---|
| pre-pub ..2011 | 7.1y | 0.40 | 0.15 | **+0.17 SR** |
| post-pub 2012.. | 14.7y | 0.26 | 0.83 | **+0.01 SR** |

Futures universe is worse still: the blend gain was +0.12 SR pre-publication and **+0.01 after**, and trend lost **−17.3%** across 2011–2019 outright.

The diversification *benefit* — the last defensible claim — was worth +0.17
Sharpe before publication and **+0.01 after.** At 30–40% weight post-2012 it
is **negative.** Correlation drifted −0.08 → +0.12.

A benefit that is large before publication and ~zero after it is the
signature of an effect that was arbitraged away, or was never there.

### 5. The real world agrees

Actual managed-futures ETFs, net of fees, excess of cash, each on its own
calendar:

| fund | since | years | exCAGR | **exSR** | SPY exSR, same window |
|---|---|---|---|---|---|
| **WTMF** | 2011 | **15.6y** | −0.3% | **−0.00** | 0.77 |
| DBMF | 2019 | 7.3y | +6.3% | 0.56 | 0.72 |
| KMLM | 2020 | 5.7y | +3.7% | 0.32 | 0.74 |
| CTA | 2022 | 4.5y | +5.4% | 0.39 | 0.68 |
| TFPN | 2023 | 3.1y | +2.4% | 0.24 | 0.97 |

The only fund with a long live track record delivered **exactly zero** excess
return over 15.6 years. Professionals with real infrastructure, running this
exact strategy, in size — zero. The short-track-record funds all trail SPY
over their own windows.

That is independent confirmation of the backtest, from live money.

## Conclusion

Diversified time-series momentum is the most credible systematic strategy
that had not been tested here. Tested properly — excess of cash, costed,
splice-cleaned, deflated for multiple testing, split at publication date, and
checked against live funds — it is:

- **not a return engine** (loses to an index fund on every measure)
- **a genuine diversifier** (correlation +0.02, pays in crises)
- **whose diversification benefit has been ~zero for 14.7 years**
- **and which no live fund has converted into excess return over 15 years**

The one thing that still holds post-2012 is drawdown reduction: 60/40 alone
−22%, plus 20% trend −17%. You pay about **1.1%/yr of return** for that.
That is a real trade-off, and an honest one — but it is a risk-management
purchase, not a money-maker, and it is available in a ticker for 0.85%/yr
rather than as a bot to build and babysit.

**This does not support building a trading bot.** It is the 51st config and
it fails like the other 50 — but for the first time the failure is measured
against the right benchmark, with the right statistics, and corroborated by
live funds. That makes it a place to stop rather than another loop.

*Descriptive of the past only. Not a prediction, not investment advice. I am
not a licensed advisor and nothing here is a recommendation to buy or sell.*
