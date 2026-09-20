"""Signal generator for flood_tide_h1 (see research/log/entries.jsonl seq=31).

Donchian-55 H1 breakout gated by an H4-EMA(200) trend filter and a Kaufman
Efficiency-Ratio directionality filter. Long-only. XAUUSD.

Pure function: OHLCV in, signal DataFrame out. No I/O, no P&L, no permutation
logic — those live in ``research/pre/scripts/run_flood_tide_edge.py``.

Frozen parameters mirror ``research/pre/flood_tide_h1.py`` ``FROZEN_PARAMS``.
Any divergence between the two is a bug — the pre-registration is immutable.

Closed-bar / no-look-ahead convention
-------------------------------------
Every quantity on bar ``t`` is computed from data available **at the close of
bar ``t``**. Concretely, ``entry_signal[t] == True`` means "as of the close of
bar ``t`` the breakout is confirmed and the regime permits it". This matches the
contract of :func:`research.pre.signal_edge.signal_edge_report`, where a signal
at bar ``t`` is acted on at ``open[t+1]``. There is therefore **exactly one**
bar of lag between observation and (hypothetical) fill — do not pre-shift the
close comparisons a second time or you double-lag the entry.

The Donchian channel is the only quantity shifted by one bar: the breakout tests
``close[t]`` against the highest high of the *prior* ``entry_len`` bars
(``t-entry_len .. t-1``), which excludes the current bar — mirroring Pine's
``ta.highest(high, N)[1]`` and the house ``iloc[-2]`` rule.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from resources.data.mask import IndicatorClass, TradabilityMask, masked_rolling

#: R3 class for the Donchian channels. Named once rather than repeated at four
#: call sites, so the four cannot drift apart.
_WINDOW = IndicatorClass.WINDOW

__all__ = ["FloodTideParams", "generate_signals", "efficiency_ratio", "merge_htf_to_ltf"]


@dataclass(frozen=True)
class FloodTideParams:
    """Frozen at hypothesis registration. Mirrors flood_tide_h1.FROZEN_PARAMS."""
    entry_len: int = 55
    exit_len: int = 20
    stop_len: int = 10
    htf_ema_len: int = 200
    er_len: int = 14
    er_threshold: float = 0.30
    reentry_cooldown_bars: int = 5


def efficiency_ratio(close: pd.Series, length: int) -> pd.Series:
    """Kaufman Efficiency Ratio over ``length`` bars.

    ER = |close[t] - close[t-length]| / sum(|close[i] - close[i-1]|, length)

    Bounded [0, 1]; higher = more directional path. Uses only closes up to and
    including bar ``t`` (rolling sum ends at ``t``), so it is look-ahead free.
    """
    net_change = (close - close.shift(length)).abs()
    per_bar_abs = close.diff().abs()
    path_length = per_bar_abs.rolling(length, min_periods=length).sum()
    er = net_change / path_length.replace(0, np.nan)
    return er.fillna(0.0)


def merge_htf_to_ltf(
    ltf: pd.DataFrame,
    htf_series: pd.Series,
    htf_series_name: str,
) -> pd.Series:
    """Merge an H4 series onto H1 timestamps without look-ahead.

    The H4 value carried onto H1 bar ``t`` is the LAST H4 value whose timestamp
    is *strictly earlier* than ``t``. ``merge_asof`` with
    ``allow_exact_matches=False`` + ``direction='backward'`` enforces this, so an
    H1 bar inside a still-forming H4 candle sees only the prior closed H4 value.

    Assumes both indexes are tz-aware UTC ``DatetimeIndex``, sorted ascending.
    """
    if not ltf.index.is_monotonic_increasing:
        raise ValueError("ltf index must be sorted ascending")
    if not htf_series.index.is_monotonic_increasing:
        raise ValueError("htf_series index must be sorted ascending")

    left = pd.DataFrame({"ltf_ts": ltf.index}, index=ltf.index)
    right = pd.DataFrame(
        {"htf_ts": htf_series.index, htf_series_name: htf_series.to_numpy()}
    )
    merged = pd.merge_asof(
        left.reset_index(drop=True).sort_values("ltf_ts"),
        right.sort_values("htf_ts"),
        left_on="ltf_ts",
        right_on="htf_ts",
        direction="backward",
        allow_exact_matches=False,   # strict: HTF stamp must be BEFORE LTF bar
    )
    merged.index = ltf.index
    return merged[htf_series_name]


def generate_signals(
    h1: pd.DataFrame,
    h4: pd.DataFrame,
    params: FloodTideParams = FloodTideParams(),
    mask: "TradabilityMask | pd.Series | None" = None,
) -> pd.DataFrame:
    """Compute flood_tide_h1 signals on the closed-bar (enter-next-open) convention.

    Parameters
    ----------
    h1 : pd.DataFrame
        H1 OHLC(V) with tz-aware UTC ``DatetimeIndex``. Columns: open, high,
        low, close (volume optional).
    h4 : pd.DataFrame
        H4 OHLC(V) with tz-aware UTC ``DatetimeIndex``. Same schema.
    params : FloodTideParams
        Frozen params. Default matches seq=31.
    mask : TradabilityMask | pd.Series | None
        Optional tradability mask. ``None`` (the default) is the seq=31 path,
        byte for byte — T9a's mask-off parity depends on that and asserts it.
        When supplied, the Donchian channels become ``masked_rolling`` WINDOW
        indicators per R3, so a channel whose lookback spans an untradable bar
        is NaN rather than a level partly built from prices nobody could trade.
        The H4 EMA and the Efficiency Ratio are deliberately left alone: the
        EMA is an ACCUMULATOR whose state must advance across the gap, and ER
        is computed on the H4 series, not the masked H1 one. Signals therefore
        change only where a Donchian window was contaminated — which is what
        makes T9a's signal-set channel attributable to a named flag.

    Returns
    -------
    pd.DataFrame indexed to ``h1`` with:
        upper_entry      : prior-``entry_len`` Donchian high (breakout level)
        lower_entry      : prior-``entry_len`` Donchian low
        lower_exit       : prior-``exit_len``  Donchian low (trail-exit level)
        lower_stop       : prior-``stop_len``  Donchian low (initial-stop level)
        htf_ema          : H4 EMA(``htf_ema_len``), backward-merged, no look-ahead
        er               : efficiency ratio over ``er_len`` bars
        htf_ok           : bool — close[t] > htf_ema[t]
        er_ok            : bool — er[t] > er_threshold
        regime_ok        : bool — htf_ok & er_ok   (the null universe)
        breakout_long    : bool — close[t] > upper_entry[t] (raw entry signal)
        candidate_entry  : bool — breakout_long & regime_ok (pre-cooldown)
        entry_signal     : bool — candidate_entry after reentry-cooldown dedup
    """
    _validate_ohlcv(h1, "h1")
    _validate_ohlcv(h4, "h4")

    close = h1["close"]
    high = h1["high"]
    low = h1["low"]

    # ---- Donchian channels — PRIOR-bar values (shift(1) excludes current) ----
    if mask is None:
        upper_entry = high.rolling(params.entry_len, min_periods=params.entry_len).max().shift(1)
        lower_entry = low.rolling(params.entry_len, min_periods=params.entry_len).min().shift(1)
        lower_exit = low.rolling(params.exit_len, min_periods=params.exit_len).min().shift(1)
        lower_stop = low.rolling(params.stop_len, min_periods=params.stop_len).min().shift(1)
    else:
        # R3: a Donchian channel is a WINDOW indicator, so a window spanning an
        # untradable bar is contaminated and reports NaN rather than a level
        # built partly out of prices nobody could have traded at. The shift(1)
        # is applied after, exactly as above, so the only difference between
        # the two branches is which windows survive.
        _w = _WINDOW
        upper_entry = masked_rolling(high, mask, params.entry_len, max, _w).shift(1)
        lower_entry = masked_rolling(low, mask, params.entry_len, min, _w).shift(1)
        lower_exit = masked_rolling(low, mask, params.exit_len, min, _w).shift(1)
        lower_stop = masked_rolling(low, mask, params.stop_len, min, _w).shift(1)

    # ---- H4 EMA(200), merged onto H1 without look-ahead ----------------------
    htf_ema_h4 = h4["close"].ewm(span=params.htf_ema_len, adjust=False).mean()
    htf_ema = merge_htf_to_ltf(h1, htf_ema_h4, "htf_ema")

    # ---- Efficiency Ratio over er_len closes ending at t ---------------------
    er = efficiency_ratio(close, params.er_len)

    # ---- Gates (all evaluated on the current closed bar t) -------------------
    htf_ok = close > htf_ema
    er_ok = er > params.er_threshold
    regime_ok = htf_ok & er_ok

    breakout_long = close > upper_entry
    candidate_entry = breakout_long & regime_ok

    entry_signal = _apply_reentry_cooldown(
        candidate_entry.fillna(False).to_numpy(),
        params.reentry_cooldown_bars,
    )

    return pd.DataFrame(
        {
            "upper_entry": upper_entry,
            "lower_entry": lower_entry,
            "lower_exit": lower_exit,
            "lower_stop": lower_stop,
            "htf_ema": htf_ema,
            "er": er,
            "htf_ok": htf_ok.fillna(False),
            "er_ok": er_ok.fillna(False),
            "regime_ok": regime_ok.fillna(False),
            "breakout_long": breakout_long.fillna(False),
            "candidate_entry": candidate_entry.fillna(False),
            "entry_signal": pd.Series(entry_signal, index=h1.index),
        },
        index=h1.index,
    )


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _apply_reentry_cooldown(candidate: np.ndarray, cooldown_bars: int) -> np.ndarray:
    """Suppress breakouts that fire within ``cooldown_bars`` of an accepted entry.

    Causal / sequential: an entry accepted at bar ``t`` blocks candidates at
    ``t+1 .. t+cooldown_bars``; the next candidate at ``> t+cooldown_bars`` is
    accepted. Depends only on prior accepted entries, so it is look-ahead free.
    """
    out = np.zeros_like(candidate, dtype=bool)
    last_entry = -(cooldown_bars + 1)
    for t in np.flatnonzero(candidate):
        if t - last_entry > cooldown_bars:
            out[t] = True
            last_entry = t
    return out


def _validate_ohlcv(df: pd.DataFrame, name: str) -> None:
    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{name} missing columns: {sorted(missing)}")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(f"{name} index must be DatetimeIndex")
    if df.index.tz is None:
        raise ValueError(f"{name} index must be tz-aware (UTC expected)")
    if not df.index.is_monotonic_increasing:
        raise ValueError(f"{name} index must be sorted ascending")
