"""Speed test for Live Arena: every bot paper-trades one week of 5- and 15-minute candles (rules in SPEED_TEST.md).

A round is one Monday-to-Monday week (UTC). A bot passes a round only if it closed at least 10 trades, made money after
fees, beat just holding (a tie doesn't count), made money in more than half the markets, and its timing beat at least
95% of the same trades slid to other times. Weeks that start before the first forward week are practice. A bot "works so far" once it passes
3 forward weeks in a row in the same market and candle size.

Run:  python3 live_arena/speed_test.py                     the most recent complete week
      python3 live_arena/speed_test.py --week 2026-08-31   a specific week, named by its Monday
It collects the candles (Coinbase for crypto, Yahoo Finance for stocks), runs every bot in headless Chrome, saves
speed/results/<week>.json and speed/<week>.md, and prints the report. Paper money only: nothing here can trade.
"""
import argparse
import datetime
import http.server
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import zoneinfo

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import server  # noqa: E402  the app's own server, started below on a free port

DATA = os.path.join(ROOT, "data", "speed")
SPEED = os.path.join(ROOT, "speed")
OUTSIDE = os.path.join(DATA, "outside")
NEW_YORK = zoneinfo.ZoneInfo("America/New_York")
STEP = 300   # seconds in a 5-minute candle
TIMEOUT = 1800
KRONOS_PYTHON = os.path.join(ROOT, "kronos", "venv", "bin", "python")   # the separate environment with PyTorch, for Kronos
BROWSERS = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"]
# The rules, written before the first forward week. The app reads them from data/speed/manifest.json.
RULES = {
    "groups": [
        {"id": "crypto", "name": "Crypto", "unit": "coin", "fee": "0.25", "ref": "BTC-USD", "source": "coinbase",
         "outside": ["fear_greed", "dvol_btc", "funding_btc", "taker_btc", "kronos", "nvidia"],
         "symbols": ["BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD", "ADA-USD", "LINK-USD", "AVAX-USD",
                     "LTC-USD", "DOT-USD", "BCH-USD", "SUI-USD"]},
        {"id": "stocks", "name": "US stocks and ETFs", "unit": "stock", "fee": "0.02", "ref": None, "source": "yahoo",
         "outside": ["vix", "vix9d", "kronos"],
         "symbols": ["SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL", "AMD",
                     "NFLX", "AVGO", "PLTR", "COIN", "MSTR", "JPM", "GLD", "TLT"]},
        # Added 2026-09-23 (SPEED_TEST.md amendment). Picked by a fixed rule, not by performance: on Web Picks' meme
        # list, a Coinbase USD market that's online, and a 7-day average of $250k+ traded a day on 2026-09-23. DOGE is
        # already in the crypto group. Counts from the week of 2026-09-28 ("from"). No Kronos: it's slow and built
        # for the other two groups.
        {"id": "memes", "name": "Meme coins", "unit": "coin", "fee": "0.25", "ref": None, "source": "coinbase",
         "from": "2026-09-28", "outside": ["fear_greed", "dvol_btc", "funding_btc", "taker_btc"],
         "symbols": ["SHIB-USD", "PEPE-USD", "BONK-USD", "WIF-USD", "FLOKI-USD", "TRUMP-USD", "PENGU-USD",
                     "POPCAT-USD", "FARTCOIN-USD", "MOODENG-USD", "SPX-USD"]},
    ],
    "timeframes": ["5", "15"],
    "per_tf_outside": ["vix", "vix9d"],   # outside series saved once per candle size (<name>_5.json, <name>_15.json)
    "warmup_days": 7,
    "shifts": 99,
    "min_closed_trades": 10,
    "timing_share": 0.95,
    "first_forward_week": "2026-09-14",
    "streak_to_work": 3,
    "history_from": "2026-07-20",
    "stopping_week": "2026-11-02",   # the last forward week that counts; its report, due 2026-11-09, decides (SPEED_TEST.md)
    # bots added after a forward week had begun, and the first week that counts for them (team_bots.js, 2026-09-13;
    # selftune_bots.js and track_record_bot.js, 2026-09-14/15; nvidia_bots.js, 2026-09-22; hour_bots.js, 2026-09-28)
    "joined": {**{bot: "2026-09-21" for bot in ["worstcoin24", "bottom3day", "leftbehind", "kronosdip", "kronosallup", "kronosteam",
                                                 "bouncecrew", "timerscrew", "calmstorm", "seconddip", "rand24h", "pairlaggard",
                                                 "kronostop", "kronostop3", "kronosbottom", "selftuner", "trackrecord"]},
               "nvidiareasoner": "2026-09-22", "btc22utc": "2026-09-28"},
}
CANDLES = {"5": "5-minute", "15": "15-minute"}
RANDOM_CONTROLS = ("coin", "randomexit", "opposite", "rand8h", "rand1h", "coinfair", "rand24h")   # controls built to have no edge


