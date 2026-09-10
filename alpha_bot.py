"""
alpha_bot.py — real-time signal / copy-trade bot.

    python alpha_bot.py run --minutes 180      # trade session (default cmd)

Signals are PUSHED onto one queue by signal_sources.py:
  * HeliusWalletSource — wss logsSubscribe on watched wallets (sub-second)
  * XStreamSource      — X API v2 filtered stream (needs X_BEARER_TOKEN)
  * WebhookSource       — local HTTP endpoint for any external alerter

Per signal: resolve to a concrete mint -> (fusion: act on first, or wait for N
sources) -> rug_screen -> anti-exit-liquidity check -> size -> buy -> manage
with a two-stage trailing stop + rug tripwire + "exit when the source wallets
have all sold".

Safe default: mode="dry_run" in alpha_config.py (real signals, simulated
fills, no key). Live places real swaps and prompts for a confirmation phrase.
Sub-second execution removes YOUR lag; it does not create an edge. Nothing here
guarantees profit — see the README.
"""

import argparse
import csv
import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass, field
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

from alpha_config import AlphaConfig
from signal_sources import SignalBus, Signal
from executors import PaperExecutor, LiveExecutor
from rug_screen import RugScreen, OnChainClient
from newcoin_config import NewCoinConfig

CONFIRM_PHRASE = "copy trade for real"
_STABLE = {"So11111111111111111111111111111111111111112",
           "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"}


def _f(x, d=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return d


@dataclass
class Position:
    mint: str
    symbol: str
    trigger: str                 # which source(s) fired
    entry_price: float
    size_usd: float
    entry_time: float
    entry_fee_usd: float
    stop_price: float
    trail_pct: float
    tp1_done: bool
    peak_price: float
    last_price: float
    entry_liquidity_usd: float
    source_wallets: list = field(default_factory=list)
    last_meta_at: float = 0.0
    last_liq: float = 0.0


@dataclass
class SessionStats:
    balance_usd: float
    starting_balance_usd: float
    signals: int = 0
    resolved: int = 0
    rug_blocked: int = 0
    late: int = 0
    entered: int = 0
    trades: int = 0
    wins: int = 0
    losses: int = 0
    gross_profit_usd: float = 0.0
    total_fees_usd: float = 0.0

    @property
    def net_pnl_usd(self):
        return self.balance_usd - self.starting_balance_usd


class TradeLogger:
    COLS = ["timestamp", "event", "mint", "symbol", "trigger", "price_usd", "size_usd",
            "fee_usd", "pnl_usd", "rug", "latency_s", "reason"]

    def __init__(self, path):
        self.path = path
        new = not os.path.exists(path)
        self.f = open(path, "a", newline="")
        self.w = csv.writer(self.f)
        if new:
            self.w.writerow(self.COLS)

    def log(self, event, mint="", symbol="", trigger="", price_usd="", size_usd="", fee_usd="",
            pnl_usd="", rug="", latency_s="", reason=""):
        self.w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), event, mint, symbol, trigger,
                         price_usd, size_usd, fee_usd, pnl_usd, rug, latency_s, reason])
        self.f.flush()

    def close(self):
        self.f.close()


