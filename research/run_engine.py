"""
The prediction-engine test (PREREG_ENGINE.md), end to end.
=========================================================

  python3 run_engine.py                  G0 self-test, then BTC-USD ETH-USD SPY QQQ NVDA TSLA:
                                         gates per variant x horizon x group -> results/engine.json,
                                         plus the prompt's prediction log per symbol
                                         (results/engine_log_<SYM>.csv.gz)
  python3 run_engine.py --skip-selftest

Deterministic given the cached data (Coinbase day files, Yahoo 2026-09-11 snapshot).
"""

import csv
import gzip
import hashlib
import json
import os
import sys
import time

import eng_core
import eng_score as sc
import eng_tf
import eng_trade as tr
from eng_core import HORIZONS, call_of, outputs

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
PREREG = os.path.join(HERE, "PREREG_ENGINE.md")
GROUPS = {"crypto": eng_tf.CRYPTO, "stocks": eng_tf.STOCKS}
DIRS = sc.DIRS
LOG_FIELDS = ["time_utc", "symbol", "horizon_min", "price", "regime", "volatility", "call", "confidence",
              "stated_prob", "target", "invalidation", "score", "momentum", "mean_reversion", "breakout",
              "candle", "price_after", "outcome", "result", "mfe", "mae", "invalidated", "e2_call", "action"]


# ------------------------------------------------------------------ one symbol

def compact(rows, key):
    """What the group gates need from one symbol x horizon x variant, without keeping the rows."""
    c = {"days": sc.day_table(rows, key), "strata": sc.strata(rows, key),
         "regime": sc.breakdown(rows, "regime", key), "vol": sc.breakdown(rows, "vol", key),
         "bucket": sc.breakdown(rows, "bucket", key), "fam": sc.breakdown(rows, "fam", key)}
    if key == "call":
        d = [r for r in rows if r["call"] in DIRS]
        c["calibration"] = sc.calibration(rows)
        c["excursion"] = [len(d), sum(r["mfe"] for r in d), sum(r["mae"] for r in d),
                          sum(r["invalidated"] for r in d), sum(r["target_err"] for r in rows),
                          sum(r["nochange_err"] for r in rows), len(rows)]
    return c


def _write_log(w, sym, h, rows):
    si, ai = eng_core.REC_FIELDS.index("sigma"), eng_core.REC_FIELDS.index("action")
    for r in rows:
        rec = r["rec"]
        o = outputs(r["S"], r["price"], rec[si], h)
        w.writerow([time.strftime("%Y-%m-%d %H:%M", time.gmtime(r["D"])), sym, h, "%.6g" % r["price"],
                    r["regime"], r["vol"], r["call"], o["confidence"], "%.2f" % o["prob"], "%.6g" % o["target"],
                    "" if o["invalidation"] is None else "%.6g" % o["invalidation"], "%.3f" % r["S"],
                    *("%.3f" % v for v in r["fam"]), "%.6g" % (r["price"] * (1 + r["ret"])), r["label"],
                    "CORRECT" if r["call"] == r["label"] else "WRONG", "%.5f" % r["mfe"], "%.5f" % r["mae"],
                    "" if r["invalidated"] is None else int(r["invalidated"]), r["e2"], rec[ai]])


