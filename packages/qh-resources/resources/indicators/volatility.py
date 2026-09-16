"""Wilder's Average True Range — ported from WMPS under T11.

Copied without numerical change from the D8 golden source. The seeding rule
is the part that varies between implementations and so is the part worth
stating: the first defined value sits at index `period` and is the plain mean
of `tr[1:period+1]`, after which the recursion takes over. True range at
index 0 is undefined (there is no previous close) and is excluded from the
seed rather than treated as `high - low`.

`research.engines.strategies.zlch` uses a variant that differs from this by
one bar. That was found during the crest_n_keel parity work and left alone
there; T11 does not reconcile it either, because it is an engine-internal
choice that shaped recorded results.

The loop is a genuine recursion, not a vectorisation someone forgot to do:
each value depends on the previous one. `ewm(alpha=1/period)` is close but
not equal — it applies a different seed — and swapping it in would break the
X22 fixture, which is the point of pinning it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


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
