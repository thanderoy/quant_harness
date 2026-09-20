"""Lo (2002) — annualising a Sharpe ratio when returns are not independent.

`sqrt(periods_per_year)` is not a conversion. It is a conversion *plus an
assumption*: that the per-period returns are serially independent. The
assumption is invisible at the call site, it is false for exactly the returns
this repo measures, and it fails in the flattering direction.

Lo, A. W. (2002), "The Statistics of Sharpe Ratios", *Financial Analysts
Journal* 58(4) — already in the README bibliography, and until now nowhere in
the code.

The correct factor is::

                              q
    eta(q) = --------------------------------------
             sqrt( q + 2 * sum_{k=1..q-1} (q-k)*rho_k )

With ``rho_k = 0`` for all k the sum vanishes and ``eta(q) = q/sqrt(q) =
sqrt(q)`` — the familiar formula, which is therefore the *special case*, not
the rule. Under **positive** autocorrelation the denominator grows and
``eta(q) < sqrt(q)``, so the naive factor **overstates** the annualised Sharpe.

Why that matters here rather than in general: a trend position held 50 bars
contributes 50 bar-returns that are positively autocorrelated by construction —
they are fifty slices of one directional move. At H1 the naive factor is
``sqrt(6048)`` ~ 77.8. If the true factor is even 15% lower, every Sharpe fed
to the gates is ~15% too high, and it is too high *before* DSR applies its
haircut and before PBO ranks anything. A gate cannot correct for an inflated
input it is never told about.

**Nothing here changes an existing number by default.** `sharpe_ratio` keeps
its IID behaviour unless asked, for the same reason the cost constants are not
silently re-priced: a metric that quietly changes meaning makes every recorded
result incomparable with every new one. What this module adds is the ability to
*measure* the inflation and to declare which annualisation produced a figure.

**A limit worth stating plainly: at bar-level frequencies this correction is
not estimable, and the module refuses rather than pretending.** Lo's sum at
``q=6048`` needs autocorrelations out to thousands of lags, weighted by up to
6048. Their sampling error accumulates faster than the bias they remove: on a
held-position process whose real dependence stops at lag 50, the estimated
omitted contribution *grows* from 1.7% at lag 150 to 35% at lag 5000, which is
noise, not structure. No bandwidth choice fixes it, so widening the window is
not offered as a remedy. A declared ``holding_period`` therefore makes the
refusal specific rather than making the number available.

The better fix, where it is available, is upstream: **trade-level returns are
close to independent** — one return per position, not fifty slices of one — so
feeding those sidesteps the correction rather than applying it. This module
exists for the cases where bar-level is what there is, and to quantify what
choosing bar-level costs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

__all__ = [
    "AnnualisationReport",
    "autocorrelations",
    "compare_annualisation",
    "lo_eta",
    "newey_west_lag",
    "BandwidthTooShort",
    "bandwidth_diagnostic",
]


def _clean(returns) -> np.ndarray:
    r = np.asarray(returns, dtype=float).ravel()
    return r[np.isfinite(r)]


def autocorrelations(returns, lags: int) -> np.ndarray:
    """Sample autocorrelations ``rho_1 .. rho_lags``.

    Uses the biased (divide by n) estimator, which is what Lo's derivation
    assumes and which is better behaved at long lags than the unbiased one —
    at lag k close to n the unbiased estimator divides by a handful of terms
    and produces values outside [-1, 1].
    """
    r = _clean(returns)
    n = r.size
    if n < 2 or lags < 1:
        return np.zeros(0)
    x = r - r.mean()
    denom = float(np.dot(x, x))
    if denom == 0:
        return np.zeros(min(lags, n - 1))
    m = min(lags, n - 1)
    # FFT rather than m dot products: Lo needs lags up to q-1, and at H1
    # (q=6048) the direct loop is thousands of passes over the whole series.
    size = 1 << (2 * n - 1).bit_length()
    f = np.fft.rfft(x, size)
    acov = np.fft.irfft(f * np.conjugate(f), size)[: m + 1]
    return (acov[1:] / denom).astype(float)


def newey_west_lag(n: int) -> int:
    """Standard truncation lag, ``floor(4 * (n/100)^(2/9))``."""
    return max(1, int(math.floor(4.0 * (n / 100.0) ** (2.0 / 9.0))))


class BandwidthTooShort(ValueError):
    """The truncation is cutting through live dependence.

    Raised rather than returned, because the number the estimator would have
    produced is not merely imprecise — it is biased toward *no correction*,
    which is the flattering direction and indistinguishable from a correct
    small correction.
    """


def bandwidth_diagnostic(returns, lag: int, q: int,
                         tolerance: float = 0.01,
                         n_sigma: float = 3.0) -> dict:
    """Is the truncation past the dependence, or through it?

    Two things had to be got right here, and the first attempt got both wrong.

    **The test is the omitted tail's contribution, not its significance.** At
    n=200,000 the noise floor is 0.0045, so a residual rho of 0.010 counts as
    "significant" while moving eta by well under a percent. Judging by
    significance refuses adequate bandwidths, and a guard that cries wolf gets
    switched off.

    **And the contribution must be measured against sampling noise.** Summing
    the tail directly makes the diagnostic measure its own estimation error:
    under no dependence each sample rho has variance ~1/n, and the sum
    ``2*sum_{k>lag}(q-k)*rho_k`` accumulates that noise with weights up to q.
    At n=150 and q=116 it reports a large omitted mass on a near-independent
    series, which is how the first version came to refuse everything it was
    shown.

    So the omitted mass is compared against its own standard error under the
    null, and only counts when it clears ``n_sigma`` of it *and* moves eta by
    more than ``tolerance``. Both conditions, because either alone
    misfires: significance without magnitude refuses good bandwidths, and
    magnitude without significance refuses small samples.
    """
    r = _clean(returns)
    n = r.size
    probe = min(max(int(lag * 4), lag + 50), n - 1)
    if probe <= lag or n < 20:
        return {"sufficient": True, "eta_shift": 0.0, "omitted_sigma": 0.0,
                "probe_lag": int(probe)}

    rho = autocorrelations(r, probe)
    k = np.arange(1, rho.size + 1)
    tail_k, tail_rho = k[lag:], rho[lag:]
    if tail_k.size == 0:
        return {"sufficient": True, "eta_shift": 0.0, "omitted_sigma": 0.0,
                "probe_lag": int(probe)}

    weights = (q - tail_k).astype(float)
    omitted = 2.0 * float(np.sum(weights * tail_rho))
    # Under the null rho_k ~ N(0, 1/n), independent across k.
    se = 2.0 * math.sqrt(float(np.sum(weights ** 2)) / n)
    sigmas = abs(omitted) / se if se > 0 else 0.0

    kept_k, kept_rho = k[:lag], rho[:lag]
    bart = 1.0 - kept_k / (lag + 1.0)
    var_kept = q + 2.0 * float(np.sum(bart * (q - kept_k) * kept_rho))
    var_all = var_kept + omitted
    if var_kept <= 0 or var_all <= 0:
        return {"sufficient": False, "eta_shift": float("inf"),
                "omitted_sigma": float(sigmas), "probe_lag": int(probe),
                "max_abs_rho_beyond": float(np.abs(tail_rho).max())}

    shift = abs(math.sqrt(var_all / var_kept) - 1.0)
    return {
        "sufficient": bool(sigmas <= n_sigma or shift <= tolerance),
        "eta_shift": float(shift),
        "omitted_sigma": float(sigmas),
        "max_abs_rho_beyond": float(np.abs(tail_rho).max()),
        "probe_lag": int(probe),
    }


def lo_eta(returns, q: int, max_lag: Optional[int] = None,
           holding_period: Optional[int] = None,
           check_bandwidth: bool = True) -> float:
    """Lo's annualisation factor for aggregating ``q`` periods.

    Returns ``sqrt(q)`` when the returns are serially uncorrelated, less than
    ``sqrt(q)`` under positive autocorrelation, and more under negative.

    **The sum is truncated and tapered, and it has to be.** Lo's formula runs
    the sum to lag ``q-1``. Evaluated literally with sample autocorrelations
    that is unusable at the sampling frequencies here: at ``q=6048`` it adds
    6047 noisy estimates weighted by up to 6047, and the accumulated sampling
    error swamps the signal. Measured on 200,000 genuinely IID draws the naive
    sum returns ``eta = 89.8`` against ``sqrt(q) = 77.8`` — a 15% error, in the
    *overstating* direction, at exactly the H1 case the correction exists for.
    A correction that inflates what it was meant to deflate is worse than none.

    So the estimator is Newey-West: truncate at ``max_lag`` and weight lag k by
    the Bartlett taper ``1 - k/(L+1)``. The taper also guarantees a
    non-negative variance term, which the raw sum does not. Default ``max_lag``
    is ``floor(4*(n/100)^(2/9))``; pass a larger one when the holding period is
    known to exceed it, since lags beyond the truncation are treated as zero.

    Raises
    ------
    ValueError
        If the variance term is non-positive — the sample cannot support a
        factor at this ``q``, and refusing beats a negative square root.
    """
    if q < 1:
        raise ValueError(f"q must be >= 1, got {q}")
    if q == 1:
        return 1.0
    r = _clean(returns)
    if r.size < 2:
        return math.sqrt(q)
    if max_lag is not None:
        lag = min(max_lag, q - 1, r.size - 1)
    elif holding_period is not None:
        # The hold sets the bandwidth, but see the module docstring: at
        # bar-level q this does not rescue the estimate, it only makes the
        # refusal informative.
        lag = min(3 * int(holding_period), q - 1, r.size - 1)
    else:
        lag = min(newey_west_lag(r.size), q - 1, r.size - 1)

    if check_bandwidth:
        diag = bandwidth_diagnostic(r, lag, q)
        if not diag["sufficient"]:
            raise BandwidthTooShort(
                f"truncating at lag {lag} omits enough dependence to move eta "
                f"by {diag['eta_shift']:.1%} (max |rho| beyond it "
                f"{diag['max_abs_rho_beyond']:.3f}). "
                "The truncation is cutting through live dependence, so eta "
                "would be biased toward no correction — the flattering "
                "direction. Pass holding_period=<bars a position is held> or "
                "an explicit max_lag past the dependence, or "
                "check_bandwidth=False to accept the bias deliberately.")
    rho = autocorrelations(r, lag)
    if rho.size == 0:
        return math.sqrt(q)
    k = np.arange(1, rho.size + 1)
    bartlett = 1.0 - k / (rho.size + 1.0)
    var_term = q + 2.0 * float(np.sum(bartlett * (q - k) * rho))
    if var_term <= 0:
        raise ValueError(
            f"autocorrelation structure gives a non-positive variance term "
            f"({var_term:.4g}) at q={q}; the sample cannot support an "
            "annualisation factor here")
    return q / math.sqrt(var_term)


@dataclass
class AnnualisationReport:
    """Both factors side by side, so the choice is visible rather than implied."""

    q: int
    sr_per_period: float
    eta_iid: float
    eta_lo: float
    sr_annualised_iid: float
    sr_annualised_lo: float
    rho_1: float
    mean_rho_first_10: float

    @property
    def inflation(self) -> float:
        """How much the IID factor exaggerates the Sharpe's MAGNITUDE.

        A magnitude statement on purpose. "Overstates" is only meaningful for
        a positive Sharpe: under positive autocorrelation the naive factor
        makes a good Sharpe look better *and a bad one look worse*, because it
        scales whatever sign is there. Reporting a signed ratio would call the
        second case an overstatement, which is backwards — and a test caught
        exactly that on an AR(1) draw that happened to have a negative mean.

        So: positive means the naive number is further from zero than Lo's.
        Whether that flatters the strategy depends on the sign of
        ``sr_per_period``.
        """
        lo = abs(self.sr_annualised_lo)
        if not math.isfinite(lo) or lo == 0:
            return float("nan")
        return abs(self.sr_annualised_iid) / lo - 1.0

    @property
    def flatters(self) -> bool:
        """True when the naive factor makes the strategy look better."""
        return self.sr_per_period > 0 and self.inflation > 0

    def as_dict(self) -> dict:
        return {
            "q": self.q,
            "sr_per_period": self.sr_per_period,
            "eta_iid": self.eta_iid,
            "eta_lo": self.eta_lo,
            "sr_annualised_iid": self.sr_annualised_iid,
            "sr_annualised_lo": self.sr_annualised_lo,
            "rho_1": self.rho_1,
            "mean_rho_first_10": self.mean_rho_first_10,
            "inflation": self.inflation,
        }


def compare_annualisation(returns, periods_per_year: int
                          ) -> AnnualisationReport:
    """Annualise the same Sharpe both ways and report the gap.

    This is the function to reach for before quoting an annualised Sharpe on
    bar-level returns: it says what the number is under each assumption and
    how far apart they are, instead of silently picking one.
    """
    r = _clean(returns)
    if r.size < 2:
        raise ValueError("need at least two finite returns")
    sd = r.std(ddof=1)
    if sd == 0 or not math.isfinite(sd):
        raise ValueError("zero or non-finite return standard deviation")
    sr_per = float(r.mean() / sd)

    eta_iid = math.sqrt(periods_per_year)
    eta_lo = lo_eta(r, periods_per_year)
    lag_used = min(newey_west_lag(r.size), periods_per_year - 1, r.size - 1)
    rho = autocorrelations(r, min(10, max(1, r.size - 1)))

    return AnnualisationReport(
        q=periods_per_year,
        sr_per_period=sr_per,
        eta_iid=eta_iid,
        eta_lo=eta_lo,
        sr_annualised_iid=sr_per * eta_iid,
        sr_annualised_lo=sr_per * eta_lo,
        rho_1=float(rho[0]) if rho.size else float("nan"),
        mean_rho_first_10=float(rho.mean()) if rho.size else float("nan"),
    )
