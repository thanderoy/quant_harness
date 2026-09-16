"""research.engines — backtesting engine wrappers."""

from research.engines.btpy_runner import (
    run_backtest,
    run_walk_forward,
    run_spread_stress,
    BtRunResult,
    WalkForwardResult,
    FoldResult,
    SpreadStressResult,
    PEPPERSTONE_XAUUSD_KNOWN_GAPS,
)
from research.engines.strategies import HMAStoch1H, HMAStochM15, ASQSafeScalping, EbbNFlow

__all__ = [
    "run_backtest",
    "run_walk_forward",
    "run_spread_stress",
    "BtRunResult",
    "WalkForwardResult",
    "FoldResult",
    "SpreadStressResult",
    "PEPPERSTONE_XAUUSD_KNOWN_GAPS",
    "HMAStoch1H",
    "HMAStochM15",
    "ASQSafeScalping",
    "EbbNFlow",
]
