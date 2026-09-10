"""
Backtest the insider copy-trade strategy against the CURRENT watchlist,
using each watched wallet's real recent buys and the tokens' real on-chain
price history (reconstructed from swap prints via Helius — no paid
historical-price API).

    python insider_backtest.py
    python insider_backtest.py --days 45 --watchlist insider_watchlist.json

For every buy a watched wallet made in the lookback window, this simulates:
  - entering `latency_minutes` after them (indexing + poll + fill delay),
  - the same portfolio limits (max_concurrent_positions, conviction sizing),
  - the same exits (take-profit / trailing / hard stop / time),
  - the same round-trip fee model,
then prints the resulting P&L, win rate, and per-wallet attribution.

READ THE CAVEATS the script prints at the end. This is a rough estimate, not
a promise — it is biased optimistic in some ways (wallets were picked
*because* they hit recent winners; token age / liquidity / holder filters
that the live bot applies can't be reconstructed historically) and
pessimistic in others (fixed latency + slippage assumption).
"""

import argparse
import heapq
import json
import os
import statistics
import time
from dotenv import load_dotenv

load_dotenv()

from insider_config import InsiderConfig
from insider_sources import LiveInsiderSource

STABLE = {InsiderConfig.sol_mint, InsiderConfig.usdc_mint}


def conviction_size(cfg, conviction, balance):
    frac = min(1.0, conviction / max(1e-9, cfg.conviction_full_size_score))
    target = cfg.min_position_usd + frac * (cfg.max_position_usd - cfg.min_position_usd)
    return min(target, cfg.max_position_usd, balance)


DEAD_TOKEN_MULT = 0.15   # a token that stops trading right after entry ≈ -85%
                         # (you can't sell into a pool with no liquidity)


