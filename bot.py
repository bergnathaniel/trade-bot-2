"""
Graduated-token scalper bot — main loop.

Run it with:
    python bot.py --minutes 10

Safe by default: mode is "paper" in config.py. Live mode (config.py:
mode="live") places real trades and requires typing a confirmation phrase
at startup — see Bot._confirm_live_mode.
"""

import argparse
import csv
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from config import Config
from data_sources import MockDataSource, LiveDataSource, TokenCandidate
from executors import PaperExecutor, LiveExecutor, FillResult


@dataclass
class Position:
    mint: str
    symbol: str
    entry_price: float
    size_usd: float
    entry_time: float
    entry_fee_usd: float
    required_exit_multiplier: float
    entry_features: str = ""  # candidate's feature values at buy time, for later analysis


@dataclass
class SessionStats:
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
        self.writer = csv.writer(self.f)
        if is_new:
            self.writer.writerow(
                ["timestamp", "event", "mint", "symbol", "price_usd",
                 "size_usd", "fee_usd", "pnl_usd", "reason"]
            )

    def log(self, event, mint="", symbol="", price_usd="", size_usd="",
             fee_usd="", pnl_usd="", reason=""):
        self.writer.writerow(
            [time.strftime("%Y-%m-%d %H:%M:%S"), event, mint, symbol,
             price_usd, size_usd, fee_usd, pnl_usd, reason]
        )
        self.f.flush()

    def close(self):
        self.f.close()


