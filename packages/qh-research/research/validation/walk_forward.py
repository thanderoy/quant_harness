"""research.validation.walk_forward — rolling/expanding train-test split generators.

Two split types:
- Rolling   : fixed-length training window slides forward.
- Expanding : training set grows (anchored at series start), test rolls forward.

Optional `purge` gap between train end and test start defeats leakage from
autocorrelated features (Lopez de Prado, "Advances in Financial ML",
Chapter 7). For a strategy whose features look back N bars, purge >= N bars.

Phase-2 additions
-----------------
- `exclude_ranges`: drop folds whose train OR test window overlaps any of
  the given (start, end) ranges. Reports dropped folds via a returned
  diagnostic if you call `*_splits_with_report`.

  Use cases:
    * Broker-history holes: bar data missing for a real period.
    * Regime exclusions: deliberately skip e.g. COVID-March-2020.
    * Holiday clusters that distort small backtest windows.

- `align_data_files`: trim multiple DataFrames to a common end-date.

Conventions
-----------
- Inputs are pandas DataFrames with a DatetimeIndex.
- Sizes accept either a pandas Timedelta, a Timedelta-compatible string
  ('1Y', '90D', '4W'), OR an integer (interpreted as a row count -- useful
  when the index is irregular, e.g. trading days only).
- exclude_ranges is a list of (start, end) tuples. Each value is anything
  pd.Timestamp can parse. Inclusive on both ends.

Backwards compatibility
-----------------------
The original API (rolling_splits / expanding_splits returning a plain
Iterator[(train, test)]) is preserved: pass nothing for `exclude_ranges`
and behaviour is identical to v0.1.0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, List, Optional, Tuple, Union

import pandas as pd

SizeLike = Union[pd.Timedelta, str, int]
DateLike = Union[pd.Timestamp, str]
ExcludeRange = Tuple[DateLike, DateLike]


# --- Helpers --------------------------------------------------------------


def _parse_td(x: SizeLike) -> Union[pd.Timedelta, int]:
    """Return pd.Timedelta if convertible; else int row-count."""
    if isinstance(x, pd.Timedelta):
        return x
    if isinstance(x, int):
        return x
    try:
        return pd.Timedelta(x)
    except (ValueError, TypeError):
        try:
            return pd.tseries.frequencies.to_offset(x).nanos and pd.Timedelta(
                pd.tseries.frequencies.to_offset(x).nanos
            )
        except Exception as e:
            raise ValueError(
                f"Cannot parse size {x!r} as Timedelta or int row-count: {e}"
            )


def _slice(df: pd.DataFrame, start_idx, end_idx) -> pd.DataFrame:
    """Inclusive slice that works for both DatetimeIndex and integer indices."""
    return df.loc[start_idx:end_idx]


def _normalise_excludes(
    exclude_ranges: Optional[List[ExcludeRange]],
) -> List[Tuple[pd.Timestamp, pd.Timestamp]]:
    """Coerce all start/end values to Timestamps and validate ordering."""
    if not exclude_ranges:
        return []
    out: List[Tuple[pd.Timestamp, pd.Timestamp]] = []
    for i, (s, e) in enumerate(exclude_ranges):
        ts = pd.Timestamp(s)
        te = pd.Timestamp(e)
        if te < ts:
            raise ValueError(
                f"exclude_ranges[{i}] has end < start: ({s!r}, {e!r})"
            )
        out.append((ts, te))
    return out


def _windows_overlap(
    a_start: pd.Timestamp, a_end: pd.Timestamp,
    b_start: pd.Timestamp, b_end: pd.Timestamp,
) -> bool:
    """True if closed intervals [a_start, a_end] and [b_start, b_end] overlap."""
    return not (a_end < b_start or a_start > b_end)


def _fold_overlaps_any(
    train_start: pd.Timestamp, train_end: pd.Timestamp,
    test_start: pd.Timestamp, test_end: pd.Timestamp,
    excludes: List[Tuple[pd.Timestamp, pd.Timestamp]],
) -> Optional[Tuple[str, Tuple[pd.Timestamp, pd.Timestamp]]]:
    """Return ("train"|"test", range) for the first overlapping exclusion,
    or None if none overlap.
    """
    for ex in excludes:
        if _windows_overlap(train_start, train_end, ex[0], ex[1]):
            return ("train", ex)
        if _windows_overlap(test_start, test_end, ex[0], ex[1]):
            return ("test", ex)
    return None


# --- Diagnostics ----------------------------------------------------------


@dataclass
class FoldExclusion:
    """Record of a fold that was dropped from a split iterator."""
    fold_index: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    overlapping_window: str
    overlapping_range: Tuple[pd.Timestamp, pd.Timestamp]


@dataclass
class SplitReport:
    """Summary of how splits + exclusions worked out."""
    folds_yielded: int = 0
    folds_excluded: List[FoldExclusion] = field(default_factory=list)

    @property
    def total_folds(self) -> int:
        return self.folds_yielded + len(self.folds_excluded)

    def summary_str(self) -> str:
        lines = [
            f"SplitReport: {self.folds_yielded} folds used / "
            f"{len(self.folds_excluded)} excluded / "
            f"{self.total_folds} total",
        ]
        for fx in self.folds_excluded:
            lines.append(
                f"  excluded fold #{fx.fold_index}: "
                f"{fx.train_start.date()} -> {fx.test_end.date()} "
                f"(overlaps {fx.overlapping_window} window with "
                f"{fx.overlapping_range[0].date()}..{fx.overlapping_range[1].date()})"
            )
        return "\n".join(lines)


# --- Generators (backwards-compatible plain API) -------------------------


def rolling_splits(
    df: pd.DataFrame,
    train_size: SizeLike,
    test_size: SizeLike,
    step_size: SizeLike = None,
    purge: SizeLike = 0,
    exclude_ranges: Optional[List[ExcludeRange]] = None,
) -> Iterator[Tuple[pd.DataFrame, pd.DataFrame]]:
    """Yield (train, test) DataFrames with a fixed-length training window.

    Examples
    --------
    >>> # 4 years training, 1 year OOS, rolled annually with no purge
    >>> for train, test in rolling_splits(df, '1460D', '365D'):
    ...     ...

    >>> # Skip folds touching a broker-history hole
    >>> for train, test in rolling_splits(
    ...     df, '1460D', '365D',
    ...     exclude_ranges=[('2025-09-12', '2025-10-15')]
    ... ):
    ...     ...
    """
    yield from rolling_splits_with_report(
        df, train_size, test_size, step_size=step_size,
        purge=purge, exclude_ranges=exclude_ranges,
        report=None,
    )


def expanding_splits(
    df: pd.DataFrame,
    initial_train: SizeLike,
    test_size: SizeLike,
    step_size: SizeLike = None,
    purge: SizeLike = 0,
    exclude_ranges: Optional[List[ExcludeRange]] = None,
) -> Iterator[Tuple[pd.DataFrame, pd.DataFrame]]:
    """Anchored walk-forward: training set grows; test window rolls forward."""
    yield from expanding_splits_with_report(
        df, initial_train, test_size, step_size=step_size,
        purge=purge, exclude_ranges=exclude_ranges,
        report=None,
    )


# --- Generators (with diagnostic report) ---------------------------------


def rolling_splits_with_report(
    df: pd.DataFrame,
    train_size: SizeLike,
    test_size: SizeLike,
    step_size: SizeLike = None,
    purge: SizeLike = 0,
    exclude_ranges: Optional[List[ExcludeRange]] = None,
    report: Optional[SplitReport] = None,
) -> Iterator[Tuple[pd.DataFrame, pd.DataFrame]]:
    """Like rolling_splits, but also populates a SplitReport if provided.

    Pass an empty SplitReport instance to capture which folds were dropped.
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("df must have a DatetimeIndex.")
    train_td = _parse_td(train_size)
    test_td = _parse_td(test_size)
    step_td = _parse_td(step_size) if step_size is not None else test_td
    purge_td = _parse_td(purge) if purge != 0 else pd.Timedelta(0)

    if any(isinstance(v, int) for v in (train_td, test_td, step_td, purge_td)):
        raise NotImplementedError(
            "Integer row-count sizes for rolling_splits not yet implemented; "
            "use Timedelta strings (e.g. '1460D', '365D')."
        )

    excludes = _normalise_excludes(exclude_ranges)

    start = df.index.min()
    end = df.index.max()

    cur_train_start = start
    fold_idx = 0
    while True:
        cur_train_end = cur_train_start + train_td
        cur_test_start = cur_train_end + purge_td
        cur_test_end = cur_test_start + test_td
        if cur_test_end > end:
            break

        train = _slice(df, cur_train_start, cur_train_end)
        test = _slice(df, cur_test_start, cur_test_end)

        if len(train) > 0 and len(test) > 0:
            overlap = _fold_overlaps_any(
                cur_train_start, cur_train_end,
                cur_test_start, cur_test_end,
                excludes,
            )
            if overlap is None:
                if report is not None:
                    report.folds_yielded += 1
                yield train, test
            else:
                if report is not None:
                    report.folds_excluded.append(FoldExclusion(
                        fold_index=fold_idx,
                        train_start=cur_train_start,
                        train_end=cur_train_end,
                        test_start=cur_test_start,
                        test_end=cur_test_end,
                        overlapping_window=overlap[0],
                        overlapping_range=overlap[1],
                    ))

        cur_train_start = cur_train_start + step_td
        fold_idx += 1