class AlphaBot:
    def __init__(self, cfg: AlphaConfig):
        self.cfg = cfg
        if cfg.starting_balance_usd > cfg.max_bankroll_usd:
            raise ValueError("starting_balance_usd exceeds max_bankroll_usd. Refusing to start.")

        self.session = requests.Session()
        self.jup_key = os.environ.get("JUPITER_API_KEY")
        self._price_cache: dict[str, tuple] = {}

        self.oc: Optional[OnChainClient] = None
        # RugScreen/OnChainClient read rug_* thresholds + endpoints from this. The
        # newcoin defaults are tuned for brand-new micro-caps; a copy bot follows
        # wallets into ESTABLISHED coins too, where CEX/LP wallets legitimately
        # hold big chunks and "dev prior mints" is meaningless. Loosen the
        # concentration / dev hard-fails; keep the ones that still mean "rug":
        # live mint/freeze authority, unlocked LP, thin liquidity, liquidity
        # draining, no sell route.
        self.rug_cfg = NewCoinConfig()
        self.rug_cfg.rug_max_top1_holder_pct = 60.0
        self.rug_cfg.rug_max_top10_holder_pct = 92.0
        self.rug_cfg.rug_max_dev_prior_mints = 10_000
        self.rug_cfg.rug_min_score_to_trade = 50.0
        self.rug_cfg.rug_caution_score = 35.0
        self.rug_cfg.rug_warn_min_holders = 0
        if cfg.mode == "live":
            self._confirm_live()
            print("=" * 60)
            print("LIVE MODE — real swaps, real money.")
            print("=" * 60)
            self.executor = LiveExecutor(cfg)
            self.oc = OnChainClient(self.rug_cfg)
        elif cfg.mode == "dry_run":
            self.executor = PaperExecutor(cfg)
            self.oc = OnChainClient(self.rug_cfg)
        else:  # paper
            self.executor = PaperExecutor(cfg)
        self.screen = RugScreen(self.rug_cfg, self.oc)

        self.bus = SignalBus(cfg, get_price=self._price)
        self.stats = SessionStats(cfg.starting_balance_usd, cfg.starting_balance_usd)
        self.positions: dict[str, Position] = {}
        self._pending: dict[str, list] = {}       # mint -> [Signal, ...] for confirm mode
        self._recent_signal_at: dict[str, float] = {}
        self._cooldown_until: dict[str, float] = {}
        self.session_loss_usd = 0.0
        self.new_positions_this_hour = 0
        self.hour_start = time.time()
        self.trades_today = 0
        self.day_start = time.time()
        self.halted = False
        self._last_manage = 0.0

        log_path = cfg.trade_log_path if cfg.mode == "live" else cfg.dry_run_log_path
        self.logger = TradeLogger(log_path)
        self._state_file = cfg.state_path
        if cfg.mode == "live" and os.path.exists(self._state_file):
            self._load_state()

    # ---------- infra ----------

    def _confirm_live(self):
        print('\nmode="live" — real swaps with the SOLANA_PRIVATE_KEY wallet.')
        if input(f'Type exactly "{CONFIRM_PHRASE}": ').strip() != CONFIRM_PHRASE:
            raise SystemExit("phrase not matched — aborting.")

    def _jup_headers(self):
        return {"x-api-key": self.jup_key} if self.jup_key else {}

    def _price(self, mint: str) -> Optional[float]:
        c = self._price_cache.get(mint)
        if c and time.time() - c[1] < 8:
            return c[0]
        try:
            r = self.session.get(self.cfg.jupiter_price_base_url, params={"ids": mint},
                                 headers=self._jup_headers(), timeout=8)
            r.raise_for_status()
            data = r.json()
            node = data.get(mint) or (data.get("data") or {}).get(mint)
            p = float(node["usdPrice"])
            self._price_cache[mint] = (p, time.time())
            return p
        except Exception:
            return None

    def _token_info(self, mint: str) -> Optional[dict]:
        try:
            r = self.session.get(self.cfg.jupiter_token_info_base_url, params={"query": mint},
                                 headers=self._jup_headers(), timeout=10)
            r.raise_for_status()
            rows = r.json()
            rows = rows.get("data", rows) if isinstance(rows, dict) else rows
            return rows or None
        except Exception:
            return None

    def _notify(self, title, msg):
        if self.cfg.mode != "live":
            return
        try:
            subprocess.run(["osascript", "-e",
                            f'display notification {json.dumps(msg)} with title {json.dumps(title)} sound name "Glass"'],
                           check=False, timeout=5)
        except Exception:
            pass

    def _save_state(self):
        if self.cfg.mode != "live":
            return
        json.dump({
            "positions": {m: asdict(p) for m, p in self.positions.items()},
            "balance_usd": self.stats.balance_usd,
            "starting_balance_usd": self.stats.starting_balance_usd,
            "trades": self.stats.trades, "wins": self.stats.wins, "losses": self.stats.losses,
            "gross_profit_usd": self.stats.gross_profit_usd, "total_fees_usd": self.stats.total_fees_usd,
            "session_loss_usd": self.session_loss_usd, "cooldown_until": self._cooldown_until,
        }, open(self._state_file, "w"), indent=2)

    def _load_state(self):
        s = json.load(open(self._state_file))
        self.positions = {m: Position(**p) for m, p in s.get("positions", {}).items()}
        for k in ("balance_usd", "starting_balance_usd", "trades", "wins", "losses",
                  "gross_profit_usd", "total_fees_usd"):
            setattr(self.stats, k, s.get(k, getattr(self.stats, k)))
        self.session_loss_usd = s.get("session_loss_usd", 0.0)
        self._cooldown_until = s.get("cooldown_until", {})
        if self.positions:
            print(f"[bot] resumed {len(self.positions)} position(s)")

    # ---------- risk ----------

    def _roll_windows(self):
        now = time.time()
        if now - self.hour_start > 3600:
            self.hour_start, self.new_positions_this_hour = now, 0
        if now - self.day_start > 86400:
            self.day_start, self.trades_today = now, 0

    def _capacity_reason(self) -> Optional[str]:
        self._roll_windows()
        if len(self.positions) >= self.cfg.max_concurrent_positions:
            return "max_concurrent"
        if self.new_positions_this_hour >= self.cfg.max_new_positions_per_hour:
            return "hourly_cap"
        if self.trades_today >= self.cfg.max_trades_per_day:
            return "daily_cap"
        return None

    def _check_circuit_breaker(self):
        if self.cfg.mode == "live" and self.session_loss_usd >= self.cfg.daily_max_loss_usd:
            self.halted = True
            self.logger.log("HALT", reason=f"daily_max_loss -${self.session_loss_usd:.2f}")
            print(f"[HALT] -${self.session_loss_usd:.2f} >= -${self.cfg.daily_max_loss_usd:.2f}")

    # ---------- resolution ----------

    def _resolve(self, sig: Signal) -> Optional[tuple[str, str, dict]]:
        """(mint, symbol, info_row) or None."""
        cfg = self.cfg
        rows = None
        mint = sig.mint
        if mint:
            rows = self._token_info(mint)
            row = next((x for x in (rows or []) if x.get("id") == mint), (rows or [{}])[0] if rows else None)
        else:
            if not sig.raw_ref:
                return None
            rows = self._token_info(sig.raw_ref)
            cands = [x for x in (rows or []) if str(x.get("symbol", "")).upper() == sig.raw_ref.upper()]
            cands.sort(key=lambda x: _f(x.get("liquidity")), reverse=True)
            row = cands[0] if cands else None
            if row:
                mint = row.get("id")
        if not row or not mint or mint in _STABLE:
            return None
        liq = _f(row.get("liquidity"))
        if liq < cfg.resolve_min_liquidity_usd:
            self.logger.log("SKIP", mint=mint, symbol=row.get("symbol", "?"), trigger=sig.source,
                            reason=f"thin (${liq:.0f} < ${cfg.resolve_min_liquidity_usd:.0f})")
            return None
        if cfg.resolve_max_holders and int(_f(row.get("holderCount"))) > cfg.resolve_max_holders:
            return None
        if cfg.resolve_max_token_age_minutes:
            created = row.get("createdAt") or (row.get("firstPool") or {}).get("createdAt")
            age_min = _age_min(created)
            if age_min is not None and age_min > cfg.resolve_max_token_age_minutes:
                self.logger.log("SKIP", mint=mint, symbol=row.get("symbol", "?"),
                                trigger=sig.source, reason=f"too_old ({age_min:.0f}m)")
                return None
        return mint, row.get("symbol", "?"), row

    # ---------- signal handling ----------

    def _on_signal(self, sig: Signal):
        self.stats.signals += 1
        if self.halted:
            return
        now = time.time()

        r = self._resolve(sig)
        if not r:
            return
        mint, symbol, row = r
        self.stats.resolved += 1

        if now < self._cooldown_until.get(mint, 0) or mint in self.positions:
            return
        last = self._recent_signal_at.get(mint, 0)
        self._recent_signal_at[mint] = now

        # fusion
        if self.cfg.fusion_mode == "confirm":
            buf = [s for s in self._pending.get(mint, []) if now - s.ts <= self.cfg.confirm_window_seconds]
            buf.append(sig)
            self._pending[mint] = buf
            srcs = {s.source for s in buf}
            if len(srcs) < self.cfg.confirm_n:
                return
            trigger = "+".join(sorted(srcs))
            fire_sig = buf[0]
        else:
            if now - last < self.cfg.signal_dedupe_seconds:
                return
            trigger = sig.source
            fire_sig = sig

        self._try_enter(mint, symbol, row, fire_sig, trigger)

    def _try_enter(self, mint, symbol, row, sig: Signal, trigger: str):
        cfg = self.cfg
        cap = self._capacity_reason()
        if cap:
            self.logger.log("SKIP", mint=mint, symbol=symbol, trigger=trigger, reason=cap)
            return

        price = self._price(mint) or _f(row.get("usdPrice"))
        if not price:
            self.logger.log("SKIP", mint=mint, symbol=symbol, trigger=trigger, reason="no_price")
            return

        # anti-exit-liquidity (on-chain copies only)
        if sig.source == "onchain" and sig.insider_price_usd > 0:
            prem = (price / sig.insider_price_usd - 1) * 100
            if prem > cfg.max_entry_premium_over_insider_pct:
                self.stats.late += 1
                self.logger.log("SKIP", mint=mint, symbol=symbol, trigger=trigger,
                                reason=f"already_ran (+{prem:.0f}% over insider)")
                return

        verdict = self.screen.screen(_RowCandidate(row, mint, symbol), price_usd=price)
        if cfg.require_rug_pass and verdict.verdict == "RUG_RISK":
            self.stats.rug_blocked += 1
            self.logger.log("SKIP", mint=mint, symbol=symbol, trigger=trigger, rug="RUG_RISK",
                            reason="rug: " + verdict.summary())
            return

        size = cfg.max_position_usd * (0.5 if verdict.verdict == "CAUTION" else 1.0)
        size = min(size, self.stats.balance_usd)
        if size < cfg.min_trade_usd:
            self.logger.log("SKIP", mint=mint, symbol=symbol, trigger=trigger, reason="balance_low")
            return

        latency = time.time() - sig.ts
        fill = self.executor.buy(mint, price, size)
        if not fill.success:
            self.logger.log("SKIP", mint=mint, symbol=symbol, trigger=trigger,
                            reason=f"buy_failed: {fill.reason}")
            return

        pos = Position(
            mint=mint, symbol=symbol, trigger=trigger, entry_price=fill.filled_price_usd,
            size_usd=size, entry_time=time.time(), entry_fee_usd=fill.fee_usd,
            stop_price=fill.filled_price_usd * (1 - cfg.hard_stop_loss_pct / 100),
            trail_pct=cfg.tight_trail_pct, tp1_done=False,
            peak_price=fill.filled_price_usd, last_price=fill.filled_price_usd,
            entry_liquidity_usd=_f(row.get("liquidity")),
            source_wallets=[sig.actor] if sig.source == "onchain" else [],
            last_liq=_f(row.get("liquidity")),
        )
        self.positions[mint] = pos
        self.stats.balance_usd -= size + fill.fee_usd
        self.stats.total_fees_usd += fill.fee_usd
        self.stats.entered += 1
        self.new_positions_this_hour += 1
        self.trades_today += 1
        self._pending.pop(mint, None)
        self._save_state()
        self.logger.log("BUY", mint=mint, symbol=symbol, trigger=trigger,
                        price_usd=f"{fill.filled_price_usd:.10f}", size_usd=f"{size:.2f}",
                        fee_usd=f"{fill.fee_usd:.4f}", rug=verdict.verdict,
                        latency_s=f"{latency:.2f}",
                        reason=f"{sig.note} | stop {pos.stop_price:.10f}")
        self._notify("alpha_bot bought", f"{symbol} ${size:.2f} via {trigger} ({latency:.1f}s)")

    # ---------- position management ----------

    def _sources_all_exited(self, pos: Position) -> bool:
        if not (self.cfg.exit_when_sources_exit and pos.source_wallets and self.oc):
            return False
        for w in pos.source_wallets:
            res = self.oc._rpc("getTokenAccountsByOwner", [w, {"mint": pos.mint}, {"encoding": "jsonParsed"}])
            try:
                bal = sum(int(a["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"])
                          for a in (res or {}).get("value", []))
                if bal > 0:
                    return False
            except Exception:
                return False
        return True

    def _manage(self, pos: Position):
        price = self._price(pos.mint)
        if not price:
            return
        liq = None
        if self.oc and time.time() - pos.last_meta_at >= 25:
            rows = self._token_info(pos.mint) or []
            row = next((x for x in rows if x.get("id") == pos.mint), rows[0] if rows else {})
            liq = _f(row.get("liquidity")) or None
            pos.last_meta_at = time.time()
            if liq:
                pos.last_liq = liq
        elif pos.last_liq:
            liq = pos.last_liq

        prev = pos.last_price
        pos.last_price = price
        pos.peak_price = max(pos.peak_price, price)
        mult = price / pos.entry_price if pos.entry_price else 1.0
        held_h = (time.time() - pos.entry_time) / 3600
        tick_move = (price / prev - 1) * 100 if prev else 0.0
        peak_dd = (price / pos.peak_price - 1) * 100

        reason = None
        if tick_move <= self.cfg.exit_on_single_tick_crash_pct:
            reason = f"tripwire_crash ({tick_move:.0f}%/tick)"
        elif liq is not None and pos.entry_liquidity_usd > 0 and \
                (liq / pos.entry_liquidity_usd - 1) * 100 <= self.cfg.exit_on_liq_drop_pct:
            reason = f"tripwire_liq ({(liq / pos.entry_liquidity_usd - 1) * 100:.0f}% vs entry)"
        elif self._sources_all_exited(pos):
            reason = "sources_exited"
        elif not pos.tp1_done and mult >= self.cfg.tp1_multiple:
            pos.tp1_done = True
            pos.stop_price = max(pos.stop_price, pos.entry_price * (1 + self.cfg.breakeven_buffer_pct / 100))
            pos.trail_pct = self.cfg.runner_trail_pct
            self.logger.log("SCALE", mint=pos.mint, symbol=pos.symbol, trigger=pos.trigger,
                            price_usd=f"{price:.10f}", reason=f"tp1 {mult:.2f}x -> stop breakeven")
            self._save_state()

        if reason is None:
            if mult >= self.cfg.final_tp_multiple:
                reason = f"take_profit ({mult:.2f}x)"
            elif price <= pos.stop_price:
                reason = "breakeven_stop" if pos.tp1_done else f"hard_stop ({(mult - 1) * 100:.0f}%)"
            elif mult > 1.0 and peak_dd <= -pos.trail_pct:
                reason = f"trailing_stop ({peak_dd:.0f}% off peak)"
            elif held_h >= self.cfg.max_hold_hours:
                reason = f"time_exit ({held_h:.1f}h)"
        if not reason:
            return

        current_value = pos.size_usd * mult
        fill = self.executor.sell(pos.mint, price, current_value)
        if not fill.success:
            if "No on-chain balance" in fill.reason:
                loss = pos.size_usd + pos.entry_fee_usd
                self.stats.trades += 1
                self.stats.losses += 1
                self.session_loss_usd += loss
                self.logger.log("SELL", mint=pos.mint, symbol=pos.symbol, trigger=pos.trigger,
                                pnl_usd=f"{-loss:.4f}", reason=f"position_lost | {fill.reason}")
                del self.positions[pos.mint]
                self._cooldown_until[pos.mint] = time.time() + self.cfg.reentry_cooldown_minutes * 60
                self._save_state()
                self._check_circuit_breaker()
            else:
                self.logger.log("ERROR", mint=pos.mint, symbol=pos.symbol,
                                reason=f"sell_failed: {fill.reason}")
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
        self.logger.log("SELL", mint=pos.mint, symbol=pos.symbol, trigger=pos.trigger,
                        price_usd=f"{fill.filled_price_usd:.10f}", size_usd=f"{current_value:.2f}",
                        fee_usd=f"{fill.fee_usd:.4f}", pnl_usd=f"{pnl:.4f}", reason=reason)
        del self.positions[pos.mint]
        self._cooldown_until[pos.mint] = time.time() + self.cfg.reentry_cooldown_minutes * 60
        self._save_state()
        self._notify(f"alpha_bot sold ({'win' if pnl > 0 else 'loss'})", f"{pos.symbol} {reason} ${pnl:.2f}")
        self._check_circuit_breaker()

    # ---------- loop ----------

    def run(self, minutes: float):
        end = time.time() + minutes * 60
        self.bus.start()
        print(f"alpha_bot | mode={self.cfg.mode} | balance ${self.stats.balance_usd:.2f} "
              f"| fusion={self.cfg.fusion_mode} | running {minutes:.0f}m")
        while time.time() < end:
            try:
                sig = self.bus.get(timeout=self.cfg.manage_interval_seconds)
                if sig:
                    self._on_signal(sig)
                if time.time() - self._last_manage >= self.cfg.manage_interval_seconds:
                    for m in list(self.positions.keys()):
                        self._manage(self.positions[m])
                    self._last_manage = time.time()
            except KeyboardInterrupt:
                print("\n[bot] interrupted")
                break
            except Exception as e:
                print(f"[bot] loop error (continuing): {e}")
        self.bus.stop()
        self._report()
        self.logger.close()

    def _report(self):
        s = self.stats
        wr = (s.wins / s.trades * 100) if s.trades else 0.0
        print("\n===== ALPHA SESSION REPORT =====")
        print(f"Signals in:          {s.signals}")
        print(f"Resolved to a mint:  {s.resolved}")
        print(f"Rug-blocked:         {s.rug_blocked}")
        print(f"Too late (ran up):   {s.late}")
        print(f"Entered:             {s.entered}")
        print(f"Trades closed:       {s.trades}  ({s.wins}W / {s.losses}L, {wr:.0f}%)")
        print(f"Gross profit:        ${s.gross_profit_usd:.4f}")
        print(f"Total fees:          ${s.total_fees_usd:.4f}")
        print(f"Net P&L:             ${s.net_pnl_usd:.4f}")
        print(f"Ending balance:      ${s.balance_usd:.2f}")
        print(f"Open positions:      {len(self.positions)}")
        print(f"Log:                 {self.logger.path}")
        print("================================\n")


