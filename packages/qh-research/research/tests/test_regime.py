"""Tests for research.pre.regime.

Emphasis is on the properties the monitor claims: each parameter is bounded or
normalised as documented, and — the load-bearing one — every per-bar value is
invariant to truncating the data after that bar (no look-ahead).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.pre.regime import (
    RegimeParams,
    latest_regime,
    regime_frame,
)


# --------------------------------------------------------------------------- #
# Data helpers                                                                 #
# --------------------------------------------------------------------------- #
def _make_h1(n: int, seed: int, trend: float = 0.0, start: float = 1800.0) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=n, freq="h", tz="UTC")
    rng = np.random.default_rng(seed)
    close = start + np.cumsum(rng.normal(trend, 0.5, n))
    high = close + np.abs(rng.normal(0, 0.3, n))
    low = close - np.abs(rng.normal(0, 0.3, n))
    return pd.DataFrame(
        {"open": close, "high": high, "low": low, "close": close}, index=idx
    )


# --------------------------------------------------------------------------- #
# Shape / bounds                                                               #
# --------------------------------------------------------------------------- #
def test_trend_quality_is_bounded_zero_one():
    rf = regime_frame(_make_h1(1200, seed=1)).dropna()
    assert not rf.empty
    assert rf["trend_quality"].between(0.0, 1.0).all()


def test_vol_regime_is_positive_and_centred_near_one():
    rf = regime_frame(_make_h1(4000, seed=2)).dropna()
    assert (rf["vol_regime"] > 0).all()
    # Random walk has no persistent vol regime, so fast/slow ATR ~ 1.
    assert 0.8 < rf["vol_regime"].median() < 1.2


def test_trend_location_is_signed_and_tracks_drift():
    up = regime_frame(_make_h1(3000, seed=3, trend=0.25)).dropna()
    down = regime_frame(_make_h1(3000, seed=3, trend=-0.25)).dropna()
    assert up["trend_location"].median() > 0
    assert down["trend_location"].median() < 0


def test_warmup_is_nan_not_zero():
    """ER's own warmup fill is 0.0, which would misread as 'churning'."""
    params = RegimeParams()
    rf = regime_frame(_make_h1(600, seed=4))
    assert rf["trend_quality"].iloc[: params.er_len].isna().all()
    longest = max(params.atr_slow, params.sma_len)
    assert rf["trend_location"].iloc[: longest - 1].isna().all()


# --------------------------------------------------------------------------- #
# Look-ahead                                                                   #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("cut", [400, 500, 599])
def test_values_invariant_to_future_bars(cut: int):
    """Truncating after bar `cut` must not change any value at or before `cut`."""
    full = _make_h1(600, seed=5)
    ref = regime_frame(full).iloc[: cut + 1]
    truncated = regime_frame(full.iloc[: cut + 1])

    cols = ["trend_quality", "vol_regime", "trend_location"]
    pd.testing.assert_frame_equal(ref[cols], truncated[cols])


# --------------------------------------------------------------------------- #
# Snapshot                                                                     #
# --------------------------------------------------------------------------- #
def test_latest_regime_defaults_to_closed_bar():
    h1 = _make_h1(800, seed=6)
    snap = latest_regime(h1)
    assert snap.timestamp == h1.index[-2]
    assert snap.close == pytest.approx(h1["close"].iloc[-2])


def test_latest_regime_forming_bar_is_opt_in():
    h1 = _make_h1(800, seed=7)
    assert latest_regime(h1, closed_bar=False).timestamp == h1.index[-1]


def test_latest_regime_raises_on_insufficient_history():
    with pytest.raises(ValueError, match="insufficient history"):
        latest_regime(_make_h1(150, seed=8))


def test_regime_frame_rejects_missing_columns():
    h1 = _make_h1(400, seed=9).drop(columns=["high"])
    with pytest.raises(ValueError, match="missing required columns"):
        regime_frame(h1)


def test_regime_frame_rejects_unsorted_index():
    h1 = _make_h1(400, seed=10).iloc[::-1]
    with pytest.raises(ValueError, match="sorted ascending"):
        regime_frame(h1)
