"""
research/engines/strategies/asq_scalping_adapter.py
===============================================
research.engines harness adapter for ASQ SafeScalping v1.20.

Mirrors the structure of hma_stoch.py so btpy_runner.py, run_walk_forward.py,
and score_a_strategy.py can consume ASQ identically to HMAStoch1H / HMAStochM15.

Drop this file into:
    packages/qh-research/research/engines/strategies/asq_scalping_adapter.py

And register in research/engines/strategies/__init__.py:
    from .asq_scalping_adapter import ASQScalpingM5

Usage (mirrors existing examples):
    from research.engines.strategies.asq_scalping_adapter import ASQScalpingM5
    from research.engines.btpy_runner import run_backtest, run_spread_stress
    from research.datasets.csv_loader import load_bars
    from research.datasets.cost_model import pepperstone_razor

    df   = load_csv('XAUUSD_M5.csv')
    cost = pepperstone_razor()
    result = run_backtest(df, ASQScalpingM5, cost, label='ASQ_M5_phase1')
    print(result)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import pandas as pd

# Strategy class lives alongside this adapter in the strategies package
from research.engines.strategies.asq_safe_scalping import ASQSafeScalping, attach_h1_mtf   # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# Phase presets
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ASQParams:
    """
    Parameter container for ASQ SafeScalping.

    All values mirror the .set file format.
    Four named constructors correspond to the four optimisation phases.
    """

    # EMA
    ema_fast       : int   = 50
    ema_slow       : int   = 200
    trend_strength : int   = 1        # 0=weak, 1=moderate, 2=strong

    # RSI
    rsi_period     : int   = 14
    rsi_buy_min    : float = 45.0
    rsi_buy_max    : float = 65.0
    rsi_sell_min   : float = 35.0
    rsi_sell_max   : float = 55.0

    # Breakout
    breakout_lookback : int   = 15
    breakout_buffer   : float = 0.3
    atr_period        : int   = 50

    # SL / TP
    sl_points : int = 300
    tp_points : int = 450

    # Breakeven
    use_breakeven    : bool = True
    breakeven_start  : int  = 150
    breakeven_offset : int  = 20

    # Trailing
    use_trailing : bool = True
    trail_start  : int  = 200
    trail_step   : int  = 100

    # Partial close
    use_partial_close : bool  = True
    tp1_points        : int   = 200
    tp1_close_pct     : float = 50.0

    # Risk
    risk_pct       : float = 0.5
    max_day_trades : int   = 4
    max_dd_pct     : float = 8.0

    # Session
    use_session   : bool = True
    session_start : int  = 8
    session_end   : int  = 17
    avoid_friday  : bool = True
    friday_cutoff : int  = 14

    # MTF
    use_mtf      : bool = False
    mtf_ema_fast : int  = 20
    mtf_ema_slow : int  = 50

    @classmethod
    def phase1_baseline(cls) -> "ASQParams":
        """Phase 1: all fixed, single structural backtest."""
        return cls()   # defaults are Phase 1 values

    @classmethod
    def phase2_risk(cls,
                    sl_points : int   = 300,
                    tp_points : int   = 450,
                    risk_pct  : float = 0.5) -> "ASQParams":
        """Phase 2: vary SL / TP / RiskPct around Phase 1 structure."""
        p = cls()
        p.sl_points = sl_points
        p.tp_points = tp_points
        p.risk_pct  = risk_pct
        return p

    @classmethod
    def phase3_exits(cls,
                     trail_start      : int = 200,
                     trail_step       : int = 100,
                     tp1_points       : int = 200,
                     breakeven_start  : int = 150,
                     sl_points        : int = 300,
                     tp_points        : int = 450,
                     risk_pct         : float = 0.5) -> "ASQParams":
        """Phase 3: vary exit management with Phase 2 winners locked."""
        p = cls.phase2_risk(sl_points, tp_points, risk_pct)
        p.trail_start     = trail_start
        p.trail_step      = trail_step
        p.tp1_points      = tp1_points
        p.breakeven_start = breakeven_start
        return p

    @classmethod
    def phase4_session(cls,
                       session_start  : int = 8,
                       session_end    : int = 17,
                       max_day_trades : int = 4,
                       friday_cutoff  : int = 14,
                       **phase3_kwargs) -> "ASQParams":
        """Phase 4: vary session window and day cap with Phase 3 winners locked."""
        p = cls.phase3_exits(**phase3_kwargs)
        p.session_start  = session_start
        p.session_end    = session_end
        p.max_day_trades = max_day_trades
        p.friday_cutoff  = friday_cutoff
        return p

    @classmethod
    def grid_optimised(cls) -> "ASQParams":
        """
        Grid-optimised preset from the .set file
        (Monte Carlo, 500 runs, Sharpe 1.27, 79% profitable).
        Use as a starting point for OOS validation — do not treat as
        the validated result until walk-forward confirms it.
        """
        p = cls()
        p.sl_points        = 300
        p.tp_points        = 450
        p.risk_pct         = 0.5
        p.breakeven_start  = 150
        p.trail_start      = 200
        p.trail_step       = 100
        p.tp1_points       = 200
        p.session_start    = 8
        p.session_end      = 17
        p.friday_cutoff    = 14
        p.max_day_trades   = 4
        return p

    def to_strategy_kwargs(self) -> dict:
        """Return a dict suitable for patching onto ASQSafeScalping class attrs."""
        return {k: v for k, v in self.__dict__.items()}


# ─────────────────────────────────────────────────────────────────────────────
# Harness-facing factory
# ─────────────────────────────────────────────────────────────────────────────

def make_asq_strategy(params: Optional[ASQParams] = None,
                      m5_df : Optional[pd.DataFrame] = None) -> type:
    """
    Return a *new* subclass of ASQSafeScalping with `params` baked in.

    Creating a fresh subclass each call is necessary because backtesting.py
    reads parameters as class attributes, and sharing a class across multiple
    Backtest() calls would cause parameter bleed-through.

    Args:
        params : ASQParams instance. Defaults to Phase 1 baseline.
        m5_df  : M5 DataFrame. If provided and params.use_mtf=True,
                 H1 close series is auto-attached via attach_h1_mtf().

    Returns:
        A Strategy subclass ready to pass to Backtest(...).
    """
    if params is None:
        params = ASQParams.phase1_baseline()

    attrs = params.to_strategy_kwargs()

    # Build unique class name so harness labels are human-readable
    cls = type(
        f"ASQSafeScalping_SL{params.sl_points}_TP{params.tp_points}",
        (ASQSafeScalping,),
        attrs,
    )

    if params.use_mtf and m5_df is not None:
        attach_h1_mtf(cls, m5_df)

    return cls


# ─────────────────────────────────────────────────────────────────────────────
# Convenience aliases (mirror HMAStoch1H / HMAStochM15 naming convention)
# ─────────────────────────────────────────────────────────────────────────────

#: Phase 1 baseline — pass directly to Backtest() or btpy_runner
ASQScalpingM5 = make_asq_strategy(ASQParams.phase1_baseline())

#: Grid-optimised preset — validate OOS before trusting
ASQScalpingM5_Optimised = make_asq_strategy(ASQParams.grid_optimised())


# ─────────────────────────────────────────────────────────────────────────────
# Walk-forward helper (mirrors run_walk_forward.py pattern)
# ─────────────────────────────────────────────────────────────────────────────

def run_asq_walk_forward(df           : pd.DataFrame,
                         params       : Optional[ASQParams] = None,
                         label        : str = 'ASQ_M5',
                         oos_months   : int = 12,
                         **wf_kwargs) -> object:
    """
    Convenience wrapper that chains make_asq_strategy() → run_walk_forward().

    Args:
        df         : M5 OHLCV DataFrame with UTC DatetimeIndex.
        params     : ASQParams. Defaults to Phase 1 baseline.
        label      : Name shown in SplitReport output.
        oos_months : OOS window per fold in months (default 12).
                     Consider 18 or 24 to address thin-fold trade count
                     (same issue diagnosed for H1 HMA+Stoch).
        **wf_kwargs: Passed through to run_walk_forward() — e.g.
                     exclude_ranges=PEPPERSTONE_XAUUSD_KNOWN_GAPS,
                     cost_model=pepperstone_razor().

    Returns:
        WalkForwardResult (same type as HMAStoch outputs).
    """
    # Import here to avoid circular deps at module load time
    from research.engines.btpy_runner import run_walk_forward         # noqa: PLC0415
    from research.datasets.cost_model import PepperstoneXAUUSDCostModel  # noqa: PLC0415

    if params is None:
        params = ASQParams.phase1_baseline()

    cost = wf_kwargs.pop('cost_model', PepperstoneXAUUSDCostModel())
    strategy_cls = make_asq_strategy(params, m5_df=df if params.use_mtf else None)

    return run_walk_forward(
        df           = df,
        strategy_cls = strategy_cls,
        cost_model   = cost,
        label        = label,
        oos_months   = oos_months,
        **wf_kwargs,
    )