def iso(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(url):
    for attempt in range(4):
        try:
            return server.fetch_json(url)
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 + 3 * attempt)


def coinbase_5m(product, start, end):
    """Coinbase's 5-minute candles starting in [start, end), 300 per request, oldest first, in the app's row layout."""
    rows, t = {}, start
    while t < end:
        stop = min(t + 300 * STEP, end)
        url = f"https://api.exchange.coinbase.com/products/{product}/candles?granularity={STEP}&start={iso(t)}&end={iso(stop - STEP)}"
        for c in fetch(url):
            if start <= c[0] < end:
                rows[c[0]] = [c[0], c[3], c[2], c[1], c[4], None, c[5]]
        t = stop
        time.sleep(0.25)
    return [rows[k] for k in sorted(rows)]


def yahoo_5m(symbol):
    """Yahoo's last 60 days of 5-minute candles, regular trading hours only (9:30 am to 4 pm New York time)."""
    j = fetch(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=60d&interval=5m&includePrePost=false")
    result = (j.get("chart") or {}).get("result")
    if not result:
        raise ValueError(f"no data for {symbol}")
    quote, rows = result[0]["indicators"]["quote"][0], []
    for k, t in enumerate(result[0].get("timestamp") or []):
        o, h, l, c, v = (quote[f][k] for f in ("open", "high", "low", "close", "volume"))
        ny = datetime.datetime.fromtimestamp(t, NEW_YORK)
        if None in (o, h, l, c) or min(o, h, l, c) <= 0 or h < l or not (9 * 60 + 30 <= ny.hour * 60 + ny.minute < 16 * 60):
            continue
        rows.append([t, o, h, l, c, None, v or 0])
    return rows


def fill_gaps(rows, step):
    """Coinbase skips 5-minute stretches with no trades. Fill them with the last close so every candle exists."""
    out = []
    for r in rows:
        while out and r[0] - out[-1][0] > step:
            c = out[-1][4]
            out.append([out[-1][0] + step, c, c, c, c, None, 0])
        out.append(r)
    return out


def resample(rows, step):
    out = []
    for t, o, h, l, c, _, v in rows:
        bucket = t // step * step
        if out and out[-1][0] == bucket:
            last = out[-1]
            last[2], last[3], last[4], last[6] = max(last[2], h), min(last[3], l), c, last[6] + v
        else:
            out.append([bucket, o, h, l, c, None, v])
    return out


def path_of(group, symbol, tf):
    return os.path.join(DATA, group, f"{symbol}_{tf}.json")


def load(group, symbol):
    path = path_of(group, symbol, "5")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)["result"][symbol]


def save(group, symbol, tf, rows):
    os.makedirs(os.path.join(DATA, group), exist_ok=True)
    with open(path_of(group, symbol, tf), "w") as f:
        json.dump({"error": [], "result": {symbol: rows}}, f, separators=(",", ":"))


def save_series(name, symbol, rows):
    os.makedirs(OUTSIDE, exist_ok=True)
    with open(os.path.join(OUTSIDE, f"{name}.json"), "w") as f:
        json.dump({"error": [], "result": {symbol: rows}}, f, separators=(",", ":"))


