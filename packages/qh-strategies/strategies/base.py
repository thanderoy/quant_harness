"""What a strategy is allowed to say, and the loop that listens to it.

Three properties are structural here rather than left to each strategy to
remember, because each of them has already failed somewhere in this project
when it was left to discipline:

**Risk units, never lots.** An :class:`EntryIntent` carries a side, a stop
distance in *price* units, and a multiple of whatever risk budget the caller
is working to. It cannot name a lot size, an account balance, a currency or a
tick — those live in ``resources.risk.sizer``, which is the only place that
knows what an instrument is. This is what lets one module run against nine
instruments: the strategy never learns which one it is looking at.

**The forming bar is not reachable (X6).** :func:`run` hands the strategy a
:class:`ClosedBars` view over everything *strictly before* the forming bar.
``closed.value("close")`` is the last closed bar — ``iloc[-2]`` of the full
frame. The house rule stops being a convention a reviewer has to spot and
becomes a shape the code cannot address around. ``prepare()`` still sees the
whole frame, deliberately: indicators are computed once on the full series to
avoid warm-up starvation (seq=67), and a non-causal indicator smuggled in
there shows up as the corrupted final bar leaking backwards, which is exactly
what X6 tests for.

**Entry and management are separately addressable (X30).** ``run(...,
entries_enabled=False)`` stops new positions being opened and leaves
:meth:`Strategy.manage_position` running on whatever is already open.
Retiring a strategy whose one ``evaluate()`` also drove the trailing stop
would otherwise strand a live position unmanaged — the failure this split
exists to make impossible.

What this loop does *not* model: intrabar fills, spread, slippage and
latency. Decisions are taken on a closed bar and expressed as a target held
from the next bar onward. The four-configuration fill frontier is
``SimulatedBroker``'s job (T12), and pretending to it here would produce a
second, quieter execution model — the thing the broker port exists to
prevent.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import Protocol, runtime_checkable

import pandas as pd

__all__ = [
    "Side",
    "EntryIntent",
    "ManagementIntent",
    "Position",
    "ClosedBars",
    "Strategy",
    "run",
    "HOLD",
]


class Side(Enum):
    LONG = 1
    SHORT = -1

    @property
    def sign(self) -> int:
        return self.value


@dataclass(frozen=True)
class EntryIntent:
    """A strategy's request to open, in units the sizer can price.

    ``stop_distance`` is in price units and must be positive: it is the
    distance from the intended entry to the initial stop, and it is what
    converts a risk budget into a size. ``risk_fraction`` is a multiple of
    that budget — 1.0 means "a full unit", 0.5 means "half". Neither is a lot.
    """

    side: Side
    stop_distance: float
    risk_fraction: float = 1.0
    tag: str = ""

    def __post_init__(self) -> None:
        if not (self.stop_distance > 0):
            raise ValueError(
                f"stop_distance must be > 0, got {self.stop_distance!r}; a "
                "non-positive stop cannot be sized against a risk budget")
        if not (0.0 < self.risk_fraction <= 1.0):
            raise ValueError(
                f"risk_fraction must be in (0, 1], got {self.risk_fraction!r}")


@dataclass(frozen=True)
class ManagementIntent:
    """What to do about an already-open position on this bar.

    ``stop_price`` replaces the working stop when given. ``close_fraction`` is
    the share of the open risk to retire now: 0.0 holds, 1.0 closes.
    """

    stop_price: float | None = None
    close_fraction: float = 0.0
    tag: str = ""

    def __post_init__(self) -> None:
        if not (0.0 <= self.close_fraction <= 1.0):
            raise ValueError(
                f"close_fraction must be in [0, 1], got {self.close_fraction!r}")


#: The common case, named so a strategy says "hold" rather than returning a
#: bare constructor call that reads like an oversight.
HOLD = ManagementIntent()


@dataclass(frozen=True)
class Position:
    """What is open, as the strategy sees it. No lots, no account currency."""

    side: Side
    entry_index: int
    entry_price: float
    stop_price: float
    risk_fraction: float
    bars_held: int = 0

    @property
    def signed_risk(self) -> float:
        return self.side.sign * self.risk_fraction


class ClosedBars:
    """Everything strictly before the forming bar, and nothing else.

    ``value("close")`` is the most recent *closed* bar; ``value("close", 1)``
    the one before it. Backed by the prepared columns as arrays, so a strategy
    reads a scalar rather than slicing a frame on every bar — which matters
    once this loop runs a 100k-bar series against nine instruments.

    There is no accessor for bar ``i``. That is the point: the forming bar is
    not merely discouraged, it is not addressable through this object.
    """

    __slots__ = ("_columns", "_index", "_i")

    def __init__(self, columns: dict[str, object], index: pd.Index, i: int):
        self._columns = columns
        self._index = index
        self._i = i

    def __len__(self) -> int:
        """Number of closed bars available."""
        return self._i

    @property
    def timestamp(self):
        """Timestamp of the last closed bar."""
        return self._index[self._i - 1]

    def value(self, column: str, back: int = 0) -> float:
        """``column`` on the last closed bar, or ``back`` bars before it."""
        if back < 0:
            raise ValueError(f"back must be >= 0, got {back}")
        j = self._i - 1 - back
        if j < 0:
            raise IndexError(
                f"asked for {back} bars before the last closed bar, but only "
                f"{self._i} closed bars exist — raise the strategy's "
                f"warmup_bars rather than reading past the start")
        try:
            col = self._columns[column]
        except KeyError:
            raise KeyError(
                f"{column!r} is not a prepared column; have "
                f"{sorted(self._columns)}") from None
        return float(col[j])

    def frame(self) -> pd.DataFrame:
        """Materialise the closed history as a frame.

        Deliberately the slow path — a strategy that needs it is doing
        something a scalar read cannot express, and the cost should be visible
        at the call site.
        """
        return pd.DataFrame(
            {k: v[:self._i] for k, v in self._columns.items()},
            index=self._index[:self._i])


@runtime_checkable
class Strategy(Protocol):
    """The contract. Instrument-neutral by construction: nothing in these
    signatures carries a symbol, a tick size or a balance."""

    name: str
    warmup_bars: int

    def prepare(self, bars: pd.DataFrame) -> pd.DataFrame:
        """Causal features for the whole series, computed once.

        Must be causal: row ``t`` may depend on rows ``<= t`` only. Computing
        here rather than per-fold is deliberate — slicing first starves an
        indicator whose lookback exceeds the window and produces zero trades
        that read as a result (seq=67).
        """
        ...

    def evaluate_entry(self, closed: ClosedBars) -> EntryIntent | None:
        """Decide from closed bars only. Return None for "no entry"."""
        ...

    def manage_position(self, closed: ClosedBars,
                        position: Position) -> ManagementIntent:
        """Manage an open position from the same closed-bar history."""
        ...


def run(strategy: Strategy, bars: pd.DataFrame, *,
        entries_enabled: bool = True,
        initial_position: Position | None = None) -> pd.DataFrame:
    """Walk ``bars`` and return the target position series, in risk units.

    Row ``i`` of the result is the position *held during* bar ``i``, decided
    from bars ``< i``. That one-bar lag is the whole no-look-ahead claim, and
    it is why truncating the tail of ``bars`` and re-running reproduces the
    surviving prefix exactly (X5).

    Parameters
    ----------
    entries_enabled
        False stops new positions opening; management of an open position
        continues regardless (X30).
    initial_position
        Seed an already-open position, so "retire the strategy while a
        position is live" is expressible and testable.

    Notes
    -----
    A position that closes on bar ``i`` may be replaced on the same bar: both
    fills happen at ``open[i]``, so nothing is being claimed that the data
    cannot support. Whether that is *wanted* is the strategy's call —
    ``flood_tide`` declines it through its re-entry cooldown. A runner that
    forbade it would be quietly imposing a trading rule from the wrong layer.

    Returns
    -------
    DataFrame indexed like ``bars``:
        ``target_risk``   signed risk units held during this bar
        ``stop_price``    the working stop while a position is held, else NaN
        ``entered``       an entry was taken at this bar's open
        ``exited``        the position was closed at this bar's open
        ``tag``           the intent tag that caused the change, else ""
    """
    features = strategy.prepare(bars)
    if len(features) != len(bars):
        raise ValueError(
            f"{strategy.name}.prepare returned {len(features)} rows for "
            f"{len(bars)} bars; features must stay aligned to the input")
    if not features.index.equals(bars.index):
        raise ValueError(
            f"{strategy.name}.prepare returned a different index; a reindex "
            "or a dropna in prepare() silently shifts every decision by the "
            "number of rows it removed")

    columns = {}
    for name in features.columns:
        col = features[name]
        if col.dtype == bool:
            columns[name] = col.to_numpy()
            continue
        try:
            columns[name] = col.to_numpy(dtype="float64",
                                         na_value=float("nan"))
        except (TypeError, ValueError) as exc:
            raise TypeError(
                f"{strategy.name}.prepare column {name!r} is "
                f"{col.dtype}, which cannot be read as a number; features "
                "must be numeric or boolean so a strategy reads a scalar "
                "per bar") from exc

    opens = bars["open"].to_numpy(dtype="float64")

    n = len(bars)
    target = [0.0] * n
    stops: list[float] = [float("nan")] * n
    entered = [False] * n
    exited = [False] * n
    tags = [""] * n

    position = initial_position
    warmup = max(1, int(strategy.warmup_bars))

    for i in range(n):
        if i < warmup:
            continue
        closed = ClosedBars(columns, features.index, i)  # bar i unreachable

        if position is not None:
            intent = strategy.manage_position(closed, position)
            if intent.stop_price is not None:
                position = replace(position, stop_price=intent.stop_price)
            if intent.close_fraction >= 1.0:
                exited[i] = True
                tags[i] = intent.tag
                position = None
            elif intent.close_fraction > 0.0:
                position = replace(
                    position,
                    risk_fraction=position.risk_fraction
                    * (1.0 - intent.close_fraction))
                tags[i] = intent.tag

        if position is None and entries_enabled:
            intent = strategy.evaluate_entry(closed)
            if intent is not None:
                entry_price = float(opens[i])
                stop = entry_price - intent.side.sign * intent.stop_distance
                position = Position(
                    side=intent.side,
                    entry_index=i,
                    entry_price=entry_price,
                    stop_price=stop,
                    risk_fraction=intent.risk_fraction,
                )
                entered[i] = True
                tags[i] = intent.tag

        if position is not None:
            target[i] = position.signed_risk
            stops[i] = position.stop_price
            position = replace(position, bars_held=position.bars_held + 1)

    return pd.DataFrame(
        {
            "target_risk": target,
            "stop_price": stops,
            "entered": entered,
            "exited": exited,
            "tag": tags,
        },
        index=bars.index,
    )
