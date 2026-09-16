"""Synthetic bars, deterministic, with no instrument identity attached.

Every test in this package runs on generated series rather than on a price
file. That is not a convenience: a fixture named XAUUSD_H1.csv would put an
instrument assumption into the one package whose whole claim is that it has
none, and it would make the suite unrunnable on a CI runner — which is how
T9a shipped green and only ever worked on one laptop.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def make_bars(n: int = 3000, *, seed: int = 11, start: float = 100.0,
              drift: float = 0.0003, vol: float = 0.004,
              freq: str = "h") -> pd.DataFrame:
    """A geometric random walk shaped like OHLC bars.

    ``open[t] == close[t-1]``, so the series has no gaps — gap behaviour is
    the mask's concern (X3/X4), not this package's.
    """
    rng = np.random.default_rng(seed)
    index = pd.date_range("2020-01-01", periods=n, freq=freq, tz="UTC")
    close = start * np.exp(rng.normal(drift, vol, n).cumsum())
    wick = np.abs(rng.normal(0, vol / 2, n))
    high = close * (1 + wick)
    low = close * (1 - wick)
    open_ = np.concatenate([[close[0]], close[:-1]])
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close,
         "volume": rng.integers(50, 500, n).astype(float)},
        index=index,
    )
