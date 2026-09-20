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


def lo_eta(returns, q: int, max_lag: Optional[int] = None) -> float:
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
    lag = max_lag if max_lag is not None else newey_west_lag(r.size)
    lag = min(lag, q - 1, r.size - 1)
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
