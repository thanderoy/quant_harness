"""Tests for research.pre.signals._ny_anchor."""

from __future__ import annotations

import pandas as pd
import pytest

from research.pre.signals._ny_anchor import daily_ny_anchor_timestamps


def _ts(s: str) -> pd.Timestamp:
    return pd.Timestamp(s, tz="UTC")


def test_dst_spring_forward_2024():
    # 2024-03-10 is the US DST spring-forward.
    # Friday 2024-03-08 anchor: 09:30 EST = 14:30 UTC
    # Monday 2024-03-11 anchor: 09:30 EDT = 13:30 UTC
    idx = pd.DatetimeIndex(
        [
            _ts("2024-03-08 15:00"),  # Friday after anchor
            _ts("2024-03-09 12:00"),  # Saturday -> Friday's anchor
            _ts("2024-03-11 14:00"),  # Monday after anchor
        ]
    )
    out = daily_ny_anchor_timestamps(idx)
    assert out.iloc[0] == _ts("2024-03-08 14:30")
    assert out.iloc[1] == _ts("2024-03-08 14:30")
    assert out.iloc[2] == _ts("2024-03-11 13:30")
    # Shift between Friday's and Monday's anchor is exactly 1 hour.
    assert out.iloc[2] - out.iloc[0] == pd.Timedelta(days=2, hours=23)


def test_dst_fall_back_2024():
    # 2024-11-03 is the US DST fall-back.
    # Friday 2024-11-01 anchor: 09:30 EDT = 13:30 UTC
    # Monday 2024-11-04 anchor: 09:30 EST = 14:30 UTC
    idx = pd.DatetimeIndex(
        [
            _ts("2024-11-01 14:00"),
            _ts("2024-11-04 15:00"),
        ]
    )
    out = daily_ny_anchor_timestamps(idx)
    assert out.iloc[0] == _ts("2024-11-01 13:30")
    assert out.iloc[1] == _ts("2024-11-04 14:30")


def test_weekend_carry_forward():
    # Saturday 2024-04-13 10:00 UTC -> tags Friday 2024-04-12 anchor (13:30 UTC, EDT).
    idx = pd.DatetimeIndex([_ts("2024-04-13 10:00")])
    out = daily_ny_anchor_timestamps(idx)
    assert out.iloc[0] == _ts("2024-04-12 13:30")


def test_pre_monday_open_uses_friday_anchor():
    # Monday 2024-04-15 02:00 UTC: NY clock shows ~22:00 Sunday — Monday's 09:30
    # NY anchor has NOT fired yet (it's 13:30 UTC). Bar should tag with Friday.
    idx = pd.DatetimeIndex([_ts("2024-04-15 02:00")])
    out = daily_ny_anchor_timestamps(idx)
    assert out.iloc[0] == _ts("2024-04-12 13:30")
