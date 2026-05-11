"""examples/gap_report.py — locate significant gaps in a bar CSV.

A 32-day gap inside your walk-forward training window silently invalidates
that fold's results. This script reports every gap above a threshold so you
can see when, where, and why.

Usage:
    python -m examples.gap_report data/raw/XAUUSD_H1.csv
    python -m examples.gap_report data/raw/XAUUSD_H1.csv --top 20
    python -m examples.gap_report data/raw/XAUUSD_H1.csv --min-hours 24

What you'll see for each gap:
    - Start and end timestamps (UTC)
    - Gap duration in hours and days
    - Day-of-week of start and end (catches lone weekend gaps that the
      loader's Saturday-midpoint filter missed)
    - Number of expected bars missing
    - Whether it spans known event windows (suggested annotation only)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from qhf.data import load_bars


# Known historical events worth flagging if a gap brushes them.
# These are illustrative -- presence of an event near a gap doesn't mean
# the event caused the gap, just worth noticing.
KNOWN_EVENTS = [
    ("2008-09-15", "2008-12-31", "Lehman / GFC fallout"),
    ("2015-01-15", "2015-01-22", "SNB unpegs CHF"),
    ("2020-03-09", "2020-04-15", "COVID-19 vol spike"),
    ("2020-08-01", "2020-08-31", "XAU all-time high spike"),
    ("2022-02-24", "2022-03-15", "Russia-Ukraine invasion"),
    ("2023-03-08", "2023-03-20", "SVB / banking crisis"),
]


def _annotate_event(start: pd.Timestamp, end: pd.Timestamp) -> str:
    """Return event label if gap overlaps any known window, else ''."""
    s = start.date()
    e = end.date()
    notes = []
    for event_start, event_end, label in KNOWN_EVENTS:
        es = pd.Timestamp(event_start).date()
        ee = pd.Timestamp(event_end).date()
        if not (e < es or s > ee):
            notes.append(label)
    return "; ".join(notes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", help="path to OHLCV CSV file")
    parser.add_argument("--top", type=int, default=10,
                        help="show top N largest gaps (default: 10)")
    parser.add_argument("--min-hours", type=float, default=None,
                        help="only show gaps >= this many hours")
    parser.add_argument("--include-weekends", action="store_true",
                        help="include normal forex weekend gaps")
    args = parser.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 2

    print(f"Loading {path.name} ...")
    result = load_bars(path)
    df = result.df
    print(f"  {result.rows:,} rows, timeframe {result.timeframe_inferred}")
    print(f"  span {result.start.date()} -> {result.end.date()} "
          f"({result.span_years:.1f} years)")
    print()

    # All gaps (don't rely on the loader's Saturday filter; we want full visibility).
    diffs = df.index.to_series().diff().dt.total_seconds()
    median = diffs.median()
    print(f"Median bar interval: {median:.0f}s ({median/3600:.2f}h)")
    print()

    # Build a gap table.
    gap_records = []
    for i in range(1, len(df.index)):
        gap_s = float(diffs.iloc[i])
        if gap_s <= median * 1.5:
            continue                             # adjacent bar, skip
        start = df.index[i - 1]
        end = df.index[i]
        is_weekend = (
            start.weekday() == 4 and end.weekday() in (0, 6)
            and (gap_s / 3600) < 80      # ~Friday close to ~Monday open
        )
        if is_weekend and not args.include_weekends:
            continue
        if args.min_hours is not None and gap_s / 3600 < args.min_hours:
            continue
        gap_records.append({
            "start": start,
            "end": end,
            "hours": gap_s / 3600,
            "days": gap_s / 86400,
            "missing_bars": int(round(gap_s / median)) - 1,
            "start_dow": start.strftime("%a"),
            "end_dow": end.strftime("%a"),
            "is_weekend": is_weekend,
        })

    if not gap_records:
        threshold = (f">={args.min_hours}h" if args.min_hours
                     else "above 1.5x median")
        print(f"No non-weekend gaps {threshold}. Data is contiguous.")
        return 0

    gap_df = pd.DataFrame(gap_records).sort_values("hours", ascending=False)
    n_show = min(args.top, len(gap_df))
    print(f"Found {len(gap_df)} gap(s). Top {n_show} by duration:")
    print()
    print(f"{'#':>2}  {'start':<19}  {'end':<19}  {'days':>6}  "
          f"{'hours':>7}  {'missing':>8}  {'dow':>9}  notes")
    print("-" * 100)
    for i, (_, row) in enumerate(gap_df.head(n_show).iterrows(), 1):
        notes = _annotate_event(row["start"], row["end"])
        if row["is_weekend"]:
            notes = ("(weekend) " + notes).strip()
        # Pre-stringify the timestamps -- f-string `:<19` on a datetime
        # would otherwise parse `<19` as a strftime spec, not a width spec.
        start_s = row["start"].strftime("%Y-%m-%d %H:%M:%S")
        end_s = row["end"].strftime("%Y-%m-%d %H:%M:%S")
        dow_s = f"{row['start_dow']}->{row['end_dow']}"
        print(f"{i:>2}  {start_s:<19}  {end_s:<19}  "
              f"{row['days']:>6.2f}  {row['hours']:>7.1f}  "
              f"{row['missing_bars']:>8,}  {dow_s:>9}  {notes}")

    # Summary stats.
    print()
    print(f"Gap summary (excl. weekends): "
          f"total={len(gap_df)}, "
          f"largest={gap_df['hours'].max():.1f}h, "
          f"median={gap_df['hours'].median():.1f}h, "
          f"missing_bars_total={gap_df['missing_bars'].sum():,}")

    pct_missing = gap_df["missing_bars"].sum() / result.rows * 100
    print(f"Estimated missing rows vs total: "
          f"{gap_df['missing_bars'].sum():,} / {result.rows:,} "
          f"({pct_missing:.2f}% of dataset)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
