# Pre-Registration: Long Picks (research-driven buy-and-hold picks, paper only)

**Frozen:** 2026-09-23, before the first round of picks exists.
**Integrity:** `PREREG.sha256` holds this file's SHA-256. `picks.py` and `score.py` refuse to run if it doesn't match. A
change means a new test with a new start date. **Paper only.** Nothing here places, or can place, a real order. None of
it is a recommendation to buy anything.

---

## The question

On request, two forward tests of "pick what I think will go up, then hold it":

1. **Moonshots:** can Claude, reading the web, pick **low-market-cap meme coins** that beat luck and beat holding bitcoin
   over a month, after realistic costs?
2. **Holds:** can Claude pick **US stocks** that beat luck and beat holding SPY over three months?

Like Web Picks (`../web_picks/PREREG_WEBPICKS.md`), a backtest is impossible because Claude already knows how the past
turned out. **The only fair test is forward:** picks are written down and fingerprinted before the prices move.

## Prior

**Very low for Moonshots, low for Holds.**
- Most tiny meme coins fall toward zero, many through rug pulls. The famous 100x coins are rare survivors. Any public
  reason to buy one (hype, influencers, big wallets) is visible to faster traders first. The project's earlier meme
  bots, including a real-money run, lost money.
- About 90% of professional US large-cap funds trailed the S&P 500 over 15 years (S&P SPIVA, year-end 2025). This
  project's stock-picking rules found nothing either (Phase 1, PICK).

## The two buckets

| | Moonshots | Holds |
|---|---|---|
| **Eligible** | In CoinGecko's `meme-token` category, market cap **$1M to $100M**, at least **$100,000** traded in the last 24 hours, on the day of the round (CoinGecko `/coins/markets`). | US common stock on Nasdaq's screener: market cap **$300M or more**, price **$5 or more**, **250,000+** shares traded that day. Letters-only symbol; warrants, units, preferred and depositary shares left out. |
| **Picks per round** | 0 to 3 | 0 to 3 |
| **Hold** | **30 days** | **90 days** |
| **Cost per trade** | **2.0%** each way (DEX fees plus the gap between buy and sell prices on thin coins; the real gap is often worse) | **0.02%** each way |
| **Prices** | CoinGecko daily prices (stamped 00:00 UTC) | Yahoo daily candles (opens) |
| **Yardstick** | Bitcoin (Coinbase daily opens) | SPY |
| **Random control** | 30 coins drawn at random from that round's eligible list, seeded by the date, stored but never shown to the picker | 60 stocks drawn the same way |

## A round

1. **Snapshot** (`picks.py snapshot`): saves both eligible lists and draws the hidden control samples.
2. **Research:** the picker searches the web and chooses 0 to 3 picks per bucket, each with a reason (20+ characters)
   and at least one source URL. Long only, no leverage.
3. **Lock** (`picks.py lock`): checks every pick against that day's eligible list, saves `rounds/<date>.json`, and
   records its SHA-256 with a timestamp in `ledger.jsonl`. `score.py` refuses to score a round whose file changed.
4. **Fills:**
   - **Holds:** enter at the open of the first daily candle dated after the lock day; exit at the open of the first
     candle dated 90 or more days after entry.
   - **Moonshots:** enter at the first CoinGecko daily price stamped after the lock time; exit at the first one 30 or
     more days after entry.
5. **Return per pick:** exit ÷ entry − 1, minus two times the cost.
6. **Dead or missing coins:** if a coin has an entry price but none at the exit date, its last available price is used
   and it's flagged. If CoinGecko no longer has the coin at all when scoring, it counts as **−100%** (a rug pull or a
   delisting). The same rules apply to every random-control coin, so neither side gets a break.
7. **Scored rounds are frozen** in `scored/<round>.json`, so a coin that later disappears can't change an old result.

Rounds run once a week on Sundays. Round 1 is locked on 2026-09-23, the day this was set up.

## Stopping point

**12 scored rounds per bucket.** Moonshots: about mid-January 2027. Holds: about mid-March 2027. No conclusions from
fewer. A bucket needs **at least 20 picks** to be judged. Never move the stopping point or the gates to rescue a result.

## The gates (a bucket needs all five)

1. **Made money:** average return per pick after costs is above zero.
2. **Beat holding:** above the yardstick's average over the same holding periods.
3. **Beat luck:** above the 95th percentile of 1,000 random-pick averages drawn from the control samples.
4. **Not one lucky pick:** still above zero with the single best pick removed. One 50x coin must not decide it.
5. **Not one lucky round:** above zero in more than half the rounds it picked in.

A pass is a lead, not proof: it would need a fresh 12-round repeat, and even then **it is not a reason to use real
money.**

## What could still be wrong, said up front

- **Overlapping holds.** Rounds are a week apart but holds last 30 or 90 days, so neighboring rounds share most of their
  days. Twelve rounds of Holds are nowhere near twelve independent chances; one strong or weak quarter dominates.
- **Costs on tiny coins** vary a lot; 2% each way may be too kind for the smallest ones.
- **CoinGecko's category and market caps** are its own; some "meme" labels are debatable. The same list is used for the
  picks and the control, so it's fair in both directions.
- **Low power.** At most 36 picks per bucket. A real small edge would likely be missed; a lucky streak is guarded
  against by gates 3 to 5, not ruled out.

## Amendments

None.
