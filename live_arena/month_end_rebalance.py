"""
Month-End Rebalancing: forward paper test of a stock/bond rebalancing-flow signal (PREREG_MONTHEND.md).
=========================================================================================================

    python3 live_arena/month_end_rebalance.py --update

Rebuilds live_arena/month_end_ledger.json and live_arena/MONTHEND_RESULTS.md from scratch every run (cheap: at
most a few dozen months), the same way best_recent.py does, so it can never drift from the saved candle data.

Rule (PREREG_MONTHEND.md): on the trading day before the last 4 trading days of a month, compare SPY's and TLT's
month-to-date return through that day's close. If SPY is ahead, short SPY for the window (rebalancers predicted to
sell stocks); if TLT is ahead, go long SPY (rebalancers predicted to buy stocks). Enter at the window's first open,
exit at the window's last close. September 2026 is explicitly skipped - see the pre-registration for why. Makes no
network calls beyond the ordinary Yahoo fetch already used everywhere else in this project.
"""

import argparse
import hashlib
import json
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import server  # noqa: E402

PREREG = os.path.join(HERE, "..", "research", "PREREG_MONTHEND.md")
SHA_FILE = os.path.join(HERE, "MONTHEND.sha256")
LEDGER = os.path.join(HERE, "month_end_ledger.json")
REPORT = os.path.join(HERE, "MONTHEND_RESULTS.md")

FEE = 0.0001   # 1bp/side, SPY's cost elsewhere in this project
WINDOW_DAYS = 4
FIRST_WINDOW_MONTH = "2026-10"   # September 2026 explicitly skipped - see PREREG_MONTHEND.md
N_RANDOM_DRAWS = 2000
RANDOM_SEED = 20260923
G4_MIN_WINDOWS = 12


def check_prereg():
    digest = hashlib.sha256(open(PREREG, "rb").read()).hexdigest()
    saved = open(SHA_FILE).read().split()[0] if os.path.exists(SHA_FILE) else None
    return digest, digest == saved


def fetch_daily(sym):
    rows = server.yahoo_rows(sym, "1440")[:-1]   # drop the possibly-unfinished last candle
    return [{"time": r[0], "open": r[1], "close": r[4]} for r in rows]


def month_key(t):
    import datetime
    d = datetime.datetime.fromtimestamp(t, datetime.timezone.utc)
    return f"{d.year:04d}-{d.month:02d}"


def group_by_month(rows):
    out = {}
    for r in rows:
        out.setdefault(month_key(r["time"]), []).append(r)
    return out


def build_windows(spy_rows, tlt_rows):
    """One entry per month with enough data on both sides, oldest first: the decision day, the 4-day window, and
    both instruments' rows for month-to-date and fill prices."""
    spy_by_month, tlt_by_month = group_by_month(spy_rows), group_by_month(tlt_rows)
    tlt_idx = {r["time"]: i for i, r in enumerate(tlt_rows)}
    months_seen = sorted(spy_by_month)
    windows = []
    for k, mk in enumerate(months_seen):
        if mk < FIRST_WINDOW_MONTH:
            continue
        if k + 1 >= len(months_seen):
            continue   # this month isn't over yet - a later month must already appear in the data
        month_spy, month_tlt = spy_by_month[mk], tlt_by_month.get(mk)
        if not month_tlt or len(month_spy) <= WINDOW_DAYS or len(month_tlt) <= WINDOW_DAYS:
            continue
        window_spy = month_spy[-WINDOW_DAYS:]
        decision_row = month_spy[-WINDOW_DAYS - 1]
        decision_time = decision_row["time"]
        if decision_time not in tlt_idx:
            continue   # need TLT's own close on the same decision day
        spy_mtd_start, tlt_mtd_start = month_spy[0]["close"], month_tlt[0]["close"]
        spy_mtd = decision_row["close"] / spy_mtd_start - 1
        tlt_mtd = tlt_rows[tlt_idx[decision_time]]["close"] / tlt_mtd_start - 1
        window_end_time = window_spy[-1]["time"]
        windows.append({
            "month": mk, "decision_date": decision_time, "spy_mtd": spy_mtd, "tlt_mtd": tlt_mtd,
            "entry_open": window_spy[0]["open"], "exit_close": window_spy[-1]["close"],
            "window_end_time": window_end_time, "window_days": len(window_spy),
        })
    return windows


def realized_return(direction, entry_open, exit_close, fee=FEE):
    raw = exit_close / entry_open - 1
    return direction * raw - 2 * fee   # one trade in, one out


def build_ledger(windows, now):
    ledger = []
    for w in windows:
        if w["window_end_time"] > now:
            continue   # window hasn't finished yet
        if w["spy_mtd"] == w["tlt_mtd"]:
            direction, why = 0, "tie"
        elif w["spy_mtd"] > w["tlt_mtd"]:
            direction, why = -1, "SPY ahead month-to-date -> predicted selling -> short"
        else:
            direction, why = 1, "TLT ahead month-to-date -> predicted buying -> long"
        ret = realized_return(direction, w["entry_open"], w["exit_close"]) if direction else 0.0
        ledger.append({
            "month": w["month"], "decision_date": w["decision_date"], "spy_mtd": w["spy_mtd"],
            "tlt_mtd": w["tlt_mtd"], "direction": direction, "why": why,
            "entry_open": w["entry_open"], "exit_close": w["exit_close"], "realized_ret": ret,
        })
    return ledger


