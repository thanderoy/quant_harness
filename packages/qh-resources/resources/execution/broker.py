"""T12 — the broker port.

`resources` defines the interface; Phase 1 ships :class:`SimulatedBroker`
against it and Phase 3 adapts the live ``MT5APIClient`` to the same port. The
point of the port is that the execution-assumption matrix becomes a set of
*configurations of one simulator* rather than a set of parallel simulation
code paths, each of which would drift from the others at its own rate.

The four configurations
-----------------------

===================== ==================================================
``IDEAL``             Signal bar close, exact price
``NEXT_OPEN``         Next bar open, exact price
``NEXT_OPEN_SPREAD``  Next bar open plus the registry median spread
``REALISTIC``         Next bar open plus 95th-percentile spread plus
                      latency-adverse slip
===================== ==================================================

They are ordered by adversity, but **the ordering is only monotone from
``NEXT_OPEN`` onwards**. ``IDEAL`` is not "the best case": it is a different
*timing*, and an overnight gap can hand it a worse price than ``NEXT_OPEN``
gets. Only the last three share a timing and differ purely by cost, so only
they can be asserted to decline. Asserting a four-way monotone frontier looks
tighter and is simply false on gapping instruments.

Spread convention
-----------------

Bars are treated as **mid**. A buy fills at ``mid + spread/2``, a sell at
``mid - spread/2``, because the measured D3 spread is a full bid-ask width
and charging it whole to each side would double the real cost. This is
stated because it differs from ``backtesting.py``'s ``spread`` parameter,
which is a fraction of price applied whole; the two must not be conflated,
and :mod:`research.engines.btpy_runner` converts between them in one place.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from resources.side import Side

__all__ = [
    "Bar",
    "Broker",
    "Fill",
    "FillConfig",
    "FRONTIER",
    "OrderRequest",
]


class FillConfig(str, Enum):
    """One execution assumption. See the module docstring for the matrix."""

    IDEAL = "ideal"
    NEXT_OPEN = "next_open"
    NEXT_OPEN_SPREAD = "next_open_spread"
    REALISTIC = "realistic"

    @property
    def fills_on_signal_bar(self) -> bool:
        """True when the fill happens on the bar that generated the signal.

        Only ``IDEAL`` does. Every other configuration waits for the next
        bar's open, which is the earliest price a decision taken on a closed
        bar could actually have been transacted at.
        """
        return self is FillConfig.IDEAL

    @property
    def charges_spread(self) -> bool:
        return self in (FillConfig.NEXT_OPEN_SPREAD, FillConfig.REALISTIC)

    @property
    def charges_slip(self) -> bool:
        return self is FillConfig.REALISTIC


#: All four, in adversity order. X23 requires that no backtest artifact is
#: written with fewer than all of these recorded, so the tuple is the
#: authority on what "all four" means rather than a literal repeated at each
#: call site.
FRONTIER: tuple[FillConfig, ...] = (
    FillConfig.IDEAL,
    FillConfig.NEXT_OPEN,
    FillConfig.NEXT_OPEN_SPREAD,
    FillConfig.REALISTIC,
)


@dataclass(frozen=True)
class Bar:
    """One OHLC bar. No volume: nothing in the fill model consults it."""

    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class OrderRequest:
    """An instruction to transact, in the vocabulary the port speaks.

    ``volume`` is in lots and is only carried through to the fill so a
    caller can cost it; no fill-price decision depends on it. Size-dependent
    market impact is deliberately not modelled — nothing in this repo has
    measured it, and a fabricated impact curve would make the ``REALISTIC``
    leg look rigorous while being invented.
    """

    symbol: str
    side: Side
    volume: float

    def __post_init__(self) -> None:
        if not (self.volume > 0):
            raise ValueError(
                f"volume must be > 0, got {self.volume!r}; a zero-volume "
                "order is a refusal and should not reach the broker")


@dataclass(frozen=True)
class Fill:
    """What the order actually transacted at, and what made it that price.

    ``spread_cost`` and ``slip_cost`` are kept separate from ``price`` so a
    result can be attributed rather than merely reported: a mechanism that
    dies between ``NEXT_OPEN_SPREAD`` and ``REALISTIC`` died of slip, and
    that is worth being able to read off the artifact.
    """

    config: FillConfig
    symbol: str
    side: Side
    volume: float
    price: float
    reference_price: float
    spread_cost: float
    slip_cost: float

    @property
    def total_adverse_cost(self) -> float:
        """Per-unit adverse cost, always >= 0."""
        return self.spread_cost + self.slip_cost


@runtime_checkable
class Broker(Protocol):
    """The port. ``SimulatedBroker`` implements it now, MT5 in Phase 3."""

    @property
    def config(self) -> FillConfig:
        ...

    def fill(self, order: OrderRequest, signal_bar: Bar,
             next_bar: Bar | None) -> Fill:
        """Price ``order``, given the bar that signalled and the one after.

        ``next_bar`` is ``None`` at the end of the series. Every
        configuration but ``IDEAL`` must refuse rather than fall back to the
        signal bar's close, because falling back silently converts the last
        signal of every run into a look-ahead-free-looking fill at a price
        that was never available.
        """
        ...
