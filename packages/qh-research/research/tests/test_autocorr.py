"""Lo (2002) annualisation — the factor, and the two ways to get it wrong.

The maths is checked against cases with known answers rather than against
itself: IID must recover `sqrt(q)`, positive autocorrelation must fall below
it, negative must exceed it. Those three pin the direction, and the direction
is the whole point — a correction that moved Sharpe the wrong way would be
worse than not correcting at all.

Two failures found while building this are pinned here, because both produce a
plausible-looking number rather than an error:

1. The untruncated sum is unusable at high `q`. Run literally to lag `q-1` it
   returned `eta = 89.8` on 200,000 genuinely IID draws at `q=6048`, against a
   true `sqrt(q) = 77.8` — 15% too high, in the *overstating* direction, at
   exactly the H1 case the correction exists for.
2. Annualising trade-level returns with a bar-level `q`. Passing
   `periods_per_year=6048` to 2,497 trade returns spanning 21.6 years produced
   an annualised Sharpe of 7.01. The right factor there is trades per year
   (~116), and `sqrt(6048/116)` is about 7 — the entire figure was the wrong
   constant.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from research.metrics.autocorr import (
    autocorrelations,
    compare_annualisation,
    lo_eta,
    newey_west_lag,
)

SEED = 0


def iid(n: int = 200_000) -> np.ndarray:
    return np.random.default_rng(SEED).normal(0.0, 1.0, n)


def ar1(phi: float, n: int = 200_000) -> np.ndarray:
    e = np.random.default_rng(SEED + 1).normal(0.0, 1.0, n)
    x = np.empty(n)
    x[0] = e[0]
    for i in range(1, n):
        x[i] = phi * x[i - 1] + e[i]
    return x


# -- the factor -------------------------------------------------------------

@pytest.mark.parametrize("q", [52, 252, 6048])
def test_iid_returns_recover_the_naive_factor(q):
    """`sqrt(q)` is the special case of Lo's formula, and must fall out of it."""
    eta = lo_eta(iid(), q)
    assert eta == pytest.approx(math.sqrt(q), rel=0.01), (
        f"on IID draws eta({q}) should be sqrt(q)={math.sqrt(q):.3f}, got "
        f"{eta:.3f}")


@pytest.mark.parametrize("phi", [0.1, 0.3, 0.5])
def test_positive_autocorrelation_deflates_the_factor(phi):
    """The direction that matters: naive annualisation overstates Sharpe."""
    eta = lo_eta(ar1(phi), 252)
    assert eta < math.sqrt(252), (
        f"phi={phi} is positively autocorrelated; eta must be below sqrt(q)")


def test_the_deflation_grows_with_the_autocorrelation():
    etas = [lo_eta(ar1(p), 252) for p in (0.1, 0.3, 0.5)]
    assert etas[0] > etas[1] > etas[2], (
        f"stronger persistence must deflate further, got {etas}")


def test_negative_autocorrelation_inflates_the_factor():
    """Mean reversion genuinely does make a per-period Sharpe scale better
    than sqrt(q). If this failed, the estimator would only ever deflate and
    would be a haircut rather than a correction."""
    assert lo_eta(ar1(-0.3), 252) > math.sqrt(252)


def test_q_of_one_is_the_identity():
    assert lo_eta(iid(1000), 1) == 1.0


# -- the truncation ---------------------------------------------------------

def test_the_untruncated_sum_is_what_the_truncation_exists_to_avoid():
    """Pins failure 1 from the module docstring.

    Reconstructs the naive estimator and shows it misses badly at q=6048 on
    IID data, so the Newey-West truncation cannot be mistaken for a detail.
    """
    r = iid()
    rho = autocorrelations(r, 6047)
    k = np.arange(1, rho.size + 1)
    naive = 6048 / math.sqrt(6048 + 2.0 * float(np.sum((6048 - k) * rho)))
    truncated = lo_eta(r, 6048)

    assert abs(naive / math.sqrt(6048) - 1) > 0.05, (
        "the naive sum is supposed to be badly wrong here; if it is now "
        "accurate the truncation may no longer be needed")
    assert truncated == pytest.approx(math.sqrt(6048), rel=0.01)


def test_the_truncation_lag_follows_the_standard_rule():
    assert newey_west_lag(100) == 4
    assert newey_west_lag(200_000) > newey_west_lag(1_000)


def test_a_longer_lag_can_be_requested():
    """Lags past the truncation are treated as zero, so a caller who knows the
    holding period exceeds it must be able to widen the window."""
    x = ar1(0.3)
    assert lo_eta(x, 252, max_lag=5) != lo_eta(x, 252, max_lag=100)


# -- autocorrelations themselves --------------------------------------------

def test_autocorrelation_of_iid_is_near_zero():
    assert abs(autocorrelations(iid(), 5)).max() < 0.02


def test_autocorrelation_recovers_a_known_ar1():
    rho = autocorrelations(ar1(0.4), 3)
    assert rho[0] == pytest.approx(0.4, abs=0.02)
    assert rho[1] == pytest.approx(0.16, abs=0.03)   # phi^2


def test_a_constant_series_has_no_autocorrelation_rather_than_a_crash():
    assert (autocorrelations(np.ones(100), 3) == 0).all()


# -- the report -------------------------------------------------------------

def test_the_report_puts_both_factors_side_by_side():
    """The choice of annualisation should be visible, not implied."""
    r = compare_annualisation(ar1(0.3), 252)
    assert r.eta_iid == pytest.approx(math.sqrt(252))
    assert r.eta_lo < r.eta_iid
    assert r.inflation > 0
    # Magnitude, not sign: the naive factor scales whatever sign is present,
    # so on a negative-mean series it makes the Sharpe *worse*, not better.
    assert abs(r.sr_annualised_iid) > abs(r.sr_annualised_lo)


def test_exaggeration_only_counts_as_flattery_when_the_sharpe_is_positive():
    """The bug this pins: a signed ratio called a more-negative Sharpe an
    overstatement. Direction depends on the sign of the underlying Sharpe."""
    neg = compare_annualisation(ar1(0.3), 252)
    assert neg.sr_per_period < 0
    assert neg.inflation > 0
    assert not neg.flatters

    pos = compare_annualisation(ar1(0.3) + 0.05, 252)
    assert pos.sr_per_period > 0
    assert pos.flatters


def test_inflation_is_zero_on_independent_returns():
    r = compare_annualisation(iid(), 252)
    assert abs(r.inflation) < 0.02


def test_it_refuses_a_degenerate_series_rather_than_returning_nan():
    with pytest.raises(ValueError):
        compare_annualisation(np.ones(500), 252)
    with pytest.raises(ValueError):
        compare_annualisation([1.0], 252)


def test_q_must_be_positive():
    with pytest.raises(ValueError):
        lo_eta(iid(1000), 0)
