"""T2 tests — tradability mask, plus X3 (WINDOW weekend rule) and X25 (class declaration)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from resources.data import IndicatorClass, MaskReason, TradabilityMask, masked_rolling
from resources.data.mask import UndeclaredIndicatorClass

#: Acceptance coverage (docs/REWRITE.md §7). Read by
#: tests/test_x_coverage.py — keep in step with what this file asserts.
pytestmark = [pytest.mark.x("X3"), pytest.mark.x("X25")]



def h1_index_with_weekend(n_before: int = 30, n_after: int = 30) -> pd.DatetimeIndex:
    """H1 bars up to a Friday close, then a 63h gap, then Monday open."""
    fri = pd.date_range("2026-01-02 00:00", periods=n_before, freq="h", tz="UTC")
    mon = pd.date_range(fri[-1] + pd.Timedelta(hours=63), periods=n_after,
                        freq="h", tz="UTC")
    return fri.append(mon)


# --------------------------------------------------------------------------- #
# Mask construction and attribution                                            #
# --------------------------------------------------------------------------- #
def test_naive_index_is_rejected():
    """A naive index silently assumes a timezone, and every session boundary
    here depends on it."""
    with pytest.raises(ValueError, match="timezone-aware"):
        TradabilityMask(pd.date_range("2026-01-01", periods=5, freq="h"))


def test_weekend_gap_flags_the_bar_after_the_gap():
    idx = h1_index_with_weekend(10, 10)
    m = TradabilityMask(idx).flag_weekend_gap()
    tradable = m.tradable
    assert not tradable.iloc[10]         # first bar after the gap
    assert tradable.iloc[9]              # last bar before it was tradable
    assert tradable.iloc[11]             # and the next one is fine
    assert m.attribution()["weekend_gap"] == 1


def test_rollover_window_flags_both_sides_of_the_hour():
    """The window is +/- 15 min around 21:00 UTC, so it is symmetric.

    Uses 15-minute bars because the boundary is 15 minutes wide — testing it
    on 30-minute bars cannot distinguish an inclusive edge from an exclusive
    one.
    """
    idx = pd.date_range("2026-01-05 20:30", periods=8, freq="15min", tz="UTC")
    m = TradabilityMask(idx).flag_rollover(utc_hour=21, minutes=15)
    flagged = {str(t)[11:16] for t, v in m.reason(MaskReason.ROLLOVER_WINDOW).items() if v}
    assert flagged == {"20:45", "21:00", "21:15"}
    assert "20:30" not in flagged      # 30 min out — outside the window
    assert "21:30" not in flagged


def test_reasons_are_additive_not_collapsed():
    """A bar untradable for two reasons keeps both.

    Collapsing to a 'primary' reason would invent a precedence nobody
    specified, and attribution is the point of the breakdown.
    """
    idx = pd.date_range("2026-01-05 20:30", periods=4, freq="30min", tz="UTC")
    spread = pd.Series([0.1, 9.9, 0.1, 0.1], index=idx)
    m = (TradabilityMask(idx)
         .flag_rollover(utc_hour=21, minutes=15)
         .flag_spread(spread, threshold=1.0))
    a = m.attribution()
    assert a["rollover_window"] >= 1
    assert a["spread_above_threshold"] == 1
    # Overlapping counts sum to more than the masked total — by design.
    assert sum(a.values()) >= m.summary()["n_masked"]


def test_summary_reports_counts_and_note():
    idx = h1_index_with_weekend(5, 5)
    s = TradabilityMask(idx).flag_weekend_gap().summary()
    assert s["n_bars"] == 10
    assert s["n_masked"] == 1
    assert s["n_tradable"] == 9
    assert "overlap" in s["attribution_note"]


# --------------------------------------------------------------------------- #
# X25 — class declaration is mandatory                                         #
# --------------------------------------------------------------------------- #
def test_x25_undeclared_indicator_class_raises():
    idx = h1_index_with_weekend(10, 10)
    s = pd.Series(np.arange(len(idx), dtype=float), index=idx)
    m = TradabilityMask(idx).flag_weekend_gap()
    with pytest.raises(UndeclaredIndicatorClass, match="no default"):
        masked_rolling(s, m, 3, np.mean)


# --------------------------------------------------------------------------- #
# X3 — WINDOW indicators NaN across the gap                                    #
# --------------------------------------------------------------------------- #
def test_x3_window_indicator_nans_windows_spanning_the_gap():
    idx = h1_index_with_weekend(20, 20)
    s = pd.Series(np.arange(len(idx), dtype=float), index=idx)
    m = TradabilityMask(idx).flag_weekend_gap()
    out = masked_rolling(s, m, 3, np.mean, IndicatorClass.WINDOW)

    # The masked bar is at position 20; a 3-bar window covers it at 20, 21, 22.
    assert out.iloc[20:23].isna().all()
    # Windows entirely before or after the gap are unaffected.
    assert not np.isnan(out.iloc[19])
    assert not np.isnan(out.iloc[23])
    assert out.iloc[19] == pytest.approx(np.mean([17.0, 18.0, 19.0]))


def test_x3_window_output_matches_plain_rolling_where_unmasked():
    """Masking must not perturb values away from the gap."""
    idx = h1_index_with_weekend(20, 20)
    s = pd.Series(np.arange(len(idx), dtype=float), index=idx)
    m = TradabilityMask(idx).flag_weekend_gap()
    out = masked_rolling(s, m, 3, np.mean, IndicatorClass.WINDOW)
    plain = s.rolling(3).apply(np.mean, raw=False)
    clean = out.notna()
    pd.testing.assert_series_equal(out[clean], plain[clean])


# --------------------------------------------------------------------------- #
# R3 — ACCUMULATOR must NOT NaN across the gap                                 #
# --------------------------------------------------------------------------- #
def test_accumulator_skips_masked_bars_and_keeps_the_calendar():
    """This is the case X3 must not be applied to.

    NaN-ing an accumulator at the gap would destroy its state for every
    subsequent bar — strictly worse than the contamination it prevents.
    """
    idx = h1_index_with_weekend(20, 20)
    s = pd.Series(np.arange(len(idx), dtype=float), index=idx)
    m = TradabilityMask(idx).flag_weekend_gap()
    out = masked_rolling(s, m, 3, np.mean, IndicatorClass.ACCUMULATOR)

    # Calendar preserved.
    pd.testing.assert_index_equal(out.index, idx)
    # The masked bar itself has no value...
    assert np.isnan(out.iloc[20])
    # ...but the bars after the gap DO, unlike the WINDOW case.
    assert not np.isnan(out.iloc[21])
    assert not np.isnan(out.iloc[22])
    # And the value skips the masked bar: 18,19,21 -> not 19,20,21.
    assert out.iloc[21] == pytest.approx(np.mean([18.0, 19.0, 21.0]))


def test_window_and_accumulator_genuinely_differ_at_the_gap():
    """If these ever agree, one of the two branches has stopped working."""
    idx = h1_index_with_weekend(20, 20)
    s = pd.Series(np.arange(len(idx), dtype=float), index=idx)
    m = TradabilityMask(idx).flag_weekend_gap()
    w = masked_rolling(s, m, 3, np.mean, IndicatorClass.WINDOW)
    a = masked_rolling(s, m, 3, np.mean, IndicatorClass.ACCUMULATOR)
    assert w.iloc[21:23].isna().all()
    assert a.iloc[21:23].notna().all()


def test_no_mask_reduces_to_plain_rolling():
    idx = pd.date_range("2026-01-05", periods=30, freq="h", tz="UTC")
    s = pd.Series(np.arange(30, dtype=float), index=idx)
    m = TradabilityMask(idx)          # nothing flagged
    for cls in (IndicatorClass.WINDOW, IndicatorClass.ACCUMULATOR):
        out = masked_rolling(s, m, 4, np.mean, cls)
        pd.testing.assert_series_equal(
            out, s.rolling(4).apply(np.mean, raw=False), check_names=False)
