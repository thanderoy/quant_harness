"""T7 — MinTRL, its inversion, and the pre-registration filter.

The load-bearing test here is the round trip. ``min_decidable_sharpe`` solves
a quadratic that was derived by hand from the MinTRL formula, and the way to
know the algebra is right is that feeding its answer back through
``min_trl`` returns the sample length you started from. Everything else
checks that the guards fire.
"""

from __future__ import annotations

import math

import pytest

from research.post.dsr import psr
from research.post.mintrl import (
    DEFAULT_ALPHA,
    NotDecidable,
    assert_decidable,
    min_decidable_sharpe,
    min_trl,
    screen,
    sharpe_variance_factor,
)


# -- the inversion ---------------------------------------------------------

@pytest.mark.parametrize("n,sr_star,skew,kurt", [
    (500, 0.00, 0.0, 3.0),
    (1000, 0.02, -0.5, 6.0),
    (250, 0.01, 0.4, 9.0),
    (5000, 0.03, -1.2, 12.0),
    (6, 0.00, 0.0, 3.0),
    (100000, 0.00, 0.0, 3.0),
])
def test_the_floor_needs_exactly_the_sample_it_was_derived_from(
        n, sr_star, skew, kurt):
    floor = min_decidable_sharpe(n, sr_star, skew=skew, kurtosis=kurt)
    assert floor is not None
    back = min_trl(floor, sr_star, skew=skew, kurtosis=kurt)
    assert back.min_trl == pytest.approx(n, rel=1e-9)


def test_the_floor_is_above_the_benchmark():
    f = min_decidable_sharpe(1000, 0.02, skew=-0.5, kurtosis=6.0)
    assert f > 0.02


def test_a_longer_sample_decides_a_smaller_effect():
    a = min_decidable_sharpe(500)
    b = min_decidable_sharpe(5000)
    c = min_decidable_sharpe(50000)
    assert a > b > c


def test_no_sharpe_is_decidable_when_tails_outrun_the_sample():
    """With heavy enough tails the variance term grows at least as fast as n."""
    assert min_decidable_sharpe(5, 0.0, skew=0.0, kurtosis=40.0) is None


def test_a_short_sample_under_normal_returns_is_still_decidable():
    assert min_decidable_sharpe(5, 0.0, skew=0.0, kurtosis=3.0) is not None


def test_there_is_a_hard_floor_on_sample_length():
    """Below n=3 no Sharpe is decidable at all, even for normal returns.

    (n-1) has to exceed Z_alpha^2 * (kurtosis-1)/4 before the quadratic has a
    positive leading coefficient. At alpha=0.05 and kurtosis=3 that term is
    1.353, so two observations decide nothing however large the Sharpe. Worth
    pinning: it is the degenerate end of the same inequality that makes fat
    tails expensive, not a special case.
    """
    assert min_decidable_sharpe(2, 0.0, skew=0.0, kurtosis=3.0) is None
    assert min_decidable_sharpe(3, 0.0, skew=0.0, kurtosis=3.0) is not None


def test_just_above_the_floor_the_answer_is_decidable_but_useless():
    """The algebra keeps working before the result means anything.

    At n=3 and n=4 the quadratic returns a floor of 2.04 and 1.28 per
    observation — above MAX_PLAUSIBLE_PER_OBS_SR, so min_trl() refuses to
    take them back. The two guards are consistent, not contradictory: a
    sample that can only detect an implausible Sharpe cannot detect anything.
    Pinned because the collision is where someone would otherwise "fix" one
    guard against the other.
    """
    assert min_decidable_sharpe(3) > 1.0
    assert min_decidable_sharpe(4) > 1.0
    with pytest.raises(ValueError, match="annualised"):
        min_trl(min_decidable_sharpe(4))
    # By n=6 the floor is back inside the plausible range.
    assert min_decidable_sharpe(6) < 1.0


# -- the formula -----------------------------------------------------------

def test_min_trl_matches_the_published_formula():
    sr, sr_star, skew, kurt = 0.08, 0.02, -0.5, 6.0
    z = min_trl(sr, sr_star, skew=skew, kurtosis=kurt).z_alpha
    expected = 1.0 + (1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr ** 2) * \
        (z / (sr - sr_star)) ** 2
    assert min_trl(sr, sr_star, skew=skew, kurtosis=kurt).min_trl == \
        pytest.approx(expected, rel=1e-15)


def test_a_bigger_edge_needs_less_data():
    small = min_trl(0.03, 0.02).min_trl
    big = min_trl(0.30, 0.02).min_trl
    assert big < small


