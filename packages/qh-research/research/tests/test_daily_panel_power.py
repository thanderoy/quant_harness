"""daily_panel_power: the seq=150 rule on synthetic series. No outcome is read."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.post.mintrl import min_decidable_sharpe
from research.pre import daily_panel_power as dp


def _series(start: str, end: str, seed: int, common: np.ndarray | None = None, w: float = 0.0) -> pd.DataFrame:
    idx = pd.bdate_range(start, end, tz="UTC")
    rng = np.random.default_rng(seed)
    r = rng.normal(0, 0.01, idx.size)
    if common is not None:
        r = w * common[: idx.size] + (1 - w) * r
    close = 100 * np.exp(np.cumsum(r))
    return pd.DataFrame({"open": close, "high": close, "low": close, "close": close, "volume": 1.0}, index=idx)


def test_n_eff_bounds():
    assert dp.n_eff(10, 0.0) == 10
    assert dp.n_eff(10, 1.0) == pytest.approx(1.0)
    assert dp.n_eff(10, 0.44) < 4          # F1: unreachable at the measured correlations


def test_floor_matches_mintrl_annualised():
    assert dp.floor(5040) == pytest.approx(min_decidable_sharpe(n_obs=5040, sr_star=0.0) * np.sqrt(252))
    assert dp.floor(20 * 252) < dp.floor(9 * 252)   # span buys power (F2)


def test_window_is_the_common_span_of_the_longest_histories():
    s = {"A": _series("2005-01-03", "2026-10-21", 1), "B": _series("2012-01-02", "2026-10-21", 2),
         "C": _series("2020-01-01", "2026-10-21", 3)}
    p = dp.plan(s)
    rows = {r["k"]: r for r in p["rows"]}
    assert rows[1]["instruments"] == ["A"] and rows[1]["start"] <= "2005-01-05"
    assert rows[2]["start"] >= "2012-01-02" and rows[3]["start"] >= "2020-01-01"


def test_correlated_instruments_add_little():
    common = np.random.default_rng(9).normal(0, 0.01, 6000)
    s = {f"S{i}": _series("2005-01-03", "2026-10-21", i, common, 0.8) for i in range(6)}
    p = dp.plan(s)
    assert p["rows"][-1]["n_eff"] < 2


def test_resampled_h1_agrees_with_its_own_daily_bars():
    idx = pd.date_range("2024-01-01", periods=24 * 400, freq="h", tz="UTC")
    idx = idx[idx.dayofweek < 5]
    close = 100 * np.exp(np.cumsum(np.random.default_rng(4).normal(0, 1e-3, idx.size)))
    h1 = pd.DataFrame({"close": close}, index=idx)
    d1 = h1.groupby(h1.index.normalize()).last()
    assert dp.cross_check(d1, h1)["agree"]
    shifted = d1.copy()
    shifted["close"] = shifted["close"].shift(1).bfill()
    assert not dp.cross_check(shifted, h1)["agree"]
