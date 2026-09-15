"""
The confirmation year (PREREG_CONFIRM.md): every search winner, rerun untouched on 2024-09-11 -> 2025-09-11.
===========================================================================================================

  python3 run_confirm.py                         winners from results/search.json
  python3 run_confirm.py results/a.json b.json   winners from several search rounds (K counts them all)

If no round has a winner, no confirmation data is loaded: the year stays untouched.
Uses run_search's stage 1 / stage 2 unchanged; only the data window differs.
"""

import datetime as dt
import hashlib
import json
import os
import re
import sys
import time

import eng_tf
import intraday
import run_search as rs
import sn_exec as ex
import sn_setups as su
import sources

HERE = os.path.dirname(os.path.abspath(__file__))
PREREG = os.path.join(HERE, "PREREG_CONFIRM.md")
START = int(dt.datetime(2024, 9, 11, tzinfo=dt.timezone.utc).timestamp())
END = int(dt.datetime(2025, 9, 11, tzinfo=dt.timezone.utc).timestamp())
DAY = 86400
MIN_DAYS = 300
_search_load = rs.load


def _load(spec):
    if spec["kind"] == "crypto" and spec.get("start"):
        raw = intraday.coinbase_1m(spec["sym"], spec["start"], spec["end"], quiet=True)
        return eng_tf.crypto_from_rows(spec["sym"], raw, spec["start"] + eng_tf.WARMUP_DAYS * DAY)
    return _search_load(spec)


def stage1(spec):
    rs.load = _load
    return rs.stage1(spec)


def stage2(spec):
    rs.load = _load
    return rs.stage2(spec)


def blackouts():
    ev = set()
    for name, label in (("cpi", "CPI"), ("empsit", "jobs")):
        for mm, dd, yy in re.findall(rf"/news\.release/archives/{name}_(\d\d)(\d\d)(\d{{4}})\.pdf",
                                     su._bls_archive(name)):
            ev.add((su._et(int(yy), int(mm), int(dd), 8, 30), label))
    for d in sources.fomc_statement_dates(2024)[0]:
        y, m, dd = (int(x) for x in d.split("-"))
        ev.add((su._et(y, m, dd, 14, 0), "FOMC"))
    ev = sorted(ev)
    return su.blackouts(ev), [e for e in ev if START <= e[0] < END]


def winners(paths):
    out = []
    for p in paths:
        res = json.load(open(p))
        for tr in rs.TRACKS:
            for row in res["tracks"][tr]:
                if row["WIN"]:
                    out.append({"source": os.path.basename(p), "track": tr, "config": row["config"],
                                "fi": rs.FILTERS.index(tuple(row["filter"])), "vi": rs.EXITS.index(tuple(row["exit"])),
                                "search_test": row["test"]})
    return out


def main():
    paths = sys.argv[1:] or [os.path.join(HERE, "results", "search.json")]
    sha = hashlib.sha256(open(PREREG, "rb").read()).hexdigest()
    print(f"PREREG_CONFIRM.md sha256 {sha}")
    W = winners(paths)
    K = len(W)
    print(f"search winners to confirm: {K}")
    if not K:
        print("No search winner, so the confirmation year stays untouched (PREREG_CONFIRM.md).")
        return
    alpha = 0.05 / K
    blk, events = blackouts()
    print(f"catalysts in the confirmation year: {len(events)}")
    btc = _load({"kind": "crypto", "sym": rs.COINS[0], "start": START, "end": END})
    bench = rs.bench_payload(btc)
    del btc
    specs = [{"kind": "crypto", "sym": s, "blk": blk, "split": 10 ** 12, "start": START, "end": END,
              "no_placebo": True, "bench": None if s == rs.COINS[0] else bench} for s in rs.COINS]
    t0 = time.time()
    outs = rs._map(stage1, specs, 5)
    kept = []
    for spec, o in zip(specs, outs):
        days = len(set(o["eligible"][1]))
        print(f"  {spec['sym']:<8} candidates {o['n']:>6}  evaluation days {days}")
        if days >= MIN_DAYS:
            kept.append((spec, o))
        else:
            print(f"  {spec['sym']} dropped: fewer than {MIN_DAYS} evaluation days")
    print(f"stage 1: {time.time() - t0:.0f}s")
    G = rs.merge([o for _, o in kept])
    lists = rs.filter_lists(G)
    need = {}
    for w in W:
        w["trades"] = rs.trades_of(G, lists[w["fi"]], w["vi"], 0, rs.FEES[w["track"]])
        for t in w["trades"]:
            need.setdefault(t["sym"], set()).add((t["i"], w["vi"]))
    jobs = []
    for si, pairs in sorted(need.items()):
        spec, o = kept[si]
        D_, day_, i1_, ca_, A_ = o["eligible"]
        pairs = sorted(pairs)
        s2 = {k: v for k, v in spec.items() if k != "bench"}
        s2["pool"] = [(D_[x], i1_[x], None if ca_[x] < 0 else ca_[x], A_[x]) for x in range(len(D_))]
        s2["trades"] = [(G["D"][i], G["i1"][i], None if G["close_at"][i] < 0 else G["close_at"][i], G["side"][i],
                         G["price"][i], G["risk"][i], G["A"][i], G["V"][i], G["P"][i], vi) for i, vi in pairs]
        jobs.append((pairs, s2))
    vals = rs._map(stage2, [j[1] for j in jobs], 5)
    lookup = {p: v for (pairs, _), vv in zip(jobs, vals) for p, v in zip(pairs, vv)}

    rows = []
    for w in W:
        tr = w.pop("trades")
        st = ex.r_stats([t["r"] for t in tr])
        bs = ex.day_bootstrap(tr, lo_q=alpha)
        pl = ex.placebo_test([t["r0"] for t in tr], [lookup.get((t["i"], w["vi"]), []) for t in tr])
        per = {}
        for t in tr:
            per.setdefault(G["syms"][t["sym"]], []).append(t["r"])
        pos = sorted(s for s, v in per.items() if sum(v) > 0)
        c1 = bool(st["n"] >= 100 and st["mean"] > 0 and bs and bs["lo"] > 0 and (st["pf"] or 0) > 1.10)
        c2 = bool(pl and pl["pct"] > 1 - alpha)
        c3 = len(pos) >= 3
        rows.append({**w, "confirm": {**st, "lo": bs["lo"] if bs else None}, "no_fee_vs_random": pl,
                     "coins_positive": pos, "C1": c1, "C2": c2, "C3": c3, "CONFIRMED": c1 and c2 and c3})
        print(f"  [{w['track']}] {w['config']}: trades {st['n']}, mean R {st['mean'] if st['mean'] is None else round(st['mean'], 3)}, "
              f"lower bound {None if not bs else round(bs['lo'], 3)}, PF {st['pf']}, random pct {pl and round(pl['pct'], 4)}, "
              f"coins+ {len(pos)}/5 -> {'CONFIRMED' if rows[-1]['CONFIRMED'] else 'not confirmed'}")
    out = {"prereg_sha256": sha, "generated_utc": time.strftime("%Y-%m-%d %H:%M"), "K": K, "alpha": alpha,
           "window": ["2024-09-11", "2025-09-11"], "rows": rows,
           "confirmed": sum(r["CONFIRMED"] for r in rows)}
    with open(os.path.join(HERE, "results", "confirm.json"), "w") as f:
        json.dump(out, f, indent=1, default=str)
    print(f"CONFIRMED: {out['confirmed']} of {K}. wrote results/confirm.json")


if __name__ == "__main__":
    main()
