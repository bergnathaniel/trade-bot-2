"""
DCA bot — buys a fixed $ amount of SOL on a fixed schedule and holds. No
selling, no prediction. Over a long enough uptrend this makes money; over a
flat/down stretch it loses (SOL is down ~45% over the last year). Backtest it
first:  python dca_backtest.py

    python dca_bot.py run --minutes 1440      # one buy check per interval
    python dca_bot.py status

Safe by default: mode="paper" in DCAConfig (simulated fills, no key). "live"
buys real SOL through Jupiter with the SOLANA_PRIVATE_KEY wallet and makes you
type a confirmation phrase. Independent of bot.py / insider_bot.py — its own
log (dca_log.csv), state (dca_state.json), and cap.
"""
import argparse, csv, json, os, subprocess, time
from dataclasses import dataclass
from dotenv import load_dotenv
load_dotenv()

import requests
from executors import PaperExecutor, LiveExecutor

CONFIRM = "buy real sol on a schedule"
SOL_MINT = "So11111111111111111111111111111111111111112"


@dataclass
class DCAConfig:
    mode: str = "paper"                # "paper" | "live"
    asset_mint: str = SOL_MINT
    usd_per_buy: float = 25.0
    interval_hours: float = 168.0       # weekly
    max_total_invested_usd: float = 500.0   # hard cap; bot stops buying past this
    # fee model (mirrors config.py so paper P&L is realistic)
    dex_swap_fee_pct: float = 0.0025
    platform_fee_flat_usd: float = 0.02
    network_fee_usd: float = 0.01
    est_slippage_pct: float = 0.004
    max_allowed_slippage_pct: float = 0.02
    jupiter_price_base_url: str = "https://api.jup.ag/price/v3"
    jupiter_swap_base_url: str = "https://api.jup.ag/swap/v2"
    sol_mint: str = SOL_MINT
    poll_seconds: float = 30.0


class DCABot:
    def __init__(self, cfg: DCAConfig):
        self.cfg = cfg
        self.state_file = "dca_state.json"
        self.state = {"coins": 0.0, "invested_usd": 0.0, "buys": 0,
                      "last_buy_ts": 0.0, "fees_usd": 0.0}
        if os.path.exists(self.state_file):
            self.state.update(json.load(open(self.state_file)))
        new = not os.path.exists("dca_log.csv")
        self.f = open("dca_log.csv", "a", newline="")
        self.w = csv.writer(self.f)
        if new:
            self.w.writerow(["timestamp", "event", "sol_price_usd", "usd_in",
                             "coins_bought", "fee_usd", "total_coins",
                             "total_invested", "portfolio_value", "reason"])
        if cfg.mode == "live":
            self._confirm()
            self.executor = LiveExecutor(cfg)
        else:
            self.executor = PaperExecutor(cfg)

    def _confirm(self):
        print("LIVE — this buys real SOL with real money on a schedule.")
        print(f'Type exactly:  {CONFIRM}')
        if input("> ").strip() != CONFIRM:
            raise SystemExit("phrase mismatch, aborting")

    def _save(self):
        json.dump(self.state, open(self.state_file, "w"), indent=2)

    def _price(self) -> float | None:
        try:
            r = requests.get(self.cfg.jupiter_price_base_url,
                             params={"ids": self.cfg.asset_mint}, timeout=10)
            r.raise_for_status()
            d = r.json()
            node = d.get(self.cfg.asset_mint) or (d.get("data") or {}).get(self.cfg.asset_mint)
            return float(node["usdPrice"]) if node and node.get("usdPrice") else None
        except Exception as e:
            print(f"[dca] price fetch failed: {e}")
            return None

    def _notify(self, msg):
        if self.cfg.mode != "live":
            return
        try:
            subprocess.run(["osascript", "-e",
                            f'display notification {json.dumps(msg)} with title "DCA bot" sound name "Glass"'],
                           check=False, timeout=5)
        except Exception:
            pass

    def status(self):
        price = self._price()
        s = self.state
        inv = s["invested_usd"]
        avg = (inv / s['coins']) if s['coins'] else 0
        print("\n=== DCA STATUS ===")
        print(f"Mode:              {self.cfg.mode}")
        print(f"Buys made:         {s['buys']}")
        print(f"SOL accumulated:   {s['coins']:.4f}")
        print(f"Total invested:    ${inv:.2f}   (cap ${self.cfg.max_total_invested_usd:.2f})")
        print(f"Fees paid:         ${s['fees_usd']:.2f}")
        print(f"Avg cost / SOL:    ${avg:.2f}")
        if price:
            val = s["coins"] * price
            print(f"SOL price now:     ${price:.2f}")
            print(f"Portfolio value:   ${val:.2f}")
            if inv:
                print(f"Profit / loss:     ${val - inv:+.2f}   ({(val/inv-1)*100:+.1f}%)")
        else:
            print("SOL price now:     (price feed unavailable right now — rerun in a minute)")
        print("==================\n")

    def _buy(self):
        price = self._price()
        if not price:
            return
        if self.state["invested_usd"] + self.cfg.usd_per_buy > self.cfg.max_total_invested_usd + 1e-6:
            self.w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), "SKIP", f"{price:.4f}",
                             "", "", "", f"{self.state['coins']:.6f}",
                             f"{self.state['invested_usd']:.2f}", "", "cap_reached"])
            self.f.flush()
            print("[dca] investment cap reached — no more buys")
            return
        fill = self.executor.buy(self.cfg.asset_mint, price, self.cfg.usd_per_buy)
        if not fill.success:
            self.w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), "ERROR", f"{price:.4f}",
                             "", "", "", "", "", "", f"buy_failed: {fill.reason}"])
            self.f.flush()
            return
        coins = fill.amount_usd / fill.filled_price_usd
        self.state["coins"] += coins
        self.state["invested_usd"] += fill.amount_usd
        self.state["fees_usd"] += fill.fee_usd
        self.state["buys"] += 1
        self.state["last_buy_ts"] = time.time()
        self._save()
        val = self.state["coins"] * price
        self.w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), "BUY", f"{price:.4f}",
                         f"{fill.amount_usd:.2f}", f"{coins:.6f}", f"{fill.fee_usd:.4f}",
                         f"{self.state['coins']:.6f}", f"{self.state['invested_usd']:.2f}",
                         f"{val:.2f}", fill.reason or ""])
        self.f.flush()
        print(f"[dca] bought ${fill.amount_usd:.2f} SOL @ ${price:.2f}  "
              f"(+{coins:.4f} SOL, total {self.state['coins']:.4f})")
        self._notify(f"Bought ${fill.amount_usd:.0f} of SOL @ ${price:.0f}")

    def run(self, minutes: float):
        interval = self.cfg.interval_hours * 3600
        end = time.time() + minutes * 60
        due = self.state["last_buy_ts"] + interval
        print(f"[dca] mode={self.cfg.mode} | ${self.cfg.usd_per_buy:g} every "
              f"{self.cfg.interval_hours:g}h | next buy "
              f"{'now' if time.time() >= due else time.strftime('%Y-%m-%d %H:%M', time.localtime(due))}")
        while time.time() < end:
            if time.time() >= self.state["last_buy_ts"] + interval:
                self._buy()
            time.sleep(self.cfg.poll_seconds)
        self.status()
        self.f.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("run"); pr.add_argument("--minutes", type=float, default=1440)
    sub.add_parser("status")
    a = ap.parse_args()
    bot = DCABot(DCAConfig())
    if a.cmd == "run":
        bot.run(minutes=a.minutes)
    else:
        bot.status()
