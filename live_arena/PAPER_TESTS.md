# Live Arena paper tests

**Set up:** the weekend of 2026-09-12, before any price in the test window existed.
**Start:** Monday **2026-09-14**. Only candles dated on or after it count; earlier prices only warm up
the indicators.
**Reviews:** **2027-03-14** (6 months) and **2027-09-14** (1 year).
**Fingerprints:** `PAPER_TESTS.sha256` holds the SHA-256 of the app, the server and the basket lists
at setup. It also fingerprints the app's bot-rules section on its own, so a change to how results are
displayed can be told apart from a rule change. If a bot rule or a list changes, the paper test
restarts with a new start date. The old test is never continued under new rules.

---

## What's being tested, and why

| test | strategy | why it's here | fee per trade |
|---|---|---|---|
| Crypto: 29 Coinbase coins ranked 21–250 | Crash Buyer, Martingale Doubler, Pyramid Builder | Beat luck and beat holding the coins on unseen coins, but not holding bitcoin (`CRYPTO_SEARCH.md`) | 0.25% |
| Micro-caps: 60 random $50M–$300M US stocks | Martingale Doubler | Beat luck on unseen micro-caps, but made less than half of what IWC made (`CONFIRM.md`) | 0.50% |
| QQQ and SPY | IBS Swing | Beat 95% of random timing on QQQ, but only matched the index's return per unit of risk (`research/PHASE7_RESULTS.md`) | 0.01% |
| S&P 500 | Leveraged trend: SSO while the S&P 500 closes above its 200-day average, else cash | Made more money than SPY since 2017 by using leverage, with the same return per unit of risk (`research/PHASE5_RESULTS.md`) | 0.02% |
| Crypto: all 29 coins | The 22 other bots with a positive average in the 93-bot basket test (listed below) | A positive average on crypto group A (0.25% per trade, next-open fills) when all 93 bots ran there on 2026-09-12. Keltner Breakout led at +175.5%, but its median coin made +1.8% and FET alone carried it. Crash Buyer, Martingale and Pyramid were positive too and are already in the first crypto test | 0.25% |
| Micro-caps: all 60 stocks | The 21 other bots with a positive average in the 93-bot basket test (listed below) | A positive average on micro-cap basket A (0.50% per trade, next-open fills) when all 93 bots ran there on 2026-09-12. Crash Buyer led at +34.8%, and none came close to holding IWC (+66.8%). Martingale was positive too and is already in the first micro-cap test | 0.50% |
| Both markets: all 29 coins, and all 60 micro-cap stocks | Breakout on Volume, Hikkake and Bull Flag, each run in both markets | Of the 39 bots added last on 2026-09-12, the only ones with a positive average in both the crypto group A and micro-cap basket A tests, apart from Santa Claus Rally (see below). None beat the luck bar in both | 0.25% on coins, 0.50% on stocks |
| Crypto: all 29 coins | The 10 other newest bots with a positive average in the 132-bot crypto basket test (listed below) | Added on request after being left out. Except Santa Claus Rally, each lost money in the micro-cap basket test | 0.25% |
| Micro-caps: all 60 stocks | The 9 other newest bots with a positive average in the 132-bot micro-cap basket test (listed below) | Added on request after being left out. Except Santa Claus Rally, each lost money in the crypto basket test | 0.50% |

None of these passed their earlier tests. They're the closest things found, and this is the only
test left on prices nobody has searched.

The 22 bots, from the highest group A average down: Keltner Breakout, Ichimoku Cloud, Ratio Snapback,
Breakout Hunter, Awesome Oscillator, Regression Slope, Double Bottom, Ratio Breakout, Big Candle, Chaikin
Money Flow, ADX Trend Strength, Darvas Box, Scale-Out Trader, ConnorsRSI, Trailing Stop Rider, Risk 1% Per
Trade, Winning Streak Doubler, Volatility-Sized Trend, Three Lower Closes, Momentum, Panic Candle Buyer and
Bitcoin Follower. A positive average on coins that were already searched is the weakest reason for any test
in this file, so this one gets a stricter bar (below).

The 21 micro-cap bots, from the highest basket A average down: Crash Buyer, Stochastic Swing, Ladder Buyer,
Grid Trader, Inside Bar Breakout, Volume Surge, Key Reversal, Dip Buyer, Williams %R, Money Flow Dip, Double
Bottom, Bullish Harami, Band Bouncer, ADX Trend Strength, IBS Swing, TRIX Crosser, Opposite Day, VWAP Magnet,
Fibonacci Bounce, Three White Soldiers and Quiet Pullback. Opposite Day is a control with no edge by design. It
qualified by the same rule and stays in as a check on the bar. This test gets the same kind of stricter bar.

