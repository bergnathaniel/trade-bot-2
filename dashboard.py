"""
Daily P&L dashboard — one consolidated view across every bot in this project.

    python3 dashboard.py                # today + last 14 days, all strategies
    python3 dashboard.py --days 30      # widen the history window
    python3 dashboard.py --html         # also write dashboard.html (open in a browser)

Read-only. Safe to run anytime, including while the bots are still going — it
only reads the CSV logs and *_state.json files. It does NOT place trades, and
it makes no network calls. "Unrealized" figures are as of the last line the
bot itself logged.

What it reads, if present:
  scalper  -> dry_run_log.csv, trade_log.csv        (live_state.json)
  insider  -> insider_dry_run_log.csv, insider_trade_log.csv
  dca      -> dca_log.csv                            (dca_state.json)
"""

import argparse
import csv
import glob
import html
import json
import os
import time
from collections import defaultdict

TODAY = time.strftime("%Y-%m-%d")

# strategy -> list of (label, csv path). First existing file that has SELL rows
# is treated as the "active" log; all existing files are summed for lifetime P&L.
LOGS = {
    "scalper": [("dry-run", "dry_run_log.csv"), ("live/paper", "trade_log.csv")],
    "insider": [("dry-run", "insider_dry_run_log.csv"), ("live", "insider_trade_log.csv")],
}
STATE_FILES = {
    "scalper": "live_state.json",
    "insider": "insider_state.json",
    "dca": "dca_state.json",
}


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def load_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def summarize_trades(rows):
    """Realized P&L / win-loss / fees for one scalper-or-insider style log."""
    sells = [r for r in rows if r.get("event") == "SELL"]
    buys = [r for r in rows if r.get("event") == "BUY"]
    per_day = defaultdict(lambda: {"pnl": 0.0, "n": 0, "w": 0, "l": 0, "fees": 0.0})
    for r in sells:
        d = (r.get("timestamp") or "")[:10]
        p = num(r.get("pnl_usd"))
        b = per_day[d]
        b["pnl"] += p
        b["n"] += 1
        b["w"] += 1 if p > 0 else 0
        b["l"] += 1 if p <= 0 else 0
        b["fees"] += num(r.get("fee_usd"))
    for r in buys:
        per_day[(r.get("timestamp") or "")[:10]]["fees"] += num(r.get("fee_usd"))
    realized = sum(num(r.get("pnl_usd")) for r in sells)
    fees = sum(num(r.get("fee_usd")) for r in rows)
    wins = sum(1 for r in sells if num(r.get("pnl_usd")) > 0)
    return {
        "per_day": per_day,
        "realized": realized,
        "fees": fees,
        "sells": len(sells),
        "buys": len(buys),
        "wins": wins,
        "open": len(buys) - len(sells),
    }


def scan_strategy(name):
    """Merge every existing log file for one strategy."""
    merged_days = defaultdict(lambda: {"pnl": 0.0, "n": 0, "w": 0, "l": 0, "fees": 0.0})
    realized = fees = sells = buys = wins = open_pos = 0.0
    files_used = []
    for label, path in LOGS[name]:
        rows = load_rows(path)
        if not rows:
            continue
        files_used.append(f"{path} ({label}, {len(rows)} rows)")
        s = summarize_trades(rows)
        for d, b in s["per_day"].items():
            m = merged_days[d]
            for k in ("pnl", "n", "w", "l", "fees"):
                m[k] += b[k]
        realized += s["realized"]
        fees += s["fees"]
        sells += s["sells"]
        buys += s["buys"]
        wins += s["wins"]
        open_pos += s["open"]
    return {
        "files": files_used,
        "per_day": merged_days,
        "realized": realized,
        "fees": fees,
        "sells": int(sells),
        "buys": int(buys),
        "wins": int(wins),
        "open": int(open_pos),
    }


def scan_dca():
    rows = load_rows("dca_log.csv")
    buys = [r for r in rows if r.get("event") == "BUY"]
    if not buys:
        return None
    last = buys[-1]
    invested = num(last.get("total_invested"))
    value = num(last.get("portfolio_value"))
    per_day = defaultdict(lambda: {"in": 0.0, "n": 0})
    for r in buys:
        d = (r.get("timestamp") or "")[:10]
        per_day[d]["in"] += num(r.get("usd_in"))
        per_day[d]["n"] += 1
    return {
        "buys": len(buys),
        "invested": invested,
        "value": value,
        "unrealized": value - invested,
        "as_of": last.get("timestamp", "?"),
        "per_day": per_day,
    }


def load_state(name):
    path = STATE_FILES.get(name)
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def money(x):
    return f"${x:+,.2f}"


# ---------------- text report ----------------

