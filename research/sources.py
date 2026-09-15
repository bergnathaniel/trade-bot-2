"""
Point-in-time, survivorship-aware data sources for the edge research program.
=============================================================================

Adds what `data.py` (Yahoo bars) does not have:

  french_table()          Ken French data library. CRSP-based, so delisted firms
                          ARE in the portfolios - the only free survivorship-free
                          US equity data there is.
  fred()                  FRED series. Used ONLY for after-the-fact regime labels:
                          observation dates are not release dates (CPI lands ~2
                          weeks late, NBER recession dates months-to-years late).
  fomc_statement_dates()  Scheduled FOMC statement days from federalreserve.gov.
                          The schedule is published about a year ahead, so acting
                          on it at the prior close uses no future information.

Everything is cached under research/.cache. Pure stdlib + requests.
"""

import csv
import datetime as dt
import functools
import io
import json
import os
import re
import time
import zipfile

import certifi
import requests

import data

CACHE = data.CACHE
FRENCH_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/{}"
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
FED = "https://www.federalreserve.gov/monetarypolicy/"
DAY, WEEK = 24 * 3600, 7 * 24 * 3600


def _cached(key, url, binary=False, max_age=WEEK):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, key)
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age:
        with open(path, "rb") as f:
            raw = f.read()
    else:
        r = requests.get(url, headers=data.UA, timeout=60, verify=certifi.where())
        r.raise_for_status()
        raw = r.content
        with open(path, "wb") as f:
            f.write(raw)
    return raw if binary else raw.decode("utf-8", "replace")


# ------------------------------------------------------------ French library

def _period(tok):
    return f"{tok[:4]}-{tok[4:6]}" if len(tok) == 6 else f"{tok[:4]}-{tok[4:6]}-{tok[6:8]}"


@functools.lru_cache(maxsize=None)
def french_sections(name):
    """
    {section title: (columns, {period: [decimal or None]})} for one library zip.

    Periods are 'YYYY-MM' or 'YYYY-MM-DD'; annual sections are dropped. Values
    are converted from percent to decimals, and the library's missing-data codes
    (-99.99, -999) become None rather than a -100% "return".
    """
    raw = _cached("french_" + name, FRENCH_URL.format(name), binary=True)
    z = zipfile.ZipFile(io.BytesIO(raw))
    text = z.read(z.namelist()[0]).decode("latin-1")
    out, title, cols, rows = {}, "main", None, None
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().split(",")]
        if not any(cells):
            continue
        if cols is not None and re.fullmatch(r"\d{6}|\d{8}", cells[0]):
            vals = []
            for c in cells[1:1 + len(cols)]:
                try:
                    v = float(c)
                except ValueError:
                    v = None
                vals.append(None if v is None or v <= -99.99 else v / 100.0)
            rows[_period(cells[0])] = vals
        elif cells[0] == "" and len(cells) > 1:
            cols, rows = cells[1:], {}
            key = title
            while key in out:
                key += "'"
            out[key] = (cols, rows)
        elif not re.fullmatch(r"\d{4}", cells[0]):
            title, cols = line.strip(), None
    return out


def french_table(name, section=None):
    """(columns, rows) of the first non-empty section whose title contains `section`."""
    secs = french_sections(name)
    for title, (cols, rows) in secs.items():
        if rows and (section is None or section.lower() in title.lower()):
            return cols, rows
    raise KeyError(f"{name}: no section matching {section!r}; sections: {list(secs)}")


def col_index(cols, col):
    norm = lambda s: re.sub(r"\s+", " ", s.strip().lower())
    for j, c in enumerate(cols):
        if norm(c) == norm(col):
            return j
    raise KeyError(f"column {col!r} not in {cols}")


def french_column(name, col, section=None):
    """{period: decimal} for one column, missing values dropped."""
    cols, rows = french_table(name, section)
    j = col_index(cols, col)
    return {p: v[j] for p, v in rows.items() if j < len(v) and v[j] is not None}


# ---------------------------------------------------------------------- FRED

def fred(series_id):
    """{date: float} for a FRED series; FRED's '.' missing marker is skipped."""
    txt = _cached(f"fred_{series_id}.csv", FRED_URL.format(series_id), max_age=DAY)
    out = {}
    for row in csv.reader(io.StringIO(txt)):
        if len(row) < 2:
            continue
        try:
            out[row[0]] = float(row[1])
        except ValueError:
            continue
    return out


# ---------------------------------------------------------------------- FOMC

