"""Build a point-in-time CFTC Commitments of Traders dataset from official CFTC files.

Usage (run isolated so nothing is imported from the data directory):
    ~/Local/quant_harness/.venv/bin/python -I build_cot.py [COT_DIR]

COT_DIR defaults to the directory containing this script. Inputs are read from
COT_DIR/raw/ (CFTC Historical Compressed zips + saved CFTC schedule pages in
raw/schedule/); output is COT_DIR/cot_positions.csv. See sources.md.

Only positioning files and CFTC release-schedule / announcement pages are read.
"""

from __future__ import annotations

import datetime as dt
import glob
import html
import logging
import os
import re
import sys
import zipfile
from zoneinfo import ZoneInfo

import pandas as pd

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
UTC = ZoneInfo("UTC")
RELEASE_TIME_ET = dt.time(15, 30)

# One standard contract per market. Codes are stable across the whole window; only the
# Market_and_Exchange_Names text changed (2022-02-08 rename for GBP, NZD, ES).
MARKETS: dict[str, tuple[str, str]] = {
    # market: (report, CFTC_Contract_Market_Code)
    "EUR": ("TFF", "099741"),
    "GBP": ("TFF", "096742"),
    "JPY": ("TFF", "097741"),
    "CHF": ("TFF", "092741"),
    "CAD": ("TFF", "090741"),
    "AUD": ("TFF", "232741"),
    "NZD": ("TFF", "112741"),
    "ES": ("TFF", "13874A"),
    "XAU": ("DISAGG", "088691"),
    "XAG": ("DISAGG", "084691"),
}

TFF_FILE_PATTERNS = ["fin_fut_txt_2006_2016.zip", "fut_fin_txt_20[0-9][0-9].zip"]
DISAGG_FILE_PATTERNS = ["fut_disagg_txt_hist_2006_2016.zip", "fut_disagg_txt_20[0-9][0-9].zip"]

TFF_COLS = {
    "Open_Interest_All": "open_interest",
    "Dealer_Positions_Long_All": "dealer_long",
    "Dealer_Positions_Short_All": "dealer_short",
    "Dealer_Positions_Spread_All": "dealer_spread",
    "Asset_Mgr_Positions_Long_All": "asset_mgr_long",
    "Asset_Mgr_Positions_Short_All": "asset_mgr_short",
    "Asset_Mgr_Positions_Spread_All": "asset_mgr_spread",
    "Lev_Money_Positions_Long_All": "lev_money_long",
    "Lev_Money_Positions_Short_All": "lev_money_short",
    "Lev_Money_Positions_Spread_All": "lev_money_spread",
    "Other_Rept_Positions_Long_All": "other_rept_long",
    "Other_Rept_Positions_Short_All": "other_rept_short",
    "Other_Rept_Positions_Spread_All": "other_rept_spread",
    "NonRept_Positions_Long_All": "nonrept_long",
    "NonRept_Positions_Short_All": "nonrept_short",
}
DISAGG_COLS = {
    "Open_Interest_All": "open_interest",
    "Prod_Merc_Positions_Long_All": "prod_merc_long",
    "Prod_Merc_Positions_Short_All": "prod_merc_short",
    "Swap_Positions_Long_All": "swap_long",
    "Swap__Positions_Short_All": "swap_short",
    "Swap__Positions_Spread_All": "swap_spread",
    "M_Money_Positions_Long_All": "m_money_long",
    "M_Money_Positions_Short_All": "m_money_short",
    "M_Money_Positions_Spread_All": "m_money_spread",
    "Other_Rept_Positions_Long_All": "other_rept_long",
    "Other_Rept_Positions_Short_All": "other_rept_short",
    "Other_Rept_Positions_Spread_All": "other_rept_spread",
    "NonRept_Positions_Long_All": "nonrept_long",
    "NonRept_Positions_Short_All": "nonrept_short",
}
POSITION_COLS = list(dict.fromkeys(list(TFF_COLS.values()) + list(DISAGG_COLS.values())))

