"""Deflated Sharpe Ratio (Bailey & López de Prado).

Turns the research log's honest trial count (`research.log.trial_count()`)
into a working multiple-testing haircut. DSR answers:

    Given that we ran N trials, what is the probability that this strategy's
    true Sharpe exceeds zero, after correcting for (a) selection bias from
    running many trials and (b) the non-normality of returns?

A high observed Sharpe means little if it is simply the maximum of many noisy
trials; DSR discounts exactly that. The common acceptance threshold is
``DSR > 0.95``.

Per-observation vs annualised — the rule
----------------------------------------
ALL DSR mathematics is in **per-observation** Sharpe units (i.e. matching the
return periodicity used to estimate `n_obs`, skew, and kurtosis). Annualisation
is applied to `sr_hat_annualised` for **display only** and never enters PSR or
the deflated benchmark. Mixing an annualised Sharpe with a per-observation `n`
is the single most common DSR bug, so this module raises ``ValueError`` if the
per-observation Sharpe exceeds ``MAX_PLAUSIBLE_PER_OBS_SR`` — any real return
series has a per-obs Sharpe well below 1.0.

Var(SR) source — be honest about it
-----------------------------------
The deflated benchmark scales with the cross-sectional standard deviation of
Sharpe estimates across trials. The function reports which path was used:

1. ``var_sr=...`` override (sensitivity analysis) → ``"override"``
2. ``trial_sharpes=...`` (sample variance of N real trial Sharpes) → ``"empirical"``
3. neither given → estimated from a single Sharpe's sampling SE → ``"estimated"``

Option 2 is strongly preferred once enough trial Sharpes are logged; option 3
is a defensible fallback when only one strategy's moments are known.

For **walk-forward** evaluations with N ≥ ~10 folds, pass the per-fold Sharpes
as ``trial_sharpes=`` (option 2). The empirical cross-fold variance captures the
actual out-of-sample variability the strategy exhibits, whereas option 3's
single-Sharpe sampling SE only describes the estimation noise of one in-sample
fit. The estimated variant typically yields a *materially higher* DSR for the
same underlying edge — a leniency that should be flagged in the writeup, not
silently accepted. Reach for option 3 only when per-fold data is genuinely
unavailable.

Worked numerical anchor
-----------------------
For ``n_obs=1000``, per-obs ``SR_hat=0.10`` (annualised ≈ 1.587 at 252),
skew=0, kurtosis=3 (normal), ``n_trials=10``, estimated ``var_sr``::

    sr_star      ≈ 0.04993
    psr_vs_zero  ≈ 0.99919
    dsr          ≈ 0.94279

The implementation pins these in :func:`test_dsr.test_worked_anchor`.

Usage
-----
>>> import numpy as np
>>> from research.post.dsr import deflated_sharpe_ratio
>>> rng = np.random.default_rng(0)
>>> r = rng.normal(0.001, 0.01, 1000)
>>> result = deflated_sharpe_ratio(r, n_trials=10)
>>> result.passes, result.dsr  # doctest: +SKIP
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from research import log as research_log

__all__ = [
    "DSRResult",
    "psr",
    "expected_max_sharpe",
    "deflated_sharpe_ratio",
    "log_dsr_evaluation",
    "MAX_PLAUSIBLE_PER_OBS_SR",
]

EULER_MASCHERONI: float = 0.5772156649015329
MAX_PLAUSIBLE_PER_OBS_SR: float = 1.0
DEFAULT_DSR_THRESHOLD: float = 0.95


# ---------------------------------------------------------------------------
# Hand-rolled standard normal CDF / inverse CDF — no scipy dependency.
# ---------------------------------------------------------------------------

def _norm_cdf(x: float) -> float:
    """Standard normal CDF via the error function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# Acklam's algorithm for the inverse standard normal CDF — accurate to ~1e-9
