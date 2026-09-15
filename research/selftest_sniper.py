"""
G0 for the sniper-system test (PREREG_SNIPER.md, section H).
===========================================================

The harness has to earn trust before its verdict means anything:
  1. the exit engine gets hand-built cases right: stop wins a tie, gaps fill at the open,
     scale-outs, breakeven, trailing, time / session / blackout / invalidation exits, costs,
     don't-chase
  2. the account rules work: sizing cap, daily loss limit, scanner position cap
  3. a synthetic random walk passes neither G1 nor G2, and random entries through the exits
     earn about nothing (the exits manufacture no edge)
  4. a synthetic series with planted, persistent drift passes G2 (the harness can find edge)
  5. no signal reads the future: truncation test on synthetic crypto and real SPY data
  6. S4's filter ignores shadow outcomes not yet known at D
"""

import math
import random

import eng_tf
import intraday
import leakage
import run_sniper as rs
import selftest_engine as se
import sn_exec as ex
import sn_setups as su

T0, DAY = se.T0, 86400


class _Bars:
    def __init__(self, rows):
        self.t = [T0 + 60 * i for i in range(len(rows))]
        self.o, self.h, self.l, self.c = ([float(r[x]) for r in rows] for x in range(4))
        self.v = [1.0] * len(rows)


def _path(rows, side, X, V, A=1.0, P=None, c5=None, close_at=None, bl=((), ())):
    return ex.exit_path(_Bars(rows), c5 or {}, 0, side, X, V, A, close_at, (list(bl[0]), list(bl[1])), P=P)


def _is(res, r, reason):
    return isinstance(res, ex.Trade) and abs(res.r_after(0.0) - r) < 1e-9 and res.reason == reason


class _Sig:
    """Just the attributes the books read."""

    def __init__(self, sym, D, day, score, out, scan=70):
        self.sym, self.D, self.day, self.score, self.scan, self.out = sym, D, day, score, scan, out
        self.price, self.risk, self.side, self.setup, self.regime = 100.0, 1.0, 1, "BRK", "RANGE"


def _trade(D, gpu, R=1.0, hold=60):
    return ex.Trade(fill=100.0, R=R, gpu=gpu, tex=200.0 + gpu, exit_t=D + hold, reason="stop", stage=0,
                    mfe=0.0, mae=-1.0)


def _synthetic(drift, seed, days=60):
    rows = se.synthetic(days, drift, seed=seed)
    market = eng_tf.crypto_from_rows("SYN", rows, T0 + 14 * DAY)
    cal, half_of = rs.calendar(market.decisions)
    _, out = rs.process_symbol(market, ([], []), None, half_of)
    g, _ = rs.evaluate_group("crypto", [out], half_of, cal, B_boot=500, B_plac=500)
    return rows, out, g


def _trace(market):
    tr = []
    su.run(su.Context(market, ([], [])), None, trace=tr)
    return tr


