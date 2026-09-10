"""
Insider / "smart money" copy-trade bot.

Two phases:

  1. DISCOVER  — mine wallets that got into big-winner tokens early and cheap,
                 and keep doing it (skill, not one lucky hit). Writes a
                 watchlist file.

        python insider_bot.py discover

  2. WATCH     — follow those wallets live. When enough of them buy the SAME
                 young token inside a short window, copy the buy, then manage
                 the exit (take-profit / trailing stop / hard stop / time /
                 "the insiders all sold").

        python insider_bot.py watch --minutes 120

Safe by default: mode is "dry_run" in insider_config.py — real discovery and
real on-chain tracking, but SIMULATED fills. No SOLANA_PRIVATE_KEY needed and
no funds move. Flip to "live" in insider_config.py only when you mean it; it
prompts for a typed confirmation at startup.

Runs completely independently of bot.py — separate loop, logs, state file and
bankroll cap — so you can run both at once.
"""

import argparse
import csv
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass, field

from dotenv import load_dotenv

load_dotenv()

from insider_config import InsiderConfig
from insider_sources import (
    MockInsiderSource, LiveInsiderSource, SwapEvent, WalletStats, CopySignal,
)
from insider_scoring import evaluate, score
from executors import PaperExecutor, LiveExecutor

CONFIRM_PHRASE = "trade real money from my wallet"


@dataclass
class InsiderPosition:
    mint: str
    symbol: str
    entry_price: float
    size_usd: float
    entry_time: float
    entry_fee_usd: float
    take_profit_multiple: float
    peak_price: float
    insiders: list = field(default_factory=list)
    entry_features: str = ""
    last_insider_check: float = 0.0   # throttles the on-chain "still holding?" RPC calls


@dataclass
class Stats:
    balance_usd: float
    starting_balance_usd: float
    trades: int = 0
    wins: int = 0
    losses: int = 0
    gross_profit_usd: float = 0.0
    total_fees_usd: float = 0.0
    skipped: int = 0

    @property
    def net_pnl_usd(self) -> float:
        return self.balance_usd - self.starting_balance_usd


class TradeLogger:
    def __init__(self, path: str):
        self.path = path
        is_new = not os.path.exists(path)
        self.f = open(path, "a", newline="")
        self.w = csv.writer(self.f)
        if is_new:
            self.w.writerow(["timestamp", "event", "mint", "symbol", "price_usd",
                             "size_usd", "fee_usd", "pnl_usd", "insiders", "reason"])

    def log(self, event, mint="", symbol="", price_usd="", size_usd="",
            fee_usd="", pnl_usd="", insiders="", reason=""):
        self.w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), event, mint, symbol,
                         price_usd, size_usd, fee_usd, pnl_usd, insiders, reason])
        self.f.flush()

    def close(self):
        self.f.close()


