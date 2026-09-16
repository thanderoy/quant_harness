"""X30 — entry evaluation and position management are separately addressable.

The failure this prevents is specific and has a name in this project: a
strategy is retired, its ``evaluate()`` stops being called, and the trailing
stop it also drove stops with it, leaving a live position unmanaged on a
broker that does not know the strategy is gone. Nothing warns. The position
sits there until it hits a hard stop nobody set, or does not.

So the split is tested at the seam, not asserted in a docstring: disabling
entries must leave management running, and an open position must still be
trailed and still exit.

The rest of this module pins the runner's contract — the risk-unit boundary,
the one-bar lag, and the refusals — because every strategy inherits them.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategies import (
    HOLD,
    ClosedBars,
    EntryIntent,
    ManagementIntent,
    Position,
    Side,
    run,
)

from synthetic import make_bars

pytestmark = [pytest.mark.x("X30")]


class AlwaysEnter:
    """Enters on the first bar it is offered and trails a fixed distance."""

    name = "always_enter"
    warmup_bars = 2

    def __init__(self, trail: float = 1.0) -> None:
        self.trail = trail
        self.entry_calls = 0
        self.manage_calls = 0

    def prepare(self, bars: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({"close": bars["close"]}, index=bars.index)

    def evaluate_entry(self, closed: ClosedBars) -> EntryIntent | None:
        self.entry_calls += 1
        return EntryIntent(side=Side.LONG, stop_distance=5.0, tag="in")

    def manage_position(self, closed: ClosedBars,
                        position: Position) -> ManagementIntent:
        self.manage_calls += 1
        close = closed.value("close")
        if close <= position.stop_price:
            return ManagementIntent(close_fraction=1.0, tag="stop")
        trailed = close - self.trail
        if trailed > position.stop_price:
            return ManagementIntent(stop_price=trailed, tag="trail")
        return HOLD


@pytest.fixture
def bars() -> pd.DataFrame:
    return make_bars(400, seed=3)


def _seed_position(bars: pd.DataFrame) -> Position:
    entry = float(bars["close"].iloc[1])
    return Position(side=Side.LONG, entry_index=2, entry_price=entry,
                    stop_price=entry - 5.0, risk_fraction=1.0)


def test_disabling_entries_still_manages_an_open_position(bars):
    """The X30 property itself."""
    strategy = AlwaysEnter()
    out = run(strategy, bars, entries_enabled=False,
              initial_position=_seed_position(bars))

    assert strategy.entry_calls == 0, "entries were disabled but still evaluated"
    assert strategy.manage_calls > 0, "management stopped with entries"
    assert not out["entered"].any()

    held = out["stop_price"].dropna()
    assert len(held) > 0, "the seeded position was never held"
    assert (held.diff().dropna() >= -1e-12).all(), (
        "the trailing stop moved down; a stop that can retreat is not a stop")


def test_disabling_entries_does_not_prevent_the_exit(bars):
    """Management must be able to *finish* — a position that can be trailed
    but never closed is only half-managed."""
    strategy = AlwaysEnter(trail=0.05)
    out = run(strategy, bars, entries_enabled=False,
              initial_position=_seed_position(bars))

    assert out["exited"].any(), (
        "the seeded position never exited with entries disabled; retiring "
        "this strategy would strand it")
    exit_at = out.index[out["exited"]][0]
    assert out.loc[exit_at:, "target_risk"].eq(0).all(), (
        "risk remained on after the exit")


def test_entries_and_management_are_both_live_by_default(bars):
    strategy = AlwaysEnter()
    out = run(strategy, bars)
    assert strategy.entry_calls > 0 and strategy.manage_calls > 0
    assert out["entered"].any()


def test_no_entry_is_taken_before_warmup(bars):
    strategy = AlwaysEnter()
    strategy.warmup_bars = 100
    out = run(strategy, bars)
    first = out.index[out["entered"]][0]
    assert out.index.get_loc(first) >= 100


def test_the_position_is_held_from_the_bar_after_the_decision(bars):
    """The one-bar lag, stated as a test rather than as a convention."""
    strategy = AlwaysEnter()
    out = run(strategy, bars)
    i = out.index.get_loc(out.index[out["entered"]][0])

    assert out["target_risk"].iloc[i - 1] == 0.0
    assert out["target_risk"].iloc[i] == 1.0
    # Filled at the open of the bar it is first held on.
    assert out["stop_price"].iloc[i] == pytest.approx(
        float(bars["open"].iloc[i]) - 5.0)


def test_partial_close_reduces_risk_without_ending_the_position(bars):
    class Halver(AlwaysEnter):
        def manage_position(self, closed, position):
            if position.bars_held == 3:
                return ManagementIntent(close_fraction=0.5, tag="partial")
            return HOLD

    out = run(Halver(), bars)
    risk = out["target_risk"]
    # Elementwise, not pytest.approx: comparing a Series to approx(0.5)
    # collapses to a single bool and silently passes on nothing.
    assert np.isclose(risk, 0.5).any(), "no partial reduction appeared"
    assert np.isclose(risk, 1.0).any(), "the position was never full-sized"
    assert not out["exited"].any(), "a partial close ended the position"


def test_an_entry_intent_cannot_name_a_lot_or_a_nonpositive_stop():
    """The risk-unit boundary. A strategy that could return lots would need
    to know the instrument, and the whole layering would be decorative."""
    assert not hasattr(EntryIntent, "lots")
    assert "symbol" not in EntryIntent.__dataclass_fields__

    with pytest.raises(ValueError, match="stop_distance"):
        EntryIntent(side=Side.LONG, stop_distance=0.0)
    with pytest.raises(ValueError, match="risk_fraction"):
        EntryIntent(side=Side.LONG, stop_distance=1.0, risk_fraction=1.5)
    with pytest.raises(ValueError, match="close_fraction"):
        ManagementIntent(close_fraction=2.0)


def test_short_positions_carry_the_sign(bars):
    class Shorting(AlwaysEnter):
        def evaluate_entry(self, closed):
            return EntryIntent(side=Side.SHORT, stop_distance=5.0)

        def manage_position(self, closed, position):
            return HOLD

    out = run(Shorting(), bars)
    i = out.index.get_loc(out.index[out["entered"]][0])
    assert out["target_risk"].iloc[i] == -1.0
    assert out["stop_price"].iloc[i] == pytest.approx(
        float(bars["open"].iloc[i]) + 5.0)


def test_misaligned_features_are_refused(bars):
    class Truncating(AlwaysEnter):
        def prepare(self, frame):
            return super().prepare(frame).iloc[10:]

    with pytest.raises(ValueError, match="rows|index"):
        run(Truncating(), bars)


def test_result_covers_every_input_bar(bars):
    out = run(AlwaysEnter(), bars)
    assert out.index.equals(bars.index)
    assert np.isfinite(out["target_risk"]).all()
