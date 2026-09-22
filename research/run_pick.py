"""
Walk-forward stock picking: trade IBS Swing / Fisher Transform only on the micro-caps each did
best on recently (PREREG_PICK.md).
=====================================================================================================

    python3 research/run_pick.py

Prints PREREG_PICK.md's SHA-256, runs the integrity checks (must all pass before any result counts),
then the six-quarter walk-forward test on baskets C+D with its four controls and six gates, and writes
research/results/pick.json + research/PICK_RESULTS.md.
"""

import hashlib
import json
import math
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LA = os.path.abspath(os.path.join(HERE, "..", "live_arena"))
sys.path.insert(0, HERE)
sys.path.insert(0, LA)

import leakage  # noqa: E402
import pick_engine as pe  # noqa: E402
import server  # noqa: E402

PREREG = os.path.join(HERE, "PREREG_PICK.md")
REPRODUCE_FIXTURE = os.path.join(HERE, "pick_reproduce_check.json")
RESULTS = os.path.join(HERE, "results", "pick.json")
REPORT = os.path.join(HERE, "PICK_RESULTS.md")

FEE = 0.005
LOOKBACK, HORIZON, RANK_EVERY, TOP_N = 252, 63, 63, 10
N_RANDOM_DRAWS = 2000
RANDOM_SEED = 20260921
N_NOISE_UNIVERSES = 10
STRATS = ("ibs", "fisher")


# ---------------------------------------------------------------- integrity checks

def check_reproduces_app():
    """pick_engine.sim() must give the app's own basket-test numbers exactly (see run comment in
    PREREG_PICK.md section G). Uses the fixture pulled from the live app on basket A, fee 0.50%,
    next-open fills, 2026-09-22."""
    ref = json.load(open(REPRODUCE_FIXTURE))
    basket = json.load(open(os.path.join(LA, "basket.json")))
    syms = ["IWC"] + [s["symbol"] for s in basket["stocks"]]
    worst = 0.0
    for sym in syms:
        rows = server.yahoo_rows(sym, "1440")[:-1]  # drop the possibly-unfinished last candle, like the app does
        for strat in STRATS:
            got, _ = pe.sim(rows, strat, float(ref["fee"]) / 100, liquidate=False)
            want = ref["per"][sym][strat]
            worst = max(worst, abs(got - want))
    return {"ok": worst < 1e-6, "worst_abs_diff": worst, "n_checked": len(syms) * len(STRATS)}


def check_no_lookahead(rows):
    """Deleting all data after a rank date must never change that date's trailing-return score
    (leakage.truncation_test). rows: one representative stock's daily candles."""
    n = len(rows)

    def weights_fn(cut):
        sub = rows if cut is None else rows[:cut + 1]
        m = len(sub)
        out = [None] * n
        for t in range(min(m, n)):
            out[t] = pe.trailing_return(sub, t, "ibs", FEE)
        return out

    return leakage.truncation_test(weights_fn, n, lag=0, n_cuts=6, seed=5)


# ---------------------------------------------------------------- synthetic data (noise + planted-persistence checks)

def synthetic_stock(rng, n, drift=0.0002, vol=0.02, edge=None):
    """A random-walk daily OHLC series, n+1 candles so a[i+1]-open lines up. `edge`, if given, is a
    callable(i) -> extra expected next-day return conditioned on today's IBS reading, used only by the
    planted-persistence check so a real, findable effect exists somewhere to test against."""
    px = 20.0
    rows = []
    ibs_prev = 0.5
    for i in range(n + 1):
        r = rng.gauss(drift, vol)
        if edge is not None:
            r += edge(ibs_prev)
        o = px
        c = px * math.exp(r)
        hi = max(o, c) * (1 + abs(rng.gauss(0, vol * 0.3)))
        lo = min(o, c) * (1 - abs(rng.gauss(0, vol * 0.3)))
        lo = max(lo, 0.01)
        rows.append([i * 86400, o, hi, lo, c, None, 1_000_000])
        rng_ = hi - lo
        ibs_prev = (c - lo) / rng_ if rng_ > 0 else 0.5
        px = c
    return rows