# across the full range. Coefficients from the published reference.
_ACKLAM_A = (
    -3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
    1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00,
)
_ACKLAM_B = (
    -5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
    6.680131188771972e+01, -1.328068155288572e+01,
)
_ACKLAM_C = (
    -7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
    -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00,
)
_ACKLAM_D = (
    7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
    3.754408661907416e+00,
)


def _norm_ppf(p: float) -> float:
    """Standard normal inverse CDF (quantile / PPF). Accurate to ~1e-9."""
    if not (0.0 < p < 1.0):
        if p == 0.0:
            return -math.inf
        if p == 1.0:
            return math.inf
        raise ValueError(f"p must be in (0, 1); got {p}")
    plow = 0.02425
    phigh = 1.0 - plow
    if p < plow:
        q = math.sqrt(-2.0 * math.log(p))
        return (((((_ACKLAM_C[0]*q + _ACKLAM_C[1])*q + _ACKLAM_C[2])*q
                 + _ACKLAM_C[3])*q + _ACKLAM_C[4])*q + _ACKLAM_C[5]) / (
               ((((_ACKLAM_D[0]*q + _ACKLAM_D[1])*q + _ACKLAM_D[2])*q
                 + _ACKLAM_D[3])*q + 1.0))
    if p > phigh:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -(((((_ACKLAM_C[0]*q + _ACKLAM_C[1])*q + _ACKLAM_C[2])*q
                  + _ACKLAM_C[3])*q + _ACKLAM_C[4])*q + _ACKLAM_C[5]) / (
                ((((_ACKLAM_D[0]*q + _ACKLAM_D[1])*q + _ACKLAM_D[2])*q
                  + _ACKLAM_D[3])*q + 1.0))
    q = p - 0.5
    r = q * q
    return ((((((_ACKLAM_A[0]*r + _ACKLAM_A[1])*r + _ACKLAM_A[2])*r
              + _ACKLAM_A[3])*r + _ACKLAM_A[4])*r + _ACKLAM_A[5]) * q) / (
           (((((_ACKLAM_B[0]*r + _ACKLAM_B[1])*r + _ACKLAM_B[2])*r
              + _ACKLAM_B[3])*r + _ACKLAM_B[4])*r + 1.0))


# ---------------------------------------------------------------------------
# Result dataclass + building blocks
# ---------------------------------------------------------------------------

@dataclass
class DSRResult:
    dsr: float
    psr_vs_zero: float
    sr_star: float
    sr_hat_per_obs: float
    sr_hat_annualised: float
    n_obs: int
    n_trials: int
    skew: float
    kurtosis: float
    var_sr: float
    var_sr_source: str
    passes: bool
    threshold: float


def psr(
    sr_hat_per_obs: float,
    sr_star: float,
    n_obs: int,
    skew: float,
    kurtosis: float,
) -> float:
    """Probabilistic Sharpe Ratio.

    All inputs in per-observation units. ``kurtosis`` is the raw (non-excess)
    fourth moment — 3.0 for a normal distribution.
    """
    if n_obs < 2:
        raise ValueError(f"n_obs must be >= 2; got {n_obs}")
    sr_se_sq = (
        1.0
        - skew * sr_hat_per_obs
        + ((kurtosis - 1.0) / 4.0) * sr_hat_per_obs ** 2
    )
    if sr_se_sq <= 0.0:
        # Pathological moments — PSR is undefined. Return 0 so a strategy
        # cannot accidentally pass via numerical chicanery.
        return 0.0
    z = (sr_hat_per_obs - sr_star) * math.sqrt(n_obs - 1) / math.sqrt(sr_se_sq)
    return _norm_cdf(z)


