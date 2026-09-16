"""T7 — Minimum Track Record Length (Bailey & López de Prado).

    MinTRL = 1 + [1 − γ₃·SR + (γ₄−1)/4 · SR²] · (Z_α / (SR − SR*))²

How long a track record has to be before a Sharpe of ``SR`` can be
distinguished from a benchmark ``SR*`` at confidence ``1 − α``, given the
return distribution's skewness and kurtosis.

This module is the sibling of :mod:`research.post.dsr` and shares its
conventions exactly:

- **Per-observation units inside the math.** Annualisation is display-only.
  An annualised Sharpe passed in here silently returns a MinTRL that is
  wrong by the square of the annualisation factor, which is why
  :data:`research.post.dsr.MAX_PLAUSIBLE_PER_OBS_SR` exists and is reused.
- **``kurtosis`` is raw, not excess.** 3.0 is normal. The published formula
  is written with γ₄ as the fourth standardised moment, and passing excess
  kurtosis understates the required length.
- **Stdlib only.** No numpy, no scipy.

The normal quantile is imported from :mod:`research.post.dsr` rather than
re-derived. Two hand-rolled inverse CDFs agreeing to eight digits and
disagreeing at the ninth is exactly the silent drift the DSR parity contract
exists to prevent, and it would be perverse to introduce it here.

The pre-registration filter
---------------------------
MinTRL answers "how much data would I need?". Turned around, it answers the
question worth asking *before* the compute is spent: **given the data I
actually have, what is the smallest effect I could detect?**
:func:`min_decidable_sharpe` inverts the formula for SR, and
:func:`screen` wraps it as a go/no-go on a hypothesis.

This matters because the alternative is arriving at a result that was never
decidable and arguing about it afterwards. A hypothesis whose plausible
effect size sits below the floor cannot produce evidence either way on the
sample it will be run against — running it anyway generates a number, not a
finding. The floor is recorded on the pre-registration itself as
``min_decidable_sharpe`` (log schema v2, T6), so the claim that a result was
decidable is checkable rather than remembered.

    >>> floor = min_decidable_sharpe(n_obs=1000, sr_star=0.02,
    ...                              skew=-0.5, kurtosis=6.0)
    >>> round(floor, 6)
    0.073155
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from research.post.dsr import MAX_PLAUSIBLE_PER_OBS_SR, _norm_ppf

__all__ = [
    "MinTRLResult",
    "ScreenResult",
    "NotDecidable",
    "sharpe_variance_factor",
    "min_trl",
    "min_decidable_sharpe",
    "screen",
    "assert_decidable",
    "DEFAULT_ALPHA",
]

#: One-sided significance level. Matches the DSR convention.
DEFAULT_ALPHA: float = 0.05


@dataclass
class MinTRLResult:
    min_trl: float
    min_trl_obs: Optional[int]
    sr_hat_per_obs: float
    sr_star: float
    edge: float
    skew: float
    kurtosis: float
    alpha: float
    z_alpha: float
    variance_factor: float
    decidable: bool
    reason: str


@dataclass
class ScreenResult:
    decidable: bool
    sr_plausible: float
    min_decidable_sharpe: Optional[float]
    headroom: Optional[float]
    n_obs: int
    sr_star: float
    skew: float
    kurtosis: float
    alpha: float
    reason: str


class NotDecidable(ValueError):
    """The intended sample cannot decide the effect the hypothesis claims.

    Raised by :func:`assert_decidable` at pre-registration. Not a warning:
    the point is to spend the refusal before the compute, because afterwards
    there is a number on the table and the argument is no longer about power.
    """


def _guard_sr(sr: float, name: str) -> None:
    if not math.isfinite(sr):
        raise ValueError(f"{name} must be finite; got {sr}")
    if abs(sr) > MAX_PLAUSIBLE_PER_OBS_SR:
        raise ValueError(
            f"{name}={sr} exceeds {MAX_PLAUSIBLE_PER_OBS_SR} per observation, "
            f"which almost always means an annualised Sharpe leaked into a "
            f"per-observation argument. MinTRL would come back wrong by the "
            f"square of the annualisation factor and still look reasonable."
        )


def _guard_moments(kurtosis: float, alpha: float) -> None:
    if kurtosis < 1.0:
        raise ValueError(
            f"kurtosis={kurtosis} is below 1.0. Note this is RAW kurtosis "
            f"(normal = 3.0), not excess — passing excess kurtosis here "
            f"understates the required track record."
        )
    if not (0.0 < alpha < 0.5):
        raise ValueError(f"alpha must be in (0, 0.5); got {alpha}")


def sharpe_variance_factor(sr_per_obs: float, skew: float,
                           kurtosis: float) -> float:
    """``1 − γ₃·SR + (γ₄−1)/4·SR²`` — the bracket in both PSR and MinTRL.

    The same quantity :func:`research.post.dsr.psr` calls ``sr_se_sq``. It is
    the estimation variance of the Sharpe under non-normal returns, scaled by
    ``n − 1``, and it is what makes negative skew and fat tails expensive:
    both push it up, and it multiplies the whole track-record requirement.

    Can go non-positive under extreme moments, at which point the Sharpe's
    sampling distribution is not usable and neither is anything built on it.
    """
    return 1.0 - skew * sr_per_obs + ((kurtosis - 1.0) / 4.0) * sr_per_obs ** 2


def min_trl(
    sr_hat_per_obs: float,
    sr_star: float = 0.0,
    *,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    alpha: float = DEFAULT_ALPHA,
) -> MinTRLResult:
    """Observations needed for ``sr_hat_per_obs`` to beat ``sr_star``.

    Returns a result rather than a bare float so the inputs travel with the
    number — a MinTRL quoted without its α, its benchmark and its moments is
    not checkable, and this one is meant to be recorded.

    ``min_trl`` is the exact real-valued requirement; ``min_trl_obs`` is that
    rounded up, because you cannot observe a fractional bar.
    """
    _guard_sr(sr_hat_per_obs, "sr_hat_per_obs")
    _guard_sr(sr_star, "sr_star")
    _guard_moments(kurtosis, alpha)

    z = _norm_ppf(1.0 - alpha)
    edge = sr_hat_per_obs - sr_star
    v = sharpe_variance_factor(sr_hat_per_obs, skew, kurtosis)

    def _undecidable(reason: str) -> MinTRLResult:
        return MinTRLResult(
            min_trl=math.inf, min_trl_obs=None,
            sr_hat_per_obs=sr_hat_per_obs, sr_star=sr_star, edge=edge,
            skew=skew, kurtosis=kurtosis, alpha=alpha, z_alpha=z,
            variance_factor=v, decidable=False, reason=reason)

    if edge <= 0.0:
        # The formula squares the edge, so a Sharpe *below* the benchmark
        # would otherwise return a finite, plausible-looking length. No
        # sample length makes an effect that points the wrong way decidable.
        return _undecidable(
            "sr_hat_per_obs does not exceed sr_star; no track record length "
            "can establish an edge that is not there")
    if v <= 0.0:
        return _undecidable(
            f"variance factor {v:.6g} is non-positive under skew={skew}, "
            f"kurtosis={kurtosis}; the Sharpe's sampling distribution is "
            f"unusable and so is any length derived from it")

    n = 1.0 + v * (z / edge) ** 2
    return MinTRLResult(
        min_trl=n, min_trl_obs=math.ceil(n),
        sr_hat_per_obs=sr_hat_per_obs, sr_star=sr_star, edge=edge,
        skew=skew, kurtosis=kurtosis, alpha=alpha, z_alpha=z,
        variance_factor=v, decidable=True,
        reason=f"decidable in {math.ceil(n)} observations")


def min_decidable_sharpe(
    n_obs: int,
    sr_star: float = 0.0,
    *,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    alpha: float = DEFAULT_ALPHA,
) -> Optional[float]:
    """The smallest per-observation Sharpe ``n_obs`` bars could establish.

    MinTRL inverted. Substituting ``SR = SR* + d`` into

        n − 1 = [1 − γ₃·SR + (γ₄−1)/4·SR²] · (Z/d)²

    and expanding the bracket around ``SR*`` gives a plain quadratic in the
    edge ``d``:

        d²·[(n−1) − Z²·a]  −  Z²·B·d  −  Z²·A  =  0

        a = (γ₄−1)/4
        A = 1 − γ₃·SR* + a·SR*²        (the bracket evaluated at SR*)
        B = 2·a·SR* − γ₃               (its slope in d)

    The positive root is the answer; the negative one is the mirror solution
    below the benchmark, which the squared edge admits and reality does not.

    Returns ``None`` when the leading coefficient is non-positive — with
    heavy enough tails the variance term grows at least as fast as the sample
    can pay for it, and no Sharpe is decidable at this length at all. That is
    a real answer about a short sample, not an error.
    """
    if n_obs < 2:
        raise ValueError(f"n_obs must be >= 2; got {n_obs}")
    _guard_sr(sr_star, "sr_star")
    _guard_moments(kurtosis, alpha)

    z = _norm_ppf(1.0 - alpha)
    zz = z * z
    a = (kurtosis - 1.0) / 4.0
    A = 1.0 - skew * sr_star + a * sr_star ** 2
    B = 2.0 * a * sr_star - skew

    c2 = (n_obs - 1) - zz * a
    if c2 <= 0.0:
        return None
    if A <= 0.0:
        # The bracket is already non-positive at the benchmark itself.
        return None

    c1 = -zz * B
    c0 = -zz * A
    disc = c1 * c1 - 4.0 * c2 * c0
    if disc < 0.0:
        return None
    d = (-c1 + math.sqrt(disc)) / (2.0 * c2)
    if d <= 0.0:
        return None
    return sr_star + d


def screen(
    sr_plausible: float,
    n_obs: int,
    sr_star: float = 0.0,
    *,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    alpha: float = DEFAULT_ALPHA,
) -> ScreenResult:
    """Is ``sr_plausible`` large enough to be detectable in ``n_obs`` bars?

    ``sr_plausible`` is the effect the hypothesis claims — the honest prior,
    written down before the run. Compare it with the floor rather than with
    whatever comes back.
    """
    _guard_sr(sr_plausible, "sr_plausible")
    floor = min_decidable_sharpe(n_obs, sr_star, skew=skew,
                                 kurtosis=kurtosis, alpha=alpha)
    if floor is None:
        return ScreenResult(
            decidable=False, sr_plausible=sr_plausible,
            min_decidable_sharpe=None, headroom=None, n_obs=n_obs,
            sr_star=sr_star, skew=skew, kurtosis=kurtosis, alpha=alpha,
            reason=(f"no Sharpe is decidable in {n_obs} observations under "
                    f"skew={skew}, kurtosis={kurtosis}: the estimation "
                    f"variance outruns the sample"))
    ok = sr_plausible >= floor
    return ScreenResult(
        decidable=ok, sr_plausible=sr_plausible,
        min_decidable_sharpe=floor, headroom=sr_plausible - floor,
        n_obs=n_obs, sr_star=sr_star, skew=skew, kurtosis=kurtosis,
        alpha=alpha,
        reason=(f"plausible SR {sr_plausible:.4f} clears the "
                f"{floor:.4f} floor for {n_obs} observations"
                if ok else
                f"plausible SR {sr_plausible:.4f} is below the {floor:.4f} "
                f"floor for {n_obs} observations; this sample cannot decide "
                f"the claim either way"))


def assert_decidable(
    sr_plausible: float,
    n_obs: int,
    sr_star: float = 0.0,
    *,
    skew: float = 0.0,
    kurtosis: float = 3.0,
    alpha: float = DEFAULT_ALPHA,
    name: str = "hypothesis",
) -> ScreenResult:
    """:func:`screen`, but refusing instead of reporting.

    Call it at pre-registration. Returns the result when the sample can
    decide the claim, raises :class:`NotDecidable` when it cannot.
    """
    result = screen(sr_plausible, n_obs, sr_star, skew=skew,
                    kurtosis=kurtosis, alpha=alpha)
    if not result.decidable:
        raise NotDecidable(
            f"{name}: {result.reason}. Either lengthen the sample, raise the "
            f"claimed effect to something the data could actually show, or "
            f"drop the hypothesis — running it produces a number, not a "
            f"finding."
        )
    return result
