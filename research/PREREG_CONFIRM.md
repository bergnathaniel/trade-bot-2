# Pre-Registration: the confirmation year (for any strategy-search winner)

**Frozen:** 2026-09-11, while the first search (`PREREG_SEARCH.md`) was running and before any of its
results were read. **Integrity:** the confirmation run prints this file's SHA-256. Changes go in a
dated *Amendments* section.

---

## Why

The user's instruction: *"dont stop until you find something that works."* Searching until
something "works" is how people fool themselves. Try enough versions and one will pass any single
test by luck.

So the second half of the search year is not the last word. Before anything is called a strategy
that works, it has to survive a whole year that no test in this project has touched.

---

## Data

- **Symbols:** Coinbase 1-minute bars for BTC-USD, ETH-USD, SOL-USD, XRP-USD and DOGE-USD.
- **Window:** 2024-09-11 00:00 → 2025-09-11 00:00 UTC. The first 14 days are warm-up.
- **Conventions:** identical to `PREREG_SNIPER.md` A–B (forward-filling, stale-data rule, 5-minute
  decisions).
- **Catalyst blackouts:**
  - CPI and jobs dates come from the same BLS archive pages.
  - FOMC dates come from `sources.fomc_statement_dates()`.
- **Dropped symbols:** a coin with fewer than 300 evaluation days is dropped and reported. The rule
  is fixed before any result.

---

## Rule

Every configuration that **WINS** in a search round is run on the confirmation year with
identical code and settings. Nothing is re-fitted. With K winners (counted across all rounds that
reach this step), each must pass, at its own fee track:

- **C1:** ≥ 100 trades. Mean R after fees > 0. The lower end of the one-sided day-bootstrap bound
  at 1 − 0.05 / K is > 0 (B = 2000, seed 20260911). Profit factor > 1.10.
- **C2:** mean R with no fees is above the (1 − 0.05 / K) percentile of random entry times through
  the identical exits. There are 20 random entries per trade, B = 2000, drawn from the
  confirmation year.
- **C3:** mean R after fees > 0 on at least 3 of the 5 coins.

**CONFIRMED** = C1–C3. Only a CONFIRMED strategy earns a forward paper-trading log. It never earns
live trading from this program.

**If a search round has no winner,** this year stays untouched. It is reserved as test data for
any later round. That later round must be pre-registered in its own file before it runs, and its
winners come back here.

---

## Amendments

(none)
