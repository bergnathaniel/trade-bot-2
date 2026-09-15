"""
An honest strategy search on the sniper system (PREREG_SEARCH.md), end to end.
=============================================================================

  python3 run_search.py                  G0 self-test, then the search:
                                           stage 1  one process per coin: every candidate x 24 exit
                                                    variants, plus a random-entry replica
                                           scoring  9,504 configurations on each half of the year
                                           select   top 10 per fee track by first-half t-stat
                                           test     W1-W3 on the second half (stage 2: random entries)
                                           stocks   the finalists on 16 stocks, 19 sessions
                                         -> results/search.json, results/search_configs.csv.gz
  python3 run_search.py --skip-selftest

Results are in R (the distance to the stop). Fees are charged in R: a trade's result after a fee c
per side is rf - c * tu, where rf is its zero-fee result and tu its turnover in R.
"""

import array
import csv
import gzip
import hashlib
import json
import math
import os
import random
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import eng_core
import eng_tf
import selftest_engine as se
import sn_exec as ex
import sn_setups as su

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
PREREG = os.path.join(HERE, "PREREG_SEARCH.md")
SEED = 20260911
DAY = 86400
COINS = ("BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "DOGE-USD")
STOCKS = ("SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "AMD",
          "NFLX", "JPM", "XOM")
FAMILIES = su.SETUPS + ("ALL8", "MOM", "REV")
ALL8 = FAMILIES.index("ALL8")
SIDES = ("long", "short", "both")
MIN_SCORES = (0, 60, 70, 80)
REGIMES = ("any", "with", "range")
FILTERS = tuple((f, s, m, r) for f in FAMILIES for s in SIDES for m in MIN_SCORES for r in REGIMES)
EXITS = tuple((k, tp, hold, inval) for k in (1, 3) for tp in ("scale", "fixed2", "none")
              for hold in (60, 480) for inval in (True, False))
FEES = {"free": 0.0, "low": 0.0005, "retail": 0.0035}
TRACKS = ("retail", "low")
STOCK_FEE = 0.0002
MIN_TRAIN, MIN_TEST, TOP, N_PLAC = 200, 100, 10, 20
WITH = (su.CATS.index("strong_with"), su.CATS.index("weak_with"))
RANGE = su.CATS.index("range")
COLS = (("D", "q"), ("day", "q"), ("half", "b"), ("fam", "b"), ("best", "b"), ("side", "b"), ("score", "h"),
        ("cat", "b"), ("pD", "q"), ("i1", "q"), ("close_at", "q"), ("price", "d"), ("risk", "d"), ("A", "d"),
        ("V", "d"), ("P", "d"))
OUTS = ("ext", "rf", "tu", "pext", "prf", "ptu")


def describe(fi, vi):
    f, s, m, r = FILTERS[fi]
    k, tp, hold, inval = EXITS[vi]
    return f"{f:<4} {s:<5} score>={m:<2} {r:<5} | stop x{k} {tp:<6} {hold:>3}m inval {'on' if inval else 'off'}"


def _map(fn, items, workers):
    if workers and len(items) > 1:
        with ProcessPoolExecutor(max_workers=min(workers, len(items))) as pool:
            return list(pool.map(fn, items))
    return [fn(x) for x in items]


# ------------------------------------------------------------------ markets

class _Bench:
    """sn_setups.Bench rebuilt in a worker from plain lists."""

    def __init__(self, p):
        self.done15, self.e9, self.e21, self.atr15, self.c1 = p["done15"], p["e9"], p["e21"], p["atr15"], p["c1"]
        self.idx1 = {t: i for i, t in enumerate(p["t1"])}


def bench_payload(market):
    t15 = eng_core.TF(market, "15m")
    m1 = market.tf["1m"]
    return {"done15": t15.s.done, "e9": t15.e9, "e21": t15.e21, "atr15": t15.atr, "c1": m1.c, "t1": m1.t}


def split_day(market):
    """Last day of the first half, as in run_sniper.calendar."""
    days = sorted({d for _, d, _ in market.decisions})
    return days[len(days) // 2 - 1]


def load(spec):
    if spec["kind"] == "syn":
        rows = se.synthetic(spec["days"], spec["drift"], seed=spec["seed"])
        return eng_tf.crypto_from_rows(spec["sym"], rows, se.T0 + 14 * DAY)
    return su.load_market(spec["sym"], spec["kind"])


# ------------------------------------------------------------------ stage 1: candidates x exits

def _put(res, prefix, vi, tr):
    if tr is None:
        res[prefix + "ext"][vi].append(-1)
        res[prefix + "rf"][vi].append(0.0)
        res[prefix + "tu"][vi].append(0.0)
    else:
        res[prefix + "ext"][vi].append(tr.exit_t)
        res[prefix + "rf"][vi].append(tr.gpu / tr.R)
        res[prefix + "tu"][vi].append(tr.tex / tr.R)


def stage1(spec):
    """
    One symbol: every candidate, its result under each exit variant, and one random-entry replica
    (a random decision time in the same half; same side, stop and invalidation distances in ATR
    units) under each variant. Compact columns; a missing trade has exit time -1. A replica only
    exists where the real trade does.
    """
    market = load(spec)
    ctx = su.Context(market, spec["blk"])
    bench = _Bench(spec["bench"]) if spec.get("bench") else None
    sigs, eligible, counts, fired = su.run(ctx, bench, mode="all")
    split, m1, c5, blk = spec["split"], ctx.m1, ctx.c5_done, ctx.blackouts
    t, o = m1.t, m1.o
    placebo = not spec.get("no_placebo")
    pools = ([], [])
    for D, day, i1, close_at, A in eligible:
        pools[0 if day <= split else 1].append((D, i1, close_at, A))
    cols = {k: array.array(tc) for k, tc in COLS}
    res = {k: [array.array("q" if k.endswith("ext") else "d") for _ in EXITS] for k in OUTS}
    for sg in sigs:
        half = 0 if sg.day <= split else 1
        s = sg.side
        draw = None
        if placebo and pools[half]:
            rng = random.Random(f"{SEED}-{spec['sym']}-{sg.D}-{sg.setup}-{s}")
            draw = pools[half][rng.randrange(len(pools[half]))]
        for k, v in (("D", sg.D), ("day", sg.day), ("half", half), ("fam", FAMILIES.index(sg.setup)),
                     ("best", int(sg.best)), ("side", s), ("score", sg.score), ("cat", su.CATS.index(sg.cat)),
                     ("pD", draw[0] if draw else -1), ("i1", sg.i1),
                     ("close_at", -1 if sg.close_at is None else sg.close_at), ("price", sg.price),
                     ("risk", sg.risk), ("A", sg.A), ("V", sg.V), ("P", sg.P)):
            cols[k].append(v)
        k0 = sg.i1 + 1
        ok = k0 < len(t) and t[k0] == sg.D
        kx, kv = sg.risk / sg.A, s * (sg.price - sg.V) / sg.A
        for vi, (mult, tp, hold, inval) in enumerate(EXITS):
            tr = (ex.exit_path(m1, c5, k0, s, sg.price - s * mult * sg.risk, sg.V if inval else None, sg.A,
                               sg.close_at, blk, P=sg.P, hold=hold, tp_mode=tp) if ok else None)
            pr = None
            if isinstance(tr, ex.Trade):
                _put(res, "", vi, tr)
                if draw is not None:
                    D2, i2, ca2, A2 = draw
                    k2 = i2 + 1
                    if k2 < len(t) and t[k2] == D2:
                        f2 = o[k2]
                        pr = ex.exit_path(m1, c5, k2, s, f2 - s * mult * kx * A2, f2 - s * kv * A2 if inval else None,
                                          A2, ca2, blk, hold=hold, tp_mode=tp)
            else:
                _put(res, "", vi, None)
            _put(res, "p", vi, pr if isinstance(pr, ex.Trade) else None)
    el = [array.array("q"), array.array("q"), array.array("q"), array.array("q"), array.array("d")]
    for D, day, i1, close_at, A in eligible:
        for col, v in zip(el, (D, day, i1, -1 if close_at is None else close_at, A)):
            col.append(v)
    return {"sym": spec["sym"], "n": len(sigs), "cols": cols, **res, "eligible": el, "counts": dict(counts),
            "fired": dict(fired)}


def merge(outs):
    G = {"syms": [o["sym"] for o in outs], "sym": array.array("b")}
    for k, tc in COLS:
        G[k] = array.array(tc)
    for k in OUTS:
        G[k] = [array.array("q" if k.endswith("ext") else "d") for _ in EXITS]
    for si, o in enumerate(outs):
        G["sym"].extend([si] * o["n"])
        for k, _ in COLS:
            G[k].extend(o["cols"][k])
        for k in OUTS:
            for vi in range(len(EXITS)):
                G[k][vi].extend(o[k][vi])
    G["n"] = len(G["D"])
    return G


def filter_lists(G):
    """Candidate indices (in symbol, time order) belonging to each entry filter."""
    lists = [[] for _ in FILTERS]
    fam, best, side, score, cat = G["fam"], G["best"], G["side"], G["score"], G["cat"]
    for i in range(G["n"]):
        fams = (fam[i], ALL8) if best[i] else (fam[i],)
        sides = (0 if side[i] > 0 else 1, 2)
        ms = [m for m, lo in enumerate(MIN_SCORES) if score[i] >= lo]
        regs = (0, 1) if cat[i] in WITH else (0, 2) if cat[i] == RANGE else (0,)
        for f in fams:
            for sd in sides:
                base = (f * 3 + sd) * 4
                for m in ms:
                    b2 = (base + m) * 3
                    for r in regs:
                        lists[b2 + r].append(i)
    return lists


# ------------------------------------------------------------------ scoring every configuration

def _greedy(order, sym, D, half, e, rf, tu):
    """One position per symbol. Per half: n, sum rf, sum tu, sum rf^2, sum rf*tu, sum tu^2."""
    acc = [0.0] * 12
    cur, busy = -1, 0
    for i in order:
        x = e[i]
        if x < 0:
            continue
        if sym[i] != cur:
            cur, busy = sym[i], 0
        if D[i] < busy:
            continue
        busy = x
        b = 6 * half[i]
        r, u = rf[i], tu[i]
        acc[b] += 1
        acc[b + 1] += r
        acc[b + 2] += u
        acc[b + 3] += r * r
        acc[b + 4] += r * u
        acc[b + 5] += u * u
    return acc


_G = _L = _P = None


def _init(G, lists, porders):
    global _G, _L, _P
    _G, _L, _P = G, lists, porders


def _score_variant(vi):
    G = _G
    sym, D, pD, half = G["sym"], G["D"], G["pD"], G["half"]
    e, rf, tu = G["ext"][vi], G["rf"][vi], G["tu"][vi]
    pe, prf, ptu = G["pext"][vi], G["prf"][vi], G["ptu"][vi]
    return ([_greedy(idx, sym, D, half, e, rf, tu) for idx in _L],
            [_greedy(idx, sym, pD, half, pe, prf, ptu) for idx in _P])


def score_all(G, lists, workers):
    sym, pD = G["sym"], G["pD"]
    porders = [sorted(idx, key=lambda i: (sym[i], pD[i])) for idx in lists]
    if workers:
        with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(G, lists, porders)) as pool:
            per_v = list(pool.map(_score_variant, range(len(EXITS))))
    else:
        _init(G, lists, porders)
        per_v = [_score_variant(vi) for vi in range(len(EXITS))]
    real = [[per_v[vi][0][fi] for vi in range(len(EXITS))] for fi in range(len(FILTERS))]
    plac = [[per_v[vi][1][fi] for vi in range(len(EXITS))] for fi in range(len(FILTERS))]
    return real, plac


def half_stats(acc, h, c):
    """(n, mean R after fee c, t) for half h."""
    b = 6 * h
    n = int(acc[b])
    if n < 2:
        return n, (acc[b + 1] - c * acc[b + 2]) / n if n else None, None
    s = acc[b + 1] - c * acc[b + 2]
    s2 = acc[b + 3] - 2 * c * acc[b + 4] + c * c * acc[b + 5]
    mean = s / n
    var = max(s2 / n - mean * mean, 0.0) * n / (n - 1)
    return n, mean, (mean / math.sqrt(var / n) if var > 0 else None)


def ranked(accs, c):
    """Configurations with >= MIN_TRAIN first-half trades, best first-half t first (ties: grid order)."""
    out = []
    for fi in range(len(FILTERS)):
        for vi in range(len(EXITS)):
            n, _, t = half_stats(accs[fi][vi], 0, c)
            if n >= MIN_TRAIN and t is not None:
                out.append((-t, fi, vi))
    out.sort()
    return [(fi, vi) for _, fi, vi in out]


def trades_of(G, idx, vi, h, c):
    e, rf, tu = G["ext"][vi], G["rf"][vi], G["tu"][vi]
    sym, D, half, day = G["sym"], G["D"], G["half"], G["day"]
    out, cur, busy = [], -1, 0
    for i in idx:
        x = e[i]
        if x < 0:
            continue
        if sym[i] != cur:
            cur, busy = sym[i], 0
        if D[i] < busy:
            continue
        busy = x
        if half[i] == h:
            out.append({"i": i, "sym": sym[i], "day": day[i], "r0": rf[i], "r": rf[i] - c * tu[i]})
    return out


# ------------------------------------------------------------------ stage 2: random entries for W2

def stage2(spec):
    market = load(spec)
    m1, s5 = market.tf["1m"], market.tf["5m"]
    c5, blk, pool, t, o = dict(zip(s5.done, s5.c)), spec["blk"], spec["pool"], m1.t, m1.o
    out = []
    for D, i1, close_at, s, price, risk, A, V, P, vi in spec["trades"]:
        mult, tp, hold, inval = EXITS[vi]
        tr = ex.exit_path(m1, c5, i1 + 1, s, price - s * mult * risk, V if inval else None, A, close_at, blk, P=P,
                          hold=hold, tp_mode=tp)
        vals = []
        if isinstance(tr, ex.Trade) and pool:
            kx, kv = tr.R / A, s * (tr.fill - V) / A
            rng = random.Random(f"{SEED}-W2-{spec['sym']}-{D}-{s}-{vi}")
            tries = 0
            while len(vals) < N_PLAC and tries < 20 * N_PLAC:
                tries += 1
                D2, i2, ca2, A2 = pool[rng.randrange(len(pool))]
                k2 = i2 + 1
                if k2 >= len(t) or t[k2] != D2:
                    continue
                f2 = o[k2]
                pr = ex.exit_path(m1, c5, k2, s, f2 - s * kx * A2, f2 - s * kv * A2 if inval else None, A2, ca2, blk,
                                  hold=hold, tp_mode=tp)
                if isinstance(pr, ex.Trade):
                    vals.append(pr.gpu / pr.R)
        out.append(vals)
    return out


# ------------------------------------------------------------------ judging and reports

def judge(G, row, c, real, lookup):
    fi, vi, trades = row["fi"], row["vi"], row["trades"]
    st = ex.r_stats([t["r"] for t in trades])
    bs = ex.day_bootstrap(trades, lo_q=0.005)
    pl = ex.placebo_test([t["r0"] for t in trades], [lookup.get((t["i"], vi), []) for t in trades])
    per = {}
    for t in trades:
        per.setdefault(G["syms"][t["sym"]], []).append(t["r"])
    coins_pos = sorted(s for s, v in per.items() if sum(v) > 0)
    w1 = bool(st["n"] >= MIN_TEST and st["mean"] > 0 and bs and bs["lo"] > 0 and (st["pf"] or 0) > 1.10)
    w2 = bool(pl and pl["mean"] > pl["p995"])
    w3 = len(coins_pos) >= 3
    return {"config": describe(fi, vi), "filter": FILTERS[fi], "exit": EXITS[vi], "fi": fi, "vi": vi,
            "train": half_stats(real[fi][vi], 0, c), "test": {**st, "lo995": bs["lo"] if bs else None},
            "test_no_fee_vs_random": pl, "coins_positive": coins_pos,
            "per_coin_mean": {s: sum(v) / len(v) for s, v in per.items()},
            "W1": w1, "W2": w2, "W3": w3, "WIN": w1 and w2 and w3}


def luck(real, plac, c):
    fr, fp = ranked(real, c), ranked(plac, c)
    return {"best_train_t_real": half_stats(real[fr[0][0]][fr[0][1]], 0, c)[2] if fr else None,
            "best_train_t_random": half_stats(plac[fp[0][0]][fp[0][1]], 0, c)[2] if fp else None,
            "random_finalists": [{"config": describe(fi, vi), "train": half_stats(plac[fi][vi], 0, c),
                                  "test": half_stats(plac[fi][vi], 1, c)} for fi, vi in fp[:TOP]]}


def hindsight(real, c):
    """The best second-half configuration (by t), and where the first half ranked it."""
    order = ranked(real, c)
    rank = {key: r for r, key in enumerate(order, 1)}
    best = None
    for fi, vi in order:
        n, _, t = half_stats(real[fi][vi], 1, c)
        if n >= MIN_TEST and t is not None and (best is None or t > best[0]):
            best = (t, fi, vi)
    if best is None:
        return None
    _, fi, vi = best
    return {"config": describe(fi, vi), "test": half_stats(real[fi][vi], 1, c),
            "train": half_stats(real[fi][vi], 0, c), "train_rank": rank[(fi, vi)], "of": len(order)}


def _ranks(xs):
    order = sorted(range(len(xs)), key=xs.__getitem__)
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for q in range(i, j + 1):
            r[order[q]] = (i + j) / 2 + 1
        i = j + 1
    return r


def spearman_train_test(real, c):
    a, b = [], []
    for fi in range(len(FILTERS)):
        for vi in range(len(EXITS)):
            n0, m0, _ = half_stats(real[fi][vi], 0, c)
            n1, m1_, _ = half_stats(real[fi][vi], 1, c)
            if n0 >= MIN_TRAIN and n1 >= MIN_TEST:
                a.append(m0)
                b.append(m1_)
    if len(a) < 3:
        return {"rho": None, "configs": len(a)}
    ra, rb = _ranks(a), _ranks(b)
    ma, mb = sum(ra) / len(ra), sum(rb) / len(rb)
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = math.sqrt(sum((x - ma) ** 2 for x in ra))
    vb = math.sqrt(sum((y - mb) ** 2 for y in rb))
    return {"rho": cov / (va * vb) if va and vb else None, "configs": len(a)}


def share_positive(real, c):
    tr = te = both = nb = 0
    ntr = nte = 0
    for fi in range(len(FILTERS)):
        for vi in range(len(EXITS)):
            n0, m0, _ = half_stats(real[fi][vi], 0, c)
            n1, m1_, _ = half_stats(real[fi][vi], 1, c)
            if n0 >= MIN_TRAIN:
                ntr += 1
                tr += m0 > 0
            if n1 >= MIN_TEST:
                nte += 1
                te += m1_ > 0
            if n0 >= MIN_TRAIN and n1 >= MIN_TEST:
                nb += 1
                both += m0 > 0 and m1_ > 0
    return {"train": tr / ntr if ntr else None, "train_configs": ntr, "test": te / nte if nte else None,
            "test_configs": nte, "both": both / nb if nb else None, "both_configs": nb}


def search(specs, workers=5, score_workers=8, log=print):
    t0 = time.time()
    outs = _map(stage1, specs, workers)
    log(f"stage 1: {time.time() - t0:.0f}s, candidates " + "  ".join(f"{o['sym']} {o['n']}" for o in outs))
    split = specs[0]["split"]
    meta = {o["sym"]: {"candidates": o["n"], "counts": o["counts"], "fired": o["fired"]} for o in outs}
    pools = []
    for o in outs:
        D_, day_, i1_, ca_, A_ = o["eligible"]
        pools.append([(D_[x], i1_[x], None if ca_[x] < 0 else ca_[x], A_[x]) for x in range(len(D_)) if day_[x] > split])
    G = merge(outs)
    del outs
    lists = filter_lists(G)
    t1 = time.time()
    real, plac = score_all(G, lists, score_workers)
    log(f"scored {len(FILTERS) * len(EXITS)} configurations, real and random replica: {time.time() - t1:.0f}s")

    picks = {tr: [{"fi": fi, "vi": vi, "trades": trades_of(G, lists[fi], vi, 1, FEES[tr])}
                  for fi, vi in ranked(real, FEES[tr])[:TOP]] for tr in TRACKS}
    need = {}
    for tr in TRACKS:
        for row in picks[tr]:
            for t in row["trades"]:
                need.setdefault(t["sym"], set()).add((t["i"], row["vi"]))
    jobs = []
    for si, pairs in sorted(need.items()):
        pairs = sorted(pairs)
        spec = {k: v for k, v in specs[si].items() if k != "bench"}
        spec["pool"] = pools[si]
        spec["trades"] = [(G["D"][i], G["i1"][i], None if G["close_at"][i] < 0 else G["close_at"][i], G["side"][i],
                           G["price"][i], G["risk"][i], G["A"][i], G["V"][i], G["P"][i], vi) for i, vi in pairs]
        jobs.append((pairs, spec))
    t2 = time.time()
    vals = _map(stage2, [j[1] for j in jobs], workers)
    lookup = {p: v for (pairs, _), vv in zip(jobs, vals) for p, v in zip(pairs, vv)}
    log(f"stage 2: random entries for {len(lookup)} finalist test trades: {time.time() - t2:.0f}s")

    out = {"split_day": split, "meta": meta, "tracks": {}, "luck": {}, "hindsight": {}, "spearman": {},
           "share_positive": {}}
    for tr in TRACKS:
        c = FEES[tr]
        out["tracks"][tr] = [judge(G, row, c, real, lookup) for row in picks[tr]]
        out["luck"][tr] = luck(real, plac, c)
        out["hindsight"][tr] = hindsight(real, c)
    for name, c in FEES.items():
        out["spearman"][name] = spearman_train_test(real, c)
        out["share_positive"][name] = share_positive(real, c)
    out["verdict"] = {tr: "FOUND" if any(r["WIN"] for r in out["tracks"][tr]) else "NOT FOUND" for tr in TRACKS}
    return out, real, plac


def stocks_check(finalists, blk, workers=5):
    spy = su.load_market("SPY", "stock")
    bench = bench_payload(spy)
    del spy
    specs = [{"kind": "stock", "sym": s, "blk": blk, "split": 10 ** 9, "no_placebo": True,
              "bench": None if s == "SPY" else bench} for s in STOCKS]
    G = merge(_map(stage1, specs, workers))
    lists = filter_lists(G)
    rows = []
    for fi, vi in finalists:
        tr = trades_of(G, lists[fi], vi, 0, STOCK_FEE)
        st, st0 = ex.r_stats([t["r"] for t in tr]), ex.r_stats([t["r0"] for t in tr])
        rows.append({"config": describe(fi, vi), "trades": st["n"], "mean_R_after_fees": st["mean"],
                     "mean_R_no_fees": st0["mean"], "pf": st["pf"], "win_rate": st["win_rate"]})
    return rows


def write_configs(path, real, plac):
    with gzip.open(path, "wt", newline="") as fh:
        w = csv.writer(fh)
        head = ["family", "side", "min_score", "regime", "stop_x", "targets", "max_hold_min", "invalidation"]
        for src in ("real", "random"):
            for fee in FEES:
                for h in ("train", "test"):
                    head += [f"{src}_{fee}_{h}_n", f"{src}_{fee}_{h}_meanR", f"{src}_{fee}_{h}_t"]
        w.writerow(head)
        for fi, (f, s, m, r) in enumerate(FILTERS):
            for vi, (k, tp, hold, inval) in enumerate(EXITS):
                row = [f, s, m, r, k, tp, hold, int(inval)]
                for src in (real, plac):
                    for c in FEES.values():
                        for h in (0, 1):
                            n, mean, t = half_stats(src[fi][vi], h, c)
                            row += [n, "" if mean is None else "%.5f" % mean, "" if t is None else "%.3f" % t]
                w.writerow(row)


def _r(x):
    return "    n/a" if x is None else f"{x:+7.3f}"


def _t(x):
    return "   n/a" if x is None else f"{x:+6.2f}"


def print_report(res):
    day = lambda d: time.strftime("%Y-%m-%d", time.gmtime(d * DAY))
    print(f"\nfirst half ends {day(res['split_day'])}")
    for tr in TRACKS:
        print(f"\n{'=' * 150}\nTRACK {tr.upper()} ({100 * FEES[tr]:.2f}% per side): top {TOP} by first-half t, "
              f"judged on the second half\n{'=' * 150}")
        print(f"{'#':>2} {'configuration':<62} | train {'n':>5} {'meanR':>7} {'t':>6} | test {'n':>5} {'meanR':>7} "
              f"{'lo99.5':>7} {'PF':>5} | no-fee {'meanR':>7} {'rnd99.5':>7} | coins+ | W1 W2 W3 WIN")
        for q, row in enumerate(res["tracks"][tr], 1):
            n0, m0, t0 = row["train"]
            te, pl = row["test"], row["test_no_fee_vs_random"] or {}
            pf = te["pf"]
            print(f"{q:>2} {row['config']:<62} | train {n0:>5} {_r(m0)} {_t(t0)} | test {te['n']:>5} {_r(te['mean'])} "
                  f"{_r(te['lo995'])} {'  inf' if pf == float('inf') else '  n/a' if pf is None else f'{pf:5.2f}'} | "
                  f"no-fee {_r(pl.get('mean'))} {_r(pl.get('p995'))} |   {len(row['coins_positive'])}/5  | "
                  + " ".join(" Y" if row[k] else " ." for k in ("W1", "W2", "W3")) + ("  WIN" if row["WIN"] else "   ."))
        L = res["luck"][tr]
        print(f"luck yardstick: best first-half t, real configurations {_t(L['best_train_t_real'])}; "
              f"random-entry configurations {_t(L['best_train_t_random'])}")
        print("  the random-entry search's top 10 on the second half (mean R): "
              + " ".join(_r(x["test"][1]) for x in L["random_finalists"]))
        H = res["hindsight"][tr]
        if H:
            print(f"hindsight: the best second-half configuration was [{H['config']}] (t {_t(H['test'][2])}, "
                  f"mean {_r(H['test'][1])}); the first half ranked it #{H['train_rank']} of {H['of']} "
                  f"(first-half mean {_r(H['train'][1])})")
    print("\nDoes the first half predict the second? Spearman rank correlation of mean R across configurations")
    for fee, s in res["spearman"].items():
        print(f"  {fee:<6} rho {_r(s['rho'])} over {s['configs']} configurations")
    print("Share of configurations with positive mean R (train / test / both)")
    for fee, s in res["share_positive"].items():
        print(f"  {fee:<6} {100 * (s['train'] or 0):5.1f}% of {s['train_configs']} / {100 * (s['test'] or 0):5.1f}% "
              f"of {s['test_configs']} / {100 * (s['both'] or 0):5.1f}% of {s['both_configs']}")
    if res.get("stocks"):
        print(f"\nFinalists on 16 stocks, 19 sessions, {100 * STOCK_FEE:.2f}%/side (reported, not gated)")
        for row in res["stocks"]:
            print(f"  {row['config']:<62} trades {row['trades']:>4}  meanR {_r(row['mean_R_after_fees'])}  "
                  f"(no fees {_r(row['mean_R_no_fees'])})")
    print("\nVERDICT: " + "  ".join(f"{tr} {v}" for tr, v in res["verdict"].items()))


def main():
    args = sys.argv[1:]
    sha = hashlib.sha256(open(PREREG, "rb").read()).hexdigest()
    print(f"PREREG_SEARCH.md sha256 {sha}")
    g0 = None
    if "--skip-selftest" not in args:
        import selftest_search
        g0 = selftest_search.run_all()
        if not g0["ok"]:
            print("\nG0 FAILED - the harness is broken, so there are no results.")
            sys.exit(1)
    blk = su.blackouts(su.catalysts())
    btc = su.load_market(COINS[0], "crypto")
    split, bench = split_day(btc), bench_payload(btc)
    del btc
    specs = [{"kind": "crypto", "sym": s, "blk": blk, "split": split, "bench": None if s == COINS[0] else bench}
             for s in COINS]
    print("\nsearch:")
    res, real, plac = search(specs, log=lambda m: print("  " + m, flush=True))
    finalists = sorted({(r["fi"], r["vi"]) for tr in TRACKS for r in res["tracks"][tr]})
    t0 = time.time()
    res["stocks"] = stocks_check(finalists, blk)
    print(f"  stocks check: {time.time() - t0:.0f}s")
    res.update({"prereg_sha256": sha, "generated_utc": time.strftime("%Y-%m-%d %H:%M"), "g0": g0,
                "grid": {"filters": len(FILTERS), "exits": len(EXITS), "configurations": len(FILTERS) * len(EXITS)}})
    print_report(res)
    write_configs(os.path.join(RESULTS, "search_configs.csv.gz"), real, plac)
    with open(os.path.join(RESULTS, "search.json"), "w") as f:
        json.dump(res, f, indent=1, default=str)
    print("wrote results/search.json and results/search_configs.csv.gz")


if __name__ == "__main__":
    main()