class InsiderBot:
    def __init__(self, cfg: InsiderConfig):
        self.cfg = cfg
        if cfg.starting_balance_usd > cfg.max_bankroll_usd:
            raise ValueError(
                f"starting_balance_usd ({cfg.starting_balance_usd}) exceeds "
                f"max_bankroll_usd ({cfg.max_bankroll_usd}). Refusing to start."
            )

        if cfg.mode == "live":
            self._confirm_live_mode()
            print("\n" + "=" * 62)
            print("LIVE MODE — the insider bot will place REAL swaps with REAL money.")
            print(f"Bankroll cap: ${cfg.max_bankroll_usd:.2f} | "
                  f"Per-trade: ${cfg.max_position_usd:.2f} | "
                  f"Circuit breaker: -${cfg.daily_max_loss_usd:.2f}")
            print("NOTE: this shares one wallet with bot.py. Their caps are separate.")
            print("=" * 62)
            self.source = LiveInsiderSource(cfg)
            self.executor = LiveExecutor(cfg)
        elif cfg.mode == "dry_run":
            self.source = LiveInsiderSource(cfg)
            self.executor = PaperExecutor(cfg)
        else:
            self.source = MockInsiderSource(cfg)
            self.executor = PaperExecutor(cfg)

        self.stats = Stats(cfg.starting_balance_usd, cfg.starting_balance_usd)
        self.positions: dict[str, InsiderPosition] = {}
        self.traded_mints: set[str] = set()
        self.session_loss_usd = 0.0
        self.new_positions_this_hour = 0
        self.hour_window_start = time.time()
        self.halted = False
        log_path = "insider_dry_run_log.csv" if cfg.mode == "dry_run" else "insider_trade_log.csv"
        self.logger = TradeLogger(log_path)
        self._state_file = "insider_state.json"
        if cfg.mode == "live":
            self._load_state()

    # ---------- live-mode guard rails ----------

    def _confirm_live_mode(self):
        print("\nThis will trade REAL money from the wallet in SOLANA_PRIVATE_KEY.")
        print(f'Type exactly:  {CONFIRM_PHRASE}')
        if input("> ").strip() != CONFIRM_PHRASE:
            raise SystemExit("Confirmation phrase did not match. Aborting.")

    def _notify(self, title: str, message: str):
        if self.cfg.mode != "live":
            return
        try:
            script = (f'display notification {json.dumps(message)} '
                      f'with title {json.dumps(title)} sound name "Glass"')
            subprocess.run(["osascript", "-e", script], check=False, timeout=5)
        except Exception:
            pass

    def _save_state(self):
        if self.cfg.mode != "live":
            return
        state = {
            "positions": {m: asdict(p) for m, p in self.positions.items()},
            "traded_mints": sorted(self.traded_mints),
            "balance_usd": self.stats.balance_usd,
            "starting_balance_usd": self.stats.starting_balance_usd,
            "trades": self.stats.trades, "wins": self.stats.wins,
            "losses": self.stats.losses, "gross_profit_usd": self.stats.gross_profit_usd,
            "total_fees_usd": self.stats.total_fees_usd, "skipped": self.stats.skipped,
            "session_loss_usd": self.session_loss_usd,
        }
        with open(self._state_file, "w") as f:
            json.dump(state, f, indent=2)

    def _load_state(self):
        if not os.path.exists(self._state_file):
            return
        with open(self._state_file) as f:
            s = json.load(f)
        self.positions = {m: InsiderPosition(**p) for m, p in s.get("positions", {}).items()}
        self.traded_mints = set(s.get("traded_mints", []))
        self.stats.balance_usd = s.get("balance_usd", self.stats.balance_usd)
        self.stats.starting_balance_usd = s.get("starting_balance_usd", self.stats.starting_balance_usd)
        self.stats.trades = s.get("trades", 0)
        self.stats.wins = s.get("wins", 0)
        self.stats.losses = s.get("losses", 0)
        self.stats.gross_profit_usd = s.get("gross_profit_usd", 0.0)
        self.stats.total_fees_usd = s.get("total_fees_usd", 0.0)
        self.stats.skipped = s.get("skipped", 0)
        self.session_loss_usd = s.get("session_loss_usd", 0.0)
        if self.positions:
            held = ", ".join(f"{p.symbol} ({m})" for m, p in self.positions.items())
            print(f"[insider] resumed {len(self.positions)} open position(s): {held}")

    def _check_circuit_breaker(self):
        if self.cfg.mode != "live":
            return
        if self.session_loss_usd >= self.cfg.daily_max_loss_usd:
            self.halted = True
            self.logger.log("HALT", reason=f"daily_max_loss hit: -${self.session_loss_usd:.2f}")
            print(f"[HALT] circuit breaker: session loss ${self.session_loss_usd:.2f} "
                  f">= ${self.cfg.daily_max_loss_usd:.2f}. No new entries.")

    def _reset_hourly_window_if_needed(self):
        if time.time() - self.hour_window_start > 3600:
            self.hour_window_start = time.time()
            self.new_positions_this_hour = 0

    # ================= PHASE 1: DISCOVER =================

    def discover(self):
        print(f"[discover] mode={self.cfg.mode} | winner threshold >= "
              f"{self.cfg.winner_min_multiple:.0f}x\n")
        winners = self.source.find_winner_mints()
        print(f"[discover] {len(winners)} winner token(s) to mine for early buyers")

        candidates: dict[str, list] = {}
        for i, mint in enumerate(winners, 1):
            buyers = self.source.early_buyers_of(mint)
            for w, ts, price in buyers:
                candidates.setdefault(w, []).append((mint, ts, price))
            print(f"  [{i}/{len(winners)}] {mint[:8]}… -> {len(buyers)} early buyers")
            time.sleep(0.2)

        for w in self.cfg.manual_wallets:
            candidates.setdefault(w, [])

        print(f"\n[discover] scoring {len(candidates)} candidate wallet(s)…")
        stats_list: list[WalletStats] = []
        for i, w in enumerate(candidates, 1):
            s = self.source.wallet_stats(w)
            if s:
                # Strongest real signal we have: this wallet was literally an
                # early buyer of N tokens that then ran >= winner_min_multiple.
                # Trust that count as a floor on early_wins (the multiple-based
                # estimate misses tokens the wallet already rotated out of).
                early_on = len({m for (m, _t, _p) in candidates.get(w, [])})
                s.early_wins = max(s.early_wins, early_on)
                stats_list.append(s)
            if i % 10 == 0:
                print(f"  scored {i}/{len(candidates)}")
            time.sleep(0.1)

        kept, rejected = evaluate(stats_list, self.cfg)

        # manual wallets are always followed, even if unscored/failing
        kept_pubkeys = {s.wallet for s in kept}
        for w in self.cfg.manual_wallets:
            if w not in kept_pubkeys:
                kept.append(WalletStats(wallet=w, note="manual_always_follow"))

        out = {
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "mode": self.cfg.mode,
            "winner_min_multiple": self.cfg.winner_min_multiple,
            "wallets": [
                {"wallet": s.wallet, "score": s.score, "hit_rate": round(s.hit_rate, 3),
                 "median_multiple": round(s.median_multiple, 2),
                 "best_multiple": round(s.best_multiple, 2),
                 "early_wins": s.early_wins, "tokens_tracked": s.tokens_tracked,
                 "last_trade_days_ago": round((time.time() - s.last_trade_ts) / 86400, 1)
                 if s.last_trade_ts else None,
                 "note": s.note}
                for s in kept
            ],
        }
        with open(self.cfg.watchlist_path, "w") as f:
            json.dump(out, f, indent=2)

        print(f"\n===== WATCHLIST ({len(kept)} wallets) -> {self.cfg.watchlist_path} =====")
        print(f"{'wallet':<46}{'score':>8}{'hit%':>7}{'med x':>8}{'earlyW':>8}{'#tok':>6}{'last':>7}")
        for s in kept:
            last = f"{(time.time() - s.last_trade_ts) / 86400:.0f}d" if s.last_trade_ts else "  ?"
            print(f"{s.wallet:<46}{s.score:>8.2f}{s.hit_rate*100:>6.0f}%"
                  f"{min(s.median_multiple, 999):>8.2f}{s.early_wins:>8}{s.tokens_tracked:>6}{last:>7}")
        if rejected:
            print(f"\n{len(rejected)} rejected. Sample reasons:")
            for s in rejected[:8]:
                print(f"  {s.wallet[:16]}…  {s.note}")
        print("\nRun:  python insider_bot.py watch --minutes 120")

    # ================= PHASE 2: WATCH =================

    def _load_watchlist(self) -> list[str]:
        self.wallet_scores: dict[str, float] = {}
        if not os.path.exists(self.cfg.watchlist_path):
            return []
        with open(self.cfg.watchlist_path) as f:
            data = json.load(f)
        rows = data.get("wallets", [])
        for row in rows:
            self.wallet_scores[row["wallet"]] = float(row.get("score") or 0.0)
        return [row["wallet"] for row in rows]

    def _conviction_size(self, sig: CopySignal) -> float:
        """Scale position size by how much combined watchlist score bought in.
        1 mediocre wallet -> near min_position_usd; several strong wallets ->
        up to max_position_usd."""
        c = self.cfg
        frac = min(1.0, sig.conviction / max(1e-9, c.conviction_full_size_score))
        target = c.min_position_usd + frac * (c.max_position_usd - c.min_position_usd)
        return min(target, c.max_position_usd, self.stats.balance_usd)

    def _passes_filters(self, sig: CopySignal) -> str | None:
        c = self.cfg
        if sig.mint in self.traded_mints or sig.mint in self.positions:
            return "already_traded_or_held"
        if len(sig.wallets) < c.min_confirmations:
            return f"not_enough_confirmations ({len(sig.wallets)} < {c.min_confirmations})"
        if sig.insider_usd < c.min_insider_buy_usd:
            return f"insider_buy_too_small (${sig.insider_usd:.0f})"
        if sig.liquidity_usd and sig.liquidity_usd < c.min_token_liquidity_usd:
            return f"liquidity_too_low ({sig.liquidity_usd:.0f} < {c.min_token_liquidity_usd:.0f})"
        if sig.holder_count and sig.holder_count > c.max_token_holders_at_copy:
            return f"too_crowded ({sig.holder_count} holders > {c.max_token_holders_at_copy})"
        if sig.price_change_1h_pct > c.max_token_price_change_1h_pct:
            return f"already_vertical ({sig.price_change_1h_pct:.0f}% 1h)"
        if c.copy_only_new_tokens and sig.token_age_minutes is not None:
            if sig.token_age_minutes > c.max_token_age_minutes:
                return f"token_too_old ({sig.token_age_minutes:.0f}m > {c.max_token_age_minutes:.0f}m)"
        if not sig.price_usd or sig.price_usd <= 0:
            return "no_price"
        # don't be exit liquidity: if it already ran past the insiders' entry
        if (sig.insider_avg_entry_usd > 0
                and sig.price_usd > sig.insider_avg_entry_usd * c.max_entry_premium_over_insider):
            prem = sig.price_usd / sig.insider_avg_entry_usd
            return f"already_ran_from_insider_entry ({prem:.2f}x their price > {c.max_entry_premium_over_insider:.2f}x)"

        # --- "research the coin" health checks (only reject on real data) ---
        if c.require_coin_health:
            if sig.price_change_5m_pct < c.min_coin_chg5m_pct:
                return f"dumping_now ({sig.price_change_5m_pct:.0f}%/5m < {c.min_coin_chg5m_pct:.0f})"
            if sig.liquidity_change_1h_pct < c.min_coin_liq_change_1h_pct:
                return f"liquidity_draining ({sig.liquidity_change_1h_pct:.0f}%/1h)"
            if sig.organic_score and sig.organic_score < c.min_coin_organic_score:
                return f"low_organic_score ({sig.organic_score:.0f} < {c.min_coin_organic_score:.0f})"
            if sig.num_organic_buyers_5m < c.min_coin_organic_buyers_5m:
                return f"no_real_buyers ({sig.num_organic_buyers_5m} organic buyers/5m)"
        return None

    def _try_enter(self, sig: CopySignal):
        reason = self._passes_filters(sig)
        if reason:
            self.stats.skipped += 1
            self.logger.log("SKIP", mint=sig.mint, symbol=sig.symbol,
                            insiders=";".join(w[:6] for w in sig.wallets), reason=reason)
            return
        if len(self.positions) >= self.cfg.max_concurrent_positions:
            self.stats.skipped += 1
            self.logger.log("SKIP", mint=sig.mint, symbol=sig.symbol, reason="max_concurrent_positions")
            return
        self._reset_hourly_window_if_needed()
        if self.new_positions_this_hour >= self.cfg.max_new_positions_per_hour:
            self.stats.skipped += 1
            self.logger.log("SKIP", mint=sig.mint, symbol=sig.symbol, reason="hourly_rate_limit")
            return
        size = self._conviction_size(sig)
        if size < 0.50:
            self.stats.skipped += 1
            self.logger.log("SKIP", mint=sig.mint, symbol=sig.symbol, reason="balance_too_low")
            return

        fill = self.executor.buy(sig.mint, sig.price_usd, size)
        if not fill.success:
            self.stats.skipped += 1
            self.logger.log("SKIP", mint=sig.mint, symbol=sig.symbol, reason=f"buy_failed: {fill.reason}")
            return

        features = (f"insiders={len(sig.wallets)} conviction={sig.conviction:.1f} "
                    f"insider_usd={sig.insider_usd:.0f} entry_prem="
                    f"{(sig.price_usd / sig.insider_avg_entry_usd) if sig.insider_avg_entry_usd else 0:.2f}x "
                    f"age_min={sig.token_age_minutes} liq={sig.liquidity_usd:.0f} "
                    f"holders={sig.holder_count} chg1h={sig.price_change_1h_pct:.0f}")
        pos = InsiderPosition(
            mint=sig.mint, symbol=sig.symbol, entry_price=fill.filled_price_usd,
            size_usd=size, entry_time=time.time(), entry_fee_usd=fill.fee_usd,
            take_profit_multiple=self.cfg.take_profit_multiple,
            peak_price=fill.filled_price_usd, insiders=list(sig.wallets),
            entry_features=features,
        )
        self.positions[sig.mint] = pos
        self.traded_mints.add(sig.mint)
        self.stats.balance_usd -= size + fill.fee_usd
        self.stats.total_fees_usd += fill.fee_usd
        self.new_positions_this_hour += 1
        self._save_state()
        self.logger.log("BUY", mint=sig.mint, symbol=sig.symbol,
                        price_usd=f"{fill.filled_price_usd:.10f}", size_usd=f"{size:.2f}",
                        fee_usd=f"{fill.fee_usd:.4f}",
                        insiders=";".join(w[:6] for w in sig.wallets),
                        reason=f"copy | TP {self.cfg.take_profit_multiple:.2f}x | {features}")
        self._notify("Insider bot bought", f"{sig.symbol}: ${size:.2f}, {len(sig.wallets)} insiders in")

    def _try_exit(self, pos: InsiderPosition):
        price = self.source.get_price(pos.mint)
        if not price:
            return
        pos.peak_price = max(pos.peak_price, price)
        mult = price / pos.entry_price
        held_min = (time.time() - pos.entry_time) / 60
        drop_from_peak = (1 - price / pos.peak_price) * 100
        loss_pct = (1 - mult) * 100

        exit_reason = None
        if mult >= pos.take_profit_multiple:
            exit_reason = "take_profit"
        elif loss_pct >= self.cfg.hard_stop_loss_pct:
            exit_reason = "hard_stop"
        elif pos.peak_price > pos.entry_price and drop_from_peak >= self.cfg.trailing_stop_pct:
            exit_reason = "trailing_stop"
        elif held_min >= self.cfg.max_hold_minutes:
            exit_reason = "time_exit"
        elif (self.cfg.exit_when_insiders_exit and pos.insiders
              and time.time() - pos.last_insider_check > 300):
            pos.last_insider_check = time.time()
            try:
                still_in = self.source.insiders_still_holding(pos.mint, pos.insiders)
                if not still_in:
                    exit_reason = "insiders_all_exited"
            except Exception as e:
                # a flaky RPC here must never wedge the price-based exits below
                print(f"[insider] insider-holding check failed for {pos.symbol}: {e}")

        if not exit_reason:
            return

        current_value = pos.size_usd * mult
        fill = self.executor.sell(pos.mint, price, current_value)
        if not fill.success:
            if "No on-chain balance" in fill.reason:
                loss = pos.size_usd + pos.entry_fee_usd
                self.stats.trades += 1
                self.stats.losses += 1
                self.session_loss_usd += loss
                self.logger.log("SELL", mint=pos.mint, symbol=pos.symbol, pnl_usd=f"{-loss:.4f}",
                                reason=f"position_lost | {pos.entry_features} | {fill.reason}")
                del self.positions[pos.mint]
                self._save_state()
                self._check_circuit_breaker()
                return
            self.logger.log("ERROR", mint=pos.mint, symbol=pos.symbol, reason=f"sell_failed: {fill.reason}")
            return

        proceeds = fill.amount_usd - fill.fee_usd
        pnl = proceeds - pos.size_usd - pos.entry_fee_usd
        self.stats.balance_usd += proceeds
        self.stats.total_fees_usd += fill.fee_usd
        self.stats.trades += 1
        if pnl > 0:
            self.stats.wins += 1
            self.stats.gross_profit_usd += pnl
        else:
            self.stats.losses += 1
            self.session_loss_usd += abs(pnl)
        self.logger.log("SELL", mint=pos.mint, symbol=pos.symbol,
                        price_usd=f"{fill.filled_price_usd:.10f}", size_usd=f"{current_value:.2f}",
                        fee_usd=f"{fill.fee_usd:.4f}", pnl_usd=f"{pnl:.4f}",
                        reason=f"{exit_reason} | peak {pos.peak_price/pos.entry_price:.2f}x | {pos.entry_features}")
        del self.positions[pos.mint]
        self._save_state()
        self._notify(f"Insider bot sold ({'win' if pnl > 0 else 'loss'})",
                     f"{pos.symbol}: {exit_reason}, P&L ${pnl:.2f}")
        self._check_circuit_breaker()

    def watch(self, minutes: float):
        watched = self._load_watchlist()
        if not watched:
            print(f"No watchlist at {self.cfg.watchlist_path}. Run:  "
                  f"python insider_bot.py discover")
            return
        print(f"[watch] following {len(watched)} wallet(s) | mode={self.cfg.mode} | "
              f"balance ${self.stats.balance_usd:.2f} | cap ${self.cfg.max_bankroll_usd:.2f}")

        interval = (self.cfg.poll_interval_seconds if self.cfg.mode == "paper"
                    else self.cfg.live_poll_interval_seconds)
        seen_since = {w: time.time() for w in watched}
        # mint -> {wallets:set, first_ts, usd, tok}  (tok = insider tokens bought,
        # so usd/tok is their avg entry price for the exit-liquidity check)
        pending: dict[str, dict] = {}
        end = time.time() + minutes * 60

        while time.time() < end:
            if not self.halted:
                for w in watched:
                    for ev in self.source.recent_buys(w, seen_since[w]):
                        seen_since[w] = max(seen_since[w], ev.timestamp)
                        if ev.usd_value < self.cfg.min_insider_buy_usd:
                            continue
                        if ev.mint in self.traded_mints or ev.mint in self.positions:
                            continue
                        p = pending.setdefault(ev.mint, {
                            "wallets": set(), "first_ts": ev.timestamp, "usd": 0.0, "tok": 0.0})
                        p["wallets"].add(w)
                        p["first_ts"] = min(p["first_ts"], ev.timestamp)
                        p["usd"] += ev.usd_value
                        p["tok"] += ev.token_amount

                now = time.time()
                for mint in list(pending):
                    p = pending[mint]
                    age_min = (now - p["first_ts"]) / 60
                    if age_min > self.cfg.confirmation_window_minutes:
                        del pending[mint]
                        continue
                    if len(p["wallets"]) < self.cfg.min_confirmations:
                        continue
                    info = self.source.token_info(mint) or {}
                    price = self.source.get_price(mint)
                    sig = CopySignal(
                        mint=mint, symbol=info.get("symbol", mint[:6]),
                        wallets=sorted(p["wallets"]), first_buy_ts=p["first_ts"],
                        insider_usd=p["usd"],
                        token_age_minutes=info.get("age_minutes"),
                        liquidity_usd=info.get("liquidity_usd", 0.0),
                        holder_count=info.get("holder_count", 0),
                        price_change_1h_pct=info.get("price_change_1h_pct", 0.0),
                        price_usd=price or 0.0,
                        insider_avg_entry_usd=(p["usd"] / p["tok"]) if p["tok"] else 0.0,
                        conviction=sum(self.wallet_scores.get(w, 0.0) for w in p["wallets"]),
                        price_change_5m_pct=info.get("price_change_5m_pct", 0.0),
                        num_organic_buyers_5m=info.get("num_organic_buyers_5m", 0),
                        organic_score=info.get("organic_score", 0.0),
                        liquidity_change_1h_pct=info.get("liquidity_change_1h_pct", 0.0),
                    )
                    self._try_enter(sig)
                    pending.pop(mint, None)

            for mint in list(self.positions):
                self._try_exit(self.positions[mint])

            time.sleep(interval)

        self._report()
        self.logger.close()

    def _report(self):
        s = self.stats
        wr = (s.wins / s.trades * 100) if s.trades else 0.0
        print("\n===== INSIDER SESSION REPORT =====")
        print(f"Trades:            {s.trades}  ({s.wins}W / {s.losses}L, {wr:.1f}% win)")
        print(f"Skipped:           {s.skipped}")
        print(f"Gross profit:      ${s.gross_profit_usd:.4f}")
        print(f"Fees paid:         ${s.total_fees_usd:.4f}")
        print(f"Net P&L:           ${s.net_pnl_usd:.4f}")
        print(f"Ending balance:    ${s.balance_usd:.2f}")
        print(f"Open positions:    {len(self.positions)}")
        print(f"Log:               {self.logger.path}")
        print("==================================\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Insider / smart-money copy-trade bot")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_disc = sub.add_parser("discover", help="build the wallet watchlist")
    p_disc.add_argument("--max-wallets", type=int, help="override max_watched_wallets")
    p_disc.add_argument("--seeds", type=str, help="comma-separated winner token mints to also mine")

    p_watch = sub.add_parser("watch", help="follow the watchlist live")
    p_watch.add_argument("--minutes", type=float, default=60)

    args = parser.parse_args()
    cfg = InsiderConfig()  # mode="dry_run" by default — see insider_config.py

    if args.cmd == "discover":
        if args.max_wallets:
            cfg.max_watched_wallets = args.max_wallets
        if args.seeds:
            cfg.seed_winner_mints = [m.strip() for m in args.seeds.split(",") if m.strip()]
        InsiderBot(cfg).discover()
    elif args.cmd == "watch":
        InsiderBot(cfg).watch(minutes=args.minutes)
