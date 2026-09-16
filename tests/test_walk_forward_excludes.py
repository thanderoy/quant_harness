"""tests/test_walk_forward_excludes.py — tests for Phase 2 walk_forward extensions.

Covers:
- Backwards compatibility: no exclude_ranges => identical behaviour to v0.1.0
- exclude_ranges drops folds whose train OR test window overlaps
- SplitReport correctly tallies yielded vs excluded
- align_data_files trims to common end-date
"""

from __future__ import annotations

import unittest

import numpy as np
import pandas as pd

from research.validation import (
    rolling_splits,
    rolling_splits_with_report,
    expanding_splits,
    expanding_splits_with_report,
    SplitReport,
    FoldExclusion,
    align_data_files,
)


def _synthetic_df(start="2010-01-01", end="2024-12-31") -> pd.DataFrame:
    idx = pd.date_range(start, end, freq="D")
    return pd.DataFrame({"x": np.arange(len(idx), dtype=float)}, index=idx)


class TestBackwardsCompat(unittest.TestCase):
    """No exclude_ranges -> exactly the original behaviour."""

    def setUp(self):
        self.df = _synthetic_df()

    def test_rolling_no_excludes_matches_baseline(self):
        # Run twice (with and without explicit None) -- counts must match.
        n_default = sum(1 for _ in rolling_splits(self.df, "1460D", "365D"))
        n_explicit = sum(1 for _ in rolling_splits(
            self.df, "1460D", "365D", exclude_ranges=None
        ))
        self.assertEqual(n_default, n_explicit)
        self.assertGreater(n_default, 5)

    def test_expanding_no_excludes_matches_baseline(self):
        n_default = sum(1 for _ in expanding_splits(self.df, "1460D", "365D"))
        n_explicit = sum(1 for _ in expanding_splits(
            self.df, "1460D", "365D", exclude_ranges=None
        ))
        self.assertEqual(n_default, n_explicit)
        self.assertGreater(n_default, 5)


class TestRollingExcludes(unittest.TestCase):
    """exclude_ranges drops the right folds."""

    def setUp(self):
        # 15-year dataset, 4y train, 1y test, 1y step => 11 folds total
        self.df = _synthetic_df("2010-01-01", "2024-12-31")
        self.train, self.test = "1460D", "365D"

    def test_exclusion_in_test_window(self):
        # Excluding 2018 should drop the fold whose test window IS 2018.
        baseline = sum(1 for _ in rolling_splits(self.df, self.train, self.test))
        with_excl = sum(1 for _ in rolling_splits(
            self.df, self.train, self.test,
            exclude_ranges=[("2018-06-01", "2018-08-31")]
        ))
        self.assertLess(with_excl, baseline)

    def test_exclusion_in_train_window(self):
        # Excluding a date in 2014 should drop folds whose TRAIN spans it.
        baseline = sum(1 for _ in rolling_splits(self.df, self.train, self.test))
        with_excl = sum(1 for _ in rolling_splits(
            self.df, self.train, self.test,
            exclude_ranges=[("2014-06-01", "2014-08-31")]
        ))
        self.assertLess(with_excl, baseline)

    def test_far_future_exclusion_no_effect(self):
        # Exclude a window OUTSIDE the dataset -- no folds dropped.
        baseline = sum(1 for _ in rolling_splits(self.df, self.train, self.test))
        with_excl = sum(1 for _ in rolling_splits(
            self.df, self.train, self.test,
            exclude_ranges=[("2099-01-01", "2099-12-31")]
        ))
        self.assertEqual(with_excl, baseline)

    def test_invalid_exclusion_order(self):
        with self.assertRaises(ValueError):
            list(rolling_splits(
                self.df, self.train, self.test,
                exclude_ranges=[("2020-12-31", "2020-01-01")]   # end < start
            ))


class TestSplitReport(unittest.TestCase):
    """SplitReport tallies yielded and excluded folds."""

    def setUp(self):
        self.df = _synthetic_df("2010-01-01", "2024-12-31")

    def test_report_counts_correctly(self):
        report = SplitReport()
        baseline_count = sum(1 for _ in rolling_splits(self.df, "1460D", "365D"))
        # Exclude one specific period that should drop ~1 fold.
        used = list(rolling_splits_with_report(
            self.df, "1460D", "365D",
            exclude_ranges=[("2020-01-01", "2020-12-31")],
            report=report,
        ))
        self.assertEqual(report.folds_yielded, len(used))
        # Total folds = yielded + excluded = baseline (without excludes)
        self.assertEqual(report.total_folds, baseline_count)
        self.assertGreaterEqual(len(report.folds_excluded), 1)

    def test_excluded_fold_records_metadata(self):
        report = SplitReport()
        list(rolling_splits_with_report(
            self.df, "1460D", "365D",
            exclude_ranges=[("2020-01-01", "2020-12-31")],
            report=report,
        ))
        for fx in report.folds_excluded:
            self.assertIsInstance(fx, FoldExclusion)
            self.assertIn(fx.overlapping_window, ("train", "test"))
            self.assertEqual(fx.overlapping_range,
                             (pd.Timestamp("2020-01-01"),
                              pd.Timestamp("2020-12-31")))

    def test_summary_str_contains_counts(self):
        report = SplitReport()
        list(rolling_splits_with_report(
            self.df, "1460D", "365D",
            exclude_ranges=[("2020-01-01", "2020-12-31")],
            report=report,
        ))
        s = report.summary_str()
        self.assertIn(f"{report.folds_yielded} folds used", s)
        self.assertIn(f"{len(report.folds_excluded)} excluded", s)


class TestAlignDataFiles(unittest.TestCase):

    def test_aligns_to_earliest_end(self):
        a = pd.DataFrame({"x": [1.0]}, index=pd.date_range("2020-01-01", periods=10))
        b = pd.DataFrame({"x": [1.0]}, index=pd.date_range("2020-01-01", periods=20))
        c = pd.DataFrame({"x": [1.0]}, index=pd.date_range("2020-01-01", periods=15))
        aligned = align_data_files([a, b, c])
        self.assertEqual(aligned[0].index.max(), aligned[1].index.max())
        self.assertEqual(aligned[1].index.max(), aligned[2].index.max())
        # Earliest of the three was a (10 days); all should end there.
        self.assertEqual(aligned[0].index.max(), a.index.max())

    def test_explicit_cutoff(self):
        a = pd.DataFrame({"x": [1.0]}, index=pd.date_range("2020-01-01", periods=20))
        b = pd.DataFrame({"x": [1.0]}, index=pd.date_range("2020-01-01", periods=30))
        aligned = align_data_files([a, b], cutoff="2020-01-10")
        for d in aligned:
            self.assertLessEqual(d.index.max(), pd.Timestamp("2020-01-10"))

    def test_empty(self):
        self.assertEqual(align_data_files([]), [])


if __name__ == "__main__":
    unittest.main()

