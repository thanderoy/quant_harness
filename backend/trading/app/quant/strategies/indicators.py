import math

import numpy as np
import pandas as pd


def wma(series: pd.Series, period: int) -> pd.Series:
    """Weighted Moving Average. Weights are linear: most recent bar has highest weight."""
    weights = np.arange(1, period + 1, dtype=float)
    weight_sum = weights.sum()

    def _apply(x: np.ndarray) -> float:
        return float(np.dot(x, weights) / weight_sum)

    return series.rolling(period).apply(_apply, raw=True)


def hma(series: pd.Series, period: int) -> pd.Series:
    """
    Hull Moving Average.
    Formula: WMA(2 * WMA(n/2) - WMA(n), sqrt(n))
    Returns a Series of the same length as input, NaN-padded at the start.
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
    """
    Stochastic Oscillator. Returns (%K, %D).
    %K = SMA(raw_k, smooth_k) where raw_k = (close - lowest_low) / (highest_high - lowest_low) * 100
    %D = SMA(%K, d_period)

    Edge-case / insufficient-data contract:
      - Warmup: the first ``k_period - 1`` bars have no rolling window and are
        NaN; %K stays NaN until index ``k_period - 1 + smooth_k - 1`` and %D
        until a further ``d_period - 1`` bars. NaN is never silently filled.
      - If ``k_period`` exceeds the series length, every value is NaN.
      - Constant price (range == 0) yields the midpoint 50.0, not NaN — that is
        a defined reading, not missing data.
    Callers evaluating live signals must guard against NaN (e.g. skip the bar)
    rather than assume a numeric %K/%D is always present.
    """
    lowest_low = low.rolling(k_period).min()
    highest_high = high.rolling(k_period).max()
    hl_range = highest_high - lowest_low
    raw_k = (close - lowest_low) / hl_range * 100
    # When the range is exactly 0 (constant prices) default to the midpoint.
    # Use mask on `hl_range == 0` rather than `where(hl_range > 0, ...)`: the
    # latter also matches the warmup region (where hl_range is NaN, so the
    # comparison is False) and would clobber the leading NaN padding with 50.0.
    # `== 0` is False for NaN, so insufficient-data bars correctly stay NaN.
    raw_k = raw_k.mask(hl_range == 0, 50.0)
    k = raw_k.rolling(smooth_k).mean()
    d = k.rolling(d_period).mean()
    return k, d


def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """
    Average True Range using Wilder's smoothing (RMA/SMMA).
    True Range = max(high-low, abs(high-prev_close), abs(low-prev_close))
    Wilder smoothing: atr[i] = (atr[i-1] * (period-1) + tr[i]) / period
    Matches Pine Script's ta.atr() output.
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

    # Seed: SMA of first `period` TR values (TR starts at index 1)
    atr_vals[period] = tr.iloc[1 : period + 1].mean()

    # Wilder's recursive smoothing
    for i in range(period + 1, n):
        atr_vals[i] = (atr_vals[i - 1] * (period - 1) + tr.iloc[i]) / period

    return pd.Series(atr_vals, index=close.index)
