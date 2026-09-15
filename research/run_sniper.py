"""
The sniper-system test (PREREG_SNIPER.md), end to end.
=====================================================

  python3 run_sniper.py                  G0 self-test, then the crypto and stock groups: gates per
                                         configuration -> results/sniper.json, plus the S1 trade log
                                         per group (results/sniper_trades_<group>.csv.gz)
  python3 run_sniper.py --skip-selftest
  python3 run_sniper.py crypto           one group only (no verdict)

Deterministic given the cached data (Coinbase day files, the Yahoo 2026-09-11 snapshot, the BLS
archive pages and the Fed's FOMC calendar).
"""

import csv
import datetime as dt
import gzip
import hashlib
import json
import os
import statistics
import sys
import time
from collections import Counter

import sn_exec as ex
import sn_setups as su

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
PREREG = os.path.join(HERE, "PREREG_SNIPER.md")
GROUPS = {"crypto": ("crypto", ("BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD")),
          "stocks": ("stock", ("SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META",
                               "TSLA", "AVGO", "AMD", "NFLX", "JPM", "XOM"))}
MIN_DAYS = {"crypto": 300, "stock": 15}
PPY = {"crypto": 365, "stock": 252}
CONFIGS = ("S1", "S2", "S3", "S4")
THRESHOLD = {"S1": 70, "S2": 85, "S3": 70, "S4": 70}
EXAMPLE_SYM = "BTC-USD"
EXAMPLE_AFTER = int(dt.datetime(2026, 3, 2, 14, tzinfo=dt.timezone.utc).timestamp())
LOG_FIELDS = ["time_utc", "symbol", "book", "setup", "side", "score", *su.PARTS, "scanner", "regime", "price",
              "ideal_entry", "stop", "invalidation", "fill", "risk_per_unit", "tp1", "tp2", "tp3",
              "account_risk", "notional_share", "exit_time_utc", "exit_reason", "tps_hit", "hold_min",
              "result_R", "result_R_before_costs", "pnl_share_of_equity", "mfe_R", "mae_R"]


def _ts(t):
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(t))


# ------------------------------------------------------------------ one symbol

