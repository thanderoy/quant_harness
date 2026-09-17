"""T12 — the broker port and the four-configuration fill frontier.

The frontier's job is to make an execution assumption falsifiable. Most of
what is asserted here is therefore about *refusal*: the cases where the
simulator must decline to produce a number rather than produce a flattering
one. A fill model that always returns a price cannot fail, and a frontier
whose adverse legs quietly collapse onto its optimistic ones will report
every mechanism as cost-surviving.
"""

from __future__ import annotations

import pytest

from resources.execution import (
    FRONTIER,
    Bar,
    Broker,
    FillConfig,
    OrderRequest,
    SimulatedBroker,
    SlipModel,
    UnmeasuredSpread,
    load_spreads,
)
from resources.instruments.registry import Registry
from resources.side import Side

pytestmark = [pytest.mark.x("X23")]

MEASURED = "XAUUSD"
UNMEASURED = "EURUSD"

#: Deliberately gapping: the next bar opens well above the signal close, so
#: IDEAL gets a better long fill than any next-open configuration.
SIGNAL = Bar(open=2000.0, high=2010.0, low=1995.0, close=2005.0)
NEXT = Bar(open=2006.0, high=2012.0, low=2000.0, close=2008.0)


@pytest.fixture(scope="module")
def specs():
    return Registry.load("pepperstone_live_20260906.json").specs


@pytest.fixture(scope="module")
def spreads():
    return load_spreads()


def broker(config, specs, **kw):
    return SimulatedBroker(config, specs=specs, **kw)


def order(side=Side.LONG, symbol=MEASURED):
    return OrderRequest(symbol, side, 0.01)


def test_the_frontier_is_every_configuration_there_is():
    """X23 relies on FRONTIER meaning "all four". If a fifth configuration
    is ever added to the enum without being added here, every completeness
    check in the repo would keep passing while silently no longer covering
    it."""
    assert set(FRONTIER) == set(FillConfig)
    assert len(FRONTIER) == 4


def test_the_simulated_broker_satisfies_the_port(specs):
    assert isinstance(broker(FillConfig.NEXT_OPEN, specs), Broker)


@pytest.mark.parametrize("side", [Side.LONG, Side.SHORT])
def test_every_cost_moves_the_fill_against_the_order(side, specs):
    """Costs are magnitudes; the side supplies the sign. A cost that could
    arrive negative would improve a fill, which is the one direction a
    spread model must never be able to move."""
    for config in FRONTIER:
        fill = broker(config, specs).fill(order(side), SIGNAL, NEXT)
        assert fill.spread_cost >= 0.0
        assert fill.slip_cost >= 0.0
        adverse = (fill.price - fill.reference_price) * side.sign
        assert adverse == pytest.approx(fill.total_adverse_cost)
        assert adverse >= 0.0


@pytest.mark.parametrize("side", [Side.LONG, Side.SHORT])
def test_the_three_next_open_legs_get_monotonically_worse(side, specs):
    """Only the last three share a timing, so only they can be ordered."""
    ordered = [FillConfig.NEXT_OPEN, FillConfig.NEXT_OPEN_SPREAD,
               FillConfig.REALISTIC]
    costs = [broker(c, specs).fill(order(side), SIGNAL, NEXT).total_adverse_cost
             for c in ordered]
    assert costs == sorted(costs)
    assert costs[0] == 0.0
    assert costs[-1] > costs[1] > costs[0]


def test_ideal_is_a_different_timing_and_not_merely_the_best_case(specs):
    """The frontier is not four-way monotone, and pretending otherwise is a
    real risk: on a gapping instrument IDEAL can be *worse* than NEXT_OPEN.
    This fixture gaps up, so a long fills better at the signal close."""
    ideal = broker(FillConfig.IDEAL, specs).fill(order(Side.LONG), SIGNAL, NEXT)
    next_open = broker(FillConfig.NEXT_OPEN, specs).fill(
        order(Side.LONG), SIGNAL, NEXT)
    assert ideal.total_adverse_cost == next_open.total_adverse_cost == 0.0
    # Same zero cost, materially different price. Cost ordering is not price
    # ordering, and the gap is why.
    assert ideal.price < next_open.price


@pytest.mark.parametrize(
    "config", [c for c in FRONTIER if not c.fills_on_signal_bar])
