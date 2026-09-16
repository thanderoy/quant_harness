"""research.datasets.csv_loader — robust loader for MT5-style OHLCV CSV files.

Handles:
- Auto-sniffed delimiter (tab, comma, semicolon).
- MT5 native date format (YYYY.MM.DD HH:MM) and ISO variants.
- Combined or split date/time columns.
- Tick-volume vs real-volume column variants.
- BOM and trailing whitespace.

Returns a `BarLoadResult` carrying both the DataFrame and a diagnostics
block (timeframe inferred, gaps detected, depth in years). The diagnostics
gate the data before any backtest runs against it.

Caching to Parquet is intentionally a separate concern: this module reads
CSV; the caller is responsible for caching the parsed DataFrame.

Convention
----------
The returned DataFrame has:
- DatetimeIndex named 'time' in UTC (no timezone if input was UTC-naive,
  but sorted, monotonic, and gap-flagged).
- Columns: open, high, low, close, volume (lowercase, in that order).
- Sorted ascending by time.
"""

from __future__ import annotations

import csv
import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Union

import numpy as np
import pandas as pd

LOGGER = logging.getLogger(__name__)


class BarLoadError(Exception):
    """Raised when CSV cannot be parsed into a usable bar DataFrame."""


# Column name aliases we accept (case-insensitive). Maps to canonical names.
_HEADER_ALIASES = {
    "time": "time", "datetime": "time", "date": "time", "timestamp": "time",
    "open": "open", "o": "open",
    "high": "high", "h": "high",
    "low": "low", "l": "low",
    "close": "close", "c": "close",
    "volume": "volume", "vol": "volume",
    "tickvol": "volume", "tick_volume": "volume",
    "real_volume": "volume",   # MT5 occasionally exports both — we keep one
}

# When two timestamp columns exist (split date/time MT5 export), we combine.
_DATE_LIKE = {"date"}
_TIME_LIKE = {"time"}

# Date format candidates, tried in order.
_DATE_FORMATS = [
    "%Y.%m.%d %H:%M",       # MT5 native
    "%Y.%m.%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y.%m.%d",
    "%Y-%m-%d",
]


@dataclass
class BarLoadResult:
    df: pd.DataFrame
    path: str
    rows: int
    timeframe_inferred: str        # e.g. "H1", "M15", "D1"
    median_bar_seconds: float
    start: pd.Timestamp
    end: pd.Timestamp
    span_days: float
    gaps: List[tuple] = field(default_factory=list)   # (gap_start, gap_end, gap_seconds)
    duplicates_dropped: int = 0
    warnings: List[str] = field(default_factory=list)

    @property
    def span_years(self) -> float:
        return self.span_days / 365.25

    def summary_str(self) -> str:
        lines = [
            f"BarLoadResult: {self.path}",
            f"  rows: {self.rows:,}",
            f"  timeframe: {self.timeframe_inferred}",
            f"  span: {self.start.date()}  ->  {self.end.date()}  "
            f"({self.span_years:.1f} years)",
            f"  median bar: {self.median_bar_seconds:.0f}s",
        ]
        if self.duplicates_dropped:
            lines.append(f"  duplicates dropped: {self.duplicates_dropped}")
        if self.gaps:
            lines.append(f"  gaps > 5x median: {len(self.gaps)} (largest: "
                         f"{max(g[2] for g in self.gaps)/3600:.1f}h)")
        if self.warnings:
            lines.append("  warnings:")
            for w in self.warnings:
                lines.append(f"    - {w}")
        return "\n".join(lines)


# ----- Internal helpers ----------------------------------------------------


def _sniff_delimiter(path: Path) -> str:
    """Sniff the delimiter using csv.Sniffer with a fallback."""
    sample_bytes = path.read_bytes()[:8192]
    # Strip BOM if present.
    if sample_bytes.startswith(b"\xef\xbb\xbf"):
        sample_bytes = sample_bytes[3:]
    sample = sample_bytes.decode("utf-8", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters="\t,;")
        return dialect.delimiter
    except csv.Error:
        # Fallback heuristic: count occurrences of each candidate.
        counts = {d: sample.count(d) for d in ["\t", ",", ";"]}
        return max(counts, key=counts.get)


