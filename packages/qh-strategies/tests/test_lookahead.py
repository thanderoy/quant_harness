"""X5 — Chan truncation. X6 — the forming bar is not readable.

Both are parametrised over every strategy in the package, so a strategy added
later inherits them by existing rather than by someone remembering.

These are the two tests that decide whether anything downstream means
anything. A look-ahead of one bar is enough to turn a dead mechanism into a
Sharpe of 1.5, and it is invisible in a result — it shows up only as a
backtest that never reproduces live. Every number this repo has produced sits
on top of them holding.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from strategies import all_strategies, run

from synthetic import make_bars

STRATEGIES = all_strategies()
IDS = [s.name for s in STRATEGIES]

pytestmark = [pytest.mark.x("X5"), pytest.mark.x("X6")]


@pytest.fixture(params=STRATEGIES, ids=IDS)
def strategy(request):
    """A fresh instance per test: FloodTide carries cooldown state between
    bars, and a shared instance would let one test's tail leak into the next."""
    return type(request.param)()


@pytest.mark.x("X5")
@pytest.mark.parametrize("truncate", [1, 5, 50, 300])
def test_truncating_the_tail_reproduces_the_surviving_prefix(strategy, truncate):
    """The Chan test.

    If a decision at bar ``t`` depended on anything after ``t``, removing the
    tail would change it. Run against several truncation depths because a
    one-bar leak and a 300-bar leak are different bugs: the first is an
    off-by-one in a shift, the second is an indicator fitted on the full
    series.
    """
    bars = make_bars(2500)
    full = run(strategy, bars)
    short = run(type(strategy)(), bars.iloc[:-truncate])

    prefix = full.iloc[:len(short)]
    pd.testing.assert_series_equal(
        short["target_risk"], prefix["target_risk"], check_names=False)
    pd.testing.assert_series_equal(
        short["stop_price"], prefix["stop_price"], check_names=False)
    pd.testing.assert_series_equal(
        short["entered"], prefix["entered"], check_names=False)


@pytest.mark.x("X5")
def test_the_truncation_guard_would_catch_a_full_sample_fit(strategy):
    """The guard must be able to fail.

    The planted leak is the one truncation is built to find: a threshold
    fitted on the whole series. Removing the tail moves the fitted value, so
    every decision downstream of it moves too.
    """
    bars = make_bars(2500)

    class Leaky(type(strategy)):
        def prepare(self, frame: pd.DataFrame) -> pd.DataFrame:
            out = super().prepare(frame)
            # A level that could only be known after seeing every bar.
            out["candidate"] = out["close"] > out["close"].max() * 0.98
            return out

    full = run(Leaky(), bars)
    short = run(Leaky(), bars.iloc[:-300])
    prefix = full.iloc[:len(short)]

    assert not short["target_risk"].equals(prefix["target_risk"]), (
        "a full-sample-fitted threshold did not change the truncated run — "
        "the X5 assertion is not testing what it claims")


@pytest.mark.x("X5")
@pytest.mark.x("X6")
def test_truncation_alone_would_miss_a_one_bar_leak(strategy):
    """Why both tests exist, pinned rather than assumed.

    A one-bar forward shift changes only the decision at the *last* bar of any
    given run, so truncation reproduces the prefix and X5 passes. It is X6 —
    corrupting the forming bar — that sees it. Neither test is sufficient
    alone, and finding this out from a failing backtest rather than from here
    would cost considerably more.
    """
    bars = make_bars(2500)

    class Leaky(type(strategy)):
        def prepare(self, frame: pd.DataFrame) -> pd.DataFrame:
            out = super().prepare(frame)
            out["candidate"] = out["candidate"].shift(-1).bfill().astype(bool)
            return out

    full = run(Leaky(), bars)
    short = run(Leaky(), bars.iloc[:-300])
    assert short["target_risk"].equals(full["target_risk"].iloc[:len(short)]), (
        "expected truncation to be blind to a one-bar leak; if this now "
        "fails, X5 has become stronger and this note is stale")

    corrupted = bars.copy()
    last = corrupted.index[-1]
    corrupted.loc[last, "close"] = corrupted["close"].iloc[-1] * 10.0
    corrupted.loc[last, "high"] = corrupted["high"].iloc[-1] * 10.0
    assert not run(Leaky(), corrupted)["target_risk"].equals(
        run(Leaky(), bars)["target_risk"]), (
        "X6 did not see a one-bar leak either — nothing in this file is "
        "testing for look-ahead")


