"""T2 — tradability mask, and the R3 rolling rule.

A bar being present in a dataframe is not the same as it having been tradable.
Weekend gaps, holidays, the rollover window and spread blowouts all produce
bars that exist in the file but could never have been acted on. Computing an
indicator across them silently mixes untradable state into a signal, and the
result looks entirely normal.

Two pieces:

``TradabilityMask``
    A boolean Series aligned to the bar index, True where tradable, plus a
    per-reason breakdown so a False can be *attributed*. Attribution matters:
    "3% of bars are masked" is not actionable, whereas "3% of bars are masked
    and all of them are the rollover window" is.

``masked_rolling``
    The R3 ruling, mechanised. Window indicators NaN out any bar whose window
    spans a masked bar; accumulator indicators skip masked bars while keeping
    the calendar index. Every indicator declares its class at definition time —
    there is no default and no per-call override, because a wrong default here
    is invisible and an override is where the wrong choice would live.

**Expected to change existing XAUUSD indicator values across weekend gaps.**
That divergence is a bug fix, not a regression, and must be quantified in the
T9 parity report rather than suppressed.
"""

from __future__ import annotations

from enum import Enum
from typing import Callable

import numpy as np
import pandas as pd


class MaskReason(str, Enum):
    """Why a bar is not tradable. Flagged independently so a False can be
    attributed to a cause rather than merely counted."""

    SESSION_CLOSED = "session_closed"
    WEEKEND_GAP = "weekend_gap"
    HOLIDAY = "holiday"
    ROLLOVER_WINDOW = "rollover_window"
    SPREAD_ABOVE_THRESHOLD = "spread_above_threshold"
    INSUFFICIENT_TICKS = "insufficient_ticks"
    SPEC_CHANGE_BOUNDARY = "spec_change_boundary"


class IndicatorClass(str, Enum):
    """How an indicator must treat masked bars (R3).

    WINDOW
        Reads a fixed lookback. If any bar in that window is untradable the
        output is contaminated, so it is NaN. Examples: SMA, WMA, HMA,
        Stochastic, rolling quantiles.

    ACCUMULATOR
        Carries recursive state. Skipping a masked bar is correct — the state
        simply does not advance — and NaN-ing would destroy the accumulator for
        every subsequent bar, which is strictly worse than the contamination it
        was meant to prevent. Examples: Wilder ATR/RMA, EMA.

    There is deliberately no default. An indicator that does not declare its
    class fails to register (X25).
    """

    WINDOW = "window"
    ACCUMULATOR = "accumulator"


class UndeclaredIndicatorClass(ValueError):
    """An indicator was used without declaring WINDOW or ACCUMULATOR."""


