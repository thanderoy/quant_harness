"""tests/test_metrics.py — smoke tests for the core math primitives.

Run with `pytest tests/` or `python -m unittest tests.test_metrics`.

Covers:
- Sharpe ratio sign and scale.
- Max drawdown on a known curve.
- Profit factor sign cases.
- DSR returns probability in [0, 1].
- DSR is HIGHER for genuine alpha than for noise (calibration).
- PBO is LOWER for genuine alpha than for noise (calibration).
- Walk-forward split count and chronological ordering.
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from qhf.metrics import (
    sharpe_ratio, max_drawdown, profit_factor, summarize,
    dsr, dsr_from_trials, pbo, expected_max_sharpe,
)
from qhf.validation import rolling_splits
from qhf.reports import Result, Thresholds, evaluate


class TestCore(unittest.TestCase):

    def test_sharpe_zero_for_zero_mean(self):
        rng = np.random.default_rng(42)
        r = rng.normal(0.0, 0.01, 1000)
        sr = sharpe_ratio(r, periods_per_year=252)
        self.assertLess(abs(sr), 1.0)  # noise: small-magnitude Sharpe

    def test_sharpe_positive_for_positive_drift(self):
        rng = np.random.default_rng(42)
        r = rng.normal(0.001, 0.005, 1000)  # ~25% ann return / ~8% ann vol
        sr = sharpe_ratio(r, periods_per_year=252)
        self.assertGreater(sr, 1.0)

    def test_max_drawdown_known(self):
        # equity goes 1 -> 1.5 -> 0.75 (50% drawdown from peak 1.5)
        # returns: +0.5, then -0.5
        r = pd.Series([0.5, -0.5])
        mdd = max_drawdown(r)
        self.assertAlmostEqual(mdd, 0.5, places=6)

    def test_profit_factor_all_wins(self):
        r = pd.Series([0.01, 0.02, 0.005])
        self.assertTrue(np.isinf(profit_factor(r)))

    def test_profit_factor_balanced(self):
        r = pd.Series([0.02, -0.01])
        # 0.02 / 0.01 = 2.0
        self.assertAlmostEqual(profit_factor(r), 2.0, places=6)

    def test_summarize_keys(self):
        rng = np.random.default_rng(0)
        s = summarize(rng.normal(0, 0.01, 500), periods_per_year=252)
        for k in ("sharpe", "sortino", "max_drawdown", "calmar",
                  "cagr", "profit_factor", "win_rate", "expectancy",
                  "n_periods"):
            self.assertIn(k, s)


class TestDeflated(unittest.TestCase):

    def test_expected_max_sharpe_grows_with_n(self):
        v = 1.0
        e10 = expected_max_sharpe(10, v)
        e100 = expected_max_sharpe(100, v)
        e1000 = expected_max_sharpe(1000, v)
        self.assertLess(e10, e100)
        self.assertLess(e100, e1000)

    def test_expected_max_sharpe_zero_for_one_trial(self):
        self.assertEqual(expected_max_sharpe(1, 1.0), 0.0)

    def test_dsr_probability_in_unit_interval(self):
        rng = np.random.default_rng(0)
        r = rng.normal(0.0005, 0.01, 1500)
        out = dsr(r, num_trials=20, sr_variance_annualised=0.5,
                  periods_per_year=252)
        self.assertGreaterEqual(out["dsr_probability"], 0.0)
        self.assertLessEqual(out["dsr_probability"], 1.0)

    def test_dsr_higher_for_alpha_than_noise(self):
        """Calibration: real alpha must have higher DSR than pure noise.

        Uses the SAME seed/setup as the demo (verified to PASS the gate);
        a different seed could land the realised alpha-Sharpe lower and
        miss the > 0.95 bar by chance — that's a property of finite samples,
        not a harness bug.
        """
        rng = np.random.default_rng(0)
        T, N = 2000, 20
        noise = pd.DataFrame(
            rng.normal(0, 0.01, size=(T, N)),
            columns=[f"s_{i}" for i in range(N)])
        rng2 = np.random.default_rng(0)  # same seed as demo
        alpha_data = rng2.normal(0, 0.01, size=(T, N))
        alpha_data[:, 5] += 0.0012  # demo uses column 5
        alpha = pd.DataFrame(alpha_data, columns=[f"s_{i}" for i in range(N)])

        d_noise = dsr_from_trials(noise, periods_per_year=252)
        d_alpha = dsr_from_trials(alpha, periods_per_year=252)
        # Core calibration property:
        self.assertGreater(d_alpha["dsr_probability"],
                           d_noise["dsr_probability"])
        # Demo-verified absolute thresholds:
        self.assertGreater(d_alpha["dsr_probability"], 0.95)
        self.assertLess(d_noise["dsr_probability"], 0.95)


class TestPBO(unittest.TestCase):

    def test_pbo_higher_for_noise_than_alpha(self):
        """Calibration: PBO should be higher when there's no edge."""
        rng = np.random.default_rng(0)
        T, N = 2000, 20
        noise = pd.DataFrame(
            rng.normal(0, 0.01, size=(T, N)),
            columns=[f"s_{i}" for i in range(N)])
        rng2 = np.random.default_rng(0)  # match demo setup
        alpha_data = rng2.normal(0, 0.01, size=(T, N))
        alpha_data[:, 5] += 0.0012
        alpha = pd.DataFrame(alpha_data, columns=[f"s_{i}" for i in range(N)])

        p_noise = pbo(noise, S=16, periods_per_year=252)
        p_alpha = pbo(alpha, S=16, periods_per_year=252)
        self.assertGreater(p_noise["pbo"], p_alpha["pbo"])
        self.assertLess(p_alpha["pbo"], 0.30)

    def test_pbo_combinations_count(self):
        rng = np.random.default_rng(0)
        M = pd.DataFrame(rng.normal(0, 0.01, size=(800, 5)))
        out = pbo(M, S=16)
        # C(16, 8) = 12,870
        self.assertEqual(out["n_combinations"], 12870)