def calendar(decisions):
    """Evaluation days and half_of(day) -> 0 / 1 (first / second half)."""
    days = sorted({d for _, d, _ in decisions})
    split = days[len(days) // 2 - 1]
    return days, (lambda d: 0 if d <= split else 1)


def process_symbol(market, blk, bench, half_of):
    ctx = su.Context(market, blk)
    sigs, eligible, counts, fired = su.run(ctx, bench)
    ex.attach_outcomes(sigs, ctx)
    pools = ([], [])
    for D, day, i1, close_at, A in eligible:
        pools[half_of(day)].append((D, i1, close_at, A))
    for sg in sigs:
        if sg.score >= 70 and isinstance(sg.out, ex.Trade):
            sg.placebo = ex.placebo_values(sg, ctx, pools[half_of(sg.day)])
    c = ctx.m1.c
    out = {"sym": market.sym, "kind": market.kind, "sigs": sigs, "counts": dict(counts), "fired": dict(fired),
           "eligible": len(eligible), "days": len({e[1] for e in eligible}), "filled": market.filled,
           "buy_hold": c[eligible[-1][2]] / c[eligible[0][2]] - 1.0 if eligible else None,
           "window_utc": [_ts(eligible[0][0]), _ts(eligible[-1][0])] if eligible else None}
    return ctx, out


def load_group(gname, blk):
    kind, syms = GROUPS[gname]
    out, bench, half_of, days = [], None, None, None
    for sym in syms:
        t0 = time.time()
        try:
            market = su.load_market(sym, kind)
        except (OSError, ValueError, KeyError) as e:
            print(f"  {sym:<8} dropped: {e}")
            continue
        if half_of is None:  # the benchmark is listed first
            days, half_of = calendar(market.decisions)
        ctx, o = process_symbol(market, blk, bench, half_of)
        if bench is None:
            bench = su.Bench(ctx)
        del ctx, market
        if o["days"] < MIN_DAYS[kind]:
            print(f"  {sym:<8} dropped: {o['days']} evaluation days < {MIN_DAYS[kind]}")
            continue
        out.append(o)
        n70 = sum(1 for s in o["sigs"] if s.score >= 70)
        print(f"  {sym:<8} decisions {o['eligible']:>6}  signals {len(o['sigs']):>6}  score>=70 {n70:>5}  "
              f"{time.time() - t0:5.1f}s", flush=True)
    return kind, out, half_of, days


# ------------------------------------------------------------------ books, gates, tables

def build_books(kind, syms_data):
    order = [o["sym"] for o in syms_data]
    rank = {s: i for i, s in enumerate(order)}
    all_sigs = sorted((sg for o in syms_data for sg in o["sigs"]), key=lambda s: (s.D, rank[s.sym]))
    day_of = su.day_of_fn(kind)
    books = {}
    for lvl in ex.LEVELS:
        flags = ex.s4_flags(all_sigs, kind, lvl)
        for lo in ((False, True) if lvl in ("free", "retail") else (False,)):
            for cfg in CONFIGS:
                if cfg == "S3":
                    tr, bl, acct = ex.book_scanner(all_sigs, kind, lvl, day_of, order, long_only=lo)
                    books[(cfg, lvl, lo)] = (tr, bl, {"portfolio": acct})
                    continue
                trs, bls, accts = [], Counter(), {}
                for o in syms_data:
                    tr, bl, acct = ex.book_symbol(o["sigs"], kind, lvl, THRESHOLD[cfg], day_of,
                                                  flags=flags if cfg == "S4" else None, long_only=lo)
                    trs += tr
                    bls.update(bl)
                    accts[o["sym"]] = acct
                trs.sort(key=lambda t: (t["D"], rank[t["sym"]]))
                books[(cfg, lvl, lo)] = (trs, bls, accts)
    return all_sigs, books


def _avg_return(accts):
    return sum(a.E - 1.0 for a in accts.values()) / len(accts)


def gates(books, cfg, half_of, B_boot, B_plac):
    tr_r, _, ac_r = books[(cfg, "retail", False)]
    tr_f = books[(cfg, "free", False)][0]
    tr_2, _, ac_2 = books[(cfg, "retail2x", False)]

    st = ex.r_stats([t["r"] for t in tr_r])
    bs = ex.day_bootstrap(tr_r, B=B_boot)
    g1 = bool(st["n"] >= 30 and st["mean"] > 0 and bs and bs["lo"] > 0 and (st["pf"] or 0) > 1.10
              and _avg_return(ac_r) > 0)
    pl = ex.placebo_test([t["r"] for t in tr_f], [t["sig"].placebo or [] for t in tr_f], B=B_plac)
    g2 = bool(pl and pl["mean"] > pl["p995"])
    st2 = ex.r_stats([t["r"] for t in tr_2])
    g3 = bool(st2["n"] >= 30 and st2["mean"] > 0 and _avg_return(ac_2) > 0)

    halves = []
    for h in (0, 1):
        th = [t for t in tr_r if half_of(t["day"]) == h]
        sh = ex.r_stats([t["r"] for t in th])
        bh = ex.day_bootstrap(th, B=B_boot, lo_q=0.025)
        fh = [t for t in tr_f if half_of(t["day"]) == h]
        ph = ex.placebo_test([t["r"] for t in fh], [t["sig"].placebo or [] for t in fh], B=B_plac)
        ok = bool(sh["n"] >= 15 and bh and bh["lo"] > 0 and (sh["pf"] or 0) > 1.10 and ph and ph["mean"] > ph["p95"])
        halves.append({"retail": sh, "retail_lo95": bh["lo"] if bh else None, "free_placebo": ph, "ok": ok})
    return {"retail": {**st, "lo995": bs["lo"] if bs else None, "avg_account_return": _avg_return(ac_r)},
            "free": ex.r_stats([t["r"] for t in tr_f]), "free_placebo": pl,
            "retail2x": {**st2, "avg_account_return": _avg_return(ac_2)}, "halves": halves,
            "gates": {"G1": g1, "G2": g2, "G3": g3, "G4": all(x["ok"] for x in halves)}}


def _mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else None


def book_summary(trades, blocked, accts, days, ppy):
    st = ex.r_stats([t["r"] for t in trades])
    ast = {name: ex.account_stats(a, days, ppy) for name, a in accts.items()}
    sh = [a["sharpe"] for a in ast.values() if a["sharpe"] is not None]
    return {"trades": st["n"], "r": st, "r_before_costs": _mean(t["r_gross"] for t in trades),
            "avg_account_return": _mean(a["return"] for a in ast.values()),
            "avg_max_dd": _mean(a["max_dd"] for a in ast.values()),
            "median_sharpe": statistics.median(sh) if sh else None,
            "trades_per_account_day": st["n"] / (len(days) * len(accts)),
            "avg_hold_min": _mean(t["hold_min"] for t in trades),
            "long_share": _mean(t["side"] > 0 for t in trades),
            "blocked": dict(blocked), "exits": dict(Counter(t["reason"] for t in trades)),
            "accounts": ast}


def signal_setup_table(all_sigs, kind):
    """Every score >= 70 signal simulated on its own: the prompt's section 33 table."""
    cost = ex.COSTS["retail"][kind]
    by = {}
    for sg in all_sigs:
        if sg.score >= 70 and isinstance(sg.out, ex.Trade):
            by.setdefault(f"{sg.setup} {'long' if sg.side > 0 else 'short'}", []).append(sg)
    return {k: {"free": ex.r_stats([s.out.r_after(0.0) for s in v]),
                "retail_no_veto": ex.r_stats([s.out.r_after(cost) for s in v]),
                "vetoed_at_retail": _mean(ex.vetoed(s, cost) for s in v),
                "avg_hold_min": _mean((s.out.exit_t - s.D) / 60 for s in v),
                "mfe_R": _mean(s.out.mfe for s in v), "mae_R": _mean(s.out.mae for s in v)}
            for k, v in sorted(by.items())}


def bucket_table(all_sigs, kind):
    cost = ex.COSTS["retail"][kind]
    b = {"<70": [], "70-79": [], "80-84": [], "85+": []}
    for sg in all_sigs:
        if isinstance(sg.out, ex.Trade):
            b["<70" if sg.score < 70 else "70-79" if sg.score < 80 else "80-84" if sg.score < 85 else "85+"].append(sg)
    return {k: {"free": ex.r_stats([s.out.r_after(0.0) for s in v]),
                "retail_no_veto": ex.r_stats([s.out.r_after(cost) for s in v])} for k, v in b.items()}


def by_field(trades, field):
    by = {}
    for t in trades:
        by.setdefault(t[field], []).append(t["r"])
    return {k: ex.r_stats(v) for k, v in sorted(by.items(), key=lambda kv: -len(kv[1]))}


def evaluate_group(kind, syms_data, half_of, days, B_boot=2000, B_plac=2000):
    all_sigs, books = build_books(kind, syms_data)
    rows = {}
    for cfg in CONFIGS:
        rows[cfg] = gates(books, cfg, half_of, B_boot, B_plac)
        rows[cfg]["books"] = {f"{lvl}{'_long_only' if lo else ''}": book_summary(*books[(c, lvl, lo)], days, PPY[kind])
                              for (c, lvl, lo) in books if c == cfg}
    s1f = books[("S1", "free", False)][0]
    g = {"symbols": {o["sym"]: {k: o[k] for k in ("counts", "fired", "eligible", "days", "filled", "buy_hold",
                                                    "window_utc")} for o in syms_data},
         "rows": rows,
         "reported": {"setups_score70_each_alone": signal_setup_table(all_sigs, kind),
                      "score_buckets_each_alone": bucket_table(all_sigs, kind),
                      "S1_free_by_setup": by_field(s1f, "setup"), "S1_free_by_regime": by_field(s1f, "regime")}}
    ex_tr = next((t for t in s1f if t["sym"] == EXAMPLE_SYM and t["D"] >= EXAMPLE_AFTER), None)
    g["example_card"] = card(ex_tr, kind) if ex_tr else None
    return g, books


# ------------------------------------------------------------------ output

def _px(x):
    return f"{x:,.2f}" if x >= 100 else f"{x:,.4f}" if x >= 1 else f"{x:.5f}"


def card(t, kind):
    """The prompt's section 38 card for one real trade, with what actually happened."""
    sg = t["sig"]
    s, f, R = sg.side, t["fill"], t["R"]
    cost = ex.COSTS["retail"][kind]
    trend = {1: "BULLISH", -1: "BEARISH", 0: "NEUTRAL"}
    htf = (1 if sg.regime in ("STRONG BULL", "WEAK BULL", "BREAKOUT") else
           -1 if sg.regime in ("STRONG BEAR", "WEAK BEAR", "BREAKDOWN") else 0)
    units = min(t["risk_pct"] * 10000 / R, 10000 / f)
    retail = ("blocked by the prompt's own cost rule at retail fees" if ex.vetoed(sg, cost)
              else f"{sg.out.r_after(cost):+.2f}R at retail fees")
    bar = "━" * 40
    return "\n".join([
        bar,
        f"SYMBOL: {sg.sym}      {_ts(sg.D)} UTC",
        f"PRICE: ${_px(sg.price)}",
        f"MARKET REGIME: {sg.regime}",
        f"HIGHER TIMEFRAME: {trend[htf]}      IMMEDIATE TREND: {trend[sg.tr15]}",
        f"SETUP: {su.SETUP_NAMES[sg.setup]}      SETUP SCORE: {sg.score}/100",
        "  " + ", ".join(f"{n} {p:.1f}" for n, p in zip(su.PARTS, sg.parts)),
        bar,
        f"ACTION: {'BUY' if s > 0 else 'SHORT'}",
        f"ENTRY: ${_px(f)}  (ideal ${_px(sg.P)})",
        f"STOP: ${_px(sg.X)}",
        f"TP1: ${_px(f + s * R)}   TP2: ${_px(f + 2 * s * R)}   TP3: ${_px(f + 3 * s * R)}",
        f"RISK/REWARD: 1:3 to TP3      ACCOUNT RISK: {100 * t['risk_pct']:.1f}%",
        f"POSITION SIZE: {units:.6g} units on a $10,000 account",
        f"INVALIDATION: a 5-minute close {'below' if s > 0 else 'above'} ${_px(sg.V)}",
        bar,
        f"WHAT HAPPENED: exit '{t['reason']}' after {t['hold_min']:.0f} min; take-profits hit: {t['stage']}",
        f"RESULT: {t['r']:+.2f}R with no fees; {retail}",
        bar])


def write_log(path, books):
    with gzip.open(path, "wt", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(LOG_FIELDS)
        for lvl in ("free", "retail"):
            for t in books[("S1", lvl, False)][0]:
                sg, f, R = t["sig"], t["fill"], t["R"]
                s = sg.side
                w.writerow([_ts(sg.D), sg.sym, f"S1 {lvl}", sg.setup, "LONG" if s > 0 else "SHORT", sg.score,
                            *("%.2f" % p for p in sg.parts), sg.scan, sg.regime, "%.6g" % sg.price, "%.6g" % sg.P,
                            "%.6g" % sg.X, "%.6g" % sg.V, "%.6g" % f, "%.6g" % R, "%.6g" % (f + s * R),
                            "%.6g" % (f + 2 * s * R), "%.6g" % (f + 3 * s * R), t["risk_pct"],
                            "%.4f" % (t["notional"] / t["E_before"]), _ts(t["exit_t"]), t["reason"], t["stage"],
                            "%.0f" % t["hold_min"], "%.4f" % t["r"], "%.4f" % t["r_gross"],
                            "%.6f" % (t["pnl"] / t["E_before"]), "%.3f" % t["mfe"], "%.3f" % t["mae"]])


def _p(x, d=1):
    return "   n/a" if x is None else f"{100 * x:6.{d}f}%"


def _r(x):
    return "    n/a" if x is None else f"{x:+7.3f}"


def _f(x):
    return "  n/a" if x is None else "  inf" if x == float("inf") else f"{x:5.2f}"


def print_group(name, g):
    print(f"\n{'=' * 110}\n{name.upper()}  ({', '.join(g['symbols'])})\n{'=' * 110}")
    print(f"{'cfg':<4}| retail: {'n':>5} {'meanR':>7} {'lo99.5':>7} {'PF':>5} {'acct':>7} "
          f"| free: {'n':>5} {'meanR':>7} {'rnd99.5':>7} {'pct':>5} | 2x: {'n':>5} {'meanR':>7} {'acct':>7} "
          f"| halves | G1 G2 G3 G4")
    for cfg, row in g["rows"].items():
        r, fr, pl, r2 = row["retail"], row["free"], row["free_placebo"] or {}, row["retail2x"]
        gt = " ".join(" Y" if row["gates"][k] else " ." for k in ("G1", "G2", "G3", "G4"))
        hv = "".join("Y" if h["ok"] else "." for h in row["halves"])
        print(f"{cfg:<4}| retail: {r['n']:>5} {_r(r['mean'])} {_r(r['lo995'])} {_f(r['pf'])} {_p(r['avg_account_return'])} "
              f"| free: {fr['n']:>5} {_r(fr['mean'])} {_r(pl.get('p995'))} {_p(pl.get('pct'), 0)} "
              f"| 2x: {r2['n']:>5} {_r(r2['mean'])} {_p(r2['avg_account_return'])} |   {hv}   | {gt}")
    print("\nBooks (average account per symbol; S3 = one shared portfolio). meanR is after that book's costs.")
    for cfg, row in g["rows"].items():
        for book, b in row["books"].items():
            st = b["r"]
            print(f"  {cfg} {book:<17} trades {b['trades']:>6}  meanR {_r(st['mean'])} (before costs {_r(b['r_before_costs'])})"
                  f"  win {_p(st['win_rate'], 0)}  PF {_f(st['pf'])}  acct {_p(b['avg_account_return'])}"
                  f"  maxDD {_p(b['avg_max_dd'], 0)}  hold {b['avg_hold_min'] or 0:4.0f}m")
    for lvl in ("free", "retail"):
        bl = g["rows"]["S1"]["books"][lvl]["blocked"]
        print(f"\nS1 {lvl}: score>=70 signals not traded: " + ", ".join(f"{k} {v}" for k, v in sorted(bl.items(), key=lambda kv: -kv[1])))
    print("S1 free exits: " + ", ".join(f"{k} {v}" for k, v in sorted(g["rows"]["S1"]["books"]["free"]["exits"].items(), key=lambda kv: -kv[1])))
    print("\nScore buckets (each best signal simulated on its own)")
    for k, v in g["reported"]["score_buckets_each_alone"].items():
        print(f"  {k:<6} n {v['free']['n']:>6}  free meanR {_r(v['free']['mean'])} win {_p(v['free']['win_rate'], 0)} "
              f"PF {_f(v['free']['pf'])} | retail, no veto: meanR {_r(v['retail_no_veto']['mean'])}")
    print("\nSetups, score >= 70, each simulated on its own")
    for k, v in g["reported"]["setups_score70_each_alone"].items():
        print(f"  {k:<10} n {v['free']['n']:>6}  free meanR {_r(v['free']['mean'])} win {_p(v['free']['win_rate'], 0)} "
              f"PF {_f(v['free']['pf'])} | retail meanR {_r(v['retail_no_veto']['mean'])} vetoed {_p(v['vetoed_at_retail'], 0)} "
              f"| hold {v['avg_hold_min']:4.0f}m MFE {v['mfe_R']:+.2f}R MAE {v['mae_R']:+.2f}R")
    print("\nSymbols")
    for sym, s in g["symbols"].items():
        c = s["counts"]
        print(f"  {sym:<8} buy&hold {_p(s['buy_hold'])}  days {s['days']}  eligible {s['eligible']}  stale {c.get('stale', 0)}"
              f"  blackout {c.get('blackout', 0)}  stop too wide {c.get('stop_too_wide', 0)}  fired "
              + " ".join(f"{k}:{v}" for k, v in s["fired"].items()))
    if g["example_card"]:
        print("\nExample: the first S1 no-fee trade on BTC-USD after 2026-03-02 14:00 UTC\n" + g["example_card"])


def main():
    args = sys.argv[1:]
    sha = hashlib.sha256(open(PREREG, "rb").read()).hexdigest()
    print(f"PREREG_SNIPER.md sha256 {sha}")
    st = None
    if "--skip-selftest" not in args:
        import selftest_sniper
        st = selftest_sniper.run_all()
        if not st["ok"]:
            print("\nG0 FAILED - the harness is broken, so there are no results.")
            sys.exit(1)
    events = su.catalysts()
    blk = su.blackouts(events)
    lo, hi = su.eng_tf.CRYPTO_START, su.eng_tf.CRYPTO_END
    inwin = [(t, lab) for t, lab in events if lo <= t < hi]
    print(f"\ncatalysts in the crypto window: {len(inwin)} "
          f"({', '.join(f'{k} {v}' for k, v in Counter(lab for _, lab in inwin).items())})")
    print("  " + ", ".join(f"{su.intraday.et(t):%Y-%m-%d} {lab}" for t, lab in inwin))
    results = {"prereg_sha256": sha, "generated_utc": time.strftime("%Y-%m-%d %H:%M"), "g0": st,
               "catalysts": [[f"{su.intraday.et(t):%Y-%m-%d %H:%M} ET", lab] for t, lab in inwin], "groups": {}}
    chosen = [a for a in args if a in GROUPS] or list(GROUPS)
    for gname in chosen:
        print(f"\n{gname}:")
        kind, syms_data, half_of, days = load_group(gname, blk)
        t0 = time.time()
        g, books = evaluate_group(kind, syms_data, half_of, days)
        write_log(os.path.join(RESULTS, f"sniper_trades_{gname}.csv.gz"), books)
        print(f"  books and gates {time.time() - t0:.1f}s")
        print_group(gname, g)
        results["groups"][gname] = g
        del syms_data, books
    if len(results["groups"]) == len(GROUPS):
        verdict = {cfg: "PASS" if all(all(results["groups"][gn]["rows"][cfg]["gates"].values()) for gn in GROUPS)
                   else "FAIL" for cfg in CONFIGS}
        results["verdict"] = verdict
        print("\nVERDICT (PASS needs G1-G4 in both groups):", "  ".join(f"{k} {v}" for k, v in verdict.items()))
    with open(os.path.join(RESULTS, "sniper.json"), "w") as f:
        json.dump(results, f, indent=1, default=str)
    print("wrote results/sniper.json")


if __name__ == "__main__":
    main()
