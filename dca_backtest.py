"""
Backtest dollar-cost-averaging into SOL using real Coinbase SOL-USD daily
closes. DCA = buy a fixed $ amount every N days, never sell, hold.

    python dca_backtest.py                       # $50/week from earliest data
    python dca_backtest.py --usd 25 --days 3 --start 2024-01-01

Reports total invested, coins held, current value, total & annualised return,
worst drawdown along the way, and how DCA compared to putting the same total
in as a lump sum on day one. Past results are not future results — SOL can
and does fall for long stretches (it's down ~45% over the last year).
"""
import argparse, datetime as dt, time
import requests

CB = "https://api.exchange.coinbase.com/products/SOL-USD/candles"


def load_daily_closes():
    """Paginate Coinbase daily candles back as far as they go. Returns
    sorted [(date, close), ...]."""
    out = {}
    end = dt.datetime.now(dt.timezone.utc)
    while True:
        start = end - dt.timedelta(days=290)
        r = requests.get(CB, params={
            "granularity": 86400,
            "start": start.isoformat(), "end": end.isoformat(),
        }, headers={"User-Agent": "dca-backtest"}, timeout=20)
        if r.status_code != 200:
            break
        rows = r.json()
        if not rows:
            break
        for t, lo, hi, op, cl, vol in rows:
            out[dt.datetime.fromtimestamp(t, dt.timezone.utc).date()] = cl
        oldest = min(row[0] for row in rows)
        new_end = dt.datetime.fromtimestamp(oldest, dt.timezone.utc)
        if new_end >= end - dt.timedelta(days=1):
            break
        end = new_end
        time.sleep(0.25)
    return sorted(out.items())


def max_drawdown(equity):
    peak = equity[0]
    worst = 0.0
    for v in equity:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    return worst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--usd", type=float, default=50.0, help="$ per buy")
    ap.add_argument("--days", type=int, default=7, help="days between buys")
    ap.add_argument("--start", type=str, help="YYYY-MM-DD (default: earliest data)")
    args = ap.parse_args()

    print("fetching real SOL-USD daily history from Coinbase…")
    series = load_daily_closes()
    if not series:
        print("could not load price data"); return
    start = dt.date.fromisoformat(args.start) if args.start else series[0][0]
    series = [(d, p) for d, p in series if d >= start]
    print(f"{len(series)} days: {series[0][0]} (${series[0][1]:.2f})  ->  "
          f"{series[-1][0]} (${series[-1][1]:.2f})\n")

    coins = 0.0
    invested = 0.0
    buys = 0
    equity = []
    next_buy = series[0][0]
    for d, price in series:
        if d >= next_buy:
            coins += args.usd / price
            invested += args.usd
            buys += 1
            next_buy = d + dt.timedelta(days=args.days)
        equity.append(coins * price)

    final_price = series[-1][1]
    value = coins * final_price
    yrs = (series[-1][0] - series[0][0]).days / 365.25
    total_ret = value / invested - 1 if invested else 0
    ann = (value / invested) ** (1 / yrs) - 1 if invested and yrs > 0 else 0

    # lump sum: same total invested, all on day one
    ls_coins = invested / series[0][1]
    ls_value = ls_coins * final_price

    print("=" * 58)
    print(f"DCA  ${args.usd:g} every {args.days}d   ({buys} buys over {yrs:.1f} yr)")
    print("=" * 58)
    print(f"Total invested:      ${invested:,.2f}")
    print(f"SOL accumulated:     {coins:.3f}")
    print(f"Value now:           ${value:,.2f}")
    print(f"Profit / loss:       ${value - invested:+,.2f}   ({total_ret*100:+.1f}%)")
    print(f"Annualised return:   {ann*100:+.1f}%/yr")
    print(f"Worst drawdown:      {max_drawdown(equity)*100:.1f}%  (peak-to-trough on the way)")
    print("-" * 58)
    print(f"Same $ as lump sum on day 1 -> ${ls_value:,.2f}   "
          f"({(ls_value/invested-1)*100:+.1f}%)")
    print("=" * 58)
    verdict = "MADE money" if value > invested else "LOST money"
    print(f"Over this window DCA {verdict}. This is one asset over one past\n"
          "window; a different start date can flip the result. Not advice.")


if __name__ == "__main__":
    main()
