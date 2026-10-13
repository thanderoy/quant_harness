# CFTC COT positioning dataset — sources and method

Built 2026-10-13 by `build_cot.py` from files in `raw/` (all downloaded from www.cftc.gov
the same day). Re-run: `~/Local/quant_harness/.venv/bin/python -I build_cot.py <this dir>`.
Output `cot_positions.csv`: 10,607 rows, one per (market, report_date), sorted by market then date.

## Positioning files (futures-only)

From https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalCompressed/index.htm
(saved as `raw/hist_page.html`), base URL `https://www.cftc.gov/files/dea/history/`:

| Report | Files used |
|---|---|
| TFF futures-only | `fin_fut_txt_2006_2016.zip` (F_TFF_2006_2016.txt), `fut_fin_txt_2017.zip` … `fut_fin_txt_2026.zip` (FinFutYY.txt) |
| Disaggregated futures-only | `fut_disagg_txt_hist_2006_2016.zip` (F_Disagg06_16.txt), `fut_disagg_txt_2017.zip` … `fut_disagg_txt_2026.zip` (f_year.txt) |

The 2026 zips (dated 2026-10-08 inside the archive) run through as-of 2026-10-06, the latest
release (Fri 2026-10-09). The current-week files `https://www.cftc.gov/dea/newcot/FinFutWk.txt`
and `.../f_disagg.txt` (`raw/`) were downloaded only to cross-check: their 2026-10-06 open interest
and spot-checked category columns for EUR, NZD, XAU and XAG match the 2026 zip exactly. The build does not read them.

All rows have `FutOnly_or_Combined == FutOnly` (asserted). `As_of_Date_In_Form_YYMMDD` is
cross-checked against `Report_Date_as_YYYY-MM-DD`, whose format differs between files.

**Overlap/dedupe:** the build dedupes on (market, report_date) and keeps the newest file. The
historical bundles end 2016-12-27 and the yearly files start 2017-01-03, so there were
**0 overlapping rows and 0 conflicts**.

## Contracts per market