def compound(rets):
    total = 1.0
    for r in rets:
        total *= 1 + r
    return total - 1


def random_control(ledger, seed=RANDOM_SEED, n=N_RANDOM_DRAWS):
    rng = random.Random(seed)
    draws = []
    for _ in range(n):
        total = 1.0
        for e in ledger:
            d = rng.choice([-1, 1])
            total *= 1 + realized_return(d, e["entry_open"], e["exit_close"])
        draws.append(total - 1)
    draws.sort()
    return draws


def hold_flat_return(ledger):
    """Just holding SPY flat (no position, no trades) over the same windows - the G2 benchmark."""
    return compound(e["exit_close"] / e["entry_open"] - 1 for e in ledger)


def write_report(digest, prereg_ok, ledger):
    def pc(x):
        return "n/a" if x is None else f"{x * 100:+.1f}%"

    lines = [
        "# Month-End Rebalancing: results", "",
        f"**Updated:** {time.strftime('%Y-%m-%d %H:%M')}. PREREG_MONTHEND.md sha256 `{digest}`"
        f" ({'matches MONTHEND.sha256' if prereg_ok else 'DOES NOT MATCH MONTHEND.sha256 - do not trust this run'}).",
        "",
    ]
    if not prereg_ok:
        with open(REPORT, "w") as f:
            f.write("\n".join(lines))
        return
    lines += [f"{len(ledger)} of {G4_MIN_WINDOWS} completed windows "
              f"(first window: {FIRST_WINDOW_MONTH}; September 2026 explicitly skipped, see the pre-registration).",
              ""]
    if not ledger:
        lines += ["**No window has completed yet.**", ""]
        with open(REPORT, "w") as f:
            f.write("\n".join(lines))
        return

    rets = [e["realized_ret"] for e in ledger]
    total = compound(rets)
    flat_total = hold_flat_return(ledger)
    draws = random_control(ledger)
    p95 = draws[int(0.95 * len(draws)) - 1]
    pct_below = sum(1 for d in draws if d < total) / len(draws)
    positive_windows = sum(1 for r in rets if r > 0)

    g1 = total > 0
    g2 = total > flat_total
    g3 = total > p95
    g4 = len(ledger) >= G4_MIN_WINDOWS and positive_windows > len(ledger) / 2
    passed_core = g1 and g3 and g4
    verdict = ("not enough windows yet" if len(ledger) < G4_MIN_WINDOWS else
               "PASS" if (passed_core and g2) else
               "real, but not worth it" if (passed_core and not g2) else "FAIL")

    lines += [
        f"**Verdict: {verdict}.**", "",
        f"- Cumulative return after fees: **{pc(total)}**",
        f"- Just holding SPY flat over the same days: {pc(flat_total)}",
        f"- Random-direction control, 95th percentile of {N_RANDOM_DRAWS} draws: {pc(p95)} "
        f"(this result beat {pct_below * 100:.1f}% of random draws)",
        f"- Positive in {positive_windows} of {len(ledger)} windows",
        "",
        "| gate | result |", "|---|---|",
        f"| G1 (positive) | {'pass' if g1 else 'fail'} |",
        f"| G2 (beats holding flat) | {'pass' if g2 else 'fail'} |",
        f"| G3 (beats random direction, 95th pct) | {'pass' if g3 else 'fail'} |",
        f"| G4 (>= {G4_MIN_WINDOWS} windows, positive in more than half) | {'pass' if g4 else 'fail'} |",
        "",
        "| month | decision | SPY MTD | TLT MTD | direction | return |", "|---|---|---|---|---|---|",
        *(f"| {e['month']} | {e['why']} | {pc(e['spy_mtd'])} | {pc(e['tlt_mtd'])} | "
          f"{'short' if e['direction'] < 0 else 'long' if e['direction'] > 0 else 'flat'} | {pc(e['realized_ret'])} |"
          for e in ledger),
        "",
    ]
    with open(REPORT, "w") as f:
        f.write("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true")
    args = ap.parse_args()

    digest, prereg_ok = check_prereg()
    print(f"PREREG_MONTHEND.md sha256 = {digest} ({'OK' if prereg_ok else 'MISMATCH - refusing to trust this run'})")
    if not prereg_ok:
        write_report(digest, False, [])
        return

    spy_rows, tlt_rows = fetch_daily("SPY"), fetch_daily("TLT")
    now = min(spy_rows[-1]["time"], tlt_rows[-1]["time"])
    windows = build_windows(spy_rows, tlt_rows)
    ledger = build_ledger(windows, now)
    print(f"{len(ledger)} completed window(s): {[e['month'] for e in ledger]}")
    for e in ledger:
        print(f"  {e['month']}: {e['why']}, return {e['realized_ret'] * 100:+.2f}%")

    if not args.update:
        return
    with open(LEDGER, "w") as f:
        json.dump({"prereg_sha256": digest, "generated": time.strftime("%Y-%m-%d %H:%M"), "windows": ledger}, f, indent=1)
    print(f"wrote {LEDGER}")
    write_report(digest, prereg_ok, ledger)
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