def synthetic_universe(seed, n_stocks=60, n_bars=760, good_ids=None):
    """good_ids: indices of stocks given a small planted mean-reversion edge an IBS-style rule can
    actually find (bounces after a low-IBS close), everything else pure random walk."""
    rng = random.Random(seed)
    good_ids = good_ids or set()

    def edge_fn(ibs_prev):
        return 0.05 * (0.2 - ibs_prev) if ibs_prev < 0.2 else 0.0

    return [synthetic_stock(random.Random(seed * 1000 + i), n_bars, edge=edge_fn if i in good_ids else None)
            for i in range(n_stocks)]


# ---------------------------------------------------------------- the walk-forward procedure itself

def rank_dates(n):
    t = LOOKBACK + pe.WARMUP
    out = []
    while t + HORIZON < n:
        out.append(t)
        t += RANK_EVERY
    return out


def compound(rets):
    total = 1.0
    for r in rets:
        total *= (1 + r)
    return total - 1


def spearman(xs, ys):
    """xs, ys same length, no Nones. Simple rank correlation, ties averaged."""
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    n = len(xs)
    if n < 2:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    dx = math.sqrt(sum((x - mx) ** 2 for x in rx))
    dy = math.sqrt(sum((y - my) ** 2 for y in ry))
    return num / (dx * dy) if dx > 0 and dy > 0 else None


def hold_return(rows, t):
    """Zero-fee price return of buying at t's next open and selling at (t+HORIZON)'s close - the
    passive benchmark a trading rule has to beat."""
    return rows[t + HORIZON][4] / rows[t + 1][1] - 1


def run_walkforward(data, strat, index_rows=None, seed=RANDOM_SEED, n_draws=N_RANDOM_DRAWS):
    """data: {symbol: rows}, all the same length. Returns the full result dict for one strategy."""
    syms = sorted(data)
    n = len(next(iter(data.values())))
    dates = rank_dates(n)
    trail, fwd = {s: [] for s in syms}, {s: [] for s in syms}
    for s in syms:
        rows = data[s]
        for t in dates:
            trail[s].append(pe.trailing_return(rows, t, strat, FEE))
            fwd[s].append(pe.forward_result(rows, t, strat, FEE))

    quarters = []
    corrs = []
    for qi, t in enumerate(dates):
        avail = [s for s in syms if trail[s][qi] is not None and fwd[s][qi] is not None]
        ranked = sorted(avail, key=lambda s: trail[s][qi], reverse=True)
        picks = ranked[:TOP_N]
        pick_rets = [fwd[s][qi][0] for s in picks]
        pick_trades = sum(fwd[s][qi][1] for s in picks)
        all_rets = [fwd[s][qi][0] for s in avail]
        q_corr = spearman([trail[s][qi] for s in avail], [fwd[s][qi][0] for s in avail])
        if q_corr is not None:
            corrs.append(q_corr)
        best = max(picks, key=lambda s: fwd[s][qi][0]) if picks else None
        quarters.append({
            "t": t, "n_available": len(avail), "picks": picks, "pick_return": sum(pick_rets) / len(pick_rets),
            "pick_trades": pick_trades, "trade_all_return": sum(all_rets) / len(all_rets),
            "hold_index": hold_return(index_rows, t) if index_rows else None,
            "hold_universe": sum(hold_return(data[s], t) for s in avail) / len(avail),
            "spearman": q_corr, "best_stock": best, "best_stock_return": fwd[best][qi][0] if best else None,
        })

    total_return = compound(q["pick_return"] for q in quarters)
    total_trades = sum(q["pick_trades"] for q in quarters)
    trade_all_total = compound(q["trade_all_return"] for q in quarters)
    hold_index_total = compound(q["hold_index"] for q in quarters) if index_rows else None
    hold_universe_total = compound(q["hold_universe"] for q in quarters)
    positive_quarters = sum(1 for q in quarters if q["pick_return"] > 0)

    rng = random.Random(seed)
    draws = []
    for _ in range(n_draws):
        total = 1.0
        for qi, t in enumerate(dates):
            avail = [s for s in syms if fwd[s][qi] is not None]
            sample = rng.sample(avail, min(TOP_N, len(avail)))
            total *= 1 + sum(fwd[s][qi][0] for s in sample) / len(sample)
        draws.append(total - 1)
    draws.sort()
    pct_below = sum(1 for d in draws if d < total_return) / len(draws)
    p95_5 = draws[math.ceil(0.975 * len(draws)) - 1]

    g1 = total_trades >= 100
    g2 = total_return > 0
    g3 = total_return > p95_5
    g4 = total_return > trade_all_total
    g5 = positive_quarters > len(quarters) / 2
    g6 = hold_index_total is None or total_return > hold_index_total
    passed_1_5 = g1 and g2 and g3 and g4 and g5
    verdict = "PASS" if (passed_1_5 and g6) else ("real, but not worth it" if passed_1_5 else "FAIL")

    return {
        "strategy": strat, "n_stocks": len(syms), "n_quarters": len(quarters), "quarters": quarters,
        "total_return": total_return, "total_trades": total_trades, "trade_all_total": trade_all_total,
        "hold_index_total": hold_index_total, "hold_universe_total": hold_universe_total,
        "positive_quarters": positive_quarters, "random_p97_5": p95_5, "random_pct_below": pct_below,
        "mean_spearman": sum(corrs) / len(corrs) if corrs else None,
        "gates": {"G1_trades": g1, "G2_positive": g2, "G3_beats_random": g3, "G4_beats_trade_all": g4,
                  "G5_quarters": g5, "G6_beats_index": g6},
        "verdict": verdict,
    }