def process(market, log_path=None):
    recs, m1 = eng_core.run(market)
    kind, F = market.kind, tr.F
    comp, e2_30 = {"E1": {}, "E2": {}}, {}
    fh = w = None
    if log_path:
        fh = gzip.open(log_path, "wt", newline="")
        w = csv.writer(fh)
        w.writerow(LOG_FIELDS)
    for h in HORIZONS:
        rows = sc.label_rows(recs, m1, h)
        sc.climatology(rows, h, kind)
        sc.learn_filter(rows, h, kind)
        comp["E1"][h], comp["E2"][h] = compact(rows, "call"), compact(rows, "e2")
        if h == 30:
            e2_30 = {r["D"]: r["e2"] for r in rows}
        if w:
            _write_log(w, market.sym, h, rows)
    if fh:
        fh.close()

    def side_a(rec):
        a = rec[F["action"]]
        return 1 if a in tr.LONG_ACTS else -1 if a in tr.SHORT_ACTS else 0

    def side_b(rec):
        return {"UP": 1, "DOWN": -1}.get(call_of(rec[F["S30"]]), 0)

    def learned(side_fn):
        def f(rec):
            s = side_fn(rec)
            return s if s and e2_30.get(rec[F["D"]]) == ("UP" if s > 0 else "DOWN") else 0
        return f

    trades = {}
    for v, fa, fb in (("E1", side_a, side_b), ("E2", learned(side_a), learned(side_b))):
        trades[v] = {"A": tr.simulate(recs, m1, fa), "A_long": tr.simulate(recs, m1, fa, long_only=True),
                     "B": tr.simulate(recs, m1, fb), "B_long": tr.simulate(recs, m1, fb, long_only=True)}
    return {"sym": market.sym, "kind": kind, "decisions": len(recs), "filled": market.filled,
            "compact": comp, "trades": trades, "tables": tr.outcome_tables(recs, m1),
            "buy_hold": tr.buy_and_hold(recs, m1),
            "window": [recs[0][0], recs[-1][0]] if recs else None}


# ------------------------------------------------------------------ group gates

def accuracy_summary(comps, days=None):
    s = [0] * 9
    for c in comps:
        for d, x in c["days"].items():
            if days is None or d in days:
                for i in range(9):
                    s[i] += x[i]
    n = s[0] or 1
    return {"predictions": s[0], "accuracy": s[1] / n, "dir_calls": s[2], "dir_call_share": s[2] / n,
            "dir_hit": s[3] / s[2] if s[2] else None, "sign_hit": s[4] / s[2] if s[2] else None,
            "false_positive": 1 - s[3] / s[2] if s[2] else None,
            "false_negative": 1 - s[6] / s[5] if s[5] else None,
            "climatology_accuracy": s[7] / n, "persistence_accuracy": s[8] / n}


def trade_block(outs, variant, book, cost_level, days=None):
    per = []
    for o in outs:
        t = [x for x in o["trades"][variant][book] if days is None or x["day"] in days]
        per.append((o, t, tr.stats(t, tr.COSTS[cost_level][o["kind"]])))
    return per


def trade_gate(outs, variant, book, days=None, B=1000):
    per = trade_block(outs, variant, book, "free", days)
    n = sum(len(t) for _, t, _ in per)
    if not n:
        return {"ok": False, "trades": 0}
    avg_ret = sum(s["total"] for _, _, s in per) / len(per)
    pf = tr.pooled_pf([s for _, _, s in per])
    mean_trade = sum(x["gross"] for _, t, _ in per for x in t) / n
    pools = [(o["tables"][0], o["tables"][1], sum(1 for x in t if x["side"] > 0),
              sum(1 for x in t if x["side"] < 0)) for o, t, _ in per]
    pl = tr.random_entries(pools, mean_trade, B=B, days=days)
    ok = avg_ret > 0 and pf is not None and pf > 1.10 and pl is not None and mean_trade > pl["p95"]
    return {"ok": bool(ok), "trades": n, "avg_symbol_return": avg_ret, "pooled_pf": pf,
            "mean_trade": mean_trade, "random_entry": pl}


def rates(counts):
    return {k: {"n": v[0], "accuracy": v[1] / v[0], "dir_calls": v[2], "dir_hit": v[3] / v[2] if v[2] else None}
            for k, v in sorted(counts.items(), key=lambda kv: -kv[1][0])}