# Report series first went public as weekly reports on these as-of dates; every earlier
# as-of date was published later as a one-off historical backfill.
DISAGG_FIRST_WEEKLY_ASOF = dt.date(2009, 9, 1)   # first Disaggregated report, released 2009-09-04
DISAGG_BACKFILL_RELEASE = dt.date(2009, 10, 20)  # history back to 2006-06-13 made public
TFF_FIRST_WEEKLY_ASOF = dt.date(2010, 7, 20)     # first TFF report (announced 2010-07-22)
TFF_BACKFILL_RELEASE = dt.date(2010, 12, 3)      # history back to June 2006 made public

# (as-of date) -> (release date, verified, source). All from cftc.gov pages saved in raw/schedule/.
D = dt.date
KNOWN_RELEASES: dict[dt.date, tuple[dt.date, bool, str]] = {
    # 2012: reports for 11/27/2012 republished with full trader classification (special ann. 2012-12-04/05).
    # First weekly Disaggregated report (gold and silver included): Disaggregated Explanatory Notes.
    # TFF rows for this date fall in the TFF backfill branch first.
    D(2009, 9, 1): (D(2009, 9, 4), True, "disagg_notes_first_report"),
    D(2012, 11, 27): (D(2012, 12, 5), True, "special_ann_2012-12-05_revised"),
    # 2013 shutdown (PR 6745-13). Only the first catch-up date is exact; the rest are week-level.
    D(2013, 10, 1): (D(2013, 10, 25), True, "pr_6745-13"),
    D(2013, 10, 8): (D(2013, 11, 1), False, "pr_6745-13_week_of_2013-10-28_latest_day"),
    D(2013, 10, 15): (D(2013, 11, 1), False, "pr_6745-13_week_of_2013-10-28_latest_day"),
    D(2013, 10, 22): (D(2013, 11, 8), False, "pr_6745-13_week_of_2013-11-04_latest_day"),
    D(2013, 10, 29): (D(2013, 11, 8), False, "pr_6745-13_week_of_2013-11-04_latest_day"),
    D(2013, 11, 5): (D(2013, 11, 8), False, "pr_6745-13_expected_resume"),
    # 2014: scheduled Mon 7/7 but inadvertently published Fri 7/4 15:30 with identical data.
    D(2014, 7, 1): (D(2014, 7, 4), True, "special_ann_2014-07-07"),
    D(2014, 12, 23): (D(2014, 12, 30), True, "special_ann_2014-12-19"),
    # 2015: complete report Mon 7/6 (an incomplete premature release on 7/3 is ignored).
    D(2015, 6, 30): (D(2015, 7, 6), True, "special_ann_2015-06-30_and_07-06"),
    # 2018-19 shutdown: last report 12/21/2018; catch-up schedule in PR 7864-19 (Tue/Fri).
    D(2018, 12, 18): (D(2018, 12, 21), True, "pr_7864-19_last_before_shutdown"),
    D(2018, 12, 24): (D(2019, 2, 1), True, "pr_7864-19_schedule"),
    D(2018, 12, 31): (D(2019, 2, 5), True, "pr_7864-19_schedule"),
    D(2019, 1, 8): (D(2019, 2, 8), True, "pr_7864-19_schedule"),
    D(2019, 1, 15): (D(2019, 2, 12), True, "pr_7864-19_schedule"),
    D(2019, 1, 22): (D(2019, 2, 15), True, "pr_7864-19_schedule"),
    D(2019, 1, 29): (D(2019, 2, 19), True, "pr_7864-19_schedule"),
    D(2019, 2, 5): (D(2019, 2, 22), True, "pr_7864-19_schedule"),
    D(2019, 2, 12): (D(2019, 2, 26), True, "pr_7864-19_schedule"),
    D(2019, 2, 19): (D(2019, 3, 1), True, "pr_7864-19_schedule"),
    D(2019, 2, 26): (D(2019, 3, 5), True, "pr_7864-19_schedule"),
    D(2019, 3, 5): (D(2019, 3, 8), True, "pr_7864-19_schedule_current"),
    D(2020, 12, 21): (D(2020, 12, 28), True, "special_ann_2020-12-28"),
    D(2021, 6, 15): (D(2021, 6, 21), True, "special_ann_2021-06-17"),
    # 2023 ION cyber incident (special announcements 2023-02-02 .. 2023-03-21).
    D(2023, 1, 31): (D(2023, 2, 24), True, "special_ann_2023-02-24_ion"),
    D(2023, 2, 7): (D(2023, 3, 3), True, "special_ann_2023-03-03_ion"),
    D(2023, 2, 14): (D(2023, 3, 8), True, "special_ann_2023-03-08_ion"),
    D(2023, 2, 21): (D(2023, 3, 10), True, "special_ann_2023-03-10_ion"),
    D(2023, 2, 28): (D(2023, 3, 14), True, "special_ann_2023-03-14_ion"),
    D(2023, 3, 7): (D(2023, 3, 16), True, "special_ann_2023-03-16_ion"),
    D(2023, 3, 14): (D(2023, 3, 21), True, "special_ann_2023-03-21_ion"),
    D(2025, 1, 7): (D(2025, 1, 13), True, "special_ann_2025-01-07"),
}
# Market-specific revisions: (market, as-of) -> (release, verified, source).
MARKET_RELEASES: dict[tuple[str, dt.date], tuple[dt.date, bool, str]] = {
    # Reports for 3/28/2017 republished 4/4/2017 for listed markets incl. CME E-mini S&P (13874A).
    ("ES", D(2017, 3, 28)): (D(2017, 4, 4), True, "special_ann_2017-04-04_revised"),
}