The both-markets test picks from the 39 bots added last. Four had a positive average in both basket tests:
Breakout on Volume (crypto +61.1%, micro-caps +8.1%), Hikkake (+8.5%, +3.9%), Bull Flag (+24.9%, +1.4%) and
Santa Claus Rally (+8.8%, +12.7%). Santa Claus Rally is left out. It only owns anything from December 23 to
January 2, so a one-year test would see a single holiday week, which can't tell a real effect from luck. The three
that are in didn't beat the luck bar in both markets, and none came close to holding bitcoin or IWC, so this is the
weakest evidence behind any test in this file. Bots that led only one market (Fisher Transform, Pocket Pivot, Chande
Momentum and others) were left out because they lost in the other one.

Those left-out bots were then requested too, so two more tests hold every other bot from the 39 newest with a
positive average in one basket test:

- **Crypto (10), from the highest group A average down:** Pocket Pivot, Chaikin Oscillator, Williams Alligator,
  Fractal Breakout, Sell in May, Santa Claus Rally, Half-Kelly Trend, Renko Bricks, RSI Trend and Rising Three
  Methods.
- **Micro-caps (9), from the highest basket A average down:** Fisher Transform, Chande Momentum, Ultimate
  Oscillator, Quiet-Day Money (NVI), Santa Claus Rally, Schaff Trend Cycle, Dip-Weighted DCA, Equity Curve Filter
  and Piercing Line.

Every one of them except Santa Claus Rally lost money in the other market's basket test, so most are expected to
fail. They get the same stricter bar as the other many-bot tests. Equity Curve Filter only trades once its own
paper record has 10 Trend Rider trades on a coin or stock, so it may sit idle for months.

## How it runs

- **Money:** $10,000 of paper money per coin or stock, per ETF for IBS, and one account for
  leveraged trend.
- **Trading:** each strategy decides at the daily close. Orders fill at the next day's open, paying
  the fee above plus 0.02% slippage.
- **Prices:**
  - **Crypto:** the saved Coinbase history plus Coinbase's latest finished days. Bots that compare a coin
    with bitcoin use bitcoin's prices from the same source.
  - **Stocks and ETFs:** Yahoo daily bars. A day's bar is used only after 4:15 pm New York time.
- **Updating:** every time the 📒 **Paper tests** panel opens, it replays every strategy from the
  start date on the latest prices. `weekly_check.py` opens it once a week (see Files).
- **The log:** the first time the panel sees a new day of prices, it adds a snapshot to
  `paper_ledger.jsonl`. That keeps a record of what happened as it happened.
- **Seeing the trades:**
  - Each test lists every buy and sell: the date, the bot, the coin or stock, the price, and the
    profit on each sale.
  - Clicking a name, or using **Show chart**, opens that coin or stock's chart with the bot's buy
    and sell arrows and a "paper start" marker.

## Yardsticks shown next to each strategy

- **Crypto:**
  - holding bitcoin
  - holding all 29 coins equally
  - the luck bar: the 90th percentile of 200 Coin Flip bots with different random calendars, on
    the same coins, fees and fills
- **The 22-bot crypto test:** holding bitcoin, holding all 29 coins equally, and a stricter luck bar. In
  each of 200 tries, 22 Coin Flip bots with different random calendars run on the same coins, fees and
  fills, and the best average is kept. The bar is the 90th percentile of those 200 bests.
- **The 21-bot micro-cap test:** holding IWC, holding all 60 stocks equally, and the same kind of stricter luck
  bar, with 21 Coin Flip bots in each try.
- **The both-markets test:** each half has its own. The crypto half has holding bitcoin, holding all 29 coins and
  a 3-bot luck bar. The micro-cap half has holding IWC, holding all 60 stocks and a 3-bot luck bar.
- **The 10-bot crypto and 9-bot micro-cap tests:** the same yardsticks as the 22-bot and 21-bot tests, with
  10-bot and 9-bot luck bars.
- **Micro-caps:** holding IWC, holding all 60 equally, and the luck bar.
- **IBS:** holding QQQ, and holding SPY.
- **Leveraged trend:** holding SPY, and holding SSO.

