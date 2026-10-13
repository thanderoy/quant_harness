"""Build macro_events.csv from official-source pages already downloaded into raw/.

Run:  python3 -I build_calendar.py            (from anywhere; paths are relative to this file)

Fetching is done separately by scripts/fetch_*.py (see sources.md). This script only parses
local copies, so it is re-runnable offline and deterministic.

Scope: 2004-06-01 .. 2026-10-12 inclusive (local release date).
No price, return or market data is read; only release dates/times and page headers.
"""
from __future__ import annotations

import csv
import datetime as dt
import html
import logging
import os
import re
import subprocess
import sys
from zoneinfo import ZoneInfo

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'scripts'))
from fomc_parse import all_meetings  # noqa: E402
from ecb_parse import listing as ecb_listing  # noqa: E402
from boj_parse import primary as boj_primary  # noqa: E402

RAW = os.path.join(HERE, 'raw')
OUT_CSV = os.path.join(HERE, 'macro_events.csv')
WIN_START = dt.date(2004, 6, 1)
WIN_END = dt.date(2026, 10, 12)
TZ = {'ET': 'America/New_York', 'UK': 'Europe/London', 'EA': 'Europe/Berlin', 'JP': 'Asia/Tokyo'}
UTC = ZoneInfo('UTC')
MONTHS = {m: i + 1 for i, m in enumerate(
    'january february march april may june july august september october november december'.split())}
MON_ABBR = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6, 'jul': 7, 'aug': 8,
            'sep': 9, 'sept': 9, 'oct': 10, 'nov': 11, 'dec': 12}
FIELDS = ['event', 'scheduled', 'local_datetime', 'tz', 'utc_datetime', 'time_known', 'verified',
          'source_quality', 'source_url', 'note']
log = logging.getLogger(__name__)

FED = 'https://www.federalreserve.gov'
FED_2006_SCHED = FED + '/newsevents/pressreleases/monetary20060720b.htm'
FED_2011_PRESSER = FED + '/newsevents/pressreleases/monetary20110324a.htm'
FED_2013_TIME = FED + '/newsevents/pressreleases/monetary20130313a.htm'
FED_JOINT_20081008 = FED + '/newsevents/press/monetary/20081008a.htm'
ECB = 'https://www.ecb.europa.eu'
ECB_2022_TIME = ECB + '/press/pr/date/2022/html/ecb.pr220627~73acedf868.en.html'
BOE = 'https://www.bankofengland.co.uk'
BOE_NOON_NOW = BOE + '/monetary-policy'
BOE_2014_RESPONSE = BOE + '/-/media/boe/files/news/2014/december/transparency-and-the-boes-mpc-response'
BOE_WARSH = BOE + '/-/media/boe/files/news/2014/december/transparency-and-the-boes-mpc-review-by-kevin-warsh.pdf'
BOE_2014_APR = BOE + '/news/2014/march/change-to-timing-of-april-2014-mpc-meeting'
BOE_2020_NOV = BOE + '/news/2020/november/time-change-november-monetary-policy-report-and-monetary-policy-committee-decision-and-minutes'
BOE_2025_MAY = BOE + '/news/2025/may/statement-on-the-timing-of-the-mpr-and-mpc-minutes'
BOJ = 'https://www.boj.or.jp'


# ----------------------------------------------------------------------------- helpers
def page_text(path: str) -> str:
    t = open(path, 'rb').read().decode('utf-8', 'replace')
    t = re.sub(r'<script.*?</script>|<style.*?</style>', '', t, flags=re.S)
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', t)))


def pdf_text(path: str, last_page: int = 1) -> str:
    r = subprocess.run(['pdftotext', '-l', str(last_page), path, '-'], capture_output=True, text=True)
    return re.sub(r'\s+', ' ', r.stdout)


