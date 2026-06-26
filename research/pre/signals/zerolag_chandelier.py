"""Chandelier direction-flip entry filtered by H4 ZLSMA bias.

This is the signal generator for the ``zerolag_chandelier`` hypothesis (see
``research/log/entries.jsonl`` seq=19). It is intentionally upstream of any
strategy code: no stops, no exits, no sizing — only ``(direction, signal)``
on each closed M15 bar.

Look-ahead protection
---------------------
The H4 series is resampled from M15 with ``label='right', closed='right'``
so each H4 bar is timestamped at its close, and the ZLSMA slope is consumed
at ``.shift(1)`` — only the *previously closed* H4 bar's slope is visible to
an M15 bar inside the current (still-forming) H4 window.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = ["emit_signals"]


# --------------------------------------------------------------------------- #
# Indicators                                                                   #
# --------------------------------------------------------------------------- #
def _wilder_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    n = len(close)
    out = np.full(n, np.nan)
    if n < period + 1:
        return pd.Series(out, index=close.index)
    out[period] = tr.iloc[1 : period + 1].mean()
    for i in range(period + 1, n):
        out[i] = (out[i - 1] * (period - 1) + tr.iloc[i]) / period
    return pd.Series(out, index=close.index)


def _linreg_endpoint(series: pd.Series, length: int) -> pd.Series:
    """Endpoint of OLS line over trailing ``length`` bars — Pine's ``ta.linreg(src, length, 0)``.

    Closed-form: for x = [0..n-1], the endpoint is mean(y) + slope * (n-1)/2.
    """
    n = length
    if n < 2:
        raise ValueError("length must be >= 2")
    x = np.arange(n, dtype=float)
    x_mean = (n - 1) / 2.0
    sxx = float(((x - x_mean) ** 2).sum())

    vals = series.to_numpy(dtype=float)
    out = np.full(vals.shape, np.nan)
    if len(vals) < n:
        return pd.Series(out, index=series.index)

    # Sliding windows: shape (len-n+1, n)
    sw = np.lib.stride_tricks.sliding_window_view(vals, n)
    y_mean = sw.mean(axis=1)
    sxy = (sw * (x - x_mean)).sum(axis=1)
    slope = sxy / sxx
    endpoint = y_mean + slope * (n - 1 - x_mean)  # = y_mean + slope * (n-1)/2
    out[n - 1 :] = endpoint
    return pd.Series(out, index=series.index)


def _zlsma(close: pd.Series, length: int) -> pd.Series:
    lsma = _linreg_endpoint(close, length)
    lsma2 = _linreg_endpoint(lsma, length)
    return lsma + (lsma - lsma2)


# --------------------------------------------------------------------------- #
# Chandelier direction                                                         #
# --------------------------------------------------------------------------- #
def _chandelier_direction(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    atr_period: int,
    atr_mult: float,
) -> pd.Series:
    """Ratcheting Chandelier direction matching the Pine reference.

    The lookback for rolling max/min is ``atr_period`` (14) — same as the ATR
    lookback, per the Pine source. Initial seed: ``dir[0] = +1``.
    """
    atr = _wilder_atr(high, low, close, atr_period).to_numpy()
    close_arr = close.to_numpy(dtype=float)
    n = len(close_arr)

    # Rolling max/min of close over atr_period bars (inclusive of current).
    roll_max = close.rolling(atr_period, min_periods=atr_period).max().to_numpy()
    roll_min = close.rolling(atr_period, min_periods=atr_period).min().to_numpy()

    long_stop = np.full(n, np.nan)
    short_stop = np.full(n, np.nan)
    direction = np.ones(n, dtype=np.int64)  # seed +1

    for t in range(n):
        atr_t = atr[t]
        if not np.isfinite(atr_t):
            # Warm-up: keep direction at seed, stops undefined.
            continue
        band = atr_mult * atr_t
        ls_raw = roll_max[t] - band
        ss_raw = roll_min[t] + band

        if t == 0 or not np.isfinite(long_stop[t - 1]):
            long_stop[t] = ls_raw
            short_stop[t] = ss_raw
        else:
            long_stop[t] = (
                max(ls_raw, long_stop[t - 1])
                if close_arr[t - 1] > long_stop[t - 1]
                else ls_raw
            )
            short_stop[t] = (
                min(ss_raw, short_stop[t - 1])
                if close_arr[t - 1] < short_stop[t - 1]
                else ss_raw
            )

        if t == 0 or not np.isfinite(short_stop[t - 1]) or not np.isfinite(long_stop[t - 1]):
            # First evaluated bar: keep seed +1.
            direction[t] = 1 if t == 0 else direction[t - 1]
            continue

        if close_arr[t] > short_stop[t - 1]:
            direction[t] = 1
        elif close_arr[t] < long_stop[t - 1]:
            direction[t] = -1
        else:
            direction[t] = direction[t - 1]

    return pd.Series(direction, index=close.index)


# --------------------------------------------------------------------------- #
# Public entry point                                                           #
# --------------------------------------------------------------------------- #
def emit_signals(
    m15_df: pd.DataFrame,
    chandelier_atr_period: int = 14,
    chandelier_atr_mult: float = 2.5,
    h4_zlsma_length: int = 50,
) -> pd.DataFrame:
    """Emit Chandelier direction-flip signals filtered by H4 ZLSMA slope.

    Parameters
    ----------
    m15_df:
        M15 OHLC with columns ``open``, ``high``, ``low``, ``close`` and a
        tz-aware UTC ``DatetimeIndex``.
    chandelier_atr_period, chandelier_atr_mult, h4_zlsma_length:
        Frozen design parameters for this hypothesis.

    Returns
    -------
    DataFrame indexed by ``m15_df.index`` with columns:
        - ``direction``: +1 / -1 / 0 (0 only on non-trigger bars)
        - ``signal``: bool, True only on direction-flip bars where the H4
          ZLSMA slope agrees with the flip direction.
    """
    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in m15_df.columns]
    if missing:
        raise ValueError(f"m15_df missing columns: {missing}")

    m15_df = m15_df[required]
    high, low, close = m15_df["high"], m15_df["low"], m15_df["close"]

    # M15 Chandelier direction
    direction = _chandelier_direction(
        high, low, close, chandelier_atr_period, chandelier_atr_mult
    )

    # H4 resample — right-labelled, right-closed so each bar is stamped at close.
    h4 = m15_df.resample("4h", label="right", closed="right").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
    ).dropna()

    zlsma_h4 = _zlsma(h4["close"], h4_zlsma_length)
    zlsma_lag = zlsma_h4.shift(1)  # use prior closed H4 bar only
    h4_rising = zlsma_lag > zlsma_lag.shift(1)
    h4_falling = zlsma_lag < zlsma_lag.shift(1)

    # Reindex H4 filter to M15 with forward fill. Combined with the .shift(1)
    # above, M15 bars inside the still-forming H4 candle see only the prior
    # closed H4 candle's slope.
    h4_rising_m15 = h4_rising.reindex(m15_df.index, method="ffill").fillna(False)
    h4_falling_m15 = h4_falling.reindex(m15_df.index, method="ffill").fillna(False)

    prev_dir = direction.shift(1)
    long_flip = (direction == 1) & (prev_dir == -1)
    short_flip = (direction == -1) & (prev_dir == 1)

    signal_long = long_flip & h4_rising_m15
    signal_short = short_flip & h4_falling_m15

    signal = (signal_long | signal_short).fillna(False).astype(bool)
    sig_dir = np.where(signal_long, 1, np.where(signal_short, -1, 0)).astype(np.int64)

    return pd.DataFrame(
        {"direction": sig_dir, "signal": signal.to_numpy()},
        index=m15_df.index,
    )
