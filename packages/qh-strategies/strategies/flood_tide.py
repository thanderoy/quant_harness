"""flood_tide — Donchian breakout with a higher-timeframe trend gate.

The mechanism registered at ``research/log`` seq=31 and shelved at seq=34
after two iterations. It is here for one reason: acceptance criterion 5 needs
*a* strategy module to run unmodified against every instrument in the
registry, and the phase's non-goals forbid inventing one. Nothing about
porting it revives it — the verdict stands, no trial is registered, and no
per-instrument result produced through this module is evidence of anything.
See :mod:`strategies.tests.test_symbol_agnostic` for why the acceptance test
deliberately asserts structure and never reports a Sharpe.

What changed in the port, and why
---------------------------------
The research implementation (``research/pre/signals/flood_tide.py``) is a
pure signal generator: OHLCV in, boolean columns out, no position state. This
is a strategy: it holds a position and manages it. Three differences follow,
and none of them is cosmetic.

1. **The H4 series is resampled from H1 rather than loaded separately.** A
   strategy that required a second timeframe frame per instrument would need
   eight more files to satisfy criterion 5. Resampling is the honest
   alternative, but it is not free: the H4 bar boundary depends on the
   broker's server day, not on UTC midnight. ``htf_offset`` exists so that is
   a stated parameter rather than an assumption, and it defaults to UTC —
   which is *not* what Pepperstone's H4 grid uses (UTC+3). Parity with seq=31
   is therefore not claimed by this module and is not tested here; T9a owns
   the parity path and reads the original signal generator untouched.

2. **The re-entry cooldown survives, and needs state.** In the research
   script the cooldown deduplicated overlapping breakout signals in a
   frame with no notion of being in a trade. Here, holding a position already
   suppresses re-entry, so the cooldown only bites after an exit. It is kept
   anyway: it is a frozen registered parameter, and dropping a parameter
   because the surrounding code changed is precisely the drift the log
   exists to catch. The state is reset in :meth:`prepare`, which ``run()``
   calls first, so a strategy instance reused across runs cannot leak a
   cooldown from one into the next.

3. **Stops are evaluated on closed bars, not intrabar.** An exit fires when a
   *closed* bar's close breaches the working stop, and is filled at the next
   open. The real thing would be touched intrabar at a worse price. That gap
   is a fill assumption and belongs to ``SimulatedBroker`` (T12); modelling it
   here would create a second, quieter execution model beside the one the
   broker port exists to be.

Long-only, as registered.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .base import (
    HOLD,
    ClosedBars,
    EntryIntent,
    ManagementIntent,
    Position,
    Side,
)

__all__ = ["FloodTideParams", "FloodTide", "efficiency_ratio"]


@dataclass(frozen=True)
class FloodTideParams:
    """Frozen at registration (seq=31). Mirrors the research module's defaults."""

    entry_len: int = 55
    exit_len: int = 20
    stop_len: int = 10
    htf_ema_len: int = 200
    er_len: int = 14
    er_threshold: float = 0.30
    reentry_cooldown_bars: int = 5

    #: Bars of the base timeframe per higher-timeframe bar (H1 -> H4 = 4).
    htf_multiple: int = 4
    #: Offset of the higher-timeframe grid from UTC midnight. Left at zero by
    #: default and stated rather than assumed — see the module docstring.
    htf_offset_hours: int = 0


def efficiency_ratio(close: pd.Series, length: int) -> pd.Series:
    """Kaufman Efficiency Ratio over ``length`` bars, bounded [0, 1].

    Ported unchanged from ``research/pre/signals/flood_tide.py``. Uses only
    closes up to and including bar ``t``.
    """
    net_change = (close - close.shift(length)).abs()
    path_length = close.diff().abs().rolling(length, min_periods=length).sum()
    er = net_change / path_length.replace(0, np.nan)
    return er.fillna(0.0)