The contract codes stayed the same across the whole window. Only the CFTC display names changed, in the
2022-02-08 report, when the CFTC shortened names (special announcement 2022-02-11: "The contract market
codes and other data elements are unaffected").

| market | report | code | name in file (period) | units |
|---|---|---|---|---|
| EUR | TFF | 099741 | EURO FX - CHICAGO MERCANTILE EXCHANGE (2006-06-13 → 2026-10-06) | EUR 125,000 |
| GBP | TFF | 096742 | BRITISH POUND STERLING - CHICAGO MERCANTILE EXCHANGE (→ 2022-02-01); BRITISH POUND - CHICAGO MERCANTILE EXCHANGE (2022-02-08 →) | GBP 62,500 |
| JPY | TFF | 097741 | JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE | JPY 12,500,000 |
| CHF | TFF | 092741 | SWISS FRANC - CHICAGO MERCANTILE EXCHANGE | CHF 125,000 |
| CAD | TFF | 090741 | CANADIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE | CAD 100,000 |
| AUD | TFF | 232741 | AUSTRALIAN DOLLAR - CHICAGO MERCANTILE EXCHANGE | AUD 100,000 |
| NZD | TFF | 112741 | NEW ZEALAND DOLLAR - CHICAGO MERCANTILE EXCHANGE (→ 2022-02-01); NZ DOLLAR - CHICAGO MERCANTILE EXCHANGE (2022-02-08 →) | NZD 100,000 |
| ES | TFF | 13874A | E-MINI S&P 500 STOCK INDEX - CHICAGO MERCANTILE EXCHANGE (→ 2022-02-01); E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE (2022-02-08 →) | $50 x S&P 500 |
| XAU | Disagg | 088691 | GOLD - COMMODITY EXCHANGE INC. | 100 troy oz |
| XAG | Disagg | 084691 | SILVER - COMMODITY EXCHANGE INC. | 5,000 troy oz |

Excluded on purpose (they share keywords or are fungible): S&P 500 Consolidated `13874+` (big + e-mini + micro
combined, per special announcements 2010-06-18 and 2023-05-05); big S&P 500 `138741` (ends 2021-09-14); Micro
E-mini S&P `13874U`; S&P total-return and dividend contracts; MICRO GOLD `088695`; MICRO SILVER `084694`; Coinbase
1-oz gold `088LM1` and PAX gold perp `180LM9`; and all cross-rate and ICE "small" FX contracts.

Gaps in the source: NZD has no rows for as-of 2006-06-20, 2006-06-27 or 2006-07-03 (it has 1,058 rows; every
other market has 1,061). Those dates are missing from the CFTC TFF file itself. Every other step between weeks is 6–8 days.
The off-Tuesday as-of dates (Mondays/Wednesdays around holidays, e.g. 2018-12-24, 2025-11-10) appear as published.

## Release dates (`release_datetime_utc`)

All release times are 15:30 America/New_York, converted with `zoneinfo`. The CFTC states this release time on the release-schedule page.
For backfills and catch-up releases, the date is sourced but the 15:30 time is assumed.
Columns:

- `release_verified`: True when an official CFTC page gives the release date for that as-of date.
- `release_source`: where the date came from (see below).
- `release_conservative_utc`: extra column. It equals `release_datetime_utc` when verified. When not verified, it is
  the later of the standard Friday and a holiday rule: if a federal holiday or closure falls Wed–Fri of the release week,
  push the release to the next business day. A Tuesday holiday moves only the as-of date. This rule reproduces all
  52 release dates on the CFTC 2026 schedule and the verified holiday cases in 2015, 2020, 2021 and 2025. Its only
  misses are two 2014 anomalies, and both of those are verified rows anyway. It is later than the standard Friday on 488 rows. **Use it
  for backtests if you want one-business-day safety on holiday weeks.** Its federal-holiday rules and the list of
  ad-hoc closures (e.g. 2018-12-05, 2025-01-09, Christmas Eve executive orders) come from general knowledge, not
  from a CFTC page.

Pages used (saved in `raw/schedule/`):

- Release schedule page: `rs_index.html`, https://www.cftc.gov/MarketReports/CommitmentsofTraders/ReleaseSchedule/index.htm.
  It shows only the 2026 schedule ("tentative"). The CFTC site does not host past years' schedules. Used for 2025-12-30 → 2026-10-06 (410 rows).
- COT Historical Special Announcements: `special_ann.html`, https://www.cftc.gov/MarketReports/CommitmentsofTraders/HistoricalSpecialAnnouncements/index.htm
- Press releases https://www.cftc.gov/PressRoom/PressReleases/6745-13, 7864-19, 9138-25, 9147-25, 5857-10
- Disaggregated Explanatory Notes: `disagg_notes.html`. TFF Explanatory Notes PDF: `tff_notes.pdf`
- Historical Viewable index pages `hv_cot090109/120109/071310/072010/072710.html` and the first disaggregated
  "other" report `disagg_other_sf090109.htm`. These show that the first weekly Disaggregated report (as-of 2009-09-01) included
  gold and silver, and that the first weekly TFF report is as-of 2010-07-20 (none is listed for 2010-07-13).

### Report-series start: backfilled history (most important point-in-time item)

| Report | First weekly report | Earlier history made public | Rows affected |
|---|---|---|---|
| Disaggregated | as-of 2009-09-01, released 2009-09-04 (Disagg. Explanatory Notes) | **2009-10-20** ("On October 20, 2009, CFTC made available more than three years of historical disaggregated data … back to June 13, 2006") | XAU, XAG as-of 2006-06-13 → 2009-08-25 (336 rows) |
| TFF | as-of 2010-07-20, so Fri 2010-07-23 (TFF announced 2010-07-22, PR 5857-10). The exact day is unverified | **2010-12-03** (special announcement: "The CFTC is publishing the historical Traders in Financial Futures-COT data, back to June 2006") | 8 TFF markets as-of 2006-06-13 → 2010-07-13 (1,709 rows) |

The CFTC also says these backfills were "backcast" using later trader classifications. So pre-launch category
splits are not what anyone could have known at the time, even after the backfill date. The open interest is unaffected.

### Delays and shutdowns found

| As-of date(s) | Normal release | Actual / assigned release | Source | Verified |
|---|---|---|---|---|
| 2012-11-27 | 2012-11-30 | 2012-12-05 (reports republished with full classifications; the file holds the revised version) | special ann. 2012-12-04/05 | yes |
| 2013-10-01 | 2013-10-04 | 2013-10-25 | PR 6745-13 (Oct 2013 shutdown) | yes |
| 2013-10-08, 10-15 | 10-11, 10-18 | 2013-11-01 (PR says only "week of Oct 28"; the latest day in that week is used) | PR 6745-13 | no |
| 2013-10-22, 10-29 | 10-25, 11-01 | 2013-11-08 (PR: "at least two more during week of Nov 4") | PR 6745-13 | no |
| 2013-11-05 | 2013-11-08 | 2013-11-08 (PR "expects" to be back on schedule by this date) | PR 6745-13 | no |
| 2014-07-01 | Mon 2014-07-07 (holiday) | **2014-07-04** (inadvertently published early with identical data) | special ann. 2014-07-07 | yes |
| 2014-12-23 | 12-26 | 2014-12-30 | special ann. 2014-12-19 | yes |
| 2015-06-30 | 07-03 | 2015-07-06 (an incomplete premature release on 07-03 is ignored) | special ann. 2015-06-30 / 07-06 | yes |
| 2017-03-28 (ES only) | 03-31 | 2017-04-04 (republished, E-mini S&P on the corrected list) | special ann. 2017-04-04 | yes |
| 2018-12-18 | 12-21 | 2018-12-21 (last report before the Dec 2018–Jan 2019 shutdown) | PR 7864-19 | yes |
| 2018-12-24, 12-31, 2019-01-08, 01-15, 01-22, 01-29, 02-05, 02-12, 02-19, 02-26, 03-05 | weekly | 2019-02-01, 02-05, 02-08, 02-12, 02-15, 02-19, 02-22, 02-26, 03-01, 03-05, 03-08 (Tue/Fri catch-up) | PR 7864-19 (an announced schedule; no later change was found on the announcements page) | yes |
| 2020-12-21 (Mon) | 12-25 | 2020-12-28 | special ann. 2020-12-28 | yes |
| 2021-06-15 | 06-18 | 2021-06-21 | special ann. 2021-06-17 | yes |
| 2023-01-31, 02-07, 02-14, 02-21, 02-28, 03-07, 03-14 | weekly | 2023-02-24, 03-03, 03-08, 03-10, 03-14, 03-16, 03-21 (ION cyber incident) | special anns. 2023-02-02 … 03-21 | yes |
| 2025-01-07 | 01-10 | 2025-01-13 (Carter National Day of Mourning) | special ann. 2025-01-07 | yes |
| 2025-09-30 … 2025-12-23 (13 reports) | 10-03 … 12-29 | 11-19, 11-21, 11-25, 12-02, 12-05, 12-09, 12-10, 12-12, 12-15, 12-17, 12-19, 12-23, 12-29 (Oct–Nov 2025 shutdown) | PR 9147-25 (2025-12-09), parsed from file; supersedes PR 9138-25 | yes* |
| 2025-12-30 … 2026-10-06 | — | per 2026 schedule incl. Mon 01-05, 06-22, 07-06 | release-schedule page | yes* |

\* The PR 9147-25 table was published 2025-12-09. Its dates after that day were the "intended" schedule.
The 2026 page calls itself "tentative". The 2026 page's Jan-05 date agrees with the PR's "returns to normal 12/29".
I found no CFTC notice of any further change.

Not verified: 2023-03-21 (the first report after the ION backlog is assumed Fri 03-24), and the 2018-12-04 week
(the 2018-12-05 day of mourning). The conservative column puts the latter on Mon 2018-12-10.

### Counts

- `release_verified=false`: **7,749 of 10,607** rows. 7,699 of these are standard Friday and 50 are 2013 week-level estimates.
- Verified by source: TFF backfill 1,709; Disagg backfill 336; 2026 schedule 410; 2025 shutdown 130; 2019
  shutdown 120; 2023 ION 70; other special announcements 71; 2013 10; first Disagg report 2.
- Standard Friday rows are exactly as instructed. For 2006–2025 holiday weeks the real release was often
  a business day later (see `release_conservative_utc`). Past annual schedules exist only as
  third-party archive copies, which are not official CFTC sources and were not used.

## DAX / German index

**No.** I found no CFTC COT report for the DAX or any German equity index. Evidence:

- None of the TFF or Disaggregated futures-only files 2006–2026 has a market name containing DAX, GERMAN, DEUTSCH,
  EUREX or STOXX.
- The legacy futures-only files 1986–2026 (`raw/legacy/deacot1986_2016.zip`, `deacot2017.zip` … `deacot2026.zip`,
  1,323 distinct market names) contain only Deutsche Mark currency futures (IMM, NYFE, Philadelphia BOT) and the COMEX
  "STOCK INDEX FUT, EUROTOP 100/300" contracts (pan-European, defunct). Nothing is a DAX or German index contract.
- The COT reports cover US-exchange (DCM) contracts only. DAX futures trade on Eurex, which the CFTC does not report on.

## Data hygiene

Only positioning files and CFTC schedule, announcement, notes and press-release pages were opened. I accessed no price,
return or market-move data. Web searches were restricted to cftc.gov. The search result snippets were about
publication schedules only.
