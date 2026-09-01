"""AVWAP / POC / HVN sweep-and-reclaim signal on XAUUSD M15.

DIAGNOSTIC role: entry-only edge measurement. The strategy's edge claim lives
in the exit design downstream — a flat or sub-1.0 E-Ratio here does not
falsify the hypothesis.

Look-ahead protections (all enforced):
- H1 HMA(50) referenced at the previously closed H1 bar (.shift(1)) before
  reindexing to M15.
- AVWAP cumulative through bar t (observable at bar t's close — no shift).
- Rolling Volume Profile uses [T-120, T-1] strictly; bin width fixed at
  close[T-1].
- Stochastic cross condition is edge-triggered at bar t (uses [t-1, t] only).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from research.pre.signals._ny_anchor import daily_ny_anchor_timestamps
from research.pre.signals._volume_profile import rolling_volume_profile_levels

__all__ = ["emit_signals"]


# --------------------------------------------------------------------------- #
# Indicators — mirrored locally (research/ does not import from strategies/).  #
# These match strategies/indicators.py bit-for-bit.                            #
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
    avwap = cum_tpv / cum_vol.replace(0, np.nan)
    return avwap


# --------------------------------------------------------------------------- #
# H1 mapping for M15 bars                                                      #
# --------------------------------------------------------------------------- #
def _m15_to_containing_h1(m15_index: pd.DatetimeIndex, h1_index: pd.DatetimeIndex) -> np.ndarray:
    """Map each M15 bar to the index of its containing H1 bar.

    H1 bars are right-labelled / right-closed, so the H1 bar that contains an
    M15 bar timestamped at time T is the H1 bar at the smallest H1 boundary
    >= T. searchsorted(side='left') returns exactly that position.
    """
    pos = h1_index.searchsorted(m15_index, side="left")
    pos = np.clip(pos, 0, len(h1_index) - 1)
    return pos


# --------------------------------------------------------------------------- #
# Sweep+reclaim primitive                                                      #
# --------------------------------------------------------------------------- #
def _long_sweep(open_: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray,
                level: np.ndarray, threshold: np.ndarray) -> np.ndarray:
    return (low < level - threshold) & (close > level) & (open_ > level)


def _short_sweep(open_: np.ndarray, high: np.ndarray, low: np.ndarray, close: np.ndarray,
                 level: np.ndarray, threshold: np.ndarray) -> np.ndarray:
    return (high > level + threshold) & (close < level) & (open_ < level)


# --------------------------------------------------------------------------- #
# Public API                                                                   #
# --------------------------------------------------------------------------- #
def emit_signals(
    m15_df: pd.DataFrame,
    h1_hma_period: int = 50,
    vp_lookback_bars: int = 120,
    vp_bin_width_pct: float = 0.00025,
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
    open_m = m15_df["open"].to_numpy(dtype=float)
    high_m = m15_df["high"].to_numpy(dtype=float)
    low_m = m15_df["low"].to_numpy(dtype=float)
    close_m = m15_df["close"].to_numpy(dtype=float)

    # ATR(14) on M15
    atr_m = _wilder_atr(m15_df["high"], m15_df["low"], m15_df["close"], atr_period).to_numpy()
    threshold = sweep_threshold_atr_mult * atr_m

    # H1 resample
    h1 = m15_df.resample("1h", label="right", closed="right").agg(
        open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"),
        volume=("volume", "sum"),
    ).dropna()

    # H1 HMA(50), lagged one bar, reindexed to M15 with ffill.
    h1_hma_lag = _hma(h1["close"], h1_hma_period).shift(1)
    hma_on_m15 = h1_hma_lag.reindex(m15_df.index, method="ffill").to_numpy()
    above_hma = close_m > hma_on_m15
    below_hma = close_m < hma_on_m15

    # Stochastic on M15, edge-triggered cross at bar t.
    k, d = _stochastic(m15_df["high"], m15_df["low"], m15_df["close"],
                       stoch_k, stoch_d, stoch_smooth)
    k_arr = k.to_numpy()
    d_arr = d.to_numpy()
    k_prev = np.concatenate([[np.nan], k_arr[:-1]])
    d_prev = np.concatenate([[np.nan], d_arr[:-1]])
    stoch_long_cross = (k_arr > d_arr) & (k_prev <= d_prev) & (k_arr < 20) & (d_arr < 20)
    stoch_short_cross = (k_arr < d_arr) & (k_prev >= d_prev) & (k_arr > 80) & (d_arr > 80)

    # AVWAP (NY anchor, DST-aware)
    anchor_ts = daily_ny_anchor_timestamps(m15_df.index)
    avwap_series = _avwap_anchored(m15_df, anchor_ts)
    avwap = avwap_series.to_numpy()

    # Volume Profile on H1 — POC and HVN list per H1 bar.
    vp = rolling_volume_profile_levels(h1, vp_lookback_bars, vp_bin_width_pct)
    poc_h1 = vp["poc"].to_numpy()
    hvn_prices_h1 = vp["hvn_prices"].tolist()

    # Map each M15 bar to its containing H1 bar.
    h1_pos = _m15_to_containing_h1(m15_df.index, h1.index)
    poc_on_m15 = poc_h1[h1_pos]

    # --- Per-bar level selection + sweep evaluation ------------------------- #
    direction = np.zeros(n, dtype=np.int64)
    signal = np.zeros(n, dtype=bool)
    level_value = np.full(n, np.nan)
    level_distance_atr = np.full(n, np.nan)
    triggering_level = np.array([""] * n, dtype=object)

    # Iterate per-bar. Vectorising the HVN proximity-filter loop across all
    # bars is awkward because the HVN set is variable-length per H1 bar.
    for t in range(n):
        if not np.isfinite(atr_m[t]) or atr_m[t] <= 0:
            continue

        # Candidate level set: (label, value)
        candidates: list[tuple[str, float]] = []
        a = avwap[t]
        if np.isfinite(a):
            candidates.append(("avwap", float(a)))
        p = poc_on_m15[t]
        if np.isfinite(p):
            candidates.append(("poc", float(p)))

        hvns = hvn_prices_h1[h1_pos[t]]
        if hvns:
            close_t = close_m[t]
            window = 2.0 * atr_m[t]
            nearby = [
                (h, abs(h - close_t)) for h in hvns if abs(h - close_t) <= window
            ]
            # hvns are already sorted by volume desc — take top-3 from that order
            top3 = [h for (h, _) in nearby][:3]
            for h in top3:
                candidates.append(("hvn", float(h)))

        if not candidates:
            continue

        # Evaluate sweep against each candidate; collect (label, value, dist, dir)
        thr = threshold[t]
        triggered: list[tuple[str, float, float, int]] = []
        for label, lv in candidates:
            lv_arr = np.array([lv])
            thr_arr = np.array([thr])
            o = np.array([open_m[t]]); h = np.array([high_m[t]])
            lo = np.array([low_m[t]]); cl = np.array([close_m[t]])
            if _long_sweep(o, h, lo, cl, lv_arr, thr_arr)[0]:
                triggered.append((label, lv, abs(close_m[t] - lv), 1))
            elif _short_sweep(o, h, lo, cl, lv_arr, thr_arr)[0]:
                triggered.append((label, lv, abs(close_m[t] - lv), -1))

        if not triggered:
            continue

        # Pick the closest level by distance to close.
        triggered.sort(key=lambda x: x[2])
        label, lv, dist, dir_ = triggered[0]

        # Apply HMA bias filter and stochastic confirmation.
        if dir_ == 1:
            if not above_hma[t] or not stoch_long_cross[t]:
                continue
        else:
            if not below_hma[t] or not stoch_short_cross[t]:
                continue

        direction[t] = dir_
        signal[t] = True
        level_value[t] = lv
        level_distance_atr[t] = dist / atr_m[t]
        triggering_level[t] = label

    return pd.DataFrame(
        {
            "signal": signal,
            "direction": direction,
            "triggering_level": triggering_level,
            "level_value": level_value,
            "level_distance_atr": level_distance_atr,
        },
        index=m15_df.index,
    )