def run_all():
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})
        print(f"  [{'ok' if ok else 'FAIL'}] {name}  {detail}", flush=True)

    print("G0 self-test (sniper)")
    flat = (100, 100.3, 99.7, 100.1)

    # 1. exit engine, hand-built paths (long unless noted; fill 100, stop 99 -> R = 1)
    d3 = _path([(100, 103.5, 99.5, 103)], 1, 99, 90)
    cases = {
        "TP1 then breakeven stop": _is(_path([(100, 101.2, 99.5, 101), (101, 101.5, 99.9, 100)] + [flat] * 5, 1, 99, 90),
                                       1 / 3, "breakeven"),
        "stop wins when a bar touches stop and TP1": _is(_path([(100, 101.5, 98.9, 100)] + [flat] * 3, 1, 99, 90), -1.0, "stop"),
        "gap through the stop fills at the open": _is(_path([(100, 100.2, 99.6, 99.8), (98.5, 98.7, 98, 98.2)] + [flat] * 3,
                                                            1, 99, 90), -1.5, "gap_stop"),
        "TP1+TP2+TP3 in one bar = +2R": _is(d3, 2.0, "tp3"),
        "trailing stop after TP2": _is(_path([(100, 102.2, 99.8, 102), (102, 102.5, 101.1, 101.5)] + [flat] * 3, 1, 99, 90),
                                       1.4, "trail"),
        "time exit at the 120th minute's close": _is(_path([flat] * 130, 1, 99, 90), 0.1, "time"),
        "session close exit": _is(_path([flat] * 10, 1, 99, 90, close_at=T0 + 180), 0.1, "session"),
        "blackout exit at the open": _is(_path([flat] * 10, 1, 99, 90, bl=([T0 + 120], [T0 + 1920])), 0.0, "blackout"),
        "invalidation: 5m close below V exits next open": _is(
            _path([flat] * 4 + [(100, 100.3, 99.7, 99.5), (99.8, 100, 99.7, 99.9)] + [flat] * 3, 1, 99, 99.6,
                  c5={T0 + 300: 99.5}), -0.2, "invalidation"),
        "short: TP1+TP2+TP3 = +2R": _is(_path([(100, 100.5, 96.5, 97)], -1, 101, 110), 2.0, "tp3"),
        "costs: 0.1%/side on +2R trade = +1.798R": isinstance(d3, ex.Trade) and abs(d3.r_after(0.001) - 1.798) < 1e-9,
        "don't chase / fill beyond stop": (_path([flat] * 3, 1, 99, 90, P=99.4) == "chase"
                                           and _path([flat] * 3, 1, 100.5, 90) == "beyond_stop"),
    }
    for name, ok in cases.items():
        check(f"exit engine: {name}", ok)

    # 2. account rules
    day_of = lambda t: (t - T0 - 1) // DAY
    sigs = [_Sig("T", T0 + 300 * (i + 1), 0, 90, _trade(T0 + 300 * (i + 1), -1.0)) for i in range(5)]
    sigs.append(_Sig("T", T0 + DAY + 300, 1, 90, _trade(T0 + DAY + 300, -1.0)))
    trades, blocked, _ = ex.book_symbol(sigs, "crypto", "free", 70, day_of)
    check("daily loss limit: 3 losses at 1% risk halt the day, next day resumes",
          len(trades) == 4 and blocked["daily_limit"] == 2 and trades[-1]["day"] == 1, (len(trades), dict(blocked)))
    trades, _, _ = ex.book_symbol([_Sig("T", T0 + 300, 0, 72, _trade(T0 + 300, 0.1, R=0.1))], "crypto", "free", 70, day_of)
    check("sizing cap: a tight stop can't lever past 1x equity", abs(trades[0]["notional"] - 1.0) < 1e-12,
          trades[0]["notional"])
    sc = [_Sig(s, T0 + 300, 0, 72, _trade(T0 + 300, 1.0, hold=3600), scan=80 - i) for i, s in enumerate("ABC")]
    trades, blocked, _ = ex.book_scanner(sc, "crypto", "free", day_of, ["A", "B", "C"])
    check("scanner: best two by scanner score, third blocked", [t["sym"] for t in trades] == ["A", "B"]
          and blocked["max_positions"] == 1, dict(blocked))

    # 3. random walk: nothing may pass, and random entries through the exits earn ~0
    _, out, g = _synthetic(0.0, 7)
    gt = g["rows"]["S1"]["gates"]
    check("random walk: S1 passes neither G1 nor G2", not (gt["G1"] or gt["G2"]),
          f"{gt}; free trades {g['rows']['S1']['free']['n']}")
    vals = [v for sg in out["sigs"] if sg.placebo for v in sg.placebo]
    mu = sum(vals) / len(vals)
    se_ = math.sqrt(sum((x - mu) ** 2 for x in vals) / (len(vals) - 1) / len(vals))
    check("random walk: random entries through the exit engine earn ~0R before costs",
          -0.05 <= mu <= 3 * se_, f"mean {mu:+.4f}R, SE {se_:.4f}, n {len(vals)}")

    # 4. planted drift: the harness must find it
    drift = 0.15
    pl, out_d, g = _synthetic(drift, 11)
    if not g["rows"]["S1"]["gates"]["G2"]:
        print("  planted drift 0.15 not detected; raising to 0.30 (synthetic calibration, PREREG H)")
        drift = 0.30
        pl, out_d, g = _synthetic(drift, 11)
    p = g["rows"]["S1"]["free_placebo"]
    check(f"planted drift {drift}: S1 free book passes G2", g["rows"]["S1"]["gates"]["G2"],
          f"mean {p['mean']:+.3f}R vs random p99.5 {p['p995']:+.3f}R, {g['rows']['S1']['free']['n']} trades")

    # 5a. look-ahead, synthetic crypto
    full = _trace(eng_tf.crypto_from_rows("SYN", pl, T0 + 14 * DAY))

    def crypto_cut(cut):
        return full if cut is None else _trace(eng_tf.crypto_from_rows("SYN", pl, T0 + 14 * DAY, end=full[cut][0]))

    res = leakage.truncation_test(crypto_cut, len(full), lag=0, n_cuts=4)
    check("look-ahead (synthetic crypto): truncated data gives identical signals", res["ok"],
          {**res, "signals": sum(1 for _, x in full if x)})

    # 5b. look-ahead, real SPY snapshot
    try:
        pp = intraday.yahoo("SPY", "1m", prepost=True, snapshot=eng_tf.STOCK_SNAPSHOT, quiet=True)
        htf = {iv: intraday.yahoo("SPY", iv, snapshot=eng_tf.STOCK_SNAPSHOT, quiet=True) for iv in ("5m", "15m", "60m")}
        full_s = _trace(eng_tf.stock_from_rows("SPY", pp, htf))

        def stock_cut(cut):
            return full_s if cut is None else _trace(eng_tf.stock_from_rows("SPY", pp, htf, cut=full_s[cut][0]))

        res = leakage.truncation_test(stock_cut, len(full_s), lag=0, n_cuts=6)
        check("look-ahead (SPY): truncated data gives identical signals", res["ok"],
              {**res, "signals": sum(1 for _, x in full_s if x)})
    except FileNotFoundError as e:
        check("look-ahead (SPY): snapshot missing", False, e)

    # 6. S4 uses only shadow outcomes already known
    sigs = sorted(out_d["sigs"], key=lambda s: s.D)
    qual = [s for s in sigs if s.score >= 70 and isinstance(s.out, ex.Trade)]
    flags = ex.s4_flags(sigs, "crypto", "free", min_n=5)
    Dk = qual[len(qual) * 3 // 4].D
    before = {id(s): flags[id(s)] for s in qual if s.D <= Dk}
    rng = random.Random(5)
    for s in qual:
        if s.out.exit_t > Dk:
            s.out.gpu += rng.choice((-10.0, 10.0)) * s.out.R
    after = ex.s4_flags(sigs, "crypto", "free", min_n=5)
    check("S4 filter ignores outcomes not yet known at D", all(after[i] == v for i, v in before.items()),
          f"{len(before)} decisions checked, {sum(before.values())} allowed")

    ok = all(c["ok"] for c in checks)
    print(f"G0 {'PASSED' if ok else 'FAILED'} ({sum(c['ok'] for c in checks)}/{len(checks)})")
    return {"ok": ok, "checks": checks, "planted_drift": drift}


if __name__ == "__main__":
    run_all()
