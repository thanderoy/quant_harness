"""AVWAP-only multi-bar sweep-and-reclaim signal on XAUUSD M15.

DIAGNOSTIC role: entry-only edge measurement. Differs from
``avwap_sweep_reclaim_m15`` in that the sweep may persist for 1, 2, or 3
consecutive M15 bars before the reclaim — same-candle reclaim is included
(sweep_bars=1) so the prior single-candle variant is a strict subset of this
trigger set.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from research.pre.signals._ny_anchor import daily_ny_anchor_timestamps

__all__ = ["emit_signals"]


# --------------------------------------------------------------------------- #
# Indicators — mirrored locally (research/ does not import from strategies/).  #
# --------------------------------------------------------------------------- #
def _wma(series: pd.Series, period: int) -> pd.Series:
    weights = np.arange(1, period + 1, dtype=float)
    weight_sum = weights.sum()
    return series.rolling(period).apply(
        lambda x: float(np.dot(x, weights) / weight_sum), raw=True
    )


def _hma(series: pd.Series, period: int) -> pd.Series:
    half = period // 2
    sqrtp = int(round(math.sqrt(period)))
    return _wma(2.0 * _wma(series, half) - _wma(series, period), sqrtp)


def _stochastic(
    high: pd.Series, low: pd.Series, close: pd.Series,
    k_period: int, d_period: int, smooth_k: int,
) -> tuple[pd.Series, pd.Series]:
    lowest = low.rolling(k_period).min()
    highest = high.rolling(k_period).max()
    rng = highest - lowest
    raw_k = (close - lowest) / rng * 100.0
    raw_k = raw_k.where(rng > 0, 50.0)
    k = raw_k.rolling(smooth_k).mean()
    d = k.rolling(d_period).mean()
    return k, d


def _wilder_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1
    ).max(axis=1)
    n = len(close)
    out = np.full(n, np.nan)
    if n < period + 1:
        return pd.Series(out, index=close.index)
    out[period] = tr.iloc[1 : period + 1].mean()
    for i in range(period + 1, n):
        out[i] = (out[i - 1] * (period - 1) + tr.iloc[i]) / period
    return pd.Series(out, index=close.index)


# --------------------------------------------------------------------------- #
# AVWAP                                                                        #
# --------------------------------------------------------------------------- #
def _avwap_anchored(m15_df: pd.DataFrame, anchor_ts: pd.Series) -> pd.Series:
    tpv = (m15_df["high"] + m15_df["low"] + m15_df["close"]) / 3.0 * m15_df["volume"]
    grouped = pd.DataFrame(
        {"tpv": tpv.to_numpy(), "vol": m15_df["volume"].to_numpy(),
         "anchor": anchor_ts.to_numpy()},
        index=m15_df.index,
    )
    cum_tpv = grouped.groupby("anchor", sort=False)["tpv"].cumsum()
    cum_vol = grouped.groupby("anchor", sort=False)["vol"].cumsum()
    return cum_tpv / cum_vol.replace(0, np.nan)


# --------------------------------------------------------------------------- #
# Multi-bar sweep state machine                                                #
# --------------------------------------------------------------------------- #
def _scan_multibar_reclaim(
    close: np.ndarray,
    avwap: np.ndarray,
    threshold: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (sweep_bars, direction) arrays.

    - sweep_bars[t] = number of consecutive sweep bars before the reclaim that
      completes at bar t (only set on reclaim bars; 0 elsewhere).
    - direction[t]  = +1 if a long-side reclaim completed at t (price was
      below AVWAP during the sweep, reclaimed above); -1 for short; 0 otherwise.

    State semantics (per the spec):
      - "Begins" at N: first bar where close crosses past level by >= threshold.
      - "Continues" at N+k: close still past level by *any* amount.
      - "Completes" at M: close back on original side; signal iff M-N in {1,2,3}.
      - 4+ persistent sweep bars => timeout, no signal, sweep resets when
        close returns to original side.
    """
    n = len(close)
    sweep_bars = np.zeros(n, dtype=np.int64)
    direction = np.zeros(n, dtype=np.int64)

    # Active sweep state: side in {0, +1 (long-side sweep, i.e. close < level),
    #                              -1 (short-side sweep, i.e. close > level)}.
    # 'duration' is the number of bars the sweep has persisted (>=1).
    # 'timed_out' indicates we are still on the wrong side after 3+ bars and
    # must wait for a reclaim before allowing any new sweep.
    side = 0
    duration = 0
    timed_out = False

    for t in range(n):
        lv = avwap[t]
        thr = threshold[t]
        c = close[t]
        if not (np.isfinite(lv) and np.isfinite(thr) and np.isfinite(c)):
            continue

        if side == 0:
            # Idle — look for a sweep start at this bar.
            if c < lv - thr:
                side = 1     # long-side opportunity (price below level)
                duration = 1
                timed_out = False
            elif c > lv + thr:
                side = -1
                duration = 1
                timed_out = False
            continue

        # Active sweep — check reclaim or continuation.
        if side == 1:
            if c > lv:
                # Reclaim. Emit signal if duration in {1,2,3} and not timed out.
                if (not timed_out) and 1 <= duration <= 3:
                    sweep_bars[t] = duration
                    direction[t] = 1
                # Reset state.
                side = 0
                duration = 0
                timed_out = False
                # Could a fresh opposite-side sweep open on this same bar?
                # The spec doesn't say no. The bar already reclaimed so close
                # is on the original side; can't be a new sweep until next bar.
            else:
                # Still on wrong side — continues.
                duration += 1
                if duration > 3:
                    timed_out = True
        else:  # side == -1
            if c < lv:
                if (not timed_out) and 1 <= duration <= 3:
                    sweep_bars[t] = duration
                    direction[t] = -1
                side = 0
                duration = 0
                timed_out = False
            else:
                duration += 1
                if duration > 3:
                    timed_out = True

    return sweep_bars, direction


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #
def emit_signals(
    m15_df: pd.DataFrame,
    h1_hma_period: int = 50,
    sweep_threshold_atr_mult: float = 0.2,
    stoch_k: int = 14,
    stoch_d: int = 3,
    stoch_smooth: int = 3,
    atr_period: int = 14,
) -> pd.DataFrame:
    required = ["open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in m15_df.columns]
    if missing:
        raise ValueError(f"m15_df missing columns: {missing}")
    if m15_df.index.tz is None:
        raise ValueError("m15_df.index must be tz-aware (UTC)")

    n = len(m15_df)
    close_m = m15_df["close"].to_numpy(dtype=float)

    # ATR(14) and threshold
    atr_m = _wilder_atr(
        m15_df["high"], m15_df["low"], m15_df["close"], atr_period
    ).to_numpy()
    threshold = sweep_threshold_atr_mult * atr_m

    # H1 HMA(50), lagged one bar, reindexed to M15 with ffill.
    h1 = m15_df.resample("1h", label="right", closed="right").agg(
        open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"),
    ).dropna()
    h1_hma_lag = _hma(h1["close"], h1_hma_period).shift(1)
    hma_on_m15 = h1_hma_lag.reindex(m15_df.index, method="ffill").to_numpy()
    above_hma = close_m > hma_on_m15
    below_hma = close_m < hma_on_m15

    # Stochastic on M15, edge-triggered cross at the reclaim bar.
    k, d = _stochastic(m15_df["high"], m15_df["low"], m15_df["close"],
                       stoch_k, stoch_d, stoch_smooth)
    k_arr = k.to_numpy(); d_arr = d.to_numpy()
    k_prev = np.concatenate([[np.nan], k_arr[:-1]])
    d_prev = np.concatenate([[np.nan], d_arr[:-1]])
    stoch_long_cross = (k_arr > d_arr) & (k_prev <= d_prev) & (k_arr < 20) & (d_arr < 20)
    stoch_short_cross = (k_arr < d_arr) & (k_prev >= d_prev) & (k_arr > 80) & (d_arr > 80)

    # AVWAP
    anchor_ts = daily_ny_anchor_timestamps(m15_df.index)
    avwap_series = _avwap_anchored(m15_df, anchor_ts)
    avwap = avwap_series.to_numpy()

    # Multi-bar sweep state machine — produces candidate reclaim events.
    sweep_bars_raw, direction_raw = _scan_multibar_reclaim(close_m, avwap, threshold)

    # Apply HMA bias and Stochastic gate at the reclaim bar.
    signal = np.zeros(n, dtype=bool)
    direction = np.zeros(n, dtype=np.int64)
    sweep_bars_out = np.zeros(n, dtype=np.int64)
    avwap_at_signal = np.full(n, np.nan)

    for t in range(n):
        d_ = direction_raw[t]
        if d_ == 0:
            continue
        if d_ == 1:
            if not above_hma[t] or not stoch_long_cross[t]:
                continue
        else:
            if not below_hma[t] or not stoch_short_cross[t]:
                continue
        signal[t] = True
        direction[t] = d_
        sweep_bars_out[t] = int(sweep_bars_raw[t])
        avwap_at_signal[t] = float(avwap[t])

    return pd.DataFrame(
        {
            "signal": signal,
            "direction": direction,
            "sweep_bars": sweep_bars_out,
            "avwap": avwap_at_signal,
        },
        index=m15_df.index,
    )
