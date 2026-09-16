"""research.engines.btpy_runner — backtesting.py engine wrapper.

Provides two entry points:

    run_backtest(bars, strategy_cls, ...)
        Single-period backtest. Returns BtRunResult with trades, equity
        curve, and per-trade return series ready for harness metrics.

    run_walk_forward(bars, strategy_cls, ...)
        Walk-forward backtest over rolling train/test splits.
        Returns WalkForwardResult with IS/OOS metrics per fold and
        aggregated across folds.

Cost model integration
----------------------
backtesting.py 0.6.5 supports two cost channels:

    spread  : fraction of entry price, applied at fill time.
              Models the fixed bid-ask spread as a price-adverse fill.
              At XAUUSD $2400, $0.22/oz spread → spread=0.22/2400≈0.0000917.

    commission : callable (size_oz, price) → dollar_amount per ORDER.
              Applied on both open and close of each trade.
              $7 RT / lot / 100 oz = $0.035/oz per order side.

Swap is NOT natively supported by backtesting.py. It is applied as a
post-processing adjustment to each trade's PnL using the cost model's
`swap_usd()` method, BEFORE metrics are computed.

Unit convention
---------------
size = lots × 100  (oz per lot, XAUUSD standard lot = 100 oz)
All PnL in USD (account currency). All returns are per-trade ReturnPct
from backtesting.py (PnL / account equity at trade entry).

Annualisation
-------------
For trade-level returns: periods_per_year ≈ trades_per_year (estimated
from trade count and observation span). Pass explicitly if you prefer
a fixed value (e.g. H1 bar-based = 6048). Default is AUTO (estimated).

Known limitations
-----------------
- Spread is proportional to price (backtesting.py constraint). True
  XAUUSD spread is ~$0.22/oz regardless of price. Error: ±15% at
  $1800-$2800 range; acceptable for research.
- Session, Friday-cutoff, and daily-cap filters are strategy-agnostic
  here. Slice bar data to desired session before calling run_backtest.
- HTF (H1) confirmation filter in ASQ is not modelled.
- backtesting.py uses fractional lots (oz); minimum representable size
  depends on strategy's calculate_lot_size output.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Type

import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy

from research.datasets.cost_model import PepperstoneXAUUSDCostModel
from research.metrics.core import (
    sharpe_ratio, max_drawdown, profit_factor, cagr,
)
from research.reports.scorecard import Result
from research.validation.walk_forward import (
    rolling_splits_with_report, SplitReport,
)

# Default excluded gaps for Pepperstone XAUUSD history.
PEPPERSTONE_XAUUSD_KNOWN_GAPS = [
    ("2025-09-12", "2025-10-15"),  # 32-day broker-history hole (all TFs)
    ("2026-01-13", "2026-01-22"),  # 9-day broker-history hole (H4/M5/D1)
]

# OHLCV columns that backtesting.py requires (case-sensitive).
_REQUIRED_COLS = {"Open", "High", "Low", "Close"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_bt_df(bars: pd.DataFrame) -> pd.DataFrame:
    """Rename OHLCV columns to backtesting.py Title-Case convention."""
    rename = {"open": "Open", "high": "High", "low": "Low",
              "close": "Close", "volume": "Volume"}
    df = bars.rename(columns=rename)
    missing = _REQUIRED_COLS - set(df.columns)
    if missing:
        raise ValueError(
            f"bars DataFrame is missing required columns: {missing}. "
            f"Got: {list(df.columns)}"
        )
    # backtesting.py needs Volume if present; it's optional.
    cols = [c for c in ["Open", "High", "Low", "Close", "Volume"]
            if c in df.columns]
    return df[cols].copy()


def _commission_callable(
    cost_model: PepperstoneXAUUSDCostModel,
) -> callable:
    """Return a callable (size_oz, price) → commission_usd per order."""
    per_lot_per_side = cost_model.commission_per_lot_round_turn / 2.0
    per_oz_per_side = per_lot_per_side / 100.0  # 1 lot = 100 oz

    def _commission(size_oz: float, price: float) -> float:  # noqa: ARG001
        return abs(size_oz) * per_oz_per_side

    return _commission


def _spread_fraction(cost_model: PepperstoneXAUUSDCostModel,
                     approx_price: float = 2400.0) -> float:
    """Convert fixed-dollar spread to backtesting.py's fractional format."""
    return cost_model.spread_usd_per_oz / approx_price