def parse_mdy(s: str) -> dt.date:
    """'January 28, 2004' / 'Sept. 8, 2006' -> date."""
    m = re.match(r'([A-Za-z]+)\.? (\d{1,2}), (\d{4})', s.strip())
    name = m.group(1).lower()
    mon = MONTHS.get(name) or MON_ABBR[name[:4] if name.startswith('sept') else name[:3]]
    return dt.date(int(m.group(3)), mon, int(m.group(2)))


def parse_dmy(s: str) -> dt.date:
    """'8 October 2008' -> date."""
    d, mo, y = s.strip().split()
    return dt.date(int(y), MONTHS[mo.lower()], int(d))


def clock(s: str) -> dt.time:
    """'2:00 p.m.' / '8:30 A.M.' / '11:36 a.m.' -> time."""
    m = re.match(r'(\d{1,2})[:.](\d{2}) ?([ap])', s.strip(), re.I)
    h, mi, ap = int(m.group(1)), int(m.group(2)), m.group(3).lower()
    if ap == 'p' and h != 12:
        h += 12
    if ap == 'a' and h == 12:
        h = 0
    return dt.time(h, mi)


def mk(event: str, scheduled: bool, day: dt.date, t: dt.time | None, tzkey: str, verified: bool,
       url: str, note: str, quality: str = 'official', stated_abbr: str | None = None) -> dict:
    tzname = TZ[tzkey]
    if t is None:
        local, utc = day.isoformat(), ''
    else:
        ldt = dt.datetime.combine(day, t, tzinfo=ZoneInfo(tzname))
        if stated_abbr:  # cross-check source-stated EST/EDT against zoneinfo
            got = ldt.tzname()
            if got != stated_abbr.upper():
                note += f' [tz check: source says {stated_abbr}, zoneinfo gives {got}]'
                verified = False
        local = ldt.strftime('%Y-%m-%dT%H:%M:%S')
        utc = ldt.astimezone(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
    return dict(event=event, scheduled=str(scheduled).lower(), local_datetime=local, tz=tzname,
                utc_datetime=utc, time_known=str(t is not None).lower(), verified=str(verified).lower(),
                source_quality=quality, source_url=url, note=note.strip(), _day=day)


def in_window(d: dt.date) -> bool:
    return WIN_START <= d <= WIN_END


# ----------------------------------------------------------------------------- FOMC
FOMC_TRANSCRIPT_215 = {  # meeting statement date -> transcript evidence (see sources.md)
    dt.date(2005, 5, 3): FED + '/monetarypolicy/files/FOMC20050503meeting.pdf',
    dt.date(2006, 6, 29): FED + '/monetarypolicy/files/FOMC20060629meeting.pdf',
}


def fomc_presconf_times() -> dict[dt.date, tuple[dt.time, str]]:
    out = {}
    d = os.path.join(RAW, 'fomc', 'presconf')
    for f in sorted(os.listdir(d)):
        s = page_text(os.path.join(d, f))
        m = re.search(r'Statement \(Released ([A-Z][a-z]+ \d{1,2}, \d{4}) at (\d{1,2}:\d{2} [ap]\.m\.)\)', s)
        if m:
            out[parse_mdy(m.group(1))] = (clock(m.group(2)), FED + '/monetarypolicy/' + f)
    return out


def fomc_rows() -> list[dict]:
    rows = []
    presconf = fomc_presconf_times()
    for m in all_meetings(RAW):
        head = m['heading']
        unsched = bool(re.search(r'Conference Call|\(unscheduled\)|\(notation vote\)', head))
        for href in m['statements']:
            path = os.path.join(RAW, 'fomc', 'stmt', href.strip('/').replace('/', '__'))
            s = page_text(path)
            md = re.search(r'Release Date: ([A-Z][a-z]+ \d{1,2}, \d{4})', s) or \
                re.search(r'links provided below\. ([A-Z][a-z]+ \d{1,2}, \d{4})', s)
            day = parse_mdy(md.group(1))
            if not in_window(day):
                continue
            url = FED + href
            note = f'calendar heading: "{head}"'
            if href.endswith('20070618a.htm'):
                note += '; calendar links file 20070618a.htm, whose content is the June 28, 2007 statement'
            mt = re.search(r'For release at (\d{1,2}:\d{2} [ap]\.m\.) ([A-Z]{3})', s)
            if mt:
                rows.append(mk('FOMC', not unsched, day, clock(mt.group(1)), 'ET', True, url,
                               note + '; time stated on release ("For release at ...")', stated_abbr=mt.group(2)))
                continue
            if day in presconf:
                t, purl = presconf[day]
                rows.append(mk('FOMC', not unsched, day, t, 'ET', True, url,
                               note + f'; press-conference meeting, statement time from {purl}'))
                continue
            if day == dt.date(2008, 10, 8):
                rows.append(mk('FOMC', False, day, dt.time(7, 0), 'ET', True, url, note))
                continue
            if unsched:
                rows.append(mk('FOMC', False, day, None, 'ET', True, url,
                               note + '; intermeeting action, release says "For immediate release" with no time; '
                                      'no official time found'))
                continue
            if day >= dt.date(2013, 3, 20):
                rows.append(mk('FOMC', True, day, dt.time(14, 0), 'ET', True, url,
                               note + f'; 2:00 p.m. for all regularly scheduled meetings per {FED_2013_TIME} '
                                      '(release page itself says "For immediate release")'))
                continue
            # scheduled, pre-2013-03-20, no per-release time: 2:15 p.m. standing practice
            if day.year == 2011:
                ver, why = True, f'2011 non-press-conference meeting; 2:15 p.m. per {FED_2011_PRESSER}'
            elif day == dt.date(2006, 10, 25):
                ver, why = True, f'time announced for this meeting in {FED_2006_SCHED}'
            elif day in FOMC_TRANSCRIPT_215:
                ver, why = True, f'2:15 p.m. stated for this meeting in transcript {FOMC_TRANSCRIPT_215[day]}'
            else:
                ver, why = False, ('2:15 p.m. is the documented standing practice (FOMC transcripts May-2005, '
                                   f'Jun-2006, Aug-2006, May-2007; {FED_2011_PRESSER}) but no official source '
                                   'states the time for this specific release')
            rows.append(mk('FOMC', True, day, dt.time(14, 15), 'ET', ver, url, note + '; ' + why))
    return rows


# ----------------------------------------------------------------------------- BLS
def bls_index(fname: str) -> dict[str, str]:
    """archive file basename -> reference-month label, from the official archive index page."""
    t = open(os.path.join(RAW, 'bls', fname), encoding='utf-8', errors='replace').read()
    t = re.sub(r'<!--.*?-->', '', t, flags=re.S)
    out = {}
    for li in re.findall(r'<li>.*?</li>', t, flags=re.S):
        m = re.search(r'([A-Z][a-z]+ \d{4}) (Employment Situation|Consumer Price Index)', li)
        if not m:
            continue
        for h in re.findall(r'href="(?:https://www\.bls\.gov)?(/news\.release/[^"]+)"', li):
            out[h.rsplit('/', 1)[1]] = (m.group(1), h)
    return out


def bls_header(path: str) -> tuple[dt.date, dt.time, str] | None:
    raw = open(path, 'rb').read().decode('utf-8', 'replace')
    s = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', raw)))
    i = s.lower().find('embargoed')
    if i < 0:
        return None
    w = s[i:i + 400]  # header only
    mt = re.search(r'(\d{1,2}:\d{2}) ?([AaPp])\.?[Mm]\.? ?\(?(E[SD]?T)\)?', w)
    if not mt:
        return None
    md = re.search(r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'
                   r' \d{1,2}, ?\d{4}', w[mt.end():mt.end() + 160])
    if not md:
        return None
    md = [re.sub(r',(\d)', r', \1', md.group(0))]
    return parse_mdy(md[0]), clock(f'{mt.group(1)} {mt.group(2)}m'), mt.group(3)


def bls_rows() -> list[dict]:
    rows = []
    for idx, ev in [('empsit.htm', 'NFP'), ('cpi.htm', 'CPI')]:
        index = bls_index(idx)
        for base, (ref, href) in sorted(index.items()):
            path = os.path.join(RAW, 'bls', 'docs', base)
            if not base.endswith(('.htm', '.txt')) or int(ref.split()[1]) < 2004:
                continue
            url_date = re.search(r'_(\d{2})(\d{2})(\d{4})\.', base)
            url_day = dt.date(int(url_date.group(3)), int(url_date.group(1)), int(url_date.group(2)))
            url = 'https://www.bls.gov' + href
            if not os.path.exists(path):
                if in_window(url_day):
                    rows.append(mk(ev, True, url_day, None, 'ET', False, url,
                                   f'reference month {ref}; release document could not be retrieved (HTTP 403 on '
                                   'repeated attempts); date taken from the official archive file name '
                                   '(MMDDYYYY) only; time not verified'))
                continue
            hdr = bls_header(path)
            if hdr is None:
                if in_window(url_day):
                    rows.append(mk(ev, True, url_day, None, 'ET', False, url,
                                   f'reference month {ref}; embargo line not parsed; date from file name only'))
                continue
            day, t, abbr = hdr
            if not in_window(day):
                continue
            note = f'reference month {ref}; date/time from embargo line of the release'
            ver = True
            if day != url_day:
                note += f'; archive file name implies {url_day}'
                ver = False
            abbr = {'ET': None}.get(abbr, abbr)
            if day == dt.date(2012, 12, 7) and abbr == 'EDT':
                note += ('; release header says "8:30 a.m. (EDT)" but 7 Dec 2012 is in EST - treated as a label typo, '
                         '08:30 Eastern local time kept')
                abbr = None
            rows.append(mk(ev, True, day, t, 'ET', ver, url, note, stated_abbr=abbr))
    return rows


# ----------------------------------------------------------------------------- ECB
ECB_EXTRA = {  # intermeeting Governing Council policy releases outside the decisions list
    'pr100510.en.html': '/press/pr/date/2010/html/pr100510.en.html',
    'pr110807.en.html': '/press/pr/date/2011/html/pr110807.en.html',
    'ecb.pr220615~2aa3900e0a.en.html': '/press/pr/date/2022/html/ecb.pr220615~2aa3900e0a.en.html',
}


def ecb_rows() -> list[dict]:
    rows = []
    items = [r for r in ecb_listing(RAW) if r['title'].lower() == 'monetary policy decisions' or 'PEPP' in r['title']]
    for h in ECB_EXTRA.values():
        items.append(dict(date=None, href=h, title='extra'))
    for r in items:
        base = r['href'].rsplit('/', 1)[1]
        if r['date']:
            day = parse_dmy(r['date'])
        else:
            day = dt.date(2000 + int(re.search(r'pr(\d\d)(\d\d)(\d\d)', base).group(1)),
                          int(re.search(r'pr(\d\d)(\d\d)(\d\d)', base).group(2)),
                          int(re.search(r'pr(\d\d)(\d\d)(\d\d)', base).group(3)))
        if not in_window(day):
            continue
        url = ECB + r['href']
        ptxt = page_text(os.path.join(RAW, 'ecb', 'pr', base))
        if f'{day.day} {day.strftime("%B")} {day.year}' not in ptxt:
            log.warning('ECB page %s does not show date %s', base, day)
        if r['title'] == 'extra' or 'PEPP' in r['title']:
            what = {'pr100510': 'Governing Council decision on measures (incl. Securities Markets Programme), '
                                'announced outside a scheduled meeting',
                    'pr110807': 'Statement by the President on Governing Council decision (SMP), Sunday',
                    'ecb.pr220615': 'Statement after the ad hoc Governing Council meeting',
                    'ecb.pr200318_1': 'PEPP announced after an unscheduled Governing Council meeting'}
            key = next(k for k in what if base.startswith(k))
            date_note = 'date from file name and ECB press-release index' if r['title'] == 'extra' else \
                'date from ECB decisions listing'
            rows.append(mk('ECB', False, day, None, 'EA', True, url,
                           f'{what[key]}; {date_note}; release page gives no time and no official time was found'))
            continue
        if day == dt.date(2008, 10, 8):
            rows.append(mk('ECB', False, day, dt.time(13, 0), 'EA', True, url,
                           'coordinated rate cut with Fed/BoE/BoC/SNB/Riksbank, decided outside the scheduled '
                           f'meeting; time from joint release "For release at 7:00 a.m. EDT" ({FED_JOINT_20081008})'))
            continue
        if day >= dt.date(2022, 7, 21):
            rows.append(mk('ECB', True, day, dt.time(14, 15), 'EA', True, url,
                           f'14:15 CET from 21 Jul 2022 per {ECB_2022_TIME}; release states press conference 14:45'))
        elif day == dt.date(2022, 6, 9):
            rows.append(mk('ECB', True, day, dt.time(13, 45), 'EA', True, url,
                           f'13:45 CET: last meeting before the change; {ECB_2022_TIME} says "instead of 13:45"'))
        else:
            rows.append(mk('ECB', True, day, dt.time(13, 45), 'EA', False, url,
                           f'13:45 CET is the pre-July-2022 practice per {ECB_2022_TIME} ("instead of 13:45"); '
                           'no official source found stating it for this release or year; release page states '
                           'only the press-conference time (14:30)'))
    return rows


# ----------------------------------------------------------------------------- BoE
BOE_UNSCHEDULED = {
    dt.date(2008, 10, 8): (dt.time(12, 0), True,
                           'special MPC meeting held "some hours in advance of its normal schedule" (minutes); '
                           f'coordinated cut, time from joint release "For release at 7:00 a.m. EDT" ({FED_JOINT_20081008})'),
}


def boe_announcements() -> list[tuple[dt.date, str, str]]:
    out = []
    d = os.path.join(RAW, 'boe', 'pages')
    for f in sorted(os.listdir(d)):
        if not f.endswith('.htm'):
            continue
        rel = '/' + f[:-4].replace('__', '/')
        is_news = re.match(r'/news/\d{4}/[a-z]+/mpc-[a-z]+-\d{4}$', rel)
        is_mps = rel.startswith('/monetary-policy-summary-and-minutes/')
        if not (is_news or is_mps or rel in BOE_EXTRA_PAGES):
            continue
        s = page_text(os.path.join(d, f))
        m = re.search(r'Published on (\d{1,2} [A-Z][a-z]+ \d{4})', s)
        if not m:
            log.warning('no publish date on %s', rel)
            continue
        day, xnote = parse_dmy(m.group(1)), ''
        pdf = os.path.join(RAW, 'boe', 'pdf', f[:-4] + '.pdf')
        if os.path.exists(pdf):
            pm = re.search(r'\b(\d{1,2} (?:January|February|March|April|May|June|July|August|September|October|'
                           r'November|December) \d{4})\b', pdf_text(pdf))
            if pm and parse_dmy(pm.group(1)) != day:
                xnote = (f'; web page says "Published on {m.group(1)}" but the press-release PDF is dated '
                         f'{pm.group(1)} - PDF date used')
                day = parse_dmy(pm.group(1))
            elif pm:
                xnote = '; date matches press-release PDF'
        out.append((day, rel, s + ' ' + xnote, xnote))
    return out


BOE_EXTRA_PAGES = {
    '/news/2020/march/boe-measures-to-respond-to-the-economic-shock-from-covid-19',
}
BOE_EXCLUDE = {  # pages in the MPS series that are not decision announcements
    '/monetary-policy-summary-and-minutes/2020/13march-2020',  # minutes of the 10 Mar 2020 special meeting
}
BOE_SPECIAL_NO_TIME = {dt.date(2020, 3, 11), dt.date(2020, 3, 19)}  # special MPC meetings, no official time found


def boe_rows() -> list[dict]:
    rows = []
    seen = set()
    for day, rel, s, xnote in sorted(boe_announcements()):
        if not in_window(day) or day in seen:
            continue
        seen.add(day)
        url = BOE + rel
        if rel in BOE_EXCLUDE:
            continue
        special = day in BOE_SPECIAL_NO_TIME
        if day in BOE_UNSCHEDULED:
            t, ver, note = BOE_UNSCHEDULED[day]
            rows.append(mk('BOE', False, day, t, 'UK', ver, url, note))
            continue
        if special:
            rows.append(mk('BOE', False, day, None, 'UK', True, url,
                           'special (unscheduled) MPC decision; page gives date only, no official time found'))
            continue
        if day == dt.date(2020, 11, 5):
            rows.append(mk('BOE', True, day, dt.time(7, 0), 'UK', True, url,
                           f'brought forward from 12:00 to 07:00 GMT per {BOE_2020_NOV}'))
        elif day == dt.date(2025, 5, 8):
            rows.append(mk('BOE', True, day, dt.time(12, 2), 'UK', True, url,
                           f'12:02 BST (VE-day two-minute silence) per {BOE_2025_MAY}'))
        elif day == dt.date(2014, 4, 10):
            rows.append(mk('BOE', True, day, dt.time(12, 0), 'UK', True, url,
                           f'"announced at the originally scheduled time of 12.00 hrs (BST)" per {BOE_2014_APR}'))
        elif day >= dt.date(2015, 8, 6):
            rows.append(mk('BOE', True, day, dt.time(12, 0), 'UK', True, url,
                           'decision + minutes published together at 12 noon from Aug 2015 '
                           f'({BOE_2014_RESPONSE}; {BOE_NOON_NOW}; 12:00 confirmed as scheduled time in {BOE_2020_NOV})'))
        else:
            rows.append(mk('BOE', True, day, dt.time(12, 0), 'UK', False, url,
                           f'12:00 is the documented standing practice ("announces the MPC decision at midday", {BOE_WARSH}; '
                           f'{BOE_2014_APR}) but no official source states the time for this specific announcement'))
    return rows


def _boe_with_pdf_notes(rows: list[dict]) -> list[dict]:
    notes = {BOE + rel: xnote for _, rel, _, xnote in boe_announcements()}
    for r in rows:
        r['note'] = (r['note'] + notes.get(r['source_url'], '')).strip()
    return rows


# ----------------------------------------------------------------------------- BoJ
BOJ_SCHED_NOTE = BOJ + '/en/mopo/mpmsche_minu/index.htm'


def _boj_cells(path: str) -> list[str]:
    t = open(path, 'rb').read().decode('utf-8', 'replace')
    out = []
    for r in re.findall(r'<tr>(.*?)</tr>', t, re.S):
        cells = re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', r, re.S)
        if cells:
            out.append([re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', ' ', c))).strip() for c in cells])
    return out


def boj_meeting_evidence() -> tuple[set[dt.date], set[dt.date]]:
    """(last days of two-day MPMs, dates of Outlook 'Bank's View' releases), from official BoJ tables."""
    two_day: set[dt.date] = set()
    # 2004-2009: minutes index tables ("Meeting on June 14 and 15[, 2008]")
    for y in range(2004, 2010):
        p = os.path.join(RAW, 'boj', 'minutes', f'minu_{y}_index.htm')
        for row in _boj_cells(p):
            m = re.search(r'Meeting on ([A-Z][a-z]+) (\d{1,2}) and (?:([A-Z][a-z]+) )?(\d{1,2})', ' '.join(row))
            if m:
                mon = MONTHS[(m.group(3) or m.group(1)).lower()]
                two_day.add(dt.date(y, mon, int(m.group(4))))
    # 2010-2025 past-meetings table and 2026 current schedule ("Jan. 20 (Mon.), 21 (Tues.)")
    for fname, years in [('mopo_mpmsche_minu_past.htm', None), ('mpmsche_current.htm', None)]:
        t = open(os.path.join(RAW, 'boj', fname), 'rb').read().decode('utf-8', 'replace')
        flat = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', t)))
        for yblock in re.split(r'(?=Table : \d{4})', flat)[1:]:
            y = int(re.match(r'Table : (\d{4})', yblock).group(1))
            for m in re.finditer(r'([A-Z][a-z]+)\.? (\d{1,2}) \([A-Za-z]+\.\), (?:([A-Z][a-z]+)\.? )?(\d{1,2}) \([A-Za-z]+\.\)(?!, \d{4})',
                                 yblock):
                mon_name = (m.group(3) or m.group(1)).lower()
                mon = MONTHS.get(mon_name) or MON_ABBR[mon_name[:4] if mon_name.startswith('sept') else mon_name[:3]]
                two_day.add(dt.date(y, mon, int(m.group(4))))
    outlook: set[dt.date] = set()
    for row in _boj_cells(os.path.join(RAW, 'boj', 'outlook_index.htm')):
        if len(row) >= 2 and ("Bank's View" in row[1] or re.search(r'\b(April|October) \d{4}\b', row[1])):
            try:
                outlook.add(parse_mdy(row[0]))
            except (AttributeError, KeyError):
                pass
    return two_day, outlook


def boj_rows() -> list[dict]:
    rows = []
    two_day, outlook = boj_meeting_evidence()
    for r in boj_primary(RAW):
        day = parse_mdy(r['date'])
        if not in_window(day):
            continue
        url = BOJ + r['href']
        base = r['href'].rsplit('/', 1)[1]
        doc = os.path.join(RAW, 'boj', 'docs', base)
        text = pdf_text(doc, 2) if base.endswith('.pdf') else page_text(doc)
        note = 'date from BoJ "Statements on Monetary Policy" listing'
        verified = True
        if re.search(r'\bunscheduled (?:Monetary Policy Meeting|MPM)', text):
            sched = False
            note += '; statement says the meeting was unscheduled'
        elif day in two_day:
            sched = True
            note += '; regular two-day MPM per BoJ meeting tables'
        elif day in outlook:
            sched = True
            note += "; single-day MPM on an Outlook Report ('The Bank's View') release date"
        else:
            sched = True
            verified = False
            note += ('; single-day meeting that BoJ sources fetched here do not show as pre-scheduled or as '
                     'unscheduled - scheduled flag UNVERIFIED')
        if r['listed_time']:
            rows.append(mk('BOJ', sched, day, clock(r['listed_time']), 'JP', verified, url,
                           note + f'; "Announced at {r["listed_time"]}" in BoJ listing'))
        else:
            rows.append(mk('BOJ', sched, day, None, 'JP', verified, url,
                           note + f'; no release time given (BoJ releases "immediately after" the MPM, {BOJ_SCHED_NOTE})'))
    return rows


# ----------------------------------------------------------------------------- main
def main() -> None:
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    rows = fomc_rows() + bls_rows() + ecb_rows() + _boe_with_pdf_notes(boe_rows()) + boj_rows()

    def key(r: dict) -> tuple:
        if r['utc_datetime']:
            return (r['utc_datetime'], r['event'])
        return (r['_day'].isoformat() + 'T00:00:00Z', r['event'])

    rows.sort(key=key)
    with open(OUT_CSV, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)
    log.info('wrote %d rows to %s', len(rows), OUT_CSV)


if __name__ == '__main__':
    main()
