"""A file named _H1 must be H1 from wherever a run starts reading it."""

from __future__ import annotations

import json

import pandas as pd

from research import data_manifest as dm


def _index(*parts: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return parts[0].append(list(parts[1:])) if len(parts) > 1 else parts[0]


def test_a_daily_prefix_in_an_hourly_file_is_found():
    daily = pd.date_range("2015-01-05", periods=10, freq="D", tz="UTC")
    hourly = pd.date_range("2015-01-20", periods=24 * 5, freq="h", tz="UTC")
    idx = _index(daily, hourly)
    assert dm.dense_start(idx, 1.0) == hourly[0]


def test_a_partial_first_day_is_not_a_prefix():
    """Data that starts mid-afternoon is still H1 data."""
    idx = pd.date_range("2015-01-05 20:00", periods=24 * 5, freq="h", tz="UTC")
    assert dm.dense_start(idx, 1.0) == idx[0]


def test_short_days_inside_the_series_are_left_alone():
    """Holidays and early closes are what the mask is for, not this check."""
    a = pd.date_range("2015-01-05", periods=24 * 5, freq="h", tz="UTC")
    holiday = pd.date_range("2015-01-12", periods=3, freq="h", tz="UTC")
    b = pd.date_range("2015-01-13", periods=24 * 5, freq="h", tz="UTC")
    idx = _index(a, holiday, b)
    assert dm.dense_start(idx, 1.0) == idx[0]


def test_daily_files_are_never_trimmed():
    idx = pd.date_range("2015-01-05", periods=30, freq="D", tz="UTC")
    assert dm.dense_start(idx, 24.0) == idx[0]


def test_timeframe_comes_from_the_filename():
    assert dm.timeframe_hours("US500_H1.csv") == 1.0
    assert dm.timeframe_hours("XAUUSD_M15.csv") == 0.25
    assert dm.timeframe_hours("DFII10.csv") is None


def test_the_manifest_records_us500s_daily_prefix():
    """897 daily bars, 2012-08-06 to 2016-01-22, under an _H1 name."""
    entry = json.loads(dm.MANIFEST.read_text())["files"]["US500_H1.csv"]
    assert entry["sparse_prefix_bars"] == 897
    assert entry["dense_from_utc"].startswith("2016-01-25")
