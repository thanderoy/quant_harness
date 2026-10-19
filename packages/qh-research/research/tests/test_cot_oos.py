"""cot_oos: synthetic checks only. No real outcome is computed."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.pre import cot_oos as co
from research.pre import cot_positioning as cp


def _frames(effect: float, n: int = 400, seed: int = 0) -> dict:
    rng = np.random.default_rng(seed)
    out = {}
    for k, s in enumerate(("EURUSD", "XAUUSD", "GER40")):
        x = rng.normal(size=n)
        x = pd.Series(x).rolling(4, min_periods=1).mean().to_numpy() * 2
        y = effect * x + rng.normal(size=n)
        out[s] = pd.DataFrame({"signal": x, "y": y})
    return out


def _structure(frames: dict) -> dict:
    return {s: {"EURUSD": "fx", "XAUUSD": "metals", "GER40": "equity_index"}[s]
            for s in frames}


@pytest.mark.parametrize("effect", [0.3, -0.3])
def test_a_planted_effect_of_either_sign_is_found(effect):
    f = _frames(effect)
    res = co.rotation_test(f, _structure(f), n_permutations=200)
    assert res["p"] < 0.05 and np.sign(res["observed"]) == np.sign(effect)


def test_a_null_panel_is_not_found():
    f = _frames(0.0, seed=7)
    res = co.rotation_test(f, _structure(f), n_permutations=200)
    assert res["p"] > 0.05


def test_the_outcome_is_not_centred():
    """A steady drift must reach the outcome: seq=146's flaw removed it."""
    rng = np.random.default_rng(0)
    idx = pd.date_range("2020-01-01", periods=4000, freq="h", tz="UTC")
    close = 100 * np.exp(np.cumsum(2e-4 + rng.normal(0, 1e-3, idx.size)))
    df = pd.DataFrame({"close": close}, index=idx)
    fr = pd.DataFrame({"pos": np.arange(0, 4000, 40)})
    y = co.add_raw_outcome(df, fr)["y"].to_numpy()
    assert np.nanmean(y) > 0.5


def test_the_outcome_scale_uses_only_earlier_intervals():
    rng = np.random.default_rng(1)
    idx = pd.date_range("2020-01-01", periods=4000, freq="h", tz="UTC")
    close = 100 * np.exp(np.cumsum(rng.normal(0, 1e-3, idx.size)))
    df = pd.DataFrame({"close": close}, index=idx)
    fr = pd.DataFrame({"pos": np.arange(0, 4000, 40)})
    a = co.add_raw_outcome(df, fr)["y"].to_numpy()
    later = df.copy()
    later.iloc[3200:, 0] *= np.exp(np.linspace(0, 1, 800))
    b = co.add_raw_outcome(later, fr)["y"].to_numpy()
    np.testing.assert_array_equal(a[:79], b[:79])


def test_only_reports_after_the_cut_are_scored():
    dates = pd.date_range("2026-08-04", periods=20, freq="7D")
    fr = pd.DataFrame({"report_date": dates, "signal": 1.0,
                       "pos": np.arange(20) * 120})
    keep = co.oos_rows(fr)
    assert (dates[keep] > pd.Timestamp(co.IN_SAMPLE_LAST_REPORT)).all()
    assert not keep[-1]   # no next interval yet
    assert keep.sum() == (dates > pd.Timestamp(co.IN_SAMPLE_LAST_REPORT)).sum() - 1


def test_the_committed_dataset_has_no_out_of_sample_rows_yet():
    cot = cp.load_cot()
    assert cot["report_date"].max() == pd.Timestamp(co.IN_SAMPLE_LAST_REPORT)


def test_the_in_sample_digest_matches_the_committed_dataset():
    co.check_dataset_extension(pd.read_csv(cp.COT))


def test_a_revised_in_sample_row_stops_the_run():
    cot = pd.read_csv(cp.COT)
    cot.loc[cot.index[5], "lev_money_long"] += 1
    with pytest.raises(RuntimeError, match="append only"):
        co.check_dataset_extension(cot)


def test_an_appended_row_does_not_change_the_digest():
    cot = pd.read_csv(cp.COT)
    extra = cot.iloc[[-1]].copy()
    extra["report_date"] = "2026-10-13"
    co.check_dataset_extension(pd.concat([cot, extra], ignore_index=True))


def test_the_look_waits_for_its_date_and_its_sample():
    full = {s: {"n_intervals": co.OOS_MIN_INTERVALS} for s in ("A", "B")}
    short = {**full, "B": {"n_intervals": co.OOS_MIN_INTERVALS - 1}}
    assert not co.ready(full, pd.Timestamp("2027-10-17"))[0]
    assert not co.ready(short, pd.Timestamp("2028-01-01"))[0]
    assert co.ready(full, pd.Timestamp(co.EARLIEST_RUN))[0]


def test_run_refuses_before_registration(tmp_path):
    (tmp_path / "entries.jsonl").write_text("")
    with pytest.raises(RuntimeError, match="not registered"):
        co.run(data_dir=tmp_path, log_dir=tmp_path)


def test_preregister_supplies_every_v2_field(tmp_path):
    from research import log as research_log
    (tmp_path / "entries.jsonl").write_text("")
    entry = co.preregister(log_dir=tmp_path)
    for f in research_log.SCHEMA_V2_FIELDS:
        assert getattr(entry, f) is not None, f
    assert entry.parameters["decisive_stream"] == "pooled_p"
    assert entry.parameters["looks"] == 1


def test_min_decidable_matches_the_intended_sample():
    from research.post.mintrl import min_decidable_sharpe
    assert round(min_decidable_sharpe(n_obs=co.INTENDED_N_OBS, sr_star=0.0), 6) \
        == co.MIN_DECIDABLE_SHARPE
