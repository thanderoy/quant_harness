"""research.pre.information_test — does a score carry information about the target?

The question comes before any trading rule. A score that ranks forward returns
can still lose money once a rule, a cost and a sizing scheme are put on it,
but a score that does not rank them cannot be rescued by any of the three. So
the score is tested on its own, as a continuous variable, against the forward
return it claims to predict:

* **Rank IC** — Spearman correlation of score and target. With a panel it is
  computed per period across instruments, which is the time fixed effect: a
  move common to every instrument that period is ranked out, so gold's drift
  cannot pass for information. With one instrument it is the time-series
  rank correlation, as the mean of the product of standardised ranks.
  Either way the t-stat is Newey-West, with the lag at least the horizon's
  overlap.
* **Monotonicity** — the target in score buckets, as excess over the period
  (or sample) mean, and the Spearman correlation of bucket order with it.
* **Conditional check** — the IC inside and outside a declared condition. The
  v3 registration names a failure condition, where the effect should vanish
  if the mechanism is right; this is where it is measured.

Two things are refused at registration, before any outcome is read, through
:func:`design`:

* a score that shares an input with the target's normalizer
  (:func:`research.pre.normalizer_check.assert_disjoint`, seq=69), and
* a prior IC the design cannot detect. The minimum detectable IC is
  ``(z_{1-α/2} + z_{power}) / sqrt(T_eff · N_eff)`` with
  ``T_eff = n_periods / horizon`` (overlapping targets are not independent)
  and ``N_eff = N / (1 + (N-1)·ρ̄)`` over the instruments (F1: nine
  correlated FX pairs are not nine observations). ``ρ̄`` is the mean
  absolute correlation of raw returns, as at seq=150 — no signal is read.

:func:`run` then refuses data shorter than the design promised, and returns
one p-value per stream for :mod:`research.pre.decisive_stream` to choose from.

>>> d = design("cross_sectional", n_periods=4000, n_instruments=9,
...            rho_bar=0.44, horizon=24, prior_ic=0.03,
...            score_inputs={"cot_net"}, target_normalizer=set())
Traceback (most recent call last):
    ...
research.post.mintrl.NotDecidable: ...
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats

from research.metrics.autocorr import newey_west_lag
from research.post.mintrl import DEFAULT_ALPHA, NotDecidable
from research.pre.daily_panel_power import n_eff
from research.pre.normalizer_check import assert_disjoint

__all__ = [
    "MODES",
    "STREAMS",
    "Design",
    "InformationResult",
    "design",
    "min_detectable_ic",
    "mean_abs_correlation",
    "nw_tstat",
    "run",
]

MODES = ("cross_sectional", "time_series")
#: The p-values :func:`run` emits, for ``decisive_stream.declare``.
STREAMS = ("ic", "ic_in_condition", "ic_out_condition")
DEFAULT_POWER = 0.8
DEFAULT_BUCKETS = 5
#: Fewest instruments a cross-sectional rank means anything over.
MIN_CROSS_SECTION = 3
#: Fewest IC observations a Newey-West t-stat is computed from.
MIN_NW_OBS = 30
COLUMNS = ("time", "instrument", "score", "target")


@dataclass(frozen=True)
class Design:
    mode: str
    n_periods: int
    n_instruments: int
    rho_bar: float
    horizon: int
    prior_ic: float
    alpha: float
    power: float
    t_eff: float
    n_eff: float
    min_detectable_ic: float


def min_detectable_ic(n_periods: int, n_instruments: int, rho_bar: float,
                      horizon: int, *, alpha: float = DEFAULT_ALPHA,
                      power: float = DEFAULT_POWER) -> tuple[float, float, float]:
    """``(mde, T_eff, N_eff)`` for a two-sided test at ``alpha`` and ``power``."""
    if n_periods < 2 or n_instruments < 1 or horizon < 1:
        raise ValueError("need n_periods >= 2, n_instruments >= 1, horizon >= 1")
    if not 0.0 <= rho_bar <= 1.0:
        raise ValueError(f"rho_bar must be in [0, 1]; got {rho_bar}")
    t_eff = n_periods / horizon
    ne = n_eff(n_instruments, rho_bar)
    z = stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power)
    return float(z / math.sqrt(t_eff * ne)), t_eff, ne


def design(mode: str, *, n_periods: int, n_instruments: int, rho_bar: float,
           horizon: int, prior_ic: float, score_inputs: set[str],
           target_normalizer: set[str], alpha: float = DEFAULT_ALPHA,
           power: float = DEFAULT_POWER, name: str = "score") -> Design:
    """Declare the test. Call at REGISTRATION, before any outcome exists.

    ``prior_ic`` is the absolute rank IC the mechanism claims. Raises
    :class:`NotDecidable` when the design could not detect it, and
    ``ContaminationError`` when the score and target share an input.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}; got {mode!r}")
    if mode == "cross_sectional" and n_instruments < MIN_CROSS_SECTION:
        raise ValueError(f"a cross-sectional rank needs >= {MIN_CROSS_SECTION} "
                         f"instruments; got {n_instruments}")
    if mode == "time_series" and n_instruments != 1:
        raise ValueError("time_series mode is one instrument; pool a panel "
                         "with cross_sectional, which carries the time effect")
    if not 0.0 < prior_ic < 1.0:
        raise ValueError(f"prior_ic must be in (0, 1); got {prior_ic}")
    assert_disjoint(score_inputs, target_normalizer, name=name)
    mde, t_eff, ne = min_detectable_ic(n_periods, n_instruments, rho_bar,
                                       horizon, alpha=alpha, power=power)
    if prior_ic < mde:
        raise NotDecidable(
            f"{name}: prior IC {prior_ic:.4f} is below the {mde:.4f} this "
            f"design can detect (T_eff={t_eff:.0f}, N_eff={ne:.2f}, "
            f"alpha={alpha}, power={power}). Lengthen the sample, widen the "
            f"panel with less correlated instruments, or drop the hypothesis.")
    return Design(mode, n_periods, n_instruments, rho_bar, horizon, prior_ic,
                  alpha, power, t_eff, ne, mde)


