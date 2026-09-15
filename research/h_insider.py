"""
Opportunistic insider trading (Cohen, Malloy & Pomorski 2012). Rules: PREREG_PHASE2.md.
======================================================================================

Insiders who trade in the same calendar month every year are "routine" - bonus
cycles, tax planning - and their trades carry little news. Insiders who trade
every year but on no fixed schedule are "opportunistic". The claim is that
their open-market purchases predict returns.

Information date = the Form 4 FILING_DATE (a date only), so a filing is usable
from the next session's open. Classification for year Y uses only trades filed
before 1 January of Y.
"""

import collections
import random

import evaluate
import leakage
import p2data
import stats
import h_stocks as hs
from h_common import UNREG_RF

OOS = "2012-01-01"


def classifier(tx):
    trades = collections.defaultdict(list)
    for fd, td, icik, ocik, code, rel in tx:
        trades[(ocik, icik)].append((fd, td))
    cache = {}

    def classify(ocik, icik, year):
        key = (ocik, icik, year)
        if key not in cache:
            cutoff = f"{year}-01-01"
            months = {year - 3: set(), year - 2: set(), year - 1: set()}
            for fd, td in trades[(ocik, icik)]:
                y = int(td[:4])
                if fd < cutoff and y in months:
                    months[y].add(td[5:7])
            if all(months.values()):
                cache[key] = "routine" if months[year - 3] & months[year - 2] & months[year - 1] else "opportunistic"
            else:
                cache[key] = None
        return cache[key]

    return classify


def month_sets(P, tx, classify, *, classified=True, min_insiders=1, officers=False,
               members=None, start="2009-01", before=None):
    buys = collections.defaultdict(lambda: collections.defaultdict(set))
    sells = collections.defaultdict(lambda: collections.defaultdict(set))
    for fd, td, icik, ocik, code, rel in tx:
        if fd[:7] < start or (before and fd >= before):
            continue
        s = P.cik_sym.get(icik)
        if s is None or (members and P.index[s] not in members):
            continue
        if officers and "officer" not in rel.lower():
            continue
        if classified and classify(ocik, icik, int(fd[:4])) != "opportunistic":
            continue
        (buys if code == "P" else sells)[fd[:7]][s].add(ocik)
    B, S = {}, {}
    for m in set(buys) | set(sells):
        b = {s for s, who in buys[m].items() if len(who) >= min_insiders}
        sl = {s for s, who in sells[m].items() if len(who) >= min_insiders}
        B[m], S[m] = b - sl, sl - b
    return B, S


def month_intervals(P, sets, hold=1):
    idx = {m[0]: k for k, m in enumerate(P.months)}
    out = []
    for m, names in sets.items():
        k = idx.get(m)
        if k is None or k + 1 >= len(P.months):
            continue
        first = P.months[k + 1][1]
        last = P.months[min(k + hold, len(P.months) - 1)][2]
        out += [(s, first, last) for s in names if hs.eligible(P, s, first - 1)]
    return out


def entry_vector(P, B, S):
    by = collections.defaultdict(list)
    for side, sets in (("long", B), ("short", S)):
        for s, a, _ in month_intervals(P, sets):
            by[a].append((s, side))
    W = [None] * P.n
    for i, v in by.items():
        W[i] = tuple(sorted(v))
    return W


