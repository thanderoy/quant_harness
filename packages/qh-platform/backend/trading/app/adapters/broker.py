"""`MT5Broker` — the live venue behind the `resources` broker port.

Phase 3 step 5. `resources.execution.broker` defines the port and
`SimulatedBroker` implements its four simulated configurations; this class is
the ``LIVE`` one, sending through the existing ``MT5APIClient``.

Two methods, for two callers:

- ``submit(order)`` is the single place an ``OrderRequest`` becomes an
  ``order/send`` request. It returns the venue's response dict unchanged, so
  a strategy's retcode handling and ``create_trade_record`` call are exactly
  what they were. The strategies use this.
- ``fill(order, signal_bar)`` is the port method. It submits, and turns an
  accepted order into a ``Fill``; a rejected one raises ``OrderRejected``
  carrying the response, because a ``Fill`` with no price would be a lie.

Whether the mapping changed anything is not asserted here but measured:
``tests/test_order_replay.py`` replays every live strategy's order path
against a baseline captured from the pre-port code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from resources.execution.broker import Bar, Fill, FillConfig, OrderRequest
from resources.side import Side

from app.adapters.mt5_api import MT5APIClient

#: Max price deviation in points for a market order. 20 is what every live
#: strategy passed before the port; it is execution policy, not a property of
#: the order, which is why it is the broker's and not OrderRequest's.
DEFAULT_DEVIATION = 20

_ACTION = {Side.LONG: "BUY", Side.SHORT: "SELL"}
_SIDE = {v: k for k, v in _ACTION.items()}


def side_from_action(action: str) -> Side:
    """``"BUY"``/``"SELL"`` (any case) to a ``Side``; anything else raises.

    Strategies speak in actions. The old client raised ``ValueError`` on any
    other value inside ``send_order``; this raises the same error at the
    same point in a strategy's ``try``, so a bad signal is still caught and
    logged where it always was.
    """
    try:
        return _SIDE[action.upper()]
    except (KeyError, AttributeError):
        raise ValueError("action must be BUY or SELL") from None


class OrderRejected(RuntimeError):
    """The venue did not fill the order. ``response`` is what it said."""

    def __init__(self, response: Optional[dict[str, Any]]) -> None:
        self.response = response
        r = response or {}
        super().__init__(
            f"order rejected: retcode={r.get('retcode', 'no response')} "
            f"{r.get('retcode_description', '')}".rstrip())


@dataclass(frozen=True)
class LiveFill(Fill):
    """A ``Fill`` plus what only a venue knows.

    Costs are attributed against the decision price, the signal bar's close.
    A single real fill cannot separate spread from slip from drift between
    decision and execution, so the whole adverse move is reported as
    ``slip_cost`` and ``spread_cost`` is 0. A favourable fill reports 0
    rather than a negative cost, which the port's contract forbids; the
    signed difference is ``price - reference_price``.
    """

    ticket: Optional[int] = None
    response: dict[str, Any] = field(default_factory=dict)


class MT5Broker:
    """The ``LIVE`` implementation of ``resources.execution.broker.Broker``."""

    def __init__(self, client: MT5APIClient,
                 deviation: int = DEFAULT_DEVIATION) -> None:
        self.client = client
        self.deviation = deviation

    @property
    def config(self) -> FillConfig:
        return FillConfig.LIVE

    def submit(self, order: OrderRequest) -> dict[str, Any]:
        """Send ``order`` as a market order; return the venue's response."""
        return self.client.send_order(
            action=_ACTION[order.side],
            symbol=order.symbol,
            volume=order.volume,
            order_type="MARKET",
            sl=order.sl,
            tp=order.tp,
            deviation=self.deviation,
            magic=order.magic,
            comment=order.comment,
        )

    def fill(self, order: OrderRequest, signal_bar: Bar,
             next_bar: Bar | None = None) -> LiveFill:
        """Transact ``order`` now and report the fill.

        ``next_bar`` must be ``None``. Passing one means a backtest is
        driving the live broker, and the right response is to stop, not to
        send a real order on historical data.
        """
        if next_bar is not None:
            raise ValueError(
                "MT5Broker fills live; a next_bar means this is being driven "
                "by historical data, and a live order must not be sent for it")
        response = self.submit(order)
        if not (response and response.get("success") is True):
            raise OrderRejected(response)

        price = float(response.get("price", 0.0))
        reference = signal_bar.close
        adverse = (price - reference) * order.side.sign
        ticket = (response.get("ticket") or response.get("order")
                  or response.get("deal"))
        return LiveFill(
            config=FillConfig.LIVE, symbol=order.symbol, side=order.side,
            volume=order.volume, price=price, reference_price=reference,
            spread_cost=0.0, slip_cost=max(0.0, adverse),
            ticket=int(ticket) if ticket is not None else None,
            response=dict(response),
        )