def test_a_missing_next_bar_is_refused_not_filled_at_the_close(config, specs):
    """The end of the series is where a silent fallback would hide: it would
    fill the final signal of every run at a price that never traded."""
    with pytest.raises(ValueError, match="no next bar"):
        broker(config, specs).fill(order(), SIGNAL, None)


def test_ideal_needs_no_next_bar(specs):
    fill = broker(FillConfig.IDEAL, specs).fill(order(), SIGNAL, None)
    assert fill.price == SIGNAL.close


def test_the_spread_charged_is_half_the_measured_width(spreads, specs):
    stats = spreads[MEASURED]
    median_leg = broker(FillConfig.NEXT_OPEN_SPREAD, specs).fill(
        order(), SIGNAL, NEXT)
    realistic = broker(FillConfig.REALISTIC, specs).fill(order(), SIGNAL, NEXT)
    assert median_leg.spread_cost == pytest.approx(stats.median / 2.0)
    assert realistic.spread_cost == pytest.approx(stats.p95 / 2.0)


def test_slip_is_one_tick_of_the_instrument_not_one_unit_of_price(specs):
    """A slip constant in price units is a gold-shaped constant, the same
    mistake the sizer's LOT_SAFETY_FLOOR_ATR was."""
    fill = broker(FillConfig.REALISTIC, specs).fill(order(), SIGNAL, NEXT)
    assert fill.slip_cost == pytest.approx(specs[MEASURED].tick_size)
    assert fill.slip_cost != pytest.approx(1.0)


def test_an_unmeasured_symbol_is_refused_rather_than_charged_zero(specs):
    """The failure this prevents: REALISTIC silently collapsing onto
    NEXT_OPEN on a symbol D3b never sampled, so the mechanism appears to
    survive a cost it was never charged."""
    assert UNMEASURED not in load_spreads()
    for config in (FillConfig.NEXT_OPEN_SPREAD, FillConfig.REALISTIC):
        with pytest.raises(UnmeasuredSpread, match="no measured spread"):
            broker(config, specs).fill(order(symbol=UNMEASURED), SIGNAL, NEXT)


def test_the_costless_legs_still_run_on_an_unmeasured_symbol(specs):
    """IDEAL and NEXT_OPEN charge nothing, so they must stay available on a
    symbol with no spread measurement — otherwise adding an instrument would
    block the whole frontier rather than two legs of it."""
    for config in (FillConfig.IDEAL, FillConfig.NEXT_OPEN):
        fill = broker(config, specs).fill(order(symbol=UNMEASURED), SIGNAL, NEXT)
        assert fill.total_adverse_cost == 0.0


def test_slip_without_an_instrument_spec_is_refused(spreads):
    with pytest.raises(KeyError, match="no InstrumentSpec|slip"):
        SimulatedBroker(FillConfig.REALISTIC, spreads=spreads, specs={}).fill(
            order(), SIGNAL, NEXT)


def test_zero_slip_needs_no_spec(spreads):
    """A deliberately slip-free REALISTIC run is a legitimate sensitivity
    check and must not require registry plumbing it will not consult."""
    fill = SimulatedBroker(FillConfig.REALISTIC, spreads=spreads, specs={},
                           slip=SlipModel(ticks=0.0)).fill(order(), SIGNAL, NEXT)
    assert fill.slip_cost == 0.0


def test_the_slip_model_admits_it_is_not_measured():
    assert SlipModel().provenance == "HAND_ENTERED"


def test_the_spread_snapshot_records_which_terminal_answered(spreads):
    """Spread is broker policy, not a property of the instrument."""
    assert spreads.provenance == "MEASURED"
    assert "Pepperstone" in spreads.broker
    assert spreads.source_artifact.startswith("d3b_")


def test_a_zero_volume_order_never_reaches_the_broker():
    """The sizer's refusal is lots=0; that is a decision not to trade, and
    it must not arrive here as an order worth pricing."""
    with pytest.raises(ValueError, match="refusal"):
        OrderRequest(MEASURED, Side.LONG, 0.0)


def test_side_is_one_enum_shared_with_strategies():
    """T12 moved Side down into resources. Two enums with equal values but
    different identity compare unequal, which surfaces as a position that
    silently never closes."""
    strategies = pytest.importorskip("strategies")
    assert strategies.Side is Side