def simulate_exit(cfg, series, entry_ts, entry_price):
    """Walk the price series forward from entry; return (mult, reason, n_points)."""
    peak = entry_price
    pts = [(ts, p) for ts, p in series if ts >= entry_ts]
    # No prints after entry, or trading dies within the first hour -> treat as
    # a rug/dead pool, not a skip. This is the common failure mode and ignoring
    # it makes the whole backtest look far better than reality.
    if not pts:
        return DEAD_TOKEN_MULT, "died_no_liquidity", 0
    if len(pts) < 3 or (pts[-1][0] - entry_ts) < 3600:
        worst = min(p for _, p in pts) / entry_price
        return min(worst, DEAD_TOKEN_MULT), "died_thin_liquidity", len(pts)
    for ts, p in pts:
        peak = max(peak, p)
        if p / entry_price >= cfg.take_profit_multiple:
            return cfg.take_profit_multiple, "take_profit", len(pts)
        if (1 - p / entry_price) * 100 >= cfg.hard_stop_loss_pct:
            return p / entry_price, "hard_stop", len(pts)
        if peak > entry_price and (1 - p / peak) * 100 >= cfg.trailing_stop_pct:
            return p / entry_price, "trailing_stop", len(pts)
        if (ts - entry_ts) / 60 >= cfg.max_hold_minutes:
            return p / entry_price, "time_exit", len(pts)
    return pts[-1][1] / entry_price, "time_exit_end_of_data", len(pts)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int)
    ap.add_argument("--watchlist", default=None)
    ap.add_argument("--min-buy", type=float,
                    help="override min_insider_buy_usd for the sim (lower = more sample)")
    args = ap.parse_args()

    cfg = InsiderConfig()
    if args.min_buy is not None:
        cfg.min_insider_buy_usd = args.min_buy
    lookback = args.days or cfg.backtest_lookback_days
    wl_path = args.watchlist or cfg.watchlist_path
    if not os.path.exists(wl_path):
        print(f"No watchlist at {wl_path}. Run:  python insider_bot.py discover")
        return

    wl = json.load(open(wl_path))
    scores = {w["wallet"]: float(w.get("score") or 0.0) for w in wl["wallets"]}
    wallets = list(scores)
    print(f"Backtesting {len(wallets)} wallet(s) over the last {lookback} days "
          f"(watchlist generated {wl.get('generated_at', '?')})\n")

    src = LiveInsiderSource(cfg)
    sol_usd = src._sol_usd()
    now = time.time()
    since = now - lookback * 86400

    # 1. collect every qualifying buy from every watched wallet
    raw_buys = []
    covered_from = now
    for w in wallets:
        evs = src._wallet_swaps(w)
        for ev in evs:
            covered_from = min(covered_from, ev.timestamp)
            if (ev.action == "buy" and ev.timestamp >= since
                    and ev.mint not in STABLE
                    and ev.usd_value >= cfg.min_insider_buy_usd):
                raw_buys.append((ev.timestamp, w, ev.mint, ev.usd_value, ev.token_amount))
        print(f"  {w[:10]}…  {len(evs)} swaps seen, "
              f"{sum(1 for b in raw_buys if b[1] == w)} qualifying buys")
    raw_buys.sort()
    if not raw_buys:
        print("\nNo qualifying insider buys in the window — nothing to simulate.")
        return

    # 2. group buys into signals (same mint, within the confirmation window)
    signals = {}
    for ts, w, mint, usd, tok in raw_buys:
        s = signals.get(mint)
        if s and ts - s["first_ts"] <= cfg.confirmation_window_minutes * 60:
            s["wallets"].add(w); s["usd"] += usd; s["tok"] += tok
        elif not s:
            signals[mint] = {"first_ts": ts, "wallets": {w}, "usd": usd, "tok": tok}
    # a signal needs the full max_hold window to have elapsed to be scorable
    resolved_before = now - (cfg.max_hold_minutes * 60 + cfg.latency_minutes * 60)
    unresolved = [m for m, s in signals.items() if s["first_ts"] > resolved_before]
    for m in unresolved:
        signals.pop(m)
    ordered = sorted(signals.items(), key=lambda x: x[1]["first_ts"])
    print(f"\n{len(ordered)} scorable signal(s) "
          f"({len(unresolved)} too recent to have played out)\n")

    # 3. simulate the portfolio chronologically
    balance = cfg.starting_balance_usd
    open_exits = []      # heap of exit_ts for currently-held positions
    trades, skips = [], []

    for mint, s in ordered:
        entry_ts = s["first_ts"] + cfg.latency_minutes * 60
        while open_exits and open_exits[0] <= entry_ts:
            heapq.heappop(open_exits)
        if len(s["wallets"]) < cfg.min_confirmations:
            skips.append((mint, "not_enough_confirmations")); continue
        if len(open_exits) >= cfg.max_concurrent_positions:
            skips.append((mint, "no_free_slot")); continue
        if balance < 0.50:
            skips.append((mint, "balance_too_low")); continue

        series, reached_start = src.token_price_series(
            mint, s["first_ts"] - 600, s["first_ts"] + cfg.max_hold_minutes * 60)
        insider_price_sol = (s["usd"] / sol_usd) / s["tok"] if s["tok"] else None

        if not series:
            if not reached_start:
                skips.append((mint, "undetermined_too_much_volume")); continue
            # we saw the token's whole history and there are no prints in the
            # 12h after their buy -> the pool is dead, you can't exit
            if insider_price_sol is None:
                skips.append((mint, "no_data_at_all")); continue
            entry_price = insider_price_sol * 1.08
        else:
            entry_price = next((p for ts, p in series if ts >= entry_ts), None)
            if entry_price is None:
                entry_price = (insider_price_sol or series[0][1]) * 1.08  # latency premium

        conviction = sum(scores.get(w, 0.0) for w in s["wallets"])
        size = conviction_size(cfg, conviction, balance)

        mult, reason, npts = simulate_exit(cfg, series, entry_ts, entry_price)
        if mult is None:
            skips.append((mint, reason)); continue

        gross = size * mult
        fees = size * cfg.round_trip_cost_pct() + 2 * cfg.platform_fee_flat_usd + 2 * cfg.network_fee_usd
        pnl = gross - size - fees
        balance += pnl
        exit_ts = entry_ts + cfg.max_hold_minutes * 60
        heapq.heappush(open_exits, exit_ts)
        trades.append({
            "mint": mint, "wallets": sorted(s["wallets"]), "size": size,
            "mult": mult, "reason": reason, "pnl": pnl, "npts": npts,
            "ts": s["first_ts"], "conviction": conviction,
        })

    # 4. report
    undetermined = sum(1 for _, r in skips if r in
                       ("undetermined_too_much_volume", "no_data_at_all"))
    report(cfg, lookback, covered_from, balance, trades, skips, scores,
           undetermined, len(ordered))