def expected_max_sharpe(n_trials: int, var_sr: float) -> float:
    """Deflated benchmark ``SR_star`` under the null, per-observation.

    The expected maximum Sharpe across ``n_trials`` independent zero-edge
    strategies whose Sharpe estimates have variance ``var_sr``.
    """
    if n_trials < 1:
        raise ValueError(f"n_trials must be >= 1; got {n_trials}")
    if var_sr < 0.0:
        raise ValueError(f"var_sr must be >= 0; got {var_sr}")
    if n_trials == 1:
        # No selection effect with a single trial. Phi_inv(0) would diverge.
        return 0.0
    sd_sr = math.sqrt(var_sr)
    q1 = _norm_ppf(1.0 - 1.0 / n_trials)
    q2 = _norm_ppf(1.0 - 1.0 / (n_trials * math.e))
    return sd_sr * ((1.0 - EULER_MASCHERONI) * q1 + EULER_MASCHERONI * q2)


def _estimated_var_sr(sr_per_obs: float, n_obs: int,
                      skew: float, kurtosis: float) -> float:
    """Sampling variance of a single per-observation Sharpe estimate."""
    return (1.0 / (n_obs - 1)) * (
        1.0 - skew * sr_per_obs + ((kurtosis - 1.0) / 4.0) * sr_per_obs ** 2
    )


def _moments(returns: np.ndarray) -> tuple[float, float, int]:
    """Return (per-obs SR, mean, std) — plus n_obs from the array length.

    Helper that centralises the per-observation Sharpe computation so the
    convention stays consistent everywhere.
    """
    n = returns.size
    mu = float(returns.mean())
    sd = float(returns.std(ddof=1))
    if sd <= 0.0:
        raise ValueError("returns have zero std; Sharpe is undefined.")
    return mu / sd, mu, sd


def _sample_skew_kurt(returns: np.ndarray) -> tuple[float, float]:
    """Sample skewness (biased) and raw kurtosis (normal = 3)."""
    x = returns - returns.mean()
    var = float((x ** 2).mean())
    if var <= 0.0:
        return 0.0, 3.0
    g3 = float((x ** 3).mean()) / (var ** 1.5)
    g4 = float((x ** 4).mean()) / (var ** 2)
    return g3, g4


