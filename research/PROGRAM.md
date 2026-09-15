# Edge Research Program

**Written:** 2026-09-10 · **Status:** Phase 1 complete, 0 of 31 passed (`PHASE1_RESULTS.md`) · Phase 2 pre-registered (`PREREG_PHASE2.md`), running
**Companion files:** `REGISTRY.csv` (every configuration ever tested) · `PREREG_PHASE1.md` (exact rules + gates, frozen before any Phase-1 result was seen)

> Descriptive research only. Nothing here is investment advice, a prediction, or a
> recommendation to buy or sell anything. I am not a licensed advisor, and I do not
> place orders or handle brokerage credentials — any live step is yours to take.

---

## 0. Starting point: what this project has already established

This program does not start at zero. **76 configurations** have already been tested
here (the project called it "60", but the groups in the log add up to 76; see
`REGISTRY.csv`). None beat an index fund. Three lessons from those failures shape
everything below:

1. **Daily-bar technical rules in liquid markets are dead on arrival.** 33 published
   pattern/indicator systems on crypto, then the classics on US ETFs, per-instrument
   walk-forward: nothing survived costs. Searching for a 77th indicator won't change that.
2. **Publication decay is the dominant pattern.** Diversified trend following
   (Sharpe gain vs 60/40 of +0.17 before publication, +0.01 after) and pairs trading
   (SR 0.70 in Gatev's sample, −0.18 in 2010-17) both worked *until they were published*.
   So every hypothesis below is judged on **post-publication data only**.
3. **Two fake wins came from construction artifacts, not markets:** pooling trades across
   instruments (Connors RSI2: "6.07x" → +1.1% CAGR per real account) and survivorship +
   equal-weighting (6 "winning" anomalies → 0 of 6 beat a no-signal control). So every
   test needs a **no-signal control** and **survivorship-free data**.

A bias I have to disclose: I know the published literature, including some evidence
published *after* each paper. That shaped which hypotheses I ranked highly. Pre-registration
stops me tuning to *this* data, but it can't erase what I already knew.

---

## 1. Where an edge could plausibly exist for this account

Ranked by how likely an edge is to survive for a **retail account with free data, no
co-location and no ability to short single stocks cheaply**:

| rank | category | why it could persist | why it's hard here |
|---|---|---|---|
| 1 | **Risk premia you are paid to bear** (volatility risk premium, equity factor premia) | It's compensation for crash/tail risk, not a mistake, so arbitrage doesn't remove it. | It's not "alpha". Returns come with left-tail risk that a Sharpe ratio understates. |
| 2 | **Structural / flow-driven timing** (FOMC, turn-of-month, overnight, auctions, rebalancing) | Driven by mechanical flows from large, price-insensitive players. The capacity is too small for big funds to bother with. | Small per-event edge. Costs and taxes can eat it. Calendar effects are easy to data-mine. |
| 3 | **Slow information diffusion** (post-earnings drift, insider buys, filing text) | Limited attention, and the data takes work to process. | Needs event timestamps (EDGAR) and survivorship-free prices. Decayed in large caps. |
| 4 | **Relative value** (pairs, ETF vs constituents) | Temporary price pressure mean-reverts. | Already tested: pairs decayed to zero after 2010. Crowded by stat-arb desks. |
| 5 | **Alternative data** (sentiment, jobs, web) | Hard-to-get information. | Paid, not point-in-time, and the vendor's backfill is itself a leakage source. |
| 6 | **Microstructure** (order-flow imbalance, auctions, spreads) | Genuine short-horizon predictability. | Needs paid tick/L2 data and low latency. Unwinnable against HFT from a retail API. |

---

## 2. Ranked hypotheses (30)

**Tier 1** = testable now with free, survivorship-free data and a long post-publication
window. It's pre-registered and being tested in Phase 1.
**Tier 2** = free data, but heavy engineering or survivorship-biased prices. Build next,
and only if Tier 1 shows the approach is worth it.
**Tier 3** = specified here for completeness. Data is paid or infeasible for this setup.

| # | ID | hypothesis | why it might exist | data | hold | what kills it | how to test | biggest bias / leakage risk |
|---|---|---|---|---|---|---|---|---|
| 1 | H01 | **Put-writing earns the volatility risk premium** (CBOE PUT index) | Investors overpay for crash insurance; dealers' capital constraints (Gârleanu-Pedersen-Poteshman 2009) | Yahoo `^PUT` 1996→, `^IRX` | 1 mo roll | Crash clustering, short-vol crowding, premium compression | Excess-of-cash SR & alpha vs SPY, post-2008 (index launched 2007), crisis windows, skew | Index is gross of option spreads; negative skew makes Sharpe look better than the risk; it may be repackaged beta |
| 2 | H02 | **Short VIX futures earn the roll yield** (SVXY, live ETF) | VIX futures trade above expected spot VIX (term premium) | Yahoo `SVXY` 2011→ | continuous | Feb-2018-type blow-ups; product redesign (−1x→−0.5x) | Live fund, all out-of-sample; alpha vs SPY, drawdown, tail | Survivorship: XIV died in 2018 and isn't in the data |
| 3 | H03 | **Short vol only in contango** (VIX < VIX3M) | Backwardation signals a regime where the premium turns negative | `^VIX`, `^VIX3M`, `SVXY` | days–weeks | Signal lag in fast crashes | Next-open execution, placebo = randomly shifted signal | Using the same close to both signal and trade (look-ahead) |
| 4 | H04 | **Pre-FOMC announcement drift** (Lucca-Moench 2015) | Uncertainty-resolution premium; dealer positioning before the statement | Fed calendars (scheduled meetings), SPY | 1 day | Publication (2011); press conference at every meeting since 2019 | Event returns 2012→ vs 1,000 random-day placebos | Including unscheduled meetings; using announcement-day info before it's public |
| 5 | H05 | **Returns accrue overnight, not intraday** (Cooper-Cliff-Gulen 2008) | Overnight inventory/illiquidity risk premium | SPY/QQQ/IWM/sectors OHLC; live NSPY/NIWM | overnight | Two trades a day of costs, short-term taxes, auction impact | Close→open net of costs, post-2009; live NightShares ETFs | Yahoo "open" ≠ an executable opening-auction price |
| 6 | H06 | **Turn-of-month effect** (Ariel 1987; Lakonishok-Smidt 1988) | Payroll/pension inflows land at month-end | SPY 1993→; French CRSP market 1926→ | 4 days | Flows smoothed over the month; front-running | Pre- vs post-1988, placebo = random 4-day blocks | Calendar data-mining (that's why the window is the published one) |
| 7 | H07 | **Volatility-managed equity** (Moreira-Muir 2017) | Volatility spikes aren't matched by expected-return spikes | SPY 1993→; French market | 1 mo | V-shaped recoveries; Cederburg et al. (2020) found it fails out-of-sample | Expanding-window scaling only, post-2017, permuted-weight placebo | **Scaling constant fitted on the full sample** (the documented look-ahead in the original) |
| 8 | H08a-k | **Equity factor premia, long/short:** size, value, momentum, ST reversal, LT reversal, profitability, investment, accruals, net issuance, low beta, low idiosyncratic volatility | Risk compensation or mispricing protected by limits to arbitrage | Ken French library (CRSP, survivorship-free) 1926/1963→ | 1–12 mo | McLean-Pontiff (2016): −58% after publication; crowding; costs | Post-publication SR & CAPM alpha, cost break-even, live L/S fund check | Academic portfolios are gross of costs and shorting frictions; not implementable retail |
| 9 | H09a-k | **Long-only factor tilts** (the implementable version of H08) | Same as H08 | French sorted portfolios; live ETFs MTUM/VLUE/QUAL/USMV/SPLV/IWD/SPHQ | 1–12 mo | Tilt is just beta or size; fund fees | Active return vs market, CAPM alpha, live-ETF alpha | Mistaking a beta or size tilt for alpha |
| 10 | H10 | **Industry momentum** (Moskowitz-Grinblatt 1999) | Industry news diffuses slowly (Hong-Torous-Valkanov 2007) | French 49 industries 1926→; SPDR sectors | 1 mo | Momentum crashes (2009) | Post-1999, random-industry placebo, EW-industries control | Changing industry definitions; skip-month choice |
| 11 | H11 | **Post-earnings drift via announcement return** (Brandt et al. 2008) | Underreaction and limited attention | EDGAR 8-K Item 2.02 acceptance timestamps + prices | 60 days | Martineau (2022): gone in large caps | Event study keyed to the *acceptance timestamp*, next-open entry | After-close releases traded at that day's close; survivorship in Yahoo prices |
| 12 | H12 | **Standardized unexpected earnings from XBRL** | Same as H11 | EDGAR `companyfacts` (`filed` date) | 60 days | Same as H11 | Seasonal random walk SUE, entry after the `filed` date | XBRL "latest value" includes restatements, so it isn't as-first-reported |
| 13 | H13 | **Opportunistic insider cluster buying** (Cohen-Malloy-Pomorski 2012) | Insiders' legal information advantage | EDGAR Form 4 (+ quarterly insider datasets) | 1–6 mo | 10b5-1 rule changes (2023); publication | Filing-acceptance timestamp as the info time; routine vs opportunistic split | Using the trade date instead of the filing date (up to 2 days early, much more before 2002) |
| 14 | H14 | **Treasury auction cycle** (Lou-Yan-Zhang 2013) | Dealers demand a price concession to absorb supply | fiscaldata.treasury.gov auctions; TLT/IEF | ~10 days | Dealer balance-sheet changes; predictable schedule gets front-run | Pre-auction short / post-auction long, placebo dates | Mixing auction, announcement and settlement dates |
| 15 | H15 | **Month-end pension rebalancing flow** (Harvey et al. 2024-25) | Mechanical rebalancing by balanced funds | SPY, TLT daily | 3–5 days | Rebalancing bands; recent publication | Month-to-date stock-bond spread computed through day −5 only | Very short out-of-sample window; month-to-date signal running into the decision day |
| 16 | H16 | **Intraday momentum** (Gao-Han-Li-Zhou 2018) | Late-day hedging and leveraged-ETF rebalancing | Yahoo 60m bars (only ~2 years) | 30–60 min | Short sample; costs | First-hour → last-bar regression, next-bar execution | Bar-timestamp alignment; low statistical power |
| 17 | H17 | **10-K "lazy prices"** (Cohen-Malloy-Nguyen 2020) | Investors ignore subtle year-over-year text changes | EDGAR 10-K/10-Q full text | 3–6 mo | Publication; NLP arms race | Cosine similarity vs prior filing, filing-date entry | Survivorship in prices; filing amendments |
| 18 | H18 | **Dividend-month premium** (Hartzmark-Solomon 2013) | Dividend-seeking demand is predictable | Yahoo dividend events | 1 mo | Publication | Predicted-dividend months vs others | Survivorship; using the declared date before it's known |
| 19 | H19 | **Index additions/deletions** | Forced index-fund demand | S&P announcements, Wikipedia change table | days | "Disappearing index effect" (Greenwood-Sammon 2022) | Announcement → effective-date returns | Announcement vs effective date; deleted firms missing from Yahoo |
| 20 | H20 | **Bond term premium timing** (term spread → duration) | Term premium is time-varying | FRED DGS10/DGS2/DTB3, IEF/TLT | 1 mo | Regime shifts in the policy rate | Expanding-window regression, post-2000 | Fitting the threshold on the full sample |
| 21 | H21 | **Gap fade in index ETFs** | Opening overreaction to overnight news | SPY/QQQ OHLC | intraday | Folklore-level evidence; this project's TA failures | Pre-set gap thresholds, placebo | Yahoo open; data-mined thresholds |
| 22 | H22 | **Sector ETF reversal after volume spikes** ("ugly" interaction) | Liquidity-driven price pressure | Sector ETF OHLCV | 1–5 days | Costs; low prior | Pre-set thresholds, placebo | Parameter mining |
| 23 | H23 | **Analyst estimate revisions** | Analysts herd and update slowly | I/B/E/S, Zacks (paid) | 1–3 mo | Crowding | — | Revision timestamps |
| 24 | H24 | **Short interest / days-to-cover** | Short sellers are informed | FINRA semi-monthly (short history), borrow data (paid) | 1 mo | Borrow cost eats it | — | Publication lag (~2 weeks) |
| 25 | H25 | **Options-implied signals** (skew, IV−RV per stock) | Informed traders use options | OptionMetrics (paid) | 1 wk–1 mo | Crowding | — | Stale option quotes at the close |
| 26 | H26 | **Order-flow / auction imbalance** | Price pressure | TAQ, exchange imbalance feeds (paid) | seconds–minutes | Latency vs HFT | — | Timestamp precision |
| 27 | H27 | **News sentiment** | Slow reaction to soft information | RavenPack etc. (paid) | days | Crowding | — | Vendor backfill ≠ real-time |
| 28 | H28 | **Job postings / web traffic / app data** | Nowcasts fundamentals | Paid alternative-data vendors | 1–3 mo | Decay; cost | — | Panel changes, backfill |
| 29 | H29 | **Search-attention (Google Trends)** | Retail attention → temporary demand | Google Trends (free, sampled) | 1 wk | — | — | Data is re-sampled and re-normalized on every pull, so it's **not point-in-time** |
| 30 | H30 | **FDA decision events** | Binary events are mispriced | PDUFA calendars (paid/scattered) | days | Binary tail risk | — | Event-date errors; survivorship of small biotechs |

**Deliberately excluded** (already tested here and dead, per `REGISTRY.csv`): candlestick
patterns, indicator systems, Connors RSI variants, crypto cross-sectional momentum,
single-asset trend following, diversified TSMOM, distance-method pairs, crypto basis
carry, meme/scalping/copy-trading.

---

## 3. Data: sources and point-in-time rules

Every feature carries an `info_ts` (when it could first be known). Every position carries
a `decision_ts`. The engine enforces `info_ts ≤ decision_ts` with a **truncation test**:
recompute signals with all data after a random cut date deleted. Every decision up to that
date must be identical. Any difference is look-ahead, and the test fails.

| source | what | timestamp semantics | survivorship | corporate actions | known traps |
|---|---|---|---|---|---|
| Yahoo chart API | Daily OHLC for ETFs/indices, 60m for 2y | Bar date = session date; close known at 16:00 ET | ETFs/indices OK; **delisted funds vanish** (XIV, original PUTW — ticker reused in 2026) | `adjclose` folds dividends/splits; OHL rescaled by the same factor | `range=max` returns monthly bars; continuous futures are spliced; "open" may not be the auction price |
| Ken French library | Factor & sorted-portfolio returns, daily/monthly | Month/day of the return; portfolios formed with FF's lags (accounting data ≥6 months old at June formation) | **CRSP-based, includes delisted firms** | Handled by CRSP | Gross of costs; academic long/short; values are revised when CRSP updates |
| `^IRX` / French RF | Cash rate | Daily | n/a | n/a | `^IRX` is an annualized discount rate in % |
| FRED | Recession (USREC), DGS10, CPI, VIX | Observation date ≠ release date (CPI ~2 wks late, NBER dates months–years late) | n/a | n/a | **Used only to label regimes after the fact — never as a trading signal** |
| Federal Reserve | FOMC calendars 1994→ | Statement ~14:00-14:15 ET on the final meeting day; schedule published a year ahead | n/a | n/a | Exclude conference calls and unscheduled meetings |
| CBOE / Yahoo `^VIX`, `^VIX3M`, `^VIX9D` | Volatility indices | Close at 16:15 ET (15 min after equities) | n/a | n/a | A VIX close is not observable at the 16:00 equity close, so signals trade at the **next open** |
| SEC EDGAR (Tier 2) | 8-K, 10-K/Q, Form 4, XBRL | `acceptanceDateTime` is the info time | Includes dead filers; **prices for dead tickers are not on Yahoo** | n/a | XBRL frames hold latest restated values, not as-first-reported |
| Treasury fiscaldata (Tier 2) | Auction results | Auction date / announcement date / issue date are distinct | n/a | n/a | Must pick the date the market actually knew |

---

## 4. Research / backtesting architecture

```
research/
  data.py        Yahoo bars, splice cleaning, ^IRX            (existing)
  sources.py     French library, FRED, FOMC dates             (new, cached, point-in-time notes)
  engine.py      weight-path backtester: session model        (new)
                 overnight segment close[t-1]->open[t], intraday open[t]->close[t]
                 exec = "close"     decision must use info available before the close (calendar only)
                 exec = "next_open" decision at close t, filled at open t+1
                 per-side costs on |Δweight|, financing spread on leverage, cash earns rf
  evaluate.py    full metric set, Newey-West alpha, multi-factor regression,
                 stationary block bootstrap, Monte Carlo horizons, placebo percentile,
                 regimes, sub-periods, deflated Sharpe, the G1-G9 gate evaluator
  leakage.py     truncation test applied to every weight function
  h_*.py         one module per hypothesis family; each returns a standard result record
  run_phase1.py  runs everything pre-registered, prints the report, writes results JSON,
                 prints the SHA-256 of PREREG_PHASE1.md it was tested against
  REGISTRY.csv   every configuration ever run, with status (never deleted)
```

Design rules:
- **Signal functions return weight arrays; the engine alone turns weights into P&L.** That
  makes the backtest engine reusable as the paper/live signal layer (§6).
- **Excess of cash everywhere.** Leverage pays rf + 1.5%/yr; unused capital earns rf.
- **The headline is always the untouched pre-registered config.** Neighbours only
  measure stability.
- **No pooling across instruments.** One account, one equity curve.

---

## 5. Evaluation protocol (applies to every hypothesis)

**Metrics reported:** gross & net return, CAGR, volatility, Sharpe, Sortino, max drawdown,
Calmar, win rate, profit factor, average & median trade, number of trades, average holding
period, turnover, exposure (long/short/gross), worst day, worst month, recovery time,
skew, kurtosis, 5% CVaR, lag-1 autocorrelation.

**Out-of-sample:** strategies taken from the literature use **post-publication data only**
for gating. The pre-publication period is shown, but it was in-sample for the authors.
Anything with fitted parameters uses an anchored walk-forward (expanding train, rolling
test blocks).

**Controls:** buy & hold of the traded asset; the relevant no-signal control (EW universe,
market); randomized placebos (random event dates, shifted signals, permuted weights, random
selection) that keep the same exposure and turnover.

**Statistics:** Newey-West t-stats; stationary block bootstrap confidence intervals;
regression on market and FF5+UMD factors ("is this just beta?"); Monte Carlo distribution
of 1-year and 3-year outcomes (reused later as the drift detector for paper and live).

**Regimes (descriptive, labelled after the fact):** bull/bear (market >20% below its
peak), high/low volatility (63-day realized vol vs expanding median), rising/falling
10-year yield (252-day change), NBER recession vs expansion, CPI YoY ≥4% vs <4%.

**Multiple testing:** the deflated Sharpe ratio uses the **cumulative** number of
configurations in `REGISTRY.csv` (legacy configurations + new hypothesis clusters). Trial
dispersion comes from the cross-section of Phase-1 out-of-sample Sharpes.

---

## 6. Minimum evidence before any real money (the gates)

### Gate A — research → paper trading (pre-registered G1-G9, see `PREREG_PHASE1.md`)
- **G1** Post-publication net excess Sharpe > 0 **and** bootstrap 95% CI lower bound > 0
- **G2** Post-publication alpha vs benchmark > 0 with Newey-West t ≥ 2.0 (not repackaged beta)
- **G3** Deflated Sharpe ≥ 0.95 against the cumulative trial count
- **G4** Still positive at 2× assumed costs
- **G5** Positive in at least 2 of 3 equal out-of-sample sub-periods
- **G6** ≥75% of pre-registered neighbours positive; median neighbour ≥ 50% of base
- **G7** Beats the 95th percentile of its randomized placebo
- **G8** Implementable in a US retail account (no single-stock shorting, leverage disclosed)
- **G9** Where a live fund runs the idea (≥4 years), its live alpha vs SPY is > 0

**PASS** = all of them → eligible for paper trading. **WATCH** = G1, G2, G4, G8 pass but
another gate fails → no paper trading; list exactly what evidence is missing. **FAIL** =
G1, G2 or G4 fails. **NI** = would pass but can't be implemented.

### Gate B — paper → Stage 3 (tiny live)
- Paper runs **≥6 months and ≥30 independent decisions**, whichever is longer.
  (A monthly strategy paper-trades to validate *operations*, not the edge.)
- Signals regenerated later by the backtest engine on final data **match paper signals
  100%** (differences allowed only for documented data revisions).
- Median fill slippage ≤ modeled cost; 90th percentile ≤ 2× modeled.
- Zero unreconciled positions; zero unhandled exceptions; data-staleness alarm and kill
  switch both drilled.
- Paper return inside the backtest's Monte Carlo 5th-95th percentile band for the same
  horizon. If it isn't, investigate before going further.

### Gate C — Stage 3 → Stage 4 (increase size)
- ≥6 months live at the tiny allocation; realized costs ≤ 1.5× modeled; live return inside
  the 5-95% band; no risk-limit breach; your written sign-off.
- Size steps at most 2× per 6 months. Target size comes from volatility and drawdown
  tolerance, never from recent P&L.

---

## 7. Paper-trading architecture (same code as the backtest)

```
 scheduler (cron, market calendar aware)
   └─ DataLayer.fetch_latest()        same loaders as research; staleness + sanity checks
   └─ Strategy.weights(history)       SAME function the backtest calls; truncation-tested
   └─ Portfolio.targets(weights, nav) rounding, min trade size, no-trade band
   └─ Risk.check(targets, state)      hard limits (§8); on breach → HALT, no orders
   └─ Execution.orders(targets, positions)   diff → orders with unique client IDs
   └─ Broker adapter  ───────────────┐
        SimBroker   (fills at next open/close from the data feed + modeled slippage)
        PaperBroker (e.g. Alpaca/IBKR paper API — account & keys created by you)
   └─ Reconciler: broker positions vs internal ledger after every cycle; mismatch → HALT
   └─ Journal: append-only JSONL of every signal, order, fill, rejection, P&L, error
   └─ Monitor: expected vs realized slippage, P&L vs Monte Carlo band, signal frequency
```

## 8. Live-trading architecture

The same stack as §7 with a live broker adapter, plus:

- **Authorization gates checked at startup and every cycle.** Strategy PASS record present;
  Gate B/C evidence file present; data feed fresh; broker connectivity OK; account state
  read from the broker (never assumed); risk limits loaded; reconciliation clean; kill
  switch absent. Any failure → **no orders**.
- **Hard risk limits (defaults):** gross exposure ≤ 1.0×; single ETF ≤ 60%, single stock
  ≤ 5%; daily loss ≥ 2% of strategy capital → halt for the day and require review;
  drawdown ≥ min(20%, 1.5× backtest 95th-percentile DD) → halt and require review; order
  size ≤ 1% of 20-day ADV; limit-price collar ±50bp from the last trade; no order if data is
  >5 minutes stale during the session. **No martingale, no averaging down, no size increase
  after losses.**
- **Order hygiene:** every order has a unique client ID, timestamp, symbol, side, quantity,
  type, limit price, strategy ID, the risk checks it passed, and its status. Delayed
  confirmations are *queried*, never re-sent.
- **Kill switch:** a file flag and an env flag, checked before every order. It stops new
  orders immediately and leaves positions for a human decision.
- **Human in the loop:** I can build, test and monitor this. Placing live orders, funding
  the account and holding API keys stay with you.

## 9. Strategy kill criteria (set before going live)
Pause and require review if any of these happen: drawdown > 1.5× backtest max DD; rolling
12-month live Sharpe below the backtest's 5th percentile; realized costs > 2× modeled for 3
consecutive months; signal frequency outside the backtest's 1st-99th percentile; market beta
drifts by >0.3 from the backtest; data-quality alarms on 3+ days in a month. **A killed
strategy is never re-tuned and restarted.** Coming back requires a new pre-registered
hypothesis and fresh out-of-sample evidence.
