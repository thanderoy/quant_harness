"""T3 — panel alignment, and the no-forward-fill rule.

The tests that matter here are the ones that fail if someone "fixes" a NaN by
filling it. A panel whose gaps are filled looks better in every summary and is
wrong in exactly the place the panel exists to be right.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from resources.data.mask import MaskReason, TradabilityMask
from resources.data.panel import Panel, PanelAlignmentError


def _frame(times, close_start=1.0):
    idx = pd.DatetimeIndex(times, tz="UTC")
    n = len(idx)
    close = np.arange(n, dtype=float) + close_start
    return pd.DataFrame(
        {"open": close, "high": close + 0.5, "low": close - 0.5,
         "close": close, "volume": np.arange(n, dtype=float)},
        index=idx)


H = pd.date_range("2026-01-05 00:00", periods=6, freq="h", tz="UTC")


def test_union_index_not_intersection():
    """One instrument's outage must not delete those hours for the others."""
    a = _frame(H)
    b = _frame(H[[0, 1, 4, 5]])
    p = Panel({"A": a, "B": b})

    assert len(p) == 6
    assert list(p.index) == list(H)


def test_absent_bars_are_masked_and_nan_not_filled():
    a = _frame(H)
    b = _frame(H[[0, 1, 4, 5]])
    p = Panel({"A": a, "B": b})

    closes = p.series("B", "close")
    assert closes.isna().loc[H[2]]
    assert closes.isna().loc[H[3]]
    # The value before the gap must not have been carried across it.
    assert closes.loc[H[1]] != closes.loc[H[4]]
    assert not p.mask("B").tradable.loc[H[2]]
    assert p.mask("B").reason(MaskReason.SESSION_CLOSED).loc[H[2]]


def test_absence_is_attributed_to_session_closed():
    p = Panel({"A": _frame(H), "B": _frame(H[[0, 1, 4, 5]])})
    attribution = p.mask("B").attribution()
    assert attribution["session_closed"] == 2


def test_a_supplied_mask_survives_reindexing_onto_the_panel():
    """The caller's mask was built on the instrument's own, shorter index."""
    b_index = H[[0, 1, 4, 5]]
    m = TradabilityMask(b_index)
    m.flag(MaskReason.ROLLOVER_WINDOW,
           pd.Series([False, True, False, False], index=b_index))

    p = Panel({"A": _frame(H), "B": _frame(b_index)}, masks={"B": m})

    mask = p.mask("B")
    assert mask.reason(MaskReason.ROLLOVER_WINDOW).loc[H[1]]
    assert not mask.tradable.loc[H[1]]
    assert mask.attribution() == {"rollover_window": 1, "session_closed": 2}


def test_a_masked_but_present_bar_still_reads_nan():
    """Tradability, not just presence, is what the accessors apply."""
    m = TradabilityMask(H)
    m.flag(MaskReason.SPREAD_ABOVE_THRESHOLD,
           pd.Series([False] * 3 + [True] + [False] * 2, index=H))
    p = Panel({"A": _frame(H)}, masks={"A": m})

    assert p.series("A", "close").isna().loc[H[3]]
    assert p.ohlcv("A").loc[H[3]].isna().all()
    # present() and tradable disagree here, and that is the point.
    assert p.present("A").loc[H[3]]
    assert not p.mask("A").tradable.loc[H[3]]


def test_raw_is_the_only_way_through_the_mask():
    m = TradabilityMask(H)
    m.flag(MaskReason.ROLLOVER_WINDOW,
           pd.Series([False] * 3 + [True] + [False] * 2, index=H))
    p = Panel({"A": _frame(H)}, masks={"A": m})

    assert p.raw("A")["close"].loc[H[3]] == pytest.approx(4.0)
    assert p.series("A", "close").isna().loc[H[3]]


def test_field_gives_symbols_as_columns_and_an_honest_denominator():
    p = Panel({"A": _frame(H), "B": _frame(H[[0, 1, 4, 5]])})
    closes = p.field("close")

    assert list(closes.columns) == ["A", "B"]
    # dropna() leaves the bars on which both were genuinely tradable.
    assert len(closes.dropna()) == 4


def test_a_filled_gap_would_produce_a_zero_return_and_does_not():
    """The specific damage forward-fill does to D4 and to volatility."""
    p = Panel({"A": _frame(H), "B": _frame(H[[0, 1, 4, 5]])})
    r = np.log(p.field("close").astype(float)).diff()

    # No manufactured zero returns inside the gap.
    assert r["B"].loc[H[2]:H[4]].isna().all()
    assert (r["B"].dropna() != 0).all()


def test_naive_index_is_refused():
    naive = _frame(H)
    naive.index = naive.index.tz_localize(None)
    with pytest.raises(PanelAlignmentError, match="timezone-aware"):
        Panel({"A": naive})


def test_duplicate_timestamps_are_refused():
    dup = _frame(H.append(H[[0]])).sort_index()
    with pytest.raises(PanelAlignmentError, match="duplicate"):
        Panel({"A": dup})


def test_missing_ohlc_column_is_refused():
    bad = _frame(H).drop(columns=["low"])
    with pytest.raises(PanelAlignmentError, match="missing columns"):
        Panel({"A": bad})


def test_empty_panel_is_refused():
    with pytest.raises(PanelAlignmentError):
        Panel({})


def test_unknown_symbol_names_what_is_available():
    p = Panel({"A": _frame(H)})
    with pytest.raises(KeyError, match="A"):
        p.series("EURUSD")


def test_summary_separates_absence_from_filtering():
    m = TradabilityMask(H[[0, 1, 4, 5]])
    m.flag(MaskReason.ROLLOVER_WINDOW,
           pd.Series([False, True, False, False], index=H[[0, 1, 4, 5]]))
    p = Panel({"A": _frame(H), "B": _frame(H[[0, 1, 4, 5]])}, masks={"B": m})

    s = p.summary()
    assert s["n_bars"] == 6
    assert s["per_symbol"]["B"]["n_present"] == 4
    assert s["per_symbol"]["B"]["n_masked"] == 3
    assert s["n_bars_tradable_for_all"] == 3
    assert "never forward-filled" in s["alignment"]


def test_non_utc_input_is_converted_not_rejected():
    ny = _frame(H).tz_convert("America/New_York")
    p = Panel({"A": ny})
    assert str(p.index.tz) == "UTC"