def report(cfg, lookback, covered_from, balance, trades, skips, scores,
           undetermined=0, n_signals=0):
    n = len(trades)
    print("=" * 60)
    if undetermined and undetermined >= max(1, n):
        print("RESULT: INCONCLUSIVE")
        print("=" * 60)
        print(f"Of {n_signals} scorable signals, {undetermined} could not be priced:")
        print("  Helius' free Enhanced Transactions API only serves recent")
        print("  history, so the price path of older buys into still-active")
        print("  tokens can't be reconstructed. Only {} signal(s) had usable".format(n))
        print("  data — too few to draw any conclusion from.")
        print()
        print("  A real historical backtest of this strategy needs a paid")
        print("  historical-price/OHLCV source (Birdeye, GeckoTerminal Pro,")
        print("  or Helius' paid tier). The forward dry-run already running")
        print("  is the unbiased test — let it accumulate for a few weeks.")
        if n:
            print("\n  (the few priced trades, for what little it's worth:)")
            for t in sorted(trades, key=lambda x: x["ts"]):
                d = time.strftime("%m-%d %H:%M", time.localtime(t["ts"]))
                print(f"    {d}  {t['mint'][:10]}…  {t['mult']:.2f}x  "
                      f"${t['pnl']:+.4f}  {t['reason']}")
        return
    if not n:
        print("No simulated trades (every signal was filtered). Skips:")
        for m, r in skips:
            print(f"  {m[:12]}…  {r}")
        return
    wins = [t for t in trades if t["pnl"] > 0]
    total_pnl = sum(t["pnl"] for t in trades)
    mults = [t["mult"] for t in trades]
    start = cfg.starting_balance_usd
    days_covered = (time.time() - covered_from) / 86400

    print(f"SIMULATED RESULT  (history actually covered ≈ {days_covered:.0f} days)")
    print("=" * 60)
    print(f"Trades:              {n}")
    print(f"Win rate:            {len(wins)}/{n}  ({len(wins)/n*100:.0f}%)")
    print(f"Total P&L:           ${total_pnl:+.4f}   "
          f"({total_pnl/start*100:+.1f}% on ${start:.2f})")
    print(f"Ending balance:      ${balance:.2f}")
    print(f"Median exit multiple:{statistics.median(mults):.2f}x   "
          f"best {max(mults):.2f}x   worst {min(mults):.2f}x")
    print(f"Avg win:  ${statistics.mean([t['pnl'] for t in wins]):+.4f}" if wins else "Avg win:  —")
    losers = [t for t in trades if t["pnl"] <= 0]
    print(f"Avg loss: ${statistics.mean([t['pnl'] for t in losers]):+.4f}" if losers else "Avg loss: —")

    from collections import Counter
    print("\nExits by reason:")
    for r, c in Counter(t["reason"] for t in trades).most_common():
        print(f"  {c:>3}  {r}")

    print("\nP&L by wallet (attribution split evenly across confirmers):")
    per = {}
    for t in trades:
        for w in t["wallets"]:
            per[w] = per.get(w, 0.0) + t["pnl"] / len(t["wallets"])
    for w, v in sorted(per.items(), key=lambda x: x[1], reverse=True):
        print(f"  {w[:12]}…  ${v:+.4f}   (score {scores.get(w, 0):.1f})")

    print("\nEvery simulated trade:")
    for t in sorted(trades, key=lambda x: x["ts"]):
        d = time.strftime("%m-%d %H:%M", time.localtime(t["ts"]))
        print(f"  {d}  {t['mint'][:12]}…  ${t['size']:.2f} -> {t['mult']:.2f}x  "
              f"${t['pnl']:+.4f}  {t['reason']}  ({t['npts']} prints)")

    if skips:
        from collections import Counter as C
        print("\nSignals skipped:")
        for r, c in C(r for _, r in skips).most_common():
            print(f"  {c:>3}  {r}")

    print("\n" + "-" * 60)
    print("CAVEATS — do not take this as a forecast:")
    print("  • These wallets were selected BECAUSE they hit recent winners.")
    print("    Their future edge is very likely lower (regression to mean).")
    print("  • Token age / liquidity / holder-count filters the live bot")
    print("    applies at entry CANNOT be reconstructed historically, so this")
    print("    sim takes trades the live bot might skip.")
    print(f"  • Entry modelled {cfg.latency_minutes:.0f} min after the insider; real")
    print("    latency and slippage vary and are often worse on thin pools.")
    print("  • Price series is reconstructed from swap prints; sparse/dead")
    print("    tokens (rugs) may be under-counted as losses, not over-.")
    print("  • Small sample. A different 30-day window can look very different.")
    print("-" * 60)


if __name__ == "__main__":
    main()
