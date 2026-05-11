"""qhf.engines.indicators — self-contained indicator implementations.

Exact copies of the user's app.quant.strategies.indicators module so the
harness has no dependency on the live-trading app. Any change to the live
indicators must be mirrored here to keep backtests faithful.

Implementations:
    wma(series, period)              Linear Weighted Moving Average
    hma(series, period)              Hull Moving Average
    stochastic(h, l, c, k, d, sk)   Slow Stochastic Oscillator
    atr(h, l, c, period)             Wilder's Average True Range

All functions accept pandas Series and return pandas Series.
All match Pine Script's ta.hma() and ta.atr() conventions exactly.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def wma(series: pd.Series, period: int) -> pd.Series:
    """Weighted Moving Average. Most-recent bar has highest weight."""
    weights = np.arange(1, period + 1, dtype=float)
    weight_sum = weights.sum()

    def _apply(x: np.ndarray) -> float:
        return float(np.dot(x, weights) / weight_sum)

    return series.rolling(period).apply(_apply, raw=True)


def hma(series: pd.Series, period: int) -> pd.Series:
    """Hull Moving Average.

    Formula: WMA(2 * WMA(n/2) - WMA(n), sqrt(n))
    Matches TradingView's ta.hma().
    """
    half_period = period // 2
    sqrt_period = round(math.sqrt(period))
    wma_half = wma(series, half_period)
    wma_full = wma(series, period)
    diff = 2.0 * wma_half - wma_full
    return wma(diff, sqrt_period)


def stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
    smooth_k: int = 3,
) -> tuple[pd.Series, pd.Series]:
    """Slow Stochastic Oscillator. Returns (%K, %D).

    %K = SMA(raw_k, smooth_k)
    %D = SMA(%K, d_period)
    raw_k = (close - lowest_low) / (highest_high - lowest_low) * 100
    """
    lowest_low = low.rolling(k_period).min()
    highest_high = high.rolling(k_period).max()
    hl_range = highest_high - lowest_low
    raw_k = (close - lowest_low) / hl_range * 100
    raw_k = raw_k.where(hl_range > 0, 50.0)
    k = raw_k.rolling(smooth_k).mean()
    d = k.rolling(d_period).mean()
    return k, d


def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Average True Range using Wilder's smoothing.

    Matches Pine Script's ta.atr(). Seeded with SMA of first `period` TRs.
    """
    n = len(close)
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)

    atr_vals = np.full(n, np.nan)
    if n < period + 1:
        return pd.Series(atr_vals, index=close.index)

    atr_vals[period] = tr.iloc[1: period + 1].mean()
    for i in range(period + 1, n):
        atr_vals[i] = (atr_vals[i - 1] * (period - 1) + tr.iloc[i]) / period

    return pd.Series(atr_vals, index=close.index)