def _apply_swap(trades: pd.DataFrame,
                cost_model: PepperstoneXAUUSDCostModel) -> pd.DataFrame:
    """Subtract swap cost from each trade's PnL and ReturnPct in-place.

    backtesting.py does not model overnight financing. We apply it as a
    post-processing step so the trade-level returns seen by the harness
    reflect the full round-trip cost including carry.
    """
    if trades.empty:
        return trades

    trades = trades.copy()
    swap_cost = np.zeros(len(trades))
    for i, row in trades.iterrows():
        direction = "BUY" if row.get("Size", 1) > 0 else "SELL"
        size_lots = abs(row.get("Size", 0)) / 100.0
        if size_lots == 0:
            continue
        entry = row["EntryTime"].to_pydatetime() if hasattr(row["EntryTime"], "to_pydatetime") else row["EntryTime"]
        exit_ = row["ExitTime"].to_pydatetime() if hasattr(row["ExitTime"], "to_pydatetime") else row["ExitTime"]
        swap_usd, _, _ = cost_model.swap_usd(size_lots, direction, entry, exit_)
        swap_cost[trades.index.get_loc(i)] = swap_usd
    trades["SwapCost"] = swap_cost
    trades["PnL"] = trades["PnL"] + trades["SwapCost"]
    # Recompute ReturnPct approximately (swap change is small vs position size).
    # ReturnPct from backtesting.py = PnL / equity_at_entry — we adjust PnL.
    # Since we can't recover exact equity_at_entry without the equity curve,
    # we adjust proportionally: new_ret = old_ret * (new_pnl / old_pnl).
    # Zero-PnL guard: if original PnL was 0, leave ReturnPct as-is.
    nonzero = trades["PnL"] != 0
    old_pnl_before_swap = trades["PnL"] - trades["SwapCost"]
    ratio = np.where(
        (nonzero) & (old_pnl_before_swap != 0),
        trades["PnL"] / old_pnl_before_swap,
        1.0,
    )
    trades["ReturnPct"] = trades["ReturnPct"] * ratio
    return trades


def _estimate_periods_per_year(trades: pd.DataFrame) -> float:
    """Estimate annualisation factor from trade frequency."""
    if len(trades) < 2:
        return 252.0
    span_days = (trades["ExitTime"].max() - trades["EntryTime"].min()).days
    if span_days <= 0:
        return 252.0
    trades_per_year = len(trades) / (span_days / 365.25)
    return max(trades_per_year, 1.0)


