# Macro release calendar: sources and release-time rules

Window: 2004-06-01 to 2026-10-12 inclusive (local release date). Built 2026-10-12.
Output: `macro_events.csv` (1,438 rows). Re-run with `python3 -I build_calendar.py`, which parses
the local copies in `raw/` only. The fetchers in `scripts/fetch_*.py` re-download them.

All sources are official: federalreserve.gov, bls.gov, ecb.europa.eu, bankofengland.co.uk and
boj.or.jp. No row is `source_quality=secondary`. No price, return or market data was read.

## Column semantics

- `local_datetime` is naive local wall-clock time in the zone named in `tz`. When `time_known=false`
  it holds only the date, and `utc_datetime` is left **empty** rather than given an invented time.
  Those rows are sorted at 00:00Z of their local date.
- UTC conversion uses Python `zoneinfo` (America/New_York, Europe/London, Europe/Berlin,
  Asia/Tokyo) and no hand-coded offsets. Where a source states EST/EDT, the build checks the
  label against zoneinfo. The only conflict was NFP 2012-12-07, whose header says "(EDT)" in
  December. That is a typo in the release: the 08:30 Eastern time is kept and the row has a note.
- `verified=true` means the **date** is confirmed by a per-release official page **and** the
  time either (a) is stated for that specific release, or (b) falls inside the explicit
  effective period of an official timing rule. `verified=false` means at least one populated
  field rests on something weaker, usually a standing practice that an official source describes
  but does not date for that release. The note always says which.
- For `time_known=false` rows, `verified` refers to the date (and, for BoJ, the scheduled flag).

## FOMC (188 rows: 178 scheduled, 10 unscheduled)

Sources:
- Meeting calendars: `https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm` (2021–2027)
  and `https://www.federalreserve.gov/monetarypolicy/fomchistorical{YYYY}.htm` (2004–2020).
