# Pre-Registration: picking the micro-cap stocks a strategy did well on (config family PICK)

**Frozen:** 2026-09-21, before any fresh basket was pulled and before any bot ran on one.
**Integrity:** the run script prints this file's SHA-256 with every result. Never edit this text
after results exist. Changes go in a dated *Amendments* section.

---

## Why this test

The user's idea: instead of trading IBS Swing or Fisher Transform on every micro-cap, trade them
only on the stocks where they did well.

Done by looking at a whole past period and keeping the winners, this can't be tested fairly. The
stocks were chosen *because* of the result, so the result can't be evidence. That is what happened
in `CONFIRM.md`: IBS Swing was basket A's headline (+167% average) and then had the worst median of
all 34 bots on 30 stocks it had never seen (−46.4%).

There is a version that can be tested honestly, and it is the same idea run in the order a real
trader would have to run it:

1. Look only at how the strategy did on each stock **in the past**.
2. Pick the stocks it did best on.
3. Trade **only those**, going forward, on prices that hadn't happened yet.
4. Repeat every quarter.

This asks the one question the idea depends on: *does a stock where the strategy worked keep being a
stock where it works?* If yes, picking winners has value. If not, the picks were luck.

**Prior: low.** Between basket A and basket B the rankings flipped completely (`CONFIRM.md`), which
is what "no persistence" looks like. This test exists to give the idea a fair hearing, not because
anything says it will pass.

---

## A. Strategies

Two, unchanged from the app, so nothing is re-written or re-tuned:
- **IBS Swing** (`id: "ibs"`, in `index.html`'s frozen bot section)
- **Fisher Transform** (`id: "fisher"`, in `extra_bots.js`, frozen)

Daily candles. Every buy and sell fills at the next candle's open. **0.50% per trade**, the same
fee `CONFIRM.md` used for micro-caps. The first 60 candles of each stock are warm-up.

## B. The stocks

Micro-caps chosen by the existing fixed rule in `make_basket.py` ($50M-$300M, US, price ≥ $1, ≥ 50,000
shares traded, plain common stock, a fixed-seed shuffle), on **stocks no bot or test in this project
has touched**:
- **Basket C**: `python3 make_basket.py --seed 20260921 --exclude basket.json --exclude basket_b.json --out basket_c.json`
- **Basket D**: `python3 make_basket.py --seed 20260922 --exclude basket.json --exclude basket_b.json --exclude basket_c.json --out basket_d.json`

C and D together are the **60-stock universe**. Baskets A and B (the 60 stocks the year-long paper
tests use) are excluded, so the two never overlap. The baskets are pulled and fingerprinted
(sha256, added to a new section of `PAPER_TESTS.sha256`-style notes) **before** any bot runs on them.

Each stock needs 721 daily candles (about 3 years), as in `make_basket.py`.

## C. The picking rule (walk-forward)

Every **63 trading days** (about a quarter), on a rank date `t`:
1. For each of the 60 stocks, run the strategy on that stock over the **252 trading days ending at
   `t`** and record its total return. Nothing after `t` is used.
2. Rank the 60 stocks by that trailing return.
3. **Pick the top 10.**
4. Trade only those 10 with the strategy over the next 63 trading days, $10,000 per stock, positions
   closed at the end of the window. Fills start at the next open after `t`.

The first rank date is after 60 warm-up candles plus 252 trading days. About six trading quarters
are left in ~3 years of data. Those six quarters, stitched together, are the **test window**.

## D. Controls

All use the same 63-day schedule, the same 10 picks per quarter, the same fee and fills:

| control | what it shows |
|---|---|
| **Random picks** | 10 stocks chosen at random each quarter, 2,000 draws (seed 20260921). Picking by past performance has to beat this, or it's no better than luck. |
| **Trade all 60** | the strategy on every stock, no picking. Picking has to beat not picking. |
| **Hold IWC** | the micro-cap index fund over the same six quarters. Is it worth doing instead of buying the fund? |
| **Hold the 60, equal weight** | what the universe itself did. |

## E. Gates (test window only, decided now)

A strategy **passes** only if all six hold:
1. **G1:** at least 100 closed trades across the six quarters.
2. **G2:** total return after fees > 0.
3. **G3:** beats the **97.5th percentile** of the random-picks control (97.5, not 95, because two
   strategies are tested).
4. **G4:** beats trading all 60.
5. **G5:** positive in more than half of the trading quarters (at least 4 of 6).
6. **G6:** beats holding IWC. Failing only this is reported as "real, but not worth it," the same
   split `CONFIRM.md` used.

## F. Always reported

- **Persistence.** For every rank date, the rank correlation between each stock's trailing return
  and its next-quarter return under the same strategy. If picking winners works, this is clearly
  above 0. If it's near 0 or negative, that alone explains a failure.
- The picks each quarter, their forward returns, and how much of the total came from the single best
  stock (the "one lucky stock" check).

## G. Integrity (must pass before any result counts)

- **Reproduces the app:** re-running the strategy on basket A must give the same per-stock returns
  as the app's own basket test. If it doesn't, there is no verdict.
- **No look-ahead:** deleting all data after a rank date must never change that date's picks
  (`leakage.truncation_test`).
- **Pure noise:** 10 synthetic random-walk universes of 60 stocks each; the full procedure must not
  pass more than 1 of the 10.
- **Planted persistence:** in synthetic stocks where the strategy truly works on a fixed subset, the
  procedure must find it. This shows the test can see a real effect, not only fail to see a fake one.

## H. Limitations, stated in advance

- **Survivorship.** These are today's micro-caps: companies that shrank into this size are in;
  ones that went bust are out (`make_basket.py`'s own caveat). Both the strategies and the random
  and trade-all controls share this tilt, but comparing to IWC (which does include failures) is
  flattered by it.
- **Six quarters of test data.** Three years of candles cannot give more once 252 days are used to
  rank. A pass would mean "worth a longer test," not proof.
- **One selection rule.** Top 10 of 60 by trailing 252-day return. Trying other windows or sizes
  until one works is exactly the re-rolling this test exists to avoid, so it won't be done.
- **Micro-cap crypto is not included.** The project's notes say the fresh-coin pool has been used
  up (`CRYPTO_SEARCH.md`), so there are no unseen coins to test on.
- **Real costs on stocks this small are often above 0.50% per trade.**

**Registry rows** (added with the results): PICK-IBS, PICK-FISHER.

---

## Amendments

(none)
