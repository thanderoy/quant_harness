"""Tests for research.post.dsr — Deflated Sharpe Ratio."""

from __future__ import annotations

import math

import numpy as np
import pytest

from research import log as research_log
from research.post.dsr import (
    DSRResult,
    deflated_sharpe_ratio,
    expected_max_sharpe,
    log_dsr_evaluation,
    psr,
)


def _returns_with_exact_sharpe(n: int, sr_per_obs: float, seed: int = 0,
                               std: float = 0.01) -> np.ndarray:
    """Construct near-normal returns with an exact per-observation Sharpe."""
    rng = np.random.default_rng(seed)
    x = rng.standard_normal(n)
    x = (x - x.mean()) / x.std(ddof=1)        # mean 0, std 1 exactly
    return x * std + sr_per_obs * std         # std=std, mean=SR*std → SR exact


# ---------------------------------------------------------------------------
# 1. PSR sanity check — hand-computed reference under skew=0, kurt=3.
# ---------------------------------------------------------------------------

def test_psr_matches_hand_computed_reference():
    sr = 0.05
    n = 500
    skew = 0.0
    kurt = 3.0
    # With skew=0, denom = sqrt(1 + ((kurt-1)/4) * SR^2) = sqrt(1 + 0.5*SR^2)
    denom = math.sqrt(1.0 + 0.5 * sr ** 2)
    z = sr * math.sqrt(n - 1) / denom
    expected = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    got = psr(sr, 0.0, n, skew, kurt)
    assert abs(got - expected) < 1e-9


# ---------------------------------------------------------------------------
# 2. Deflation increases the benchmark with N.
# ---------------------------------------------------------------------------

def test_expected_max_sharpe_monotone_in_n():
    var_sr = 0.001
    n_vals = [1, 10, 100, 1000]
    vals = [expected_max_sharpe(n, var_sr) for n in n_vals]
    assert vals[0] == 0.0                            # N=1 → no selection
    assert vals[1] < vals[2] < vals[3]               # strict growth
    assert vals[1] > 0.0
    # And materially larger by 1000: at least 2x the N=10 value.
    assert vals[3] > 2.0 * vals[1]


# ---------------------------------------------------------------------------
# 3. More trials lower the DSR.
# ---------------------------------------------------------------------------

def test_more_trials_lower_dsr():
    r = _returns_with_exact_sharpe(n=1000, sr_per_obs=0.08, seed=1)
    d1 = deflated_sharpe_ratio(r, n_trials=1).dsr
    d10 = deflated_sharpe_ratio(r, n_trials=10).dsr
    d100 = deflated_sharpe_ratio(r, n_trials=100).dsr
    assert d1 > d10 > d100


# ---------------------------------------------------------------------------
# 4. Non-normality penalty — fat tails and negative skew lower PSR.
# ---------------------------------------------------------------------------

def test_fat_tails_lower_psr():
    sr = 0.10
    n = 1000
    p_normal = psr(sr, 0.0, n, skew=0.0, kurtosis=3.0)
    p_fat = psr(sr, 0.0, n, skew=0.0, kurtosis=8.0)
    assert p_fat < p_normal


def test_negative_skew_lowers_psr():
    sr = 0.10
    n = 1000
    p_zero = psr(sr, 0.0, n, skew=0.0, kurtosis=3.0)
    p_neg = psr(sr, 0.0, n, skew=-1.0, kurtosis=3.0)
    assert p_neg < p_zero


# ---------------------------------------------------------------------------
# 5. Strong strategy under low search passes.
# ---------------------------------------------------------------------------

def test_strong_low_search_passes():
    r = _returns_with_exact_sharpe(n=1000, sr_per_obs=0.15, seed=2)
    result = deflated_sharpe_ratio(r, n_trials=2)
    assert result.passes
    assert result.dsr > 0.95
    # Annualisation is for display only — sanity-check it.
    assert math.isclose(result.sr_hat_annualised,
                        0.15 * math.sqrt(252), rel_tol=1e-6)


# ---------------------------------------------------------------------------
# 6. Same Sharpe under heavy search fails — selection bias bites.
# ---------------------------------------------------------------------------

def test_marginal_under_heavy_search_fails():
    # Same per-obs SR as the strong-passing test; only N differs. With a
    # large enough search space, even an annualised Sharpe ~2.4 fails DSR —
    # exactly the selection-bias correction the haircut exists to apply.
    r = _returns_with_exact_sharpe(n=1000, sr_per_obs=0.15, seed=2)
    result = deflated_sharpe_ratio(r, n_trials=10_000)
    assert not result.passes
    assert result.dsr < 0.95


