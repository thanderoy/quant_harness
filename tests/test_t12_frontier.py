"""X23 — no backtest artifact is written under a single fill assumption.

The gate is placed at construction rather than at serialisation, so the
tests here are mostly about what the code *refuses* to do. The failure mode
being prevented is not a crash: it is a perfectly well-formed artifact
recording one flattering execution assumption, which reads on the page
exactly like one that survived costs.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from research.engines.btpy_runner import BtRunResult, _fill_parameters
from research.engines.frontier import (
    FAILED,
    NO_EDGE,
    SURVIVES,
    FillFrontier,
    IncompleteFrontier,
    write_backtest_artifact,
)
from research.datasets.cost_model import PepperstoneXAUUSDCostModel
from resources.execution import FRONTIER, FillConfig, SlipModel

pytestmark = [pytest.mark.x("X23")]


def result(sharpe: float) -> BtRunResult:
    empty = pd.DataFrame()
    r = BtRunResult(
        strategy_name="Fake", start=pd.Timestamp("2024-01-01"),
        end=pd.Timestamp("2024-02-01"), n_bars=100, n_trades=10,
        stats={}, trades=empty, equity_curve=empty,
        return_pct_series=pd.Series(dtype=float))
    r.sharpe = sharpe
    return r


def frontier(**sharpes) -> FillFrontier:
    default = {c: result(1.0) for c in FRONTIER}
    for name, value in sharpes.items():
        default[FillConfig[name.upper()]] = result(value)
    return FillFrontier("Fake", "XAUUSD", default, cost_to_atr=0.03)


@pytest.mark.parametrize("dropped", list(FRONTIER))
def test_a_frontier_missing_any_configuration_cannot_be_built(dropped):
    partial = {c: result(1.0) for c in FRONTIER if c is not dropped}
    with pytest.raises(IncompleteFrontier, match="requires all four"):
        FillFrontier("Fake", "XAUUSD", partial)


def test_an_artifact_cannot_be_written_from_a_single_result(tmp_path):
    with pytest.raises(IncompleteFrontier, match="must be written from"):
        write_backtest_artifact(tmp_path / "a.json", result(1.0))


def test_a_written_artifact_records_all_four_configurations(tmp_path):
    path = write_backtest_artifact(tmp_path / "a.json", frontier())
    record = json.loads(path.read_text())
    assert set(record["fill_frontier"]) == {c.value for c in FRONTIER}
    for leg in record["fill_frontier"].values():
        assert "sharpe" in leg and "n_trades" in leg


def test_the_artifact_names_the_spread_snapshot_it_was_costed_with(tmp_path):
    """A cost figure with no provenance cannot be re-checked later, and the
    spread snapshot is broker-specific."""
    record = json.loads(
        write_backtest_artifact(tmp_path / "a.json", frontier()).read_text())
    assert record["spread_provenance"] == "MEASURED"
    assert record["spread_snapshot"].startswith("d3b_")
    assert "Pepperstone" in record["broker"]
    assert record["cost_to_atr"] == 0.03


def test_an_edge_that_dies_before_realistic_is_reported_failed():
    """The spec's wording, made mechanical: failed, not conditional. There
    is no verdict here that means "works with tight execution"."""
    assert frontier(realistic=-0.2).verdict == FAILED
    assert frontier(next_open_spread=-0.1, realistic=-0.4).verdict == FAILED


def test_a_mechanism_with_no_edge_even_optimistically_is_named_separately():
    """Distinguished from FAILED because the two call for different next
    steps: one is an execution problem, the other was never a signal."""
    assert frontier(next_open=-0.5, realistic=-0.9).verdict == NO_EDGE


def test_surviving_requires_the_realistic_leg_not_the_optimistic_one():
    assert frontier().verdict == SURVIVES
    assert frontier(realistic=0.01).verdict == SURVIVES


def test_the_legacy_fill_path_is_untouched_by_t12():
    """Every Sharpe already in the research log was produced with
    ``fill_config=None``. If this changes, those numbers silently stop
    meaning what they meant when they were recorded."""
    cost_model = PepperstoneXAUUSDCostModel()
    trade_on_close, spread = _fill_parameters(
        None, cost_model, "XAUUSD", 2400.0, SlipModel())
    assert trade_on_close is False
    assert spread == cost_model.spread_usd_per_oz / 2400.0


def test_only_ideal_fills_on_the_signal_bar():
    cost_model = PepperstoneXAUUSDCostModel()
    for config in FRONTIER:
        trade_on_close, _ = _fill_parameters(
            config, cost_model, "XAUUSD", 2400.0, SlipModel())
        assert trade_on_close is (config is FillConfig.IDEAL)


def test_the_engine_is_charged_half_the_measured_width_not_the_whole_one():
    """The port treats bars as mid; backtesting.py's spread is applied
    whole. Conflating the two doubles the modelled cost."""
    from resources.execution import load_spreads
    stats = load_spreads()["XAUUSD"]
    cost_model = PepperstoneXAUUSDCostModel()
    _, spread = _fill_parameters(FillConfig.NEXT_OPEN_SPREAD, cost_model,
                                 "XAUUSD", 2400.0, SlipModel())
    assert spread == pytest.approx((stats.median / 2.0) / 2400.0)


def test_the_costless_legs_are_charged_nothing():
    cost_model = PepperstoneXAUUSDCostModel()
    for config in (FillConfig.IDEAL, FillConfig.NEXT_OPEN):
        _, spread = _fill_parameters(config, cost_model, "XAUUSD", 2400.0,
                                     SlipModel())
        assert spread == 0.0
