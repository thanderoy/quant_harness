"""Tests for research.pre.signals.avwap_sweep_reclaim_m15.emit_signals."""

from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from research.pre.signals.avwap_sweep_reclaim_m15 import emit_signals


def _m15_idx(n: int, start: str = "2024-01-02 00:00") -> pd.DatetimeIndex:
    return pd.date_range(start=start, periods=n, freq="15min", tz="UTC")


def _ohlc(close: np.ndarray, idx: pd.DatetimeIndex, vol: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(len(idx), vol),
        },
        index=idx,
    )


def _sig_hash(df: pd.DataFrame) -> str:
    return hashlib.sha256(df.to_csv().encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# 13. Determinism                                                              #
# --------------------------------------------------------------------------- #
def test_determinism():
    n = 2500
    idx = _m15_idx(n)
    rng = np.random.default_rng(7)
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
    assert _sig_hash(s1) == _sig_hash(s2)
    pd.testing.assert_frame_equal(s1, s2)


# --------------------------------------------------------------------------- #
# 14. No NaN in signal column                                                  #
# --------------------------------------------------------------------------- #
def test_no_nan_in_signal_column():
    n = 600
    idx = _m15_idx(n)
    close = np.full(n, 2000.0)
    ohlc = _ohlc(close, idx)
    out = emit_signals(ohlc)
    assert out["signal"].dtype == bool
    assert not out["signal"].isna().any()


# --------------------------------------------------------------------------- #
# 9. HMA filter excludes against-bias signals                                  #
# --------------------------------------------------------------------------- #
def test_hma_filter_blocks_against_bias_longs():
    """Strong downtrend: price stays well below H1 HMA(50). No long signal
    can fire regardless of sweep/stoch conditions."""
    n = 3000
    idx = _m15_idx(n)
    # Linearly drop from 2200 to 1800 over the series — sustained downtrend.
    close = np.linspace(2200, 1800, n)
    # Add a small noise component so stoch/sweep would otherwise fire.
    close = close + np.sin(np.arange(n) / 5.0) * 1.5
    ohlc = _ohlc(close, idx)
    out = emit_signals(ohlc)
    assert int(((out["signal"]) & (out["direction"] == 1)).sum()) == 0


# --------------------------------------------------------------------------- #
# 13b. Output structural columns are present and typed                         #
# --------------------------------------------------------------------------- #
def test_output_columns_present():
    n = 500
    idx = _m15_idx(n)
    ohlc = _ohlc(np.full(n, 2000.0), idx)
    out = emit_signals(ohlc)
    for col in ["signal", "direction", "triggering_level", "level_value", "level_distance_atr"]:
        assert col in out.columns
    assert out["direction"].dtype == np.int64
    # On flat input the triggering_level entries must all be empty strings.
    assert (out["triggering_level"] == "").all()


# --------------------------------------------------------------------------- #
# Edge-triggered Stochastic: synthetic veto check                              #
# --------------------------------------------------------------------------- #
def test_no_signal_on_flat_input():
    """Flat price → no sweep, no stochastic cross, no signal."""
    n = 800
    idx = _m15_idx(n)
    ohlc = _ohlc(np.full(n, 2000.0), idx)
    out = emit_signals(ohlc)
    assert not out["signal"].any()
