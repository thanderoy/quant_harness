"""Three-parameter regime monitor for XAUUSD.

A *descriptive* read of market state — not a signal and not a gate. It answers
three questions that are otherwise easy to conflate:

    trend_quality  (ER)          is price moving directionally, or churning?
    vol_regime     (ATR ratio)   is vol expanding or compressing?
    trend_location (bias)        which side are we on, and how stretched?

All three are bounded or ATR-normalised, so they are comparable across price
levels, volatility regimes and years — which raw ADX/ATR readings are not.
ER in particular is the intended replacement for ADX, which this repo has
documented as unreliable on XAU.

The primitives are *reused*, not reimplemented, so the numbers here agree
bit-for-bit with the signal-edge and live-strategy layers:

- :func:`research.pre.signals.flood_tide.efficiency_ratio`
- :func:`research.pre.signal_edge.wilder_atr` (mirrors ``strategies/indicators.atr``)

PITFALL (no look-ahead): every column at bar ``t`` is a function of bars
``[0, t]`` only. Both upstream primitives guarantee this and are tested for it;
``regime_frame`` adds no forward-looking transform. Consumers evaluating a live
signal must still read ``.iloc[-2]`` (last *closed* bar), per house convention.

Usage
-----
>>> from research.pre.regime import regime_frame, latest_regime
>>> rf = regime_frame(h1)
>>> latest_regime(h1)
RegimeSnapshot(trend_quality=0.31, vol_regime=0.88, trend_location=1.42, ...)
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import pandas as pd

from research.pre.signal_edge import wilder_atr
from research.pre.signals.flood_tide import efficiency_ratio

__all__ = [
    "RegimeParams",
    "RegimeSnapshot",
    "regime_frame",
    "latest_regime",
    "ER_LEN",
    "ATR_FAST",
    "ATR_SLOW",
    "SMA_LEN",
]

# Defaults per the monitoring spec. Module-level so they are citable from a
# hypothesis registration without re-deriving them from a call site.
ER_LEN = 20        # Kaufman ER lookback (H1)
ATR_FAST = 14      # short-window ATR — same period as the house sizing ATR
ATR_SLOW = 100     # long-window ATR — the vol baseline
SMA_LEN = 200      # trend anchor for directional bias

# Interpretation cutoffs. Descriptive labels only — NOT trade filters. They
# exist so a snapshot prints something a human can read at a glance.
#
# Calibrated against XAUUSD H1, 2004-06-11 -> 2025-12-31 (124,688 scored bars).
# Percentile of each cutoff in that sample is given so the labels stay honest:
# a cutoff that fires most of the time is not a label, it is noise.
ER_TRENDING = 0.30       # p65  — >= this = directional path
ER_CHURNING = 0.15       # p36  — <= this = chop
VOL_EXPANDING = 1.10     # p76  — >= this = expanding
VOL_COMPRESSING = 0.90   # p31  — <= this = compressing
# On H1 the SMA(200) anchor is ~8 days away while ATR(14) spans ~14 hours, so
# |bias| is naturally large: its median is 4.25 ATR and 75% of bars exceed 2.0.
# An earlier 2.0 cutoff labelled 74.9% of history "stretched". p90 = 9.53.
BIAS_STRETCHED = 9.5     # p90  — |bias| >= this = genuinely extended


@dataclass(frozen=True)
class RegimeParams:
    """Windows for the three regime parameters."""
    er_len: int = ER_LEN
    atr_fast: int = ATR_FAST
    atr_slow: int = ATR_SLOW
    sma_len: int = SMA_LEN


@dataclass(frozen=True)
class RegimeSnapshot:
    """One bar's regime read, with human-readable labels."""
    timestamp: pd.Timestamp
    close: float
    trend_quality: float      # ER, bounded [0, 1]
    vol_regime: float         # ATR(fast) / ATR(slow), >0, 1.0 = neutral
    trend_location: float     # (close - SMA) / ATR(fast), signed ATR units
    trend_label: str
    vol_label: str
    bias_label: str

    def as_dict(self) -> dict:
        d = asdict(self)
        d["timestamp"] = self.timestamp.isoformat()
        return d