def monthly_placebo(P, B, S, draws=1000):
    """G7: gross monthly Sharpe of the real B/S sets vs random eligible stocks, same counts."""
    idx = {m[0]: k for k, m in enumerate(P.months)}
    rows = []
    for m in sorted(set(B) | set(S)):
        k = idx.get(m)
        if k is None or k + 1 >= len(P.months):
            continue
        _, first, last = P.months[k + 1]
        if P.dates[first] < OOS:
            continue
        ret = {}
        for s in P.C:
            if hs.eligible(P, s, first - 1) and P.O[s][first] and P.C[s][last]:
                ret[s] = P.C[s][last] / P.O[s][first] - 1
        if ret:
            b = [s for s in B.get(m, ()) if s in ret]
            sl = [s for s in S.get(m, ()) if s in ret]
            rows.append((ret, list(ret), b, sl, sum(ret.values()) / len(ret)))

    def sharpes(bsets, ssets):
        lo_r, ls_r = [], []
        for (ret, _, _, _, mu), bb, ss in zip(rows, bsets, ssets):
            mb = sum(ret[s] for s in bb) / len(bb) if bb else mu
            ms = sum(ret[s] for s in ss) / len(ss) if ss else mu
            lo_r.append(mb - mu)
            ls_r.append(mb - ms)
        return stats.sharpe(lo_r, periods=12), stats.sharpe(ls_r, periods=12)

    lo_actual, ls_actual = sharpes([r[2] for r in rows], [r[3] for r in rows])
    rng = random.Random(evaluate.SEED_PLACEBO)
    lo_d, ls_d = [], []
    for _ in range(draws):
        bs, ss = [], []
        for _, pool, b, sl, _ in rows:
            pick = rng.sample(pool, min(len(pool), len(b) + len(sl)))
            bs.append(pick[:len(b)])
            ss.append(pick[len(b):])
        a, c = sharpes(bs, ss)
        lo_d.append(a)
        ls_d.append(c)
    return {"lo_actual": lo_actual, "ls_actual": ls_actual, "lo": lo_d, "ls": ls_d, "months": len(rows),
            "describe": "random eligible stocks, same counts per month; statistic = gross monthly Sharpe"}


def h13():
    P = hs.panel()
    tx = p2data.insider_transactions(list(P.cik_sym))
    classify = classifier(tx)
    B, S = month_sets(P, tx, classify)

    def ser(b, s, hold=1):
        return hs.series(P, month_intervals(P, b, hold), month_intervals(P, s, hold))

    base = ser(B, S)
    variants = [
        ("all open-market trades, unclassified", month_sets(P, tx, classify, classified=False, start="2006-02"), 1),
        ("2+ opportunistic insiders", month_sets(P, tx, classify, min_insiders=2), 1),
        ("hold 3 months", (B, S), 3),
        ("officers only", month_sets(P, tx, classify, officers=True), 1),
        ("S&P 500 names only", month_sets(P, tx, classify, members={"SP500"}), 1),
        ("S&P 400 names only", month_sets(P, tx, classify, members={"SP400"}), 1),
    ]
    nb = [(nm, ser(b, s, hold)) for nm, (b, s), hold in variants]
    placebo = monthly_placebo(P, B, S)

    def truncated(cut):
        before = hs.before_date(P, cut)
        cut_tx = tx if before is None else [r for r in tx if r[0] < before]
        return entry_vector(P, *month_sets(P, cut_tx, classifier(cut_tx), before=before))

    leak = leakage.truncation_test(truncated, P.n, lag=1)
    classified = collections.Counter()
    for fd, td, icik, ocik, code, rel in tx:
        if fd >= "2009-01-01" and icik in P.cik_sym:
            classified[classify(ocik, icik, int(fd[:4])) or "unclassified"] += 1
    per_year = collections.defaultdict(lambda: [0, 0])
    for m, names in B.items():
        per_year[m[:4]][0] += len(names)
    for m, names in S.items():
        per_year[m[:4]][1] += len(names)
    return hs.pair_records(
        P, hid="H13", cluster="INSIDER", base=base, neighbours=nb, placebo=placebo, oos=OOS, leak=leak,
        texts=dict(data="SEC Insider Transactions Data Sets (Form 4) 2006->; Yahoo prices; S&P 500 + 400",
                   ls_name="Opportunistic insider buys minus sells",
                   lo_name="Opportunistic insider buys, long-only",
                   ls_hyp="Stocks bought by opportunistic insiders beat stocks they sell over the next month",
                   lo_hyp="Stocks bought by opportunistic insiders beat the universe over the next month",
                   ls_costs="5/10bp per side + 0.30%/yr borrow (2x costs)",
                   lo_costs="5/10bp per side (2x costs)"),
        extra={"open_market_rows": len(tx), "trades_2009_on_by_class": dict(classified),
               "stock_months_per_year_buy_sell": {y: v for y, v in sorted(per_year.items())},
               "placebo_months": placebo["months"]},
        notes=["Placebo statistic is a gross monthly Sharpe; the gated series are daily and net of costs."],
        unregistered=[UNREG_RF, "Classification is per (insider, issuer) pair."])