class FloodTide:
    """Donchian-``entry_len`` breakout, gated by an HTF EMA and an ER floor.

    Instrument-neutral: every parameter is a bar count or a dimensionless
    ratio. The one price-dimensioned quantity it emits is a stop *distance*,
    which is what :func:`resources.risk.sizer.size_position` consumes.
    """

    name = "flood_tide"

    def __init__(self, params: FloodTideParams | None = None) -> None:
        self.params = params or FloodTideParams()
        self._last_entry_index: int | None = None

    @property
    def warmup_bars(self) -> int:
        """Enough base bars for the slowest input to be defined.

        The HTF EMA is the binding constraint: ``htf_ema_len`` higher-timeframe
        bars is ``htf_ema_len * htf_multiple`` base bars, and an EMA is only
        approximately converged at its span, so this is a floor rather than a
        guarantee. Set generously — starving an indicator produces zero trades
        that read as a result (seq=67).
        """
        p = self.params
        return max(
            p.entry_len,
            p.exit_len,
            p.stop_len,
            p.er_len,
            p.htf_ema_len * p.htf_multiple,
        ) + 1

    # -- features ----------------------------------------------------------

    def prepare(self, bars: pd.DataFrame) -> pd.DataFrame:
        """Causal features for the whole series. Resets per-run state."""
        self._last_entry_index = None
        _validate(bars)
        p = self.params

        close, high, low = bars["close"], bars["high"], bars["low"]

        # Donchian levels use the PRIOR entry_len bars: .shift(1) excludes the
        # bar being tested, mirroring Pine's ta.highest(high, N)[1].
        upper_entry = high.rolling(p.entry_len, min_periods=p.entry_len).max().shift(1)
        lower_exit = low.rolling(p.exit_len, min_periods=p.exit_len).min().shift(1)
        lower_stop = low.rolling(p.stop_len, min_periods=p.stop_len).min().shift(1)

        htf_ema = self._htf_ema(close)
        er = efficiency_ratio(close, p.er_len)

        regime_ok = (close > htf_ema) & (er > p.er_threshold)
        breakout = close > upper_entry

        return pd.DataFrame(
            {
                "close": close,
                "upper_entry": upper_entry,
                "lower_exit": lower_exit,
                "lower_stop": lower_stop,
                "htf_ema": htf_ema,
                "er": er,
                "regime_ok": regime_ok.fillna(False),
                "breakout": breakout.fillna(False),
                "candidate": (breakout & regime_ok).fillna(False),
            },
            index=bars.index,
        )

    def _htf_ema(self, close: pd.Series) -> pd.Series:
        """EMA of the resampled higher-timeframe close, merged back without
        look-ahead.

        The merge is strict-backward: the value carried onto base bar ``t`` is
        the last HTF value whose stamp is *strictly earlier* than ``t``, so a
        base bar inside a still-forming HTF candle sees only the prior closed
        one. ``allow_exact_matches=False`` is what enforces that, and removing
        it would leak the forming HTF bar into every decision inside it.
        """
        p = self.params
        rule = f"{p.htf_multiple}h"
        offset = pd.Timedelta(hours=p.htf_offset_hours)

        htf_close = close.resample(rule, label="left", closed="left",
                                   origin="epoch", offset=offset).last().dropna()
        if htf_close.empty:
            return pd.Series(np.nan, index=close.index)

        ema = htf_close.ewm(span=p.htf_ema_len, adjust=False).mean()

        # The HTF bar stamped at its OPEN is only known at its close, so the
        # stamp is advanced by one HTF period before merging. Merging on the
        # open stamp would make the whole HTF bar visible from its first
        # minute — a four-bar look-ahead that no test of the base series
        # would ever show.
        available_at = ema.index + pd.Timedelta(hours=p.htf_multiple)

        merged = pd.merge_asof(
            pd.DataFrame({"ts": close.index}),
            pd.DataFrame({"htf_ts": available_at,
                          "htf_ema": ema.to_numpy()}),
            left_on="ts",
            right_on="htf_ts",
            direction="backward",
            allow_exact_matches=True,
        )
        merged.index = close.index
        return merged["htf_ema"]

    # -- decisions ---------------------------------------------------------

    def evaluate_entry(self, closed: ClosedBars) -> EntryIntent | None:
        """Long on a confirmed breakout in a permitted regime, after cooldown."""
        if not closed.value("candidate"):
            return None

        i = len(closed)   # the bar about to form; the entry would fill at its open
        if self._last_entry_index is not None:
            if i - self._last_entry_index <= self.params.reentry_cooldown_bars:
                return None

        close = closed.value("close")
        stop_level = closed.value("lower_stop")
        stop_distance = close - stop_level
        if not np.isfinite(stop_distance) or stop_distance <= 0:
            # A Donchian low at or above the close means the channel has not
            # yet separated. Refusing is correct: there is no stop to size
            # against, and substituting a floor here would invent risk the
            # mechanism never expressed.
            return None

        self._last_entry_index = i
        return EntryIntent(side=Side.LONG, stop_distance=stop_distance,
                           tag="breakout")

    def manage_position(self, closed: ClosedBars,
                        position: Position) -> ManagementIntent:
        """Trail the stop to the Donchian exit low; close on a breach."""
        close = closed.value("close")
        if np.isfinite(close) and close <= position.stop_price:
            return ManagementIntent(close_fraction=1.0, tag="stop")

        trail = closed.value("lower_exit")
        if np.isfinite(trail) and trail > position.stop_price:
            # Ratchet only. A stop that can move down is not a stop.
            return ManagementIntent(stop_price=trail, tag="trail")

        return HOLD


def _validate(bars: pd.DataFrame) -> None:
    required = {"open", "high", "low", "close"}
    missing = required - set(bars.columns)
    if missing:
        raise ValueError(f"bars missing columns: {sorted(missing)}")
    if not isinstance(bars.index, pd.DatetimeIndex):
        raise ValueError("bars index must be a DatetimeIndex")
    if bars.index.tz is None:
        raise ValueError("bars index must be tz-aware (UTC expected)")
    if not bars.index.is_monotonic_increasing:
        raise ValueError("bars index must be sorted ascending")