# ---------------------------------------------------------------- noise + planted-persistence integrity checks

def check_pure_noise():
    passes = 0
    detail = []
    for u in range(N_NOISE_UNIVERSES):
        universe = synthetic_universe(seed=90000 + u, good_ids=set())
        data = {f"S{i}": rows for i, rows in enumerate(universe)}
        any_pass = False
        for strat in STRATS:
            res = run_walkforward(data, strat, index_rows=None, seed=RANDOM_SEED, n_draws=400)
            if res["gates"]["G1_trades"] and res["gates"]["G2_positive"] and res["gates"]["G3_beats_random"] \
                    and res["gates"]["G4_beats_trade_all"] and res["gates"]["G5_quarters"]:
                any_pass = True
        passes += any_pass
        detail.append(any_pass)
    return {"ok": passes <= 1, "passes": passes, "of": N_NOISE_UNIVERSES, "detail": detail}


def check_planted_persistence():
    good_ids = set(range(10))
    universe = synthetic_universe(seed=77001, good_ids=good_ids)
    data = {f"S{i}": rows for i, rows in enumerate(universe)}
    res = run_walkforward(data, "ibs", index_rows=None, seed=RANDOM_SEED, n_draws=400)
    corr_ok = res["mean_spearman"] is not None and res["mean_spearman"] > 0.05
    good_syms = {f"S{i}" for i in good_ids}
    pick_hits = sum(1 for q in res["quarters"] for s in q["picks"] if s in good_syms)
    pick_slots = sum(len(q["picks"]) for q in res["quarters"])
    hit_rate = pick_hits / pick_slots if pick_slots else 0.0
    chance_rate = 10 / 60
    finds_it = corr_ok and hit_rate > chance_rate * 1.5
    return {"ok": finds_it, "mean_spearman": res["mean_spearman"], "pick_hit_rate": hit_rate,
            "chance_rate": chance_rate, "verdict": res["verdict"]}


# ---------------------------------------------------------------- real data + report

def load_basket_symbols(name):
    with open(os.path.join(LA, name)) as f:
        return [s["symbol"] for s in json.load(f)["stocks"]]


def fetch_all(syms):
    data = {}
    for i, sym in enumerate(syms):
        rows = server.yahoo_rows(sym, "1440")[:-1]
        data[sym] = rows
        print(f"  [{i + 1}/{len(syms)}] {sym}: {len(rows)} candles")
        time.sleep(0.15)
    return data


def align(data):
    """Trim every series to the shared trailing window (same trading days) so rank dates line up
    across stocks. Yahoo returns one bar per US trading day, so equal-length series already line
    up; this only bites if a symbol has real gaps."""
    lens = {s: len(r) for s, r in data.items()}
    n = min(lens.values())
    mism = {s: l for s, l in lens.items() if l != n}
    return {s: r[-n:] for s, r in data.items()}, n, mism


