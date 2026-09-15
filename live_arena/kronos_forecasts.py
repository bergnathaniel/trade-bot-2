"""Kronos forecasts for the Live Arena speed test (SPEED_TEST.md). Paper money only: nothing here can trade.

Kronos (Shi et al., AAAI 2026; github.com/shiyu-coder/Kronos, MIT license) is an open-source AI model pre-trained on
price candles from 45+ exchanges. Kronos-small came out in 2025, so it has never seen the 2026 weeks tested here.

For every hour of a week and every market in the speed test, it reads that market's last hourly candles (built from
the saved 5-minute candles, using only candles that had already closed) and forecasts the next 8 hourly candles. The
forecasts go to data/speed/outside/kronos_<group>.json, stamped with the moment they could first be known: the close
of the last hour they used. The Kronos bots (kronos_bots.js) read them. Each saved row is
[time, 1-hour forecast return, 4-hour forecast return, lowest forecast low within 8 hours, 8-hour forecast return,
None, 0], every return measured from the last close Kronos saw.

Run with the separate Python environment that has PyTorch (speed_test.py does this every week when it exists):
    live_arena/kronos/venv/bin/python live_arena/kronos_forecasts.py --week 2026-08-31
"""
import argparse
import datetime
import json
import os
import sys
import time
import zoneinfo

ROOT = os.path.dirname(os.path.abspath(__file__))
KRONOS = os.path.join(ROOT, "kronos")
os.environ.setdefault("HF_HOME", os.path.join(KRONOS, "hf"))   # the model files, downloaded once into live_arena/kronos/hf
os.environ.setdefault("HF_HUB_OFFLINE", "1")                    # a forecast run never goes online
sys.path.insert(0, KRONOS)

import pandas as pd  # noqa: E402
import torch  # noqa: E402
from model import Kronos, KronosPredictor, KronosTokenizer  # noqa: E402  the model code from the Kronos repository

DATA = os.path.join(ROOT, "data", "speed")
OUTSIDE = os.path.join(DATA, "outside")
NEW_YORK = zoneinfo.ZoneInfo("America/New_York")
HOUR = 3600
LOOKBACK = {"crypto": 160, "stocks": 140}   # hourly candles of history in each forecast
PRED_LEN = 8                                 # hourly candles forecast
SAMPLES = 4                                  # forecast paths averaged for each market


def hourly(rows, group):
    """Hourly candles from 5-minute ones, as [start, end, open, high, low, close, volume]: UTC hours for crypto, and
    New York session hours from 9:30 for stocks (the last one runs from 3:30 to 4 pm)."""
    bars = {}
    for t, o, h, l, c, _, v in rows:
        if group == "crypto":
            start = t // HOUR * HOUR
            end = start + HOUR
        else:
            ny = datetime.datetime.fromtimestamp(t, NEW_YORK)
            session = int(ny.replace(hour=9, minute=30, second=0, microsecond=0).timestamp())
            start = session + (t - session) // HOUR * HOUR
            end = min(start + HOUR, int(ny.replace(hour=16, minute=0, second=0, microsecond=0).timestamp()))
        bar = bars.get(start)
        if bar is None:
            bars[start] = [start, end, o, h, l, c, v or 0]
        else:
            bar[3], bar[4], bar[5], bar[6] = max(bar[3], h), min(bar[4], l), c, bar[6] + (v or 0)
    return [bars[k] for k in sorted(bars)]


def clock(t, group):
    """The date and time Kronos sees for a candle: UTC for crypto, New York time for stocks."""
    zone = datetime.timezone.utc if group == "crypto" else NEW_YORK
    return datetime.datetime.fromtimestamp(t, zone).replace(tzinfo=None)


