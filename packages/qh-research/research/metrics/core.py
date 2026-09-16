"""research.metrics.core — basic backtest performance metrics.

All functions accept a 1-D pandas Series or numpy array of returns
(simple, NOT log) and an explicit `periods_per_year` for annualisation.

Conventions
-----------
- Returns are simple per-period returns (e.g. 0.01 for +1%).
- `periods_per_year`:
    daily equity bars      -> 252
    daily forex bars       -> 252  (5 days/wk x ~50 wk)
    hourly forex bars      -> 6048 (252 * 24)
    weekly                 -> 52
    trade-level returns    -> trades_per_year (estimate from sample)
- Risk-free rate `rf` is annualised; we convert internally.

References
----------
- Lo, A. (2002) "The Statistics of Sharpe Ratios", FAJ.
- Mertens, E. (2002) "Variance of the IID estimator of the Sharpe ratio".
- Pardo, R. (2008) The Evaluation and Optimization of Trading Strategies.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def _to_array(x) -> np.ndarray:
    """Coerce input to a 1-D float numpy array, dropping NaNs."""
    if isinstance(x, pd.Series):
        return x.dropna().to_numpy(dtype=float)
    arr = np.asarray(x, dtype=float)
    return arr[~np.isnan(arr)]


def equity_curve(returns, initial: float = 1.0) -> pd.Series:
    """Compound a returns stream into an equity curve."""
    r = _to_array(returns)
    if r.size == 0:
        return pd.Series([initial], dtype=float)
    return pd.Series(initial * np.cumprod(1.0 + r))


def sharpe_ratio(returns, periods_per_year: int, rf: float = 0.0) -> float:
    """Annualised Sharpe ratio.

    SR = (mean(r) - rf_per_period) / std(r) * sqrt(periods_per_year)

    Returns NaN if std == 0, T < 2, or non-finite.
    """
    r = _to_array(returns)
    if r.size < 2:
        return float("nan")
    rf_per = rf / periods_per_year
    excess = r - rf_per
    sd = excess.std(ddof=1)
    if sd == 0 or not np.isfinite(sd):
        return float("nan")
    return float(excess.mean() / sd * np.sqrt(periods_per_year))


def sortino_ratio(returns, periods_per_year: int,
                  rf: float = 0.0, mar: float = 0.0) -> float:
    """Annualised Sortino — downside-deviation-based Sharpe analogue.

    Uses Minimum Acceptable Return `mar` (annualised) as the threshold;
    default 0 (penalise only outright losses, not relative underperformance).
    """
    r = _to_array(returns)
    if r.size < 2:
        return float("nan")
    rf_per = rf / periods_per_year
    mar_per = mar / periods_per_year
    excess = r - rf_per
    downside = np.minimum(r - mar_per, 0.0)
    dd = np.sqrt(np.mean(downside ** 2))
    if dd == 0 or not np.isfinite(dd):
        return float("inf") if excess.mean() > 0 else float("nan")
    return float(excess.mean() / dd * np.sqrt(periods_per_year))


def max_drawdown(returns) -> float:
    """Maximum peak-to-trough drawdown as a positive fraction.

    e.g. 0.20 => 20% drawdown.
    """
    eq = equity_curve(returns)
    if len(eq) < 2:
        return 0.0
    peak = eq.cummax()
    dd = (eq - peak) / peak
    return float(-dd.min())


def cagr(returns, periods_per_year: int) -> float:
    """Compound annual growth rate from a returns stream."""
    r = _to_array(returns)
    if r.size == 0:
        return float("nan")
    final = float((1.0 + r).prod())
    if final <= 0:
        return float("nan")  # blew up — undefined CAGR
    years = r.size / periods_per_year
    if years <= 0:
        return float("nan")
    return float(final ** (1.0 / years) - 1.0)


def calmar_ratio(returns, periods_per_year: int) -> float:
    """CAGR / |max drawdown|. NaN if either undefined."""
    c = cagr(returns, periods_per_year)
    mdd = max_drawdown(returns)
    if mdd == 0 or not np.isfinite(mdd) or not np.isfinite(c):
        return float("nan")
    return float(c / mdd)


def profit_factor(returns) -> float:
    """Sum of positive returns / absolute sum of negative returns."""
    r = _to_array(returns)
    if r.size == 0:
        return float("nan")
    gains = r[r > 0].sum()
    losses = -r[r < 0].sum()
    if losses == 0:
        return float("inf") if gains > 0 else float("nan")
    return float(gains / losses)


def win_rate(returns) -> float:
    """Fraction of strictly positive returns."""
    r = _to_array(returns)
    if r.size == 0:
        return float("nan")
    return float((r > 0).sum() / r.size)


def expectancy(returns) -> float:
    """Mean per-period (or per-trade) return."""
    r = _to_array(returns)
    if r.size == 0:
        return float("nan")
    return float(r.mean())


def sharpe_std_error(sharpe: float, T: int,
                     skew: float = 0.0, kurt_excess: float = 0.0) -> float:
    """Standard error of an estimated Sharpe under non-normal returns.

    Mertens (2002), restated in Bailey & López de Prado (2014):

        Var(SR_hat) = (1 - skew*SR + ((kurt-1)/4) * SR**2) / (T-1)

    where `kurt` is the *raw* kurtosis (3 for normal). If you pass excess
    kurtosis (default scipy convention), this function adds 3 internally.

    The Sharpe `sharpe` and the moments must be in the SAME period basis
    (typically per-period, NOT annualised).
    """
    if T < 2:
        return float("nan")
    g4 = kurt_excess + 3.0
    var = (1.0 - skew * sharpe + ((g4 - 1.0) / 4.0) * sharpe ** 2) / (T - 1)
    if var < 0 or not np.isfinite(var):
        return float("nan")
    return float(np.sqrt(var))


def summarize(returns, periods_per_year: int) -> dict:
    """One-shot dict of every standard metric.

    Useful for serialising into a strategy-research log.
    """
    r = _to_array(returns)
    return {
        "n_periods": int(r.size),
        "sharpe": sharpe_ratio(r, periods_per_year),
        "sortino": sortino_ratio(r, periods_per_year),
        "max_drawdown": max_drawdown(r),
        "calmar": calmar_ratio(r, periods_per_year),
        "cagr": cagr(r, periods_per_year),
        "profit_factor": profit_factor(r),
        "win_rate": win_rate(r),
        "expectancy": expectancy(r),
    }
