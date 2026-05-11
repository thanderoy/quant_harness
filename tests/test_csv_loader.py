"""tests/test_csv_loader.py — round-trip tests for the CSV loader.

Synthesises CSV files in the exact MT5 export format and verifies the
loader recovers them correctly, infers the right timeframe, and warns
on common gotchas.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from io import StringIO

import pandas as pd
import numpy as np

from qhf.data.csv_loader import (
    load_bars, BarLoadError,
    _sniff_delimiter, _normalise_headers, _infer_timeframe, _detect_gaps,
)


def _write(content: str, suffix: str = ".csv") -> str:
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


# ----- A canonical MT5-style H1 sample (matches user's actual export) ------

H1_TAB_SAMPLE = (
    "Date\tOpen\tHigh\tLow\tClose\tVolume\n"
    "2004.06.11 07:00\t384\t384.3\t383.3\t383.8\t44\n"
    "2004.06.11 08:00\t383.8\t384.3\t383.1\t383.1\t41\n"
    "2004.06.11 09:00\t383.1\t384.1\t382.8\t383.1\t55\n"
    "2004.06.11 10:00\t383\t383.8\t383\t383.6\t33\n"
    "2004.06.11 11:00\t383.6\t383.8\t383.5\t383.6\t23\n"
)


# ----- Tests --------------------------------------------------------------


class TestSniffer(unittest.TestCase):

    def test_sniff_tab(self):
        path = _write(H1_TAB_SAMPLE)
        try:
            self.assertEqual(_sniff_delimiter(__import__("pathlib").Path(path)),
                             "\t")
        finally:
            os.unlink(path)

    def test_sniff_comma(self):
        comma = H1_TAB_SAMPLE.replace("\t", ",")
        path = _write(comma)
        try:
            self.assertEqual(_sniff_delimiter(__import__("pathlib").Path(path)),
                             ",")
        finally:
            os.unlink(path)


class TestHeaderNorm(unittest.TestCase):

    def test_aliases(self):
        cols = ["Date", "Open", "High", "Low", "Close", "Volume"]
        self.assertEqual(_normalise_headers(cols),
                         ["time", "open", "high", "low", "close", "volume"])

    def test_bom_stripped(self):
        cols = ["\ufeffdate", "open", "high", "low", "close"]
        self.assertEqual(_normalise_headers(cols),
                         ["time", "open", "high", "low", "close"])

    def test_tick_volume(self):
        cols = ["timestamp", "o", "h", "l", "c", "tick_volume"]
        self.assertEqual(_normalise_headers(cols),
                         ["time", "open", "high", "low", "close", "volume"])


class TestInferTimeframe(unittest.TestCase):

    def test_h1(self):
        self.assertEqual(_infer_timeframe(3600), "H1")

    def test_m15(self):
        self.assertEqual(_infer_timeframe(900), "M15")

    def test_d1(self):
        self.assertEqual(_infer_timeframe(86400), "D1")

    def test_unknown(self):
        self.assertTrue(_infer_timeframe(7777).startswith("~"))


class TestLoadH1Sample(unittest.TestCase):

    def setUp(self):
        self.path = _write(H1_TAB_SAMPLE)

    def tearDown(self):
        if os.path.exists(self.path):
            os.unlink(self.path)

    def test_loads_user_real_format(self):
        result = load_bars(self.path, expected_timeframe="H1")
        self.assertEqual(result.rows, 5)
        self.assertEqual(result.timeframe_inferred, "H1")
        self.assertEqual(result.df.iloc[0]["close"], 383.8)
        self.assertEqual(result.df.index[0], pd.Timestamp("2004-06-11 07:00"))
        self.assertEqual(result.df.index[-1], pd.Timestamp("2004-06-11 11:00"))
        self.assertEqual(list(result.df.columns),
                         ["open", "high", "low", "close", "volume"])

    def test_warning_on_wrong_expected_tf(self):
        # An H1 file labelled as M15 should warn.
        result = load_bars(self.path, expected_timeframe="M15")
        self.assertTrue(any("Expected M15" in w for w in result.warnings))


class TestSyntheticDepth(unittest.TestCase):
    """Generate a longer synthetic series to exercise gap detection
    and depth-in-years computation."""

    def setUp(self):
        # 1000 H1 bars starting Mon 2024-01-01 with weekend gaps.
        idx = pd.date_range("2024-01-01", periods=1000, freq="h")
        idx = idx[idx.weekday < 5]   # drop weekend bars (forex-like)
        prices = 2000 + np.cumsum(np.random.default_rng(42).normal(0, 1, len(idx)))
        df = pd.DataFrame({
            "Date": [t.strftime("%Y.%m.%d %H:%M") for t in idx],
            "Open": prices - 0.1,
            "High": prices + 0.5,
            "Low": prices - 0.5,
            "Close": prices,
            "Volume": 100,
        })
        buf = StringIO()
        df.to_csv(buf, sep="\t", index=False)
        self.path = _write(buf.getvalue())

    def tearDown(self):
        if os.path.exists(self.path):
            os.unlink(self.path)

    def test_loads_and_infers_h1(self):
        result = load_bars(self.path, expected_timeframe="H1")
        self.assertEqual(result.timeframe_inferred, "H1")
        # Weekend gaps should be filtered (Saturday-midpoint exclusion).
        self.assertEqual(len(result.gaps), 0)
        self.assertGreater(result.span_days, 30)


class TestOHLCSanity(unittest.TestCase):

    def test_high_below_low_warned(self):
        bad = (
            "Date,Open,High,Low,Close,Volume\n"
            "2024-01-01 00:00,100,90,95,98,1\n"   # high<low
            "2024-01-01 01:00,98,101,97,100,1\n"
        )
        path = _write(bad)
        try:
            result = load_bars(path)
            self.assertTrue(any("OHLC sanity" in w for w in result.warnings))
        finally:
            os.unlink(path)


class TestErrorPaths(unittest.TestCase):

    def test_missing_file(self):
        with self.assertRaises(BarLoadError):
            load_bars("/no/such/path.csv")

    def test_empty_file(self):
        path = _write("")
        try:
            with self.assertRaises(BarLoadError):
                load_bars(path)
        finally:
            os.unlink(path)

    def test_missing_columns(self):
        path = _write("date,foo\n2024-01-01,1\n")
        try:
            with self.assertRaises(BarLoadError):
                load_bars(path)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
