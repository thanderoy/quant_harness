"""equity_fx_lead: synthetic checks only. No real outcome is computed."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.pre import equity_fx_lead as ef


def _pair(lead: float, n: int = 6000, seed: int = 0):
    """Weekday H1 bars where the follower's next return loads on the leader's."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-06", periods=n * 7 // 5 + 200, freq="h", tz="UTC")
    idx = idx[idx.dayofweek < 5][:n]
    rl = rng.normal(0, 1e-3, n)
    rf = rng.normal(0, 1e-3, n) + 0.5 * rl
    rf[1:] += lead * rl[:-1]
    def frame(r):
        c = 100 * np.exp(np.cumsum(r))
        return pd.DataFrame({"open": c, "high": c, "low": c, "close": c,
                             "volume": 1.0}, index=idx)
    return frame(rl), frame(rf)


def _frames(lead: float) -> dict:
    out = {}
    for k, s in enumerate(ef.FOLLOWERS):
        leader, follower = _pair(lead, seed=k)
        out[s] = ef.pair_frame(leader, follower, 1, with_outcomes=True)
    return out


@pytest.mark.parametrize("lead", [0.1, -0.1])
def test_a_planted_lead_of_either_sign_is_found(lead):
    res = ef.rotation_test(_frames(lead), 1, n_permutations=200)
    assert res["p"] < 0.05 and np.sign(res["observed"]) == np.sign(lead)


def test_a_purely_contemporaneous_link_is_not_a_lead():
    """The gold/dollar case: strong same-hour co-movement, no lead."""
    f = _frames(0.0)
    res = ef.rotation_test(f, 1, n_permutations=200)
    assert res["p"] > 0.05
    same = np.mean([np.mean(v["x"] * v["same_hour"]) for v in f.values()])
    assert same > 0.3


def test_orientation_flips_the_outcome():
    leader, follower = _pair(0.1)
    a = ef.pair_frame(leader, follower, 1, with_outcomes=True)
    b = ef.pair_frame(leader, follower, -1, with_outcomes=True)
    np.testing.assert_allclose(a["y_h1"], -b["y_h1"])


def test_the_feature_is_causal():
    leader, follower = _pair(0.0)
    a = ef.pair_frame(leader, follower, 1)
    later = leader.copy()
    later.iloc[4000:, :4] *= 3
    b = ef.pair_frame(later, follower, 1)
    cut = a["time"] < leader.index[4000]
    np.testing.assert_array_equal(a.loc[cut, "x"], b.loc[b["time"] < leader.index[4000], "x"])


def test_no_outcome_straddles_a_gap():
    leader, follower = _pair(0.0)
    follower = follower.drop(follower.index[3000:3003])
    fr = ef.pair_frame(leader, follower, 1, with_outcomes=True)
    t = fr["time"].to_numpy("datetime64[ns]")
    gap_start = np.datetime64(leader.index[2999].tz_localize(None))
    h = max(ef.HORIZONS)
    near = (t > gap_start - np.timedelta64(h, "h")) & (t <= gap_start)
    assert not near.any()


def test_counting_computes_no_outcome():
    leader, follower = _pair(0.0)
    fr = ef.pair_frame(leader, follower, 1)
    assert not [c for c in fr if c.startswith("y_h") or c == "same_hour"]


def test_count_and_run_select_the_same_rows():
    leader, follower = _pair(0.0)
    a = ef.pair_frame(leader, follower, 1)
    b = ef.pair_frame(leader, follower, 1, with_outcomes=True)
    assert a["time"].tolist() == b["time"].tolist()


def test_feature_and_target_are_disjoint():
    spec = ef.feature_spec()
    assert not set(spec["feature_inputs"]) & set(spec["target_normalizer"])


def test_run_refuses_before_registration(tmp_path):
    (tmp_path / "entries.jsonl").write_text("")
    with pytest.raises(RuntimeError, match="not registered"):
        ef.run(data_dir=tmp_path, log_dir=tmp_path)


def test_preregister_supplies_every_v2_field(tmp_path):
    from research import log as research_log
    (tmp_path / "entries.jsonl").write_text("")
    entry = ef.preregister(log_dir=tmp_path)
    for f in research_log.SCHEMA_V2_FIELDS:
        assert getattr(entry, f) is not None, f
    assert entry.parameters["decisive_stream"] == "pooled_p_h1"


def test_min_decidable_matches_the_intended_sample():
    from research.post.mintrl import min_decidable_sharpe
    assert round(min_decidable_sharpe(n_obs=ef.INTENDED_N_OBS, sr_star=0.0), 6) \
        == ef.MIN_DECIDABLE_SHARPE


def test_a_follower_without_same_hour_co_movement_voids_the_run():
    stream = ef.decisive_stream()
    res = {"h1": {"observed": 0.01, "p": 0.01,
                  "per_instrument": {"A": {"observed": 0.01}, "B": {"observed": 0.01}}}}
    assert ef.verdict(res, stream, {"A": 0.3, "B": -0.01})[0] == "VOID"
    assert ef.verdict(res, stream, {"A": 0.3, "B": 0.2})[0] == "ALIVE"
