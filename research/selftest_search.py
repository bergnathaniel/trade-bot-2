"""
G0 for the strategy search (PREREG_SEARCH.md, section G).
========================================================

  1. the new exit variants get hand-built cases right (one 2R target, no target, a 60-minute
     hold, invalidation off, a x3 stop)
  2. all-candidates mode leaves the sniper signals unchanged (its ALL8 picks = best mode)
  3. no candidate reads the future: truncation on synthetic crypto and real SPY, all-candidates mode
  4. parallel and serial runs give identical candidates and configuration statistics
  5. five synthetic random-walk coins: no finalist WINS in either fee track
  6. the same kind of coins with planted drift 0.30: at least one finalist WINS in the low track

run_sniper.py reproducing its 2026-09-11 results after the module changes is checked by comparing
its output files (see SEARCH_RESULTS.md).
"""

import eng_tf
import intraday
import leakage
import run_search as rs
import selftest_engine as se
import selftest_sniper as ss
import sn_exec as ex
import sn_setups as su

T0, DAY = se.T0, 86400


def _path(rows, side, X, V, c5=None, hold=120, tp="scale"):
    return ex.exit_path(ss._Bars(rows), c5 or {}, 0, side, X, V, 1.0, None, ([], []), hold=hold, tp_mode=tp)


def _trace(market):
    tr = []
    su.run(su.Context(market, ([], [])), None, trace=tr, mode="all")
    return tr


def _group(drift, days, n=5, seed0=300):
    specs = [{"kind": "syn", "sym": f"SYN{i}", "drift": drift, "seed": seed0 + i, "days": days,
              "blk": ([], []), "bench": None} for i in range(n)]
    split = rs.split_day(rs.load(specs[0]))
    for s in specs:
        s["split"] = split
    return specs


def run_all():
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})
        print(f"  [{'ok' if ok else 'FAIL'}] {name}  {detail}", flush=True)

    print("G0 self-test (search)")
    flat = (100, 100.3, 99.7, 100.1)

    # 1. exit variants (long, fill 100)
    cases = {
        "one 2R target": ss._is(_path([(100, 102.5, 99.5, 102)], 1, 99, 90, tp="fixed2"), 2.0, "target"),
        "one 2R target: no scale-out at 1R, no breakeven": ss._is(
            _path([(100, 101.2, 99.5, 101), (101, 101.1, 98.9, 99)] + [flat] * 3, 1, 99, 90, tp="fixed2"), -1.0, "stop"),
        "no target: 60-minute time exit": ss._is(_path([flat] * 70, 1, 99, 90, hold=60, tp="none"), 0.1, "time"),
        "invalidation off ignores the 5m close": ss._is(
            _path([flat] * 4 + [(100, 100.3, 99.7, 99.5), (99.8, 100, 99.7, 99.9)] + [flat] * 10, 1, 99, None,
                  c5={T0 + 300: 99.5}, hold=10, tp="none"), 0.1, "time"),
        "stop x3 = 3x the risk": ss._is(_path([(100, 101, 98.5, 99)] + [flat] * 5, 1, 97, 90, hold=5, tp="none"),
                                        0.1 / 3, "time"),
    }
    for name, ok in cases.items():
        check(f"exit variants: {name}", ok)

    # 2. all-candidates mode vs best mode
    rows = se.synthetic(40, 0.3, seed=11)
    ctx = su.Context(eng_tf.crypto_from_rows("SYN", rows, T0 + 14 * DAY), ([], []))
    best = su.run(ctx, None)[0]
    allc = su.run(ctx, None, mode="all")[0]

    def key(s):
        return s.D, s.setup, s.side, s.score, s.scan, s.P, s.X, s.V, s.risk

    check("all-candidates mode: its ALL8 picks equal best mode", [key(s) for s in allc if s.best] == [key(s) for s in best],
          f"{len(best)} best signals, {len(allc)} candidates, families {sorted({s.setup for s in allc})}")

    # 3. look-ahead, all-candidates mode
    full = _trace(eng_tf.crypto_from_rows("SYN", rows, T0 + 14 * DAY))
    res = leakage.truncation_test(
        lambda cut: full if cut is None else _trace(eng_tf.crypto_from_rows("SYN", rows, T0 + 14 * DAY, end=full[cut][0])),
        len(full), lag=0, n_cuts=4)
    check("look-ahead (synthetic crypto, all candidates)", res["ok"], res)
    try:
        pp = intraday.yahoo("SPY", "1m", prepost=True, snapshot=eng_tf.STOCK_SNAPSHOT, quiet=True)
        htf = {iv: intraday.yahoo("SPY", iv, snapshot=eng_tf.STOCK_SNAPSHOT, quiet=True) for iv in ("5m", "15m", "60m")}
        full_s = _trace(eng_tf.stock_from_rows("SPY", pp, htf))
        res = leakage.truncation_test(
            lambda cut: full_s if cut is None else _trace(eng_tf.stock_from_rows("SPY", pp, htf, cut=full_s[cut][0])),
            len(full_s), lag=0, n_cuts=6)
        check("look-ahead (SPY, all candidates)", res["ok"], res)
    except FileNotFoundError as e:
        check("look-ahead (SPY): snapshot missing", False, e)

    # 4. parallel == serial
    specs = _group(0.0, 30, n=3, seed0=200)
    a = [rs.stage1(s) for s in specs]
    b = rs._map(rs.stage1, specs, 3)
    same = all(x["n"] == y["n"] and x["cols"] == y["cols"] and all(x[k] == y[k] for k in rs.OUTS)
               for x, y in zip(a, b))
    G = rs.merge(a)
    lists = rs.filter_lists(G)
    real_a, plac_a = rs.score_all(G, lists, 0)
    real_b, plac_b = rs.score_all(G, lists, 3)
    check("parallel == serial: candidates and configuration statistics",
          same and real_a == real_b and plac_a == plac_b, f"{G['n']} candidates")

    # 5. random walk: no winners
    out = rs.search(_group(0.0, 90), log=lambda m: print("     " + m, flush=True))[0]
    wins = {tr: sum(r["WIN"] for r in out["tracks"][tr]) for tr in rs.TRACKS}
    check("random walk (5 coins): no finalist wins in either track", not any(wins.values()),
          f"wins {wins}; best test means " + str({tr: round(max((r['test']['mean'] or -9) for r in out['tracks'][tr]), 3)
                                                 for tr in rs.TRACKS}))

    # 6. planted drift: the search must find it
    out = rs.search(_group(0.30, 90, seed0=400), log=lambda m: print("     " + m, flush=True))[0]
    wins = {tr: sum(r["WIN"] for r in out["tracks"][tr]) for tr in rs.TRACKS}
    top = out["tracks"]["low"][0]
    check("planted drift 0.30 (5 coins): at least one finalist wins in the low track", wins["low"] >= 1,
          f"wins {wins}; low #1 [{top['config']}] test mean {top['test']['mean']:+.3f}R")

    ok = all(c["ok"] for c in checks)
    print(f"G0 {'PASSED' if ok else 'FAILED'} ({sum(c['ok'] for c in checks)}/{len(checks)})")
    return {"ok": ok, "checks": checks}


if __name__ == "__main__":
    run_all()
