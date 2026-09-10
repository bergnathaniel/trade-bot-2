"""
20-day momentum bot (mom_20).

The rule, once a day:
  * if today's price is HIGHER than it was 20 days ago  -> be in the asset
  * if it's LOWER                                        -> be in cash (USDC)
  * otherwise do nothing
That's the whole strategy. It rode the crypto uptrends and stepped aside for
the worst of the drops. It does NOT make you rich fast — few trades a year,
held for weeks/months, and it still had ~-70% drawdowns. Backtest it:
    python classic_strats.py SOL-USD

    python momentum_bot.py status
    python momentum_bot.py check                  # one decision now, then exit
    python momentum_bot.py run --minutes 1440     # checks once per interval

Default mode is "paper": it just tracks what it *would* do, no money, no key.
"live" swaps USDC<->SOL through Jupiter with the SOLANA_PRIVATE_KEY wallet
and makes you type a confirmation phrase. Run paper for weeks first.

Live execution notes (fixed 2026-08-27, matched to executors.py which has
actually placed real swaps):
  * every Jupiter call now sends the x-api-key header (Jupiter rejects
    keyless calls on all tiers now);
  * a swap is only believed once its signature CONFIRMS on-chain — Jupiter
    returning "Success" is not enough, it has lied before;
  * the bot's position/units are updated from the ACTUAL on-chain fill
    amounts, and ONLY after a confirmed fill. A failed swap leaves the
    recorded position untouched instead of desyncing it from the wallet;
  * the SOL->USDC leg leaves a gas reserve so the wallet can still pay fees.
"""
import argparse, base64, csv, json, os, time, datetime as dt
from dataclasses import dataclass
from dotenv import load_dotenv
load_dotenv()
import requests

CONFIRM = "move my money in and out of sol on this signal"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
USDC_DECIMALS = 6
SOL = "So11111111111111111111111111111111111111112"
LAMPORTS_PER_SOL = 1_000_000_000
GAS_RESERVE_LAMPORTS = 15_000_000     # ~0.015 SOL kept back for rent + priority fees


@dataclass
class MomentumConfig:
    mode: str = "paper"
    symbol: str = "SOL-USD"        # Coinbase product for the price history
    asset_mint: str = SOL
    lookback_days: int = 20
    start_cash_usd: float = 100.0  # paper starting cash (live: display baseline only)
    fee_pct: float = 0.003
    max_slippage_bps: int = 100
    coinbase: str = "https://api.exchange.coinbase.com/products/{}/candles"
    jup_price: str = "https://api.jup.ag/price/v3"
    jup_swap: str = "https://api.jup.ag/swap/v2"