def expanding_splits_with_report(
    df: pd.DataFrame,
    initial_train: SizeLike,
    test_size: SizeLike,
    step_size: SizeLike = None,
    purge: SizeLike = 0,
    exclude_ranges: Optional[List[ExcludeRange]] = None,
    report: Optional[SplitReport] = None,
) -> Iterator[Tuple[pd.DataFrame, pd.DataFrame]]:
    """Like expanding_splits, but also populates a SplitReport if provided."""
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("df must have a DatetimeIndex.")
    initial_td = _parse_td(initial_train)
    test_td = _parse_td(test_size)
    step_td = _parse_td(step_size) if step_size is not None else test_td
    purge_td = _parse_td(purge) if purge != 0 else pd.Timedelta(0)

    if any(isinstance(v, int) for v in (initial_td, test_td, step_td, purge_td)):
        raise NotImplementedError(
            "Integer row-count sizes for expanding_splits not yet implemented."
        )

    excludes = _normalise_excludes(exclude_ranges)

    start = df.index.min()
    end = df.index.max()

    cur_train_end = start + initial_td
    fold_idx = 0
    while True:
        cur_test_start = cur_train_end + purge_td
        cur_test_end = cur_test_start + test_td
        if cur_test_end > end:
            break

        train = _slice(df, start, cur_train_end)
        test = _slice(df, cur_test_start, cur_test_end)

        if len(train) > 0 and len(test) > 0:
            overlap = _fold_overlaps_any(
                start, cur_train_end,
                cur_test_start, cur_test_end,
                excludes,
            )
            if overlap is None:
                if report is not None:
                    report.folds_yielded += 1
                yield train, test
            else:
                if report is not None:
                    report.folds_excluded.append(FoldExclusion(
                        fold_index=fold_idx,
                        train_start=start,
                        train_end=cur_train_end,
                        test_start=cur_test_start,
                        test_end=cur_test_end,
                        overlapping_window=overlap[0],
                        overlapping_range=overlap[1],
                    ))

        cur_train_end = cur_train_end + step_td
        fold_idx += 1


# --- Multi-file alignment helper -----------------------------------------


def align_data_files(
    dfs: List[pd.DataFrame],
    cutoff: Optional[DateLike] = None,
) -> List[pd.DataFrame]:
    """Truncate multiple DataFrames to a common end date.

    If `cutoff` is None, uses the earliest of all frames' end dates so
    every frame ends at the same timestamp. Otherwise truncates each
    frame to <= cutoff.

    Useful when CSV files were exported on different days and you need
    them aligned for parallel multi-timeframe analysis.
    """
    if not dfs:
        return []
    if cutoff is None:
        cutoff_ts = min(d.index.max() for d in dfs)
    else:
        cutoff_ts = pd.Timestamp(cutoff)
    return [d.loc[:cutoff_ts] for d in dfs]
