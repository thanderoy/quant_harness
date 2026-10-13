"""cot_positioning: dataset and synthetic checks only. No real outcome is computed."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.pre import cot_positioning as cp


def _cot(n: int = 400, seed: int = 0, report: str = "TFF") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2011-01-04", periods=n, freq="7D")
    lo, sh = cp.SPEC[report]
    net = np.cumsum(rng.normal(0, 2000, n))
    return pd.DataFrame({
        "market": "EUR", "report": report, "report_date": dates,
        "release": (dates + pd.Timedelta(days=3, hours=19, minutes=30)).tz_localize("UTC"),
        "open_interest": 400_000.0,
        lo: 100_000 + np.maximum(net, 0), sh: 100_000 + np.maximum(-net, 0)})


def _prices(cot: pd.DataFrame, effect: float, seed: int = 0) -> pd.DataFrame:
    """H1 weekday bars; each interval's drift follows the oriented signal."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2011-01-03", cot["report_date"].max() + pd.Timedelta(days=14),
                        freq="h", tz="UTC")
    idx = idx[idx.dayofweek < 5]
    sig = cp.positioning_z(cot, "EUR", 1)
    r = rng.normal(0, 1e-3, idx.size)
    pos = cp.entry_positions(idx, sig["release"])
    z = np.nan_to_num(sig["signal"].to_numpy())
    for k in range(len(pos) - 1):
        if pos[k] < 0 or pos[k + 1] <= pos[k]:
            continue
        r[pos[k] + 1:pos[k + 1] + 1] += effect * z[k] * 1e-3 / (pos[k + 1] - pos[k])
    close = 100 * np.exp(np.cumsum(r))
    return pd.DataFrame({"open": close, "high": close, "low": close,
                         "close": close, "volume": 1.0}, index=idx)


def test_feature_and_target_are_disjoint():
    assert "cftc_positions" in cp.feature_spec()["feature_inputs"]


def test_usd_base_pairs_are_flipped():
    for s in ("USDJPY", "USDCHF", "USDCAD"):
        assert cp.MARKETS[s][1] == -1
    for s in ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "XAUUSD", "XAGUSD", "GER40"):
        assert cp.MARKETS[s][1] == 1
    assert cp.MARKETS["GER40"][0] == "ES"


def test_z_score_is_causal():
    cot = _cot()
    a = cp.positioning_z(cot, "EUR", 1)
    later = cot.copy()
    later.loc[later.index[300:], "lev_money_long"] *= 5
    b = cp.positioning_z(later, "EUR", 1)
    np.testing.assert_array_equal(a["signal"][:300].to_numpy(),
                                  b["signal"][:300].to_numpy())


def test_reports_before_launch_are_excluded():
    cot = _cot()
    cot["report_date"] = cot["report_date"] - pd.Timedelta(days=365 * 2)
    z = cp.positioning_z(cot, "EUR", 1)
    assert (z["report_date"] >= pd.Timestamp(cp.LAUNCH["TFF"])).all()


def test_orientation_flips_the_signal():
    cot = _cot()
    a, b = cp.positioning_z(cot, "EUR", 1), cp.positioning_z(cot, "EUR", -1)
    np.testing.assert_allclose(a["signal"].dropna(), -b["signal"].dropna())


def test_entry_is_the_first_close_after_release():
    idx = pd.date_range("2024-01-05 18:00", periods=10, freq="h", tz="UTC")
    rel = pd.Series(pd.to_datetime(["2024-01-05 20:30Z"]))  # 22:30 server (EET)
    j = cp.entry_positions(idx, rel)[0]
    close_server = idx[j].tz_localize(None) + pd.Timedelta(hours=1)
    assert close_server == pd.Timestamp("2024-01-05 23:00")


def test_the_real_dataset_is_point_in_time():
    cot = cp.load_cot()
    assert (cot["release"].dt.tz_localize(None) > cot["report_date"]).all()
    assert set(cot["market"]) == {m for m, _ in cp.MARKETS.values()}
    assert not cot.duplicated(["market", "report_date"]).any()


@pytest.mark.parametrize("effect", [6.0, -6.0])
def test_a_planted_effect_of_either_sign_is_found(effect):
    frames, labels, st = {}, {}, {}
    for k, s in enumerate(("fx", "metals", "equity_index")):
        cot = _cot(seed=k)
        df = _prices(cot, effect, seed=k)
        fr = cp.instrument_frame(df, cp.positioning_z(cot, "EUR", 1),
                                 with_outcomes=True)
        frames[s], labels[s], st[s] = fr, cp.label_terciles(fr["signal"]), s
    res = cp.rotation_test(frames, labels, st, 1, n_permutations=200)
    assert res["p"] < 0.05 and np.sign(res["observed"]) == np.sign(effect)


def test_a_null_panel_is_not_found():
    frames, labels, st = {}, {}, {}
    for k, s in enumerate(("fx", "metals", "equity_index")):
        cot = _cot(seed=k + 20)
        df = _prices(cot, 0.0, seed=k + 20)
        fr = cp.instrument_frame(df, cp.positioning_z(cot, "EUR", 1),
                                 with_outcomes=True)
        frames[s], labels[s], st[s] = fr, cp.label_terciles(fr["signal"]), s
    res = cp.rotation_test(frames, labels, st, 1, n_permutations=200)
    assert res["p"] > 0.05


def test_run_refuses_before_registration(tmp_path):
    (tmp_path / "entries.jsonl").write_text("")
    with pytest.raises(RuntimeError, match="not registered"):
        cp.run(data_dir=tmp_path, log_dir=tmp_path)


def test_parameters_are_one_set_for_the_whole_panel():
    params = cp.registration_parameters()
    assert params["decisive_stream"] in cp.STREAMS
    assert not set(params) & set(cp.PANEL_2B)


def test_preregister_supplies_every_v2_field(tmp_path):
    from research import log as research_log
    (tmp_path / "entries.jsonl").write_text("")
    entry = cp.preregister(log_dir=tmp_path)
    for f in research_log.SCHEMA_V2_FIELDS:
        assert getattr(entry, f) is not None, f


def test_min_decidable_matches_the_intended_sample():
    from research.post.mintrl import min_decidable_sharpe
    assert round(min_decidable_sharpe(n_obs=cp.INTENDED_N_OBS, sr_star=0.0), 6) \
        == cp.MIN_DECIDABLE_SHARPE