def _apply_session_filter(bars: pd.DataFrame,
                           session_hours: Optional[tuple]) -> pd.DataFrame:
    """Filter bars to a UTC-hour session window.

    Parameters
    ----------
    bars : pd.DataFrame
        OHLCV DataFrame with DatetimeIndex in UTC.
    session_hours : (start_hour, end_hour_exclusive) or None
        e.g. (8, 17) keeps bars where 8 <= hour < 17.
        None returns bars unchanged.

    Limitation
    ----------
    Pre-filtering changes indicator computation: HMA, ATR and Stochastic
    are calculated on session-only bars, not all-hours bars. The overnight
    gap between session close and next session open is treated as a
    normal 1-bar gap for indicator purposes. This slightly underestimates
    ATR across sessions. Acceptable for research; for production, compute
    indicators on all bars and restrict signal generation to session hours.
    """
    if session_hours is None:
        return bars
    start_h, end_h = session_hours
    mask = (bars.index.hour >= start_h) & (bars.index.hour < end_h)
    filtered = bars.loc[mask]
    if filtered.empty:
        raise ValueError(
            f"Session filter ({start_h}:00–{end_h}:00 UTC) removed all bars. "
            "Check that timestamps are UTC and session_hours is correct."
        )
    return filtered


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class BtRunResult:
    """Result from a single backtesting.py run."""
    strategy_name: str
    start: pd.Timestamp
    end: pd.Timestamp
    n_bars: int
    n_trades: int
    stats: dict                     # raw backtesting.py stats dict
    trades: pd.DataFrame            # trade-level data with swap applied
    equity_curve: pd.DataFrame      # from stats._equity_curve
    return_pct_series: pd.Series    # per-trade ReturnPct for harness metrics

    # Computed from trade-level returns
    sharpe: float = float("nan")
    max_dd: float = float("nan")
    pf: float = float("nan")

    def _compute_metrics(self, periods_per_year: Optional[int] = None):
        """Compute harness metrics from trade-level returns.

        NOTE: `periods_per_year` here is used only as a fallback when there
        are too few trades to estimate frequency. For trade-level returns the
        correct annualisation is trades_per_year, NOT the bar-based
        periods_per_year (H1=6048, M15=24192). Using the bar count would
        inflate Sharpe by sqrt(bar_ppy / trades_ppy) — e.g. 24x for H1.
        """
        r = self.return_pct_series
        if r.empty:
            return
        # Always estimate from actual trade frequency.
        ppy = (_estimate_periods_per_year(self.trades)
               if len(self.trades) >= 2
               else (periods_per_year or 52))
        self.sharpe = sharpe_ratio(r, int(round(ppy)))
        self.max_dd = max_drawdown(r)
        self.pf = profit_factor(r)
        return self

    def summary_str(self) -> str:
        return (
            f"BtRunResult: {self.strategy_name}  "
            f"{self.start.date()} -> {self.end.date()}\n"
            f"  trades: {self.n_trades}   sharpe: {self.sharpe:.2f}   "
            f"max_dd: {self.max_dd:.1%}   PF: {self.pf:.2f}"
        )


@dataclass
class FoldResult:
    """IS + OOS result for one walk-forward fold."""
    fold_index: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    is_result: BtRunResult
    oos_result: BtRunResult