def update_registry(results):
    """Appends/replaces only the PICK-* rows, leaving every other line byte-identical (no re-quoting
    churn from a csv round-trip)."""
    reg_path = os.path.join(HERE, "REGISTRY.csv")
    import csv
    import io
    with open(reg_path, newline="") as f:
        lines = f.read().splitlines(keepends=True)
    header = next(csv.reader([lines[0]]))
    ids = {"PICK-IBS", "PICK-FISHER"}
    kept = [ln for ln in lines[1:] if next(csv.reader([ln]))[0] not in ids]
    if kept and not kept[-1].endswith("\n"):
        kept[-1] += "\n"
    today = time.strftime("%Y-%m-%d")
    new_lines = []
    for strat, label in (("ibs", "PICK-IBS"), ("fisher", "PICK-FISHER")):
        r = results[strat]
        q0, qn = r["quarters"][0], r["quarters"][-1]
        row = {
            "id": label, "date": today, "phase": "pick", "cluster": "stock-picking",
            "strategy": f"{'IBS Swing' if strat == 'ibs' else 'Fisher Transform'} on its own trailing-252d winners",
            "hypothesis": "picking micro-caps by trailing strategy performance beats no picking",
            "data": "baskets C+D, 60 fresh micro-caps, Yahoo daily", "test_period": f"{q0['t']}..{qn['t'] + HORIZON}",
            "oos_period": f"{r['n_quarters']} quarters", "oos_cagr": f"{r['total_return'] * 100:+.1f}% total",
            "oos_sharpe": "n/a", "max_dd": "n/a", "costs": "0.50%/trade",
            "n_configs": 1, "status": r["verdict"], "file": "research/run_pick.py",
            "notes": f"gates: {', '.join(k for k, v in r['gates'].items() if not v) or 'none failed'}",
        }
        buf = io.StringIO()
        csv.writer(buf).writerow([row.get(h, "") for h in header])
        new_lines.append(buf.getvalue())
    with open(reg_path, "w", newline="") as f:
        f.write(lines[0])
        f.writelines(kept)
        f.writelines(new_lines)
    print(f"updated REGISTRY.csv ({len(ids)} PICK rows)")


def write_report(sha, integrity, results, n_bars, mism):
    def pc(x):
        return "n/a" if x is None else f"{x * 100:+.1f}%"

    lines = [
        "# PICK results: picking micro-caps a strategy did well on (walk-forward)", "",
        f"**Run:** {time.strftime('%Y-%m-%d %H:%M')}. PREREG_PICK.md sha256 `{sha}`.", "",
        "## Integrity checks (must all pass before any result counts)", "",
        f"- Reproduces the app's own basket-test numbers exactly: "
        f"{'PASS' if integrity['reproduce']['ok'] else 'FAIL'} (worst diff {integrity['reproduce']['worst_abs_diff']:.2e})",
        f"- No look-ahead (truncation test): {'PASS' if integrity['no_lookahead']['ok'] else 'FAIL'}",
        f"- Pure noise (10 fake universes, no real edge anywhere): "
        f"{'PASS' if integrity['noise']['ok'] else 'FAIL'} "
        f"({integrity['noise']['passes']} of {integrity['noise']['of']} synthetic universes passed all 5 non-index gates)",
        f"- Planted persistence (can the test find a real, injected edge?): "
        f"{'PASS' if integrity['planted']['ok'] else 'FAIL'} "
        f"(mean rank correlation {integrity['planted']['mean_spearman']}, "
        f"picked the seeded-edge stocks {integrity['planted']['pick_hit_rate'] * 100:.0f}% of the time vs "
        f"{integrity['planted']['chance_rate'] * 100:.0f}% by chance)",
        "",
    ]
    all_ok = all(integrity[k]["ok"] for k in ("reproduce", "no_lookahead", "noise", "planted"))
    if not all_ok:
        lines += ["**One or more integrity checks failed. The walk-forward result below is not trustworthy "
                  "as written and needs to be fixed before it counts.**", ""]

    lines += [f"## Data", "", f"60 stocks (baskets C+D), {n_bars} daily candles each after alignment"
              f"{f', {len(mism)} symbols trimmed for length mismatch' if mism else ''}. 0.50% fee, next-open fills, "
              f"60-candle warm-up, ranked every {RANK_EVERY} trading days on trailing {LOOKBACK}-day return, "
              f"top {TOP_N} of 60 traded forward {HORIZON} days, $10,000 per stock.", ""]

    for strat, name in (("ibs", "IBS Swing"), ("fisher", "Fisher Transform")):
        r = results[strat]
        lines += [f"## {name}: {r['verdict']}", "",
                  f"- {r['n_quarters']} quarters, {r['total_trades']} closed trades",
                  f"- Total return picking the top {TOP_N}: **{pc(r['total_return'])}**",
                  f"- Random 10-of-60 picks, 97.5th percentile of {N_RANDOM_DRAWS} draws: {pc(r['random_p97_5'])} "
                  f"(this result beat {r['random_pct_below'] * 100:.1f}% of random draws)",
                  f"- Trading all 60, no picking: {pc(r['trade_all_total'])}",
                  f"- Holding IWC over the same stretch: {pc(r['hold_index_total'])}",
                  f"- Holding the 60 stocks equally: {pc(r['hold_universe_total'])}",
                  f"- Positive in {r['positive_quarters']} of {r['n_quarters']} quarters",
                  f"- Mean rank correlation between trailing and next-quarter return: "
                  f"{r['mean_spearman'] if r['mean_spearman'] is None else round(r['mean_spearman'], 3)}",
                  "",
                  "| gate | result |", "|---|---|",
                  *(f"| {k} | {'pass' if v else 'fail'} |" for k, v in r["gates"].items()),
                  "",
                  "| quarter | picks | return | best stock | its return |", "|---|---|---|---|---|",
                  *(f"| {i + 1} | {', '.join(q['picks'])} | {pc(q['pick_return'])} | "
                    f"{q['best_stock']} | {pc(q['best_stock_return'])} |" for i, q in enumerate(r["quarters"])),
                  ""]
    with open(REPORT, "w") as f:
        f.write("\n".join(lines))
    print(f"wrote {REPORT}")


