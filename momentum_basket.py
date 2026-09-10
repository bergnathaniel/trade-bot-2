"""
20-day momentum BASKET — BTC / ETH / SOL, volatility-weighted.

The rule, re-checked on an interval:
  * For each asset: if today's close > its close `lookback_days` ago -> that
    asset is "on", else "off" (its weight goes to cash).
  * Among the "on" assets, weight inversely to recent volatility (calmer asset
    gets more), capped at `max_weight` each, remainder in cash (USDC).
  * Only actually rebalance when some asset's target weight has drifted from
    its current weight by more than `rebalance_threshold` — otherwise hold and
    pay no fees.

This is the one approach in this project that survived honest out-of-sample
testing (see classic_strats.py / strategies-tested memory). It is slow — a
handful of rebalances a year, held for weeks — and it still eats deep
drawdowns. It aims to roughly match buy-and-hold with less pain, not to be
fast money.

    python momentum_basket.py backtest          # ~1-3 yr sim vs equal-weight hold
    python momentum_basket.py status
    python momentum_basket.py check              # one decision now, then exit
    python momentum_basket.py run --minutes 1440

Default mode "paper": tracks what it would do, no money, no key. "live" swaps
USDC<->asset through Jupiter with SOLANA_PRIVATE_KEY and needs a typed
confirmation phrase. Only assets with a Solana `mint` set below trade live —
by default that's SOL only; BTC/ETH are paper/backtest-only unless you add
mints you trust (wrapped BTC/ETH liquidity on Solana is thin; a real exchange
is the better venue for those legs).
"""

import argparse
import csv
import datetime as dt
import json
import os
import statistics
import time
from dataclasses import dataclass, field

import requests
from dotenv import load_dotenv

load_dotenv()

CONFIRM = "rebalance my money on the momentum signal"
USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL = "So11111111111111111111111111111111111111112"

# sym -> Solana mint for LIVE trading (None = paper/backtest only)
ASSET_MINTS = {
    "BTC-USD": None,
    "ETH-USD": None,
    "SOL-USD": SOL,
}

CB = "https://api.exchange.coinbase.com/products/{}/candles"
JUP_PRICE = "https://api.jup.ag/price/v3"
JUP_SWAP = "https://api.jup.ag/swap/v2"


@dataclass
class BasketConfig:
    mode: str = "paper"
    symbols: tuple = ("BTC-USD", "ETH-USD", "SOL-USD")
    lookback_days: int = 20
    vol_lookback_days: int = 20
    max_weight: float = 0.60            # per-asset cap
    rebalance_threshold: float = 0.08   # min weight drift before we trade
    # Whipsaw guard: only flip an asset "on" when it's this % ABOVE its 20d
    # level, "off" when this % BELOW; hold state in the band between. 0 = the
    # raw daily rule (~30 flips/yr/asset). Try 3-6 to cut churn — but that's a
    # tuning knob, validate it in paper, don't trust a fitted value.
    signal_deadband_pct: float = 0.0
    fee_pct: float = 0.003
    max_slippage_bps: int = 100
    start_cash_usd: float = 100.0
    recheck_hours: float = 6.0          # signal is daily; 6h polling is plenty


# ---------------------------------------------------------------- data

def daily_closes(symbol: str, days: int = 320) -> list[float]:
    """Oldest-first daily closes, paging Coinbase's 300-candle cap."""
    out: dict = {}
    end = dt.datetime.now(dt.timezone.utc)
    while len(out) < days:
        start = end - dt.timedelta(days=290)
        r = requests.get(CB.format(symbol), params={
            "granularity": 86400, "start": start.isoformat(), "end": end.isoformat(),
        }, headers={"User-Agent": "momentum-basket"}, timeout=20)
        if r.status_code != 200 or not r.json():
            break
        rows = r.json()
        for t, lo, hi, op, cl, v in rows:
            out[dt.datetime.fromtimestamp(t, dt.timezone.utc).date()] = float(cl)
        oldest = min(x[0] for x in rows)
        ne = dt.datetime.fromtimestamp(oldest, dt.timezone.utc)
        if ne >= end - dt.timedelta(days=1):
            break
        end = ne
    return [p for _, p in sorted(out.items())]


