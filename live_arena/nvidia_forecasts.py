"""NVIDIA Reasoner's daily calls for the Live Arena speed test (SPEED_TEST.md). Paper money only.

Unlike Kronos (kronos_forecasts.py), a model actually trained to forecast prices, this asks a
general-purpose LLM hosted free by NVIDIA (build.nvidia.com's NIM API) to look at a coin's recent
daily prices and call BUY, HOLD or SELL, with one sentence of reasoning - the same job Track Record's
hard-coded signals do, done by asking a model to think about it instead.

Crypto only (stocks would add market-hours bookkeeping for no real benefit) and once a day per coin,
not per candle: the speed test runs thousands of candle-decisions a week, and an LLM API call isn't
meant for that. Calls go to data/speed/outside/nvidia_crypto.json, keyed by the UTC day's start,
stamped with the moment they could first be known: that day's close. nvidia_bots.js reads them.

Needs NVIDIA_API_KEY set in the environment (sign up free at build.nvidia.com, generate a key there,
set it yourself - never paste it into a chat). If it isn't set, this step is skipped with a message,
the same way kronos_forecasts.py is skipped when its PyTorch environment isn't installed.

Run (speed_test.py does this every week when the key is set):
    python3 live_arena/nvidia_forecasts.py --week 2026-08-31

Unlike Kronos, which runs locally and reproduces exactly on a rerun (`torch.manual_seed`), this calls
a live model over the network - a rerun of the same day may not give the same call. That's inherent
to this test, not a bug.
"""
import argparse
import datetime
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data", "speed")
OUTSIDE = os.path.join(DATA, "outside")
DAY = 86400
LOOKBACK_DAYS = 14
GROUP = "crypto"
API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = os.environ.get("NVIDIA_MODEL", "meta/llama-3.2-11b-vision-instruct")  # confirmed enabled on the free-tier account this was built with

try:  # python.org builds on macOS ship without CA certs (same fallback as server.py)
    import certifi
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CTX = ssl.create_default_context(
        cafile="/etc/ssl/cert.pem" if os.path.exists("/etc/ssl/cert.pem") else None)


def daily_bars(rows):
    """Full UTC calendar days from 5-minute candles, as [day_start, open, high, low, close, None, volume]."""
    bars = {}
    for t, o, h, l, c, _, v in rows:
        start = t // DAY * DAY
        bar = bars.get(start)
        if bar is None:
            bars[start] = [start, o, h, l, c, None, v or 0]
        else:
            bar[2], bar[3], bar[4], bar[6] = max(bar[2], h), min(bar[3], l), c, bar[6] + (v or 0)
    return [bars[k] for k in sorted(bars)]


def prompt_for(symbol, bars, j):
    """bars[j] is the day being decided; uses bars[j-LOOKBACK_DAYS:j+1] only - nothing after that day's close."""
    window = bars[max(0, j - LOOKBACK_DAYS):j + 1]
    closes = ", ".join(f"${b[4]:,.4f}" for b in window)
    close = window[-1][4]
    chg1 = close / window[-2][4] - 1 if len(window) >= 2 else None
    chg7 = close / window[-8][4] - 1 if len(window) >= 8 else None
    chg14 = close / window[0][4] - 1 if len(window) >= 15 else None

    def pct(x):
        return "n/a" if x is None else f"{x * 100:+.1f}%"

    return (
        f"You are looking at daily price data for {symbol}, a cryptocurrency traded on Coinbase.\n"
        f"Daily closes, oldest first: {closes}.\n"
        f"Today's close: ${close:,.4f}. Change over 1 day: {pct(chg1)}. Over 7 days: {pct(chg7)}. Over 14 days: {pct(chg14)}.\n\n"
        "Based only on this price history, should a trader BUY, HOLD (stay in cash / do nothing), or SELL "
        "(if already holding)? Respond in exactly this format, nothing else:\n"
        "ACTION: BUY, HOLD, or SELL\n"
        "REASON: one short sentence.\n"
        "Do not use any information beyond what is given above - no news, no knowledge of what happened after this date."
    )


def call_nvidia(prompt, api_key, seed):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2, "max_tokens": 120, "seed": seed,
    }).encode()
    req = urllib.request.Request(API_URL, data=body, method="POST", headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30, context=SSL_CTX) as r:
        j = json.load(r)
    return j["choices"][0]["message"]["content"]


def parse(text):
    m_act = re.search(r"ACTION:\s*(BUY|HOLD|SELL)", text, re.I)
    m_reason = re.search(r"REASON:\s*(.+)", text, re.I)
    action = m_act.group(1).lower() if m_act else "hold"
    reason = m_reason.group(1).strip() if m_reason else "(could not parse the model's response)"
    return action, reason[:300]


def load_saved():
    path = os.path.join(OUTSIDE, f"nvidia_{GROUP}.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return {s: {r[0]: r for r in rows} for s, rows in json.load(f)["result"].items()}


def save(table):
    path = os.path.join(OUTSIDE, f"nvidia_{GROUP}.json")
    with open(path + ".tmp", "w") as f:
        json.dump({"error": [], "result": {s: [rows[k] for k in sorted(rows)] for s, rows in sorted(table.items())}}, f)
    os.replace(path + ".tmp", path)


def main():
    ap = argparse.ArgumentParser(description="NVIDIA Reasoner's daily calls for one week of the speed test (paper money only).")
    ap.add_argument("--week", required=True, metavar="YYYY-MM-DD", help="the Monday that starts the week, in UTC")
    ap.add_argument("--force", action="store_true", help="recompute calls that were already saved")
    args = ap.parse_args()

    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        print("NVIDIA Reasoner: NVIDIA_API_KEY isn't set, so no calls were made this week.", file=sys.stderr)
        return

    day0 = datetime.date.fromisoformat(args.week)
    start = int(datetime.datetime(day0.year, day0.month, day0.day, tzinfo=datetime.timezone.utc).timestamp())
    stop = start + 7 * DAY
    with open(os.path.join(DATA, "manifest.json")) as f:
        groups = json.load(f)["groups"]
    group = next(g for g in groups if g["id"] == GROUP)

    table, made, problems = load_saved(), 0, []
    began = time.time()
    for s in group["symbols"]:
        try:
            with open(os.path.join(DATA, GROUP, f"{s}_5.json")) as f:
                bars = daily_bars(json.load(f)["result"][s])
        except (OSError, KeyError, ValueError) as e:
            problems.append(f"{s}: no candles ({e})")
            continue
        for j, bar in enumerate(bars):
            day_start = bar[0]
            if not (start <= day_start < stop) or day_start + DAY > time.time():
                continue
            if day_start in table.get(s, {}) and not args.force:
                continue
            if j < 1:   # needs at least yesterday's close to say anything about a change
                continue
            try:
                text = call_nvidia(prompt_for(s, bars, j), api_key, seed=day_start)
                action, reason = parse(text)
                table.setdefault(s, {})[day_start] = [day_start, action, reason]
                made += 1
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, ValueError) as e:
                problems.append(f"{s} {datetime.datetime.fromtimestamp(day_start, datetime.timezone.utc).date()}: {e}")
            time.sleep(1.0)   # polite pacing for a free-tier API
    save(table)
    print(f"NVIDIA Reasoner: {made} new calls for the week of {args.week} in {time.time() - began:.0f} seconds", file=sys.stderr)
    for p in problems:
        print(f"  problem: {p}", file=sys.stderr)


if __name__ == "__main__":
    main()
