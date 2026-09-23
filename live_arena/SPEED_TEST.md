# Live Arena speed test

**Written:** 2026-09-13, before the first forward week.
**Asked for:** "keep running more bots until more works, do as many as you can, and don't paper trade for a year:
have the bots take more trades and paper trade only for a week."

The year-long paper tests in `PAPER_TESTS.md` keep running unchanged in the background. This is a separate,
faster test.

## How it works

- **Every bot, every week.** All Live Arena bots trade one Monday-to-Monday week (UTC) at a time, on 5-minute and
  15-minute candles, so they take many more trades than on daily candles. Any bot added later joins in its first
  full week.
- **Markets:**
  - **Crypto (12 coins):** BTC, ETH, SOL, XRP, DOGE, ADA, LINK, AVAX, LTC, DOT, BCH, SUI. 5-minute candles from
    Coinbase. A 5-minute stretch with no trades is filled with the last price.
  - **US stocks and ETFs (20):** SPY, QQQ, IWM, DIA, AAPL, MSFT, NVDA, TSLA, AMZN, META, GOOGL, AMD, NFLX, AVGO,
    PLTR, COIN, MSTR, JPM, GLD, TLT. 5-minute candles from Yahoo Finance, regular trading hours only.
  - 15-minute candles are built from the 5-minute ones.
- **Outside data** (collected by `speed_test.py` every week, free and without keys):
  - **Stocks:** the VIX and VIX9D (the same fear gauge for the next 9 days instead of 30), 5-minute readings from
    Yahoo Finance.
  - **Crypto:** the daily Crypto Fear & Greed Index (alternative.me), bitcoin's hourly implied volatility index
    DVOL (Deribit), bitcoin's 8-hour perpetual swap funding rate (OKX), and the hourly taker volume on bitcoin's
    perpetual swaps: how much trading came from aggressive buyers and how much from aggressive sellers (OKX keeps 30
    days of it, so the saved history starts on 2026-08-14).
  - **Kronos forecasts (both groups):** every hour, Kronos-small, an open-source AI model pre-trained on price candles
    from 45+ exchanges and released in 2025, forecasts each market's next 8 hourly candles from its last 160 (crypto)
    or 140 (stocks) hourly candles, built from the saved 5-minute candles. `kronos_forecasts.py` computes them on the
    CPU, averaging 4 forecast paths with a fixed random seed for each hour, so a rerun gives the same forecasts.
  - Bots only see readings that were already public: yesterday's Fear & Greed value, the last finished DVOL hour and
    taker volume hour, the last settled funding rate, the VIX and VIX9D candles that closed together with theirs, and
    a Kronos forecast made from hours that had already closed, less than an hour old.
- **Breadth data:** bots can also see the other markets in their group at the same candle times.
- **Trading:**
  - $10,000 of paper money per bot per market.
  - Orders fill at the next candle's open, plus 0.02% slippage.
  - Fees per trade: 0.25% on crypto, 0.02% on stocks.
  - The 7 days before the week only warm up the indicators.
- **Weekly run:** `python3 live_arena/speed_test.py` collects the candles, computes Kronos's forecasts, runs every bot in headless Chrome, and
  writes `speed/<week>.md`. The scheduled Monday task runs it for the week that just ended.
  `python3 live_arena/speed_test.py --history` reruns every complete week since 2026-07-20 and writes
  `speed/history.md`, which checks whether the bots that pass look like more than luck.

## Passing a week

A bot passes a week in a market (crypto or stocks) at a candle size (5 or 15 minutes) only if all five hold:

1. **It really traded:** at least 10 closed trades (a buy and its sale) across the markets. Buying once and holding
   doesn't count.
2. **It made money:** its average return across the markets, after fees, is above zero.
3. **It beat just holding:** its average is above just holding the same markets for the week. A tie doesn't count.
4. **It was broad:** it made money in more than half the markets.
5. **Its timing beat luck:** before fees, its result beats at least 95% of 99 copies of the same trades slid to
   other times in the week. Sliding keeps how often it was in the market and how much it traded, and changes only
   when. A bot with no timing skill beats about half the copies.

## Working so far

- Weeks that start before **2026-09-14** are practice. They show how the test works, but don't count.
- A bot **works so far** once it passes **3 forward weeks in a row** in the same market and candle size. The first
  possible date is the report on Monday 2026-10-05.
- Even then, "works so far" means worth watching longer, not proof, and not a signal to use real money.

## Stopping point

Set on 2026-09-13, at the user's request, before any forward week had a result.

- The speed test counts 8 forward weeks: the weeks of 2026-09-14 through 2026-11-02. The report on **Monday
  2026-11-09** is the last one that counts.
- If no bot works so far in that report (3 or more forward weeks in a row, still going), the answer is no: none of
  these bots showed a short-term edge. Stop adding bots and stop spending time on the speed test. A bot that reached
  3 weeks earlier but then failed a week doesn't count. The year-long paper tests keep running on their own schedule.