def render_text(days):
    out = []
    p = out.append
    p("")
    p("=" * 66)
    p(f"  DAILY P&L DASHBOARD           {time.strftime('%Y-%m-%d %H:%M')}")
    p("=" * 66)

    grand_today = grand_life = 0.0
    day_keys = sorted({
        d for name in LOGS for d in scan_strategy(name)["per_day"]
    }, reverse=True)[:days]

    for name in LOGS:
        s = scan_strategy(name)
        st = load_state(name)
        p("")
        p(f"── {name.upper()} " + "─" * (63 - len(name)))
        if not s["files"]:
            p("   no log file yet — this bot hasn't recorded anything")
            continue
        for fu in s["files"]:
            p(f"   log: {fu}")

        today = s["per_day"].get(TODAY, {"pnl": 0.0, "n": 0, "w": 0, "l": 0, "fees": 0.0})
        grand_today += today["pnl"]
        grand_life += s["realized"]

        wr = (s["wins"] / s["sells"] * 100) if s["sells"] else 0.0
        p("")
        p(f"   TODAY ({TODAY}):  {money(today['pnl'])}   "
          f"{today['n']} closed  ({today['w']}W/{today['l']}L)  "
          f"fees ${today['fees']:.2f}")
        p(f"   Lifetime:        {money(s['realized'])}   "
          f"{s['sells']} closed  ({wr:.0f}% win)  "
          f"fees ${s['fees']:.2f}   open now: {s['open']}")
        if s["sells"]:
            verdict = "PROFITABLE" if s["realized"] > 0 else "LOSING"
            exp = s["realized"] / s["sells"]
            p(f"   Verdict:         {verdict} after fees  (expectancy {money(exp)}/trade)")
        else:
            p("   Verdict:         no closed trades yet — nothing to judge")

        if st:
            bal = st.get("balance_usd")
            start = st.get("starting_balance_usd")
            if bal is not None and start:
                p(f"   Wallet state:    ${bal:,.2f} of ${start:,.2f} start  "
                  f"({(bal/start - 1) * 100:+.1f}%)   [{STATE_FILES[name]}]")

        recent = sorted((d for d in s["per_day"] if d in day_keys), reverse=True)
        if recent:
            p("")
            p("   recent days:")
            for d in recent:
                b = s["per_day"][d]
                bar = ("+" if b["pnl"] >= 0 else "-") * min(30, int(abs(b["pnl"]) * 4) + (1 if b["pnl"] else 0))
                mark = "  <-- today" if d == TODAY else ""
                p(f"     {d}  {money(b['pnl']):>10}  {b['n']:>2} trades  {bar}{mark}")

    dca = scan_dca()
    p("")
    p("── DCA " + "─" * 60)
    if not dca:
        p("   no dca_log.csv buys yet")
    else:
        tin = sum(v["in"] for d, v in dca["per_day"].items() if d == TODAY)
        p(f"   {dca['buys']} buys, ${dca['invested']:,.2f} invested   (as of {dca['as_of']})")
        p(f"   TODAY: ${tin:,.2f} bought")
        p(f"   Portfolio value: ${dca['value']:,.2f}   unrealized {money(dca['unrealized'])}"
          f"  ({(dca['value']/dca['invested'] - 1) * 100:+.1f}%)" if dca["invested"] else "")
        p("   (buy-and-hold — 'unrealized' moves with SOL price; last logged value only)")

    p("")
    p("=" * 66)
    p(f"  ALL STRATEGIES — realized today:    {money(grand_today)}")
    p(f"  ALL STRATEGIES — realized lifetime: {money(grand_life)}")
    if dca and dca["invested"]:
        p(f"  + DCA unrealized:                   {money(dca['unrealized'])}")
    p("=" * 66)
    p("  Realized = closed trades only. This is paper/dry-run money unless")
    p("  a *_state.json above shows a live wallet. Nothing here is a")
    p("  guarantee of future results.")
    p("=" * 66)
    p("")
    return "\n".join(out)


# ---------------- html report ----------------