class _RowCandidate:
    """Adapts a Jupiter token-info row to the attribute shape RugScreen expects."""

    def __init__(self, row: dict, mint: str, symbol: str):
        audit = row.get("audit") or {}
        s5 = row.get("stats5m") or {}
        self.mint = mint
        self.symbol = symbol
        self.liquidity_usd = _f(row.get("liquidity"))
        self.holder_count = int(_f(row.get("holderCount")))
        self.top_wallet_pct = _f(audit.get("topHoldersPercentage"), 100.0)
        self.renounced = bool(audit.get("mintAuthorityDisabled")) and bool(audit.get("freezeAuthorityDisabled"))
        self.lp_locked = bool(audit.get("lpBurned", True)) if "lpBurned" in audit else True
        self.organic_score = _f(row.get("organicScore"))
        self.dev_mints = int(_f(audit.get("devMints"), 0))
        self.num_organic_buyers_5m = int(_f(s5.get("numOrganicBuyers")))
        self.price_change_5m_pct = _f(s5.get("priceChange"))
        self.price_change_1h_pct = _f((row.get("stats1h") or {}).get("priceChange"))


def _age_min(created) -> Optional[float]:
    if not created:
        return None
    try:
        if isinstance(created, (int, float)):
            return (time.time() - float(created)) / 60
        import datetime as _dt
        return (time.time() - _dt.datetime.fromisoformat(str(created).replace("Z", "+00:00")).timestamp()) / 60
    except Exception:
        return None


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="real-time signal / copy-trade bot")
    sub = p.add_subparsers(dest="cmd")
    pr = sub.add_parser("run")
    pr.add_argument("--minutes", type=float, default=180)
    p.add_argument("--minutes", type=float, default=180, help=argparse.SUPPRESS)
    a = p.parse_args()
    AlphaBot(AlphaConfig()).run(minutes=getattr(a, "minutes", 180))
