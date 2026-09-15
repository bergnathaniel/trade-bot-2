"""Weekly check of the Live Arena paper tests.

Opens the app's Paper tests panel once in headless Chrome, so the numbers come from the same code as the panel,
then prints a plain-English summary: every buy and sell since the last check, where each test stands next to its
yardsticks, and the orders waiting for the next open. Opening the panel also adds the day's snapshot to
paper_ledger.jsonl. Paper money only: nothing here can place a real trade.

Run:       python3 live_arena/weekly_check.py
           (also saves the summary as live_arena/weekly/<date>.md)
Practice:  python3 live_arena/weekly_check.py --from 2026-06-01 [--days 7]
           (pretends the tests started on that date; prints only, never logged or saved)
"""
import argparse
import datetime
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import server  # noqa: E402  the app's own server, started below on a free port

WEEKLY = os.path.join(ROOT, "weekly")
STATE = os.path.join(WEEKLY, "last_check.json")   # the last price day already reported, per test
BROWSERS = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]
TIMEOUT = 600
MAX_ROWS = 40


def run_panel(practice_from):
    """Serve the app on a free port, open it with ?paper=auto in headless Chrome, and wait for the result it saves."""
    browser = next((b for b in BROWSERS if os.path.exists(b)), None) or shutil.which("google-chrome") or shutil.which("chromium")
    if not browser:
        sys.exit("No Chrome, Chromium, Edge or Brave found. The check runs the app in a headless browser.")
    target = server.LATEST_PRACTICE if practice_from else server.LATEST
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{httpd.server_address[1]}/?paper=auto" + (f"&from={practice_from}" if practice_from else "")
    profile = tempfile.mkdtemp(prefix="live-arena-check-")
    started = time.time()
    chrome = subprocess.Popen([browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
                               "--mute-audio", f"--user-data-dir={profile}", url],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        while time.time() - started < TIMEOUT:
            if os.path.exists(target) and os.path.getmtime(target) >= started:
                with open(target) as f:
                    return json.load(f)
            if chrome.poll() is not None:
                sys.exit("Headless Chrome closed before the paper tests finished.")
            time.sleep(2)
        sys.exit(f"The paper tests didn't finish within {TIMEOUT // 60} minutes. Is the internet connection up?")
    finally:
        chrome.terminate()
        try:
            chrome.wait(timeout=10)
        except subprocess.TimeoutExpired:
            chrome.kill()
        httpd.shutdown()
        shutil.rmtree(profile, ignore_errors=True)


def pct(x):
    return "–" if x is None else f"{x * 100:+.1f}%"


def money(x):
    return f"-${-x:,.2f}" if x < 0 else f"+${x:,.2f}"


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def price(x):   # same rounding as the app's trade list
    return f"{x:,.2f}" if x >= 100 else f"{x:.3f}" if x >= 1 else f"{x:.3g}"


def versus(x, y, name):
    if x is None or y is None:
        return f"no number yet for {name}"
    return f"{'ahead of' if x > y else 'behind'} {name} ({pct(x)} vs {pct(y)})"


def beats(x, y):
    return x is not None and y is not None and x > y


def trade_lines(fills):
    sells = [f for f in fills if f["side"] == "sell"]
    text = f"{plural(len(fills) - len(sells), 'buy')} and {plural(len(sells), 'sell')}"
    if sells:
        best, worst = max(sells, key=lambda f: f["pnl"]), min(sells, key=lambda f: f["pnl"])
        text += f". Profit on the sales: {money(sum(f['pnl'] for f in sells))} in total"
        if len(sells) > 1:
            text += f"; best {best['bot']} on {best['symbol']} {money(best['pnl'])}, worst {worst['bot']} on {worst['symbol']} {money(worst['pnl'])}"
    rows = sorted(fills, key=lambda f: f["day"], reverse=True)
    out = [text + ".", "", "| Date (filled at the open) | Bot | What | Action | Price | Profit on the sale |", "|---|---|---|---|---:|---:|"]
    for f in rows[:MAX_ROWS]:
        out.append(f"| {f['day']} | {f['bot']} | {f['symbol']} | {'Bought' if f['side'] == 'buy' else 'Sold'} | {price(f['price'])} | "
                   f"{money(f['pnl']) if f['side'] == 'sell' else ''} |")
    if len(rows) > MAX_ROWS:
        out += ["", f"({len(rows) - MAX_ROWS} older ones not shown; the app's Paper tests panel lists them all.)"]
    return out


def test_section(t, fills, label, start):
    lines = [f"## {t['title']}", ""]
    if t.get("error"):
        return lines + [f"Couldn't update: {t['error']}"]
    if not t["through"] or t["through"] < start:
        return lines + ["No prices from the start date on yet, so nothing has traded."]
    lines += [f"Prices through {t['through']}. {t['fee']}% per trade, orders fill at the next open, $10,000 of paper money per account.", ""]
    trades = trade_lines(fills) if fills else ["none."]
    lines += [f"**Buys and sells {label}:** {trades[0]}"] + trades[1:]
    lines += ["", f"**Since {start}:**", ""]
    if "bots" in t:
        n, unit, strict, names = t["n"], t.get("unit") or "coin", t.get("strict"), t["bot_names"]
        extra = f" Without its best {unit} |" if strict else ""
        lines += [f"| | Average return |{extra} Median | Made money | Holding now | Trades |",
                  "|---|---:|" + ("---:|" if strict else "") + "---:|---:|---:|---:|"]
        lines += [f"| {names[b['bot']]} | {pct(b['avg'])} |" + (f" {pct(b.get('without_best'))} |" if strict else "")
                  + f" {pct(b['median'])} | {b['up']} of {n} | {b['holding']} of {n} | {b['trades']} |" for b in t["bots"]]
        blanks = " |" * (5 if strict else 4)
        lines += [f"| Just holding all {n} | {pct(t['hold_avg'])} |{blanks}",
                  f"| Just holding {t['index_name']} | {pct(t['index'])} |{blanks}",
                  f"| Luck bar: {t.get('luck_label') or '90th percentile of 200 random Coin Flips'} | {pct(t['luck'])} |{blanks}", ""]

        def checks(b):   # (what it's compared with, its number, the bar)
            out = [("the luck bar", b["avg"], t["luck"]), (f"holding all {n}", b["avg"], t["hold_avg"]), (t["index_name"], b["avg"], t["index"])]
            if strict:
                out.append((f"{t['index_name']} with its best {unit} left out", b.get("without_best"), t["index"]))
            return out

        if len(t["bots"]) <= 5:
            lines += [f"- {names[b['bot']]}: {', '.join(versus(x, y, name) for name, x, y in checks(b))}; "
                      f"made money on {b['up']} of {n} (the bar needs more than half)." for b in t["bots"]]
        else:
            table = [checks(b) for b in t["bots"]]
            counts = "; ".join(f"{sum(beats(c[k][1], c[k][2]) for c in table)} ahead of {table[0][k][0]}" for k in range(len(table[0])))
            leaders = [names[b["bot"]] for b, c in zip(t["bots"], table) if all(beats(x, y) for _, x, y in c) and b["up"] > n / 2]
            lines += [f"- Of the {len(t['bots'])} bots: {counts}; {sum(b['up'] > n / 2 for b in t['bots'])} made money on more than half of the {n}.",
                      f"- Ahead on every part of the bar so far: {', '.join(leaders) or 'none'}."]
    elif "rows" in t:
        lines += ["| | Return | Just holding it | Holding now | Trades |", "|---|---:|---:|---:|---:|"]
        lines += [f"| IBS Swing on {r['symbol']} | {pct(r['ret'])} | {pct(r['hold'])} | {'yes' if r['holding'] else 'no'} | {r['trades']} |" for r in t["rows"]]
        lines += [""] + [f"- IBS Swing on {r['symbol']}: {versus(r['ret'], r['hold'], 'holding ' + r['symbol'])}." for r in t["rows"]]
    else:
        lines += ["| | Return | Holding now | Trades |", "|---|---:|---:|---:|",
                  f"| Leveraged trend | {pct(t['ret'])} | {'SSO' if t['holding'] else 'cash'} | {t['trades']} |",
                  f"| Just holding SPY | {pct(t['spy'])} | | |", f"| Just holding SSO | {pct(t['sso'])} | | |", "",
                  f"- Leveraged trend: {versus(t['ret'], t['spy'], 'holding SPY')}."]
    if t["pending"]:
        shown = " · ".join(f"{p['bot']} {p['act']}s {p['symbol']}" for p in t["pending"][:15])
        more = f" · and {len(t['pending']) - 15} more" if len(t["pending"]) > 15 else ""
        lines += ["", f"**Waiting to fill at the next open ({len(t['pending'])}):** {shown}{more}"]
    if t["stale"]:
        lines += ["", "No fresh prices for: " + ", ".join(t["stale"]) + "."]
    return lines


def main():
    ap = argparse.ArgumentParser(description="Weekly check of the Live Arena paper tests (paper money only).")
    ap.add_argument("--from", dest="practice_from", metavar="YYYY-MM-DD", help="practice run from a pretend start date")
    ap.add_argument("--days", type=int, default=7, help="practice runs: list the trades from this many days before the last price")
    args = ap.parse_args()
    if args.practice_from:
        datetime.date.fromisoformat(args.practice_from)   # a bad date fails here, before Chrome starts
    snap = run_panel(args.practice_from)
    start, through = snap["from"], snap["data_through"]
    state = {}
    if not snap["practice"] and os.path.exists(STATE):
        with open(STATE) as f:
            state = json.load(f)
    lines = [f"# Live Arena paper tests: {'PRACTICE run from a pretend start of ' + start if snap['practice'] else 'weekly check'}", "",
             f"Checked {datetime.datetime.now():%Y-%m-%d %H:%M}. Paper money only; none of these are real trades."]
    if not through or through < start:
        lines.append(f"The paper tests start on {start}, and no prices from that day on exist yet. The first buy or sell can happen at the open after it.")
    else:
        day = (datetime.date.today() - datetime.date.fromisoformat(start)).days + 1
        lines.append(f"Day {day} since the start on {start}. Only the reviews on {' and '.join(snap['reviews'])} decide pass or fail, "
                     "under the bar in live_arena/PAPER_TESTS.md. Until then these are progress numbers.")
    new_state = {}
    for t in snap["tests"]:
        if snap["practice"]:
            cutoff = (datetime.date.fromisoformat(through) - datetime.timedelta(days=args.days)).isoformat() if through else start
            label = f"in the last {args.days} days of prices (after {cutoff})"
        else:
            cutoff = state.get(t["test"])
            label = f"since the last check (after {cutoff})" if cutoff else f"since the start on {start}"
        fills = [f for f in t.get("fills", []) if cutoff is None or f["day"] > cutoff]
        lines += [""] + test_section(t, fills, label, start)
        new_state[t["test"]] = t.get("through") or state.get(t["test"])
    text = "\n".join(lines) + "\n"
    print(text)
    if not snap["practice"]:
        os.makedirs(WEEKLY, exist_ok=True)
        path = os.path.join(WEEKLY, f"{datetime.date.today()}.md")
        with open(path, "w") as f:
            f.write(text)
        with open(STATE, "w") as f:
            json.dump(new_state, f, indent=1)
        print(f"Saved live_arena/weekly/{os.path.basename(path)}")


if __name__ == "__main__":
    main()