def main():
    sha = hashlib.sha256(open(PREREG, "rb").read()).hexdigest()
    print(f"PREREG_PICK.md sha256 = {sha}")

    print("\n--- integrity: reproduces the app's own numbers ---")
    reproduce = check_reproduces_app()
    print(reproduce)

    print("\n--- integrity: no look-ahead (truncation test) ---")
    probe_sym = load_basket_symbols("basket_c.json")[0]
    probe_rows = server.yahoo_rows(probe_sym, "1440")[:-1]
    no_lookahead = check_no_lookahead(probe_rows)
    print(no_lookahead)

    print("\n--- integrity: pure noise (10 fake universes) ---")
    noise = check_pure_noise()
    print(noise)

    print("\n--- integrity: planted persistence ---")
    planted = check_planted_persistence()
    print(planted)

    integrity = {"reproduce": reproduce, "no_lookahead": no_lookahead, "noise": noise, "planted": planted}
    all_ok = all(v["ok"] for v in integrity.values())
    if not all_ok:
        print("\nINTEGRITY CHECK FAILED - fix before trusting any walk-forward result.")

    print("\n--- fetching baskets C + D (60 stocks) ---")
    syms = load_basket_symbols("basket_c.json") + load_basket_symbols("basket_d.json")
    data = fetch_all(syms)
    data, n_bars, mism = align(data)
    if mism:
        print(f"length mismatches trimmed: {mism}")
    index_rows = server.yahoo_rows("IWC", "1440")[:-1]
    index_rows = index_rows[-n_bars:] if len(index_rows) >= n_bars else index_rows

    print(f"\n--- walk-forward, {len(rank_dates(n_bars))} quarters ---")
    results = {}
    for strat in STRATS:
        print(f"\n{strat}:")
        res = run_walkforward(data, strat, index_rows=index_rows)
        results[strat] = res
        print(f"  total return {res['total_return'] * 100:+.1f}%  trades {res['total_trades']}  "
              f"verdict {res['verdict']}")

    os.makedirs(os.path.dirname(RESULTS), exist_ok=True)
    with open(RESULTS, "w") as f:
        json.dump({"prereg_sha256": sha, "integrity": integrity, "results": results,
                    "symbols": syms, "n_bars": n_bars}, f, indent=1, default=str)
    print(f"\nwrote {RESULTS}")

    write_report(sha, integrity, results, n_bars, mism)
    update_registry(results)


if __name__ == "__main__":
    main()