def live_price(mint: str) -> float | None:
    try:
        d = requests.get(JUP_PRICE, params={"ids": mint}, timeout=10).json()
        n = d.get(mint) or (d.get("data") or {}).get(mint)
        return float(n["usdPrice"]) if n else None
    except Exception:
        return None


# ---------------------------------------------------------------- strategy

def _vol(returns: list[float]) -> float:
    return max(statistics.pstdev(returns), 1e-4) if len(returns) >= 2 else 1e-4


def target_weights(hist: dict[str, list[float]], cfg: BasketConfig) -> dict[str, float]:
    """hist: sym -> oldest-first closes ending 'now'. Returns {sym: weight},
    plus '_cash'. Weights sum to 1."""
    raw: dict[str, float] = {}
    band = cfg.signal_deadband_pct / 100.0
    for sym, closes in hist.items():
        if len(closes) < max(cfg.lookback_days, cfg.vol_lookback_days) + 1:
            raw[sym] = 0.0
            continue
        past = closes[-1 - cfg.lookback_days]
        # decisively above its 20d level -> on; within the band or below -> cash
        on = closes[-1] > past * (1 + band)
        rets = [closes[i] / closes[i - 1] - 1 for i in range(-cfg.vol_lookback_days, 0)]
        raw[sym] = (1.0 / _vol(rets)) if on else 0.0

    tot = sum(raw.values())
    if tot <= 0:
        return {**{s: 0.0 for s in hist}, "_cash": 1.0}

    w = {s: raw[s] / tot for s in hist}
    # apply per-asset cap, push the overflow to cash (simple one pass)
    capped = {s: min(v, cfg.max_weight) for s, v in w.items()}
    used = sum(capped.values())
    return {**capped, "_cash": max(0.0, 1.0 - used)}


def current_weights(holdings: dict[str, float], cash_usd: float,
                    prices: dict[str, float]) -> tuple[dict[str, float], float]:
    vals = {s: holdings.get(s, 0.0) * prices[s] for s in prices}
    total = cash_usd + sum(vals.values())
    if total <= 0:
        return {s: 0.0 for s in prices}, 0.0
    return {s: vals[s] / total for s in prices}, total


def needs_rebalance(tgt: dict[str, float], cur: dict[str, float], cfg: BasketConfig) -> bool:
    return any(abs(tgt.get(s, 0.0) - cur.get(s, 0.0)) >= cfg.rebalance_threshold
              for s in cur)


# ---------------------------------------------------------------- bot