class MomentumBot:
    def __init__(self, cfg: MomentumConfig):
        self.cfg = cfg
        # live keeps its own state/log so it can never be desynced by a paper run
        self.sf = "momentum_live_state.json" if cfg.mode == "live" else "momentum_state.json"
        log_path = "momentum_live_log.csv" if cfg.mode == "live" else "momentum_log.csv"
        self.state = {"position": "cash", "units": 0.0,
                      "cash_usd": cfg.start_cash_usd, "entry_price": 0.0,
                      "last_check": 0.0, "switches": 0}
        if os.path.exists(self.sf):
            self.state.update(json.load(open(self.sf)))
        new = not os.path.exists(log_path)
        self.f = open(log_path, "a", newline="")
        self.w = csv.writer(self.f)
        if new:
            self.w.writerow(["timestamp", "action", "price", "price_20d_ago",
                             "signal", "position", "value_usd", "note"])

        self.session = requests.Session()
        self.jup_key = os.environ.get("JUPITER_API_KEY")

        if cfg.mode == "live":
            print("LIVE — this moves real money between USDC and SOL.")
            print(f'Type exactly:  {CONFIRM}')
            if input("> ").strip() != CONFIRM:
                raise SystemExit("phrase mismatch")
            self.rpc = os.environ.get("HELIUS_RPC_URL")
            if not self.rpc:
                raise SystemExit("HELIUS_RPC_URL is not set in .env")
            if not self.jup_key:
                print("[momentum] WARNING: JUPITER_API_KEY not set — Jupiter's "
                      "keyless tier is heavily rate-limited and may reject swaps. "
                      "Get a free key at https://portal.jup.ag")
            from wallet import load_keypair
            self.kp = load_keypair()
            self.pubkey = str(self.kp.pubkey())
            lamports = self._rpc("getBalance", [self.pubkey])["value"]
            sol_bal = lamports / LAMPORTS_PER_SOL
            usdc_bal = self._token_balance_raw(USDC) / 10 ** USDC_DECIMALS
            print(f"wallet: {self.pubkey}")
            print(f"balance: {sol_bal:.4f} SOL + {usdc_bal:.2f} USDC")
            if lamports <= GAS_RESERVE_LAMPORTS:
                raise SystemExit(
                    f"wallet has only {sol_bal:.4f} SOL — need > "
                    f"{GAS_RESERVE_LAMPORTS / LAMPORTS_PER_SOL:.3f} for gas. Fund it first.")
            # RECONCILE recorded position with what the wallet actually holds,
            # so a stale state file (e.g. copied from a paper run) can't make
            # the bot think it's in cash while the wallet is in SOL.
            tradable_sol = (lamports - GAS_RESERVE_LAMPORTS) / LAMPORTS_PER_SOL
            px = self._live_price() or 0.0
            sol_value = tradable_sol * px
            real_pos = "asset" if sol_value >= max(usdc_bal, 1.0) else "cash"
            self._reconcile_from_wallet(verbose=True)

    # ---------- persistence ----------
    def _save(self):
        json.dump(self.state, open(self.sf, "w"), indent=2)

    # ---------- market data ----------
    def _history(self):
        """~30 daily closes for the configured symbol, oldest first."""
        end = dt.datetime.now(dt.timezone.utc)
        r = self.session.get(self.cfg.coinbase.format(self.cfg.symbol),
                             params={"granularity": 86400,
                                     "start": (end - dt.timedelta(days=40)).isoformat(),
                                     "end": end.isoformat()},
                             headers={"User-Agent": "momentum-bot"}, timeout=20)
        r.raise_for_status()
        rows = sorted(r.json())          # [time, low, high, open, close, vol]
        return [c[4] for c in rows]

    def _jup_headers(self):
        return {"x-api-key": self.jup_key} if self.jup_key else {}

    def _live_price(self):
        try:
            d = self.session.get(self.cfg.jup_price, params={"ids": self.cfg.asset_mint},
                                 headers=self._jup_headers(), timeout=10).json()
            n = d.get(self.cfg.asset_mint) or (d.get("data") or {}).get(self.cfg.asset_mint)
            return float(n["usdPrice"]) if n else None
        except Exception:
            return None

    def _value(self, price):
        return self.state["cash_usd"] if self.state["position"] == "cash" \
            else self.state["units"] * price

    # ---------- RPC ----------
    def _rpc(self, method, params):
        resp = self.session.post(self.rpc, json={"jsonrpc": "2.0", "id": 1,
                                 "method": method, "params": params}, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"RPC {method} failed: {data['error']}")
        return data["result"]

    def _token_balance_raw(self, mint):
        """Total raw balance across all this owner's accounts for `mint`."""
        res = self._rpc("getTokenAccountsByOwner",
                        [self.pubkey, {"mint": mint}, {"encoding": "jsonParsed"}])
        total = 0
        for acc in res.get("value", []):
            info = acc["account"]["data"]["parsed"]["info"]["tokenAmount"]
            total += int(info["amount"])
        return total

    def _confirm(self, signature, tries=12, delay=1.0):
        for _ in range(tries):
            res = self._rpc("getSignatureStatuses", [[signature]])
            st = (res.get("value") or [None])[0]
            if st:
                if st.get("err"):
                    return False
                if st.get("confirmationStatus") in ("confirmed", "finalized"):
                    return True
            time.sleep(delay)
        return False

    def _reconcile_from_wallet(self, verbose=False):
        """Set recorded position/amounts from what the wallet actually holds.
        Called at live startup AND before every live decision, so a missed
        confirmation or an outside transfer can't leave the bot desynced."""
        lamports = self._rpc("getBalance", [self.pubkey])["value"]
        usdc_bal = self._token_balance_raw(USDC) / 10 ** USDC_DECIMALS
        tradable_sol = max(lamports - GAS_RESERVE_LAMPORTS, 0) / LAMPORTS_PER_SOL
        px = self._live_price() or 0.0
        real_pos = "asset" if tradable_sol * px >= max(usdc_bal, 1.0) else "cash"
        if verbose and real_pos != self.state["position"]:
            print(f"[momentum] reconciling '{self.state['position']}' -> "
                  f"'{real_pos}' from wallet contents")
        self.state["position"] = real_pos
        if real_pos == "asset":
            self.state["units"], self.state["cash_usd"] = lamports / LAMPORTS_PER_SOL, 0.0
        else:
            self.state["units"], self.state["cash_usd"] = 0.0, usdc_bal
        self._save()

    # ---------- live swap ----------
    def _live_swap(self, ins, outs):
        """Swap the WHOLE balance of `ins` into `outs`. Returns dict with the
        confirmed on-chain signature and actual in/out raw amounts. Raises on
        any failure (caller must not touch position state if this raises)."""
        from solders.transaction import VersionedTransaction

        if ins == SOL:
            lamports = self._rpc("getBalance", [self.pubkey])["value"]
            amount = lamports - GAS_RESERVE_LAMPORTS
            if amount <= 0:
                raise RuntimeError(
                    f"SOL balance {lamports / LAMPORTS_PER_SOL:.6f} at/under gas reserve")
        else:
            amount = self._token_balance_raw(ins)
            if amount <= 0:
                raise RuntimeError(f"balance of {ins} is zero — nothing to swap")

        order = self.session.get(f"{self.cfg.jup_swap}/order", params={
            "inputMint": ins, "outputMint": outs, "amount": amount,
            "taker": self.pubkey, "slippageBps": self.cfg.max_slippage_bps},
            headers=self._jup_headers(), timeout=15).json()
        if not order.get("transaction"):
            raise RuntimeError(
                f"Jupiter could not build a swap: {order.get('errorMessage') or order}")

        unsigned = VersionedTransaction.from_bytes(base64.b64decode(order["transaction"]))
        signed = VersionedTransaction(unsigned.message, [self.kp])

        ex = self.session.post(f"{self.cfg.jup_swap}/execute", json={
            "signedTransaction": base64.b64encode(bytes(signed)).decode(),
            "requestId": order["requestId"]},
            headers={**self._jup_headers(), "Content-Type": "application/json"},
            timeout=30).json()

        if ex.get("status") != "Success":
            raise RuntimeError(f"Jupiter execute did not succeed: {ex}")
        sig = ex.get("signature")
        if not sig or not self._confirm(sig):
            raise RuntimeError(
                f"swap reported success but never confirmed on-chain (signature {sig})")

        return {"signature": sig,
                "in_raw": int(ex.get("totalInputAmount", amount)),
                "out_raw": int(ex["totalOutputAmount"])}

    # ---------- decision ----------
    def decide(self):
        hist = self._history()
        if len(hist) < self.cfg.lookback_days + 1:
            print("not enough price history yet"); return
        price = self._live_price() or hist[-1]
        past = hist[-1 - self.cfg.lookback_days]
        signal = "asset" if price > past else "cash"
        if self.cfg.mode == "live":
            self._reconcile_from_wallet()   # trust the chain, not the last run
        pos = self.state["position"]
        note, action = "", "hold"

        if signal != pos and self.cfg.mode != "live":
            fee = self.cfg.fee_pct
            if signal == "asset":                       # cash -> buy asset
                self.state["units"] = self.state["cash_usd"] * (1 - fee) / price
                self.state["cash_usd"] = 0.0
                self.state["entry_price"] = price
                note = "BUY"
            else:                                        # asset -> sell to cash
                self.state["cash_usd"] = self.state["units"] * price * (1 - fee)
                self.state["units"] = 0.0
                self.state["entry_price"] = 0.0
                note = "SELL"
            self.state["position"] = signal
            self.state["switches"] += 1
            action = signal.upper()

        elif signal != pos and self.cfg.mode == "live":
            try:
                if signal == "asset":                   # USDC -> SOL
                    res = self._live_swap(USDC, self.cfg.asset_mint)
                    self.state["units"] = res["out_raw"] / LAMPORTS_PER_SOL
                    self.state["cash_usd"] = 0.0
                    self.state["entry_price"] = price
                else:                                    # SOL -> USDC
                    res = self._live_swap(self.cfg.asset_mint, USDC)
                    self.state["cash_usd"] = res["out_raw"] / 10 ** USDC_DECIMALS
                    self.state["units"] = 0.0
                    self.state["entry_price"] = 0.0
                self.state["position"] = signal
                self.state["switches"] += 1
                action = signal.upper()
                note = f"LIVE {res['signature']}"
                print(f"[momentum] LIVE {action} confirmed: {res['signature']}")
            except Exception as e:
                action, note = "hold", f"LIVE_SWAP_FAILED: {e}"
                print(f"[momentum] LIVE SWAP FAILED — position left as '{pos}': {e}")

        self.state["last_check"] = time.time()
        self._save()
        self.w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), action,
                         f"{price:.4f}", f"{past:.4f}", signal,
                         self.state["position"], f"{self._value(price):.2f}", note])
        self.f.flush()
        print(f"[momentum] price ${price:.2f} vs 20d-ago ${past:.2f} -> signal={signal} "
              f"| now {self.state['position']} | value ${self._value(price):.2f}")

    # ---------- status ----------
    def status(self):
        try:
            hist = self._history()
            price = self._live_price() or hist[-1]
            past = hist[-1 - self.cfg.lookback_days]
            sig = "asset" if price > past else "cash"
        except Exception:
            price = past = 0; sig = "?"
        s = self.state
        val = self._value(price) if price else s["cash_usd"] + s["units"]
        print("\n=== MOMENTUM STATUS ===")
        print(f"Mode:            {self.cfg.mode}   ({self.cfg.symbol}, {self.cfg.lookback_days}d)")
        print(f"Currently:       {s['position'].upper()}")
        print(f"Price now:       ${price:.2f}   20d ago: ${past:.2f}   -> signal: {sig.upper()}")
        print(f"Switches so far: {s['switches']}")
        print(f"Value:           ${val:.2f}   (started ${self.cfg.start_cash_usd:.2f})")
        if self.cfg.start_cash_usd:
            print(f"P&L:             ${val - self.cfg.start_cash_usd:+.2f} "
                  f"({(val/self.cfg.start_cash_usd-1)*100:+.1f}%)")
        print("=======================\n")

    def run(self, minutes):
        interval = 6 * 3600  # re-check every 6h; signal is daily so this is plenty
        end = time.time() + minutes * 60
        print(f"[momentum] mode={self.cfg.mode} {self.cfg.symbol} {self.cfg.lookback_days}d | "
              f"position={self.state['position']}")
        while time.time() < end:
            try:
                self.decide()
            except Exception as e:
                print(f"[momentum] check failed: {e}")
            time.sleep(min(interval, max(1, end - time.time())))
        self.status()
        self.f.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("run"); pr.add_argument("--minutes", type=float, default=1440)
    pr.add_argument("--live", action="store_true", help="use real money (also needs the confirm phrase)")
    for name in ("status", "check"):
        p = sub.add_parser(name)
        p.add_argument("--live", action="store_true")
    a = ap.parse_args()
    cfg = MomentumConfig(mode="live" if getattr(a, "live", False) else "paper")
    bot = MomentumBot(cfg)
    if a.cmd == "run":
        bot.run(a.minutes)
    elif a.cmd == "check":
        bot.decide()
    else:
        bot.status()