## The bar, set before any forward price existed

At each review, a strategy passes only if all of these hold over the whole time since the start:

1. **It beats luck and holding its own coins or stocks.**
   - For the baskets, its average beats both the luck bar and the "holding all" average.
   - For IBS, it beats holding that ETF.
2. **It beats the practical alternative:** holding bitcoin for crypto, IWC for micro-caps, QQQ or
   SPY for IBS on each, and SPY for leveraged trend.
3. **For the baskets, it made money on more than half of them.**

**The 22-bot crypto test has a stricter bar.** Testing 22 bots at once gives luck 22 chances, so a bot
passes only if all of these hold:

1. Its average beats the 22-bot luck bar and holding all 29 coins.
2. Its average beats holding bitcoin.
3. Its average still beats holding bitcoin with its single best coin left out.
4. It made money on more than half of the 29 coins.

**The 21-bot micro-cap test has the same stricter bar, with IWC in place of bitcoin.** A bot passes only if its
average beats the 21-bot luck bar and holding all 60 stocks, beats holding IWC, still beats holding IWC with its
single best stock left out, and it made money on more than half of the 60 stocks.

**The both-markets test:** a bot passes only if it clears that same stricter bar, with a 3-bot luck bar, in both
halves: against bitcoin and the 29 coins, and against IWC and the 60 stocks.

**The 10-bot crypto and 9-bot micro-cap tests** use the same stricter bar as the 22-bot and 21-bot tests, with
10-bot and 9-bot luck bars.

Passing at 6 months means "keep going". A strategy has to pass again at 1 year.

- **A pass** means it's worth a longer paper test and a proper write-up. It is not a signal to use
  real money, and Claude won't place trades either way.
- **A fail** means nothing this project has found beats the simple alternatives, even on fresh
  prices.

## Limits, stated at setup

- **A year is short.** One good or bad year for crypto or small stocks can decide the result. That's
  why the luck bars and holds sit next to every strategy.
- **Trading is simplified.** Fills at the open and flat fees are simplifications; small coins and
  stocks cost more to trade in size.
- **The lists are from September 2026.**
  - If Yahoo stops returning a stock's prices, for example after a delisting or buyout, the stock
    drops out of the averages and is listed under "No fresh prices". Check the ledger's earlier
    snapshots when that happens.
  - Coins keep their last saved price.

## Files

- `index.html` (the 📒 Paper tests panel) and `server.py`
- `more_bots.js`: the rules of 16 of the 22 crypto bots and 10 of the 21 micro-cap bots. Frozen from 2026-09-12, like the bot section of
  `index.html`; any new bots go in a new file.
- `extra_bots.js`: the rules of the both-markets bots and of the 10-bot and 9-bot tests. Frozen from 2026-09-12 too; any new bots go in
  another new file.
- `paper_ledger.jsonl`: daily snapshots, created on the first day with forward prices
- `weekly_check.py`: opens the panel in headless Chrome and writes `weekly/<date>.md`, a summary of the buys and sells
  since the last check and where each test stands. A scheduled task in the Claude app runs it every Monday at 9 am.
  The panel's latest full update, trades included, is saved in `paper_latest.json`.
- `PAPER_TESTS.sha256`: the fingerprints (refreshed by the amendments below)

## Amendments

- **2026-09-13, before the start date, display only.**
  - Added the full buy-and-sell list and the chart view.
  - No bot rule, list, fee or fill changed. The edits touched only the paper panel's display code.
  - The app's whole-file fingerprint was refreshed, and the bot-rules section has its own fingerprint
    from here on.
  - The app's fingerprint at setup was `5e54bbbd…c093fd0`.
- **2026-09-12 evening, before the start date: more bots, a weekly check, more markets. No tested rule changed.**
  - 52 new bots went into a separate file, `more_bots.js`. None of them are in the paper tests. The bot section of
    `index.html` is byte-for-byte unchanged: its fingerprint is still `58054e19…a1808`.
  - The paper tests now run only their own bots plus Buy & Hold, instead of every bot in the app, so a problem in any
    other bot can't reach them.
  - Checked with a practice start of 2026-06-01 on identical prices for all 94 symbols. The tested bots' 1,090 buys
    and sells, returns, luck bars and next-open orders came out identical in three runs: the old app, the new app, and
    the new app with all 93 bots running (SHA-256 of the results `2aac7b11…c35b` each time).
  - `weekly_check.py` and the scheduled weekly run were added. They only read results. A practice run from another
    start date is never written to the ledger.
  - Display only: more coins and stocks to pick from, a box to type any ticker, and more decimals for coins under a cent.
  - The whole-file fingerprints of `index.html` and `server.py` were refreshed, and `more_bots.js` and
    `weekly_check.py` were added to `PAPER_TESTS.sha256`.
