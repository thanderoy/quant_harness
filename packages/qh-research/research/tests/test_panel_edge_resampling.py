"""The majors have no native H4, so the panel's trend filter reads a
resampled series on every instrument it judges.

`panel_edge`'s docstring asserted that resampling reproduces native H4
exactly, cited the numbers, and said "a test runs it". No such test existed,
and `check_panel` never called `validate_resampling` either — the field was
declared on the report and left empty. The claim was true and unguarded,
which is the state that lets it stop being true without anyone noticing.

XAUUSD is the only instrument here with both series, so it is the only place
the assumption is checkable. That makes these tests narrow, not optional: if
resampling drifts, every major's `regime_ok` silently changes and the panel
verdict moves with it.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from research.pre.panel_edge import resample_h4, validate_resampling

DATA = Path(os.environ.get(
    "QH_DATA_DIR",
    Path(__file__).resolve().parents[1] / "data"))

#: Measured 2026-09-22. The remainder are partial bars at the series ends,
#: which is why this is not simply len(native).
EXPECTED_COMMON_BARS = 32_876
EXPECTED_NATIVE_BARS = 32_960

needs_pair = pytest.mark.skipif(
    not ((DATA / "XAUUSD_H1.csv").exists() and (DATA / "XAUUSD_H4.csv").exists()),
    reason=("XAUUSD H1 and native H4 not both present; set $QH_DATA_DIR to the "
            "directory holding them"))


def _load(name: str) -> pd.DataFrame:
    from research.pre.scripts.run_flood_tide_edge import load_ohlcv
    return load_ohlcv(DATA / name)


# -- the claim the docstring made -------------------------------------------

@needs_pair
def test_resampled_h4_matches_native_h4_exactly():
    """100% on all four fields, not 'close enough'.

    A tolerance here would be the wrong instrument: these are aggregations of
    the same ticks, so any mismatch is a bug in the aggregation rather than
    float noise to be absorbed.
    """
    r = validate_resampling(_load("XAUUSD_H1.csv"), _load("XAUUSD_H4.csv"))
    assert r["common_bars"] == EXPECTED_COMMON_BARS
    assert r["native_bars"] == EXPECTED_NATIVE_BARS
    for field, rate in r["exact_match_rate"].items():
        assert rate == 1.0, f"{field} matches on {rate:.6%} of common bars"


@needs_pair
def test_the_overlap_is_nearly_the_whole_native_series():
    """Guards the other direction: 100% agreement on three bars would pass
    the test above and mean nothing."""
    r = validate_resampling(_load("XAUUSD_H1.csv"), _load("XAUUSD_H4.csv"))
    assert r["common_bars"] / r["native_bars"] > 0.99


# -- the aggregation itself, without needing the pair -----------------------

def test_resampling_takes_first_open_last_close_and_the_extremes():
    idx = pd.date_range("2024-01-01", periods=8, freq="1h")
    h1 = pd.DataFrame(
        {"open":  [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
         "high":  [1.5, 9.0, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5],
         "low":   [0.5, 1.8, 2.8, 0.1, 4.8, 5.8, 6.8, 7.8],
         "close": [1.2, 2.2, 3.2, 4.2, 5.2, 6.2, 7.2, 8.2]}, index=idx)
    out = resample_h4(h1)
    assert len(out) == 2
    first = out.iloc[0]
    assert first["open"] == 1.0      # first open of the four
    assert first["close"] == 4.2     # last close of the four
    assert first["high"] == 9.0      # max, not the last bar's high
    assert first["low"] == 0.1       # min, not the first bar's low


def test_an_incomplete_trailing_group_still_aggregates_what_it_has():
    """Resampling must not invent a bar, and must not drop a real partial one
    silently — the ends are exactly where the 84-bar gap above comes from."""
    idx = pd.date_range("2024-01-01", periods=6, freq="1h")
    h1 = pd.DataFrame({"open": [1.0] * 6, "high": [2.0] * 6,
                       "low": [0.5] * 6, "close": [1.5] * 6}, index=idx)
    out = resample_h4(h1)
    assert len(out) == 2


# -- the runtime wiring -----------------------------------------------------

def test_an_empty_overlap_is_reported_rather_than_raising():
    idx_a = pd.date_range("2024-01-01", periods=8, freq="1h")
    idx_b = pd.date_range("2030-01-01", periods=2, freq="4h")
    h1 = pd.DataFrame({"open": [1.0] * 8, "high": [2.0] * 8,
                       "low": [0.5] * 8, "close": [1.5] * 8}, index=idx_a)
    h4 = pd.DataFrame({"open": [1.0] * 2, "high": [2.0] * 2,
                       "low": [0.5] * 2, "close": [1.5] * 2}, index=idx_b)
    r = validate_resampling(h1, h4)
    assert r["common_bars"] == 0
    assert r["exact_match_rate"] == {}


def test_check_panel_records_the_resampling_check_on_the_report():
    """The report has carried a `resampling_check` field since it was written;
    nothing populated it. The panel's verdict should travel with the evidence
    that its H4 inputs are sound."""
    from research.pre import panel_edge
    import inspect
    src = inspect.getsource(panel_edge.check_panel)
    assert "validate_resampling" in src, (
        "check_panel does not run the resampling validation, so "
        "PanelEdgeReport.resampling_check is always empty and the module "
        "docstring's claim is unsupported at runtime.")