# US federal holidays/closures not produced by the fixed rules below (used only for the
# conservative inferred column). Executive-order closures and national days of mourning.
EXTRA_CLOSURES = {
    D(2007, 1, 2), D(2012, 10, 29), D(2012, 10, 30), D(2012, 12, 24), D(2014, 12, 26),
    D(2015, 12, 24), D(2018, 12, 5), D(2018, 12, 24), D(2019, 12, 24), D(2020, 12, 24),
    D(2024, 12, 24), D(2025, 1, 9), D(2025, 12, 24), D(2025, 12, 26),
}


def nth_weekday(year: int, month: int, weekday: int, n: int) -> dt.date:
    """n-th (1-based) weekday of a month; n=-1 means last."""
    if n > 0:
        first = dt.date(year, month, 1)
        return first + dt.timedelta(days=(weekday - first.weekday()) % 7 + 7 * (n - 1))
    nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
    last = nxt - dt.timedelta(days=1)
    return last - dt.timedelta(days=(last.weekday() - weekday) % 7)


def observed(day: dt.date) -> dt.date:
    if day.weekday() == 5:
        return day - dt.timedelta(days=1)
    if day.weekday() == 6:
        return day + dt.timedelta(days=1)
    return day


def federal_holidays(year: int) -> set[dt.date]:
    days = {
        observed(dt.date(year, 1, 1)),
        nth_weekday(year, 1, 0, 3),
        nth_weekday(year, 2, 0, 3),
        nth_weekday(year, 5, 0, -1),
        observed(dt.date(year, 7, 4)),
        nth_weekday(year, 9, 0, 1),
        nth_weekday(year, 10, 0, 2),
        observed(dt.date(year, 11, 11)),
        nth_weekday(year, 11, 3, 4),
        observed(dt.date(year, 12, 25)),
    }
    if year >= 2021:
        days.add(observed(dt.date(year, 6, 19)))
    days.add(observed(dt.date(year + 1, 1, 1)))  # Jan 1 on Saturday is observed Dec 31
    return days


def is_closed(day: dt.date) -> bool:
    return day.weekday() >= 5 or day in federal_holidays(day.year) or day in EXTRA_CLOSURES


def standard_friday(asof: dt.date) -> dt.date:
    return asof + dt.timedelta(days=(4 - asof.weekday()) % 7)


def holiday_rule_release(asof: dt.date) -> dt.date:
    """Inferred release: Friday of the as-of week, pushed to the next business day if a
    federal holiday/closure falls on the Wednesday-Friday before it (the pattern on the
    CFTC 2026 schedule). A Tuesday holiday only moves the as-of date, not the release."""
    fri = standard_friday(asof)
    wed = fri - dt.timedelta(days=2)
    if any(is_closed(wed + dt.timedelta(days=k)) for k in range(3)):
        day = fri + dt.timedelta(days=1)
        while is_closed(day):
            day += dt.timedelta(days=1)
        return day
    return fri