def next_starts(end, group, n):
    """Start times of the n hourly candles that follow a candle ending at `end` (stocks skip nights and weekends)."""
    if group == "crypto":
        return [end + k * HOUR for k in range(n)]
    out, day = [], datetime.datetime.fromtimestamp(end, NEW_YORK).date()
    while len(out) < n:
        if day.weekday() < 5:
            session = int(datetime.datetime(day.year, day.month, day.day, 9, 30, tzinfo=NEW_YORK).timestamp())
            out += [s for s in (session + k * HOUR for k in range(7)) if s >= end]
        day += datetime.timedelta(days=1)
    return out[:n]


def load_saved(group):
    path = os.path.join(OUTSIDE, f"kronos_{group}.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return {s: {r[0]: r for r in rows} for s, rows in json.load(f)["result"].items()}


def save(group, table):
    path = os.path.join(OUTSIDE, f"kronos_{group}.json")
    with open(path + ".tmp", "w") as f:
        json.dump({"error": [], "result": {s: [rows[k] for k in sorted(rows)] for s, rows in sorted(table.items())}}, f, separators=(",", ":"))
    os.replace(path + ".tmp", path)


def main():
    ap = argparse.ArgumentParser(description="Kronos's hourly forecasts for one week of the speed test (paper money only).")
    ap.add_argument("--week", required=True, metavar="YYYY-MM-DD", help="the Monday that starts the week, in UTC")
    ap.add_argument("--force", action="store_true", help="recompute forecasts that were already saved")
    args = ap.parse_args()
    day = datetime.date.fromisoformat(args.week)
    start = int(datetime.datetime(day.year, day.month, day.day, tzinfo=datetime.timezone.utc).timestamp())
    stop = start + 7 * 86400
    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base").eval()
    model = Kronos.from_pretrained("NeoQuasar/Kronos-small").eval()
    predictor = KronosPredictor(model, tokenizer, device="cpu", max_context=512)   # the CPU repeats forecasts exactly on a rerun
    with open(os.path.join(DATA, "manifest.json")) as f:
        groups = json.load(f)["groups"]
    for g in groups:
        group, look, began, made = g["id"], LOOKBACK[g["id"]], time.time(), 0
        series = {}
        for s in g["symbols"]:
            try:
                with open(os.path.join(DATA, group, f"{s}_5.json")) as f:
                    series[s] = hourly(json.load(f)["result"][s], group)
            except (OSError, KeyError, ValueError):
                continue
        index = {s: {b[1]: j for j, b in enumerate(bars)} for s, bars in series.items()}
        table = load_saved(group)
        ends = sorted({b[1] for bars in series.values() for b in bars if start <= b[1] <= stop and b[1] <= time.time()})
        for end in ends:
            batch = []
            for s, bars in series.items():
                j = index[s].get(end)
                if j is None or j + 1 < look or (end in table.get(s, {}) and not args.force):
                    continue
                batch.append((s, bars[j + 1 - look:j + 1]))
            if not batch:
                continue
            frames, x_times, y_times = [], [], []
            for s, window in batch:
                df = pd.DataFrame([b[2:7] for b in window], columns=["open", "high", "low", "close", "volume"])
                df["amount"] = df["volume"] * df["close"]
                frames.append(df)
                x_times.append(pd.Series([clock(b[0], group) for b in window]))
                y_times.append(pd.Series([clock(t, group) for t in next_starts(end, group, PRED_LEN)]))
            torch.manual_seed(end)   # the forecast paths are random; seeding by the hour makes reruns repeatable
            preds = predictor.predict_batch(frames, x_times, y_times, pred_len=PRED_LEN, T=1.0, top_k=0, top_p=0.9,
                                            sample_count=SAMPLES, verbose=False)
            for (s, window), p in zip(batch, preds):
                last, close, low = window[-1][5], p["close"].to_numpy(), p["low"].to_numpy()
                table.setdefault(s, {})[end] = [end, float(close[0] / last - 1), float(close[3] / last - 1),
                                                float(low.min() / last - 1), float(close[PRED_LEN - 1] / last - 1), None, 0]
                made += 1
        save(group, table)
        print(f"Kronos: {made} new {group} forecasts for the week of {args.week} in {time.time() - began:.0f} seconds", file=sys.stderr)


if __name__ == "__main__":
    main()
