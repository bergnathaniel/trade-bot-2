"""
Phase-2 data layer: stock universe, SEC filings, XBRL earnings, insider trades.
==============================================================================

    python3 research/p2data.py      # build every cache (SEC + Yahoo; ~20-30 min cold)

Everything lands in research/.cache/p2 and is reused, so a rerun tests exactly
the same inputs. Point-in-time rules live next to the code that enforces them:

  universe()              today's S&P 500 + MidCap 400 members, frozen at first fetch.
                          Survivorship-biased by construction - see gate G10.
  filings(cik)            8-K and 10-Q accession, items and acceptanceDateTime (UTC).
  to_et(...)              UTC -> New York time; the only clock trading decisions use.
  eps_facts(cik, concept) XBRL EPS facts from original 10-Qs, with period start/end.
  insider_transactions()  open-market P/S trades from the SEC's quarterly Form 4 data
                          sets, streamed in memory and reduced to six columns.

SEC fair access: at most ~9 requests a second, retries with backoff, and a
User-Agent naming the project. Pure stdlib + requests.
"""

import csv
import datetime as dt
import io
import json
import os
import re
import sys
import time
import zipfile
from zoneinfo import ZoneInfo

import certifi
import requests

import data

CACHE = os.path.join(data.CACHE, "p2")
SEC_UA = {"User-Agent": "Trade-Bot-Research/1.0 personal-research",
          "Accept-Encoding": "gzip, deflate"}
NY = ZoneInfo("America/New_York")
WIKI = {"SP500": "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "SP400": "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"}
INSIDER_PAGE = "https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets"
KEEP_FORMS = {"8-K", "10-Q"}
_last_request = [0.0]


def _path(*parts):
    p = os.path.join(CACHE, *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def _load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _save(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, separators=(",", ":"))
    os.replace(tmp, path)


def sec_get(url, tries=6):
    """GET from sec.gov within fair-access limits. None on 404."""
    for k in range(tries):
        wait = 0.115 - (time.time() - _last_request[0])
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.time()
        try:
            r = requests.get(url, headers=SEC_UA, timeout=180, verify=certifi.where())
        except requests.RequestException:
            time.sleep(2 ** k)
            continue
        if r.status_code == 200:
            return r.content
        if r.status_code == 404:
            return None
        time.sleep(2 ** k + 1)
    raise RuntimeError(f"SEC fetch failed after {tries} tries: {url}")


# ------------------------------------------------------------------ universe

def universe():
    """
    Current S&P 500 + S&P MidCap 400 members, frozen at the first fetch so every
    rerun tests the same names. These are TODAY's members: firms that went
    bankrupt, were acquired or shrank out of the indexes are absent, and firms
    that grew into them are present. That is survivorship bias; gate G10 records it.
    """
    path = _path("universe.json")
    got = _load(path)
    if got:
        return got
    tick = json.loads(sec_get("https://www.sec.gov/files/company_tickers.json"))
    by_ticker = {v["ticker"].upper(): int(v["cik_str"]) for v in tick.values()}
    members, seen = [], set()
    for idx, url in WIKI.items():
        html = requests.get(url, headers=data.UA, timeout=60, verify=certifi.where()).text
        table = re.search(r'<table[^>]*id="constituents"[^>]*>(.*?)</table>', html, re.S).group(1)
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S):
            cells = [re.sub(r"<[^>]+>", "", c).strip()
                     for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S)]
            if not cells or cells[0] in ("", "Symbol"):
                continue
            sym = cells[0].upper()
            cik = int(cells[6]) if idx == "SP500" and len(cells) > 6 and cells[6].isdigit() else None
            link = re.search(r"CIK=(\d+)", tr)
            if cik is None and link:
                cik = int(link.group(1))
            if cik is None:
                cik = by_ticker.get(sym) or by_ticker.get(sym.replace(".", "-"))
            if cik is None or cik in seen:
                continue
            seen.add(cik)
            members.append({"ticker": sym, "yahoo": sym.replace(".", "-"), "cik": cik,
                            "index": idx, "name": cells[1] if len(cells) > 1 else sym})
    out = {"fetched": time.strftime("%Y-%m-%d"), "members": members}
    _save(path, out)
    return out