def to_utc_iso(day: dt.date) -> str:
    local = dt.datetime.combine(day, RELEASE_TIME_ET, tzinfo=ET)
    return local.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def html_text(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        raw = fh.read()
    raw = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S)
    raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", html.unescape(raw))


def parse_2025_shutdown_table(path: str) -> dict[dt.date, dt.date]:
    """PR 9147-25 (2025-12-09): 'COT Report Date / Original / New Publish Date' rows."""
    text = html_text(path)
    out: dict[dt.date, dt.date] = {}
    for a, _b, c in re.findall(r"(\d\d/\d\d/\d{4}) (\d\d/\d\d/\d{4}) (\d\d/\d\d/\d{4})", text):
        out[dt.datetime.strptime(a, "%m/%d/%Y").date()] = dt.datetime.strptime(c, "%m/%d/%Y").date()
    if len(out) != 13:
        raise ValueError(f"expected 13 rows in 2025 shutdown table, got {len(out)}")
    return out


def parse_2026_schedule(path: str) -> list[dt.date]:
    """Release-schedule page: '2026 Release Schedule Month Dates January 05* 09 ...'."""
    text = html_text(path)
    seg = text[text.index("2026 Release Schedule"): text.index("Delayed release date")]
    months = ["January", "February", "March", "April", "May", "June", "July", "August",
              "September", "October", "November", "December"]
    dates: list[dt.date] = []
    for i, name in enumerate(months):
        start = seg.index(name) + len(name)
        end = seg.index(months[i + 1]) if i < 11 else len(seg)
        for day in re.findall(r"(\d\d)\*?", seg[start:end]):
            dates.append(dt.date(2026, i + 1, int(day)))
    return dates


def load_report(raw: str, patterns: list[str], report: str) -> pd.DataFrame:
    paths = sorted({p for pat in patterns for p in glob.glob(os.path.join(raw, pat))})
    if not paths:
        raise FileNotFoundError(f"no {report} files in {raw}")
    wanted = {code for rep, code in MARKETS.values() if rep == report}
    frames = []
    for order, path in enumerate(paths):
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if len(names) != 1:
                raise ValueError(f"{path}: expected one member, got {names}")
            df = pd.read_csv(zf.open(names[0]), dtype=str, low_memory=False)
        df["CFTC_Contract_Market_Code"] = df["CFTC_Contract_Market_Code"].str.strip()
        df = df[df["CFTC_Contract_Market_Code"].isin(wanted)].copy()
        bad = df["FutOnly_or_Combined"].str.strip().ne("FutOnly")
        if bad.any():
            raise ValueError(f"{path}: non futures-only rows present")
        df["source_file"] = os.path.basename(path)
        # Historical multi-year bundles are older snapshots than the per-year files.
        df["_priority"] = 0 if "2006_2016" in path else 1 + order
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def tidy(df: pd.DataFrame, report: str, colmap: dict[str, str]) -> pd.DataFrame:
    code_to_market = {code: m for m, (rep, code) in MARKETS.items() if rep == report}
    out = pd.DataFrame({
        "market": df["CFTC_Contract_Market_Code"].map(code_to_market),
        "report": report,
        "cftc_contract_market_code": df["CFTC_Contract_Market_Code"],
        "market_and_exchange_names": df["Market_and_Exchange_Names"].str.strip(),
        "contract_units": df["Contract_Units"].str.strip(),
        "report_date": pd.to_datetime(df["As_of_Date_In_Form_YYMMDD"].str.strip(), format="%y%m%d").dt.date,
        "source_file": df["source_file"],
        "_priority": df["_priority"],
    })
    for src, dst in colmap.items():
        out[dst] = pd.to_numeric(df[src].str.strip(), errors="raise").astype("Int64")
    # Cross-check the second date column (format differs between files).
    alt = pd.to_datetime(df["Report_Date_as_YYYY-MM-DD"].str.strip(), format="mixed").dt.date
    if (alt != out["report_date"]).any():
        raise ValueError(f"{report}: date columns disagree")
    return out