def render_html(days):
    strat = {name: scan_strategy(name) for name in LOGS}
    dca = scan_dca()
    grand_today = sum(
        s["per_day"].get(TODAY, {"pnl": 0.0})["pnl"] for s in strat.values()
    )
    grand_life = sum(s["realized"] for s in strat.values())

    def cls(v):
        return "pos" if v > 0 else ("neg" if v < 0 else "flat")

    rows_html = []
    for name, s in strat.items():
        if not s["files"]:
            continue
        today = s["per_day"].get(TODAY, {"pnl": 0.0, "n": 0, "w": 0, "l": 0})
        wr = (s["wins"] / s["sells"] * 100) if s["sells"] else 0.0
        day_rows = ""
        for d in sorted(s["per_day"], reverse=True)[:days]:
            b = s["per_day"][d]
            day_rows += (
                f"<tr class='{'today' if d == TODAY else ''}'>"
                f"<td>{d}</td><td class='{cls(b['pnl'])}'>{money(b['pnl'])}</td>"
                f"<td>{b['n']}</td><td>{b['w']}W / {b['l']}L</td></tr>"
            )
        rows_html.append(f"""
        <section>
          <h2>{html.escape(name.upper())}</h2>
          <div class="cards">
            <div class="card"><span>Today</span><b class="{cls(today['pnl'])}">{money(today['pnl'])}</b>
              <small>{today['n']} closed &middot; {today['w']}W/{today['l']}L</small></div>
            <div class="card"><span>Lifetime realized</span><b class="{cls(s['realized'])}">{money(s['realized'])}</b>
              <small>{s['sells']} closed &middot; {wr:.0f}% win &middot; fees ${s['fees']:.2f}</small></div>
            <div class="card"><span>Open now</span><b class="flat">{s['open']}</b>
              <small>{('PROFITABLE' if s['realized'] > 0 else 'LOSING') + ' after fees' if s['sells'] else 'no closed trades yet'}</small></div>
          </div>
          <table><thead><tr><th>Day</th><th>Realized P&amp;L</th><th>Trades</th><th>W/L</th></tr></thead>
          <tbody>{day_rows or "<tr><td colspan=4>no closed trades</td></tr>"}</tbody></table>
        </section>""")

    dca_html = ""
    if dca and dca["invested"]:
        dca_html = f"""
        <section>
          <h2>DCA</h2>
          <div class="cards">
            <div class="card"><span>Invested</span><b class="flat">${dca['invested']:,.2f}</b><small>{dca['buys']} buys</small></div>
            <div class="card"><span>Portfolio value</span><b class="flat">${dca['value']:,.2f}</b><small>as of {html.escape(dca['as_of'])}</small></div>
            <div class="card"><span>Unrealized</span><b class="{cls(dca['unrealized'])}">{money(dca['unrealized'])}</b>
              <small>{(dca['value'] / dca['invested'] - 1) * 100:+.1f}% &middot; moves with SOL price</small></div>
          </div>
        </section>"""

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Trade Bot P&amp;L</title>
<style>
  :root {{ color-scheme: light dark; --bg:#fff; --fg:#111; --mut:#666; --line:#e3e3e3; --card:#f7f7f8; }}
  @media (prefers-color-scheme:dark) {{ :root {{ --bg:#0f1113; --fg:#e8e8e8; --mut:#9aa0a6; --line:#26292e; --card:#17191c; }} }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; padding:2rem 1rem 4rem; background:var(--bg); color:var(--fg);
    font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
  main {{ max-width:820px; margin:0 auto; }}
  h1 {{ font-size:1.3rem; margin:0 0 .25rem; }}
  .stamp {{ color:var(--mut); font-size:.85rem; margin-bottom:1.5rem; }}
  .grand {{ display:flex; gap:1rem; flex-wrap:wrap; margin-bottom:2rem; }}
  .grand .card b {{ font-size:1.5rem; }}
  section {{ margin:1.5rem 0; }}
  h2 {{ font-size:1rem; letter-spacing:.05em; color:var(--mut); border-bottom:1px solid var(--line); padding-bottom:.4rem; }}
  .cards {{ display:flex; gap:1rem; flex-wrap:wrap; margin:1rem 0; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:.8rem 1rem; min-width:170px; }}
  .card span {{ display:block; color:var(--mut); font-size:.75rem; text-transform:uppercase; letter-spacing:.04em; }}
  .card b {{ display:block; font-size:1.15rem; margin:.15rem 0; }}
  .card small {{ color:var(--mut); }}
  table {{ width:100%; border-collapse:collapse; font-variant-numeric:tabular-nums; }}
  th,td {{ text-align:right; padding:.35rem .6rem; border-bottom:1px solid var(--line); }}
  th:first-child,td:first-child {{ text-align:left; }}
  tr.today td {{ font-weight:700; }}
  .pos {{ color:#12854a; }} .neg {{ color:#c0392b; }} .flat {{ color:var(--fg); }}
  @media (prefers-color-scheme:dark) {{ .pos {{ color:#4ade80; }} .neg {{ color:#f87171; }} }}
  footer {{ margin-top:3rem; color:var(--mut); font-size:.8rem; }}
</style></head><body><main>
  <h1>Trade Bot &mdash; Daily P&amp;L</h1>
  <div class="stamp">generated {time.strftime('%Y-%m-%d %H:%M')} &middot; read-only view of local logs</div>
  <div class="grand">
    <div class="card"><span>All strategies &mdash; today</span><b class="{cls(grand_today)}">{money(grand_today)}</b><small>realized, closed trades</small></div>
    <div class="card"><span>All strategies &mdash; lifetime</span><b class="{cls(grand_life)}">{money(grand_life)}</b><small>realized, closed trades</small></div>
  </div>
  {''.join(rows_html)}
  {dca_html}
  <footer>Realized = closed trades only. Paper/dry-run money unless a wallet state file shows live.
  Past results do not predict future ones.</footer>
</main></body></html>"""


def main():
    ap = argparse.ArgumentParser(description="Daily P&L dashboard across all bots")
    ap.add_argument("--days", type=int, default=14, help="history window (default 14)")
    ap.add_argument("--html", action="store_true", help="also write dashboard.html")
    args = ap.parse_args()

    print(render_text(args.days))

    if args.html:
        with open("dashboard.html", "w") as f:
            f.write(render_html(args.days))
        print(f"wrote {os.path.abspath('dashboard.html')}  — open it in a browser\n")


if __name__ == "__main__":
    main()