def deflated_sharpe_ratio(
    returns: "np.ndarray | Sequence[float]",
    *,
    n_trials: Optional[int] = None,
    trial_sharpes: "np.ndarray | Sequence[float] | None" = None,
    var_sr: Optional[float] = None,
    periods_per_year: int = 252,
    threshold: float = DEFAULT_DSR_THRESHOLD,
    log_dir: Path = research_log.DEFAULT_LOG_DIR,
) -> DSRResult:
    """Compute the Deflated Sharpe Ratio for a strategy's return stream.

    Parameters
    ----------
    returns:
        1-D array of per-observation returns (daily, per-trade, etc.).
        Periodicity must match ``periods_per_year``.
    n_trials:
        Number of trials searched. If ``None``, reads the honest floor from
        ``research.log.trial_count()``.
    trial_sharpes:
        Optional per-observation Sharpe estimates from the N trials. If given,
        ``Var(SR)`` is their sample variance (``var_sr_source="empirical"``).
    var_sr:
        Explicit override for ``Var(SR)``. Mutually exclusive with
        ``trial_sharpes``. Sets ``var_sr_source="override"``.
    periods_per_year:
        For annualised display only. Never enters the DSR math.
    threshold:
        Acceptance cutoff for ``passes`` (default 0.95).
    log_dir:
        Where to read ``trial_count()`` from when ``n_trials`` is ``None``.

    Returns
    -------
    DSRResult
        Includes ``var_sr_source`` so the calculation is auditable.

    Raises
    ------
    ValueError
        If both ``trial_sharpes`` and ``var_sr`` are given; if the per-
        observation Sharpe exceeds :data:`MAX_PLAUSIBLE_PER_OBS_SR` (almost
        always a sign that an annualised Sharpe leaked in); if ``returns`` has
        zero std.
    """
    if trial_sharpes is not None and var_sr is not None:
        raise ValueError("Pass only one of trial_sharpes / var_sr, not both.")

    r = np.asarray(returns, dtype=float)
    if r.ndim != 1 or r.size < 2:
        raise ValueError(f"returns must be 1-D with >= 2 obs; got shape {r.shape}")

    sr_hat_per_obs, _, _ = _moments(r)
    if abs(sr_hat_per_obs) > MAX_PLAUSIBLE_PER_OBS_SR:
        raise ValueError(
            f"per-observation Sharpe |{sr_hat_per_obs:.3f}| > "
            f"{MAX_PLAUSIBLE_PER_OBS_SR}; this is almost certainly an "
            "annualised Sharpe leaking into a per-observation calculation. "
            "Pass raw per-period returns, not standardised/annualised values."
        )

    skew, kurtosis = _sample_skew_kurt(r)
    n_obs = int(r.size)

    if n_trials is None:
        n_trials = research_log.trial_count(log_dir=log_dir)
    n_trials = max(int(n_trials), 1)

    # Var(SR) source precedence: override > empirical > estimated.
    if var_sr is not None:
        var_sr_used = float(var_sr)
        var_sr_source = "override"
    elif trial_sharpes is not None:
        ts = np.asarray(trial_sharpes, dtype=float)
        if ts.size < 2:
            raise ValueError("trial_sharpes needs >= 2 values for sample variance.")
        var_sr_used = float(ts.var(ddof=1))
        var_sr_source = "empirical"
    else:
        var_sr_used = _estimated_var_sr(sr_hat_per_obs, n_obs, skew, kurtosis)
        var_sr_source = "estimated"

    sr_star = expected_max_sharpe(n_trials, var_sr_used)
    dsr_value = psr(sr_hat_per_obs, sr_star, n_obs, skew, kurtosis)
    psr_zero = psr(sr_hat_per_obs, 0.0, n_obs, skew, kurtosis)

    return DSRResult(
        dsr=dsr_value,
        psr_vs_zero=psr_zero,
        sr_star=sr_star,
        sr_hat_per_obs=sr_hat_per_obs,
        sr_hat_annualised=sr_hat_per_obs * math.sqrt(periods_per_year),
        n_obs=n_obs,
        n_trials=n_trials,
        skew=skew,
        kurtosis=kurtosis,
        var_sr=var_sr_used,
        var_sr_source=var_sr_source,
        passes=dsr_value > threshold,
        threshold=threshold,
    )


# ---------------------------------------------------------------------------
# Log integration
# ---------------------------------------------------------------------------

def log_dsr_evaluation(
    hypothesis_id: str,
    result: DSRResult,
    *,
    stage: "research_log.Stage" = research_log.Stage.OOS,
    log_dir: Path = research_log.DEFAULT_LOG_DIR,
) -> research_log.LogEntry:
    """Record a DSR evaluation as an UPDATE on the research log.

    ``counts_as_trial=False`` — evaluating a strategy is not a new trial, so
    DSR evaluations never inflate ``trial_count()``. Calling this at a later N
    produces a richer history that visibly shows the haircut tightening as
    the search space grew.
    """
    if not isinstance(result, DSRResult):
        raise TypeError("result must be a DSRResult")
    metrics = {
        "dsr": round(result.dsr, 6),
        "psr_vs_zero": round(result.psr_vs_zero, 6),
        "sr_star_per_obs": round(result.sr_star, 6),
        "sr_hat_annualised": round(result.sr_hat_annualised, 4),
        "n_trials": result.n_trials,
        "n_obs": result.n_obs,
        "var_sr_source": result.var_sr_source,
        "passes": result.passes,
    }
    verdict = (research_log.Verdict.PROMOTED if result.passes
               else research_log.Verdict.OPEN)
    note = (
        f"DSR evaluation at N={result.n_trials}: dsr={result.dsr:.4f} "
        f"(threshold={result.threshold}, "
        f"{'PASS' if result.passes else 'FAIL'}); "
        f"var_sr_source={result.var_sr_source}."
    )
    return research_log.update_hypothesis(
        hypothesis_id, stage=stage, verdict=verdict,
        metrics=metrics, note=note,
        counts_as_trial=False, log_dir=log_dir,
    )
