"""Weighted and Hull moving averages — ported from WMPS under T11.

These are the D8 golden implementations, copied without numerical change.
`resources` is where the single definition of each lives from here on: the
live app, the backtester and the research engines had three copies between
them, and three copies of a formula is three chances for a backtest to
disagree with the account.

There is nothing instrument-specific to remove — a weighted mean of a price
series does not know what it is averaging — so unlike the sizer this port is
a move, not a rewrite, and X22 asserts exact equality against the fixture.

`hma`'s window arithmetic is worth naming because it is easy to "tidy" into
something subtly different: the half window is `period // 2` (floor) and the
smoothing window is `round(sqrt(period))`, which is banker's rounding on a
Python float. For period=21 that is 10 and 5; for period=50, 25 and 7. Both
match TradingView's `ta.hma()`, which is the reason to leave them alone.
"""

from __future__ import annotations

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