def mean_abs_correlation(returns: pd.DataFrame) -> float:
    """``ρ̄`` for :func:`design`: mean absolute pairwise correlation of a wide
    frame of raw returns (one column per instrument)."""
    c = returns.corr().to_numpy()
    iu = np.triu_indices_from(c, k=1)
    if iu[0].size == 0:
        return 0.0
    return float(np.nanmean(np.abs(c[iu])))


def nw_tstat(x: np.ndarray, lag: int) -> float:
    """Newey-West (Bartlett) t-stat of the mean; NaN under :data:`MIN_NW_OBS`."""
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    n = x.size
    if n < MIN_NW_OBS:
        return float("nan")
    e = x - math.fsum(x) / n
    var = math.fsum(e * e) / n
    for k in range(1, min(lag, n - 1) + 1):
        var += 2.0 * (1.0 - k / (lag + 1.0)) * math.fsum(e[k:] * e[:-k]) / n
    if var <= 0:
        return float("nan")
    return float((math.fsum(x) / n) / math.sqrt(var / n))


def _p(t: float) -> float:
    return float(2 * stats.norm.sf(abs(t))) if np.isfinite(t) else float("nan")


def _std_rank(s: pd.Series) -> pd.Series:
    r = s.rank()
    sd = r.std(ddof=0)
    return (r - r.mean()) / sd if sd > 0 else r * np.nan


def _ic_series(df: pd.DataFrame, mode: str) -> pd.Series:
    """One IC observation per period: cross-sectional Spearman, or the
    product of standardised ranks whose mean is the time-series Spearman."""
    if mode == "time_series":
        prod = _std_rank(df["score"]) * _std_rank(df["target"])
        return pd.Series(prod.to_numpy(), index=df["time"].to_numpy())
    g = df.groupby("time")
    sx = g["score"].rank()
    sy = g["target"].rank()
    keep = g["score"].transform("size") >= MIN_CROSS_SECTION
    ranked = pd.DataFrame({"time": df["time"], "x": sx, "y": sy})[keep]
    return ranked.groupby("time").apply(
        lambda f: f["x"].corr(f["y"]), include_groups=False).dropna()


def _ic_stats(ic: pd.Series, lag: int) -> dict:
    t = nw_tstat(ic.to_numpy(), lag)
    return {"ic": float(ic.mean()) if ic.size else float("nan"),
            "t": t, "p": _p(t), "n_periods": int(ic.size)}


def _buckets(df: pd.DataFrame, mode: str, n: int) -> dict:
    """Target by score bucket, as excess over the period (or sample) mean."""
    if mode == "cross_sectional":
        g = df.groupby("time")
        pct = g["score"].rank(pct=True)
        excess = df["target"] - g["target"].transform("mean")
    else:
        pct = df["score"].rank(pct=True)
        excess = df["target"] - df["target"].mean()
    b = np.minimum((pct * n).apply(math.ceil), n) - 1
    means = [float(excess[b == i].mean()) for i in range(n)]
    ok = [m for m in means if np.isfinite(m)]
    # Rounded: a perfect order otherwise reads 0.9999999999999999.
    rho = (round(float(stats.spearmanr(range(len(ok)), ok).statistic), 12)
           if len(ok) >= 3 else float("nan"))
    return {"excess_by_bucket": means, "monotonicity": rho}


@dataclass(frozen=True)
class InformationResult:
    design: Design
    lag: int
    overall: dict
    monotonicity: dict
    in_condition: Optional[dict]
    out_condition: Optional[dict]
    p_values: dict

    def to_dict(self) -> dict:
        return asdict(self)


def run(panel: pd.DataFrame, d: Design, *,
        condition: Optional[pd.Series] = None,
        n_buckets: int = DEFAULT_BUCKETS) -> InformationResult:
    """Measure the declared design on ``panel``.

    ``panel`` is long: one row per (time, instrument) with ``score`` known at
    ``time`` and ``target`` the forward return over the declared horizon.
    ``condition`` is a boolean Series indexed by time — True where the
    mechanism says the effect should be present.
    """
    missing = set(COLUMNS) - set(panel.columns)
    if missing:
        raise ValueError(f"panel lacks columns {sorted(missing)}")
    df = panel.loc[:, list(COLUMNS)].dropna().sort_values(["time", "instrument"])
    if d.mode == "time_series" and df["instrument"].nunique() != 1:
        raise ValueError("time_series design given a multi-instrument panel")
    n_periods = df["time"].nunique()
    if n_periods < d.n_periods:
        raise NotDecidable(
            f"the design was declared on {d.n_periods} periods and the data "
            f"has {n_periods}; the decidability promise does not hold")
    lag = max(d.horizon - 1, newey_west_lag(n_periods))
    ic = _ic_series(df, d.mode)
    overall = _ic_stats(ic, lag)
    p_values = {"ic": overall["p"]}
    inside = outside = None
    if condition is not None:
        cond = condition.reindex(ic.index).fillna(False).astype(bool).to_numpy()
        inside = _ic_stats(ic[cond], lag)
        outside = _ic_stats(ic[~cond], lag)
        p_values.update(ic_in_condition=inside["p"],
                        ic_out_condition=outside["p"])
    return InformationResult(d, lag, overall, _buckets(df, d.mode, n_buckets),
                             inside, outside, p_values)
