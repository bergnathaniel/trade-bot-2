"""
Earnings-event hypotheses on SEC timestamps. Exact rules: PREREG_PHASE2.md.
==========================================================================

  H11  earnings-announcement return drift - 8-K Item 2.02 (or 12) acceptance times
  H12  standardized unexpected earnings drift - XBRL EPS from original 10-Qs

The information clock is the SEC acceptance time in New York, never the filing
date: a release accepted at 16:05 ET cannot inform a trade at 15:59.
"""

import bisect
import collections
import datetime as dt
import statistics

import leakage
import p2data
import h_stocks as hs
from h_common import UNREG_RF

EAR_OOS = "2009-01-01"
SUE_OOS = "2003-01-01"      # the whole sample is post-publication


def _days(a, b):
    return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days


def reaction_session(P, et_date, et_time):
    """First session whose prices can reflect a release accepted at (et_date, et_time)."""
    i = bisect.bisect_left(P.dates, et_date)
    if i >= P.n:
        return None
    if P.dates[i] != et_date:
        return i
    if et_time == "00:00:00" or et_time >= "16:00:00":
        return i + 1
    return i


# ----------------------------------------------------------------------- H11

def ear_events(P, *, one_day=False, members=None, cut=None):
    before = hs.before_date(P, cut)
    out = []
    for s, cik in P.sym_cik.items():
        if members and P.index[s] not in members:
            continue
        window = None
        for acc, form, items, accepted, _ in p2data.filings(cik):
            if form != "8-K":
                continue
            codes = items.split(",") if items else []
            if "2.02" not in codes and "12" not in codes:
                continue
            et_d, et_t = p2data.to_et(accepted)
            if before and et_d >= before:
                break
            if window and _days(window, et_d) < 45:
                continue
            window = et_d
            d0 = reaction_session(P, et_d, et_t)
            if d0 is None or d0 < 1 or d0 + 2 >= P.n or not hs.eligible(P, s, d0 - 1):
                continue
            end = d0 if one_day else d0 + 1
            if cut is not None and end > cut:
                continue
            a, b = P.C[s][d0 - 1], P.C[s][end]
            sa, sb = P.spy[d0 - 1], P.spy[end]
            if not (a and b and sa and sb):
                continue
            out.append({"sym": s, "known": end, "entry": d0 + 2, "signal": b / a - 1 - (sb / sa - 1)})
    return out


def h11():
    P = hs.panel()
    raw = ear_events(P)
    ev = hs.label(P, raw)
    neighbours = [
        ("EAR over one session", hs.label(P, ear_events(P, one_day=True)), 60),
        ("hold 30 sessions", ev, 30),
        ("hold 120 sessions", ev, 120),
        ("deciles", hs.label(P, raw, lo=0.1, hi=0.9), 60),
        ("S&P 500 names only", hs.label(P, ear_events(P, members={"SP500"})), 60),
        ("S&P 400 names only", hs.label(P, ear_events(P, members={"SP400"})), 60),
    ]
    base = hs.series(P, hs.intervals(P, ev, "long", 60), hs.intervals(P, ev, "short", 60))
    nb = [(nm, hs.series(P, hs.intervals(P, e, "long", hd), hs.intervals(P, e, "short", hd)))
          for nm, e, hd in neighbours]
    placebo = hs.event_placebo(P, ev, EAR_OOS, 60)
    placebo["describe"] = "signal permuted across out-of-sample events; statistic = 60-session abnormal-return spread"
    leak = leakage.truncation_test(lambda cut: hs.entry_vector(P, hs.label(P, ear_events(P, cut=cut))),
                                   P.n, lag=1)
    labelled = [e for e in ev if e["side"]]
    return hs.pair_records(
        P, hid="H11", cluster="PEAD-EAR", base=base, neighbours=nb, placebo=placebo, oos=EAR_OOS,
        leak=leak,
        texts=dict(data="SEC EDGAR 8-K Item 2.02/12 acceptance times; Yahoo prices; S&P 500 + 400 members",
                   ls_name="Earnings-reaction drift, long/short",
                   lo_name="Earnings-reaction drift, long-only",
                   ls_hyp="The strongest 3-day reactions to earnings keep beating the weakest for 60 sessions",
                   lo_hyp="Holding the strongest earnings reactions for 60 sessions beats holding the universe",
                   ls_costs="5/10bp per side + 0.30%/yr borrow (2x costs)",
                   lo_costs="5/10bp per side (2x costs)"),
        extra={"earnings_8k_events": len(raw), "labelled_events": len(labelled),
               "events_per_year": dict(sorted(collections.Counter(P.dates[e["entry"]][:4] for e in labelled).items())),
               "oos_placebo_events": placebo["events"], "oos_abnormal_return_by_bucket": placebo["oos_buckets"]},
        notes=["Placebo statistic is event-level (PREREG_PHASE2 G7), not a Sharpe ratio."],
        unregistered=[UNREG_RF, "A filing's 45-day de-duplication window is anchored on the first earnings "
                                "8-K considered, even if that one is later skipped for missing prices."])


