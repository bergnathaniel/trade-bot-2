"""
G0 for the engine test (PREREG_ENGINE.md, section E).
====================================================

The harness has to earn trust before its verdict means anything:
  1. indicators return textbook values on trivial inputs
  2. a synthetic random walk does NOT pass G1-G3 (no manufactured edge)
  3. a synthetic series with planted, persistent drift DOES pass G1 and G3 (it can find edge)
  4. the shuffle placebo's exact moments match brute-force Monte Carlo
  5. no decision reads the future: truncation test on synthetic crypto and real SPY data
  6. the E2 filter and the climatology control only use outcomes already known
"""

import math
import random

import eng_core
import eng_ind as ind
import eng_score as sc
import eng_tf
import intraday
import leakage
import run_engine

DAY = 86400
T0 = 1735689600  # 2025-01-01 00:00 UTC


def synthetic(days, drift, seed, sigma=0.0005):
    """1-minute bars. With drift > 0 the mean return is +/- drift*sigma, flipping every ~4 hours."""
    rng = random.Random(seed)
    px, sign, rows = 100.0, 1, []
    for i in range(days * 1440):
        if drift and rng.random() < 1 / 240:
            sign = -sign
        o, c = px, px * math.exp(rng.gauss(drift * sigma * sign, sigma))
        hi = max(o, c) * math.exp(abs(rng.gauss(0, sigma / 2)))
        lo = min(o, c) * math.exp(-abs(rng.gauss(0, sigma / 2)))
        rows.append([T0 + 60 * i, o, hi, lo, c, rng.lognormvariate(0, 0.5)])
        px = c
    return rows


def _market(rows, end=None):
    return eng_tf.crypto_from_rows("SYN", rows, T0 + 14 * DAY, end=end)


def run_all():
    checks = []

    def check(name, ok, detail=""):
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})
        print(f"  [{'ok' if ok else 'FAIL'}] {name}  {detail}", flush=True)

    print("G0 self-test")
    # 1. indicators
    rng = random.Random(3)
    xs = [rng.random() for _ in range(300)]
    brute = [max(xs[max(0, i - 6):i + 1]) if i >= 6 else None for i in range(300)]
    check("indicators: EMA/RSI/ATR/Bollinger/rolling max",
          ind.ema([5.0] * 50, 9)[-1] == 5.0 and ind.rsi([float(i) for i in range(1, 40)])[-1] == 100.0
          and abs(ind.atr([11.0] * 40, [9.0] * 40, [10.0] * 40)[-1] - 2.0) < 1e-12
          and ind.bollinger([3.0] * 30)[0][-1] == 3.0 and ind.rolling_max(xs, 7) == brute)

    # 2. random walk: nothing may pass
    rw = synthetic(60, 0.0, seed=7)
    o = run_engine.process(_market(rw))
    halves, cache = run_engine.halves_of([o]), {}
    for h in eng_core.HORIZONS:
        g = run_engine.evaluate([o], "E1", h, cache, halves, B_boot=500, B_rand=300)["gates"]
        check(f"random walk H{h}: G1, G2, G3 all fail", not (g["G1"] or g["G2"] or g["G3"]), g)

    # 3. planted drift: the harness must find it
    pl = synthetic(60, 0.15, seed=11)
    o = run_engine.process(_market(pl))
    ev = run_engine.evaluate([o], "E1", 30, {}, run_engine.halves_of([o]), B_boot=500, B_rand=300)
    check("planted drift H30: G1 and G3 pass", ev["gates"]["G1"] and ev["gates"]["G3"],
          f"hit {ev['accuracy']['dir_hit']:.3f} vs shuffle p99.5 {ev['shuffle']['p995']:.3f}; "
          f"PF {ev['trade_free']['pooled_pf']:.2f}, {ev['trade_free']['trades']} trades")

    # 4. shuffle moments vs Monte Carlo
    recs, m1 = eng_core.run(_market(rw))
    rows = sc.label_rows(recs, m1, 30)
    an = sc.shuffle_test(rows, "call")
    mu, sd = sc.shuffle_monte_carlo(rows, "call", B=300)
    check("shuffle placebo: exact moments match Monte Carlo",
          abs(an["placebo_mean"] - mu) < 0.25 * an["placebo_sd"] and 0.85 < sd / an["placebo_sd"] < 1.15,
          f"mean {an['placebo_mean']:.4f} vs {mu:.4f}, sd {an['placebo_sd']:.5f} vs {sd:.5f}")

    # 5a. look-ahead, synthetic crypto
    full = eng_core.run(_market(pl))[0]

    def crypto_cut(cut):
        return full if cut is None else eng_core.run(_market(pl, end=full[cut][0]))[0]

    res = leakage.truncation_test(crypto_cut, len(full), lag=0, n_cuts=4)
    check("look-ahead (synthetic crypto): truncated data gives identical decisions", res["ok"], res)

    # 5b. look-ahead, real SPY snapshot (native 5m/15m/60m bars + premarket levels)
    try:
        pp = intraday.yahoo("SPY", "1m", prepost=True, snapshot=eng_tf.STOCK_SNAPSHOT, quiet=True)
        htf = {iv: intraday.yahoo("SPY", iv, snapshot=eng_tf.STOCK_SNAPSHOT, quiet=True) for iv in ("5m", "15m", "60m")}
        full_s = eng_core.run(eng_tf.stock_from_rows("SPY", pp, htf))[0]

        def stock_cut(cut):
            return full_s if cut is None else eng_core.run(eng_tf.stock_from_rows("SPY", pp, htf, cut=full_s[cut][0]))[0]

        res = leakage.truncation_test(stock_cut, len(full_s), lag=0, n_cuts=6)
        check("look-ahead (SPY): truncated data gives identical decisions", res["ok"], res)
    except FileNotFoundError as e:
        check("look-ahead (SPY): snapshot missing", False, e)

    # 6. E2 filter and climatology use only resolved outcomes
    recs, m1 = eng_core.run(_market(pl))
    rows = sc.label_rows(recs, m1, 30)
    sc.climatology(rows, 30, "crypto")
    sc.learn_filter(rows, 30, "crypto")
    k = len(rows) * 3 // 4
    before = (rows[k]["e2"], rows[k]["clim"])
    Dk, flip = rows[k]["D"], random.Random(5)
    for r in rows:
        if r["D"] + 30 * 60 > Dk:
            r["label"] = flip.choice(("UP", "DOWN", "SIDEWAYS"))
    sc.climatology(rows, 30, "crypto")
    sc.learn_filter(rows, 30, "crypto")
    check("E2 filter + climatology ignore unresolved outcomes", before == (rows[k]["e2"], rows[k]["clim"]), before)

    ok = all(c["ok"] for c in checks)
    print(f"G0 {'PASSED' if ok else 'FAILED'} ({sum(c['ok'] for c in checks)}/{len(checks)})")
    return {"ok": ok, "checks": checks}


if __name__ == "__main__":
    run_all()
