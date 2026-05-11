"""qhf.metrics.deflated — Probabilistic & Deflated Sharpe Ratios.

Implements
----------
- PSR  : Probabilistic Sharpe Ratio (Bailey & López de Prado 2012)
- DSR  : Deflated Sharpe Ratio (Bailey & López de Prado 2014)
- Expected maximum Sharpe under the null (extreme-value approximation).

Why this matters
----------------
A nominal Sharpe of 1.5 from "the best of 100 backtested variants" is NOT
the same as a Sharpe of 1.5 from a single hypothesis. The DSR penalises
for:

    1. Selection bias from N trials  (multiple-testing problem).
    2. Non-normality of returns      (skew, kurtosis).
    3. Sample length T               (more data => more confidence).

Output is a probability in [0, 1]: "Pr[ true SR > expected_max_under_null ]".
A high value (e.g. > 0.95) supports keeping the strategy.

References
----------
- Bailey, D. H., & López de Prado, M. (2012). "The Sharpe Ratio Efficient
  Frontier." Journal of Risk, 15(2).
- Bailey, D. H., & López de Prado, M. (2014). "The Deflated Sharpe Ratio:
  Correcting for Selection Bias, Backtest Overfitting and Non-Normality."
  Journal of Portfolio Management, 40(5).

Convention note
---------------
PSR's variance correction uses *per-period* SR & moments; this module
converts annualised SR variances to per-period internally. Consumers
pass annualised Sharpes and `periods_per_year`; we handle the rest.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

from qhf.metrics.core import _to_array, sharpe_ratio


_EULER_MASCHERONI = 0.5772156649015328606


def psr(sr_per_period: float, T: int,
        skew: float = 0.0, kurt_excess: float = 0.0,
        sr_benchmark_per_period: float = 0.0) -> float:
    """Probabilistic Sharpe Ratio.

    Pr[ true_SR > sr_benchmark ] given an observed per-period Sharpe over
    T periods, with sample skewness `skew` and excess kurtosis `kurt_excess`.

        PSR = Phi(  (SR - SR0) * sqrt(T - 1)
                  / sqrt(1 - skew*SR + ((kurt-1)/4) * SR**2)  )

    where kurt = kurt_excess + 3.

    Parameters
    ----------
    sr_per_period : float
        Observed per-period Sharpe (NOT annualised).
    T : int
        Number of return observations.
    skew : float
        Sample skewness of returns (scipy default convention).
    kurt_excess : float
        Sample excess kurtosis (Fisher; scipy default).
    sr_benchmark_per_period : float
        Per-period benchmark Sharpe to beat. Default 0.

    Returns
    -------
    p : float in [0, 1]
    """
    if T < 2:
        return float("nan")
    g4 = kurt_excess + 3.0
    denom_var = (1.0
                 - skew * sr_per_period
                 + ((g4 - 1.0) / 4.0) * sr_per_period ** 2)
    if denom_var <= 0 or not np.isfinite(denom_var):
        return float("nan")
    z = ((sr_per_period - sr_benchmark_per_period)
         * math.sqrt(T - 1) / math.sqrt(denom_var))
    return float(stats.norm.cdf(z))


def expected_max_sharpe(num_trials: int, sr_variance: float) -> float:
    """Expected MAXIMUM Sharpe under the null over N independent trials.

    From extreme value theory (Bailey & López de Prado 2014, eq. 8):

        E[ max{SR_n} ] ~~ sqrt(V[SR]) * (
            (1 - gamma_E) * Phi^{-1}(1 - 1/N)
          +  gamma_E      * Phi^{-1}(1 - 1/(N*e))
        )

    where gamma_E ~ 0.5772 is the Euler-Mascheroni constant.

    Parameters
    ----------
    num_trials : int
        Number of strategy variants tried (a.k.a. N).
        IMPORTANT: this should be the TOTAL trials over the research
        program, not just this run. If you previously tried 50 variants
        of a different strategy on this data, those count too.
    sr_variance : float
        Cross-sectional variance of the trial Sharpes, in the SAME period
        basis as the SR you'll deflate. (Per-period if comparing per-period
        SRs; annualised if comparing annualised SRs.)

    Returns
    -------
    sr_max : float
        Expected maximum Sharpe purely from selection / luck.
    """
    if num_trials < 1:
        return float("nan")
    if num_trials == 1:
        return 0.0
    n = num_trials
    z1 = stats.norm.ppf(1.0 - 1.0 / n)
    z2 = stats.norm.ppf(1.0 - 1.0 / (n * math.e))
    return float(math.sqrt(max(sr_variance, 0.0))
                 * ((1.0 - _EULER_MASCHERONI) * z1
                    + _EULER_MASCHERONI * z2))


def dsr(returns,
        num_trials: int,
        sr_variance_annualised: float,
        periods_per_year: int) -> dict:
    """Deflated Sharpe Ratio for a single strategy's returns.

    Computes:
    - Observed Sharpe (per-period and annualised).
    - Expected max Sharpe under the null given (num_trials, sr_variance).
    - DSR probability = PSR with benchmark = expected max under null.

    Parameters
    ----------
    returns : array-like
        Per-period (simple) returns of the strategy.
    num_trials : int
        Number of variants tried in the research program. Be honest:
        every parameter sweep cell, every discarded variant, counts.
    sr_variance_annualised : float
        Cross-sectional variance of trial annualised Sharpes.
    periods_per_year : int
        For annualisation conversions.

    Returns
    -------
    dict with keys:
        T                        sample size
        sharpe_obs_per_period
        sharpe_obs_annualised
        sr_benchmark_per_period
        sr_benchmark_annualised
        deflated_value_annualised  observed - benchmark, in Sharpe units
        dsr_probability            in [0, 1] -- main result
        skew, kurt_excess
        num_trials, sr_variance_annualised
        warning  (only if T < 30)
    """
    r = _to_array(returns)
    T = r.size
    out = {
        "T": T,
        "num_trials": num_trials,
        "sr_variance_annualised": sr_variance_annualised,
        "periods_per_year": periods_per_year,
    }
    if T < 30:
        out.update({
            "sharpe_obs_per_period": float("nan"),
            "sharpe_obs_annualised": float("nan"),
            "sr_benchmark_per_period": float("nan"),
            "sr_benchmark_annualised": float("nan"),
            "deflated_value_annualised": float("nan"),
            "dsr_probability": float("nan"),
            "skew": float("nan"),
            "kurt_excess": float("nan"),
            "warning": f"T={T} < 30 -- DSR not reliable.",
        })
        return out

    mu = float(r.mean())
    sd = float(r.std(ddof=1))
    if sd == 0 or not np.isfinite(sd):
        out.update({
            "sharpe_obs_per_period": float("nan"),
            "sharpe_obs_annualised": float("nan"),
            "sr_benchmark_per_period": float("nan"),
            "sr_benchmark_annualised": float("nan"),
            "deflated_value_annualised": float("nan"),
            "dsr_probability": float("nan"),
            "skew": float("nan"),
            "kurt_excess": float("nan"),
            "warning": "Zero / non-finite return std.",
        })
        return out

    sr_per = mu / sd
    sr_ann = sr_per * math.sqrt(periods_per_year)

    # Convert annualised SR variance -> per-period.
    # SR_ann = SR_per * sqrt(K) so Var(SR_ann) = K * Var(SR_per).
    sr_var_per = sr_variance_annualised / periods_per_year

    sr_max_per = expected_max_sharpe(num_trials, sr_var_per)
    sr_max_ann = sr_max_per * math.sqrt(periods_per_year)

    skew = float(stats.skew(r, bias=False))
    kurt_ex = float(stats.kurtosis(r, fisher=True, bias=False))

    p = psr(sr_per, T,
            skew=skew, kurt_excess=kurt_ex,
            sr_benchmark_per_period=sr_max_per)

    out.update({
        "sharpe_obs_per_period": sr_per,
        "sharpe_obs_annualised": sr_ann,
        "sr_benchmark_per_period": sr_max_per,
        "sr_benchmark_annualised": sr_max_ann,
        "deflated_value_annualised": sr_ann - sr_max_ann,
        "dsr_probability": p,
        "skew": skew,
        "kurt_excess": kurt_ex,
    })
    return out


def dsr_from_trials(returns_matrix: pd.DataFrame,
                    periods_per_year: int,
                    winner_col: Optional[str] = None,
                    extra_trials: int = 0) -> dict:
    """DSR when you have a returns matrix of N strategy variants.

    Picks the highest-Sharpe column (or `winner_col` if specified),
    estimates `sr_variance` from the cross-section, and deflates.

    Parameters
    ----------
    returns_matrix : pd.DataFrame
        T rows x N columns of per-period returns.
    periods_per_year : int
    winner_col : str, optional
        Column name to deflate (default: argmax-Sharpe column).
    extra_trials : int
        Add to N for trials run elsewhere (e.g. discarded variants of
        a different strategy on the same data). Be honest about this.

    Returns
    -------
    dict from `dsr(...)` plus:
        winner             : column name picked
        sr_variance_observed: cross-section variance of annualised Sharpes
        all_sharpes        : dict of {col: annualised Sharpe}
    """
    if returns_matrix.shape[1] < 2:
        raise ValueError("Need at least 2 trial columns to estimate "
                         "sr_variance from the cross-section.")
    sr_each = returns_matrix.apply(
        lambda c: sharpe_ratio(c, periods_per_year)
    )
    if winner_col is None:
        winner_col = str(sr_each.idxmax())
    sr_var_ann = float(sr_each.var(ddof=1))
    n_trials = returns_matrix.shape[1] + extra_trials
    out = dsr(returns_matrix[winner_col],
              num_trials=n_trials,
              sr_variance_annualised=sr_var_ann,
              periods_per_year=periods_per_year)
    out["winner"] = winner_col
    out["sr_variance_observed"] = sr_var_ann
    out["all_sharpes"] = sr_each.to_dict()
    return out