def evaluate(outs, variant, h, cache, halves, B_boot=2000, B_rand=1000):
    comps = [o["compact"][variant][h] for o in outs]
    acc = accuracy_summary(comps)
    sh = sc.shuffle_from_strata([c["strata"] for c in comps])
    g1 = bool(sh and sh["hit"] > sh["p995"])
    bs = sc.day_bootstrap_edge([c["days"] for c in comps], B=B_boot)
    g2 = bool(bs["edge"] > 0 and bs["lo"] > 0)

    book = "A" if sum(len(o["trades"][variant]["A"]) for o in outs) >= 100 else "B"
    if (variant, book) not in cache:
        full = trade_gate(outs, variant, book, B=B_rand)
        retail = [s for _, _, s in trade_block(outs, variant, book, "retail")]
        g4 = sum(s["total"] for s in retail) / len(retail) > 0 and (tr.pooled_pf(retail) or 0) > 1.0
        half_gates = [trade_gate(outs, variant, book, days=hd, B=B_rand) for hd in halves]
        cache[(variant, book)] = (full, bool(g4), half_gates, retail)
    full, g4, half_gates, retail = cache[(variant, book)]

    halves_out = []
    for hd, tg in zip(halves, half_gates):
        shh = sc.shuffle_from_strata([c["strata"] for c in comps], days=hd)
        halves_out.append({"shuffle": shh, "trade": tg,
                           "ok": bool(shh and shh["hit"] > shh["p95"]) and tg["ok"]})
    out = {"accuracy": acc, "shuffle": sh, "bootstrap": bs, "book": book, "trade_free": full,
           "trade_retail": {"avg_symbol_return": sum(s["total"] for s in retail) / len(retail),
                            "pooled_pf": tr.pooled_pf(retail), "trades": sum(s["trades"] for s in retail)},
           "halves": halves_out,
           "by_regime": rates(sc.merge_counts([c["regime"] for c in comps])),
           "by_volatility": rates(sc.merge_counts([c["vol"] for c in comps])),
           "by_confidence": rates(sc.merge_counts([c["bucket"] for c in comps])),
           "by_signal_mix": dict(list(rates(sc.merge_counts([c["fam"] for c in comps])).items())[:12]),
           "gates": {"G1": g1, "G2": g2, "G3": full["ok"], "G4": g4, "G5": all(x["ok"] for x in halves_out)}}
    if variant == "E1":
        cal = sc.merge_counts([c["calibration"] for c in comps])
        out["calibration"] = {k: {"n": v[0], "stated": v[2] / v[0], "actual": v[1] / v[0]} for k, v in sorted(cal.items())}
        ex = sc.merge_counts([{"x": c["excursion"]} for c in comps])["x"]
        out["excursion"] = {"avg_mfe": ex[1] / ex[0] if ex[0] else None, "avg_mae": ex[2] / ex[0] if ex[0] else None,
                            "invalidated_share": ex[3] / ex[0] if ex[0] else None,
                            "target_error": ex[4] / ex[6], "no_change_error": ex[5] / ex[6]}
    return out


