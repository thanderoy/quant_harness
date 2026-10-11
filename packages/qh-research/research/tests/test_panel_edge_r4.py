"""R4 — the E-Ratio horizon counts tradable bars, not calendar bars.

`panel_edge` measures excursions over ``h`` *positions* in the series. An
instrument's closed hours are not in its series, so a positional horizon
cannot count them — but "cannot" is a property of the implementation, and
these tests demonstrate it rather than assert it in prose.

The decisive one is the invariance test: the same prices stamped on a 24-hour
calendar and on an exchange calendar with a nightly close produce identical
excursions. If anything in the measurement read timestamps — a calendar-hours
window, a resample, a time-based rolling — the two would differ.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.pre.panel_edge import _instrument_excursions

DATA = Path(os.environ.get(
    "QH_DATA_DIR", Path(__file__).resolve().parents[1] / "data"))


def _session_index(days: int, open_hour: int = 9, close_hour: int = 22
                   ) -> pd.DatetimeIndex:
    """H1 bars 09:00..22:00 each weekday — an index's nightly close."""
    parts = [pd.date_range(f"2024-03-{4 + d:02d} {open_hour:02d}:00",
                           f"2024-03-{4 + d:02d} {close_hour:02d}:00",
                           freq="h", tz="UTC") for d in range(days)]
    out = parts[0]
    for p in parts[1:]:
        out = out.append(p)
    return out


def _ohlc(index: pd.DatetimeIndex, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, len(index)))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) + rng.uniform(0.1, 1.0, len(index))
    low = np.minimum(open_, close) - rng.uniform(0.1, 1.0, len(index))
    return pd.DataFrame({"open": open_, "high": high, "low": low,
                         "close": close}, index=index)


def test_the_horizon_reaches_across_the_nightly_close_to_the_next_session():
    """A signal two bars before the close, h=3: the window is the last bar of
    the session and the first two of the next one. A calendar count of three
    hours would end inside the closure, where there is nothing to measure."""
    idx = _session_index(2)
    df = _ohlc(idx)
    t = 12                                   # 21:00 on day one
    assert idx[t].hour == 21
    spike = 15                               # 10:00 on day two
    assert idx[spike].hour == 10 and idx[spike].day != idx[t].day
    df.iloc[spike, df.columns.get_loc("high")] = 10_000.0
    atr = np.ones(len(df))

    mfe, _ = _instrument_excursions(df, np.array([t]), 3, atr)
    entry = df["open"].iloc[t + 1]
    assert mfe[0] == pytest.approx(10_000.0 - entry)
    calendar_hours = (idx[t + 3] - idx[t]).total_seconds() / 3600
    assert calendar_hours == 13              # 3 bars of exposure, 13 hours


def test_excursions_are_invariant_to_the_closed_hours_between_bars():
    """Same prices, two calendars, identical result: closed hours are not
    counted as exposure because nothing in the measurement reads time."""
    session = _session_index(10)
    continuous = pd.date_range(session[0], periods=len(session), freq="h")
    df_s = _ohlc(session)
    df_c = df_s.set_axis(continuous)
    atr = np.full(len(df_s), 1.3)
    signals = np.arange(5, len(df_s) - 30, 7)
    for h in (5, 20):
        a = _instrument_excursions(df_s, signals, h, atr)
        b = _instrument_excursions(df_c, signals, h, atr)
        np.testing.assert_array_equal(a[0], b[0])
        np.testing.assert_array_equal(a[1], b[1])


GER40 = DATA / "GER40_H1.csv"


@pytest.mark.skipif(not GER40.exists(),
                    reason="GER40_H1.csv not present; set $QH_DATA_DIR")
def test_on_ger40_a_20_bar_horizon_spans_more_than_20_hours():
    """On the real calendar: every h=20 window holds exactly 20 present bars,
    while the wall-clock time it covers is longer wherever it crosses a close.
    The difference is GER40's closed hours, and none of it is counted."""
    from research import admission
    from research.pre.scripts.run_flood_tide_edge import load_ohlcv
    h1 = load_ohlcv(GER40)
    h1 = h1[h1.index >= admission.require("GER40", "H1", DATA)]
    ts = ((h1.index - h1.index[0]).total_seconds() // 3600).to_numpy()
    h = 20
    span = ts[h:] - ts[:-h]                           # hours covered by h bars
    assert (span >= h).all()
    crossing = span > h
    # Most 20-bar windows on a ~22-bar trading day cross a nightly close.
    assert crossing.mean() > 0.5
    assert np.median(span[crossing]) > h