def _trend_label(er: float) -> str:
    if er >= ER_TRENDING:
        return "trending"
    if er <= ER_CHURNING:
        return "churning"
    return "mixed"


def _vol_label(ratio: float) -> str:
    if ratio >= VOL_EXPANDING:
        return "expanding"
    if ratio <= VOL_COMPRESSING:
        return "compressing"
    return "neutral"


def _bias_label(bias: float) -> str:
    side = "above" if bias >= 0 else "below"
    if abs(bias) >= BIAS_STRETCHED:
        return f"stretched {side}"
    return f"{side} anchor"


def regime_frame(
    ohlc: pd.DataFrame,
    params: RegimeParams = RegimeParams(),
) -> pd.DataFrame:
    """Compute the three regime parameters for every bar.

    Parameters
    ----------
    ohlc : pd.DataFrame
        OHLC with a tz-aware UTC ``DatetimeIndex``, sorted ascending. Requires
        ``high``, ``low``, ``close``.

    Returns
    -------
    pd.DataFrame
        Indexed like ``ohlc``, with columns ``close``, ``trend_quality``,
        ``vol_regime``, ``trend_location``, plus the intermediate ``atr_fast``,
        ``atr_slow`` and ``sma`` for auditability. Leading bars are NaN until
        the longest window (``max(atr_slow, sma_len)``) has filled.
    """
    missing = {"high", "low", "close"} - set(ohlc.columns)
    if missing:
        raise ValueError(f"ohlc missing required columns: {sorted(missing)}")
    if not ohlc.index.is_monotonic_increasing:
        raise ValueError("ohlc index must be sorted ascending")

    close = ohlc["close"].astype(float)
    atr_fast = wilder_atr(ohlc["high"], ohlc["low"], close, params.atr_fast)
    atr_slow = wilder_atr(ohlc["high"], ohlc["low"], close, params.atr_slow)
    sma = close.rolling(params.sma_len, min_periods=params.sma_len).mean()

    out = pd.DataFrame(index=ohlc.index)
    out["close"] = close
    out["trend_quality"] = efficiency_ratio(close, params.er_len)
    out["vol_regime"] = atr_fast / atr_slow
    out["trend_location"] = (close - sma) / atr_fast
    out["atr_fast"] = atr_fast
    out["atr_slow"] = atr_slow
    out["sma"] = sma

    # efficiency_ratio fills its warmup with 0.0; that is a real ER value and
    # would read as "churning" rather than "unknown". Blank it so the warmup is
    # unambiguously NaN across all three parameters.
    out.loc[out.index[: params.er_len], "trend_quality"] = float("nan")
    return out


def latest_regime(
    ohlc: pd.DataFrame,
    params: RegimeParams = RegimeParams(),
    closed_bar: bool = True,
) -> RegimeSnapshot:
    """Regime read for the most recent bar.

    ``closed_bar=True`` (default) reads ``.iloc[-2]``, the last *closed* bar,
    per the house no-look-ahead convention. Pass ``False`` only for display of
    the currently-forming bar.
    """
    rf = regime_frame(ohlc, params)
    row = rf.iloc[-2] if closed_bar else rf.iloc[-1]
    if row[["trend_quality", "vol_regime", "trend_location"]].isna().any():
        raise ValueError(
            f"insufficient history: need > {max(params.atr_slow, params.sma_len)} "
            f"bars past warmup, got {len(rf)}"
        )
    return RegimeSnapshot(
        timestamp=row.name,
        close=float(row["close"]),
        trend_quality=float(row["trend_quality"]),
        vol_regime=float(row["vol_regime"]),
        trend_location=float(row["trend_location"]),
        trend_label=_trend_label(float(row["trend_quality"])),
        vol_label=_vol_label(float(row["vol_regime"])),
        bias_label=_bias_label(float(row["trend_location"])),
    )