# ------------------------------------------------------------------- EDGAR

def filings(cik):
    """
    [accession, form, items, acceptanceDateTime (UTC), filingDate] for every
    8-K and 10-Q since 2002, oldest first. The filing DATE is not the information
    time: a filing accepted at 17:31 ET is dated the next business day.
    """
    path = _path("edgar", f"{cik}.json")
    got = _load(path)
    if got is not None:
        return got
    raw = sec_get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
    if raw is None:
        _save(path, [])
        return []
    j = json.loads(raw)
    blocks = [j["filings"]["recent"]]
    for f in j["filings"].get("files", []):
        if f["filingTo"] >= "2002-01-01":
            extra = sec_get("https://data.sec.gov/submissions/" + f["name"])
            if extra:
                blocks.append(json.loads(extra))
    rows = {}
    for b in blocks:
        for i, form in enumerate(b["form"]):
            if form in KEEP_FORMS and b["filingDate"][i] >= "2002-01-01":
                rows[b["accessionNumber"][i]] = [b["accessionNumber"][i], form, b["items"][i],
                                                 b["acceptanceDateTime"][i], b["filingDate"][i]]
    out = sorted(rows.values(), key=lambda r: r[3])
    _save(path, out)
    return out


def to_et(acceptance):
    """'2026-07-30T20:30:28.000Z' (UTC) -> ('2026-07-30', '16:30:28') in New York time."""
    t = dt.datetime.strptime(acceptance[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)
    t = t.astimezone(NY)
    return t.strftime("%Y-%m-%d"), t.strftime("%H:%M:%S")


def eps_facts(cik, concept):
    """[accession, start, end, value] for every USD/share fact reported on an original 10-Q."""
    path = _path("xbrl", f"{cik}_{concept}.json")
    got = _load(path)
    if got is not None:
        return got
    raw = sec_get(f"https://data.sec.gov/api/xbrl/companyconcept/CIK{int(cik):010d}/us-gaap/{concept}.json")
    rows = []
    if raw:
        for f in json.loads(raw).get("units", {}).get("USD/shares", []):
            if f.get("form") == "10-Q" and f.get("start") and f.get("end"):
                rows.append([f["accn"], f["start"], f["end"], f["val"]])
    _save(path, rows)
    return rows


# ------------------------------------------------------------ insider trades

def _iso(s):
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(s.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _tsv(z, name, cols):
    with z.open(name) as fh:
        rd = csv.reader(io.TextIOWrapper(fh, encoding="utf-8", errors="replace", newline=""),
                        delimiter="\t", quoting=csv.QUOTE_NONE)
        head = next(rd)
        ix = [head.index(c) for c in cols]
        top = max(ix)
        for row in rd:
            if len(row) > top:
                yield [row[i] for i in ix]


def _parse_quarter(raw, want):
    z = zipfile.ZipFile(io.BytesIO(raw))
    subs = {}
    for acc, fdate, dtype, icik in _tsv(z, "SUBMISSION.tsv",
                                        ["ACCESSION_NUMBER", "FILING_DATE", "DOCUMENT_TYPE", "ISSUERCIK"]):
        if dtype.strip() == "4":
            try:
                c = int(icik)
            except ValueError:
                continue
            fd = _iso(fdate)
            if c in want and fd:
                subs[acc] = (fd, c)
    owners = {}
    for acc, ocik, rel in _tsv(z, "REPORTINGOWNER.tsv",
                               ["ACCESSION_NUMBER", "RPTOWNERCIK", "RPTOWNER_RELATIONSHIP"]):
        if acc in subs:
            owners.setdefault(acc, []).append((ocik.strip(), rel.strip()))
    out = []
    for acc, tdate, code, ad in _tsv(z, "NONDERIV_TRANS.tsv",
                                     ["ACCESSION_NUMBER", "TRANS_DATE", "TRANS_CODE", "TRANS_ACQUIRED_DISP_CD"]):
        code, ad = code.strip(), ad.strip()
        if acc not in subs or (code, ad) not in (("P", "A"), ("S", "D")):
            continue
        td = _iso(tdate)
        if not td:
            continue
        fd, icik = subs[acc]
        for ocik, rel in owners.get(acc, []):
            out.append([fd, td, icik, ocik, code, rel])
    return out


def insider_transactions(ciks):
    """
    [filing_date, trans_date, issuer_cik, owner_cik, code, relationship] for
    open-market purchases (P) and sales (S) on original Form 4s by `ciks`, 2006Q1 on.
    Each quarterly zip is read in memory; only this extract is cached.
    """
    want = {int(c) for c in ciks}
    links_path = _path("insider", "_links.json")
    links = _load(links_path)
    if not links:
        page = sec_get(INSIDER_PAGE).decode("utf-8", "replace")
        links = sorted(set(re.findall(r'href="([^"]*_form345\.zip)"', page)),
                       key=lambda u: u.rsplit("/", 1)[-1])
        _save(links_path, links)
    rows = []
    for link in links:
        quarter = link.rsplit("/", 1)[-1].split("_")[0]
        path = _path("insider", f"{quarter}.json")
        got = _load(path)
        if got is None:
            raw = sec_get(link if link.startswith("http") else "https://www.sec.gov" + link)
            got = _parse_quarter(raw, want) if raw else []
            _save(path, got)
        rows += got
    return rows


# ------------------------------------------------------------------- prices

def prices(members, log=print):
    """Warm the Yahoo cache (data.fetch) for every member, politely, with retries."""
    ok = 0
    for k, m in enumerate(members):
        bars = []
        for attempt in range(4):
            bars = data.fetch(m["yahoo"], quiet=True)
            if bars:
                break
            time.sleep(2 + 3 * attempt)
        ok += len(bars) > 312
        time.sleep(0.12)
        if (k + 1) % 100 == 0:
            log(f"  prices {k + 1}/{len(members)} ({ok} usable)")
    return ok


# -------------------------------------------------------------------- build

def coverage():
    u = universe()
    mem = u["members"]
    ins_dir = os.path.join(CACHE, "insider")
    return {"universe_fetched": u["fetched"], "members": len(mem),
            "sp500": sum(m["index"] == "SP500" for m in mem),
            "sp400": sum(m["index"] == "SP400" for m in mem),
            "edgar_cached": sum(os.path.exists(os.path.join(CACHE, "edgar", f"{m['cik']}.json")) for m in mem),
            "xbrl_cached": sum(os.path.exists(os.path.join(CACHE, "xbrl", f"{m['cik']}_EarningsPerShareDiluted.json"))
                               for m in mem),
            "insider_quarters_cached": len([f for f in os.listdir(ins_dir) if f[:4].isdigit()])
            if os.path.isdir(ins_dir) else 0}


def build():
    t0 = time.time()
    say = lambda s: print(f"[{time.time() - t0:6.0f}s] {s}", flush=True)  # noqa: E731
    mem = universe()["members"]
    say(f"universe: {len(mem)} names")
    say(f"prices: {prices(mem, say)} of {len(mem)} usable")
    n8 = n10 = 0
    for k, m in enumerate(mem):
        rows = filings(m["cik"])
        n8 += sum(1 for r in rows if r[1] == "8-K" and r[2] and re.search(r"(^|,)(2\.02|12)(,|$)", r[2]))
        n10 += sum(1 for r in rows if r[1] == "10-Q")
        eps_facts(m["cik"], "EarningsPerShareDiluted")
        eps_facts(m["cik"], "EarningsPerShareBasic")
        if (k + 1) % 50 == 0:
            say(f"  SEC {k + 1}/{len(mem)}: {n8} earnings 8-Ks, {n10} 10-Qs so far")
    say(f"SEC done: {n8} earnings 8-Ks, {n10} 10-Qs")
    tx = insider_transactions([m["cik"] for m in mem])
    say(f"insider trades: {len(tx)} open-market P/S rows")
    say(f"coverage: {coverage()}")


if __name__ == "__main__":
    sys.exit(build())
