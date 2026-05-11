"""qhf.metrics — performance metrics with multiple-testing corrections."""

from qhf.metrics.core import (
    sharpe_ratio,
    sortino_ratio,
    max_drawdown,
    calmar_ratio,
    profit_factor,
    win_rate,
    expectancy,
    cagr,
    sharpe_std_error,
    summarize,
    equity_curve,
)
from qhf.metrics.deflated import (
    psr,
    expected_max_sharpe,
    dsr,
    dsr_from_trials,
)
from qhf.metrics.pbo import pbo

__all__ = [
    "sharpe_ratio", "sortino_ratio", "max_drawdown", "calmar_ratio",
    "profit_factor", "win_rate", "expectancy", "cagr",
    "sharpe_std_error", "summarize", "equity_curve",
    "psr", "expected_max_sharpe", "dsr", "dsr_from_trials",
    "pbo",
]