# ---------------------------------------------------------------------------
# 7. Var(SR) source precedence: override > empirical > estimated.
# ---------------------------------------------------------------------------

def test_var_sr_source_precedence():
    r = _returns_with_exact_sharpe(n=500, sr_per_obs=0.05, seed=3)

    res_override = deflated_sharpe_ratio(r, n_trials=10, var_sr=0.002)
    assert res_override.var_sr_source == "override"
    assert math.isclose(res_override.var_sr, 0.002)

    res_emp = deflated_sharpe_ratio(
        r, n_trials=10, trial_sharpes=np.array([0.02, 0.04, 0.06, 0.08, 0.10]),
    )
    assert res_emp.var_sr_source == "empirical"
    assert math.isclose(
        res_emp.var_sr,
        float(np.array([0.02, 0.04, 0.06, 0.08, 0.10]).var(ddof=1)),
        rel_tol=1e-12,
    )

    res_est = deflated_sharpe_ratio(r, n_trials=10)
    assert res_est.var_sr_source == "estimated"
    assert res_est.var_sr > 0.0

    with pytest.raises(ValueError, match="only one"):
        deflated_sharpe_ratio(r, n_trials=10, var_sr=0.001,
                              trial_sharpes=[0.01, 0.02, 0.03])


# ---------------------------------------------------------------------------
# 8. n_trials defaults to the research log's honest floor.
# ---------------------------------------------------------------------------

def test_n_trials_defaults_to_log(tmp_path):
    for hid in ("h1", "h2", "h3", "h4", "h5", "h6", "h7"):
        research_log.register_hypothesis(
            hid, title=hid, mechanism="m", log_dir=tmp_path,
        )
    r = _returns_with_exact_sharpe(n=500, sr_per_obs=0.05, seed=4)
    result = deflated_sharpe_ratio(r, log_dir=tmp_path)
    assert result.n_trials == 7
    assert research_log.trial_count(log_dir=tmp_path) == 7


# ---------------------------------------------------------------------------
# 9. Annualised-input guard.
# ---------------------------------------------------------------------------

def test_rejects_annualised_input_leak():
    # Tiny noise around a large mean → per-obs SR ≫ 1.0 → clearly annualised.
    rng = np.random.default_rng(5)
    bad = rng.standard_normal(500) * 0.001 + 0.5    # SR ≈ 500
    with pytest.raises(ValueError, match="annualised"):
        deflated_sharpe_ratio(bad, n_trials=10)


# ---------------------------------------------------------------------------
# 10. Log round-trip — evaluation does not inflate trial_count.
# ---------------------------------------------------------------------------

def test_log_dsr_evaluation_preserves_trial_count(tmp_path):
    research_log.register_hypothesis(
        "h1", title="t", mechanism="m", log_dir=tmp_path,
    )
    before = research_log.trial_count(log_dir=tmp_path)

    r = _returns_with_exact_sharpe(n=1000, sr_per_obs=0.12, seed=6)
    result = deflated_sharpe_ratio(r, n_trials=5)
    entry = log_dsr_evaluation("h1", result, log_dir=tmp_path)

    assert entry.event_type is research_log.EventType.UPDATE
    assert entry.counts_as_trial is False
    after = research_log.trial_count(log_dir=tmp_path)
    assert after == before
    ok, msg = research_log.verify(log_dir=tmp_path)
    assert ok, msg
    # Metrics survived the round trip.
    hist = research_log.history("h1", log_dir=tmp_path)
    last = hist[-1]
    assert "dsr" in last.metrics
    assert last.metrics["passes"] == result.passes


# ---------------------------------------------------------------------------
# Worked numerical anchor — pin the documented example.
# ---------------------------------------------------------------------------

def test_worked_anchor():
    """Pin the numbers in the module docstring."""
    sr = 0.10
    n = 1000
    skew = 0.0
    kurt = 3.0
    n_trials = 10

    # estimated var_sr
    var_sr = (1.0 / (n - 1)) * (1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr ** 2)
    sr_star = expected_max_sharpe(n_trials, var_sr)
    psr_zero = psr(sr, 0.0, n, skew, kurt)
    dsr_value = psr(sr, sr_star, n, skew, kurt)

    assert abs(sr_star - 0.04993) < 5e-4
    assert abs(psr_zero - 0.99919) < 5e-4
    assert abs(dsr_value - 0.94279) < 5e-4