@pytest.mark.x("X6")
def test_corrupting_the_forming_bar_changes_nothing(strategy):
    """Signal generation never reads the bar still forming.

    ``high``, ``low`` and ``close`` of the final bar are replaced with
    nonsense. ``open`` is deliberately left alone: the open of bar ``i`` *is*
    known at the moment an order decided at bar ``i-1`` fills, so a fill price
    that moves with it is execution, not look-ahead. Corrupting it too would
    make this test fail for a correct implementation — the same conflation
    that made the original ``iloc[-2]`` rule necessary to write down.
    """
    bars = make_bars(2500)
    clean = run(strategy, bars)

    corrupted = bars.copy()
    last = corrupted.index[-1]
    corrupted.loc[last, "close"] = corrupted["close"].iloc[-1] * 10.0
    corrupted.loc[last, "high"] = corrupted["high"].iloc[-1] * 10.0
    corrupted.loc[last, "low"] = corrupted["low"].iloc[-1] / 10.0

    dirty = run(type(strategy)(), corrupted)

    pd.testing.assert_frame_equal(dirty, clean)


@pytest.mark.x("X6")
def test_the_closed_bar_view_refuses_the_forming_bar(strategy):
    """Structural, not behavioural: there is no accessor for bar ``i``.

    The discipline is enforced by the shape of what a strategy is handed, so
    a strategy cannot reach the forming bar even by mistake. This pins that
    the view stays that shape.
    """
    from strategies.base import ClosedBars

    features = strategy.prepare(make_bars(600))
    columns = {c: features[c].to_numpy() for c in features.columns}
    closed = ClosedBars(columns, features.index, 400)

    assert len(closed) == 400
    assert closed.timestamp == features.index[399]
    assert closed.value("close") == pytest.approx(
        float(features["close"].iloc[399]))
    assert closed.value("close", 1) == pytest.approx(
        float(features["close"].iloc[398]))

    # No index, no slice, no positional access beyond the boundary.
    assert not hasattr(closed, "__getitem__")
    with pytest.raises(ValueError):
        closed.value("close", -1)
    assert closed.frame().index[-1] == features.index[399]


@pytest.mark.x("X6")
def test_prepare_must_not_reindex(strategy):
    """A dropna in prepare() shifts every subsequent decision silently.

    Cheap to write, and it catches the one refactor most likely to introduce
    an off-by-many: "the warm-up rows are NaN, let's drop them".
    """
    bars = make_bars(800)

    class Dropping(type(strategy)):
        def prepare(self, frame: pd.DataFrame) -> pd.DataFrame:
            return super().prepare(frame).dropna()

    with pytest.raises(ValueError, match="rows|index"):
        run(Dropping(), bars)


@pytest.mark.x("X5")
def test_a_strategy_instance_does_not_leak_state_between_runs(strategy):
    """Reusing one instance must give the same answer as a fresh one.

    FloodTide keeps a cooldown index across bars. If ``prepare()`` failed to
    reset it, a second run would start mid-cooldown and X5 would fail
    intermittently, in a way that looks like a look-ahead and is not.
    """
    bars = make_bars(2000)
    first = run(strategy, bars)
    second = run(strategy, bars)
    pd.testing.assert_frame_equal(first, second)
    pd.testing.assert_frame_equal(first, run(type(strategy)(), bars))


def test_the_fixture_actually_trades(strategy):
    """A look-ahead test over a series that produced no positions proves
    nothing. This is the denominator check for everything above."""
    out = run(strategy, make_bars(2500))
    assert out["entered"].sum() > 0, (
        f"{strategy.name} took no entries on the fixture — X5 and X6 would "
        "pass vacuously")
    assert np.isfinite(out["stop_price"]).any()
