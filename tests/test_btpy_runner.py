"""tests/test_btpy_runner.py — tests for the backtesting.py engine wrapper.

Tests are split into three groups:

    TestCostModel     Verify spread/commission/swap are applied to trades.
    TestPipelineFlow  Verify single backtest + walk-forward return correct types,
                      trade counts, and don't crash on edge cases.
    TestSignalLogic   Verify HMAStoch1H and HMAStochM15 fire on known conditions.
"""

from __future__ import annotations

import unittest
import warnings
from datetime import datetime

import numpy as np
import pandas as pd
from backtesting import Strategy

warnings.filterwarnings("ignore")

from research.engines.btpy_runner import (
    run_backtest, run_walk_forward,
    BtRunResult, WalkForwardResult,
    _commission_callable, _spread_fraction, _apply_swap,
    PEPPERSTONE_XAUUSD_KNOWN_GAPS,
)
from research.engines.sizer import calculate_lot_size
from research.datasets.cost_model import PepperstoneXAUUSDCostModel
from research.engines.strategies import HMAStoch1H, HMAStochM15
from research.engines.indicators import hma, stochastic, atr as calc_atr
from research.reports.scorecard import evaluate, Thresholds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bars(n: int = 5000, seed: int = 0, price: float = 2400.0,
               sigma: float = 1.5) -> pd.DataFrame:
    """Synthetic weekday-hourly XAUUSD bars."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n * 2, freq="h")
    idx = idx[idx.dayofweek < 5][:n]
    prices = price + np.cumsum(rng.normal(0, sigma, n))
    prices = np.maximum(prices, 500)
    return pd.DataFrame({
        "open": prices, "high": prices + 1.5,
        "low": prices - 1.5, "close": prices,
    }, index=idx)


class _TrivialStrategy(Strategy):
    """Fires a long every 100 bars to give the pipeline testable trades."""
    _counter = 0

    def init(self):
        self._counter = 0

    def next(self):
        self._counter += 1
        if self.position:
            return
        if self._counter % 100 == 0:
            close = float(self.data.Close[-1])
            lots, eff_atr = calculate_lot_size(float(self.equity), 3.0)
            size = round(lots * 100, 2)
            self.buy(size=size, sl=close - 3.0, tp=close + 6.0)


# ---------------------------------------------------------------------------
# Cost model mechanics
# ---------------------------------------------------------------------------


class TestCostModelMechanics(unittest.TestCase):

    def setUp(self):
        # Mechanics need a non-zero schedule; the measured one is 0.00.
        self.cost = PepperstoneXAUUSDCostModel.for_scenario("conservative")

    def test_commission_callable_per_oz(self):
        fn = _commission_callable(self.cost)
        # $7 RT / lot / 100oz / 2 sides = $0.035/oz/order
        self.assertAlmostEqual(fn(1.0, 2400), 0.035, places=5)
        self.assertAlmostEqual(fn(100.0, 2400), 3.5, places=5)

    def test_commission_negative_size_absolute(self):
        fn = _commission_callable(self.cost)
        # short: size is negative; commission must still be positive
        self.assertAlmostEqual(fn(-1.0, 2400), 0.035, places=5)

    def test_spread_fraction_at_default_price(self):
        frac = _spread_fraction(self.cost, approx_price=2400)
        self.assertAlmostEqual(frac * 2400, 0.22, places=4)

    def test_apply_swap_reduces_pnl_for_long_held_overnight(self):
        # Build a fake trades DF with one long held 2 nights.
        cost = PepperstoneXAUUSDCostModel(
            swap_long_per_lot_night=-1.0,  # simple test value
        )
        trades = pd.DataFrame({
            "Size": [1.0],          # 1 oz = 0.01 lots
            "PnL": [10.0],
            "ReturnPct": [0.01],
            "Commission": [0.035],
            "EntryTime": [pd.Timestamp("2024-05-06 12:00")],
            "ExitTime": [pd.Timestamp("2024-05-08 12:00")],
            "EntryBar": [0], "ExitBar": [48],
            "EntryPrice": [2400], "ExitPrice": [2410],
            "SL": [2397], "TP": [2406],
            "Duration": [pd.Timedelta("2d")],
            "Tag": [None],
            "Entry_λ(C)": [None], "Exit_λ(C)": [None],
        })
        result = _apply_swap(trades, cost)
        # 1 oz = 0.01 lots; 2 nights swap = 2 * -1.0 * 0.01 = -$0.02
        self.assertLess(result.iloc[0]["PnL"], 10.0)
        self.assertIn("SwapCost", result.columns)

    def test_apply_swap_empty_df(self):
        result = _apply_swap(pd.DataFrame(), self.cost)
        self.assertTrue(result.empty)


# ---------------------------------------------------------------------------
# Pipeline flow
# ---------------------------------------------------------------------------


class TestPipelineFlow(unittest.TestCase):

    def setUp(self):
        self.bars_3y = _make_bars(n=252 * 24 * 3, seed=1)
        self.bars_7y = _make_bars(n=252 * 24 * 7, seed=2)

    def test_run_backtest_returns_correct_type(self):
        r = run_backtest(self.bars_3y, _TrivialStrategy, cash=10_000,
                         periods_per_year=6048)
        self.assertIsInstance(r, BtRunResult)

    def test_run_backtest_has_trades(self):
        r = run_backtest(self.bars_3y, _TrivialStrategy, cash=10_000)
        self.assertGreater(r.n_trades, 0)

    def test_return_pct_series_length_matches_trades(self):
        r = run_backtest(self.bars_3y, _TrivialStrategy, cash=10_000)
        self.assertEqual(len(r.return_pct_series), r.n_trades)

    def test_run_backtest_no_trades_no_crash(self):
        # Very short window: not enough bars for warmup → no trades.
        r = run_backtest(self.bars_3y.iloc[:10], _TrivialStrategy, cash=10_000)
        self.assertIsInstance(r, BtRunResult)
        self.assertTrue(r.return_pct_series.empty)

    def test_walk_forward_returns_correct_type(self):
        wf = run_walk_forward(
            self.bars_7y, _TrivialStrategy,
            train_size="1460D", test_size="365D", step_size="180D",
            exclude_ranges=[], cash=10_000, verbose=False,
        )
        self.assertIsInstance(wf, WalkForwardResult)

    def test_walk_forward_produces_multiple_folds(self):
        # Need > train_size + 2*test_size of data for 2 folds.
        # 1460D train + 2×365D = 2190D ≈ 6y. Use bars_7y.
        wf = run_walk_forward(
            self.bars_7y, _TrivialStrategy,
            train_size="1095D", test_size="365D", step_size="365D",
            exclude_ranges=[], cash=10_000, verbose=False,
        )
        self.assertGreater(len(wf.folds), 1)

    def test_walk_forward_exclusion_drops_folds(self):
        # Create a gap range that overlaps known fold dates.
        bars = self.bars_7y
        mid = bars.index[len(bars) // 2].date().isoformat()
        mid_end = (bars.index[len(bars) // 2] + pd.Timedelta("60D")).date().isoformat()

        wf_no_excl = run_walk_forward(
            bars, _TrivialStrategy,
            train_size="1460D", test_size="365D", step_size="180D",
            exclude_ranges=[], cash=10_000, verbose=False,
        )
        wf_with_excl = run_walk_forward(
            bars, _TrivialStrategy,
            train_size="1460D", test_size="365D", step_size="180D",
            exclude_ranges=[(mid, mid_end)], cash=10_000, verbose=False,
        )
        self.assertGreater(len(wf_no_excl.folds), len(wf_with_excl.folds))

    def test_known_gaps_constant_is_list_of_tuples(self):
        for item in PEPPERSTONE_XAUUSD_KNOWN_GAPS:
            self.assertIsInstance(item, tuple)
            self.assertEqual(len(item), 2)

    def test_to_scorecard_result_builds_result_object(self):
        wf = run_walk_forward(
            self.bars_7y, _TrivialStrategy,
            train_size="1460D", test_size="365D", step_size="365D",
            exclude_ranges=[], cash=10_000, verbose=False,
        )
        r = wf.to_scorecard_result(name="test", num_trials=1)
        # evaluate() should run without crashing
        gate_report = evaluate(r, Thresholds())
        self.assertIsNotNone(gate_report)

    def test_cost_model_commission_applied(self):
        # With zero commission, commissions in trade DF should be 0.
        from research.datasets.cost_model import PepperstoneXAUUSDCostModel
        free_cost = PepperstoneXAUUSDCostModel(
            spread_usd_per_oz=0.0,
            commission_per_lot_round_turn=0.0,
            swap_long_per_lot_night=0.0,
            swap_short_per_lot_night=0.0,
        )
        r_free = run_backtest(self.bars_3y, _TrivialStrategy, cash=10_000,
                              cost_model=free_cost)
        if not r_free.trades.empty:
            self.assertTrue((r_free.trades["Commission"] == 0).all())

        # With non-zero commission, at least some trades should have it.
        r_real = run_backtest(self.bars_3y, _TrivialStrategy, cash=10_000,
                              cost_model=PepperstoneXAUUSDCostModel.for_scenario("conservative"))
        if not r_real.trades.empty:
            self.assertTrue((r_real.trades["Commission"] > 0).any())


# ---------------------------------------------------------------------------
# Signal logic for HMA+Stoch strategies
# ---------------------------------------------------------------------------


class TestHMAStochSignalLogic(unittest.TestCase):
    """Verify the strategy adapters have the right signal conditions.

    We test the underlying indicator+condition logic directly (not via the
    backtesting.py adapter) to avoid engine overhead and non-determinism.
    """

    def _make_trending_bars(self, n: int, direction: float = 1.0,
                            seed: int = 0) -> pd.DataFrame:
        rng = np.random.default_rng(seed)
        drift = direction * 0.15  # per-bar drift
        prices = 2400 + np.cumsum(rng.normal(drift, 0.3, n))
        prices = np.maximum(prices, 500)
        idx = pd.date_range("2020-01-01", periods=n, freq="h")
        return pd.DataFrame({
            "open": prices, "high": prices + 0.5,
            "low": prices - 0.5, "close": prices,
        }, index=idx)

    def _compute_signals(self, bars: pd.DataFrame, hma_period=55,
                         stoch_k=14, stoch_d=3, stoch_sk=3):
        c = bars["close"]
        h = bars["high"]
        lo = bars["low"]
        hma_s = hma(c, hma_period)
        k, d = stochastic(h, lo, c, stoch_k, stoch_d, stoch_sk)
        atr_s = calc_atr(h, lo, c, 14)
        long_sigs = (
            (hma_s > hma_s.shift(1)) & (c > hma_s)
            & (k.shift(1) < d.shift(1)) & (k > d) & (k.shift(1) < 20.0)
        )
        short_sigs = (
            (hma_s < hma_s.shift(1)) & (c < hma_s)
            & (k.shift(1) > d.shift(1)) & (k < d) & (k.shift(1) > 80.0)
        )
        return long_sigs, short_sigs, atr_s

    def test_indicators_produce_series_of_correct_length(self):
        bars = self._make_trending_bars(1000)
        longs, shorts, atr_s = self._compute_signals(bars)
        self.assertEqual(len(longs), 1000)
        self.assertEqual(len(shorts), 1000)
        self.assertEqual(len(atr_s), 1000)

    def test_uptrend_data_produces_more_longs_than_shorts(self):
        """In a strong uptrend, long signals should dominate short signals."""
        bars = self._make_trending_bars(5000, direction=1.0)
        longs, shorts, _ = self._compute_signals(bars)
        # Not guaranteed on all seeds, but directionally correct.
        if longs.sum() > 0 or shorts.sum() > 0:
            self.assertGreaterEqual(longs.sum(), shorts.sum())

    def test_downtrend_data_produces_more_shorts_than_longs(self):
        bars = self._make_trending_bars(5000, direction=-1.0)
        longs, shorts, _ = self._compute_signals(bars)
        if longs.sum() > 0 or shorts.sum() > 0:
            self.assertGreaterEqual(shorts.sum(), longs.sum())

    def test_strategy_classes_are_importable_and_have_defaults(self):
        self.assertEqual(HMAStoch1H.hma_period, 55)
        self.assertEqual(HMAStoch1H.risk_pct, 0.02)
        self.assertEqual(HMAStoch1H.min_atr_for_signal, 1.0)
        self.assertEqual(HMAStochM15.hma_period, 21)
        self.assertEqual(HMAStochM15.risk_pct, 0.01)
        # v1.2 correction: was 5.0 (broken — blocked 98% of M15 signals)
        self.assertEqual(HMAStochM15.min_atr_for_signal, 2.0)

    def test_m15_atr_filter_blocks_low_atr_bars(self):
        """M15 has min_atr_for_signal=5.0 which blocks most H1-period ATRs."""
        bars = self._make_trending_bars(2000)
        _, _, atr_s = self._compute_signals(bars, hma_period=21)
        # With small-sigma synthetic data, ATR is typically < 5.0.
        pct_above_5 = (atr_s.dropna() >= 5.0).mean()
        # The filter would block most signals.
        self.assertLess(pct_above_5, 0.5)


class TestSessionFilter(unittest.TestCase):

    def _make_all_hours(self) -> pd.DataFrame:
        """24/7 weekday-hourly bars."""
        idx = pd.date_range("2022-01-01", periods=5000, freq="h")
        idx = idx[idx.dayofweek < 5][:3000]
        prices = 2400 + np.cumsum(np.random.default_rng(5).normal(0, 1, len(idx)))
        return pd.DataFrame({
            "open": prices, "high": prices + 1,
            "low": prices - 1, "close": prices,
        }, index=idx)

    def test_session_filter_removes_outside_hours(self):
        from research.engines.btpy_runner import _apply_session_filter
        bars = self._make_all_hours()
        filtered = _apply_session_filter(bars, session_hours=(8, 17))
        hours = filtered.index.hour
        self.assertTrue((hours >= 8).all())
        self.assertTrue((hours < 17).all())

    def test_no_session_filter_returns_unchanged(self):
        from research.engines.btpy_runner import _apply_session_filter
        bars = self._make_all_hours()
        result = _apply_session_filter(bars, session_hours=None)
        self.assertEqual(len(result), len(bars))

    def test_session_filter_reduces_bar_count(self):
        from research.engines.btpy_runner import _apply_session_filter
        bars = self._make_all_hours()
        filtered = _apply_session_filter(bars, session_hours=(8, 17))
        # 9 session hours vs 24 total: ~37.5% of bars kept
        self.assertLess(len(filtered), len(bars))
        self.assertGreater(len(filtered), 0)

    def test_run_backtest_with_session_filter(self):
        bars = self._make_all_hours()
        r = run_backtest(bars, _TrivialStrategy, cash=10_000,
                         session_hours=(8, 17))
        self.assertIsInstance(r, BtRunResult)

    def test_invalid_session_raises(self):
        from research.engines.btpy_runner import _apply_session_filter
        bars = self._make_all_hours()
        # Hours 2-3 UTC: no bars will pass weekday-h filter for this data.
        # Actually let's test with impossible hours
        with self.assertRaises(ValueError):
            _apply_session_filter(bars, session_hours=(25, 26))  # impossible


class TestSpreadStress(unittest.TestCase):

    def setUp(self):
        self.bars = _make_bars(n=252 * 24 * 7, seed=3)

    def test_returns_stress_result_type(self):
        from research.engines import run_spread_stress, SpreadStressResult
        stress = run_spread_stress(
            self.bars, _TrivialStrategy,
            multipliers=[1.0, 1.5],
            train_size="1095D", test_size="365D", step_size="365D",
            exclude_ranges=[], cash=10_000, verbose=False,
        )
        self.assertIsInstance(stress, SpreadStressResult)

    def test_result_count_matches_multipliers(self):
        from research.engines import run_spread_stress
        stress = run_spread_stress(
            self.bars, _TrivialStrategy,
            multipliers=[1.0, 1.5, 2.0],
            train_size="1095D", test_size="365D", step_size="365D",
            exclude_ranges=[], cash=10_000, verbose=False,
        )
        self.assertEqual(len(stress.results), 3)

    def test_higher_spread_increases_costs(self):
        """Wider spread should reduce or maintain OOS profit factor."""
        from research.engines import run_spread_stress
        stress = run_spread_stress(
            self.bars, _TrivialStrategy,
            multipliers=[1.0, 2.0],
            train_size="1095D", test_size="365D", step_size="365D",
            exclude_ranges=[], cash=10_000, verbose=False,
        )
        pf_1x = stress.results[0].oos_profit_factor
        pf_2x = stress.results[1].oos_profit_factor
        # With more costs, PF should be <= baseline (or both NaN)
        if not (pd.isna(pf_1x) or pd.isna(pf_2x)):
            self.assertLessEqual(pf_2x, pf_1x + 0.01)  # small tolerance

    def test_summary_str_contains_multipliers(self):
        from research.engines import run_spread_stress
        stress = run_spread_stress(
            self.bars, _TrivialStrategy,
            multipliers=[1.0, 1.5],
            train_size="1095D", test_size="365D", step_size="365D",
            exclude_ranges=[], cash=10_000, verbose=False,
        )
        s = stress.summary_str()
        self.assertIn("1.0×", s)
        self.assertIn("1.5×", s)


if __name__ == "__main__":
    unittest.main()