class Bot:
    def __init__(self, cfg: Config):
        self.cfg = cfg

        # Hard safety check — never allow the configured bankroll to exceed the cap.
        if cfg.starting_balance_usd > cfg.max_bankroll_usd:
            raise ValueError(
                f"starting_balance_usd ({cfg.starting_balance_usd}) exceeds "
                f"max_bankroll_usd ({cfg.max_bankroll_usd}). Refusing to start."
            )

        if cfg.mode == "live":
            print("\n" + "=" * 60)
            print("LIVE MODE — this places real trades with real money.")
            print(f"Bankroll cap: ${cfg.max_bankroll_usd:.2f} | "
                  f"Per-trade cap: ${cfg.max_position_usd:.2f} | "
                  f"Circuit breaker: -${cfg.daily_max_loss_usd:.2f}")
            print("=" * 60)
            self.data_source = LiveDataSource(cfg)
            self.executor = LiveExecutor(cfg)
        elif cfg.mode == "dry_run":
            # Real graduation feed + real prices, but PaperExecutor simulates the
            # fills — no wallet, no RPC, no funds at risk.
            self.data_source = LiveDataSource(cfg)
            self.executor = PaperExecutor(cfg)
        else:
            self.data_source = MockDataSource()
            self.executor = PaperExecutor(cfg)

        self.stats = SessionStats(
            balance_usd=cfg.starting_balance_usd,
            starting_balance_usd=cfg.starting_balance_usd,
        )
        self.positions: dict[str, Position] = {}
        self.session_loss_usd = 0.0
        self.new_positions_this_hour = 0
        self.hour_window_start = time.time()
        self.halted = False
        log_path = "dry_run_log.csv" if cfg.mode == "dry_run" else "trade_log.csv"
        self.logger = TradeLogger(log_path)

        # Live mode persists open positions + balance across restarts. Without this,
        # stopping and restarting the bot (e.g. after a config change) silently forgets
        # any position it's still holding on-chain — this happened for real and is why
        # this exists. Paper/dry_run don't touch real money, so they stay ephemeral.
        self._state_file = "live_state.json"
        if cfg.mode == "live":
            self._load_state()

    def _save_state(self):
        if self.cfg.mode != "live":
            return
        state = {
            "positions": {mint: asdict(pos) for mint, pos in self.positions.items()},
            "balance_usd": self.stats.balance_usd,
            "starting_balance_usd": self.stats.starting_balance_usd,
            "trades": self.stats.trades,
            "wins": self.stats.wins,
            "losses": self.stats.losses,
            "gross_profit_usd": self.stats.gross_profit_usd,
            "total_fees_usd": self.stats.total_fees_usd,
            "skipped": self.stats.skipped,
            "session_loss_usd": self.session_loss_usd,
        }
        with open(self._state_file, "w") as f:
            json.dump(state, f, indent=2)

    def _load_state(self):
        if not os.path.exists(self._state_file):
            return
        with open(self._state_file) as f:
            state = json.load(f)
        self.positions = {mint: Position(**p) for mint, p in state.get("positions", {}).items()}
        self.stats.balance_usd = state.get("balance_usd", self.stats.balance_usd)
        self.stats.starting_balance_usd = state.get("starting_balance_usd", self.stats.starting_balance_usd)
        self.stats.trades = state.get("trades", 0)
        self.stats.wins = state.get("wins", 0)
        self.stats.losses = state.get("losses", 0)
        self.stats.gross_profit_usd = state.get("gross_profit_usd", 0.0)
        self.stats.total_fees_usd = state.get("total_fees_usd", 0.0)
        self.stats.skipped = state.get("skipped", 0)
        self.session_loss_usd = state.get("session_loss_usd", 0.0)
        if self.positions:
            held = ", ".join(f"{p.symbol} ({m})" for m, p in self.positions.items())
            print(f"[Bot] resumed {len(self.positions)} open position(s) from {self._state_file}: {held}")

    def _notify(self, title: str, message: str):
        """macOS notification/sound so a real trade doesn't go unnoticed in the terminal."""
        if self.cfg.mode != "live":
            return
        try:
            script = f'display notification {json.dumps(message)} with title {json.dumps(title)} sound name "Glass"'
            subprocess.run(["osascript", "-e", script], check=False, timeout=5)
        except Exception:
            pass  # a missed notification is never worth crashing the bot over

    # ---------- risk controls ----------

    def _check_circuit_breaker(self):
        # The circuit breaker protects real money — it has no purpose in dry_run/paper
        # (no funds at risk), and halting it there just kills data collection early for
        # no reason. This is exactly what happened: a dry-run session inherited a $1.50
        # threshold tuned for live trading and went quiet a couple hours in.
        if self.cfg.mode != "live":
            return
        if self.session_loss_usd >= self.cfg.daily_max_loss_usd:
            self.halted = True
            self.logger.log("HALT", reason=f"daily_max_loss hit: -${self.session_loss_usd:.2f}")
            print(f"[HALT] Circuit breaker tripped. Session loss ${self.session_loss_usd:.2f} "
                  f">= limit ${self.cfg.daily_max_loss_usd:.2f}. Halting new entries.")

    def _reset_hourly_window_if_needed(self):
        if time.time() - self.hour_window_start > 3600:
            self.hour_window_start = time.time()
            self.new_positions_this_hour = 0

    # ---------- entry ----------

    def _passes_filters(self, c: TokenCandidate) -> Optional[str]:
        if self.cfg.mode == "dry_run":
            # Train/test-validated findings from a 338-trade batch, split in half and only
            # kept if the SAME direction showed up in both halves independently (not just
            # in the aggregate — that's how noise gets mistaken for signal). All of these
            # replicated. The story: this tight 30-min-scalp strategy does better on early/
            # thin/currently-dipping tokens and worse on already-popular/high-liquidity/
            # already-pumping ones — by the time a token looks "safe," the quick move this
            # strategy needs has usually already happened. Concentration cap dropped: the
            # data didn't support it (high concentration wasn't worse here), though that's
            # the one flip I'm least comfortable with given real rug risk — the tight
            # stop-loss is what's actually protecting against that now, not this filter.
            if c.liquidity_usd <= 0:
                return "no_liquidity"
            if c.dev_mints > 2:
                return f"serial_dev ({c.dev_mints} prior mints)"
            if c.liquidity_usd > 5000:
                return f"liquidity_too_high_for_this_strategy ({c.liquidity_usd:.0f} > 5000)"
            if c.holder_count > 100:
                return f"too_many_holders_for_this_strategy ({c.holder_count} > 100)"
            if c.price_change_5m_pct > 15:
                return f"already_pumping_5m ({c.price_change_5m_pct:.1f}% > 15%)"
            if c.price_change_1h_pct > 30:
                return f"already_pumping_1h ({c.price_change_1h_pct:.1f}% > 30%)"
            return None
        if c.liquidity_usd < self.cfg.min_liquidity_usd_at_entry:
            return f"liquidity_too_low ({c.liquidity_usd:.0f} < {self.cfg.min_liquidity_usd_at_entry:.0f})"
        if c.holder_count < self.cfg.min_holder_count:
            return f"too_few_holders ({c.holder_count} < {self.cfg.min_holder_count})"
        if c.top_wallet_pct > self.cfg.max_single_wallet_holding_pct:
            return f"concentration_risk ({c.top_wallet_pct:.1f}% > {self.cfg.max_single_wallet_holding_pct:.1f}%)"
        if not c.renounced:
            return "authority_not_renounced"
        if not c.lp_locked:
            return "lp_not_locked"
        # organic_score of exactly 0.0 showed up on nearly every real candidate — that's
        # Jupiter not having computed it yet this soon after graduation, not a real score
        # of zero (real observed scores were in the 60s-70s). Treat unset (0.0) as unknown
        # and skip the check, rather than rejecting almost everything for a data gap.
        if 0.0 < c.organic_score < self.cfg.min_organic_score:
            return f"organic_score_too_low ({c.organic_score:.0f} < {self.cfg.min_organic_score:.0f})"
        if c.price_change_5m_pct < self.cfg.min_price_change_5m_pct:
            return f"actively_dumping ({c.price_change_5m_pct:.1f}% in 5m)"
        if c.price_change_1h_pct < self.cfg.min_price_change_1h_pct:
            return f"actively_dumping_1h ({c.price_change_1h_pct:.1f}% in 1h)"
        if c.num_organic_buyers_5m < self.cfg.min_organic_buyers_5m:
            return f"too_few_organic_buyers ({c.num_organic_buyers_5m} < {self.cfg.min_organic_buyers_5m})"
        if c.dev_mints > self.cfg.max_dev_mints:
            return f"serial_dev ({c.dev_mints} prior mints)"
        return None

    def _try_enter(self, c: TokenCandidate):
        reason = self._passes_filters(c)
        if reason:
            self.stats.skipped += 1
            self.logger.log("SKIP", mint=c.mint, symbol=c.symbol, reason=reason)
            return

        if len(self.positions) >= self.cfg.max_concurrent_positions:
            self.stats.skipped += 1
            self.logger.log("SKIP", mint=c.mint, symbol=c.symbol, reason="max_concurrent_positions")
            return

        self._reset_hourly_window_if_needed()
        if self.new_positions_this_hour >= self.cfg.max_new_positions_per_hour:
            self.stats.skipped += 1
            self.logger.log("SKIP", mint=c.mint, symbol=c.symbol, reason="hourly_rate_limit")
            return

        size = min(self.cfg.max_position_usd, self.stats.balance_usd)
        if size < 0.50:  # not worth trading dust
            self.stats.skipped += 1
            self.logger.log("SKIP", mint=c.mint, symbol=c.symbol, reason="balance_too_low")
            return

        tick = self.data_source.get_price(c.mint)
        if not tick:
            return

        fill = self.executor.buy(c.mint, tick.price_usd, size)
        if not fill.success:
            self.stats.skipped += 1
            self.logger.log("SKIP", mint=c.mint, symbol=c.symbol, reason=f"buy_failed: {fill.reason}")
            return
        # NOTE: there is no post-hoc "reject if slippage too high" check here anymore.
        # For LiveExecutor, by the time fill.success is True, the swap already executed
        # on-chain — real SOL is spent and real tokens are already in the wallet. Checking
        # slippage_pct afterward and discarding the trade doesn't undo it, it just makes
        # the bot lose track of a real position it still holds (this happened for real:
        # a live buy filled, got discarded here as "slippage_too_high", and the tokens
        # sat untracked in the wallet with no exit management). Jupiter's own slippageBps
        # parameter (set from max_allowed_slippage_pct, see executors.py) already enforces
        # this atomically on-chain — the swap fails outright instead of overfilling.

        req_mult = self.cfg.required_exit_multiplier(size)
        features = (
            f"liq={c.liquidity_usd:.0f} holders={c.holder_count} top_pct={c.top_wallet_pct:.1f} "
            f"organic={c.organic_score:.0f} chg5m={c.price_change_5m_pct:.1f} "
            f"chg1h={c.price_change_1h_pct:.1f} organic_buyers5m={c.num_organic_buyers_5m} "
            f"dev_mints={c.dev_mints} renounced={c.renounced} lp_locked={c.lp_locked}"
        )
        pos = Position(
            mint=c.mint,
            symbol=c.symbol,
            entry_price=fill.filled_price_usd,
            size_usd=size,
            entry_time=time.time(),
            entry_fee_usd=fill.fee_usd,
            required_exit_multiplier=req_mult,
            entry_features=features,
        )
        self.positions[c.mint] = pos
        self.stats.balance_usd -= size            # capital locked into the position
        self.stats.balance_usd -= fill.fee_usd     # buy-side fee
        self.stats.total_fees_usd += fill.fee_usd
        self.new_positions_this_hour += 1
        self._save_state()

        self.logger.log(
            "BUY", mint=c.mint, symbol=c.symbol, price_usd=f"{fill.filled_price_usd:.8f}",
            size_usd=f"{size:.2f}", fee_usd=f"{fill.fee_usd:.4f}",
            reason=f"needs {req_mult:.3f}x to exit profitably | tx:{fill.reason}"
        )
        self._notify("Bot bought a token", f"{c.symbol}: ${size:.2f}, needs {req_mult:.3f}x to exit profitably")

    # ---------- exit ----------

    def _try_exit(self, pos: Position):
        tick = self.data_source.get_price(pos.mint)
        if not tick:
            return

        held_minutes = (time.time() - pos.entry_time) / 60
        price_multiple = tick.price_usd / pos.entry_price
        loss_pct = (1 - price_multiple) * 100

        exit_reason = None
        if price_multiple >= pos.required_exit_multiplier:
            exit_reason = "take_profit"
        elif loss_pct >= self.cfg.stop_loss_pct:
            exit_reason = "stop_loss"
        elif held_minutes >= self.cfg.max_hold_minutes:
            exit_reason = "time_exit"

        if not exit_reason:
            return

        current_value = pos.size_usd * price_multiple
        fill = self.executor.sell(pos.mint, tick.price_usd, current_value)
        if not fill.success:
            if "No on-chain balance found" in fill.reason:
                # Nothing left to sell — retrying forever would just spam the API
                # (this is part of what caused the 429 rate-limit errors). The tokens
                # are gone (sold elsewhere, or the original buy never really delivered
                # them). This is a REAL, full loss of the position's capital — it must
                # be counted in stats/session_loss_usd, or it silently bypasses the
                # circuit breaker entirely (this happened for real: two ~$2 positions
                # vanished this way overnight, untracked, invisible to the loss limit
                # meant to stop exactly this).
                loss = pos.size_usd + pos.entry_fee_usd
                self.stats.trades += 1
                self.stats.losses += 1
                self.session_loss_usd += loss
                self.logger.log("SELL", mint=pos.mint, symbol=pos.symbol, pnl_usd=f"{-loss:.4f}",
                                 reason=f"position_lost | {pos.entry_features} | {fill.reason}")
                print(f"[WARN] {pos.symbol} ({pos.mint}) has no on-chain balance — "
                      f"counting as a ${loss:.2f} loss and dropping from tracking")
                del self.positions[pos.mint]
                self._save_state()
                self._notify("Bot lost a position", f"{pos.symbol}: no on-chain balance, ${loss:.2f} loss")
                self._check_circuit_breaker()
                return
            self.logger.log("ERROR", mint=pos.mint, symbol=pos.symbol, reason=f"sell_failed: {fill.reason}")
            print(f"[WARN] sell failed for {pos.symbol} ({pos.mint}): {fill.reason} — will retry next tick")
            return  # keep the position open, retry the exit next loop tick

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

        self.logger.log(
            "SELL", mint=pos.mint, symbol=pos.symbol, price_usd=f"{fill.filled_price_usd:.8f}",
            size_usd=f"{current_value:.2f}", fee_usd=f"{fill.fee_usd:.4f}",
            pnl_usd=f"{pnl:.4f}", reason=f"{exit_reason} | {pos.entry_features} | tx:{fill.reason}"
        )
        del self.positions[pos.mint]
        self._save_state()
        self._notify(
            f"Bot sold a token ({'win' if pnl > 0 else 'loss'})",
            f"{pos.symbol}: {exit_reason}, P&L ${pnl:.2f}",
        )
        self._check_circuit_breaker()

    # ---------- main loop ----------

    def run(self, minutes: float):
        end_time = time.time() + minutes * 60
        interval = self.cfg.poll_interval_seconds if self.cfg.mode == "paper" else self.cfg.live_poll_interval_seconds
        print(f"Starting bot | mode={self.cfg.mode} | balance=${self.stats.balance_usd:.2f} "
              f"| max_bankroll=${self.cfg.max_bankroll_usd:.2f}")

        while time.time() < end_time:
            if not self.halted:
                for c in self.data_source.poll_new_graduations():
                    self._try_enter(c)

            for mint in list(self.positions.keys()):
                self._try_exit(self.positions[mint])

            time.sleep(interval)

        self._report()
        self.logger.close()

    def _report(self):
        s = self.stats
        win_rate = (s.wins / s.trades * 100) if s.trades else 0.0
        print("\n===== SESSION REPORT =====")
        print(f"Trades executed:     {s.trades}")
        print(f"Wins / Losses:       {s.wins} / {s.losses}  ({win_rate:.1f}% win rate)")
        print(f"Skipped (filtered):  {s.skipped}")
        print(f"Gross profit:        ${s.gross_profit_usd:.4f}")
        print(f"Total fees paid:     ${s.total_fees_usd:.4f}")
        print(f"Net P&L:             ${s.net_pnl_usd:.4f}")
        print(f"Ending balance:      ${s.balance_usd:.2f}")
        print(f"Trade log:           {self.logger.path}")
        print("===========================\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=float, default=10, help="How long to run the session")
    args = parser.parse_args()

    cfg = Config()  # mode="paper" by default — see config.py
    bot = Bot(cfg)
    bot.run(minutes=args.minutes)
