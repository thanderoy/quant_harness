"""
Unit tests for app.quant.strategies.indicators

Fixture: 20 bars, monotonically rising prices.
  close[i] = 1801 + i
  high[i]  = 1805 + i
  low[i]   = 1795 + i

With this fixture:
  TR[i>=1] = max(10, 5, 5) = 10  →  ATR(14) = 10.0 everywhere it is defined
  raw_k[i>=13] = 19/23 * 100 ≈ 82.6087  →  k = d ≈ 82.6087 after warmup
"""

import math

import numpy as np
import pandas as pd
import pytest

from app.quant.strategies.indicators import atr, hma, stochastic, wma

N = 20
CLOSE = pd.Series([1801.0 + i for i in range(N)])
HIGH = pd.Series([1805.0 + i for i in range(N)])
LOW = pd.Series([1795.0 + i for i in range(N)])

RAW_K_CONST = 19.0 / 23.0 * 100  # ≈ 82.6087


# ---------------------------------------------------------------------------
# WMA
# ---------------------------------------------------------------------------


def test_wma_length_preserved():
    series = pd.Series([10.0 * i for i in range(1, 8)])  # 7 values
    result = wma(series, period=5)
    assert len(result) == 7


def test_wma_nan_padding():
    series = pd.Series([10.0 * i for i in range(1, 8)])
    result = wma(series, period=5)
    assert result.iloc[:4].isna().all()
    assert not result.iloc[4:].isna().any()


def test_wma_known_values():
    # close = [10, 20, 30, 40, 50, 60, 70], period=5
    series = pd.Series([10.0 * i for i in range(1, 8)])
    result = wma(series, period=5)
    # WMA(5)[4] = (1*10 + 2*20 + 3*30 + 4*40 + 5*50) / 15 = 550/15
    assert result.iloc[4] == pytest.approx(550.0 / 15, rel=1e-6)
    # WMA(5)[5] = (1*20 + 2*30 + 3*40 + 4*50 + 5*60) / 15 = 700/15
    assert result.iloc[5] == pytest.approx(700.0 / 15, rel=1e-6)
    # WMA(5)[6] = (1*30 + 2*40 + 3*50 + 4*60 + 5*70) / 15 = 850/15
    assert result.iloc[6] == pytest.approx(850.0 / 15, rel=1e-6)


def test_wma_period_longer_than_series():
    series = pd.Series([1.0, 2.0, 3.0])
    result = wma(series, period=10)
    assert len(result) == 3
    assert result.isna().all()


def test_wma_constant_series():
    series = pd.Series([5.0] * 10)
    result = wma(series, period=3)
    assert result.dropna().tolist() == pytest.approx([5.0] * 8, rel=1e-6)


# ---------------------------------------------------------------------------
# HMA
# ---------------------------------------------------------------------------


def test_hma_length_preserved():
    result = hma(CLOSE, period=14)
    assert len(result) == N


def test_hma_nan_at_start():
    result = hma(CLOSE, period=14)
    # HMA(14): warmup = 14 (WMA full) + sqrt(14)≈4 - 1 = 16
    assert result.iloc[:16].isna().all()


def test_hma_non_nan_after_warmup():
    result = hma(CLOSE, period=14)
    valid = result.dropna()
    assert len(valid) > 0
    assert not valid.isna().any()


def test_hma_period_longer_than_series():
    short = pd.Series([1800.0 + i for i in range(5)])
    result = hma(short, period=10)
    assert len(result) == 5
    assert result.isna().all()


def test_hma_linear_series_tracks_price():
    # For a steadily rising series, HMA values should also rise
    result = hma(CLOSE, period=14)
    valid = result.dropna().reset_index(drop=True)
    diffs = valid.diff().dropna()
    assert (diffs > 0).all(), "HMA should rise on a strictly rising close series"


# ---------------------------------------------------------------------------
# Stochastic
# ---------------------------------------------------------------------------


def test_stochastic_length_preserved():
    k, d = stochastic(HIGH, LOW, CLOSE, k_period=14, d_period=3, smooth_k=3)
    assert len(k) == N
    assert len(d) == N