def halves_of(outs):
    days = sorted({d for o in outs for d in o["compact"]["E1"][5]["days"]})
    return [set(days[:len(days) // 2]), set(days[len(days) // 2:])]


# ------------------------------------------------------------------ report

def _p(x, d=1):
    return "   n/a" if x is None else f"{100 * x:6.{d}f}%"


def print_group(name, g):
    print(f"\n{'=' * 100}\n{name.upper()}  ({', '.join(g['symbols'])})\n{'=' * 100}")
    print(f"{'config':<9} {'preds':>7} {'dir%':>7} {'hit':>7} {'shuf':>7} {'p99.5':>7} {'sign':>7} | "
          f"{'acc':>7} {'clim':>7} {'pers':>7} {'edge lo':>8} | bk {'trd':>5} {'PF':>5} {'ret/sym':>8} {'rnd95':>7} | "
          f"{'retail':>8} | G1 G2 G3 G4 G5")
    for key, ev in g["rows"].items():
        a, s, b, t, r = ev["accuracy"], ev["shuffle"] or {}, ev["bootstrap"], ev["trade_free"], ev["trade_retail"]
        gates = " ".join(" Y" if ev["gates"][k] else " ." for k in ("G1", "G2", "G3", "G4", "G5"))
        rnd = (t.get("random_entry") or {}).get("p95")
        print(f"{key:<9} {a['predictions']:>7} {_p(a['dir_call_share'])} {_p(a['dir_hit'])} {_p(s.get('placebo_mean'))} "
              f"{_p(s.get('p995'))} {_p(a['sign_hit'])} | {_p(a['accuracy'])} {_p(a['climatology_accuracy'])} "
              f"{_p(a['persistence_accuracy'])} {100 * b['lo']:+7.2f}p | {ev['book']:>2} {t['trades']:>5} "
              f"{(t.get('pooled_pf') or 0):5.2f} {_p(t.get('avg_symbol_return'))}  {_p(rnd, 3)} | "
              f"{_p(r['avg_symbol_return'])} | {gates}")
    print("\nTrades per symbol, E1 (30-minute rules). total return / trades / win rate / PF / max drawdown")
    for sym, s in g["symbol_trades"].items():
        print(f"  {sym:<8} buy&hold over the window {_p(s['buy_hold'])}   decisions {s['decisions']}   filled minutes {s['filled']}")
        for book, costs in s["E1"].items():
            line = "  ".join(f"{lvl}: {_p(c['total'])} n={c['trades']} win={_p(c['win_rate'], 0)} "
                             f"PF={(c['pf'] or 0):.2f} dd={_p(c['max_dd'], 0)}" for lvl, c in costs.items())
            print(f"    {book:<7} {line}")


def main():
    args = sys.argv[1:]
    sha = hashlib.sha256(open(PREREG, "rb").read()).hexdigest()
    print(f"PREREG_ENGINE.md sha256 {sha}")
    st = None
    if "--skip-selftest" not in args:
        import selftest_engine
        st = selftest_engine.run_all()
        if not st["ok"]:
            print("\nG0 FAILED - the harness is broken, so there are no results.")
            sys.exit(1)
    results = {"prereg_sha256": sha, "generated_utc": time.strftime("%Y-%m-%d %H:%M"), "g0": st, "groups": {}}
    for gname, syms in GROUPS.items():
        outs = []
        for sym in syms:
            t0 = time.time()
            o = process(eng_tf.load(sym), log_path=os.path.join(RESULTS, f"engine_log_{sym}.csv.gz"))
            outs.append(o)
            print(f"  {sym:<8} {o['decisions']} decisions  {time.time() - t0:5.1f}s", flush=True)
        halves, cache = halves_of(outs), {}
        g = {"symbols": list(syms), "rows": {}, "symbol_trades": {}}
        for variant in ("E1", "E2"):
            for h in HORIZONS:
                g["rows"][f"{variant}-H{h}"] = evaluate(outs, variant, h, cache, halves)
        for o in outs:
            g["symbol_trades"][o["sym"]] = {
                "buy_hold": o["buy_hold"], "decisions": o["decisions"], "filled": o["filled"],
                "window_utc": [time.strftime("%Y-%m-%d %H:%M", time.gmtime(x)) for x in o["window"]],
                "E1": {book: {lvl: tr.stats(o["trades"]["E1"][book], tr.COSTS[lvl][o["kind"]])
                              for lvl in ("free", "low", "retail")}
                       for book in ("A", "A_long", "B", "B_long")}}
        results["groups"][gname] = g
        print_group(gname, g)
        del outs

    verdict = {}
    for key in results["groups"]["crypto"]["rows"]:
        per = {gn: results["groups"][gn]["rows"][key]["gates"] for gn in GROUPS}
        verdict[key] = "PASS" if all(all(v.values()) for v in per.values()) else "FAIL"
    results["verdict"] = verdict
    print("\nVERDICT (PASS needs G1-G5 in both groups):", "  ".join(f"{k} {v}" for k, v in verdict.items()))
    with open(os.path.join(RESULTS, "engine.json"), "w") as f:
        json.dump(results, f, indent=1, default=str)
    print("wrote results/engine.json")


if __name__ == "__main__":
    main()