@dataclass
class WalkForwardResult:
    """Aggregated walk-forward result across all non-excluded folds."""
    strategy_name: str
    folds: List[FoldResult]
    split_report: SplitReport

    # Aggregate metrics (computed across all OOS folds)
    oos_return_pct: pd.Series = field(default_factory=pd.Series)
    is_sharpes: List[float] = field(default_factory=list)
    oos_sharpes: List[float] = field(default_factory=list)

    # Overall summary statistics
    mean_is_sharpe: float = float("nan")
    oos_sharpe: float = float("nan")    # Sharpe of concatenated OOS returns
    is_oos_gap: float = float("nan")
    oos_max_dd: float = float("nan")
    n_trades_oos: int = 0
    oos_profit_factor: float = float("nan")

    def to_scorecard_result(
        self, name: Optional[str] = None,
        num_trials: int = 1,
        sr_variance_annualised: Optional[float] = None,
        periods_per_year: int = 252,
    ) -> Result:
        """Build a Result object ready for research.reports.scorecard.evaluate().

        Parameters
        ----------
        num_trials : int
            Total strategy variants tested on this dataset. Honest count
            (every parameter sweep cell, every discarded variant).
        sr_variance_annualised : float, optional
            Cross-sectional variance of IS Sharpes from a parameter sweep.
            If None, estimated from the fold-level IS Sharpes.
        periods_per_year : int
            Annualisation basis. Use 6048 for H1, 24192 for M15.
        """
        n = name or self.strategy_name
        sr_var = sr_variance_annualised
        if sr_var is None and len(self.is_sharpes) > 1:
            sr_var = float(pd.Series(self.is_sharpes).var(ddof=1))
        elif sr_var is None:
            sr_var = 0.5   # rough fallback

        return Result(
            name=n,
            is_sharpe=self.mean_is_sharpe,
            oos_sharpe=self.oos_sharpe,
            is_max_dd=float(max_drawdown(
                pd.concat([f.is_result.return_pct_series
                           for f in self.folds
                           if not f.is_result.return_pct_series.empty])
            )),
            oos_max_dd=self.oos_max_dd,
            n_trades_oos=self.n_trades_oos,
            profit_factor_oos=self.oos_profit_factor,
            pbo=None,    # populate separately from pbo() if needed
            dsr_probability=None,   # populate separately from dsr()
        )

    def summary_str(self) -> str:
        lines = [
            f"WalkForwardResult: {self.strategy_name}",
            f"  folds used: {len(self.folds)} / "
            f"{self.split_report.total_folds} total",
            f"  mean IS Sharpe : {self.mean_is_sharpe:.2f}",
            f"  OOS Sharpe     : {self.oos_sharpe:.2f}",
            f"  IS-OOS gap     : {self.is_oos_gap:+.2f}",
            f"  OOS max DD     : {self.oos_max_dd:.1%}",
            f"  OOS trades     : {self.n_trades_oos}",
            f"  OOS profit fac.: {self.oos_profit_factor:.2f}",
        ]
        if self.split_report.folds_excluded:
            lines.append(f"  excluded folds : {len(self.split_report.folds_excluded)}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core runner: single backtest
# ---------------------------------------------------------------------------


def run_backtest(
    bars: pd.DataFrame,
    strategy_cls: Type[Strategy],
    params: Optional[Dict] = None,
    cash: float = 10_000,
    cost_model: Optional[PepperstoneXAUUSDCostModel] = None,
    finalize_trades: bool = True,
    periods_per_year: Optional[int] = None,
    approx_gold_price: float = 2400.0,
    session_hours: Optional[tuple] = None,
) -> BtRunResult:
    """Run a single-period backtest with full cost modeling.

    Parameters
    ----------
    bars : pd.DataFrame
        OHLCV DataFrame from research.datasets.load_bars(). Index must be
        DatetimeIndex. Columns may be lowercase (open, high, low, close)
        or Title-Case — both are handled.
    strategy_cls : Type[Strategy]
        A backtesting.py Strategy subclass (e.g. HMAStoch1H, HMAStochM15).
    params : dict, optional
        Strategy attribute overrides passed to bt.run(**params).
    cash : float
        Starting account equity. Use 10_000 for a meaningful OOS sample
        even if your live account is $100 — the lot sizer scales to equity.
    cost_model : PepperstoneXAUUSDCostModel, optional
        Defaults to standard Pepperstone Razor MT5 cost model.
    finalize_trades : bool
        Close open positions at backtest end (recommended for OOS periods).
    periods_per_year : int, optional
        For Sharpe annualisation. If None, estimated from trade frequency.
    approx_gold_price : float
        Used for spread-to-fraction conversion. Default $2400/oz.

    Returns
    -------
    BtRunResult
        Contains trades (with swap applied), equity curve, and pre-computed
        harness metrics.
    """
    if cost_model is None:
        cost_model = PepperstoneXAUUSDCostModel()

    bars = _apply_session_filter(bars, session_hours)
    bt_df = _build_bt_df(bars)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        bt = Backtest(
            bt_df,
            strategy_cls,
            cash=cash,
            spread=_spread_fraction(cost_model, approx_gold_price),
            commission=_commission_callable(cost_model),
            margin=1.0 / 400.0,
            trade_on_close=False,
            exclusive_orders=True,
            finalize_trades=finalize_trades,
        )
        stats = bt.run(**(params or {}))

    trades = stats._trades.copy() if hasattr(stats, "_trades") else pd.DataFrame()
    equity_curve = stats._equity_curve.copy() if hasattr(stats, "_equity_curve") else pd.DataFrame()

    if not trades.empty:
        trades = _apply_swap(trades, cost_model)

    ret_pct = (trades["ReturnPct"] if not trades.empty
               else pd.Series(dtype=float))

    result = BtRunResult(
        strategy_name=strategy_cls.__name__,
        start=pd.Timestamp(bt_df.index[0]),
        end=pd.Timestamp(bt_df.index[-1]),
        n_bars=len(bt_df),
        n_trades=len(trades),
        stats=dict(stats),
        trades=trades,
        equity_curve=equity_curve,
        return_pct_series=ret_pct,
    )
    result._compute_metrics(periods_per_year)
    return result


# ---------------------------------------------------------------------------
# Walk-forward runner
# ---------------------------------------------------------------------------


def run_walk_forward(
    bars: pd.DataFrame,
    strategy_cls: Type[Strategy],
    params: Optional[Dict] = None,
    train_size: str = "1460D",
    test_size: str = "365D",
    step_size: Optional[str] = None,
    purge: str = "0D",
    exclude_ranges=None,
    cash: float = 10_000,
    cost_model: Optional[PepperstoneXAUUSDCostModel] = None,
    periods_per_year: Optional[int] = None,
    approx_gold_price: float = 2400.0,
    session_hours: Optional[tuple] = None,
    verbose: bool = True,
) -> WalkForwardResult:
    """Walk-forward backtest with IS/OOS split and gap exclusion.

    Runs `run_backtest` on each (train, test) pair from rolling_splits.
    Folds that overlap `exclude_ranges` are skipped and reported.

    Parameters
    ----------
    bars : pd.DataFrame
        Full bar history (OHLCV).
    strategy_cls : Type[Strategy]
        Strategy to evaluate.
    params : dict, optional
        Strategy attribute overrides.
    train_size, test_size, step_size : str
        Walk-forward window sizes. e.g. "1460D" / "365D".
    purge : str
        Gap between train end and test start to avoid leakage.
    exclude_ranges : list of (start, end), optional
        Defaults to PEPPERSTONE_XAUUSD_KNOWN_GAPS if None.
    cash : float
        Starting cash for each fold (reset per fold).
    cost_model : PepperstoneXAUUSDCostModel, optional
    periods_per_year : int, optional
        For Sharpe annualisation. If None, estimated per fold.
    verbose : bool
        Print fold progress.

    Returns
    -------
    WalkForwardResult
    """
    if cost_model is None:
        cost_model = PepperstoneXAUUSDCostModel()
    if exclude_ranges is None:
        exclude_ranges = PEPPERSTONE_XAUUSD_KNOWN_GAPS

    # Apply session filter before splitting so walk-forward windows
    # are computed on session-only bar timestamps.
    bars = _apply_session_filter(bars, session_hours)

    report = SplitReport()
    folds: List[FoldResult] = []

    splits = list(rolling_splits_with_report(
        bars,
        train_size=train_size,
        test_size=test_size,
        step_size=step_size,
        purge=purge,
        exclude_ranges=exclude_ranges,
        report=report,
    ))

    if verbose:
        print(f"Walk-forward: {len(splits)} folds "
              f"({len(report.folds_excluded)} excluded)")

    for fold_idx, (train, test) in enumerate(splits):
        if verbose:
            print(f"  Fold {fold_idx+1}/{len(splits)}: "
                  f"train {train.index[0].date()} -> {train.index[-1].date()}  |  "
                  f"test {test.index[0].date()} -> {test.index[-1].date()}  ", end="")

        is_result = run_backtest(
            train, strategy_cls, params=params,
            cash=cash, cost_model=cost_model,
            finalize_trades=True,
            periods_per_year=periods_per_year,
            approx_gold_price=approx_gold_price,
            session_hours=None,  # already filtered at the top
        )
        oos_result = run_backtest(
            test, strategy_cls, params=params,
            cash=cash, cost_model=cost_model,
            finalize_trades=True,
            periods_per_year=periods_per_year,
            approx_gold_price=approx_gold_price,
            session_hours=None,  # already filtered at the top
        )

        oos_flag = " ⚠ low trades" if oos_result.n_trades < 10 else ""
        if verbose:
            print(f"IS trades={is_result.n_trades} SR={is_result.sharpe:.2f}  |  "
                  f"OOS trades={oos_result.n_trades} SR={oos_result.sharpe:.2f}{oos_flag}")

        folds.append(FoldResult(
            fold_index=fold_idx,
            train_start=train.index[0],
            train_end=train.index[-1],
            test_start=test.index[0],
            test_end=test.index[-1],
            is_result=is_result,
            oos_result=oos_result,
        ))

    # --- Aggregate -----------------------------------------------------------

    all_oos_series = [f.oos_result.return_pct_series for f in folds
                      if not f.oos_result.return_pct_series.empty]
    all_oos_returns = (pd.concat(all_oos_series, ignore_index=True)
                       if all_oos_series else pd.Series(dtype=float))

    is_sharpes = [f.is_result.sharpe for f in folds]
    oos_sharpes = [f.oos_result.sharpe for f in folds]
    n_trades_oos = sum(f.oos_result.n_trades for f in folds)

    all_oos_trades = pd.concat(
        [f.oos_result.trades for f in folds if not f.oos_result.trades.empty],
        ignore_index=True,
    ) if folds else pd.DataFrame()

    ppy = int(round(
        _estimate_periods_per_year(all_oos_trades)
        if not all_oos_trades.empty and len(all_oos_trades) >= 2
        else (periods_per_year or 52)
    ))

    oos_sharpe = (sharpe_ratio(all_oos_returns, ppy)
                  if not all_oos_returns.empty else float("nan"))
    mean_is_sharpe = (float(np.nanmean(is_sharpes))
                      if is_sharpes else float("nan"))
    oos_max_dd = (max_drawdown(all_oos_returns)
                  if not all_oos_returns.empty else float("nan"))
    oos_pf = (profit_factor(all_oos_returns)
              if not all_oos_returns.empty else float("nan"))

    wf = WalkForwardResult(
        strategy_name=strategy_cls.__name__,
        folds=folds,
        split_report=report,
        oos_return_pct=all_oos_returns,
        is_sharpes=is_sharpes,
        oos_sharpes=oos_sharpes,
        mean_is_sharpe=mean_is_sharpe,
        oos_sharpe=oos_sharpe,
        is_oos_gap=mean_is_sharpe - oos_sharpe,
        oos_max_dd=oos_max_dd,
        n_trades_oos=n_trades_oos,
        oos_profit_factor=oos_pf,
    )
    return wf


# ---------------------------------------------------------------------------
# Spread stress test
# ---------------------------------------------------------------------------


@dataclass
class SpreadStressResult:
    """Result of running the same walk-forward at multiple spread levels."""
    strategy_name: str
    multipliers: List[float]
    results: List[WalkForwardResult]
    base_spread_usd_per_oz: float

    def summary_str(self) -> str:
        lines = [
            f"Spread stress test: {self.strategy_name}",
            f"  base spread: ${self.base_spread_usd_per_oz}/oz  "
            f"(Pepperstone Razor typical)",
            f"",
            f"  {'Multiplier':>11}  {'Spread $/oz':>11}  "
            f"{'OOS Sharpe':>10}  {'OOS PF':>7}  "
            f"{'OOS DD':>7}  {'Trades':>7}  Gate",
        ]
        for mult, wf in zip(self.multipliers, self.results):
            spread = self.base_spread_usd_per_oz * mult
            pf_flag = "✅" if wf.oos_profit_factor >= 1.20 else "❌"
            sharpe_flag = "✅" if wf.oos_sharpe > 0 else "❌"
            lines.append(
                f"  {mult:>9.1f}×  "
                f"  ${spread:>8.2f}  "
                f"{wf.oos_sharpe:>10.2f}  "
                f"{wf.oos_profit_factor:>7.2f}  "
                f"{wf.oos_max_dd:>6.1%}  "
                f"{wf.n_trades_oos:>7}  "
                f"{sharpe_flag}{pf_flag}"
            )
        return "\n".join(lines)

    @property
    def base_result(self) -> WalkForwardResult:
        """The 1× (baseline) result."""
        return self.results[0] if self.results else None

    def survives_stress(self, pf_threshold: float = 1.20) -> bool:
        """True if OOS profit factor stays above threshold at ALL multipliers."""
        return all(wf.oos_profit_factor >= pf_threshold
                   for wf in self.results)


def run_spread_stress(
    bars: pd.DataFrame,
    strategy_cls: Type[Strategy],
    multipliers: Optional[List[float]] = None,
    params: Optional[Dict] = None,
    train_size: str = "1460D",
    test_size: str = "365D",
    step_size: Optional[str] = None,
    purge: str = "0D",
    exclude_ranges=None,
    cash: float = 10_000,
    cost_model: Optional[PepperstoneXAUUSDCostModel] = None,
    periods_per_year: Optional[int] = None,
    approx_gold_price: float = 2400.0,
    session_hours: Optional[tuple] = None,
    verbose: bool = True,
) -> SpreadStressResult:
    """Run walk-forward at multiple spread levels and report edge robustness.

    Tests whether the strategy's profit factor and Sharpe survive realistic
    spread widening (e.g. during news events or low-liquidity sessions).

    Parameters
    ----------
    multipliers : list of float, optional
        Spread multipliers to test. Default [1.0, 1.5, 2.0].
        1.0 = baseline; 1.5 = 50% wider; 2.0 = double spread.
    cost_model : PepperstoneXAUUSDCostModel, optional
        The 1× reference cost model. Other runs scale its spread.
    All other parameters are forwarded to run_walk_forward.
    """
    if multipliers is None:
        multipliers = [1.0, 1.5, 2.0]
    if cost_model is None:
        cost_model = PepperstoneXAUUSDCostModel()
    if exclude_ranges is None:
        exclude_ranges = PEPPERSTONE_XAUUSD_KNOWN_GAPS

    results: List[WalkForwardResult] = []

    for mult in multipliers:
        stressed = PepperstoneXAUUSDCostModel(
            spread_usd_per_oz=cost_model.spread_usd_per_oz * mult,
            commission_per_lot_round_turn=(
                cost_model.commission_per_lot_round_turn
            ),
            swap_long_per_lot_night=cost_model.swap_long_per_lot_night,
            swap_short_per_lot_night=cost_model.swap_short_per_lot_night,
            stops_level_floor_usd_per_oz=(
                cost_model.stops_level_floor_usd_per_oz
            ),
        )
        if verbose:
            spread_val = cost_model.spread_usd_per_oz * mult
            print(f"\n--- Spread {mult:.1f}× (${spread_val:.2f}/oz) ---")

        wf = run_walk_forward(
            bars=bars,
            strategy_cls=strategy_cls,
            params=params,
            train_size=train_size,
            test_size=test_size,
            step_size=step_size,
            purge=purge,
            exclude_ranges=exclude_ranges,
            cash=cash,
            cost_model=stressed,
            periods_per_year=periods_per_year,
            approx_gold_price=approx_gold_price,
            session_hours=session_hours,
            verbose=verbose,
        )
        results.append(wf)

    return SpreadStressResult(
        strategy_name=strategy_cls.__name__,
        multipliers=multipliers,
        results=results,
        base_spread_usd_per_oz=cost_model.spread_usd_per_oz,
    )