class TradabilityMask:
    """Boolean tradability per bar, with attributable reasons.

    ``mask[i]`` is True when the bar was tradable. Reasons are additive: a bar
    may be untradable for several reasons at once, and each is retained rather
    than collapsed to the first one found.
    """

    def __init__(self, index: pd.DatetimeIndex) -> None:
        if not isinstance(index, pd.DatetimeIndex):
            raise TypeError("TradabilityMask requires a DatetimeIndex")
        if index.tz is None:
            raise ValueError(
                "index must be timezone-aware — a naive index silently assumes "
                "a timezone, and every session boundary here depends on it"
            )
        self.index = index
        self._reasons: dict[MaskReason, pd.Series] = {}

    # -- construction ------------------------------------------------------

    def flag(self, reason: MaskReason, condition: pd.Series) -> "TradabilityMask":
        """Mark bars where ``condition`` is True as untradable for ``reason``."""
        cond = condition.reindex(self.index, fill_value=False).astype(bool)
        if reason in self._reasons:
            cond = self._reasons[reason] | cond
        self._reasons[reason] = cond
        return self

    def flag_weekend_gap(self, max_gap_hours: float = 40.0) -> "TradabilityMask":
        """Flag the first bar after a gap longer than ``max_gap_hours``.

        The bar *after* the gap is the untradable one — it is the bar whose
        preceding state is stale. The bar before the gap was tradable when it
        printed.
        """
        deltas = self.index.to_series().diff()
        hours = deltas.dt.total_seconds() / 3600.0
        return self.flag(MaskReason.WEEKEND_GAP, (hours > max_gap_hours).fillna(False))

    def flag_rollover(self, utc_hour: int = 21, minutes: int = 15) -> "TradabilityMask":
        """Flag the daily rollover window, where spreads widen sharply."""
        mins = (self.index.hour - utc_hour) * 60 + self.index.minute
        within = (np.abs(mins) <= minutes) | (np.abs(mins + 1440) <= minutes)
        return self.flag(MaskReason.ROLLOVER_WINDOW,
                         pd.Series(within, index=self.index))

    def flag_spread(self, spread: pd.Series, threshold: float) -> "TradabilityMask":
        return self.flag(MaskReason.SPREAD_ABOVE_THRESHOLD, spread > threshold)

    # -- access ------------------------------------------------------------

    @property
    def tradable(self) -> pd.Series:
        """True where the bar is tradable for every declared reason."""
        out = pd.Series(True, index=self.index)
        for cond in self._reasons.values():
            out &= ~cond
        return out

    def reason(self, reason: MaskReason) -> pd.Series:
        return self._reasons.get(
            reason, pd.Series(False, index=self.index))

    def attribution(self) -> dict[str, int]:
        """Masked-bar count per reason.

        Counts overlap by construction; a bar untradable for two reasons
        appears in both. Summing these will exceed ``n_masked`` and that is
        correct — collapsing to a single 'primary' reason would invent a
        precedence nobody specified.
        """
        return {r.value: int(c.sum()) for r, c in sorted(
            self._reasons.items(), key=lambda kv: kv[0].value)}

    def summary(self) -> dict:
        t = self.tradable
        return {
            "n_bars": int(len(t)),
            "n_tradable": int(t.sum()),
            "n_masked": int((~t).sum()),
            "masked_pct": float((~t).mean() * 100.0),
            "attribution": self.attribution(),
            "attribution_note": "counts overlap; a bar may have several reasons",
        }


def masked_rolling(
    series: pd.Series,
    mask: pd.Series | TradabilityMask,
    window: int,
    fn: Callable[[pd.Series], float],
    indicator_class: IndicatorClass | None = None,
) -> pd.Series:
    """Apply ``fn`` over ``window`` bars, honouring the R3 mask rule.

    ``indicator_class`` is required. Passing None raises rather than assuming a
    default: the two behaviours differ precisely where it matters, and a silent
    default would make the wrong one the common case.

    WINDOW
        Output is NaN for any bar whose lookback window contains a masked bar.
        The window is contaminated, so the value is not reported.

    ACCUMULATOR
        Masked bars are dropped before applying ``fn``, and the result is
        reindexed onto the original calendar. State advances across the gap
        rather than being destroyed by it.
    """
    if indicator_class is None:
        raise UndeclaredIndicatorClass(
            "masked_rolling requires indicator_class=WINDOW or ACCUMULATOR. "
            "There is no default: the two differ exactly where it matters, and "
            "a default would make the wrong one silent."
        )
    tradable = mask.tradable if isinstance(mask, TradabilityMask) else mask
    tradable = tradable.reindex(series.index, fill_value=False).astype(bool)

    if indicator_class is IndicatorClass.WINDOW:
        raw = series.rolling(window).apply(fn, raw=False)
        # A window is contaminated if it contains any masked bar. Counting
        # masked bars in the same window is exactly a rolling sum.
        contaminated = (~tradable).rolling(window).sum() > 0
        return raw.where(~contaminated)

    compacted = series[tradable]
    rolled = compacted.rolling(window).apply(fn, raw=False)
    return rolled.reindex(series.index)
