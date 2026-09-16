"""research.reports.scorecard — pre-registered gate evaluation.

Pre-registration discipline: thresholds are defined here, in code,
BEFORE inspecting any backtest's results. This is the same logic
behind clinical-trial pre-registration: prevents you from rationalising
a fail into a pass after the fact.

Default gates (Phase 1; align with the validation report's Phase 1 spec):

    is_oos_gap_max      = 0.5    IS-OOS Sharpe gap.
    pbo_max             = 0.5    Beats coin-flip overfitting.
    dsr_prob_min        = 0.95   Significant after multiple testing.
    max_dd_oos_max      = 0.30   Survivable OOS drawdown.
    n_trades_oos_min    = 30     Minimum statistical power.
    profit_factor_oos_min = 1.20

Production-target tightening (override Thresholds for live deployment):

    is_oos_gap_max      = 0.3
    pbo_max             = 0.3
    dsr_prob_min        = 0.99
    max_dd_oos_max      = 0.15
    n_trades_oos_min    = 100
    profit_factor_oos_min = 1.40
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import List, Optional


@dataclass
class Thresholds:
    """Gate thresholds. Override fields to tighten / loosen for context."""
    is_oos_gap_max: float = 0.5
    pbo_max: float = 0.5
    dsr_prob_min: float = 0.95
    max_dd_oos_max: float = 0.30
    n_trades_oos_min: int = 30
    profit_factor_oos_min: float = 1.20

    @classmethod
    def production(cls) -> "Thresholds":
        """Tighter gates for live-capital deployment."""
        return cls(
            is_oos_gap_max=0.3,
            pbo_max=0.3,
            dsr_prob_min=0.99,
            max_dd_oos_max=0.15,
            n_trades_oos_min=100,
            profit_factor_oos_min=1.40,
        )


@dataclass
class Result:
    """Bundle of metrics from a single strategy's backtest."""
    name: str
    is_sharpe: float
    oos_sharpe: float
    is_max_dd: float
    oos_max_dd: float
    n_trades_oos: int
    profit_factor_oos: float
    pbo: Optional[float] = None
    dsr_probability: Optional[float] = None

    @property
    def is_oos_gap(self) -> float:
        return self.is_sharpe - self.oos_sharpe


@dataclass
class GateReport:
    """Outcome of evaluating a Result against Thresholds."""
    strategy: str
    passed: bool
    failures: List[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def __str__(self) -> str:
        head = f"[{'PASS' if self.passed else 'FAIL'}] {self.strategy}"
        if not self.failures:
            return head
        return head + "\n  - " + "\n  - ".join(self.failures)


def evaluate(result: Result,
             thresholds: Optional[Thresholds] = None) -> GateReport:
    """Apply gates to a Result and return a GateReport."""
    t = thresholds or Thresholds()
    fails: List[str] = []

    if result.is_oos_gap > t.is_oos_gap_max:
        fails.append(
            f"IS-OOS Sharpe gap = {result.is_oos_gap:.2f} "
            f"> threshold {t.is_oos_gap_max} "
            "(strategy may be IS-overfit)."
        )
    if result.pbo is not None and result.pbo > t.pbo_max:
        fails.append(
            f"PBO = {result.pbo:.2f} > threshold {t.pbo_max} "
            "(IS-best strategies don't generalise OOS)."
        )
    if (result.dsr_probability is not None
            and result.dsr_probability < t.dsr_prob_min):
        fails.append(
            f"DSR probability = {result.dsr_probability:.3f} "
            f"< threshold {t.dsr_prob_min} "
            "(observed Sharpe not significant after multiple-testing)."
        )
    if result.oos_max_dd > t.max_dd_oos_max:
        fails.append(
            f"OOS max drawdown = {result.oos_max_dd:.1%} "
            f"> threshold {t.max_dd_oos_max:.1%}."
        )
    if result.n_trades_oos < t.n_trades_oos_min:
        fails.append(
            f"OOS trade count = {result.n_trades_oos} "
            f"< minimum {t.n_trades_oos_min} (insufficient power)."
        )
    if result.profit_factor_oos < t.profit_factor_oos_min:
        fails.append(
            f"OOS profit factor = {result.profit_factor_oos:.2f} "
            f"< minimum {t.profit_factor_oos_min}."
        )

    return GateReport(
        strategy=result.name,
        passed=len(fails) == 0,
        failures=fails,
        metrics=asdict(result),
    )
