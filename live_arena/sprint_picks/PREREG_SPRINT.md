# Pre-Registration: Sprint Picks (one round, 10 meme coins + 10 stocks, checked at 1 and 2 weeks)

**Frozen:** 2026-09-23, before any pick exists.
**Integrity:** `PREREG.sha256` holds this file's SHA-256; `sprint.py` refuses to run if it doesn't match. **Paper only.**
Nothing here places, or can place, a real order, and none of it is a recommendation to buy anything.

## The question

On request: Claude picks **10 low-cap meme coins and 10 US stocks** it thinks will go up, and they're checked after
**1 week** and **2 weeks**. Did the picks beat random picks from the same lists, and beat just holding bitcoin / SPY?

## Said up front: what this can and can't show

- **One round of 20 picks over 1-2 weeks is mostly luck.** Small meme coins often move ±50% in a week. Even a clear
  "pass" here is one lucky or unlucky fortnight, not evidence of skill. Every other test in this project needs months.
- **This test is not a signal to use real money,** whatever the result. The user said he may put $10 of real money in if
  it goes up a lot. That is his decision alone; Claude doesn't place trades or advise on them.

## Rules

| | Meme coins | Stocks |
|---|---|---|
| **Eligible** | The same list as Long Picks' Moonshots on 2026-09-23: CoinGecko `meme-token`, market cap $1M-$100M, $100k+ traded in 24 hours | The same as Long Picks' Holds: US common stock, $300M+ market cap, price $5+, 250,000+ shares traded |
| **Picks** | exactly 10, each with a reason and a source | exactly 10, each with a reason and a source |
| **Cost** | 2% each way | 0.02% each way |
| **Prices** | CoinGecko daily prices (00:00 UTC) | Yahoo daily opens |
| **Yardstick** | Bitcoin (Coinbase daily opens) | SPY |
| **Random control** | 60 eligible coins drawn at random (seeded by the date), never shown to the picker | 60 stocks, the same way |

- **Entry:** the first daily price after the lock (coins), the first daily open after the lock day (stocks).
- **Checkpoints:** the first daily price 7 days after entry, and 14 days after entry. Each checkpoint is scored as if every
  pick were sold then, paying the cost again.
- **Missing coins:** a coin CoinGecko no longer has counts as −100%; one with no price at the checkpoint uses its last
  price. The same rules apply to the random coins.

## What "went up a lot" means here (decided now)

For each bucket and checkpoint, the picks' **average return after costs** has to beat **both**:
1. the yardstick (bitcoin or SPY) over the same days, and
2. the **95th percentile of 1,000 random 10-pick averages** from the control sample.

Anything less is reported as "no better than luck." Even meeting it is one round and proves nothing.

## Amendments

None.