class TestWalkForward(unittest.TestCase):

    def test_rolling_splits_chronological(self):
        idx = pd.date_range("2010-01-01", "2020-12-31", freq="D")
        df = pd.DataFrame({"x": range(len(idx))}, index=idx)
        splits = list(rolling_splits(df, "1460D", "365D"))
        self.assertGreater(len(splits), 5)
        for train, test in splits:
            self.assertLess(train.index.max(), test.index.max())
            self.assertLess(train.index.min(), test.index.min())


class TestScorecard(unittest.TestCase):

    def test_pass_case(self):
        r = Result(
            name="good", is_sharpe=1.4, oos_sharpe=1.2,
            is_max_dd=0.15, oos_max_dd=0.18,
            n_trades_oos=200, profit_factor_oos=1.6,
            pbo=0.10, dsr_probability=0.99)
        rep = evaluate(r)
        self.assertTrue(rep.passed)
        self.assertEqual(len(rep.failures), 0)

    def test_fail_on_gap(self):
        r = Result(
            name="overfit", is_sharpe=2.5, oos_sharpe=1.0,
            is_max_dd=0.10, oos_max_dd=0.15,
            n_trades_oos=200, profit_factor_oos=1.6,
            pbo=0.10, dsr_probability=0.99)
        rep = evaluate(r)
        self.assertFalse(rep.passed)
        self.assertTrue(any("gap" in f.lower() for f in rep.failures))

    def test_production_thresholds_stricter(self):
        r = Result(
            name="research-pass-prod-fail",
            is_sharpe=1.5, oos_sharpe=1.2,
            is_max_dd=0.15, oos_max_dd=0.20,
            n_trades_oos=50, profit_factor_oos=1.30,
            pbo=0.40, dsr_probability=0.96)
        # research: passes
        self.assertTrue(evaluate(r, Thresholds()).passed)
        # production: fails (PBO=0.40 > 0.30, trades=50 < 100, etc.)
        self.assertFalse(evaluate(r, Thresholds.production()).passed)


if __name__ == "__main__":
    unittest.main()
