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
    """Weighted Moving Average. Weights are linear: most recent bar has highest weight.

    The reduction is :func:`math.fsum`, not ``np.dot``, and the reason is the
    whole of X22's history.

    ``np.dot`` dispatches to BLAS. OpenBLAS blocks and vectorises the
    reduction, and how it blocks depends on the kernel it selects for the CPU
    it finds at run time — so the summation *order*, and therefore the last
    bit, is a property of the machine rather than of this source. That was
    already known (T11, seq=97/98). What was not known until 2026-09-20 is
    that it is not only the machine: regenerating the D8 fixture from
    byte-identical WMPS sources, on byte-identical input, on the *same*
    machine reproduced ``wma_20``, ``wma_55``, ``hma_21`` and ``hma_55`` only
    to 5 ULP, because numpy moved underneath it. ``wma_9``, the column seq=98
    recorded as the one CI could not reproduce, came back exact. The set of
    drifting columns is itself unstable, which is the point at which "pin the
    values and bound the difference" stops being a contract at all: it pins a
    toolchain, and it has to be re-pinned at every numpy bump.

    ``math.fsum`` is correctly rounded — it returns the nearest float64 to the
    exact sum, by construction. The elementwise products are themselves
    exactly rounded by IEEE-754. So the result is fixed by the standard, not
    by a kernel, a thread count or a numpy release, and is reproducible on any
    conforming platform. This costs roughly 2-3x on the reduction, which is
    hundredths of a second over 6000 bars, and buys a fixture that does not
    expire.

    It is deliberately 2-4 ULP away from WMPS's ``np.dot``, and it is the more
    accurate of the two. D8 pins the arithmetic, not the accident of how one
    machine once summed it.
    """
    weights = np.arange(1, period + 1, dtype=float)
    weight_sum = float(weights.sum())

    def _apply(x: np.ndarray) -> float:
        return math.fsum(x * weights) / weight_sum

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
