"""
Crypto perpetual-futures funding-rate carry (the "cash and carry" basis trade).
==============================================================================

The only MECHANICAL candidate left. Everything else tested in this project was
a statistical pattern - buy when the indicator says so and hope the pattern
repeats. This is different: a perpetual swap has no expiry, so exchanges force
it toward spot with a funding payment every 8 hours. When the rate is positive,
longs literally pay shorts. Hold spot and short the perp in equal size and the
price exposure cancels, leaving the funding stream.

That is a real cash flow, not a backtested edge. The questions are only:
how big, how stable, and does it survive fees.

Data: OKX public funding-rate history (Binance and Bybit both geo-block from
here - 451 and 403 respectively).

Economics modelled per 8h period, on $1 of deployed capital:
  * buy `spot_frac` of spot, short the same notional of the perp
  * the perp leg needs margin, so spot_frac = 1 / (1 + 1/perp_leverage)
  * a short receives +funding when the rate is positive, pays when negative
  * fees charged on both legs at entry and exit (2 legs x 2 = 4 x `fee`)
  * idle capital earns the cash rate, so the comparison is excess of cash
"""

import json
import os
import time

import certifi
import requests

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache")
OKX = "https://www.okx.com/api/v5/public/funding-rate-history"
UA = {"User-Agent": "Mozilla/5.0"}
PERIODS_PER_YEAR = 365 * 3          # funding settles every 8 hours


def fetch_funding(inst, max_pages=200, quiet=False):
    """Full funding history for an OKX swap, oldest first. Cached for a day."""
    path = os.path.join(CACHE, f"funding_{inst.replace('-', '_')}.json")
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < 24 * 3600:
        try:
            return json.load(open(path))
        except json.JSONDecodeError:
            pass
    rows, after, seen = [], None, set()
    for _ in range(max_pages):
        p = {"instId": inst, "limit": 100}
        if after:
            p["after"] = after
        try:
            r = requests.get(OKX, params=p, timeout=20, verify=certifi.where(), headers=UA)
            data = r.json().get("data", [])
        except Exception as e:
            if not quiet:
                print(f"  {inst}: {type(e).__name__}")
            break
        if not data:
            break
        new = 0
        for d in data:
            t = int(d["fundingTime"])
            if t in seen:
                continue
            seen.add(t)
            rows.append([t, float(d["fundingRate"])])
            new += 1
        if new == 0:
            break
        after = str(min(int(d["fundingTime"]) for d in data))
        time.sleep(0.12)                      # OKX public rate limit
    rows.sort()
    if rows:
        json.dump(rows, open(path, "w"))
    if not quiet:
        span = f"{_ymd(rows[0][0])} -> {_ymd(rows[-1][0])}" if rows else "EMPTY"
        print(f"  {inst:<18} {len(rows):>6} periods  {span}")
    return rows


def _ymd(ms):
    return time.strftime("%Y-%m-%d", time.gmtime(ms / 1000))


def carry(rows, *, fee=0.0005, perp_leverage=5.0, threshold=None,
          lookback=9, rf_annual=None):
    """
    Per-period NET returns on $1 of capital, excess of cash.

    threshold : if set, only hold the trade when the trailing mean funding rate
                over `lookback` periods exceeds it; otherwise sit in cash. This
                is the realistic version - nobody holds through negative carry.
    rf_annual : {date: annual rate} to subtract; None treats cash as 0%.
    """
    spot_frac = 1.0 / (1.0 + 1.0 / perp_leverage)
    out, dates, on_prev = [], [], False
    n_switch = 0
    for i, (t, f) in enumerate(rows):
        on = True
        if threshold is not None:
            if i < lookback:
                on = False
            else:
                trail = sum(x[1] for x in rows[i - lookback:i]) / lookback
                on = trail > threshold
        r = spot_frac * f if on else 0.0
        if on != on_prev:
            r -= 2 * fee                      # two legs, entering or exiting
            n_switch += 1
        if rf_annual is not None:
            d = _ymd(t)
            r -= (rf_annual.get(d, 0.0) * 8 / 24) if not on else 0.0
        out.append(r)
        dates.append(_ymd(t))
        on_prev = on
    return {"rets": out, "dates": dates, "switches": n_switch,
            "pct_on": sum(1 for i, r in enumerate(out) if r != 0) / max(len(out), 1)}


def ann(rets):
    """Compounded annualised return from 8-hourly returns."""
    eq = 1.0
    for r in rets:
        eq *= (1 + r)
        if eq <= 0:
            return -1.0
    return eq ** (PERIODS_PER_YEAR / max(len(rets), 1)) - 1


# --------------------------------------------------------- CME dated basis

def last_friday(y, m):
    """CME bitcoin futures settle on the last Friday of the contract month."""
    import calendar
    cal = calendar.monthcalendar(y, m)
    fridays = [w[calendar.FRIDAY] for w in cal if w[calendar.FRIDAY] != 0]
    return fridays[-1]


def days_to_expiry(ymd):
    """Calendar days from `ymd` to the front-month CME settlement."""
    import datetime
    d = datetime.date(*map(int, ymd.split("-")))
    exp = datetime.date(d.year, d.month, last_friday(d.year, d.month))
    if d >= exp:
        y, m = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
        exp = datetime.date(y, m, last_friday(y, m))
    return max((exp - d).days, 1)


def cme_basis(fut_bars, spot_bars, min_days=3):
    """
    Annualised cash-and-carry yield from front-month futures vs spot.

    Buying spot and shorting the future locks in (F/S - 1) over the days to
    settlement; annualising makes contracts of different maturity comparable.
    Days inside `min_days` of expiry are dropped - the annualisation explodes
    there and no one holds a basis trade into settlement.
    """
    f = {_ymd(b[0] * 1000): b[4] for b in fut_bars}
    s = {_ymd(b[0] * 1000): b[4] for b in spot_bars}
    out = []
    for d in sorted(set(f) & set(s)):
        if s[d] <= 0:
            continue
        dte = days_to_expiry(d)
        if dte < min_days:
            continue
        out.append([d, (f[d] / s[d] - 1) * 365.0 / dte, dte])
    return out