def load_series(name, symbol):
    path = os.path.join(OUTSIDE, f"{name}.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)["result"][symbol]


def as_row(t, value):   # a single number stored as a flat candle, so the app's loader can read it
    return [t, value, value, value, value, None, 0]


def collect_outside(start, end):
    """The outside signals some bots read: VIX and VIX9D, crypto Fear & Greed, and bitcoin's implied volatility, funding rate and taker volume."""
    problems, oldest = [], start - RULES["warmup_days"] * 86400 - 86400
    try:   # VIX (the S&P 500 options fear gauge), 5-minute candles in regular hours, from Yahoo
        rows = {r[0]: r for r in load_series("vix_5", "^VIX")}
        rows.update({r[0]: r for r in yahoo_5m("^VIX")})
        vix = [rows[k] for k in sorted(rows)]
        save_series("vix_5", "^VIX", vix)
        save_series("vix_15", "^VIX", resample(vix, 900))
    except Exception as e:
        problems.append(f"VIX: {e}")
    try:   # the Crypto Fear & Greed Index, one value a day, from alternative.me
        days = fetch("https://api.alternative.me/fng/?limit=0&format=json")["data"]
        save_series("fear_greed", "FNG", sorted(as_row(int(d["timestamp"]), int(d["value"])) for d in days))
    except Exception as e:
        problems.append(f"Fear & Greed: {e}")
    try:   # bitcoin's 30-day implied volatility index (DVOL), hourly, from Deribit
        rows, stop = {r[0]: r for r in load_series("dvol_btc", "DVOL")}, end * 1000
        for _ in range(20):
            res = fetch(f"https://www.deribit.com/api/v2/public/get_volatility_index_data?currency=BTC&resolution=3600"
                        f"&start_timestamp={oldest * 1000}&end_timestamp={stop}")["result"]
            for ms, o, h, l, c in res["data"]:
                rows[ms // 1000] = [ms // 1000, o, h, l, c, None, 0]
            if not res.get("continuation") or res["continuation"] <= oldest * 1000:
                break
            stop = res["continuation"]
            time.sleep(0.25)
        save_series("dvol_btc", "DVOL", [rows[k] for k in sorted(rows)])
    except Exception as e:
        problems.append(f"DVOL: {e}")
    try:   # bitcoin perpetual swap funding rate (BTC-USDT on OKX), settled every 8 hours
        rows, after = {r[0]: r for r in load_series("funding_btc", "FUNDING")}, ""
        for _ in range(20):
            page = fetch("https://www.okx.com/api/v5/public/funding-rate-history?instId=BTC-USDT-SWAP&limit=100" + (f"&after={after}" if after else ""))["data"]
            if not page:
                break
            for x in page:
                t = int(x["fundingTime"]) // 1000
                rows[t] = as_row(t, float(x.get("realizedRate") or x["fundingRate"]))
            after = page[-1]["fundingTime"]
            if int(after) // 1000 <= oldest:
                break
            time.sleep(0.25)
        save_series("funding_btc", "FUNDING", [rows[k] for k in sorted(rows)])
    except Exception as e:
        problems.append(f"funding: {e}")
    try:   # VIX9D (the same fear gauge for the next 9 days instead of 30), 5-minute candles in regular hours, from Yahoo
        rows = {r[0]: r for r in load_series("vix9d_5", "^VIX9D")}
        rows.update({r[0]: r for r in yahoo_5m("^VIX9D")})
        vix9d = [rows[k] for k in sorted(rows)]
        save_series("vix9d_5", "^VIX9D", vix9d)
        save_series("vix9d_15", "^VIX9D", resample(vix9d, 900))
    except Exception as e:
        problems.append(f"VIX9D: {e}")
    try:   # hourly taker volume on bitcoin's perpetual swaps (OKX keeps 30 days), stamped at the hour's start
        rows = {r[0]: r for r in load_series("taker_btc", "TAKER")}
        for ts, sold, bought in fetch("https://www.okx.com/api/v5/rubik/stat/taker-volume?ccy=BTC&instType=CONTRACTS&period=1H")["data"]:
            t, s, b = int(ts) // 1000, float(sold), float(bought)
            if t + 3600 <= time.time():   # finished hours only; open = seller-initiated volume, close = buyer-initiated
                rows[t] = [t, s, max(s, b), min(s, b), b, None, s + b]
        save_series("taker_btc", "TAKER", [rows[k] for k in sorted(rows)])
    except Exception as e:
        problems.append(f"taker volume: {e}")
    return problems


def collect(start, end):
    """Make sure every market has 5- and 15-minute candles from the warm-up through the end of the week."""
    need_from, problems = start - RULES["warmup_days"] * 86400, []
    for g in RULES["groups"]:
        for symbol in g["symbols"]:
            stored = {r[0]: r for r in load(g["id"], symbol)}
            try:
                if g["source"] == "coinbase":
                    have = sorted(stored)
                    if not have or have[0] > need_from or have[-1] < end - STEP:
                        stored.update({r[0]: r for r in coinbase_5m(symbol, need_from, end)})
                    rows = fill_gaps([stored[k] for k in sorted(stored)], STEP)
                else:
                    stored.update({r[0]: r for r in yahoo_5m(symbol)})
                    rows = [stored[k] for k in sorted(stored)]
            except Exception as e:
                problems.append(f"{symbol}: {e}")
                rows = [stored[k] for k in sorted(stored)]
            save(g["id"], symbol, "5", rows)
            save(g["id"], symbol, "15", resample(rows, 900))
            print(f"  {symbol}: {len(rows)} 5-minute candles", file=sys.stderr)
    problems += collect_outside(start, end)
    with open(os.path.join(DATA, "manifest.json"), "w") as f:
        json.dump(RULES, f, indent=1)
    return problems


def kronos_forecasts(week):
    """Kronos's hourly forecasts for the week (kronos_forecasts.py), when its Python environment is installed."""
    if not os.path.exists(KRONOS_PYTHON):
        return ["Kronos forecasts: live_arena/kronos/venv isn't installed, so the Kronos bots had nothing to read"]
    print("Computing Kronos's forecasts...", file=sys.stderr)
    try:
        subprocess.run([KRONOS_PYTHON, os.path.join(ROOT, "kronos_forecasts.py"), "--week", week.isoformat()], check=True, timeout=6 * 3600)
        return []
    except Exception as e:
        return [f"Kronos forecasts: {e}"]


def nvidia_forecasts(week):
    """NVIDIA Reasoner's daily calls for the week (nvidia_forecasts.py), when NVIDIA_API_KEY is set."""
    if not os.environ.get("NVIDIA_API_KEY"):
        return ["NVIDIA Reasoner: NVIDIA_API_KEY isn't set, so it had nothing to read this week"]
    print("Computing NVIDIA Reasoner's calls...", file=sys.stderr)
    try:
        subprocess.run([sys.executable, os.path.join(ROOT, "nvidia_forecasts.py"), "--week", week.isoformat()], check=True, timeout=1800)
        return []
    except Exception as e:
        return [f"NVIDIA Reasoner: {e}"]


def run_bots(week):
    """Serve the app on a free port, open it at ?speed=<week> in headless Chrome, and wait for the results it posts."""
    browser = next((b for b in BROWSERS if os.path.exists(b)), None) or shutil.which("google-chrome") or shutil.which("chromium")
    if not browser:
        sys.exit("No Chrome, Chromium, Edge or Brave found. The speed test runs the app's bots in a headless browser.")
    target = os.path.join(SPEED, "results", f"{week}.json")
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    profile, started = tempfile.mkdtemp(prefix="live-arena-speed-"), time.time()
    chrome = subprocess.Popen([browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check", "--mute-audio",
                               f"--user-data-dir={profile}", f"http://127.0.0.1:{httpd.server_address[1]}/?speed={week}"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        while time.time() - started < TIMEOUT:
            if os.path.exists(target) and os.path.getmtime(target) >= started:
                with open(target) as f:
                    return json.load(f)
            if chrome.poll() is not None:
                sys.exit("Headless Chrome closed before the speed test finished.")
            time.sleep(3)
        sys.exit(f"The speed test didn't finish within {TIMEOUT // 60} minutes.")
    finally:
        chrome.terminate()
        try:
            chrome.wait(timeout=10)
        except subprocess.TimeoutExpired:
            chrome.kill()
        httpd.shutdown()
        shutil.rmtree(profile, ignore_errors=True)


def pct(x, dp=1):
    return "–" if x is None else f"{x * 100:+.{dp}f}%"


def counts_from(bot_id, group_id):
    """The first week a bot's result in a market counts: after both the bot and the market joined."""
    g = next((g for g in RULES["groups"] if g["id"] == group_id), {})
    return max(RULES.get("joined", {}).get(bot_id, RULES["first_forward_week"]), g.get("from", RULES["first_forward_week"]))


def streaks(week):
    """Forward weeks passed in a row, ending with `week`, for each (bot, market, candle size)."""
    counts, alive, day = {}, None, datetime.date.fromisoformat(week)
    first = datetime.date.fromisoformat(RULES["first_forward_week"])
    while day >= first:
        path = os.path.join(SPEED, "results", f"{day}.json")
        if not os.path.exists(path):
            break
        with open(path) as f:
            res = json.load(f)
        if res.get("error"):
            break
        # bots or markets added after a forward week began only count from the week they joined
        passed = {(b["id"], g["group"], g["tf"]) for g in res["groups"] for b in g["bots"]
                  if b["pass"] and counts_from(b["id"], g["group"]) <= day.isoformat()}
        alive = passed if alive is None else alive & passed
        if not alive:
            break
        for key in alive:
            counts[key] = counts.get(key, 0) + 1
        day -= datetime.timedelta(days=7)
    return counts


def report(week, res, problems):
    practice = week < RULES["first_forward_week"]
    n_markets = sum(len(g["symbols"]) for g in RULES["groups"])
    lines = [f"# Speed test: week of {week}{' (practice)' if practice else ''}", "",
             f"Paper money only. All {res['bot_count']} bots traded {iso(res['start'])[:10]} to {iso(res['end'])[:10]} (UTC) in {n_markets} markets "
             "on 5- and 15-minute candles, filling at the next candle's open and paying fees.", "",
             f"To pass the week, a bot needs all five: at least {RULES['min_closed_trades']} closed trades (a buy and its sale); made money after fees; "
             f"beat just holding (a tie doesn't count); made money in more than half the markets; and its timing beat at least "
             f"{round(RULES['timing_share'] * 100)}% of the same trades slid to other times.", ""]
    lines.append("This week is practice: it came before the rules were frozen, so it doesn't count toward a streak." if practice else
                 f"A bot works so far once it passes {RULES['streak_to_work']} forward weeks in a row in the same market and candle size.")
    lines += ["", "## Summary", "",
              "| Market | Candles | Fee | Just holding | Bots that lost money | Bots that passed | Controls that passed |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for g in res["groups"]:
        bots, controls = [b for b in g["bots"] if not b["control"]], [b for b in g["bots"] if b["control"]]
        lines.append(f"| {g['name']} ({len(g['markets'])}) | {CANDLES[g['tf']]} | {g['fee']}% | {pct(g['hold'], 2)} | "
                     f"{sum(1 for b in bots if not b['avg'] > 0)} of {len(bots)} | {sum(b['pass'] for b in bots)} of {len(bots)} | "
                     f"{sum(b['pass'] for b in controls)} of {len(controls)} |")
    counts = {} if practice else streaks(week)
    passed = sorted(((g, b) for g in res["groups"] for b in g["bots"] if b["pass"] and not b["control"]), key=lambda x: -x[1]["avg"])
    lines += ["", "## Bots that passed this week", ""]
    if passed:
        lines += ["| Bot | Market | Candles | Average | Made money in | Closed trades | Timing beat | Forward weeks in a row |",
                  "|---|---|---|---:|---:|---:|---:|---:|"]
        lines += [f"| {b['name']} | {g['name']} | {CANDLES[g['tf']]} | {pct(b['avg'], 2)} | {b['up']} of {len(g['markets'])} | {b['closed']} | "
                  f"{round(b['timing'] * 100)}% | {'practice' if practice else 'joined later' if counts_from(b['id'], g['group']) > week else counts.get((b['id'], g['group'], g['tf']), 1)} |" for g, b in passed]
    else:
        lines.append("None.")
    if not practice:
        names = {(b["id"], g["group"], g["tf"]): (b["name"], g["name"], CANDLES[g["tf"]]) for g in res["groups"] for b in g["bots"]}
        works = sorted((k for k, v in counts.items() if v >= RULES["streak_to_work"] and k in names), key=lambda k: -counts[k])
        lines += ["", f"## Working so far ({RULES['streak_to_work']}+ forward weeks in a row)", ""]
        lines += [f"- {names[k][0]} on {names[k][1]}, {names[k][2]} candles: {counts[k]} weeks in a row" for k in works] or ["None yet."]
        last = RULES["stopping_week"]
        due = (datetime.date.fromisoformat(last) + datetime.timedelta(days=7)).isoformat()
        if week < last:
            left = (datetime.date.fromisoformat(last) - datetime.date.fromisoformat(week)).days // 7
            lines += ["", f"Stopping point: {left} more forward week{'s' if left != 1 else ''} after this one. If no bot works so far "
                          f"in the report due {due} (the week of {last}), the answer is no (SPEED_TEST.md)."]
        elif week == last:
            lines += ["", "**Stopping point reached.** " + (
                f"{len(works)} bot{'s' if len(works) != 1 else ''} work{'' if len(works) != 1 else 's'} so far, so "
                f"{'they keep' if len(works) != 1 else 'it keeps'} paper trading with the rules unchanged, to see whether that holds up for months. "
                "That still isn't a reason to use real money." if works else
                "No bot works so far, so the speed test's answer is no: none of these bots showed a short-term edge. "
                "Per SPEED_TEST.md, stop adding bots and stop spending time on the speed test.")]
        else:
            lines += ["", f"This week comes after the stopping point (the week of {last}, reported {due}), so it doesn't change that decision."]
    lines += ["", "## Closest misses", "", "The five highest averages in each market and candle size that didn't pass, and why.", ""]
    for g in res["groups"]:
        misses = sorted((b for b in g["bots"] if not b["pass"] and not b["control"] and b["trades"] > 0), key=lambda b: -b["avg"])[:5]
        lines += [f"**{g['name']}, {CANDLES[g['tf']]}:** " + ("; ".join(f"{b['name']} {pct(b['avg'], 2)} ({', '.join(b['fails'])})" for b in misses) or "none."), ""]
    control_passes = [f"{b['name']} ({g['name']}, {CANDLES[g['tf']]})" for g in res["groups"] for b in g["bots"] if b["pass"] and b["control"]]
    control_names = sorted({b["name"] for g in res["groups"] for b in g["bots"] if b["control"]})
    lines.append(f"Controls ({', '.join(control_names)}) that passed, which would mean the bar is too easy: "
                 + (", ".join(control_passes) if control_passes else "none") + ".")
    missing = [f"{s} ({g['name']}, {CANDLES[g['tf']]})" for g in res["groups"] for s in g["missing"]]
    if missing or problems:
        lines += ["", "Data problems: " + "; ".join(problems + [f"no candles for {m}" for m in missing]) + "."]
    return "\n".join(lines) + "\n"


def history_report(weeks):
    """Every week side by side, and whether the bots that passed look like more than luck."""
    tally, names, per_week = {}, {}, []
    for w in weeks:
        with open(os.path.join(SPEED, "results", f"{w}.json")) as f:
            res = json.load(f)
        row = {"week": w}
        for g in res["groups"]:
            row[f"{g['name']}, {CANDLES[g['tf']]}"] = sum(1 for b in g["bots"] if b["pass"] and not b["control"])
            for b in g["bots"]:
                key = (b["id"], g["group"], g["tf"])
                names[key] = (b["name"], g["name"], CANDLES[g["tf"]], b["control"], b["id"])
                tally.setdefault(key, {})[w] = b["pass"]
        per_week.append(row)
    bots = {k: v for k, v in tally.items() if not names[k][3]}
    randoms = {k: v for k, v in tally.items() if names[k][4] in RANDOM_CONTROLS}
    tries, passes = sum(len(v) for v in bots.values()), sum(sum(v.values()) for v in bots.values())
    rate, n = (passes / tries if tries else 0), len(weeks)
    luck_two = len(bots) * (1 - sum(math.comb(n, k) * rate ** k * (1 - rate) ** (n - k) for k in (0, 1))) if n >= 2 else 0
    counts = {k: sum(v.values()) for k, v in bots.items()}
    forward = [w for w in weeks if w >= RULES["first_forward_week"]]
    lines = [f"# Speed test history: {n} weeks, {weeks[0]} to {weeks[-1]}", "",
             "Paper money only. The weekly report's rules (SPEED_TEST.md), applied to every bot in every week. "
             + (f"{len(forward)} of these weeks are forward weeks." if forward else "All of these weeks are practice, so none count toward a streak."), "",
             "## Could this be luck?", "",
             f"- {len(bots)} contestants (a bot in one market at one candle size) had {tries:,} weekly chances and passed {passes} times ({rate * 100:.2f}%).",
             f"- If every pass were luck at that rate, about {luck_two:.1f} contestants would pass 2 or more of the {n} weeks by chance. "
             f"{sum(1 for c in counts.values() if c >= 2)} did.",
             f"- The controls built to have no edge ({', '.join(sorted({names[k][0] for k in randoms}))}) passed {sum(sum(v.values()) for v in randoms.values())} "
             f"of {sum(len(v) for v in randoms.values())} weekly chances.", "",
             "## Passed the most weeks", ""]
    top = sorted((k for k in counts if counts[k] >= 1), key=lambda k: (-counts[k], names[k][0]))[:20]
    if top:
        lines += ["| Bot | Market | Candles | Weeks passed | Which weeks |", "|---|---|---|---:|---|"]
        lines += [f"| {names[k][0]} | {names[k][1]} | {names[k][2]} | {counts[k]} of {len(bots[k])} | "
                  f"{', '.join(w[5:] for w, p in sorted(bots[k].items()) if p)} |" for k in top]
    else:
        lines.append("No bot passed any week.")
    labels = [label for label in per_week[0] if label != "week"]
    lines += ["", "## Bots that passed each week", "", "| Week | " + " | ".join(labels) + " |", "|---|" + "---:|" * len(labels)]
    lines += [f"| {r['week']} | " + " | ".join(str(r.get(label, "–")) for label in labels) + " |" for r in per_week]
    return "\n".join(lines) + "\n"


def run_week(week):
    start = int(datetime.datetime(week.year, week.month, week.day, tzinfo=datetime.timezone.utc).timestamp())
    print(f"Collecting candles for the week of {week}...", file=sys.stderr)
    problems = collect(start, start + 7 * 86400)
    problems += kronos_forecasts(week)
    problems += nvidia_forecasts(week)
    print("Running every bot in headless Chrome...", file=sys.stderr)
    res = run_bots(week.isoformat())
    if res.get("error"):
        sys.exit("The speed test failed in the browser:\n" + res["error"])
    text = report(week.isoformat(), res, problems)
    with open(os.path.join(SPEED, f"{week}.md"), "w") as f:
        f.write(text)
    return text


def main():
    ap = argparse.ArgumentParser(description="Live Arena speed test: every bot, one week, 5- and 15-minute candles (paper money only).")
    ap.add_argument("--week", metavar="YYYY-MM-DD", help="the Monday that starts the week, in UTC (default: the most recent complete week)")
    ap.add_argument("--history", action="store_true", help=f"run every complete week since {RULES['history_from']} and compare them in speed/history.md")
    args = ap.parse_args()
    now = datetime.datetime.now(datetime.timezone.utc)
    latest = now.date() - datetime.timedelta(days=now.weekday() + 7)
    if args.history:
        weeks, day = [], datetime.date.fromisoformat(RULES["history_from"])
        while day <= latest:
            weeks.append(day)
            day += datetime.timedelta(days=7)
        for w in weeks:
            run_week(w)
            print(f"Week of {w} done.", file=sys.stderr)
        text = history_report([w.isoformat() for w in weeks])
        with open(os.path.join(SPEED, "history.md"), "w") as f:
            f.write(text)
        print(text)
        print("Saved live_arena/speed/history.md")
        return
    week = datetime.date.fromisoformat(args.week) if args.week else latest
    if week.weekday() != 0:
        sys.exit("--week has to be a Monday.")
    if int(datetime.datetime(week.year, week.month, week.day, tzinfo=datetime.timezone.utc).timestamp()) + 7 * 86400 > now.timestamp():
        sys.exit(f"The week of {week} isn't over yet.")
    text = run_week(week)
    print(text)
    print(f"Saved live_arena/speed/{week}.md")


if __name__ == "__main__":
    main()