def _normalise_headers(cols: List[str]) -> List[str]:
    """Lowercase, strip whitespace and BOM, map via aliases."""
    out = []
    for c in cols:
        c2 = c.strip().lstrip("\ufeff").lower()
        out.append(_HEADER_ALIASES.get(c2, c2))
    return out


def _parse_timestamps(s: pd.Series) -> pd.Series:
    """Try a battery of formats, return parsed datetimes or raise."""
    last_err = None
    for fmt in _DATE_FORMATS:
        try:
            return pd.to_datetime(s, format=fmt, errors="raise")
        except (ValueError, TypeError) as e:
            last_err = e
            continue
    # Final fallback: let pandas infer (slower, more permissive).
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return pd.to_datetime(s, errors="raise")
    except Exception as e:
        raise BarLoadError(
            f"Could not parse timestamps. Tried {len(_DATE_FORMATS)} explicit "
            f"formats and pandas inference. Last error: {e}; "
            f"earlier explicit error: {last_err}"
        )


def _infer_timeframe(median_seconds: float) -> str:
    """Map a median bar interval to a timeframe label."""
    candidates = [
        ("M1", 60),
        ("M5", 300),
        ("M15", 900),
        ("M30", 1800),
        ("H1", 3600),
        ("H4", 14400),
        ("D1", 86400),
        ("W1", 604800),
    ]
    # Pick the closest candidate (relative tolerance).
    best, best_err = None, float("inf")
    for label, sec in candidates:
        err = abs(median_seconds - sec) / sec
        if err < best_err:
            best, best_err = label, err
    if best_err > 0.10:
        return f"~{int(median_seconds)}s (no standard match)"
    return best


def _detect_gaps(idx: pd.DatetimeIndex, median_seconds: float,
                 gap_factor: float = 5.0) -> List[tuple]:
    """Find consecutive timestamps with gap > gap_factor * median.

    Returns list of (gap_start, gap_end, gap_seconds). Forex weekend gaps
    (Friday close -> Sunday open) are filtered: any gap whose midpoint
    falls on Saturday is dropped.
    """
    if len(idx) < 2:
        return []
    diffs = idx.to_series().diff().dt.total_seconds().to_numpy()[1:]
    threshold = median_seconds * gap_factor
    starts = idx[:-1][diffs > threshold]
    ends = idx[1:][diffs > threshold]
    secs = diffs[diffs > threshold]
    out = []
    for s, e, g in zip(starts, ends, secs):
        midpoint = s + (e - s) / 2
        if midpoint.weekday() == 5:  # Saturday — normal forex weekend
            continue
        out.append((s, e, float(g)))
    return out


# ----- Public API ----------------------------------------------------------