_MON = {m[:3]: i + 1 for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"])}
_MON_RE = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
_EXCLUDE = ("unscheduled", "conference call", "notation", "cancel")


def _last_day(text, year):
    """'January 31-February 1' / 'Jan/Feb' + '31-1' / 'June 16-17*' -> last calendar day."""
    months = re.findall(_MON_RE, text.lower())
    days = re.findall(r"\d+", text)
    if not months or not days:
        return None
    return f"{year:04d}-{_MON[months[-1][:3]]:02d}-{int(days[-1]):02d}"


def _fomc_historical(year):
    """(kept, excluded) from fomchistoricalYYYY.htm; None if the page does not exist."""
    try:
        html = _cached(f"fomc_hist_{year}.htm", FED + f"fomchistorical{year}.htm",
                       max_age=365 * DAY)
    except requests.HTTPError:
        return None
    kept, excluded = [], []
    for raw in re.findall(r"<h5[^>]*>([^<]+)</h5>", html):     # 2011+ pages add a class attribute
        t = " ".join(raw.split())
        m = re.search(r"-\s*(\d{4})\s*$", t)
        if not m or int(m.group(1)) != year:
            continue
        low = t.lower()
        if " meeting" not in low or any(x in low for x in _EXCLUDE):
            excluded.append(t)
            continue
        d = _last_day(t[:low.index(" meeting")], year)
        (kept if d else excluded).append(d or t)
    return kept, excluded


def _fomc_recent():
    """(kept, excluded) from the current calendars page (most recent ~5 years)."""
    html = _cached("fomc_calendars.htm", FED + "fomccalendars.htm", max_age=WEEK)
    kept, excluded = [], []
    parts = re.split(r"(\d{4})\s+FOMC Meetings", html)
    for k in range(1, len(parts) - 1, 2):
        year, chunk = int(parts[k]), parts[k + 1]
        for row in re.split(r'class="[^"]*fomc-meeting__month', chunk)[1:]:
            mon = re.search(r"<strong>([^<]+)</strong>", row)
            day = re.search(r'fomc-meeting__date[^>]*>([^<]+)<', row)
            if not mon or not day:
                continue
            label = f"{mon.group(1)} {day.group(1)}".strip()
            if any(x in label.lower() for x in _EXCLUDE):
                excluded.append(f"{label} {year}")
                continue
            d = _last_day(label, year)
            (kept if d else excluded).append(d or f"{label} {year}")
    return kept, excluded


def fomc_statement_dates(start_year=1994):
    """
    Sorted statement dates of SCHEDULED FOMC meetings from `start_year` up to
    yesterday, plus the list of excluded entries (calls, unscheduled, cancelled,
    notation votes, unparsed, merged) so the exclusions can be audited rather
    than trusted.

    Two traps in the Fed's pages: the pre-empted March 17-18 2020 meeting is
    still listed (marked cancelled - no statement exists), and September 2003
    lists sessions on the 15th and 16th separately. Sessions on consecutive
    days are one meeting, so they collapse to the last day, the statement day.
    """
    dates, excluded = set(), []
    for y in range(start_year, time.gmtime().tm_year + 1):
        got = _fomc_historical(y)
        if got:
            dates.update(got[0])
            excluded += got[1]
    kept, exc = _fomc_recent()
    dates.update(d for d in kept if d[:4] >= str(start_year))
    excluded += exc
    today = time.strftime("%Y-%m-%d", time.gmtime())
    merged = []
    for d in sorted(x for x in dates if x < today):
        if merged and (dt.date.fromisoformat(d) - dt.date.fromisoformat(merged[-1])).days == 1:
            excluded.append(f"{merged[-1]} merged into {d} (consecutive-day sessions)")
            merged[-1] = d
        else:
            merged.append(d)
    return merged, excluded


# ---------------------------------------------------------- Treasury auctions

FISCAL = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/"
          "accounting/od/auctions_query")
AUCTION_FIELDS = ("auction_date,announcemt_date,issue_date,security_type,security_term,"
                  "original_security_term,reopening,inflation_index_security,closing_time_comp,cusip")


def treasury_auctions():
    """
    Every Treasury auction on record (fiscaldata.treasury.gov), oldest first.

    The auction schedule is announced in advance (the announcement date is
    typically a week before; the quarterly refunding calendar months before),
    and results post at the competitive close (1:00 pm ET for coupons), so a
    position taken at the close of the day BEFORE an auction or at the close of
    the auction day itself uses no future information.
    """
    path = os.path.join(CACHE, "fiscal_auctions.json")
    if os.path.exists(path) and time.time() - os.path.getmtime(path) < DAY:
        with open(path) as f:
            return json.load(f)
    rows, page = [], 1
    while True:
        r = requests.get(FISCAL, headers=data.UA, timeout=60, verify=certifi.where(),
                         params={"fields": AUCTION_FIELDS, "page[size]": 10000,
                                 "page[number]": page, "sort": "auction_date"})
        r.raise_for_status()
        body = r.json()
        rows += body["data"]
        if page >= body["meta"]["total-pages"]:
            break
        page += 1
    os.makedirs(CACHE, exist_ok=True)
    with open(path, "w") as f:
        json.dump(rows, f)
    return rows
