"""Cost uncertainty is a declared scenario, not a hidden multiplier.

The model carried commission = 7.00 after it had been measured at 0.00 across
358 live deals, justified as conservatism. That put a known-false value where
a reader sees a documented constant, with the reasoning in a README rather
than in the code returning the number — the same defect class as a seeded
Sharpe, differing only in pointing somewhere safe.

The fix keeps the conservatism and loses the deception: measured values are
the model's, conservative values are a scenario you ask for by name, and every
computed cost says which produced it.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from research.datasets.cost_model import (
    CONSERVATIVE_COMMISSION_PER_LOT_RT,
    MEASURED_COMMISSION_PER_LOT_RT,
    CostScenario,
    PepperstoneXAUUSDCostModel,
)

TRADE = dict(lots=0.10, direction="BUY",
             entry_dt=datetime(2024, 5, 6, 12, 0),
             exit_dt=datetime(2024, 5, 11, 12, 0))


def test_the_default_model_is_the_measured_one():
    """What the account actually pays is the default, not the stress case."""
    m = PepperstoneXAUUSDCostModel()
    assert m.scenario is CostScenario.MEASURED
    assert m.commission_per_lot_round_turn == MEASURED_COMMISSION_PER_LOT_RT == 0.0


def test_the_measured_commission_is_zero_because_it_was_measured():
    """358 deals, five symbols, fourteen months, every one at 0.00 (seq=105)."""
    m = PepperstoneXAUUSDCostModel.for_scenario(CostScenario.MEASURED)
    assert m.commission_round_turn_usd(1.0) == 0.0


def test_conservative_is_available_by_name():
    m = PepperstoneXAUUSDCostModel.for_scenario("conservative")
    assert m.commission_per_lot_round_turn == CONSERVATIVE_COMMISSION_PER_LOT_RT
    assert m.commission_round_turn_usd(1.0) == 7.0


def test_conservative_really_is_more_expensive():
    """A stress scenario that does not stress is decoration."""
    cheap = PepperstoneXAUUSDCostModel.for_scenario("measured").trade_cost(**TRADE)
    dear = PepperstoneXAUUSDCostModel.for_scenario("conservative").trade_cost(**TRADE)
    assert dear.spread_usd > cheap.spread_usd
    assert dear.commission_usd > cheap.commission_usd


def test_every_breakdown_says_which_scenario_produced_it():
    """The property that makes changing the default safe: nothing is silently
    re-priced when each figure carries its assumptions."""
    for name in ("measured", "conservative"):
        b = PepperstoneXAUUSDCostModel.for_scenario(name).trade_cost(**TRADE)
        assert b.scenario == name


def test_an_unknown_scenario_is_refused():
    with pytest.raises(ValueError):
        PepperstoneXAUUSDCostModel.for_scenario("optimistic")


def test_the_two_scenarios_are_reportable_side_by_side():
    """The point of an axis rather than a constant."""
    rows = {n: PepperstoneXAUUSDCostModel.for_scenario(n).trade_cost(**TRADE)
            for n in ("measured", "conservative")}
    assert {r.scenario for r in rows.values()} == {"measured", "conservative"}