class BasketBot:
    def __init__(self, cfg: BasketConfig):
        self.cfg = cfg
        self.sf = "momentum_basket_state.json"
        self.state = {
            "holdings": {s: 0.0 for s in cfg.symbols},
            "cash_usd": cfg.start_cash_usd,
            "rebalances": 0, "last_check": 0.0,
        }
        if os.path.exists(self.sf):
            self.state.update(json.load(open(self.sf)))
        new = not os.path.exists("momentum_basket_log.csv")
        self.f = open("momentum_basket_log.csv", "a", newline="")
        self.w = csv.writer(self.f)
        if new:
            self.w.writerow(["timestamp", "action", "signals", "target_weights",
                             "value_usd", "note"])
        if cfg.mode == "live":
            print("LIVE — this moves real money between USDC and assets.")
            live_syms = [s for s in cfg.symbols if ASSET_MINTS.get(s)]
            print(f"Live-tradable legs: {live_syms or '(none)'}  "
                  f"(others fold into cash)")
            print(f'Type exactly:  {CONFIRM}')
            if input("> ").strip() != CONFIRM:
                raise SystemExit("phrase mismatch")
            from wallet import load_keypair
            self.kp = load_keypair()
            self.pubkey = str(self.kp.pubkey())
            print(f"wallet: {self.pubkey}")

    def _save(self):
        json.dump(self.state, open(self.sf, "w"), indent=2)

    def _hist(self) -> dict[str, list[float]]:
        return {s: daily_closes(s, self.cfg.lookback_days + self.cfg.vol_lookback_days + 5)
                for s in self.cfg.symbols}

    def _prices(self, hist: dict[str, list[float]]) -> dict[str, float]:
        out = {}
        for s in self.cfg.symbols:
            mint = ASSET_MINTS.get(s)
            p = live_price(mint) if mint else None
            out[s] = p or (hist[s][-1] if hist[s] else 0.0)
        return out

    def decide(self):
        hist = self._hist()
        if any(len(v) < self.cfg.lookback_days + 1 for v in hist.values()):
            print("not enough price history yet")
            return
        prices = self._prices(hist)
        tgt = target_weights(hist, self.cfg)

        # in live mode, non-live legs fold into cash
        if self.cfg.mode == "live":
            for s in list(tgt):
                if s != "_cash" and not ASSET_MINTS.get(s):
                    tgt["_cash"] += tgt.pop(s)
                    tgt[s] = 0.0

        cur, total = current_weights(self.state["holdings"], self.state["cash_usd"], prices)
        signals = {s: ("on" if hist[s][-1] > hist[s][-1 - self.cfg.lookback_days] else "off")
                   for s in self.cfg.symbols}

        if total <= 0:
            total = self.state["cash_usd"] + sum(
                self.state["holdings"].get(s, 0) * prices[s] for s in prices)

        note = "hold"
        action = "hold"
        if needs_rebalance(tgt, cur, self.cfg):
            turnover = sum(abs(tgt.get(s, 0.0) - cur.get(s, 0.0)) for s in self.cfg.symbols) * total
            fee_cost = turnover * self.cfg.fee_pct
            new_hold = {}
            for s in self.cfg.symbols:
                tv = tgt.get(s, 0.0) * total
                new_hold[s] = tv / prices[s] if prices[s] > 0 else 0.0
            self.state["holdings"] = new_hold
            self.state["cash_usd"] = max(0.0, tgt["_cash"] * total - fee_cost)
            self.state["rebalances"] += 1
            action = "rebalance"
            note = (f"turnover ${turnover:.2f} fee ${fee_cost:.2f}"
                    if self.cfg.mode != "live"
                    else self._live_rebalance(tgt, total, prices))

        self.state["last_check"] = time.time()
        self._save()
        val = self.state["cash_usd"] + sum(
            self.state["holdings"].get(s, 0) * prices[s] for s in prices)
        self.w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), action,
                         ",".join(f"{s.split('-')[0]}:{signals[s]}" for s in self.cfg.symbols),
                         ",".join(f"{s.split('-')[0]}:{tgt.get(s, 0):.2f}" for s in self.cfg.symbols)
                         + f",CASH:{tgt['_cash']:.2f}",
                         f"{val:.2f}", note])
        self.f.flush()
        print(f"[basket] {action} | " +
              " ".join(f"{s.split('-')[0]}={signals[s]}/{tgt.get(s, 0):.0%}" for s in self.cfg.symbols) +
              f" cash={tgt['_cash']:.0%} | value ${val:.2f}")

    def _live_rebalance(self, tgt, total, prices) -> str:
        """Best-effort: sell everything to USDC, then buy each target leg.
        Simple and robust; the fee model above already assumed full turnover."""
        import base64
        from solders.transaction import VersionedTransaction
        rpc = os.environ["HELIUS_RPC_URL"]

        def rpc_call(m, p):
            return requests.post(rpc, json={"jsonrpc": "2.0", "id": 1, "method": m,
                                            "params": p}, timeout=15).json()["result"]

        def swap(ins, outs, amount):
            if amount <= 0:
                return "skip(0)"
            o = requests.get(f"{JUP_SWAP}/order", params={
                "inputMint": ins, "outputMint": outs, "amount": int(amount),
                "taker": self.pubkey, "slippageBps": self.cfg.max_slippage_bps}, timeout=15).json()
            if not o.get("transaction"):
                return f"order_fail:{o.get('errorMessage')}"
            tx = VersionedTransaction.from_bytes(base64.b64decode(o["transaction"]))
            signed = VersionedTransaction(tx.message, [self.kp])
            e = requests.post(f"{JUP_SWAP}/execute", json={
                "signedTransaction": base64.b64encode(bytes(signed)).decode(),
                "requestId": o["requestId"]}, timeout=30).json()
            return f"{e.get('status')}:{e.get('signature', '')[:10]}"

        results = []
        for s in self.cfg.symbols:
            mint = ASSET_MINTS.get(s)
            if not mint or mint == SOL:
                continue
            accs = rpc_call("getTokenAccountsByOwner",
                            [self.pubkey, {"mint": mint}, {"encoding": "jsonParsed"}])["value"]
            bal = int(accs[0]["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"]) if accs else 0
            if bal > 0:
                results.append(f"{s}->USDC {swap(mint, USDC, bal)}")
        for s in self.cfg.symbols:
            mint = ASSET_MINTS.get(s)
            w = tgt.get(s, 0.0)
            if not mint or w <= 0:
                continue
            # buy from USDC (6 decimals)
            usd_amt = int(w * total * 1e6)
            results.append(f"USDC->{s} {swap(USDC, mint, usd_amt)}")
        return " | ".join(results) or "no_live_legs"

    def status(self):
        try:
            hist = self._hist()
            prices = self._prices(hist)
            tgt = target_weights(hist, self.cfg)
            sig = {s: ("on" if hist[s][-1] > hist[s][-1 - self.cfg.lookback_days] else "off")
                   for s in self.cfg.symbols}
        except Exception as e:
            print(f"status: price fetch failed: {e}")
            return
        val = self.state["cash_usd"] + sum(
            self.state["holdings"].get(s, 0) * prices[s] for s in prices)
        print("\n=== MOMENTUM BASKET STATUS ===")
        print(f"Mode: {self.cfg.mode}  lookback {self.cfg.lookback_days}d  "
              f"vol {self.cfg.vol_lookback_days}d  cap {self.cfg.max_weight:.0%}")
        for s in self.cfg.symbols:
            held = self.state["holdings"].get(s, 0) * prices[s]
            print(f"  {s:<8} signal {sig[s]:<3}  target {tgt.get(s, 0):>4.0%}  "
                  f"held ${held:>8.2f}  (${prices[s]:,.2f})")
        print(f"  {'CASH':<8}                target {tgt['_cash']:>4.0%}  held ${self.state['cash_usd']:>8.2f}")
        print(f"Rebalances: {self.state['rebalances']}")
        print(f"Value: ${val:.2f}  (started ${self.cfg.start_cash_usd:.2f}, "
              f"{(val / self.cfg.start_cash_usd - 1) * 100:+.1f}%)")
        print("==============================\n")

    def run(self, minutes: float):
        end = time.time() + minutes * 60
        interval = self.cfg.recheck_hours * 3600
        print(f"[basket] mode={self.cfg.mode} {list(self.cfg.symbols)} | "
              f"rebalances so far {self.state['rebalances']}")
        while time.time() < end:
            try:
                self.decide()
            except Exception as e:
                print(f"[basket] check failed: {e}")
            time.sleep(min(interval, max(1, end - time.time())))
        self.status()
        self.f.close()