def load_bars(path: Union[str, Path],
              expected_timeframe: Optional[str] = None) -> BarLoadResult:
    """Load an OHLCV CSV file with diagnostics.

    Parameters
    ----------
    path : str or Path
        Path to the CSV file.
    expected_timeframe : str, optional
        If given (e.g. "H1"), warn loudly if the inferred timeframe doesn't
        match. This catches the "I exported D1 but called the file H1" bug.

    Returns
    -------
    BarLoadResult

    Raises
    ------
    BarLoadError
        On any unparseable input. Better to fail loud than silently feed
        bad data to a backtest.
    """
    p = Path(path)
    if not p.exists():
        raise BarLoadError(f"File not found: {p}")
    if p.stat().st_size == 0:
        raise BarLoadError(f"Empty file: {p}")

    delim = _sniff_delimiter(p)
    LOGGER.info(f"Loading {p.name}: sniffed delimiter = {delim!r}")

    try:
        raw = pd.read_csv(p, sep=delim, engine="python",
                          encoding="utf-8-sig", skipinitialspace=True)
    except Exception as e:
        raise BarLoadError(f"pandas.read_csv failed on {p}: {e}")

    if raw.empty:
        raise BarLoadError(f"No data rows in {p}")

    raw.columns = _normalise_headers(list(raw.columns))

    # Combine split date+time columns if present.
    if "date" in raw.columns and "time" in raw.columns and "open" in raw.columns:
        # MT5 export with two timestamp columns. After alias-mapping, both
        # may have collapsed to "time" -- detect by counting.
        pass  # already handled below
    if list(raw.columns).count("time") == 2:
        # Two columns aliased to "time" -- that means original was Date + Time.
        # Recover positional split.
        positions = [i for i, c in enumerate(raw.columns) if c == "time"]
        date_col = raw.iloc[:, positions[0]].astype(str)
        time_col = raw.iloc[:, positions[1]].astype(str)
        raw["time"] = date_col.str.strip() + " " + time_col.str.strip()
        # Drop the older "time" column (the second occurrence we replaced
        # via setting raw["time"] = ... actually keeps the first; the
        # duplicate column persists). Drop duplicates.
        raw = raw.loc[:, ~raw.columns.duplicated(keep="first")]

    required = {"time", "open", "high", "low", "close"}
    missing = required - set(raw.columns)
    if missing:
        raise BarLoadError(
            f"Required columns missing after header normalisation: {missing}. "
            f"Got: {list(raw.columns)}"
        )

    # Parse timestamps.
    raw["time"] = _parse_timestamps(raw["time"])

    # Coerce numerics.
    for col in ("open", "high", "low", "close"):
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    if "volume" in raw.columns:
        raw["volume"] = pd.to_numeric(raw["volume"], errors="coerce")
    else:
        raw["volume"] = 0.0

    # Drop rows with NaN OHLC.
    pre_drop = len(raw)
    raw = raw.dropna(subset=["open", "high", "low", "close"])
    if len(raw) < pre_drop:
        LOGGER.warning(f"Dropped {pre_drop - len(raw)} rows with NaN OHLC")

    # Sort and de-duplicate.
    raw = raw.sort_values("time").reset_index(drop=True)
    pre_dup = len(raw)
    raw = raw.drop_duplicates(subset=["time"], keep="first")
    duplicates_dropped = pre_dup - len(raw)

    # Set as index.
    df = raw.set_index("time")[["open", "high", "low", "close", "volume"]]

    # Diagnostics.
    if len(df) < 2:
        raise BarLoadError(f"Fewer than 2 valid rows in {p}")
    diffs = df.index.to_series().diff().dt.total_seconds().dropna()
    median_seconds = float(diffs.median())
    timeframe_inferred = _infer_timeframe(median_seconds)
    gaps = _detect_gaps(df.index, median_seconds)

    warnings_list: List[str] = []
    if expected_timeframe and not timeframe_inferred.lower().startswith(
            expected_timeframe.lower()):
        warnings_list.append(
            f"Expected {expected_timeframe} but inferred {timeframe_inferred}. "
            "Check that the right file was loaded."
        )
    # Sanity OHLC checks.
    bad_rows = df[(df["high"] < df["low"]) | (df["high"] < df["open"]) |
                  (df["high"] < df["close"]) | (df["low"] > df["open"]) |
                  (df["low"] > df["close"])]
    if len(bad_rows):
        warnings_list.append(
            f"{len(bad_rows)} rows fail OHLC sanity (high < low or "
            "open/close outside high-low range). First: "
            f"{bad_rows.index[0]}"
        )

    return BarLoadResult(
        df=df,
        path=str(p),
        rows=len(df),
        timeframe_inferred=timeframe_inferred,
        median_bar_seconds=median_seconds,
        start=df.index[0],
        end=df.index[-1],
        span_days=(df.index[-1] - df.index[0]).total_seconds() / 86400,
        gaps=gaps,
        duplicates_dropped=duplicates_dropped,
        warnings=warnings_list,
    )
