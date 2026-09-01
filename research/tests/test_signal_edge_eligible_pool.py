"""Tests for the eligible_pool extension to signal_edge_report.

The null and random baseline must draw entries only from the caller-supplied
eligible universe, while the *actual* signal statistic is untouched. Default
(None) behaviour must be byte-for-byte identical to an all-True mask.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from research.pre.signal_edge import signal_edge_report


def _gbm_ohlc(n: int, seed: int, sigma: float = 0.004, start: float = 1800.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = start * np.exp(np.cumsum(rng.normal(0.0, sigma, n)))
    open_ = np.empty(n)
    open_[0] = start
    open_[1:] = close[:-1]
    body_hi = np.maximum(open_, close)
    body_lo = np.minimum(open_, close)
    wick = np.abs(rng.normal(0.0, sigma, n)) * close
    idx = pd.date_range("2020-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame(
        {"open": open_, "high": body_hi + wick, "low": body_lo - wick, "close": close},
        index=idx,
    )


def _random_signal(n: int, seed: int, k: int = 60) -> pd.Series:
    rng = np.random.default_rng(seed)
    idx = rng.choice(np.arange(60, n - 120), size=k, replace=False)
    s = pd.Series(0, index=range(n), dtype=np.int64)
    s.iloc[idx] = 1
    return s


def test_none_equals_all_true_mask():
    n = 800
    ohlc = _gbm_ohlc(n, seed=1)
    signal = _random_signal(n, seed=2)
    signal.index = ohlc.index

    base = signal_edge_report(signal, ohlc, forward_windows=[20, 50],
                              n_permutations=200, random_seed=5)
    mask = signal_edge_report(signal, ohlc, forward_windows=[20, 50],
                              n_permutations=200, random_seed=5,
                              eligible_pool=np.ones(n, dtype=bool))

    pd.testing.assert_frame_equal(base.permutation, mask.permutation)
    pd.testing.assert_frame_equal(base.baseline, mask.baseline)
    assert mask.metadata["eligible_pool_restricted"] is True
    assert base.metadata["eligible_pool_restricted"] is False


def test_bool_mask_and_integer_positions_agree():
    n = 800
    ohlc = _gbm_ohlc(n, seed=3)
    signal = _random_signal(n, seed=4)
    signal.index = ohlc.index

    mask = np.zeros(n, dtype=bool)
    mask[100:500] = True
    by_mask = signal_edge_report(signal, ohlc, forward_windows=[20, 50],
                                 n_permutations=200, random_seed=9, eligible_pool=mask)
    by_idx = signal_edge_report(signal, ohlc, forward_windows=[20, 50],
                                n_permutations=200, random_seed=9,
                                eligible_pool=np.flatnonzero(mask))
    pd.testing.assert_frame_equal(by_mask.permutation, by_idx.permutation)


def test_restricting_null_pool_shrinks_eligible_count_and_can_starve_it():
    n = 600
    ohlc = _gbm_ohlc(n, seed=6)
    signal = _random_signal(n, seed=7, k=40)
    signal.index = ohlc.index

    # Unrestricted: p-values are finite.
    full = signal_edge_report(signal, ohlc, forward_windows=[20],
                              n_permutations=200, random_seed=11)
    assert np.isfinite(full.permutation["p_value"].iloc[0])

    # Restrict the eligible universe to the last 3 bars: no forward window fits,
    # so the null pool is empty and the p-value must be NaN — proof the null
    # sampling honours eligible_pool (the actual E-Ratio is still computed).
    mask = np.zeros(n, dtype=bool)
    mask[-3:] = True
    starved = signal_edge_report(signal, ohlc, forward_windows=[20],
                                 n_permutations=200, random_seed=11, eligible_pool=mask)
    assert starved.metadata["n_eligible_pool_bars"] <= 3
    assert np.isnan(starved.permutation["p_value"].iloc[0])
    # The observed E-Ratio itself is unaffected by the null restriction.
    assert np.isfinite(starved.per_window["e_ratio"].iloc[0])
    pd.testing.assert_series_equal(
        full.per_window["e_ratio"], starved.per_window["e_ratio"]
    )
