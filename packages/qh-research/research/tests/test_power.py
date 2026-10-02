"""The gate stack's measured power — and the unit it has to be measured at.

`power.py` answers a question five falsifications made unavoidable: is this
harness capable of passing anything, or is it tuned to a rejection rate of
one? These tests pin the machinery and the two results that came out of it,
including the one that was wrong.
"""

from __future__ import annotations

import numpy as np
import pytest

from research.reports.power import (WALK_FORWARD_FOLDS,
                                    FoldConventionError,
                                    periods_per_year_for,
    GATE_NAMES,
    PowerCurve,
    PowerPoint,
    REALISTIC_N_OBS,
    detection_floor,
    power_curve,
)
from research.reports.scorecard import Thresholds


def _curve(points) -> PowerCurve:
    c = PowerCurve()
    for sr, passed, n in points:
        c.points.append(PowerPoint(injected_sharpe=sr, n_trials=n,
                                   n_passed=passed))
    return c


# -- the summary statistics -------------------------------------------------

def test_the_detection_floor_is_the_first_level_that_reaches_the_target():
    c = _curve([(0.0, 0, 20), (0.5, 2, 20), (1.2, 15, 20), (1.5, 14, 20)])
    assert detection_floor(c, target=0.5) == 1.2


def test_a_floor_that_is_never_reached_is_none_and_that_is_the_finding():
    """None is a result, not a missing value: a stack that cannot pass an
    injected 1.5 half the time will not pass a real mechanism either."""
    c = _curve([(0.0, 0, 20), (1.5, 1, 20)])
    assert detection_floor(c) is None


def test_the_zero_row_is_the_false_positive_rate():
    """A power curve without its type-I rate is half a measurement."""
    c = _curve([(0.0, 1, 20), (1.2, 15, 20)])
    assert c.false_positive_rate == pytest.approx(0.05)


def test_a_gate_that_never_rejects_shows_a_pass_rate_of_one():
    """The inert-gate case. n_trades passed 100% at every injected level on
    2,000 observations, because 2,000 always clears 30 or 100 — a gate
    contributing nothing to a six-way AND is false comfort, and the per-gate
    rate is what makes it visible."""
    p = PowerPoint(injected_sharpe=1.2, n_trials=20, n_passed=15)
    assert p.gate_pass_rate("n_trades") == 1.0


def test_a_gate_that_always_rejects_shows_a_pass_rate_of_zero():
    p = PowerPoint(injected_sharpe=0.3, n_trials=20, n_passed=0)
    p.gate_failures.update(["dsr"] * 20)
    assert p.gate_pass_rate("dsr") == 0.0


def test_gate_names_cover_every_gate_the_scorecard_applies():
    """A reworded failure message must surface as 'unattributed' rather than
    being silently miscounted, so the mapping has to stay complete."""
    t = Thresholds()
    for field in ("is_oos_gap_max", "pbo_max", "dsr_prob_min",
                  "max_dd_oos_max", "n_trades_oos_min",
                  "profit_factor_oos_min"):
        assert hasattr(t, field)
    assert len(GATE_NAMES) == 6


# -- the unit ---------------------------------------------------------------

def test_the_default_unit_is_one_folds_trades_and_that_is_not_where_verdicts_are_taken():
    """Pins the mistake, because it produced a confident wrong answer.

    Measuring at n=114 — one fold's OOS trades — gave a 0% pass rate at every
    injected Sharpe including 1.5, which reads as "the harness passes
    nothing". It was an artifact: MinTRL puts the minimum decidable annualised
    Sharpe at n=114 at 1.66, so the whole curve ran below the theoretical
    floor and the gates were correctly refusing an undecidable sample.

    The recorded verdicts were never taken there: crest_n_keel's DSR used
    2,141 pooled trades, asqs 1,147. Any power claim has to name its n.
    """
    assert REALISTIC_N_OBS == 114, (
        "the per-fold default is kept because it is the honest per-fold "
        "number; what changed is that a power claim must state whether it is "
        "per-fold or pooled")


def test_noise_does_not_pass():
    """The one end-to-end assertion worth its runtime: at the pooled unit the
    false-positive rate is zero."""
    c = power_curve(levels=(0.0,), n_trials=5, T=2000,
                    folds=WALK_FORWARD_FOLDS)
    assert c.points[0].pass_rate == 0.0


# -- the fold convention ----------------------------------------------------
# periods_per_year and T are two claims about the same span, and carrying the
# pairing by hand produced a wrong measurement: a sweep run with
# periods_per_year=T instead of T//17 reported 0% at every injected level.
# That failure is dangerous because it looks like a result. "Nothing passes"
# is exactly what this module exists to report, so a rescaled axis reads as a
# finding rather than as broken units.

def test_a_single_fold_annualises_at_its_own_length():
    assert periods_per_year_for(114, folds=1) == 114


def test_a_pooled_run_annualises_per_fold_not_per_sample():
    """The case that was wrong: 2,000 pooled observations over 17 one-year
    windows make a year 117 observations long, not 2,000."""
    assert periods_per_year_for(2000, folds=WALK_FORWARD_FOLDS) == 2000 // 17
    assert periods_per_year_for(2000, folds=WALK_FORWARD_FOLDS) != 2000


def test_the_default_fold_count_is_the_walk_forward_the_numbers_came_from():
    assert WALK_FORWARD_FOLDS == 17
    assert periods_per_year_for(3500) == 3500 // 17


def test_an_inconsistent_pair_is_refused_rather_than_resolved():
    """Precedence would be the wrong answer here. Both values assert how many
    observations make a year, so preferring one silently is the defect."""
    with pytest.raises(FoldConventionError, match="disagrees"):
        power_curve(levels=(0.0,), n_trials=1, T=2000,
                    periods_per_year=2000, folds=WALK_FORWARD_FOLDS)


def test_the_error_names_both_claims_and_what_was_implied():
    with pytest.raises(FoldConventionError) as e:
        power_curve(levels=(0.0,), n_trials=1, T=2000,
                    periods_per_year=999, folds=WALK_FORWARD_FOLDS)
    m = str(e.value)
    assert "999" in m          # what was passed
    assert "2000" in m         # the sample it disagrees with
    assert str(2000 // 17) in m  # what the fold count implies


def test_an_agreeing_override_is_not_a_conflict():
    c = power_curve(levels=(0.0,), n_trials=1, T=2000,
                    periods_per_year=2000 // 17, folds=WALK_FORWARD_FOLDS)
    assert c.periods_per_year == 2000 // 17


def test_zero_folds_is_refused():
    with pytest.raises(ValueError, match="folds"):
        periods_per_year_for(2000, folds=0)
