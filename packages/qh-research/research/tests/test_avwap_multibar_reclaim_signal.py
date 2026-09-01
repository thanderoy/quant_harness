"""Tests for research.pre.signals.avwap_multibar_reclaim_m15.

Focus is on the multi-bar sweep state machine — the rest (HMA filter, stoch
edge-trigger, AVWAP construction) is tested in test_avwap_sweep_reclaim_signal.py
and test_ny_anchor.py and uses the same helpers.
"""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from research.pre.signals.avwap_multibar_reclaim_m15 import (
    emit_signals,
    _scan_multibar_reclaim,
)


def _idx(n: int, start: str = "2024-01-02 00:00") -> pd.DatetimeIndex:
    return pd.date_range(start=start, periods=n, freq="15min", tz="UTC")


# --------------------------------------------------------------------------- #
# State machine — direct unit tests                                            #
# --------------------------------------------------------------------------- #
def test_state_machine_1bar_reclaim():
    # Long-side: close dips below level by > threshold for 1 bar, then reclaims.
    close = np.array([100.0, 95.0, 101.0])
    avwap = np.array([100.0, 100.0, 100.0])
    thr = np.array([1.0, 1.0, 1.0])
    sweep, direction = _scan_multibar_reclaim(close, avwap, thr)
    assert direction[2] == 1
    assert sweep[2] == 1
    assert (sweep[:2] == 0).all()


def test_state_machine_2bar_reclaim_with_intra_retrace():
    # Sweep starts at bar 1 (close=95 < 99). Bar 2 retraces partially (close=98
    # still < 100, so still on wrong side but no longer past threshold). Bar 3
    # reclaims (close=101 > 100). Expected: 2-bar sweep, signal at bar 3.
    close = np.array([100.0, 95.0, 98.0, 101.0])
    avwap = np.array([100.0, 100.0, 100.0, 100.0])
    thr = np.array([1.0, 1.0, 1.0, 1.0])
    sweep, direction = _scan_multibar_reclaim(close, avwap, thr)
    assert direction[3] == 1
    assert sweep[3] == 2


def test_state_machine_3bar_reclaim():
    close = np.array([100.0, 95.0, 97.0, 96.0, 101.0])
    avwap = np.full(5, 100.0)
    thr = np.full(5, 1.0)
    sweep, direction = _scan_multibar_reclaim(close, avwap, thr)
    assert direction[4] == 1
    assert sweep[4] == 3


def test_state_machine_4bar_timeout_no_signal():
    # 4 consecutive sweep bars before any reclaim → timeout, no signal even
    # though bar 5 does reclaim.
    close = np.array([100.0, 95.0, 96.0, 97.0, 98.0, 101.0])
    avwap = np.full(6, 100.0)
    thr = np.full(6, 1.0)
    sweep, direction = _scan_multibar_reclaim(close, avwap, thr)
    assert direction[5] == 0
    assert (sweep == 0).all()


def test_state_machine_threshold_breach_only_at_start():
    # Bar 1 just barely below threshold (close=98.5 vs level-thr=99) — no sweep
    # starts. Bar 1 just past (close=98.99) → starts. Then bar 2 close=99.5 is
    # still on wrong side. Bar 3 reclaims.
    close = np.array([100.0, 98.99, 99.5, 100.5])
    avwap = np.full(4, 100.0)
    thr = np.full(4, 1.0)  # threshold breach line: <99
    sweep, direction = _scan_multibar_reclaim(close, avwap, thr)
    assert direction[3] == 1
    assert sweep[3] == 2


def test_state_machine_no_signal_if_only_threshold_grazed_with_no_breach():
    # Close hovers at level - threshold/2 — never breaches the threshold; the
    # state machine must stay idle.
    close = np.array([100.0, 99.5, 99.5, 99.5, 100.0])
    avwap = np.full(5, 100.0)
    thr = np.full(5, 1.0)
    sweep, direction = _scan_multibar_reclaim(close, avwap, thr)
    assert (direction == 0).all()
    assert (sweep == 0).all()


def test_state_machine_short_side_symmetric():
    # Short sweep: close > level + thr for 2 bars, then reclaim down.
    close = np.array([100.0, 105.0, 103.0, 99.0])
    avwap = np.full(4, 100.0)
    thr = np.full(4, 1.0)
    sweep, direction = _scan_multibar_reclaim(close, avwap, thr)
    assert direction[3] == -1
    assert sweep[3] == 2


def test_state_machine_timeout_locks_until_reclaim():
    # 4 bars wrong-side → timed_out. Even if bars 5-7 stay wrong-side and
    # bar 8 reclaims, no signal: the bar-5+ continuation can never become
    # valid (would need timed_out flag cleared at reclaim, which produces no
    # signal because timed_out was set). Bar 9 starts a NEW sweep though.
    close = np.array([100.0, 95.0, 95.0, 95.0, 95.0, 95.0, 95.0, 101.0, 95.0, 101.0])
    avwap = np.full(10, 100.0)
    thr = np.full(10, 1.0)
    sweep, direction = _scan_multibar_reclaim(close, avwap, thr)
    # Bar 7 reclaim must NOT emit because the sweep that opened at bar 1 timed out.
    assert direction[7] == 0
    # Bar 9 reclaims a fresh 1-bar sweep opened at bar 8.
    assert direction[9] == 1
    assert sweep[9] == 1


# --------------------------------------------------------------------------- #
# Full pipeline                                                                #
# --------------------------------------------------------------------------- #
def test_determinism_and_no_nan_signal():
    n = 2500
    idx = _idx(n)
    rng = np.random.default_rng(11)
    walk = np.cumsum(rng.normal(0, 0.3, n)) + 2000.0
    high = walk + rng.uniform(0.2, 1.0, n)
    low = walk - rng.uniform(0.2, 1.0, n)
    open_ = walk + rng.normal(0, 0.1, n)
    vol = rng.uniform(80, 120, n)
    ohlc = pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": walk, "volume": vol},
        index=idx,
    )
    s1 = emit_signals(ohlc)
    s2 = emit_signals(ohlc)
    pd.testing.assert_frame_equal(s1, s2)
    assert s1["signal"].dtype == bool
    assert not s1["signal"].isna().any()
    # All triggered signals must have sweep_bars in {1,2,3}.
    triggered = s1[s1["signal"]]
    if len(triggered) > 0:
        assert triggered["sweep_bars"].isin([1, 2, 3]).all()


def test_hma_filter_blocks_against_bias():
    """In a sustained downtrend, no long signal can fire even on long reclaims."""
    n = 3000
    idx = _idx(n)
    base = np.linspace(2200, 1800, n)
    close = base + np.sin(np.arange(n) / 5.0) * 1.5
    ohlc = pd.DataFrame(
        {
            "open": close, "high": close + 0.5, "low": close - 0.5,
            "close": close, "volume": np.full(n, 100.0),
        },
        index=idx,
    )
    out = emit_signals(ohlc)
    assert int(((out["signal"]) & (out["direction"] == 1)).sum()) == 0


def test_output_columns_present():
    n = 500
    idx = _idx(n)
    close = np.full(n, 2000.0)
    ohlc = pd.DataFrame(
        {
            "open": close, "high": close + 0.5, "low": close - 0.5,
            "close": close, "volume": np.full(n, 100.0),
        },
        index=idx,
    )
    out = emit_signals(ohlc)
    for c in ["signal", "direction", "sweep_bars", "avwap"]:
        assert c in out.columns
    assert out["direction"].dtype == np.int64
    assert out["sweep_bars"].dtype == np.int64
    assert not out["signal"].any()