def dedupe(df: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    key = ["market", "report_date"]
    value_cols = [c for c in POSITION_COLS if c in df.columns]
    dups = df[df.duplicated(key, keep=False)]
    conflicts = 0
    for _, grp in dups.groupby(key):
        if len(grp[value_cols].drop_duplicates()) > 1:
            conflicts += 1
            logger.warning("conflicting duplicate %s; keeping newest file:\n%s",
                           grp.iloc[0][key].tolist(), grp[["source_file"] + value_cols].to_string())
    df = df.sort_values("_priority").drop_duplicates(key, keep="last")
    return df, len(dups), conflicts


def assign_release(df: pd.DataFrame, schedule_dir: str) -> pd.DataFrame:
    shutdown_2025 = parse_2025_shutdown_table(os.path.join(schedule_dir, "pr_9147-25.html"))
    sched_2026 = parse_2026_schedule(os.path.join(schedule_dir, "rs_index.html"))
    asofs_2026 = sorted({d for d in df["report_date"] if d >= dt.date(2025, 12, 26)})
    map_2026: dict[dt.date, dt.date] = {}
    for rel in sched_2026:
        prior = [d for d in asofs_2026 if d < rel and (rel - d).days <= 7]
        if prior:
            map_2026[max(prior)] = rel

    rel_dates, verified, sources, conservative = [], [], [], []
    for market, report, asof in zip(df["market"], df["report"], df["report_date"]):
        first_weekly = TFF_FIRST_WEEKLY_ASOF if report == "TFF" else DISAGG_FIRST_WEEKLY_ASOF
        if asof < first_weekly:
            rel = TFF_BACKFILL_RELEASE if report == "TFF" else DISAGG_BACKFILL_RELEASE
            item = (rel, True, f"{report.lower()}_history_backfill")
        elif (market, asof) in MARKET_RELEASES:
            item = MARKET_RELEASES[(market, asof)]
        elif asof in KNOWN_RELEASES:
            item = KNOWN_RELEASES[asof]
        elif asof in shutdown_2025:
            item = (shutdown_2025[asof], True, "pr_9147-25_shutdown_2025")
        elif asof in map_2026:
            item = (map_2026[asof], True, "cftc_release_schedule_2026")
        else:
            item = (standard_friday(asof), False, "standard_friday_unverified")
        rel, ok, src = item
        if rel < asof:
            raise ValueError(f"release before as-of for {market} {asof}")
        cons = rel if ok else max(rel, holiday_rule_release(asof))
        rel_dates.append(to_utc_iso(rel))
        verified.append(ok)
        sources.append(src)
        conservative.append(to_utc_iso(cons))
    df = df.copy()
    df["release_datetime_utc"] = rel_dates
    df["release_verified"] = verified
    df["release_source"] = sources
    df["release_conservative_utc"] = conservative
    return df


def main(cot_dir: str) -> None:
    raw = os.path.join(cot_dir, "raw")
    tff = tidy(load_report(raw, TFF_FILE_PATTERNS, "TFF"), "TFF", TFF_COLS)
    dis = tidy(load_report(raw, DISAGG_FILE_PATTERNS, "DISAGG"), "DISAGG", DISAGG_COLS)
    df = pd.concat([tff, dis], ignore_index=True)
    df, n_dup_rows, n_conflicts = dedupe(df)
    logger.info("overlap rows=%d conflicting keys=%d", n_dup_rows, n_conflicts)
    df = assign_release(df, os.path.join(raw, "schedule"))

    for market, grp in df.sort_values("report_date").groupby("market"):
        gaps = grp["report_date"].diff().dropna()
        odd = grp.loc[gaps.index[(gaps != dt.timedelta(days=7))], "report_date"]
        for d in odd:
            prev = grp["report_date"][grp["report_date"] < d].max()
            logger.info("%s non-7-day step %s -> %s", market, prev, d)

    cols = ["market", "report", "cftc_contract_market_code", "market_and_exchange_names",
            "contract_units", "report_date", "release_datetime_utc", "release_verified",
            "release_source", "release_conservative_utc"] + POSITION_COLS + ["source_file"]
    df = df.sort_values(["market", "report_date"])[cols]
    out = os.path.join(cot_dir, "cot_positions.csv")
    df.to_csv(out, index=False)
    logger.info("wrote %s rows=%d", out, len(df))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s", stream=sys.stdout)
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__)))
