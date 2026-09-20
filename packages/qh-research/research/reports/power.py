"""Measured power of the gate stack — can this harness pass anything?

Two scenarios are a sanity check: noise fails, obvious alpha passes. They
establish that the arithmetic is not inverted. They do not establish the thing
that actually matters after five consecutive falsifications, which is the
**joint false-negative rate of six AND-ed gates**.

That question is not rhetorical. Six gates each rejecting independently at
10% would pass a genuine edge only 53% of the time, and a run of five
rejections is then unremarkable whether or not any mechanism had an edge. Until
the rate is measured, "the mechanism failed" and "the stack rejects nearly
everything" produce identical evidence, and no further falsification can
distinguish them. Running a sixth mechanism before measuring this would produce
a result nobody could interpret.

So: inject alpha at a known annualised Sharpe among noise strategies, run the
whole stack exactly as a real evaluation would, and record how often it passes.
Sweeping the injected Sharpe gives a power curve, and the level at which the
curve crosses a useful pass rate is the harness's **empirical detection floor**
— `min_decidable_sharpe` measured rather than derived, which is the direct test
of R8's decidability gate.

Three details that decide whether the number means anything:

**The winner is selected, not handed over.** Each trial scores whichever column
the sweep picks, exactly as the demo and a real run do. At low injected Sharpe
the sweep often picks a noise column instead, and that misselection is part of
the power being measured rather than something to correct for.

**Sharpe 0.0 is included.** A power curve without its false-positive rate is
half a measurement: a stack that passes 90% of real edges is worthless if it
also passes 50% of noise. The 0.0 row is the type-I rate and should be near
zero.

**Per-gate attribution is recorded.** "Pass rate 20%" is not actionable; "DSR
rejected 78% of them" is. With gates AND-ed, one dominant rejector sets the
joint rate, and it is the only one worth arguing about.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np
import pandas as pd

from research.metrics.core import sharpe_ratio, summarize
from research.metrics.deflated import dsr_from_trials
from research.metrics.pbo import pbo
from research.reports.scorecard import Result, Thresholds, evaluate

__all__ = [
    "GATE_NAMES",
    "PowerCurve",
    "PowerPoint",
    "detection_floor",
    "power_curve",
]

#: Default injected levels. 0.0 is the false-positive row and is not optional.
DEFAULT_LEVELS = (0.0, 0.3, 0.5, 0.8, 1.2, 1.5)

#: Gate labels, matched against the prose `evaluate` emits. Kept as a mapping
#: rather than parsed loosely so a reworded failure message shows up as an
#: unattributed rejection instead of being silently miscounted.
GATE_NAMES = {
    "IS-OOS Sharpe gap": "is_oos_gap",
    "PBO": "pbo",
    "DSR probability": "dsr",
    "OOS max drawdown": "max_dd",
    "OOS trades": "n_trades",
    "OOS profit factor": "profit_factor",
}


def _attribute(failures: Sequence[str]) -> list[str]:
    out = []
    for f in failures:
        for prefix, name in GATE_NAMES.items():
            if f.startswith(prefix):
                out.append(name)
                break
        else:
            out.append("unattributed")
    return out


@dataclass
class PowerPoint:
    """One injected Sharpe level."""

    injected_sharpe: float
    n_trials: int
    n_passed: int
    gate_failures: Counter = field(default_factory=Counter)
    winner_was_alpha: int = 0

    @property
    def pass_rate(self) -> float:
        return self.n_passed / self.n_trials if self.n_trials else float("nan")

    @property
    def selection_rate(self) -> float:
        """How often the sweep picked the column alpha was injected into."""
        return (self.winner_was_alpha / self.n_trials
                if self.n_trials else float("nan"))

    def dominant_gate(self) -> Optional[str]:
        return self.gate_failures.most_common(1)[0][0] if self.gate_failures else None


@dataclass
class PowerCurve:
    points: list[PowerPoint] = field(default_factory=list)
    thresholds_name: str = "research"
    periods_per_year: int = 252
    n_strategies: int = 20

    @property
    def false_positive_rate(self) -> float:
        for p in self.points:
            if p.injected_sharpe == 0.0:
                return p.pass_rate
        return float("nan")

    def as_dict(self) -> dict:
        return {
            "thresholds": self.thresholds_name,
            "periods_per_year": self.periods_per_year,
            "n_strategies": self.n_strategies,
            "false_positive_rate": self.false_positive_rate,
            "detection_floor": detection_floor(self),
            "points": [
                {"injected_sharpe": p.injected_sharpe,
                 "n_trials": p.n_trials,
                 "pass_rate": p.pass_rate,
                 "selection_rate": p.selection_rate,
                 "dominant_gate": p.dominant_gate(),
                 "gate_failures": dict(p.gate_failures)}
                for p in self.points
            ],
        }


def detection_floor(curve: PowerCurve, target: float = 0.5) -> Optional[float]:
    """Lowest injected Sharpe whose pass rate reaches ``target``.

    ``None`` means the curve never gets there — which is the finding, not a
    missing value: a stack that cannot pass an injected Sharpe of 1.5 half the
    time will not pass a real mechanism either.
    """
    for p in sorted(curve.points, key=lambda x: x.injected_sharpe):
        if p.injected_sharpe > 0 and p.pass_rate >= target:
            return p.injected_sharpe
    return None


def _panel(rng, target_sharpe: float, T: int, n: int, ppy: int,
           sigma: float, alpha_idx: int) -> pd.DataFrame:
    """Noise, with one column carrying a known annualised Sharpe.

    ``mu = SR_ann * sigma / sqrt(ppy)`` inverts the annualisation, so the
    injected column has the target Sharpe *in expectation*. Its realised
    Sharpe varies by sampling, which is correct — a real mechanism's measured
    Sharpe is a draw too.
    """
    data = rng.normal(0.0, sigma, size=(T, n))
    if target_sharpe:
        data[:, alpha_idx] += target_sharpe * sigma / math.sqrt(ppy)
    return pd.DataFrame(data, columns=[f"s_{i:02d}" for i in range(n)])


def _score_one(M: pd.DataFrame, ppy: int, thresholds: Thresholds):
    """Run the stack exactly as an evaluation would, and return its verdict."""
    pbo_res = pbo(M, S=16, periods_per_year=ppy)
    dsr_res = dsr_from_trials(M, periods_per_year=ppy)
    winner = dsr_res["winner"]

    wr = M[winner]
    half = len(wr) // 2
    is_part, oos_part = wr.iloc[:half], wr.iloc[half:]
    full = summarize(wr, ppy)
    res = Result(
        name=winner,
        is_sharpe=sharpe_ratio(is_part, ppy),
        oos_sharpe=sharpe_ratio(oos_part, ppy),
        is_max_dd=full["max_drawdown"],
        oos_max_dd=full["max_drawdown"],
        n_trades_oos=len(oos_part),
        profit_factor_oos=full["profit_factor"],
        pbo=pbo_res["pbo"],
        dsr_probability=dsr_res["dsr_probability"],
    )
    return evaluate(res, thresholds), winner


def power_curve(levels: Sequence[float] = DEFAULT_LEVELS,
                n_trials: int = 100,
                n_strategies: int = 20,
                T: int = 2000,
                periods_per_year: int = 252,
                sigma: float = 0.01,
                thresholds: Optional[Thresholds] = None,
                thresholds_name: str = "research",
                seed: int = 0) -> PowerCurve:
    """Measure pass rate against injected Sharpe."""
    t = thresholds or Thresholds()
    curve = PowerCurve(thresholds_name=thresholds_name,
                       periods_per_year=periods_per_year,
                       n_strategies=n_strategies)
    alpha_idx = 5

    for level in levels:
        point = PowerPoint(injected_sharpe=float(level), n_trials=n_trials,
                           n_passed=0)
        for trial in range(n_trials):
            rng = np.random.default_rng(
                seed + trial * 1000 + int(level * 100))
            M = _panel(rng, level, T, n_strategies, periods_per_year, sigma,
                       alpha_idx)
            report, winner = _score_one(M, periods_per_year, t)
            if winner == f"s_{alpha_idx:02d}":
                point.winner_was_alpha += 1
            if report.passed:
                point.n_passed += 1
            else:
                point.gate_failures.update(_attribute(report.failures))
        curve.points.append(point)
    return curve