- Each statement page linked as "Statement". The release date comes from the page itself.
- Press-conference pages `.../monetarypolicy/fomcpresconf{YYYYMMDD}.htm` (2011–2013).
- Rule documents (in `raw/rules/`):
  - 2011-03-24, `.../newsevents/pressreleases/monetary20110324a.htm`: at the three 2011
    press-briefing meetings the statement is "expected to be released at around 12:30 p.m., one
    hour and forty-five minutes earlier than for other FOMC meetings", which implies 2:15 p.m.
    for the others.
  - 2013-03-13, `.../newsevents/pressreleases/monetary20130313a.htm`: "Committee policy
    statements for all regularly scheduled meetings will now be released at 2 p.m. Eastern Time."
  - 2006-07-20, `.../newsevents/pressreleases/monetary20060720b.htm`: the October 2006
    statement "will be released around 2:15 p.m. EDT".
  - FOMC transcripts, `.../monetarypolicy/files/FOMC{date}meeting.pdf`: May 2005 ("We issue a
    statement at 2:15 p.m. on the day of our meeting"), Jun 2006 ("released as usual at 2:15"),
    Aug 2006, May 2007 and Mar 2013 ("The statement will now come out at 2:00 for every
    meeting"). These were searched only for clock-time strings next to release keywords
    (`scripts/transcript_times.py`). Only the cited transcripts are kept in `raw/`.

Release-time rules found:

| Period | Time (ET) | Evidence |
|---|---|---|
| to Jan 2013, regular meetings | 14:15 | standing practice (transcripts 2005–2007; 2011-03-24 release). Per-release pages say only "For immediate release". |
| Apr 2011 – Dec 2012, press-conference meetings | 12:20–12:35 | exact time on each press-conference page, e.g. 2012-01-25 at 12:20, 2012-04-25/06-20/09-13 at 12:35, the others 12:30 |
| from 2013-03-20 (first meeting after the 2013-03-13 notice) | 14:00 | 2013-03-13 release. From 2016 every statement page also says "For release at 2:00 p.m." |

So the 2:15 → 2:00 switch is dated by the Fed to the **March 19–20, 2013** meeting. The
January 2013 meeting was still on the old schedule (14:15, unverified).

Verification: 54 scheduled rows are `verified=false`. They are 2004–2010 (except Oct 2006 and
the two meetings whose transcripts state the time), the three 2012 meetings without a press
conference, and Jan 2013. Their date is confirmed; 14:15 is the documented standing practice but
is not stated for that release.

Unscheduled (`scheduled=false`): every intermeeting action that has a "Statement" link on the
Fed calendar (conference calls, "(unscheduled)" meetings and notation votes):
2007-08-10, 2007-08-17, 2008-01-22, 2008-03-11 (no time on the release, so `time_known=false`);
2008-10-08 07:00 (coordinated cut); 2010-05-09 21:15; 2019-10-11 11:00; 2020-03-03 10:00;
2020-03-15 17:00 (Sunday); 2020-03-23 08:00. The notation votes of 2020-03-19 and 2020-03-31 are
listed by the Fed as "Press Release" (swap lines / FIMA repo), not "Statement", and are
**excluded**. So are calls with no statement (e.g. 2013-10-16, 2014-03-04) and the
2025-08-22 notation vote. The cancelled 17–18 March 2020 meeting has no row.
Data quirk: the 2007 calendar links the June 27–28, 2007 statement as `20070618a.htm`. That
file's content is the June 28 statement, which the note records.

## NFP – Employment Situation (268 rows) and CPI (267 rows)

Sources:
- Archive indexes `https://www.bls.gov/bls/news-release/empsit.htm` and `.../cpi.htm`. Future
  releases in HTML comments are stripped.
- Each archived release (`/news.release/archives/*_MMDDYYYY.htm`, or `/news.release/history/*.txt`
  for 2004–2007). Date and time come from the release's own embargo line, e.g. "Transmission of
  material in this release is embargoed until 8:30 a.m. (EDT) Friday, October 2, 2026", and are
  cross-checked against the date in the file name. All agree.
- The release documents contain the published figures. Only the embargo header (a 400-character
  window) is parsed.

Rule found: every parsed release is 08:30 ET. There is no exception in the window.

Rows that are not 08:30-verified: **CPI 2016-06-16 (reference month May 2016)**. bls.gov
returned HTTP 403 for both the HTML and the PDF on repeated attempts. The date comes from the
official file name only, so the row has `time_known=false` and `verified=false`.

Shutdowns and moved releases (all taken from the releases themselves):
- Oct 2013 shutdown: Sep-2013 NFP on **Tue 2013-10-22** (normally the first Friday), Oct-2013
  NFP on 2013-11-08, Sep-2013 CPI on 2013-10-30, Oct-2013 CPI on 2013-11-20.
- Dec 2018 – Jan 2019 partial shutdown: no moved dates show up in the release headers. The
  releases on 2019-01-04/01-11/02-01/02-13 follow the usual pattern.
- Oct–Nov 2025 shutdown: **October 2025 Employment Situation and October 2025 CPI were never
  published**. The BLS index says "Not published because of 2025 lapse in federal government
  appropriations", so they have no rows. Sep-2025 CPI came out Fri 2025-10-24, Sep-2025 NFP on
  Thu 2025-11-20, Nov-2025 NFP on Tue 2025-12-16 and Nov-2025 CPI on Thu 2025-12-18.
- Other non-Friday NFP dates (Thursdays before 4 July and similar): 2008-07-03, 2009-07-02,
  2014-07-03, 2015-07-02, 2020-07-02, 2025-07-03, 2026-07-02. Also Wed 2026-02-11.
- Sep-2026 CPI (due after 2026-10-12) is outside the window.

## ECB (226 rows: 221 scheduled, 5 unscheduled)

Sources:
- Decisions list `https://www.ecb.europa.eu/press/govcdec/mopo/html/index.en.html`, which loads
  `.../press/govcdec/mopo/{YYYY}/html/index_include.en.html` per year. Every item titled
  "Monetary policy decisions" is a row, and the date on each press release page was checked
  against the listing.
- Rule document 2022-06-27, `.../press/pr/date/2022/html/ecb.pr220627~73acedf868.en.html`:
  "Starting from 21 July, monetary policy decisions will be published at 14:15 CET (instead of
  13:45). The press conferences will begin at 14:45 CET (instead of 14:30)." The current
  Governing Council page (`.../press/govcdec/html/index.en.html`) restates 14:15 CET.

| Period | Time (CET/CEST, Europe/Berlin) | Evidence |
|---|---|---|
| to 2022-06-09 | 13:45 | 2022-06-27 release ("instead of 13:45"). No official source located that dates 13:45 for earlier years. Every release page gives only "press conference starting at 2.30 p.m." |
| from **2022-07-21** | 14:15 | 2022-06-27 release |

The change date is confirmed from the source as 21 July 2022. Verification: the 186 rows before
2022-06-09 are `verified=false`. The date is confirmed, and 13:45 is the documented pre-change
practice but not documented per release or per year. 2022-06-09 and everything from 2022-07-21
are `verified=true`.

Unscheduled (`scheduled=false`):
- 2008-10-08: coordinated cut. 13:00 CEST comes from the joint release's "For release at
  7:00 a.m. EDT" on federalreserve.gov (`.../newsevents/press/monetary/20081008a.htm`).
- 2010-05-10 (Securities Markets Programme decision), 2011-08-07 (Sunday statement by the
  President), 2020-03-18 (PEPP, after an unscheduled Governing Council meeting) and 2022-06-15
  ("Statement after the ad hoc meeting"). The release pages give no time and no official time
  was found, so these are `time_known=false`.
- Not included: same-day companion releases (TLTRO, TPI, reserve remuneration) and liquidity-only
  or swap-line releases outside the decisions list.

## Bank of England MPC (230 rows: 227 scheduled, 3 unscheduled)

Sources:
- Decision announcement pages. For 2004-06 to 2015-07 these are
  `https://www.bankofengland.co.uk/news/{YYYY}/{month}/mpc-{month}-{YYYY}`, cross-checked against
  the dated press-release PDF linked from each page. For 2015-08 onwards they are
  `.../monetary-policy-summary-and-minutes/{YYYY}/{slug}`, found through the Bank's news-listing API.
- Cross-check: MPC voting record `.../-/media/boe/files/monetary-policy-summary-and-minutes/mpcvoting.xlsx`
  (dates only were read). Every voting date has an announcement. The six date differences are
  meetings that voted the day before the announcement (Oct 2013, Apr 2014, Oct 2014, May 2015,
  Jun 2015, Jul 2015).
- Rule and timing documents (in `raw/rules/`):
  - Warsh Review, Dec 2014 (`.../news/2014/december/transparency-and-the-boes-mpc-review-by-kevin-warsh.pdf`):
    "The Bank announces the MPC's decision at midday on the Thursday (Day 2)". This describes
    the pre-2015 practice without dating it.
  - 2014-03-31 (`.../news/2014/march/change-to-timing-of-april-2014-mpc-meeting`): the April 2014
    decision "will still be announced at the originally scheduled time of 12.00 hrs (BST)".
  - Dec 2014 response (`.../-/media/boe/files/news/2014/december/transparency-and-the-boes-mpc-response`):
    from **August 2015** the minutes, and the Inflation Report where relevant, are published at
    the same time as the decision.
  - Current pages `.../monetary-policy` and `.../monetary-policy-summary-and-minutes/monetary-policy-summary-and-minutes`:
    "published at 12 noon on a Thursday eight times a year"; "We publish the MPC's decision with
    the minutes of the meetings at 12 noon".
  - 2016-05-09 (`.../news/2016/may/confirmation-of-changes-to-the-mpc-meeting-schedule`): moves
    to 8 meetings a year. The meeting due to end 13 Oct 2016 was the first one dropped.
  - Exceptions: 2020-11-04 notice (`.../news/2020/november/time-change-...`), 5 Nov 2020 at
    **07:00 GMT** "not at 12:00 hrs (GMT) as previously scheduled"; and 2025-05-06 notice
    (`.../news/2025/may/statement-on-the-timing-of-the-mpr-and-mpc-minutes`), 8 May 2025 at
    **12:02 BST** (VE-day silence) "instead of the regular time of 12pm".

| Period | Time (Europe/London) | Evidence |
|---|---|---|
| 2004-06 to 2015-07 | 12:00 decision only. Minutes followed two weeks later (09:30, as stated on e.g. the Apr-2006 page). | Warsh Review (describes the practice); explicit only for Apr 2014 |
| from **2015-08-06** | 12:00 decision + minutes (+ Inflation Report/MPR in quarterly months) | Dec-2014 response, current BoE pages, 2020 and 2025 notices |
| 2020-11-05 | 07:00 GMT | 2020-11-04 notice |
| 2025-05-08 | 12:02 BST | 2025-05-06 notice |

Verification: the 132 rows from Jun 2004 to Jul 2015 (except 2014-04-10) are `verified=false`.
Their date is confirmed by the page and the PDF, but 12:00 is not stated per announcement.
- Date conflict found and resolved: for April 2006 the web page says "Published on 04 April
  2006", but the official press-release PDF is dated **6 April 2006**, which is also the
  voting-record date. The PDF date is used and the row has a note.
- Moved announcements, where the date comes from the page and PDF and the time is unverified:
  Mon 2005-05-09, Mon 2010-05-10 and Mon 2015-05-11, which follow general elections.

Unscheduled (`scheduled=false`):
- 2008-10-08: special meeting "some hours in advance of its normal schedule". 12:00 BST comes
  from the joint release's 7:00 a.m. EDT.
- 2020-03-11 and 2020-03-19: special meetings. The pages give no time, so these are
  `time_known=false`.
- The page `.../2020/13march-2020` is the *minutes* of the 10–11 Mar 2020 special meeting, so it
  has no row.

## Bank of Japan (259 rows: 256 marked scheduled, 3 unscheduled)

Sources:
- "Statements on Monetary Policy" by year, `https://www.boj.or.jp/en/mopo/mpmdeci/state_{YYYY}/index.htm`.
  There is one primary statement per date; "(Reference)" documents, operation notices and joint
  statements are dropped.
- Release time: from 2009 to 2015 the BoJ listing gives "Announced at h:mm" for each statement.
  That accounts for the 103 `time_known=true` rows (including one in 2008). For 2004–2008 and
  2016–2026 no time is given anywhere fetched. The current schedule page
  (`.../en/mopo/mpmsche_minu/index.htm`) says statements are released "immediately after
  relevant MPMs", so there is no fixed time and these 156 rows are `time_known=false`.
- Scheduled status:
  - `scheduled=false` only where the statement itself says "unscheduled": 2009-12-01,
    2010-08-30 and 2020-05-22.
  - A row counts as a regular meeting when the BoJ tables show it as a two-day MPM (minutes
    indexes `.../minu_{YYYY}/index.htm` for 2004–2009, `.../mpmsche_minu/past.htm` and the
    current schedule for 2010–2026), or when it falls on an Outlook Report ("The Bank's View")
    release date (`.../en/mopo/outlook/index.htm`).
  - **11 single-day meetings could not be shown to be either pre-scheduled or unscheduled** from
    official text. They are left `scheduled=true`, `verified=false` and flagged in the note:
    2004-06-25, 2005-07-27, 2008-09-18, 2008-09-29, 2008-10-14, 2008-12-02, 2010-05-10,
    2011-03-14, 2011-08-04, 2011-11-30 (22:00 JST) and 2020-03-16. Several of these are probably
    ad hoc or brought-forward meetings, but no official source fetched here says so.

## Things deliberately not done

- No market reaction, price, yield or return data was used to choose, date or time any event.
- No time was filled in from a pattern. Where only a standing practice is documented, the time
  is given with `verified=false` and the rule is cited. Where nothing is documented,
  `time_known=false`.