- **2026-09-12, later that evening, before the start date: a fifth test.**
  - Added the 22-bot crypto test, when asked to add "all the green" bots and Keltner Breakout to the paper tests.
    The bots were chosen by one rule: a positive average with at least one trade on crypto group A (0.25% per
    trade, next-open fills) when all 93 bots ran there. Coin Flip, a yardstick, and the three bots already in the
    first crypto test were left out.
  - It uses the stricter bar above: a luck bar for 22 bots, and beating bitcoin with its best coin left out.
  - `more_bots.js` now holds tested rules, so it is frozen from here on. Its fingerprint, `6fb2c492…`, is unchanged
    since the previous amendment.
  - The first four tests are unchanged. Rechecked with the practice start of 2026-06-01 on identical prices, their
    results hash to `2aac7b11…c35b` again. Their luck bar's code was reorganized to share parts with the new bar;
    the only difference is that it no longer resets bots the calculation doesn't use.
  - The weekly check and its scheduled task now cover all five tests.
- **2026-09-12, the same evening, before the start date: a sixth test.**
  - Added the 21-bot micro-cap test, when asked to add "the green micro cap bots" to the paper tests. Same rule as the
    crypto one: a positive average with at least one trade on micro-cap basket A (0.50% per trade, next-open fills)
    when all 93 bots ran there, re-run before this change and matching the earlier run. Martingale was left out
    because it's already in the first micro-cap test. Opposite Day, a no-edge control, qualified and stays in.
  - It uses the same stricter bar as the 22-bot crypto test, with IWC in place of bitcoin.
  - Display only: the stricter-bar note on both many-bot cards now names the test's own index ("holding Bitcoin",
    "holding iShares Micro-Cap ETF") instead of always saying bitcoin.
  - The five earlier tests are unchanged. Their results on the practice start of 2026-06-01, with identical prices,
    hash to `7a54eb36…` before and after this change, and the first four still hash to `2aac7b11…c35b`.
  - `more_bots.js` and index.html's bot section are unchanged. Only index.html's whole-file fingerprint was refreshed.
  - The weekly check and its scheduled task now cover all six tests.
- **2026-09-12, later still, before the start date: 39 more bots, display only.**
  - Added `extra_bots.js` with 39 new bots, loaded after `more_bots.js`. None of them are in any paper test, and no
    tested rule, list, fee or fill changed. index.html's bot section (`58054e19…`) and `more_bots.js` (`6fb2c492…`)
    are unchanged.
  - The six tests' results on the practice start of 2026-06-01, with identical prices, hash to `cb39086f…` both
    before and after the change.
  - index.html's whole-file fingerprint was refreshed for the extra script tag, and `extra_bots.js` was added to
    `PAPER_TESTS.sha256`.
- **2026-09-12, last change before the start date: the both-markets test.**
  - Asked to "add the ones you think should be added" from the 39 newest bots. Claude picked Breakout on Volume,
    Hikkake and Bull Flag, the ones with a positive average in both 132-bot basket tests, and left out Santa Claus
    Rally for the reason given above.
  - It runs as two halves in the panel and the weekly report, one per market, with the stricter bar and a 3-bot luck
    bar in each. A bot passes only if it clears the bar in both halves.
  - `extra_bots.js` now holds tested rules, so it is frozen from here on. Its fingerprint, `1953fafb…`, is unchanged.
    So are index.html's bot section (`58054e19…`) and `more_bots.js` (`6fb2c492…`).
  - The six earlier tests are unchanged: on the practice start of 2026-06-01 with identical prices, their results
    still match `cb39086f…`. Only index.html's whole-file fingerprint was refreshed.
  - The weekly check and its scheduled task now cover all eight sections.
