"""T9b mask-on — every differing trade has a named cause.

Criterion 3's T9b half is a single binary claim, so most of these tests are
about making sure the claim is not satisfied cheaply: that the comparison
actually produced differences, that all three kinds are looked at, and that
the two attribution mechanisms are told apart rather than blurred into one
flag name.

No ``pytest.mark.x`` — criterion 3 has no X id, and X15b is the mask-off
check. See the note in ``test_t9a_mask_on``.

The run needs the OHLC CSVs, which are committed in this repo, so unlike T9a
this runs on CI. It is slow (two simulations per fold per timeframe), hence
the module-scoped fixture.
"""

from __future__ import annotations

import numpy as np
import pytest

from research.parity import t9b_mask_on as m


@pytest.fixture(scope="module")
def report():
    return m.check_mask_on()


# -- the contamination helper, which needs no data -------------------------

def test_a_clean_window_is_not_contaminated():
    tradable = np.ones(10, dtype=bool)
    assert not m._contaminated(tradable, 3).any()


def test_a_masked_bar_contaminates_exactly_its_window():
    tradable = np.ones(10, dtype=bool)
    tradable[4] = False
    bad = m._contaminated(tradable, 3)
    # bar 4 and the two bars whose 3-bar lookback still contains it
    assert list(np.flatnonzero(bad)) == [4, 5, 6]


def test_the_window_reaches_back_not_forward():
    """A lookback is backward-looking. If contamination leaked forward-only or
    both ways, an indicator would be NaN'd on bars that never read the masked
    one — which would look like the mask doing more than it does."""
    tradable = np.ones(10, dtype=bool)
    tradable[4] = False
    bad = m._contaminated(tradable, 3)
    assert not bad[3], "bar 3 precedes the masked bar and cannot read it"


def test_the_hma_span_is_the_composed_one_not_the_period():
    """HMA smooths a WMA with another WMA, so its true reach is longer than
    `period`. Using `period` would call contaminated values clean."""
    class FakeEngine:
        @staticmethod
        def hma(close, period):
            return np.zeros(len(close))

    tradable = np.ones(80, dtype=bool)
    tradable[0] = False
    out = m.masked_hma(FakeEngine, np.zeros(80), 55, tradable)
    span = 55 + round(55 ** 0.5) - 1
    assert np.isnan(out[span - 1]), (
        "the last bar of the composed span must still be contaminated")
    assert not np.isnan(out[span]), "one bar past the span must be clean"


# -- the run ----------------------------------------------------------------

def test_every_differing_trade_is_attributed(report):
    """Criterion 3, T9b half, in one assertion."""
    for t in report.timeframes:
        assert t.unattributed == [], (
            f"{t.timeframe}: {len(t.unattributed)} differing trades have no "
            f"named cause; first few: {t.unattributed[:5]}")
    assert report.fully_attributed


def test_the_comparison_actually_found_differences(report):
    """Guards the previous test against passing vacuously."""
    assert any(t.lost for t in report.timeframes)
    assert any(t.diverged for t in report.timeframes), (
        "no diverged trades at all would mean the ATR accumulator path is not "
        "being exercised, which is where most of the reach is")


def test_all_three_kinds_of_difference_are_separated(report):
    """A trade that survived with a moved exit is not the same event as one
    that vanished, and a count alone would hide it entirely."""
    for t in report.timeframes:
        total = len(t.lost) + len(t.gained) + len(t.diverged)
        assert total > 0
        assert t.n_trades_on != t.n_trades_off or t.diverged


def test_both_mechanisms_are_named_and_distinguished(report):
    """The window and accumulator routes reach differently — one is local, the
    other unbounded — so collapsing them to "weekend_gap" would lose the only
    part that explains a trade hundreds of bars from any masked bar."""
    for t in report.timeframes:
        assert m.WINDOW_CAUSE in t.attribution
        assert m.ACCUMULATOR_CAUSE in t.attribution
        assert t.attribution[m.ACCUMULATOR_CAUSE] > 0, (
            f"{t.timeframe}: nothing attributed to the accumulator shift, but "
            "a Wilder ATR on a compacted series differs from the first masked "
            "bar onward — this should reach a lot of trades")


def test_the_starvation_margin_is_reported_per_timeframe(report):
    """The finding that matters going forward is the margin between a
    lookback and a clean run, so it must be on every run, not in a docstring."""
    for t in report.timeframes:
        assert t.clean_run_median > 0
        assert t.max_lookback > 0


def test_h4_has_much_less_headroom_than_h1(report):
    """The timeframe-level statement of the starvation law: a trading week is
    a fixed amount of time and a coarser bar makes it fewer bars."""
    by_tf = {t.timeframe: t for t in report.timeframes}
    assert by_tf["H4"].clean_run_median < by_tf["H1"].clean_run_median


def test_nothing_is_annihilated_in_this_configuration(report):
    """Pins the current state. If a future config pushes a lookback past its
    clean run this fails, which is the notice worth having."""
    annihilated = [t.timeframe for t in report.timeframes if t.annihilated]
    assert not annihilated, (
        f"{annihilated} produce no trades under the mask — window starvation. "
        "That is a real finding, not a test bug: update this expectation and "
        "record it.")


def test_the_report_serialises(report):
    d = report.as_dict()
    assert d["mode"] == "mask_on"
    assert d["flags_applied"] == ["weekend_gap"]
    assert len(d["timeframes"]) == len(report.timeframes)


def test_logging_it_is_not_a_trial(tmp_path, report):
    from research import log as research_log
    research_log.register_hypothesis("seed", title="t", mechanism="m",
                                     log_dir=tmp_path)
    before = research_log.trial_count(tmp_path)
    entry = m.log_mask_on(report, log_dir=tmp_path)
    assert entry.counts_as_trial is False
    assert research_log.trial_count(tmp_path) == before
    ok, msg = research_log.verify(tmp_path)
    assert ok, msg
