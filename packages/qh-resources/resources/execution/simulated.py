"""`SimulatedBroker` — one simulator, four configurations.

Every execution assumption in the repo is a configuration of this class. The
alternative, which this exists to prevent, is one bespoke fill path per
experiment: they start identical, diverge as each is patched locally, and by
the time two results disagree nobody can say whether the mechanism or the
fill model was responsible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

from resources.execution.broker import (
    Bar,
    Fill,
    FillConfig,
    OrderRequest,
)
from resources.execution.spreads import SpreadSnapshot, load_spreads
from resources.instruments.registry import InstrumentSpec

__all__ = ["SimulatedBroker", "SlipModel"]


@dataclass(frozen=True)
class SlipModel:
    """Latency-adverse slip, in ticks.

    ``HAND_ENTERED`` is not a placeholder to be tidied away — it is the
    honest provenance. Nothing in this repo has measured the latency between
    a Celery beat tick firing and a Pepperstone fill, so one tick is a
    stated guess, and it is stamped as one so that a ``REALISTIC`` result
    cannot be read as if the slip were sourced.

    It used to share that status with the $7.00/lot commission. It no longer
    does: at seq=101 the commission value was sourced to Pepperstone's own
    MT5 Razor schedule and raised to ``BROKER_PUBLISHED``, leaving slip the
    last cost input with no source at all. Slip is also the harder of the
    two, because no published document can supply it — a schedule states a
    commission, but slip is a property of this account's latency to this
    broker, and only a real fill measures it. Until one does, a ``REALISTIC``
    fill is sourced on its spread and its commission, and guessed on its slip.
    """

    ticks: float = 1.0
    provenance: str = "HAND_ENTERED"

    def __post_init__(self) -> None:
        if self.ticks < 0:
            raise ValueError(f"slip ticks must be >= 0, got {self.ticks!r}")


@dataclass
class SimulatedBroker:
    """Prices an order under one :class:`FillConfig`.

    ``spreads`` and ``specs`` are only consulted by the configurations that
    need them, so an ``IDEAL`` or ``NEXT_OPEN`` broker can be constructed
    with neither — which matters, because those two legs must stay runnable
    on a symbol D3b never sampled.
    """

    config: FillConfig
    spreads: Optional[SpreadSnapshot] = None
    specs: Mapping[str, InstrumentSpec] = field(default_factory=dict)
    slip: SlipModel = field(default_factory=SlipModel)

    def __post_init__(self) -> None:
        if self.config.charges_spread and self.spreads is None:
            self.spreads = load_spreads()

    def fill(self, order: OrderRequest, signal_bar: Bar,
             next_bar: Bar | None) -> Fill:
        reference = self._reference_price(order, signal_bar, next_bar)
        spread_cost = self._spread_cost(order)
        slip_cost = self._slip_cost(order)
        # Adverse by construction: a buy pays up, a sell is paid down. The
        # sign comes from the side, never from the cost, so a cost can never
        # arrive as a negative number and quietly improve a fill.
        price = reference + order.side.sign * (spread_cost + slip_cost)
        return Fill(
            config=self.config,
            symbol=order.symbol,
            side=order.side,
            volume=order.volume,
            price=price,
            reference_price=reference,
            spread_cost=spread_cost,
            slip_cost=slip_cost,
        )

    def _reference_price(self, order: OrderRequest, signal_bar: Bar,
                         next_bar: Bar | None) -> float:
        if self.config.fills_on_signal_bar:
            return signal_bar.close
        if next_bar is None:
            raise ValueError(
                f"{self.config.value} fills at the next bar's open, and "
                f"there is no next bar after the signal for {order.symbol}. "
                "Falling back to the signal bar's close would turn the last "
                "signal of every run into a fill at a price that was never "
                "available, so this refuses.")
        return next_bar.open

    def _spread_cost(self, order: OrderRequest) -> float:
        if not self.config.charges_spread:
            return 0.0
        assert self.spreads is not None  # established in __post_init__
        stats = self.spreads[order.symbol]
        full = stats.p95 if self.config is FillConfig.REALISTIC else stats.median
        # Half per side: the measurement is a full bid-ask width, and a round
        # trip crosses it once, not twice.
        return full / 2.0

    def _slip_cost(self, order: OrderRequest) -> float:
        if not self.config.charges_slip or self.slip.ticks == 0:
            return 0.0
        try:
            spec = self.specs[order.symbol]
        except KeyError:
            raise KeyError(
                f"{self.config.value} charges slip in ticks and no "
                f"InstrumentSpec was supplied for {order.symbol!r}; slip "
                "cannot be converted to price units. Pass specs= from the "
                "registry.") from None
        return self.slip.ticks * spec.tick_size