- If a bot does work so far in that report, it keeps paper trading with its rules unchanged, to see whether it holds up
  for months. That still isn't a reason to use real money.
- The deadline doesn't move, and no rule, bot or fee changes to rescue a result. A bot added later counts only from
  the week it joined, so a bot joining after the week of 2026-10-19 can't reach 3 weeks by the stopping point.

## Limits, stated before the first week

- **A week is short.** One market move can decide it, which is why a single week never counts on its own.
- **Many contestants.** 232 bots × 2 markets × 2 candle sizes is 928 tries a week. Even a fair test lets a few
  through by luck each week; three weeks in a row filters most of them out.
- **Fees decide short-term trading.** On 5-minute crypto candles, the average move is smaller than two fees of
  0.25%, so most fast crypto bots are expected to lose. Stock fees are near zero for big, liquid stocks, which gives
  those bots a fairer shot.
- **Trading is simplified.** Fills at the next open, fixed fees and filled gaps are simplifications, and real orders
  move the price in small coins.
- **Controls stay in.** Coin Flip, Buy & Hold, Steady Buyer, Random Entry and Opposite Day run every week, and since
  2026-09-13 so do three more random-entry controls: Random Entry with an 8-hour and with a 1-hour hold, and
  Independent Coin Flip. If they pass, the bar is too easy.

## Changes before the first forward week

- **2026-09-13, after the practice week of 2026-08-24.** Buy & Hold, a control, and Hold With a Stop "passed" on
  stocks without really trading:
  - With 20 stocks, one buy each met the first draft's minimum of 20 buys and sells.
  - Matching just holding counted as beating it.
  - Their timing score came down to the single first candle they sat out.

  The minimum became 10 closed trades, and a tie with just holding no longer counts. Both practice weeks were run again
  under the new rules. No forward week had started.
- **2026-09-13, later: more bots and more data.** No pass rule changed.
  - Added 27 bots in `data_bots.js`:
    - breadth bots that read the rest of their group;
    - outside-data bots that read VIX, Fear & Greed, DVOL or funding;
    - bots built on published intraday effects (Gao, Han, Li and Zhou 2018; Shen, Urquhart and Wang 2022; Heston,
      Korajczyk and Sadka 2010; a bitcoin hour-of-day study; and a study of reversals after extreme moves in liquid
      stocks).
  - Added the outside data above, 8 weeks of 5-minute crypto history, and the `--history` option.
  - The new bots join from the first forward week, like every other bot.
- **2026-09-13, evening: bots built from the practice weeks, and more controls.** No pass rule changed.
  - What the practice weeks showed:
    - On crypto, the dip-buying bots scored best on the timing check, but most traded hundreds of times a week at
      0.25% a trade and lost it all to fees.
    - In 8 weeks of 5- and 15-minute crypto candles, small drops were followed by tiny bounces. After a drop of 3% or
      more over a few hours, and especially after drops that hit the whole group at once, prices rose about 0.4% to
      0.8% on average over the next 4 to 8 hours, in both halves of the 8 weeks. A buy and a sale cost 0.54%.
    - On stocks, no simple intraday effect held up in both halves.
    - Open interest, the long/short account ratio, the Coinbase premium and the perpetual swap's premium over spot
      showed nothing either, so no bot uses them.
  - Added 22 bots in `lesson_bots.js`:
    - bounce bots that wait for big drops and hold for hours, with variants on drop size, holding time, exits,
      volume, trend, group-wide drops and bitcoin's drop;
    - fee-aware versions of bots that timed well (Wide Grid, and NY Selloff held to 4 pm), and a Cost-Aware Learner
      that only buys when its forecast beats the fees (the filter from a 2026 study of machine-learning bitcoin
      trading);
    - Taker Buy Pressure (a 2026 study by Kim and Hansen found order imbalance predicts crypto returns over 4 to 12
      hours) and Calm VIX Curve (VIX9D against VIX);
    - Noise Area Breakout, the SPY day-trading rule of Zarattini, Aziz and Barbon (2024), buying side only;
    - three random-entry controls: 8-hour and 1-hour holds to match the new bots, and an Independent Coin Flip with
      a different random calendar in every market.
  - Their thresholds were picked after seeing the practice weeks, so their practice results were fitted to those weeks
    and prove nothing. Like every bot, they're judged only on forward weeks.
  - Added VIX9D and bitcoin taker volume to the outside data. The weekly and history reports now name every control,
    and the history report's luck check counts all six random controls.
- **2026-09-13, late evening: Kronos, an AI forecasting model.** No pass rule changed.
  - With the user's permission, installed Kronos-small (github.com/shiyu-coder/Kronos, MIT license) in its own Python
    environment in `live_arena/kronos/`, and added `kronos_forecasts.py`, which `speed_test.py` runs every week before
    the bots.
  - Added 3 bots in `kronos_bots.js`:
    - Kronos 8-Hour Forecast: buys when the 8-hour forecast beats what a buy and a sale cost.
    - Kronos Strong Forecast: needs twice that, with the 4-hour forecast up too.
    - Kronos Next Hour: the 1-hour forecast beats the cost; holds 1 hour.
    Each holds longer only while its newest forecast still clears its bar.
  - Kronos's settings and the bots' rules were fixed before the first forward week began and weren't tuned on any
    week's prices.
  - `speed_test.py` also gained a `joined` list: a bot added after a forward week has begun only counts from the next
    week.
