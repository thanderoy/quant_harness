"""DST-aware NY cash-open anchor mapping for M15 bars.

For each M15 bar (UTC), return the UTC timestamp of the most recent
09:30 America/New_York anchor at-or-before that bar. Anchors fire only on
US weekdays (Mon-Fri); over weekends Friday's anchor carries forward.
DST transitions in March and November are handled via ``zoneinfo``.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

__all__ = ["daily_ny_anchor_timestamps"]

_NY = ZoneInfo("America/New_York")
_UTC = ZoneInfo("UTC")


def daily_ny_anchor_timestamps(m15_index: pd.DatetimeIndex) -> pd.Series:
    if m15_index.tz is None:
        raise ValueError("m15_index must be tz-aware (UTC)")
    if len(m15_index) == 0:
        return pd.Series([], index=m15_index, dtype="datetime64[ns, UTC]")

    # Build candidate anchors at 09:30 NY for every US weekday spanning the
    # M15 range (with a one-week pad before the start to cover the case where
    # the earliest M15 bar falls before the first anchor inside the range).
    first_ny_date = m15_index[0].tz_convert(_NY).date() - timedelta(days=7)
    last_ny_date = m15_index[-1].tz_convert(_NY).date()
    n_days = (last_ny_date - first_ny_date).days + 1

    anchors_utc: list[pd.Timestamp] = []
    for k in range(n_days):
        d = first_ny_date + timedelta(days=k)
        if d.weekday() >= 5:  # Sat=5, Sun=6
            continue
        local = datetime.combine(d, time(9, 30), tzinfo=_NY)
        anchors_utc.append(pd.Timestamp(local.astimezone(_UTC)))

    anchors_idx = pd.DatetimeIndex(anchors_utc)
    # "Most recent anchor <= bar" — searchsorted with side='right' then -1.
    positions = anchors_idx.searchsorted(m15_index, side="right") - 1

    valid = positions >= 0
    # Map each valid position to its anchor timestamp; invalid -> NaT.
    safe_pos = np.where(valid, positions, 0)
    picked = anchors_idx[safe_pos]
    out = pd.Series(picked, index=m15_index)
    out[~valid] = pd.NaT
    return out
