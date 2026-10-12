"""activity_reversal: synthetic checks only. No real outcome is computed here."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.pre import activity_reversal as ar
from research.pre.normalizer_check import ContaminationError, assert_disjoint


def _series(n_weeks: int = 60, seed: int = 0, effect: float = 0.0) -> pd.DataFrame:
    """Weekday H1 bars with a planted activity -> follow-through link.

    A bar with high volume is followed, over the next 4 bars, by a move of
    ``effect`` x its own return in the same direction; low volume, the
    opposite. ``effect=0`` is a pure null.
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-06", periods=n_weeks * 7 * 24, freq="h", tz="UTC")
    idx = idx[idx.dayofweek < 5]
    n = idx.size
    vol = np.exp(rng.normal(0, 0.5, n)) * 1000
    r = rng.normal(0, 1e-3, n)
    z = (np.log(vol / 1000)) / 0.5
    for i in range(n - 5):
        if abs(r[i]) > 1e-3:
            r[i + 1:i + 5] += effect * np.sign(z[i]) * r[i] / 4
    close = 100 * np.exp(np.cumsum(r))
    return pd.DataFrame({"open": close, "high": close, "low": close,
                         "close": close, "volume": vol}, index=idx)


def _panel(effect: float) -> tuple[dict, dict, dict]:
    frames, labels, structure = {}, {}, {}
    for k, (sym, st) in enumerate([("A", "fx"), ("B", "metals"),
                                   ("C", "equity_index")]):
        df = _series(seed=k, effect=effect)
        trad = np.ones(len(df), bool)
        trad[(df.index.dayofweek == 0) & (df.index.hour == 0)] = False
        ev = ar.instrument_events(df, trad, with_outcomes=True)
        frames[sym], labels[sym] = ev, ar.label_terciles(ev["activity"])
        structure[sym] = st
    return frames, labels, structure


def test_feature_and_target_are_disjoint():
    spec = ar.feature_spec()
    assert spec["feature_inputs"] == ["volume"]
    with pytest.raises(ContaminationError):
        assert_disjoint({"volume", "close_logret_std"}, {"close_logret_std"})


def test_relative_activity_is_causal():
    df = _series(n_weeks=20)
    a = ar.relative_activity(df["volume"])
    t = df.index[len(df) // 2]
    later = df["volume"].copy()
    later[later.index > t] *= 50
    b = ar.relative_activity(later)
    pd.testing.assert_series_equal(a[a.index <= t], b[b.index <= t])


def test_relative_activity_compares_like_hours_only():
    """A volume regime that differs by hour must not read as activity."""
    df = _series(n_weeks=20)
    v = pd.Series(np.where(df.index.hour < 12, 100.0, 10_000.0), index=df.index)
    a = ar.relative_activity(v).dropna()
    assert len(a) and np.allclose(a, 0.0)


def test_a_feed_break_blanks_one_baseline_window():
    df = _series(n_weeks=30)
    a = ar.relative_activity(df["volume"], breaks=("2020-04-06",))
    start = pd.Timestamp("2020-04-06", tz="UTC")
    inside = a[(a.index >= start) & (a.index < start + pd.Timedelta(weeks=8))]
    after = a[a.index >= start + pd.Timedelta(weeks=8)]
    assert inside.isna().all() and after.notna().any()


def test_events_never_share_a_forward_bar():
    df = _series(n_weeks=40)
    ev = ar.instrument_events(df, np.ones(len(df), bool))
    pos = df.index.get_indexer(ev["time"])
    assert (np.diff(pos) > max(ar.HORIZONS)).all()


def test_no_event_window_crosses_a_masked_bar():
    df = _series(n_weeks=40)
    trad = np.ones(len(df), bool)
    trad[::50] = False
    ev = ar.instrument_events(df, trad)
    pos = df.index.get_indexer(ev["time"])
    for p in pos:
        assert trad[p + 1:p + max(ar.HORIZONS) + 1].all()


def test_thin_keeps_the_first_of_a_cluster():
    assert ar.thin(np.array([0, 3, 12, 13, 30]), 12).tolist() == [0, 13, 30]


def test_rotation_never_sits_at_identity():
    rng = np.random.default_rng(0)
    lab = np.arange(100)
    for _ in range(200):
        shift = int(np.argmax(ar._rotate(lab, rng) == 0))
        assert 10 <= shift <= 90


@pytest.mark.parametrize("effect", [1.5, -1.5])
def test_a_planted_effect_of_either_sign_is_found(effect):
    frames, labels, structure = _panel(effect)
    res = ar.permutation_test(frames, labels, structure, 4, n_permutations=200)
    assert res["p"] < 0.05
    assert np.sign(res["observed"]) == np.sign(effect)


def test_a_null_panel_is_not_found():
    frames, labels, structure = _panel(0.0)
    res = ar.permutation_test(frames, labels, structure, 4, n_permutations=200)
    assert res["p"] > 0.05


def test_verdict_requires_every_structure():
    stream = ar.decisive_stream()
    res = {"h4": {"p": 0.001, "observed": 0.2,
                  "per_structure": {"fx": {"observed": 0.2}}}}
    assert ar.verdict(res, stream, {"fx"})[0] == "UNTESTED_STRUCTURE"


def test_verdict_separates_pooled_only_from_alive():
    stream = ar.decisive_stream()
    ps = {"fx": {"observed": 0.2}, "metals": {"observed": 0.1},
          "equity_index": {"observed": -0.05}}
    res = {"h4": {"p": 0.01, "observed": 0.08, "per_structure": ps}}
    tested = set(ar.STRUCTURES)
    assert ar.verdict(res, stream, tested)[0] == "ALIVE_POOLED_ONLY"
    ps["equity_index"]["observed"] = 0.01
    assert ar.verdict(res, stream, tested)[0] == "ALIVE"
    res["h4"]["p"] = 0.2
    assert ar.verdict(res, stream, tested)[0] == "DEAD"


def test_run_refuses_before_registration(tmp_path):
    (tmp_path / "entries.jsonl").write_text("")
    with pytest.raises(RuntimeError, match="not registered"):
        ar.run(data_dir=tmp_path, log_dir=tmp_path)


def test_parameters_are_one_set_for_the_whole_panel():
    params = ar.registration_parameters()
    assert not set(params) & set(ar.PANEL_2B)
    assert params["decisive_stream"] in ar.STREAMS
    assert params["two_sided"] is True


def test_preregister_supplies_every_v2_field(tmp_path):
    from research import log as research_log
    (tmp_path / "entries.jsonl").write_text("")
    entry = ar.preregister(log_dir=tmp_path)
    for f in research_log.SCHEMA_V2_FIELDS:
        assert getattr(entry, f) is not None, f
    assert entry.counts_as_trial
    assert entry.parameters["decisive_stream"] == "pooled_p_h4"


def test_min_decidable_matches_the_intended_sample():
    from research.post.mintrl import min_decidable_sharpe
    got = min_decidable_sharpe(n_obs=ar.INTENDED_N_OBS, sr_star=0.0)
    assert round(got, 6) == ar.MIN_DECIDABLE_SHARPE


def test_log_result_kills_unless_alive(tmp_path):
    from research import log as research_log
    (tmp_path / "entries.jsonl").write_text("")
    ar.preregister(log_dir=tmp_path)
    res = {"verdict": "DEAD", "reason": "p", "streams": {},
           "results": {"h4": {"observed": 0.0, "per_structure": {}}},
           "instruments": []}
    e = ar.log_result(res, "a.json", log_dir=tmp_path)
    assert e.verdict == research_log.Verdict.KILLED and not e.counts_as_trial
