"""qhf — Quant Harness for Forex.

A pre-registered, multiple-testing-aware validation harness for
discretionary-by-rule trading strategies (XAUUSD-focused).

Phase 1 (this delivery):
    - qhf.metrics.core       basic performance metrics
    - qhf.metrics.deflated   Probabilistic & Deflated Sharpe (BLDP)
    - qhf.metrics.pbo        Probability of Backtest Overfitting (CSCV)
    - qhf.validation.walk_forward  rolling/expanding split generators
    - qhf.reports.scorecard  gate evaluator with pre-registered thresholds

Phase 2 (next):
    - qhf.data.mt5_loader    XAUUSD bar loader from MetaTrader5
    - qhf.engines.vbt_runner VectorBT parameter-sweep wrapper
    - qhf.engines.btpy_runner backtesting.py path-dependent wrapper
    - qhf.validation.stress  spread/cost stress and parameter sensitivity
"""

__version__ = "0.1.0"