- **2026-09-12, still before the start date: the left-out newest bots, on request.**
  - After the both-markets test was set up, the bots Claude had left out were requested too. Two tests now hold
    every other bot from the 39 newest with a positive average in one basket test: 10 on crypto and 9 on
    micro-caps, with Santa Claus Rally in both.
  - Both use the stricter bar, with 10-bot and 9-bot luck bars.
  - No bot rules changed. index.html's bot section (`58054e19…`), `more_bots.js` (`6fb2c492…`) and
    `extra_bots.js` (`1953fafb…`) are unchanged.
  - The eight earlier sections are unchanged: on the practice start of 2026-06-01 with identical prices, their
    results match `76ec0a2c…` before and after. Only index.html's whole-file fingerprint was refreshed.
  - The weekly check and its scheduled task now cover all ten sections.
- **2026-09-13, before the start date: fast bots and the weekly speed test, outside these tests.**
  - Added `fast_bots.js` (33 bots for 5- and 15-minute candles) and the separate weekly speed test (`SPEED_TEST.md`,
    `speed_test.py`, `speed_test.js`, and a results endpoint in `server.py`). None of it is part of these paper tests.
  - No tested rule changed. index.html's bot section, `more_bots.js` and `extra_bots.js` are unchanged.
  - The ten sections are unchanged: on the practice start of 2026-06-01 with identical prices, their results match
    `5c995c88…` before and after. index.html's and server.py's whole-file fingerprints were refreshed.
- **2026-09-13, later that day: data bots, outside these tests.**
  - Added `data_bots.js`: 27 bots that read the speed test's group, outside signals (VIX, Crypto Fear & Greed,
    bitcoin's implied volatility and funding rate) or published intraday effects. Also added outside-data collection
    to `speed_test.py`. None of it is part of these paper tests.
  - The ten sections are unchanged: on the practice start of 2026-06-01 with identical prices, their results still
    match `5c995c88…`. index.html's whole-file fingerprint was refreshed, and `data_bots.js` was added to
    `PAPER_TESTS.sha256`.
- **2026-09-13, evening: bots built from the speed test's practice weeks, outside these tests.**
  - Added `lesson_bots.js`: 22 bots for the weekly speed test (bots that buy big drops and hold for hours, fee-aware
    bots, two outside-data bots, a published stock day-trading rule and three random-entry controls). Also added VIX9D
    and bitcoin taker volume to `speed_test.py`'s data. None of it is part of these paper tests.
  - The ten sections are unchanged: on the practice start of 2026-06-01 with identical prices, their results still
    match `5c995c88…`. index.html's bot section (`58054e19…`) and the four earlier bot files are unchanged. index.html's
    whole-file fingerprint was refreshed, and `lesson_bots.js` was added to `PAPER_TESTS.sha256`.
- **2026-09-13, late evening: Kronos bots, outside these tests.**
  - Added `kronos_bots.js` (3 bots that trade on forecasts from Kronos, an open-source AI model for price candles) and
    `kronos_forecasts.py`, which computes those forecasts for the weekly speed test. None of it is part of these paper
    tests.
  - The ten sections are unchanged: on the practice start of 2026-06-01 with identical prices, their results still
    match `5c995c88…`. index.html's whole-file fingerprint was refreshed, and `kronos_bots.js` was added to
    `PAPER_TESTS.sha256`.
- **2026-09-14, just after midnight UTC: team bots, outside these tests.**
  - Added `team_bots.js`: 15 speed-test bots (group rankings, pairs, Kronos combinations and teams of existing bots),
    counted from the week of 2026-09-21. None of them is part of these paper tests.
  - The ten sections are unchanged. With every symbol's prices cut off at the baseline's last day, their results match
    `5c995c88…` exactly.
    - The unpinned check differed only because 30 of the 94 symbols had gained the finished 2026-09-13 daily candle.
    - From now on, check against the baseline with prices pinned this way.
  - index.html's bot section (`58054e19…`) and the earlier bot files are unchanged. index.html's whole-file fingerprint
    was refreshed, and `team_bots.js` was added to `PAPER_TESTS.sha256`.
- **2026-09-14: Self-Tuner, outside these tests.**
  - Added `selftune_bots.js`: 1 speed-test bot that re-picks its own RSI settings from trailing no-lookahead
    performance instead of using one frozen setting, counted from the week of 2026-09-21. Not part of these paper
    tests, and it doesn't touch any market, basket, or fee these tests use.
  - No trades had happened in any of the ten sections yet (Day 1 of the real start), so there was nothing to
    re-verify against a baseline.
  - index.html's bot section (`58054e19…`) and every earlier bot file are unchanged. index.html's whole-file
    fingerprint was refreshed, and `selftune_bots.js` was added to `PAPER_TESTS.sha256`.
