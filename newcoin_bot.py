"""
newcoin_bot.py — meme-coin momentum bot.

    python newcoin_bot.py run --minutes 240      # trade session (default cmd)
    python newcoin_bot.py train                  # fit the optional scorer on your logs

Pipeline per coin:
  1. discovery.LiveDiscovery pulls Jupiter's top-traded feed (+ optional
     pump.fun migrations). Candidate must fall inside the universe BAND
     (liquidity / market-cap / volume / age / holders / 24h-change).
  2. regime gate — no new entries while SOL is dumping on the hour or meme
     breadth is weak.
  3. rug_screen.RugScreen — SAFE / CAUTION / RUG_RISK (+ itemised reasons).
  4. observe price for observation_seconds, then movement_study.classify_setup
     must return "breakout" or "pullback".
  5. edge gate — assumed target move must clear ~3x the round-trip cost.
  6. optional newcoin_model — P(win) gate once >= model_min_samples closed trades.
  7. buy. Exit: two-stage trailing stop (tight until +tp1, then stop to
     breakeven + wide trail), hard take-profit, time exit, and a rug tripwire
     (liquidity collapse / one-tick crash / holder concentration spike).

Safe by default: mode="dry_run" in newcoin_config.py. Live mode places real
swaps and makes you type a confirmation phrase. Nothing here guarantees
profit — see the README's "Realistic expectations".
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

from newcoin_config import NewCoinConfig
from discovery import MockDiscovery, LiveDiscovery, MemeCandidate
from executors import PaperExecutor, LiveExecutor
from rug_screen import RugScreen, OnChainClient, RugVerdict
from movement_study import MovementTracker, study, classify_setup
from newcoin_model import LogisticModel, features_to_str, train_from_log

CONFIRM_PHRASE = "trade meme coins for real"


@dataclass
class Position:
    mint: str
    symbol: str
    setup: str
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
    entry_top1_pct: float
    rug_score: float
    features_str: str = ""
    last_meta_at: float = 0.0
    last_liquidity_usd: float = 0.0


@dataclass
class Observation:
    candidate: MemeCandidate
    verdict: RugVerdict
    tracker: MovementTracker
    started_at: float
    deadline_at: float
    last_meta_at: float = 0.0
    last_info: dict = field(default_factory=dict)


@dataclass
class SessionStats:
    balance_usd: float
    starting_balance_usd: float
    trades: int = 0
    wins: int = 0
    losses: int = 0
    gross_profit_usd: float = 0.0
    total_fees_usd: float = 0.0
    seen: int = 0
    out_of_band: int = 0
    screened: int = 0
    rug_risk: int = 0
    caution: int = 0
    no_setup: int = 0
    regime_blocked: int = 0
    entered: int = 0

    @property
    def net_pnl_usd(self) -> float:
        return self.balance_usd - self.starting_balance_usd


class TradeLogger:
    COLUMNS = ["timestamp", "event", "mint", "symbol", "setup", "price_usd", "size_usd",
               "fee_usd", "pnl_usd", "rug_verdict", "movement", "features", "reason"]

    def __init__(self, path: str):
        self.path = path
        is_new = not os.path.exists(path)
        self.f = open(path, "a", newline="")
        self.w = csv.writer(self.f)
        if is_new:
            self.w.writerow(self.COLUMNS)

    def log(self, event, mint="", symbol="", setup="", price_usd="", size_usd="", fee_usd="",
            pnl_usd="", rug_verdict="", movement="", features="", reason=""):
        self.w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), event, mint, symbol, setup,
                         price_usd, size_usd, fee_usd, pnl_usd, rug_verdict, movement,
                         features, reason])
        self.f.flush()

    def close(self):
        self.f.close()


class NewCoinBot:
    def __init__(self, cfg: NewCoinConfig):
        self.cfg = cfg
        if cfg.starting_balance_usd > cfg.max_bankroll_usd:
            raise ValueError(
                f"starting_balance_usd ({cfg.starting_balance_usd}) exceeds "
                f"max_bankroll_usd ({cfg.max_bankroll_usd}). Refusing to start."
            )

        self.oc: Optional[OnChainClient] = None
        if cfg.mode == "live":
            self._confirm_live_mode()
            print("=" * 60)
            print("LIVE MODE — real swaps, real money.")
            print(f"Bankroll cap ${cfg.max_bankroll_usd:.2f} | per-trade ${cfg.max_position_usd:.2f} "
                  f"| circuit breaker -${cfg.daily_max_loss_usd:.2f}")
            print("=" * 60)
            self.discovery = LiveDiscovery(cfg)
            self.executor = LiveExecutor(cfg)
            self.oc = OnChainClient(cfg)
        elif cfg.mode == "dry_run":
            self.discovery = LiveDiscovery(cfg)
            self.executor = PaperExecutor(cfg)
            self.oc = OnChainClient(cfg)
        else:  # paper
            self.discovery = MockDiscovery(cfg)
            self.executor = PaperExecutor(cfg)

        self.screen = RugScreen(cfg, self.oc)
        self.model: Optional[LogisticModel] = None
        if cfg.use_model:
            self.model = LogisticModel.load(cfg.model_path)
            if self.model and self.model.n_train >= cfg.model_min_samples:
                print(f"[model] loaded — trained on {self.model.n_train} trades, "
                      f"in-sample acc {self.model.in_sample_acc:.2f} (gate active)")
            elif self.model:
                print(f"[model] only {self.model.n_train} trades (< {cfg.model_min_samples}) "
                      f"— gate OFF, rules only")

        self.stats = SessionStats(cfg.starting_balance_usd, cfg.starting_balance_usd)
        self.positions: dict[str, Position] = {}
        self.observing: dict[str, Observation] = {}
        self._cooldown_until: dict[str, float] = {}
        self.session_loss_usd = 0.0
        self.new_positions_this_hour = 0
        self.hour_window_start = time.time()
        self.trades_today = 0
        self.day_start = time.time()
        self.halted = False
        self._regime = {"ok": True}
        self._regime_at = 0.0

        log_path = cfg.trade_log_path if cfg.mode == "live" else cfg.dry_run_log_path
        self.logger = TradeLogger(log_path)
        self._state_file = cfg.state_path
        if cfg.mode == "live":
            self._load_state()

    # ---------- live confirmation + state ----------

    def _confirm_live_mode(self):
        print("\nmode=\"live\" — this places REAL swaps with REAL funds from the "
              "SOLANA_PRIVATE_KEY wallet (shared with bot.py / insider_bot.py).")
        if input(f'Type exactly "{CONFIRM_PHRASE}" to proceed: ').strip() != CONFIRM_PHRASE:
            raise SystemExit("Confirmation phrase not matched — aborting before any trade.")

    def _save_state(self):
        if self.cfg.mode != "live":
            return
        state = {
            "positions": {m: asdict(p) for m, p in self.positions.items()},
            "balance_usd": self.stats.balance_usd,
            "starting_balance_usd": self.stats.starting_balance_usd,
            "trades": self.stats.trades, "wins": self.stats.wins, "losses": self.stats.losses,
            "gross_profit_usd": self.stats.gross_profit_usd,
            "total_fees_usd": self.stats.total_fees_usd,
            "session_loss_usd": self.session_loss_usd,
            "cooldown_until": self._cooldown_until,
        }
        with open(self._state_file, "w") as f:
            json.dump(state, f, indent=2)

    def _load_state(self):
        if not os.path.exists(self._state_file):
            return
        with open(self._state_file) as f:
            s = json.load(f)
        self.positions = {m: Position(**p) for m, p in s.get("positions", {}).items()}
        self.stats.balance_usd = s.get("balance_usd", self.stats.balance_usd)
        self.stats.starting_balance_usd = s.get("starting_balance_usd", self.stats.starting_balance_usd)
        for k in ("trades", "wins", "losses", "gross_profit_usd", "total_fees_usd"):
            setattr(self.stats, k, s.get(k, getattr(self.stats, k)))
        self.session_loss_usd = s.get("session_loss_usd", 0.0)
        self._cooldown_until = s.get("cooldown_until", {})
        if self.positions:
            print(f"[bot] resumed {len(self.positions)} open position(s) from {self._state_file}")

    def _notify(self, title: str, message: str):
        if self.cfg.mode != "live":
            return
        try:
            script = f'display notification {json.dumps(message)} with title {json.dumps(title)} sound name "Glass"'
            subprocess.run(["osascript", "-e", script], check=False, timeout=5)
        except Exception:
            pass

    # ---------- helpers ----------

    def _price(self, mint: str) -> Optional[float]:
        return self.discovery.get_price(mint)

    def _info(self, mint: str) -> dict:
        try:
            return self.discovery.token_info(mint) or {}
        except Exception:
            return {}

    def _ctx_from(self, cand: MemeCandidate, info: dict) -> dict:
        """5m/1h/24h context for classify_setup — prefer fresh info, fall back
        to the candidate snapshot."""
        return {
            "chg5m_pct": info.get("chg5m_pct", cand.price_change_5m_pct),
            "chg1h_pct": info.get("chg1h_pct", cand.price_change_1h_pct),
            "chg24h_pct": info.get("chg24h_pct", cand.price_change_24h_pct),
            "num_buys_5m": info.get("num_buys_5m", cand.num_buys_5m),
            "num_sells_5m": info.get("num_sells_5m", cand.num_sells_5m),
            "liq_change_1h_pct": info.get("liq_change_1h_pct", cand.liquidity_change_1h_pct),
        }

    def _regime_ok(self) -> dict:
        if time.time() - self._regime_at > 60:
            try:
                self._regime = self.discovery.market_regime()
            except Exception as e:
                print(f"[bot] regime check failed ({e}) — assuming OK")
                self._regime = {"ok": True, "sol_1h_pct": 0.0, "breadth_green": 0.5}
            self._regime_at = time.time()
        return self._regime

    def _check_circuit_breaker(self):
        if self.cfg.mode != "live":
            return
        if self.session_loss_usd >= self.cfg.daily_max_loss_usd:
            self.halted = True
            self.logger.log("HALT", reason=f"daily_max_loss -${self.session_loss_usd:.2f}")
            print(f"[HALT] circuit breaker: -${self.session_loss_usd:.2f} >= "
                  f"-${self.cfg.daily_max_loss_usd:.2f}")

    def _roll_windows(self):
        now = time.time()
        if now - self.hour_window_start > 3600:
            self.hour_window_start = now
            self.new_positions_this_hour = 0
        if now - self.day_start > 86400:
            self.day_start = now
            self.trades_today = 0

    def _capacity_reason(self) -> Optional[str]:
        self._roll_windows()
        if len(self.positions) >= self.cfg.max_concurrent_positions:
            return "max_concurrent_positions"
        if self.new_positions_this_hour >= self.cfg.max_new_positions_per_hour:
            return "hourly_rate_limit"
        if self.trades_today >= self.cfg.max_trades_per_day:
            return "daily_trade_cap"
        return None

    # ---------- band filter ----------

    def _band_reason(self, c: MemeCandidate) -> Optional[str]:
        cfg = self.cfg
        if c.liquidity_usd < cfg.band_min_liquidity_usd:
            return f"liq_below_band (${c.liquidity_usd:.0f})"
        if c.liquidity_usd > cfg.band_max_liquidity_usd:
            return f"liq_above_band (${c.liquidity_usd:.0f})"
        if c.market_cap_usd is not None:
            if c.market_cap_usd < cfg.band_min_market_cap_usd:
                return f"mcap_below_band (${c.market_cap_usd:.0f})"
            if c.market_cap_usd > cfg.band_max_market_cap_usd:
                return f"mcap_above_band (${c.market_cap_usd:.0f})"
        if c.volume_24h_usd is not None and c.volume_24h_usd < cfg.band_min_volume_24h_usd:
            return f"vol_below_band (${c.volume_24h_usd:.0f})"
        if c.age_minutes is not None:
            if c.age_minutes < cfg.band_min_age_minutes:
                return f"too_new ({c.age_minutes:.0f}m)"
            if c.age_minutes > cfg.band_max_age_days * 1440:
                return f"too_old ({c.age_minutes / 1440:.1f}d)"
        if c.holder_count < cfg.band_min_holders:
            return f"too_few_holders ({c.holder_count})"
        if c.price_change_24h_pct < cfg.band_min_24h_change_pct:
            return f"knife (24h {c.price_change_24h_pct:.0f}%)"
        if c.price_change_24h_pct > cfg.band_max_24h_change_pct:
            return f"blowoff (24h {c.price_change_24h_pct:.0f}%)"
        return None

    # ---------- stage 1: band + rug screen ----------

    def _consider_new(self, c: MemeCandidate):
        self.stats.seen += 1
        if c.mint in self.positions or c.mint in self.observing:
            return
        cd = self._cooldown_until.get(c.mint, 0.0)
        if time.time() < cd:
            return

        band = self._band_reason(c)
        if band:
            self.stats.out_of_band += 1
            return  # out-of-band is the common case; don't spam the log

        self.stats.screened += 1
        price = self._price(c.mint) or c.price_usd or 0.0
        info = self._info(c.mint) if self.oc else {}
        verdict = self.screen.screen(c, price_usd=price, info=info)
        self.logger.log("SCREEN", mint=c.mint, symbol=c.symbol, rug_verdict=verdict.verdict,
                        reason=verdict.summary())

        if verdict.verdict == "RUG_RISK":
            self.stats.rug_risk += 1
            self.logger.log("SKIP", mint=c.mint, symbol=c.symbol, rug_verdict="RUG_RISK",
                            reason="rug_screen: " + verdict.summary())
            return
        if verdict.verdict == "CAUTION":
            self.stats.caution += 1
            if not self.cfg.trade_on_caution:
                self.logger.log("SKIP", mint=c.mint, symbol=c.symbol, rug_verdict="CAUTION",
                                reason="caution disabled")
                return

        now = time.time()
        tr = MovementTracker(c.mint, c.symbol)
        p = self._price(c.mint)
        if p:
            tr.add(p, info.get("holder_count"), info.get("liquidity_usd"))
        self.observing[c.mint] = Observation(
            candidate=c, verdict=verdict, tracker=tr, started_at=now,
            deadline_at=now + self.cfg.observation_seconds, last_meta_at=now, last_info=info,
        )

    # ---------- stage 2: observe, classify, decide ----------

    def _poll_observations(self):
        for mint, obs in list(self.observing.items()):
            p = self._price(mint)
            if p:
                h = lq = None
                if time.time() - obs.last_meta_at >= self.cfg.meta_refresh_seconds:
                    obs.last_info = self._info(mint) or obs.last_info
                    obs.last_meta_at = time.time()
                    h = obs.last_info.get("holder_count")
                    lq = obs.last_info.get("liquidity_usd")
                obs.tracker.add(p, h, lq)
            if time.time() >= obs.deadline_at:
                self._evaluate(mint, obs)

    def _feature_dict(self, c: MemeCandidate, verdict: RugVerdict, snap, setup: str, info: dict) -> dict:
        feats = {
            "rug_score": round(verdict.score, 2),
            "liq_usd": round(info.get("liquidity_usd", c.liquidity_usd) or 0.0, 2),
            "mcap_usd": round(info.get("market_cap_usd") or c.market_cap_usd or 0.0, 2),
            "vol24_usd": round(info.get("volume_24h_usd") or c.volume_24h_usd or 0.0, 2),
            "holders": int(info.get("holder_count", c.holder_count) or 0),
            "top1_pct": round(info.get("top_wallet_pct", c.top_wallet_pct) or 0.0, 2),
            "organic_score": round(info.get("organic_score", c.organic_score) or 0.0, 2),
            "chg5m_pct": round(info.get("chg5m_pct", c.price_change_5m_pct) or 0.0, 2),
            "chg1h_pct": round(info.get("chg1h_pct", c.price_change_1h_pct) or 0.0, 2),
            "chg24h_pct": round(info.get("chg24h_pct", c.price_change_24h_pct) or 0.0, 2),
            "organic_buyers_5m": int(info.get("num_organic_buyers_5m", c.num_organic_buyers_5m) or 0),
            "buys_5m": int(info.get("num_buys_5m", c.num_buys_5m) or 0),
            "sells_5m": int(info.get("num_sells_5m", c.num_sells_5m) or 0),
            "dev_mints": int(c.dev_mints),
            "setup_breakout": 1 if setup == "breakout" else 0,
            "setup_pullback": 1 if setup == "pullback" else 0,
        }
        feats.update(snap.as_features())
        return feats

    def _evaluate(self, mint: str, obs: Observation):
        self.observing.pop(mint, None)
        c, verdict, tr = obs.candidate, obs.verdict, obs.tracker
        info = obs.last_info or self._info(mint)

        snap = study(tr)
        if snap is None or snap.n_ticks < self.cfg.min_observation_ticks:
            self.logger.log("SKIP", mint=mint, symbol=c.symbol, rug_verdict=verdict.verdict,
                            reason=f"no_price_data ({tr.n} ticks / {tr.observed_seconds:.0f}s)")
            return

        ctx = self._ctx_from(c, info)
        setup, mv_reason = classify_setup(snap, ctx, self.cfg)
        if not setup:
            self.stats.no_setup += 1
            self.logger.log("SKIP", mint=mint, symbol=c.symbol, rug_verdict=verdict.verdict,
                            movement=mv_reason, reason="setup: " + mv_reason)
            return

        if not self._regime_ok().get("ok", True):
            self.stats.regime_blocked += 1
            r = self._regime
            self.logger.log("SKIP", mint=mint, symbol=c.symbol, rug_verdict=verdict.verdict,
                            movement=mv_reason,
                            reason=f"regime: SOL 1h {r.get('sol_1h_pct', 0):.1f}% "
                                   f"breadth {r.get('breadth_green', 0):.2f}")
            return

        last_liq = tr.last_liquidity() or info.get("liquidity_usd")
        if last_liq is not None and last_liq < self.cfg.rug_min_liquidity_usd:
            self.logger.log("SKIP", mint=mint, symbol=c.symbol, rug_verdict=verdict.verdict,
                            movement=mv_reason, reason=f"liquidity_gone (${last_liq:.0f})")
            return

        cap = self._capacity_reason()
        if cap:
            self.logger.log("SKIP", mint=mint, symbol=c.symbol, reason=cap)
            return

        size = self.cfg.max_position_usd * (0.5 if verdict.verdict == "CAUTION" else 1.0)
        size = min(size, self.stats.balance_usd)
        if size < self.cfg.min_trade_usd:
            self.logger.log("SKIP", mint=mint, symbol=c.symbol, reason="balance_too_low")
            return
        if not self.cfg.edge_ok(size):
            self.logger.log("SKIP", mint=mint, symbol=c.symbol,
                            reason=f"edge_below_cost (target {self.cfg.assumed_target_move_pct:.0f}% vs "
                                   f"{self.cfg.round_trip_cost_usd(size) / size * 100:.1f}% cost)")
            return

        feats = self._feature_dict(c, verdict, snap, setup, info)
        if self.model and self.model.n_train >= self.cfg.model_min_samples:
            p_win = self.model.predict_proba(feats)
            feats["model_p"] = round(p_win, 4)
            if p_win < self.cfg.model_min_prob:
                self.logger.log("SKIP", mint=mint, symbol=c.symbol, setup=setup,
                                rug_verdict=verdict.verdict, movement=mv_reason,
                                features=features_to_str(feats),
                                reason=f"model_veto p={p_win:.2f}")
                return

        price = self._price(mint)
        if not price:
            self.logger.log("SKIP", mint=mint, symbol=c.symbol, reason="no_price_at_entry")
            return

        fill = self.executor.buy(mint, price, size)
        if not fill.success:
            self.logger.log("SKIP", mint=mint, symbol=c.symbol, reason=f"buy_failed: {fill.reason}")
            return

        pos = Position(
            mint=mint, symbol=c.symbol, setup=setup, entry_price=fill.filled_price_usd,
            size_usd=size, entry_time=time.time(), entry_fee_usd=fill.fee_usd,
            stop_price=fill.filled_price_usd * (1 - self.cfg.hard_stop_loss_pct / 100),
            trail_pct=self.cfg.tight_trail_pct, tp1_done=False,
            peak_price=fill.filled_price_usd, last_price=fill.filled_price_usd,
            entry_liquidity_usd=last_liq or c.liquidity_usd,
            entry_top1_pct=info.get("top_wallet_pct", c.top_wallet_pct) or 0.0,
            rug_score=verdict.score, features_str=features_to_str(feats),
            last_liquidity_usd=last_liq or c.liquidity_usd,
        )
        self.positions[mint] = pos
        self.stats.balance_usd -= size + fill.fee_usd
        self.stats.total_fees_usd += fill.fee_usd
        self.stats.entered += 1
        self.new_positions_this_hour += 1
        self.trades_today += 1
        self._save_state()
        self.logger.log("BUY", mint=mint, symbol=c.symbol, setup=setup,
                        price_usd=f"{fill.filled_price_usd:.10f}", size_usd=f"{size:.2f}",
                        fee_usd=f"{fill.fee_usd:.4f}", rug_verdict=verdict.verdict,
                        movement=mv_reason, features=features_to_str(feats),
                        reason=f"{setup} | stop {pos.stop_price:.10f} | {verdict.summary()}")
        self._notify("newcoin_bot bought", f"{c.symbol} ${size:.2f} {setup} rug={verdict.verdict}")

    # ---------- stage 3: manage a position ----------

    def _manage_position(self, pos: Position):
        price = self._price(pos.mint)
        if not price:
            return
        liq = top1 = None
        if self.oc and time.time() - pos.last_meta_at >= self.cfg.meta_refresh_seconds:
            info = self._info(pos.mint)
            pos.last_meta_at = time.time()
            liq = info.get("liquidity_usd")
            top1 = info.get("top_wallet_pct")
            if liq:
                pos.last_liquidity_usd = liq
        elif pos.last_liquidity_usd:
            liq = pos.last_liquidity_usd

        prev = pos.last_price
        pos.last_price = price
        pos.peak_price = max(pos.peak_price, price)
        mult = price / pos.entry_price if pos.entry_price else 1.0
        held_h = (time.time() - pos.entry_time) / 3600
        tick_move_pct = (price / prev - 1) * 100 if prev else 0.0
        peak_dd_pct = (price / pos.peak_price - 1) * 100

        reason = None
        if tick_move_pct <= self.cfg.exit_on_single_tick_crash_pct:
            reason = f"rug_tripwire_crash ({tick_move_pct:.0f}% in one poll)"
        elif liq is not None and pos.entry_liquidity_usd > 0 and \
                (liq / pos.entry_liquidity_usd - 1) * 100 <= self.cfg.exit_on_liq_drop_pct:
            reason = f"rug_tripwire_liq ({(liq / pos.entry_liquidity_usd - 1) * 100:.0f}% vs entry)"
        elif top1 is not None and pos.entry_top1_pct > 0 and \
                top1 - pos.entry_top1_pct >= self.cfg.exit_on_top1_spike_pct:
            reason = f"rug_tripwire_concentration (top1 {pos.entry_top1_pct:.0f}%->{top1:.0f}%)"

        if reason is None:
            # two-stage trailing stop
            if not pos.tp1_done and mult >= self.cfg.tp1_multiple:
                pos.tp1_done = True
                pos.stop_price = max(pos.stop_price,
                                     pos.entry_price * (1 + self.cfg.breakeven_buffer_pct / 100))
                pos.trail_pct = self.cfg.runner_trail_pct
                self.logger.log("SCALE", mint=pos.mint, symbol=pos.symbol, setup=pos.setup,
                                price_usd=f"{price:.10f}",
                                reason=f"tp1 hit ({mult:.2f}x) — stop->breakeven, trail {pos.trail_pct:.0f}%")
                self._save_state()

            if mult >= self.cfg.final_tp_multiple:
                reason = f"take_profit ({mult:.2f}x)"
            elif price <= pos.stop_price:
                reason = "breakeven_stop" if pos.tp1_done else f"hard_stop ({(mult - 1) * 100:.0f}%)"
            elif mult > 1.0 and peak_dd_pct <= -pos.trail_pct:
                reason = f"trailing_stop ({peak_dd_pct:.0f}% off peak)"
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
                self.logger.log("SELL", mint=pos.mint, symbol=pos.symbol, setup=pos.setup,
                                pnl_usd=f"{-loss:.4f}", features=pos.features_str,
                                reason=f"position_lost | {fill.reason}")
                del self.positions[pos.mint]
                self._cooldown_until[pos.mint] = time.time() + self.cfg.reentry_cooldown_minutes * 60
                self._save_state()
                self._check_circuit_breaker()
                return
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

        self.logger.log("SELL", mint=pos.mint, symbol=pos.symbol, setup=pos.setup,
                        price_usd=f"{fill.filled_price_usd:.10f}", size_usd=f"{current_value:.2f}",
                        fee_usd=f"{fill.fee_usd:.4f}", pnl_usd=f"{pnl:.4f}",
                        features=pos.features_str, reason=reason)
        del self.positions[pos.mint]
        self._cooldown_until[pos.mint] = time.time() + self.cfg.reentry_cooldown_minutes * 60
        self._save_state()
        self._notify(f"newcoin_bot sold ({'win' if pnl > 0 else 'loss'})",
                     f"{pos.symbol} {reason} P&L ${pnl:.2f}")
        self._check_circuit_breaker()

    # ---------- main loop ----------

    def run(self, minutes: float):
        end = time.time() + minutes * 60
        interval = (self.cfg.poll_interval_seconds if self.cfg.mode == "paper"
                    else self.cfg.live_poll_interval_seconds)
        print(f"newcoin_bot | mode={self.cfg.mode} | balance ${self.stats.balance_usd:.2f} "
              f"| bankroll cap ${self.cfg.max_bankroll_usd:.2f} | universe={','.join(self.cfg.universe)} "
              f"| running {minutes:.0f}m")
        while time.time() < end:
            try:
                self._regime_ok()  # refresh the 60s regime cache
                if not self.halted and not self._capacity_reason():
                    for c in self.discovery.poll():
                        self._consider_new(c)
                elif not self.halted:
                    self.discovery.poll()  # keep the feed / caches warm
                self._poll_observations()
                for mint in list(self.positions.keys()):
                    self._manage_position(self.positions[mint])
            except KeyboardInterrupt:
                print("\n[bot] interrupted — reporting")
                break
            except Exception as e:
                print(f"[bot] loop error (continuing): {e}")
            time.sleep(interval)
        self._report()
        self.logger.close()
        if hasattr(self.discovery, "close"):
            self.discovery.close()

    def _report(self):
        s = self.stats
        wr = (s.wins / s.trades * 100) if s.trades else 0.0
        print("\n===== NEWCOIN SESSION REPORT =====")
        print(f"Seen (feed):         {s.seen}")
        print(f"Out of band:         {s.out_of_band}")
        print(f"Screened:            {s.screened}  (rug_risk {s.rug_risk} | caution {s.caution})")
        print(f"No setup:            {s.no_setup}")
        print(f"Regime-blocked:      {s.regime_blocked}")
        print(f"Entered:             {s.entered}")
        print(f"Trades closed:       {s.trades}   ({s.wins}W / {s.losses}L, {wr:.0f}% win rate)")
        print(f"Gross profit:        ${s.gross_profit_usd:.4f}")
        print(f"Total fees paid:     ${s.total_fees_usd:.4f}")
        print(f"Net P&L:             ${s.net_pnl_usd:.4f}")
        print(f"Ending balance:      ${s.balance_usd:.2f}")
        print(f"Open positions:      {len(self.positions)}")
        print(f"Log:                 {self.logger.path}")
        print("==================================\n")


def _cmd_train(cfg: NewCoinConfig):
    for path in (cfg.trade_log_path, cfg.dry_run_log_path):
        if os.path.exists(path):
            res = train_from_log(path, cfg.model_path)
            print(f"\n[train] source={path}")
            print(f"        closed trades: {res['samples']}  ({res['wins']}W / {res['losses']}L)")
            if res.get("trained"):
                print(f"        model written: {res['model_path']}  in-sample acc {res['in_sample_acc']}")
                print(f"        gate activates once >= {cfg.model_min_samples} closed trades exist")
            else:
                print(f"        not trained: {res.get('note', 'insufficient data')}")
            if res["samples"]:
                return
    print("[train] no trade log found yet — run some dry-run sessions first")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="meme-coin momentum bot")
    sub = parser.add_subparsers(dest="cmd")
    p_run = sub.add_parser("run", help="run a trading session")
    p_run.add_argument("--minutes", type=float, default=240)
    sub.add_parser("train", help="fit the optional scorer on the trade log")
    parser.add_argument("--minutes", type=float, default=240, help=argparse.SUPPRESS)
    args = parser.parse_args()

    cfg = NewCoinConfig()
    if args.cmd == "train":
        _cmd_train(cfg)
    else:
        NewCoinBot(cfg).run(minutes=getattr(args, "minutes", 240))