def test_fat_tails_are_expensive():
    thin = min_trl(0.08, 0.02, kurtosis=3.0).min_trl
    fat = min_trl(0.08, 0.02, kurtosis=12.0).min_trl
    assert fat > thin


def test_negative_skew_is_expensive():
    """Losses in the left tail cost track record; gains there pay for it."""
    neg = min_trl(0.08, 0.02, skew=-1.0).min_trl
    zero = min_trl(0.08, 0.02, skew=0.0).min_trl
    pos = min_trl(0.08, 0.02, skew=1.0).min_trl
    assert neg > zero > pos


def test_a_stricter_alpha_needs_more_data():
    lax = min_trl(0.08, 0.02, alpha=0.10).min_trl
    strict = min_trl(0.08, 0.02, alpha=0.01).min_trl
    assert strict > lax


def test_min_trl_obs_rounds_up():
    r = min_trl(0.05)
    assert r.min_trl_obs == math.ceil(r.min_trl)
    assert r.min_trl_obs >= r.min_trl


# -- agreement with the DSR sibling ---------------------------------------

def test_the_variance_factor_is_the_one_psr_uses():
    """MinTRL and PSR share a bracket; if they drift, one of them is wrong.

    At exactly MinTRL observations the PSR must equal 1 - alpha by
    construction — that is what MinTRL means. This reconstructs it through
    the other module's code path.
    """
    sr, sr_star, skew, kurt = 0.08, 0.02, -0.5, 6.0
    r = min_trl(sr, sr_star, skew=skew, kurtosis=kurt)
    got = psr(sr, sr_star, r.min_trl_obs, skew, kurt)
    assert got == pytest.approx(1.0 - DEFAULT_ALPHA, abs=1e-4)


def test_variance_factor_is_one_at_zero_sharpe():
    assert sharpe_variance_factor(0.0, -0.5, 9.0) == 1.0


# -- guards ----------------------------------------------------------------

def test_a_sharpe_below_the_benchmark_is_never_decidable():
    """The formula squares the edge, so this would otherwise look finite."""
    r = min_trl(0.01, 0.05)
    assert not r.decidable
    assert r.min_trl == math.inf
    assert r.min_trl_obs is None
    assert "not there" in r.reason


def test_a_sharpe_equal_to_the_benchmark_is_never_decidable():
    assert not min_trl(0.05, 0.05).decidable


def test_an_annualised_sharpe_is_refused():
    with pytest.raises(ValueError, match="annualised"):
        min_trl(1.76, 0.0)


def test_excess_kurtosis_is_refused():
    with pytest.raises(ValueError, match="RAW kurtosis"):
        min_trl(0.05, kurtosis=0.0)


def test_a_bad_alpha_is_refused():
    with pytest.raises(ValueError, match="alpha"):
        min_trl(0.05, alpha=0.9)


def test_too_few_observations_is_refused():
    with pytest.raises(ValueError, match="n_obs"):
        min_decidable_sharpe(1)


def test_a_non_positive_variance_factor_is_reported_not_raised():
    r = min_trl(0.9, 0.0, skew=2.0, kurtosis=1.0)
    assert not r.decidable
    assert "non-positive" in r.reason


# -- the pre-registration filter -------------------------------------------

def test_a_plausible_effect_above_the_floor_passes():
    r = screen(sr_plausible=0.10, n_obs=1000, sr_star=0.02)
    assert r.decidable
    assert r.headroom > 0


def test_a_plausible_effect_below_the_floor_fails():
    r = screen(sr_plausible=0.01, n_obs=250, sr_star=0.02)
    assert not r.decidable
    assert "cannot decide the claim either way" in r.reason


def test_assert_decidable_refuses_before_the_compute():
    with pytest.raises(NotDecidable, match="produces a number, not a finding"):
        assert_decidable(0.005, n_obs=250, sr_star=0.02, name="some_idea")


def test_assert_decidable_returns_the_result_when_it_passes():
    r = assert_decidable(0.20, n_obs=2000, sr_star=0.02)
    assert r.decidable
    assert r.min_decidable_sharpe is not None


def test_screen_reports_when_nothing_is_decidable():
    r = screen(sr_plausible=0.5, n_obs=5, kurtosis=40.0)
    assert not r.decidable
    assert r.min_decidable_sharpe is None
    assert "outruns the sample" in r.reason


def test_the_floor_is_exactly_the_screen_boundary():
    floor = min_decidable_sharpe(1000, 0.02, skew=-0.5, kurtosis=6.0)
    assert screen(floor, 1000, 0.02, skew=-0.5, kurtosis=6.0).decidable
    assert not screen(floor * 0.999, 1000, 0.02,
                      skew=-0.5, kurtosis=6.0).decidable
