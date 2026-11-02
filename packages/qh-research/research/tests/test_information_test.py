"""information_test on synthetic panels with a known amount of information."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from research.post.mintrl import NotDecidable
from research.pre import information_test as it
from research.pre.decisive_stream import declare
from research.pre.normalizer_check import ContaminationError

N_T, N_I = 3000, 8
FREE = dict(score_inputs={"score"}, target_normalizer=set())


def _panel(ic: float, seed: int, *, n_t: int = N_T, n_i: int = N_I,
           common: float = 0.0, drift: float = 0.0,
           live: np.ndarray | None = None) -> pd.DataFrame:
    """``target = ic·score + noise``, plus an optional market move shared by
    every instrument (and loaded on the score) and a constant drift.
    ``live`` masks the periods where the score carries information."""
    rng = np.random.default_rng(seed)
    m = rng.normal(size=(n_t, 1))
    score = rng.normal(size=(n_t, n_i)) + common * m
    k = ic if live is None else ic * live[:, None]
    noise = rng.normal(size=(n_t, n_i)) * math.sqrt(1 - ic ** 2)
    target = k * score + noise + common * m + drift
    t = np.repeat(np.arange(n_t), n_i)
    return pd.DataFrame({"time": t, "instrument": np.tile(np.arange(n_i), n_t),
                         "score": score.ravel(), "target": target.ravel()})


def _design(mode: str = "cross_sectional", n_i: int = N_I, **kw) -> it.Design:
    base = dict(n_periods=N_T, n_instruments=n_i, rho_bar=0.0, horizon=1,
                prior_ic=0.05, **FREE)
    return it.design(mode, **{**base, **kw})


def test_min_detectable_ic_is_the_closed_form():
    mde, t_eff, ne = it.min_detectable_ic(5000, 9, 0.44, 24)
    z = stats.norm.ppf(0.975) + stats.norm.ppf(0.8)
    assert t_eff == pytest.approx(5000 / 24)
    assert ne == pytest.approx(9 / (1 + 8 * 0.44))
    assert mde == pytest.approx(z / math.sqrt(t_eff * ne))
    # Correlation and overlap both cost power; length buys it back.
    assert it.min_detectable_ic(5000, 9, 0.8, 24)[0] > mde
    assert it.min_detectable_ic(5000, 9, 0.44, 48)[0] > mde
    assert it.min_detectable_ic(20000, 9, 0.44, 24)[0] < mde


def test_an_undetectable_prior_is_refused_at_registration():
    """F1: nine correlated pairs at H24 cannot see an IC of 0.03."""
    with pytest.raises(NotDecidable, match="below the"):
        it.design("cross_sectional", n_periods=4000, n_instruments=9,
                  rho_bar=0.44, horizon=24, prior_ic=0.03, **FREE)


def test_a_contaminated_score_is_refused_at_registration():
    with pytest.raises(ContaminationError, match="atr14"):
        _design(score_inputs={"atr14", "atr100"}, target_normalizer={"atr14"})


@pytest.mark.parametrize("mode,n_i", [("cross_sectional", 2),
                                      ("time_series", 3), ("pooled", 8)])
def test_a_mode_must_fit_the_panel(mode, n_i):
    with pytest.raises(ValueError):
        _design(mode, n_i=n_i)


def test_information_is_found_and_its_size_recovered():
    r = it.run(_panel(0.10, seed=1), _design())
    assert r.overall["p"] < 1e-6
    # Expected Spearman of n=8 normal pairs at Pearson 0.10 (Moran 1948):
    # a per-period rank IC over a small cross-section is shrunk toward zero.
    n, rho = N_I, 0.10
    want = (6 / math.pi) * ((n - 2) / (n + 1) * math.asin(rho / 2)
                            + math.asin(rho) / (2 * (n + 1)))
    assert r.overall["ic"] == pytest.approx(want, abs=0.01)
    assert r.monotonicity["monotonicity"] == 1.0


def test_no_information_is_not_found():
    r = it.run(_panel(0.0, seed=2), _design())
    assert r.overall["p"] > 0.05
    assert abs(r.overall["ic"]) < 0.02


def test_a_shared_market_move_is_ranked_out():
    """The time effect: a score loaded on the common move predicts every
    instrument's target together, and none of them relative to the others."""
    p = _panel(0.0, seed=3, common=2.0)
    pooled = stats.spearmanr(p["score"], p["target"]).statistic
    assert pooled > 0.5                      # what a pooled regression would see
    r = it.run(p, _design())
    assert abs(r.overall["ic"]) < 0.02 and r.overall["p"] > 0.05


def test_drift_does_not_make_every_bucket_look_profitable():
    """Screen rule 3: buckets are excess over the mean, not raw returns."""
    p = _panel(0.0, seed=4, n_i=1, drift=5.0)
    r = it.run(p, _design("time_series", n_i=1, prior_ic=0.1))
    assert max(abs(b) for b in r.monotonicity["excess_by_bucket"]) < 0.15


def test_the_conditional_check_separates_where_the_effect_should_live():
    live = (np.arange(N_T) % 2 == 0)
    p = _panel(0.15, seed=5, live=live.astype(float))
    cond = pd.Series(live, index=np.arange(N_T))
    r = it.run(p, _design(), condition=cond)
    assert r.in_condition["p"] < 1e-6
    assert r.out_condition["p"] > 0.05
    assert set(r.p_values) == set(it.STREAMS)
    stream = declare("ic_out_condition", 0.05, set(it.STREAMS),
                     rationale="the failure condition: no effect off auction days")
    assert stream.verdict(r.p_values)[0] == "FAIL"


def test_the_time_series_mode_recovers_a_single_instrument_ic():
    p = _panel(0.10, seed=6, n_i=1)
    r = it.run(p, _design("time_series", n_i=1, prior_ic=0.1))
    want = stats.spearmanr(p["score"], p["target"]).statistic
    assert r.overall["ic"] == pytest.approx(want, abs=1e-12)
    assert r.overall["p"] < 1e-3


def test_overlap_widens_the_standard_error():
    """A sum over h bars repeats h-1 of them in the next one; Newey-West at
    the overlap lag must not count those as fresh evidence."""
    rng = np.random.default_rng(7)
    x = pd.Series(rng.normal(0.02, 1, 20000)).rolling(24).sum().dropna().to_numpy()
    assert abs(it.nw_tstat(x, 23)) < abs(it.nw_tstat(x, 0)) / 3


def test_data_shorter_than_the_design_is_refused():
    with pytest.raises(NotDecidable, match="declared on"):
        it.run(_panel(0.1, seed=8, n_t=N_T - 1), _design())


def test_mean_abs_correlation():
    rng = np.random.default_rng(9)
    c = rng.normal(size=5000)
    w = pd.DataFrame({"a": c + rng.normal(size=5000),
                      "b": c + rng.normal(size=5000),
                      "c": rng.normal(size=5000)})
    # corr(a,b)=0.5, the other two pairs 0.
    assert it.mean_abs_correlation(w) == pytest.approx(0.5 / 3, abs=0.03)
    assert it.mean_abs_correlation(w[["a"]]) == 0.0