# ---------------------------------------------------------------- backtest

def backtest(cfg: BasketConfig):
    print("fetching daily history…")
    hist = {s: daily_closes(s, 400) for s in cfg.symbols}
    n = min(len(v) for v in hist.values())
    if n < cfg.lookback_days + 40:
        print(f"not enough overlapping history ({n} days)")
        return
    hist = {s: v[-n:] for s, v in hist.items()}
    yrs = n / 365.25
    warm = max(cfg.lookback_days, cfg.vol_lookback_days) + 1

    def curve(strategy_weights) -> tuple[list[float], int, dict]:
        cash, units = 1.0, {s: 0.0 for s in cfg.symbols}
        eq, rebals = [], 0
        time_on = {s: 0 for s in cfg.symbols}
        for i in range(warm, n):
            px = {s: hist[s][i] for s in cfg.symbols}
            sub = {s: hist[s][: i + 1] for s in cfg.symbols}
            tgt = strategy_weights(sub)
            for s in cfg.symbols:
                if tgt.get(s, 0) > 0:
                    time_on[s] += 1
            total = cash + sum(units[s] * px[s] for s in cfg.symbols)
            cur = {s: (units[s] * px[s] / total if total else 0) for s in cfg.symbols}
            if any(abs(tgt.get(s, 0) - cur.get(s, 0)) >= cfg.rebalance_threshold for s in cfg.symbols):
                turnover = sum(abs(tgt.get(s, 0) - cur.get(s, 0)) for s in cfg.symbols) * total
                fee = turnover * cfg.fee_pct
                for s in cfg.symbols:
                    units[s] = tgt.get(s, 0) * total / px[s] if px[s] else 0
                cash = max(0.0, tgt["_cash"] * total - fee)
                rebals += 1
            eq.append(cash + sum(units[s] * px[s] for s in cfg.symbols))
        return eq, rebals, time_on

    def ew_hold(sub):
        return {**{s: 1 / len(cfg.symbols) for s in cfg.symbols}, "_cash": 0.0}

    eq_bkt, rb, ton = curve(lambda sub: target_weights(sub, cfg))
    eq_hold, _, _ = curve(ew_hold)

    def stats(eq):
        tr = eq[-1] / eq[0] - 1
        cagr = (eq[-1] / eq[0]) ** (1 / yrs) - 1
        peak = eq[0]
        mdd = 0.0
        for v in eq:
            peak = max(peak, v)
            mdd = min(mdd, v / peak - 1)
        return tr, cagr, mdd

    trb, cb_, mb = stats(eq_bkt)
    trh, ch_, mh = stats(eq_hold)
    print(f"\n{n} days ({yrs:.1f} yr), {list(cfg.symbols)}\n")
    print(f"{'':<22} {'total':>10} {'CAGR':>9} {'max DD':>9}  extra")
    print("-" * 66)
    print(f"{'momentum basket':<22} {trb * 100:>+9.0f}% {cb_ * 100:>+8.1f}% {mb * 100:>+8.0f}%  "
          f"{rb} rebalances")
    print(f"{'equal-weight hold':<22} {trh * 100:>+9.0f}% {ch_ * 100:>+8.1f}% {mh * 100:>+8.0f}%")
    print("\ntime in market:", "  ".join(
        f"{s.split('-')[0]} {ton[s] / (n - warm) * 100:.0f}%" for s in cfg.symbols))
    print("\nThe basket 'works' only if it ~matches hold's return with a smaller max DD,")
    print("or beats it. A short window (1-3 yr) is not proof — run it in paper too.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    pr = sub.add_parser("run")
    pr.add_argument("--minutes", type=float, default=1440)
    sub.add_parser("status")
    sub.add_parser("check")
    sub.add_parser("backtest")
    a = ap.parse_args()
    cfg = BasketConfig()
    if a.cmd == "backtest":
        backtest(cfg)
    else:
        bot = BasketBot(cfg)
        if a.cmd == "run":
            bot.run(a.minutes)
        elif a.cmd == "check":
            bot.decide()
        else:
            bot.status()