def test_stochastic_nan_padding():
    k, d = stochastic(HIGH, LOW, CLOSE, k_period=14, d_period=3, smooth_k=3)
    # raw_k valid from index 13, k from 13+2=15, d from 15+2=17
    assert k.iloc[:15].isna().all()
    assert d.iloc[:17].isna().all()


def test_stochastic_known_k_value():
    k, _ = stochastic(HIGH, LOW, CLOSE, k_period=14, d_period=3, smooth_k=3)
    # k[15..19] should be the smoothed constant raw_k ≈ 82.6087
    for i in range(15, N):
        assert k.iloc[i] == pytest.approx(RAW_K_CONST, rel=1e-4)


def test_stochastic_known_d_value():
    _, d = stochastic(HIGH, LOW, CLOSE, k_period=14, d_period=3, smooth_k=3)
    for i in range(17, N):
        assert d.iloc[i] == pytest.approx(RAW_K_CONST, rel=1e-4)


def test_stochastic_period_longer_than_series():
    short_high = HIGH.iloc[:5]
    short_low = LOW.iloc[:5]
    short_close = CLOSE.iloc[:5]
    k, d = stochastic(short_high, short_low, short_close, k_period=14)
    assert len(k) == 5
    assert k.isna().all()


def test_stochastic_constant_price_no_crash():
    """Constant price produces range=0. Should not raise; returns 50.0 (midpoint)."""
    const = pd.Series([1900.0] * 20)
    k, d = stochastic(const, const, const, k_period=5)
    # Where not NaN, values should be 50.0
    valid_k = k.dropna()
    assert (valid_k == 50.0).all()


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------


def test_atr_length_preserved():
    result = atr(HIGH, LOW, CLOSE, period=14)
    assert len(result) == N


def test_atr_nan_at_start():
    result = atr(HIGH, LOW, CLOSE, period=14)
    # ATR valid from index 14
    assert result.iloc[:14].isna().all()


def test_atr_non_nan_after_warmup():
    result = atr(HIGH, LOW, CLOSE, period=14)
    assert not result.iloc[14:].isna().any()


def test_atr_constant_tr():
    # TR is always 10 for this fixture → ATR should be exactly 10.0
    result = atr(HIGH, LOW, CLOSE, period=14)
    for i in range(14, N):
        assert result.iloc[i] == pytest.approx(10.0, rel=1e-6)


def test_atr_period_longer_than_series():
    result = atr(HIGH.iloc[:5], LOW.iloc[:5], CLOSE.iloc[:5], period=14)
    assert len(result) == 5
    assert result.isna().all()


def test_atr_wilder_smoothing():
    """
    Create a TR series that steps from 10 to 20 after the seed period.
    Verify Wilder's formula: atr[i] = (atr[i-1] * 13 + tr[i]) / 14
    """
    period = 14
    n = 30
    # Build close, high, low so TR = 10 for first 15 bars, 20 afterwards
    close_vals = [1800.0 + i for i in range(n)]
    high_vals = [c + 5 for c in close_vals]
    low_vals = [c - 5 for c in close_vals]
    # Override high for bars 15..29 to make TR=20
    for i in range(15, n):
        high_vals[i] = close_vals[i] + 10
    c = pd.Series(close_vals)
    h = pd.Series(high_vals)
    lo = pd.Series(low_vals)

    result = atr(h, lo, c, period=period)

    # Seed ATR at index 14 = mean(TR[1..14]) = 10.0
    assert result.iloc[14] == pytest.approx(10.0, rel=1e-6)
    # Index 15: Wilder step with TR[15]=20
    expected_15 = (10.0 * 13 + 20.0) / 14
    assert result.iloc[15] == pytest.approx(expected_15, rel=1e-6)
    # Index 16: Wilder step with TR[16]=20
    expected_16 = (expected_15 * 13 + 20.0) / 14
    assert result.iloc[16] == pytest.approx(expected_16, rel=1e-6)