# ----------------------------------------------------------------------- H12

def sue_events(P, *, basic_only=False, members=None, cut=None):
    before = hs.before_date(P, cut)
    concepts = ("EarningsPerShareBasic",) if basic_only else ("EarningsPerShareDiluted", "EarningsPerShareBasic")
    out = []
    for s, cik in P.sym_cik.items():
        if members and P.index[s] not in members:
            continue
        accepted = {r[0]: r[3] for r in p2data.filings(cik) if r[1] == "10-Q"}
        delta = {}
        for concept in concepts:
            by_acc = collections.defaultdict(list)
            for accn, start, end, val in p2data.eps_facts(cik, concept):
                by_acc[accn].append((start, end, val))
            for accn, facts in by_acc.items():
                if accn in delta or accn not in accepted:
                    continue
                quarter = [(e, v) for st, e, v in facts if 80 <= _days(st, e) <= 100]
                if not quarter:
                    continue
                cur_end = max(e for e, _ in quarter)
                cur = next(v for e, v in quarter if e == cur_end)
                comps = sorted((abs(_days(e, cur_end) - 365), v) for e, v in quarter
                               if 350 <= _days(e, cur_end) <= 380)
                if comps:
                    delta[accn] = cur - comps[0][1]
        history = []
        for when, d_eps in sorted((accepted[a], d) for a, d in delta.items()):
            et_d, _ = p2data.to_et(when)
            if before and et_d >= before:
                break
            prior = history[-6:]
            history.append(d_eps)
            if len(prior) < 4:
                continue
            sd = statistics.stdev(prior)
            entry = bisect.bisect_right(P.dates, et_d)
            if sd <= 0 or entry < 1 or entry >= P.n or not hs.eligible(P, s, entry - 1):
                continue
            out.append({"sym": s, "known": entry - 1, "entry": entry, "signal": d_eps / sd})
    return out


def h12():
    P = hs.panel()
    raw = sue_events(P)
    ev = hs.label(P, raw)
    neighbours = [
        ("hold 30 sessions", ev, 30),
        ("hold 120 sessions", ev, 120),
        ("deciles", hs.label(P, raw, lo=0.1, hi=0.9), 60),
        ("basic EPS only", hs.label(P, sue_events(P, basic_only=True)), 60),
        ("S&P 500 names only", hs.label(P, sue_events(P, members={"SP500"})), 60),
        ("S&P 400 names only", hs.label(P, sue_events(P, members={"SP400"})), 60),
    ]
    base = hs.series(P, hs.intervals(P, ev, "long", 60), hs.intervals(P, ev, "short", 60))
    nb = [(nm, hs.series(P, hs.intervals(P, e, "long", hd), hs.intervals(P, e, "short", hd)))
          for nm, e, hd in neighbours]
    placebo = hs.event_placebo(P, ev, SUE_OOS, 60)
    placebo["describe"] = "SUE permuted across events; statistic = 60-session abnormal-return spread"
    leak = leakage.truncation_test(lambda cut: hs.entry_vector(P, hs.label(P, sue_events(P, cut=cut))),
                                   P.n, lag=1)
    labelled = [e for e in ev if e["side"]]
    return hs.pair_records(
        P, hid="H12", cluster="PEAD-SUE", base=base, neighbours=nb, placebo=placebo, oos=SUE_OOS,
        leak=leak,
        texts=dict(data="SEC XBRL EPS from original 10-Qs + EDGAR acceptance times; Yahoo prices; S&P 500 + 400",
                   ls_name="Earnings-surprise drift, long/short",
                   lo_name="Earnings-surprise drift, long-only",
                   ls_hyp="Stocks with the largest standardized earnings surprises beat those with the "
                          "smallest for 60 sessions after the 10-Q",
                   lo_hyp="Holding the largest standardized earnings surprises for 60 sessions beats the universe",
                   ls_costs="5/10bp per side + 0.30%/yr borrow (2x costs)",
                   lo_costs="5/10bp per side (2x costs)"),
        extra={"sue_events": len(raw), "labelled_events": len(labelled),
               "events_per_year": dict(sorted(collections.Counter(P.dates[e["entry"]][:4] for e in labelled).items())),
               "placebo_events": placebo["events"], "abnormal_return_by_bucket": placebo["oos_buckets"]},
        notes=["Event date is the 10-Q, usually weeks after the earnings press release, so this measures "
               "drift that remains once the formal filing is public."],
        unregistered=[UNREG_RF, "If one filing reports two comparative quarters equally close to 365 days, "
                                "the lower value wins the sort tie."])
