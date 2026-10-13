"""event_drift: calendar and synthetic checks only. No real outcome is computed."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.pre import event_drift as ed


def _cal(times_utc: list[str], event: str = "NFP") -> pd.DataFrame:
    return pd.DataFrame({"event": event,
                         "utc": pd.to_datetime(times_utc, utc=True),
                         "verified": True})


def _series(n_weeks: int = 200, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2015-01-05", periods=n_weeks * 7 * 24, freq="h",
                        tz="UTC")
    idx = idx[idx.dayofweek < 5]
    r = rng.normal(0, 1e-3, idx.size)
    close = 100 * np.exp(np.cumsum(r))
    return pd.DataFrame({"open": close, "high": close, "low": close,
                         "close": close, "volume": 1.0}, index=idx)


def _plant(df: pd.DataFrame, cal: pd.DataFrame, effect: float) -> pd.DataFrame:
    """Make each event bar's next 4 bars continue (or reverse) its move."""
    df = df.copy()
    logc = np.log(df["close"].to_numpy())
    r = np.r_[0.0, np.diff(logc)]
    pos = pd.Series(np.arange(len(df)), index=df.index.tz_localize(None))
    for b in ed.server_bar(cal["utc"]).map(pos).dropna().astype(int):
        r[b] = 3e-3 * np.sign(r[b] or 1)
        r[b + 1:b + 5] += effect * r[b] / 4
    df["close"] = 100 * np.exp(np.cumsum(r))
    return df


def _weekly_events(df: pd.DataFrame, every: int = 2) -> pd.DataFrame:
    """An NFP-like Friday 12:30 UTC release every ``every`` weeks."""
    fridays = pd.date_range(df.index[0].normalize(), df.index[-1], freq="W-FRI")
    t = [f"{d.date()} 12:30" for d in fridays[::every]][2:-2]
    return _cal(t)


def _prepared(effect: float, seed: int = 0) -> dict:
    out = {}
    for k, sym in enumerate(("A", "B", "C")):
        base = _series(seed=seed + k)
        cal = _weekly_events(base)
        df = _plant(base, cal, effect)
        trad = np.ones(len(df), bool)
        ev = ed.instrument_events(df, trad, cal, ("NFP",), with_outcomes=True)
        bars = ed._bar_frame(df, trad)
        out[sym] = ed._Prepared(df.index, bars, ev, ed.quiet_mask(df.index, cal))
    return out


STRUCT = {"A": "fx", "B": "metals", "C": "equity_index"}


@pytest.mark.parametrize("utc,server", [
    ("2026-10-07 12:00", "2026-10-07 15:00"),   # EEST
    ("2026-01-14 13:30", "2026-01-14 15:00"),   # EET, half-hour release
    ("2025-03-21 12:30", "2025-03-21 14:00"),   # US on DST, EU not yet
])
def test_server_bar_follows_eu_dst(utc, server):
    got = ed.server_bar(pd.Series(pd.to_datetime([utc], utc=True)))
    assert got.iloc[0] == pd.Timestamp(server)


def test_feature_and_target_are_disjoint():
    assert ed.feature_spec()["feature_inputs"] == ["calendar_timestamp"]


def test_reach_is_fixed_by_currency():
    assert ed.REACH["USDJPY"] == ed.US_EVENTS
    assert "ECB" in ed.REACH["GER40"] and "ECB" in ed.REACH["EURUSD"]
    assert "BOE" in ed.REACH["GBPUSD"]
    assert not any("BOJ" in r for r in ed.REACH.values())


def test_quiet_mask_clears_24h_around_releases():
    df = _series(n_weeks=4)
    cal = _cal(["2015-01-14 12:00"])
    q = pd.Series(ed.quiet_mask(df.index, cal), index=df.index.tz_localize(None))
    centre = pd.Timestamp("2015-01-14 14:00")   # server bar of the release
    assert not q[centre - pd.Timedelta(hours=23):centre + pd.Timedelta(hours=23)].any()
    assert q[centre + pd.Timedelta(hours=25):].all()


def test_placebos_share_the_hour_of_week_and_avoid_the_event_week():
    df = _series(n_weeks=120)
    cal = _weekly_events(df, every=10)
    trad = np.ones(len(df), bool)
    ev = ed.instrument_events(df, trad, cal, ("NFP",))
    bars = ed._bar_frame(df, trad)
    ok = bars["clean_h4"].to_numpy() & ed.quiet_mask(df.index, cal)
    pos = ed.placebo_positions(df.index, ev["pos"].to_numpy(), ok,
                               np.random.default_rng(1))
    assert (pos >= 0).all()
    a, b = df.index[ev["pos"].to_numpy()], df.index[pos]
    assert (a.dayofweek == b.dayofweek).all() and (a.hour == b.hour).all()
    assert (abs((b - a).days) >= 7).all()
    assert ok[pos].all()


def test_load_calendar_keeps_scheduled_releases_with_a_time():
    cal = ed.load_calendar()
    assert len(cal) > 1000
    assert cal["utc"].dt.tz is not None
    assert set(cal["event"]) >= {"FOMC", "NFP", "CPI", "ECB", "BOE"}


@pytest.mark.parametrize("effect", [1.5, -1.5])
def test_a_planted_effect_of_either_sign_is_found(effect):
    res = ed.placebo_test(_prepared(effect), STRUCT, 4, n_permutations=200)
    assert res["p"] < 0.05
    assert np.sign(res["observed"]) == np.sign(effect)


def test_a_null_panel_is_not_found():
    res = ed.placebo_test(_prepared(0.0, seed=10), STRUCT, 4,
                          n_permutations=200)
    assert res["p"] > 0.05


def test_run_refuses_before_registration(tmp_path):
    (tmp_path / "entries.jsonl").write_text("")
    with pytest.raises(RuntimeError, match="not registered"):
        ed.run(data_dir=tmp_path, log_dir=tmp_path)


def test_parameters_are_one_set_for_the_whole_panel():
    params = ed.registration_parameters()
    assert not set(params) & set(ed.PANEL_2B)
    assert params["decisive_stream"] in ed.STREAMS


def test_a_friday_release_keeps_the_horizons_that_fit_before_the_weekend():
    """The NFP case: 8 bars to the weekly close, so h=1 and h=4 are measured
    and h=12 is not, instead of the event being dropped from all three."""
    df = _series(n_weeks=30)
    df = df[~((df.index.dayofweek == 4) & (df.index.hour >= 22))]
    trad = ed.build_panel_mask(df.index).tradable.to_numpy()
    cal = _cal(["2015-05-08 12:30"])     # server bar Fri 15:00
    ev = ed.instrument_events(df, trad, cal, ("NFP",), with_outcomes=True)
    assert len(ev) == 1
    assert np.isfinite(ev["y_h1"][0]) and np.isfinite(ev["y_h4"][0])
    assert np.isnan(ev["y_h12"][0])


def test_preregister_supplies_every_v2_field(tmp_path):
    from research import log as research_log
    (tmp_path / "entries.jsonl").write_text("")
    entry = ed.preregister(log_dir=tmp_path)
    for f in research_log.SCHEMA_V2_FIELDS:
        assert getattr(entry, f) is not None, f
    assert entry.counts_as_trial


def test_min_decidable_matches_the_intended_sample():
    from research.post.mintrl import min_decidable_sharpe
    got = min_decidable_sharpe(n_obs=ed.INTENDED_N_OBS, sr_star=0.0)
    assert round(got, 6) == ed.MIN_DECIDABLE_SHARPE
