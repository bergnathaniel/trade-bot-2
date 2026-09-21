# Pre-Registration: Web Picks (research-driven picks, paper only)

**Frozen:** 2026-09-21, before the first round of picks exists.
**Integrity:** `PREREG.sha256` holds this file's SHA-256. `score.py` refuses to score if it doesn't match. A change
means a new test with a new start date. The old one is never continued under new rules.
**Paper only.** Nothing here places, or can place, a real order. Every pick is a line in a file.

---

## The question

Can Claude, reading the web the way a person would (news, filings, forums, analyst notes), pick stocks, micro-caps and
crypto or meme coins that beat luck and beat just holding, after trading costs?

The other bots in Live Arena are fixed rules on price candles. They can be replayed on old prices. A web-reading
picker can't: Claude already knows how the past turned out, so any backtest would be contaminated. **The only fair test
is forward.** Picks are written down and locked *before* the prices move, then scored a week later.

## Prior

Low. News is public the moment it's published and prices react fast. Micro-caps and meme coins are where promotional
posts and pump-and-dump schemes live, so a picker that reads the web there can end up buying other people's exits.
Every earlier test in this project has found nothing that beats holding the index. This test exists to check, not
because anything suggests it works.

## The three buckets

| Bucket | Who is eligible (as of the day of the round) | Fee per trade | Yardstick |
|---|---|---:|---|
| `stocks` | US-listed common stock, market cap of $2B or more, price of $5 or more, at least 500,000 shares traded that day. Letters-only symbol. Nasdaq's US screener is the source. | 0.02% | SPY |
| `micro` | Same, but market cap $50M to under $300M, price of $1 or more, at least 50,000 shares. The same rule as `make_basket.py`. | 0.50% | IWC |
| `crypto` | A USD market on Coinbase that is online and open for trading, not a stablecoin, and averaging at least $250,000 of trading a day over the last 7 finished days. Meme coins are included and are tagged from a fixed list (below). | 0.25% | BTC-USD |

Anything outside these rules is rejected at lock time. Companies between $300M and $2B are in no bucket.

Meme tag (descriptive only, never used in a gate): DOGE, SHIB, PEPE, BONK, WIF, FLOKI, TRUMP, PENGU, POPCAT, MOG, BRETT,
TURBO, FARTCOIN, PNUT, MEW, MOODENG, GOAT, SPX, MEME, NEIRO, BOME, DOGS, HMSTR.

## A round

1. **Snapshot** (`picks.py snapshot`): pulls the eligible lists and draws a random control sample of 60 eligible
   symbols per bucket, seeded from the date. The sample is stored but never shown to the picker.
2. **Research:** the picker searches the web and chooses **0 to 3 long picks per bucket**. Passing on a bucket is
   allowed. Each pick needs a symbol, a reason of at least 20 characters, and at least one source URL. Long only. No
   shorts, no leverage, no options.
3. **Lock** (`picks.py lock`): validates every pick against the eligibility rules, saves `rounds/<date>.json`, and
   records the file's SHA-256 with a timestamp in `ledger.jsonl`. Picks can't be edited afterwards. `score.py`
   re-checks each hash.
4. **Fills:** entry is the **open of the first daily candle dated after the lock day** (UTC date for crypto, New York
   date for stocks). Exit is the **open of the first daily candle dated 7 or more days after the entry candle**. One
   hold, no early sales, no stops, no adding.
5. **Return per pick:** exit open ÷ entry open − 1, minus **two times the fee** (buy and sell).
   The fees are the ones the rest of Live Arena uses. Real costs on micro-caps and small coins are usually higher
   (the gap between buy and sell prices), so the micro and crypto numbers flatter the picker.
6. **Missing data:** if a stock has an entry candle but no exit candle once the yardstick has one, its last available
   open is used and the pick is flagged. If it has no entry candle, it is dropped and flagged.

## The yardsticks

- **The yardstick fund** (SPY, IWC, BTC-USD): its return over the same entry-to-exit days of each round, with no fees.
- **Random picks:** for every round and bucket with *k* picks, *k* symbols drawn at random from that round's control
  sample, paying the same fees over the same days. Done 1,000 times with a fixed seed. Compared as the average return
  per pick across all rounds.

## Stopping point

**12 scored rounds.** The first round is 2026-09-21. The verdict is read when the twelfth round is scored (about 2026-12-21
if a round runs every week). No conclusions from fewer. A bucket needs at least **20 picks** in total to be judged. If it
has fewer, the answer for that bucket is "not enough picks."
Never move the stopping point or the gates to rescue a result.

## The gates (a bucket needs all five to pass)

1. **Made money:** average return per pick after fees is above zero.
2. **Beat holding:** that average is above the yardstick fund's average over the same weeks.
3. **Beat luck:** that average is above the 95th percentile of the 1,000 random-pick averages.
4. **Not one lucky pick:** the average is still above zero with the single best pick removed.
5. **Not one lucky week:** the bucket's average was above zero in more than half of the rounds it picked in.

A pass in one bucket out of three is a lead, not proof: three buckets means three chances at luck. A passing
bucket would need a second, fresh 12-round test with the rules unchanged before it counts for anything, and even
then it is not a reason to use real money.

## What could still be wrong, said up front

- **Claude's own knowledge.** Claude may recall facts from before its training cutoff, but a pick is only useful if it
  reflects the coming week, which Claude can't know. The forward design covers this.
- **A weekly sample is tiny.** 12 rounds × 3 picks = 36 picks per bucket at most. The gates guard against a lucky
  streak, but the test has low power: a real small edge would likely be missed.
- **Survivorship in the control sample** is limited to symbols eligible on the day of the round, which is how the picker's
  own choices are limited, so it's fair in both directions.
- **The lock timestamp** comes from this Mac's clock. The git history is the outside witness, so commit the rounds.
- **Dollar returns on the sales** in other reports aren't used here. Only percent returns per pick count.

## Amendments

None.