- **2026-09-13, as the first forward week began: team bots, counted from 2026-09-21.** No pass rule changed.
  - What the practice weeks showed first:
    - The crypto group's biggest 24-hour loser, when down 4% or more, rose about 0.9% to 1.0% over the next day in
      both halves.
    - Stocks that fell 1.5 points more than their group over 3 hours did a little better than the group over the next
      day, in both halves.
    - The day's biggest winner did worse than the group afterward, so no bot chases it.
    - Buying the stock or ETF that fell 2.5 standard deviations behind its usual partner (such as COIN and MSTR)
      averaged about +0.2% a trade in both halves. The same idea on crypto pairs didn't beat the fees.
  - Added 15 bots in `team_bots.js`:
    - the group's biggest 24-hour loser, and its bottom three;
    - a market left behind by its group over 3 hours, and a stock or ETF left behind by its usual partner;
    - Kronos combinations: with a dip; with agreement at every horizon; the group's top pick and top three by Kronos's
      8-hour forecast; and a control, Kronos Bottom Pick, that buys the market Kronos likes least;
    - three teams that buy when several existing bots hold a market: the 3 Kronos bots, the 11 bounce bots, and the
      9 best-timed bots of the practice weeks;
    - a dip buyer that waits for the selling to calm down, and a second-dip retest;
    - a random-entry control with a 24-hour hold.
  - They were finished as the first forward week began, so they count from the week of 2026-09-21 (`joined` in
    `speed_test.py`). Their week of 2026-09-14 is still reported, marked "joined later".
  - Checked in the practice weeks but not made into bots, because they didn't hold up in both halves or were too rare:
    - flight to safety (stocks falling while bonds rise);
    - bitcoin jumping while COIN and MSTR lag (they already move with it within the hour);
    - crypto drops by time of day, or on weekends (weekend drops didn't bounce in the second half);
    - holding stocks left behind at 3 pm until the next morning (the result flipped between halves).

## Changes after the first forward week began

No pass rule, fee, bar or stopping point changed in any of these. Every addition counts only from a later week.

- **2026-09-14/15: Self-Tuner and Track Record**, counted from the week of 2026-09-21 (`selftune_bots.js`,
  `track_record_bot.js`).
- **2026-09-22: NVIDIA Reasoner** (`nvidia_bots.js`, `nvidia_forecasts.py`): a free NVIDIA-hosted AI model calls buy,
  hold or sell once a day per crypto coin. Counted from the week of 2026-09-28. `speed_test.js` also started saving
  each bot's result per coin (for `best_recent.py`); no grading changed.
- **2026-09-23: Late-Night Hours** (`hour_bots.js`): buy at 22:00 UTC, sell at midnight (Padyšák & Vojtko 2022).
  Counted from the week of 2026-09-28.
- **2026-09-23: a third market, meme coins, counted from the week of 2026-09-28.** On request. Every bot runs on 11
  Coinbase meme coins on 5- and 15-minute candles, graded by the same five rules, at the crypto fee (0.25%).
  - **Picked by a fixed rule, not by performance:** on Web Picks' meme list, a Coinbase USD market that's online, and
    an average of at least $250,000 traded a day over the 7 days before 2026-09-23 (Web Picks' own bar). DOGE is
    already in the crypto group. That gave SHIB, PEPE, BONK, WIF, FLOKI, TRUMP, PENGU, POPCAT, FARTCOIN, MOODENG and
    SPX. MOG, TURBO and PNUT traded too little. The list never changes during the test.
  - A streak has to be in the same market, so a meme pass never adds to a crypto streak.
  - Meme weeks through 2026-11-02 give at most 6 weeks, enough for a streak of 3 before the stopping point.
  - No Kronos for this group (it's slow and built for the other two). Bots that need bitcoin's prices in the same
    group, or Kronos, just wait here.
  - **Limits:** real costs on these coins are usually well above 0.25% (the gap between buy and sell prices), so
    passes here flatter the bots. These are the bigger, Coinbase-listed memes, not the tiny ones on pump.fun. The
    project's earlier meme-coin bots (the Solana bots removed on 2026-09-10) all lost money.
- **2026-09-23: Hype Leader** (`hype_bots.js`), on request: picks which coin in its group to buy by volume surge
  (24 hours of dollar volume against its own normal day over the 6 days before). Buys only the group's biggest surge,
  2x or more, with the price up, and sells 6 hours later. Counted from the week of 2026-09-28. First built at 3x and
  24 hours; a dry run on the week of 2026-09-14 showed only 3 closed trades on memes, short of the 10 a pass needs, so
  on request it was changed to 2x and 6 hours (16 trades), choosing by trade count only, without looking at returns.
  Locked from here: no more changes.