- **2026-09-15: more chart history, outside these tests.**
  - `server.py`'s `/api/ohlc` and `/api/yahoo` now load up to 2,000 candles instead of 720 (Yahoo
    only; Kraken's public endpoint has a real 720-candle ceiling that couldn't be paginated past -
    see the commit message). Doesn't touch any market, basket, fee, or bot rule these tests use;
    it's how many candles the chart displays when opened, nothing about what a bot decides.
  - No trades had happened in any of the ten sections yet (Day 2), so there was nothing to
    re-verify against a baseline. server.py's whole-file fingerprint was refreshed.
- **2026-09-15: Track Record, outside these tests.**
  - Added `track_record_bot.js`: 1 speed-test bot that learns via multiplicative-weights (an
    ensemble of six named signals whose trust weights rise or fall with their own track record),
    counted from the week of 2026-09-21. Not part of these paper tests.
  - No trades had happened in any of the ten sections yet (Day 2-3), so there was nothing to
    re-verify against a baseline.
  - index.html's bot section (`58054e19…`) and every earlier bot file are unchanged. index.html's
    whole-file fingerprint was refreshed, and `track_record_bot.js` was added to
    `PAPER_TESTS.sha256`.
- **2026-09-16: sidebar layout fix, outside these tests.**
  - Changed the `<style>` block only (a CSS grid width and one `@media` breakpoint) so the right
    sidebar stops collapsing below the chart on windows narrower than 900px. No JavaScript touched,
    so nothing about how a bot decides or a trade fills could have changed.
  - Positions had opened in several sections by now (buys since 2026-09-14, no sells yet), so this
    is the first amendment since real activity started. Not re-verified against a pinned baseline
    the way earlier bot-rule changes were, since a CSS-only diff has no code path that touches
    execution - there's nothing for it to have changed.
  - index.html's bot section (`58054e19…`) is unchanged (it's below line 940; this edit is above
    line 60). index.html's whole-file fingerprint was refreshed.
- **2026-09-22: NVIDIA Reasoner, outside these tests.**
  - Added `nvidia_bots.js`: 1 speed-test bot that asks a general-purpose AI model, hosted free by
    NVIDIA (build.nvidia.com's NIM API, not a model trained to forecast prices), to call buy, hold
    or sell once a day per coin, with its reasoning shown. `nvidia_forecasts.py` makes the calls
    (crypto only, once a day, not per candle) and needs `NVIDIA_API_KEY` set or it's skipped.
    Counted from the week of 2026-09-22. Not part of these paper tests.
  - Positions were already open in several sections by now, but this is a pure bot addition
    (`BOTS.push`, a new independent bot object) that doesn't touch any existing bot's `decide()`,
    `execute()`, or any shared function, so there's no code path through which it could change an
    existing bot's fills - not re-verified against a pinned baseline, the same reasoning as the
    2026-09-16 CSS-only change.
  - index.html's bot section (`58054e19…`) is unchanged (verified byte-for-byte: `sed -n
    '384,940p' index.html` still hashes to `58054e19…`; this edit only adds a `<script>` include
    after line 958). index.html's whole-file fingerprint was refreshed, and `nvidia_bots.js` was
    added to `PAPER_TESTS.sha256`.
- **2026-09-23: Late-Night Hours bot, outside these tests; plus a stale fingerprint fixed.**
  - Added `hour_bots.js`: 1 speed-test bot from published bitcoin research (Padyšák & Vojtko 2022, SSRN
    4081000): buy at 22:00 UTC, sell at midnight UTC, every day. Counted from the week of 2026-09-28. Not
    part of these paper tests.
  - A pure bot addition (`BOTS.push`), same reasoning as the 2026-09-22 entry: no existing bot's
    `decide()`, `execute()` or shared function is touched.
  - index.html's bot section (`58054e19…`) is unchanged (verified: `sed -n '384,940p' index.html` still
    hashes to `58054e19…`). index.html's whole-file fingerprint was refreshed, and `hour_bots.js` was added
    to `PAPER_TESTS.sha256`.
  - **Correction to the 2026-09-22 entry:** `nvidia_bots.js`'s fingerprint was taken before a last edit
    (reading its saved calls as `{time, action, reason}` objects instead of arrays), so the committed hash
    didn't match the committed file. Refreshed here. `nvidia_bots.js` is a speed-test-only bot, so this
    never affected any paper-tested bot.
