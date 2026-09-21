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
    BandwidthTooShort,
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
    # check_bandwidth=False: this tests that max_lag reaches the estimator,
    # not whether either lag is sufficient — the guard has its own tests.
    assert (lo_eta(x, 252, max_lag=5, check_bandwidth=False)
            != lo_eta(x, 252, max_lag=100, check_bandwidth=False))


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


# -- the bandwidth guard ----------------------------------------------------
#
# Added after the power test (below) showed the estimator was accurate under
# the null and badly wrong under exactly the dependence it exists for.

def _blocks(hold: int, n: int = 200_000, seed: int = 3) -> np.ndarray:
    """One decision driving `hold` consecutive bar returns — a held position."""
    rng = np.random.default_rng(seed)
    return (np.repeat(rng.normal(0, 1, n // hold + 1), hold)[:n]
            + rng.normal(0, 0.3, n))


def _analytic_eta(phi: float, q: int) -> float:
    k = np.arange(1, q)
    return q / math.sqrt(q + 2.0 * float(np.sum((q - k) * phi ** k)))


@pytest.mark.parametrize("phi", [0.05, 0.10, 0.20])
@pytest.mark.parametrize("q", [252, 6048])
def test_eta_recovers_the_analytic_value_when_dependence_is_present(phi, q):
    """The power test, as distinct from the size test above.

    Recovering sqrt(q) on IID draws shows the estimator is unbiased under the
    null. It says nothing about whether it recovers the *right* eta when
    autocorrelation is actually there, which is the only case it exists for.
    AR(1) has rho_k = phi^k, so the analytic answer is known.
    """
    est = lo_eta(ar1(phi), q)
    assert est == pytest.approx(_analytic_eta(phi, q), rel=0.02)


@pytest.mark.parametrize("hold", [50, 200])
def test_a_held_position_is_refused_at_the_default_bandwidth(hold):
    """The finding that made the guard necessary.

    A position held 50 bars has dependence out to lag 50, while the
    rule-of-thumb bandwidth at n=200,000 is 21. Measured against the true eta
    the default was 55% too high at hold=50 and 208% at hold=200 — biased
    toward *no* correction, which is the flattering direction and
    indistinguishable from a correct small one. Silently returning that number
    is worse than refusing.
    """
    with pytest.raises(BandwidthTooShort):
        lo_eta(_blocks(hold), 6048)


def test_a_held_position_is_refused_even_with_the_holding_period_declared():
    """The finding, not a gap in the implementation.

    At q=6048 Lo's sum needs autocorrelations out to thousands of lags,
    weighted by up to 6048, and their sampling error accumulates faster than
    the bias they remove — on a process whose real dependence stops at lag 50
    the estimated omitted contribution *grows* from 1.7% at lag 150 to 35% at
    lag 5000. Declaring the hold makes the refusal specific; it does not make
    the number obtainable. The correct response is to change the input to
    trade-level returns, not to widen the window.
    """
    with pytest.raises(BandwidthTooShort):
        lo_eta(_blocks(50), 6048, holding_period=50)


@pytest.mark.parametrize("n", [150, 500, 2500])
def test_small_near_independent_samples_are_not_refused(n):
    """The guard's own failure mode, pinned.

    Its first version compared the omitted tail against a significance floor
    and then against its raw magnitude. Both made it measure its own
    estimation noise: at n=150 the tail autocorrelations have SE ~0.08, the
    weighted sum of them looks large, and every near-independent trade-level
    series was refused. A guard that refuses everything is not a guard.
    """
    rng = np.random.default_rng(11)
    e = rng.normal(0, 1, n)
    x = np.empty(n)
    x[0] = e[0]
    for i in range(1, n):
        x[i] = 0.02 * x[i - 1] + e[i]
    assert lo_eta(x, 116) == pytest.approx(math.sqrt(116), rel=0.10)


def test_the_guard_can_be_switched_off_deliberately():
    assert lo_eta(_blocks(50), 6048, check_bandwidth=False) > 0


# -- the measured claim -----------------------------------------------------

def test_holding_a_position_does_not_make_bar_returns_autocorrelated():
    """The intuition this module was written on, measured and refuted.

    "A position held 50 bars contributes 50 positively autocorrelated bar
    returns" is false. The position's sign persists; a bar return is position
    times price increment, and gold's H1 increments are near-white. Only
    serially correlated increments would confer it.

    Measured on crest_n_keel H1 momentum: rho_1 is NEGATIVE and naive
    annualisation overstates by about 1.09x, not the 2-3x the intuition
    implied. That is why the bar-level path is documented as inferior rather
    than refused by default — the magnitude did not justify refusing.

    Pinned because it is the number a deprecation decision rests on.
    """
    import pandas as pd
    from research.post.sweeps import cnk_engine as engine
    from research.post.sweeps import run_cnk_sweep as sweep
    from research.post.sweeps.data import load

    df = load("H1")
    bars = engine.Bars(df)
    hma_v = engine.hma(bars.close, 55)
    atr_v = engine.atr(bars.high, bars.low, bars.close, 14)
    lo, sh = engine.momentum_signals(bars, hma_v)
    sim = engine.simulate(
        bars, "momentum", hma_v, atr_v, lo, sh, enable_long=True,
        enable_short=False, sl_mult=0.0, tp_mult=0.0, trail_mult=3.0,
        risk_pct=sweep.RISK_PCT, min_atr=0.0, max_dd_halt=1.0,
        record_trades=True)

    close = np.asarray(bars.close, dtype=float)
    pos_of = {pd.Timestamp(t): i for i, t in enumerate(df.index)}
    pos = np.zeros(len(close))
    for r in sim["records"]:
        a = pos_of[pd.Timestamp(r["entry_ts"])]
        b = pos_of[pd.Timestamp(r["exit_ts"])]
        pos[a:b] = 1.0 if r["direction"] == "long" else -1.0

    bar_ret = np.zeros(len(close))
    bar_ret[1:] = pos[:-1] * np.diff(close) / close[:-1]
    held = bar_ret[pos != 0]

    assert held.size > 10_000, "expected a large held-bar sample"
    rho = autocorrelations(held, 10)
    assert rho[0] < 0.05, (
        f"rho_1 = {rho[0]:+.4f}. The documented claim is that holding does "
        "not confer positive autocorrelation; a strongly positive value here "
        "would overturn it and the bar-level deprecation decision with it.")
