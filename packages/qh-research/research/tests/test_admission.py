"""The admission gate: integrity only, and nothing enters a universe without it."""

from __future__ import annotations

import pandas as pd
import pytest

from research import admission as adm


def _frame(index: pd.DatetimeIndex) -> pd.DataFrame:
    n = len(index)
    base = pd.Series(range(n), index=index, dtype=float) * 0.01 + 100.0
    return pd.DataFrame({"open": base, "high": base + 1, "low": base - 1,
                         "close": base + 0.5}, index=index)


def _hours(start: str, days: int) -> pd.DatetimeIndex:
    """Weekday hourly bars, 23 a day, the shape of a real H1 export."""
    out = []
    for d in pd.bdate_range(start, periods=days, tz="UTC"):
        out.extend(d + pd.Timedelta(hours=h) for h in range(23))
    return pd.DatetimeIndex(out)


def test_a_clean_hourly_series_is_admitted_whole():
    a = adm.admit_frame("X", "H1", _frame(_hours("2020-01-06", 60)))
    assert a.verdict == adm.ADMIT
    assert a.census["bars_before_admitted"] == 0


def test_a_daily_prefix_moves_the_start():
    daily = pd.bdate_range("2019-06-03", periods=40, tz="UTC")
    hourly = _hours("2019-08-05", 60)
    a = adm.admit_frame("X", "H1", _frame(daily.append(hourly)))
    assert a.verdict == adm.ADMIT_FROM
    assert pd.Timestamp(a.admit_from) == hourly[0]


def test_six_bars_a_day_is_h4_not_h1():
    """GER40's middle stretch: enough bars to look dense, four hours apart."""
    h4 = pd.DatetimeIndex([d + pd.Timedelta(hours=h)
                           for d in pd.bdate_range("2019-06-03", periods=40, tz="UTC")
                           for h in range(0, 24, 4)])
    hourly = _hours("2019-08-05", 60)
    a = adm.admit_frame("X", "H1", _frame(h4.append(hourly)))
    assert a.verdict == adm.ADMIT_FROM
    assert pd.Timestamp(a.admit_from) == hourly[0]


def test_a_holiday_half_day_still_conforms():
    idx = _hours("2020-01-06", 30)
    half = idx[(idx.normalize() != pd.Timestamp("2020-01-20", tz="UTC"))
               | (idx.hour < 10)]
    assert adm.admit_frame("X", "H1", _frame(half)).verdict == adm.ADMIT


def test_an_undeclared_hole_refuses_and_a_declared_one_does_not(monkeypatch):
    idx = _hours("2020-01-06", 30).append(_hours("2020-03-02", 30))
    a = adm.admit_frame("X", "H1", _frame(idx))
    assert a.verdict == adm.REFUSE
    assert a.census["undeclared_holes"]

    monkeypatch.setitem(adm.KNOWN_HOLES, "X", [("2020-02-14", "2020-03-02")])
    assert adm.admit_frame("X", "H1", _frame(idx)).verdict == adm.ADMIT


def test_off_grid_bars_refuse():
    idx = _hours("2020-01-06", 30)
    idx = idx.insert(5, idx[4] + pd.Timedelta(minutes=30))
    assert adm.admit_frame("X", "H1", _frame(idx)).verdict == adm.REFUSE


def test_a_low_above_the_body_refuses():
    df = _frame(_hours("2020-01-06", 30))
    df.iloc[10, df.columns.get_loc("low")] = df["open"].iloc[10] + 5
    a = adm.admit_frame("X", "H1", df)
    assert a.verdict == adm.REFUSE
    assert any("bracket" in r for r in a.reasons)


def test_require_raises_on_refusal(tmp_path):
    idx = _hours("2020-01-06", 30).append(_hours("2020-03-02", 30))
    df = _frame(idx)
    lines = ["Date;Open;High;Low;Close;Volume"] + [
        f"{t:%Y.%m.%d %H:%M};{r.open};{r.high};{r.low};{r.close};1"
        for t, r in df.iterrows()]
    (tmp_path / "HOLED_H1.csv").write_text("\n".join(lines) + "\n")
    with pytest.raises(adm.AdmissionRefused):
        adm.require("HOLED", "H1", tmp_path)


def test_the_panel_will_not_run_an_unadmitted_instrument(tmp_path):
    from research.pre.panel_edge import check_panel

    idx = _hours("2020-01-06", 30).append(_hours("2020-03-02", 30))
    df = _frame(idx)
    lines = ["Date;Open;High;Low;Close;Volume"] + [
        f"{t:%Y.%m.%d %H:%M};{r.open};{r.high};{r.low};{r.close};1"
        for t, r in df.iterrows()]
    (tmp_path / "HOLED_H1.csv").write_text("\n".join(lines) + "\n")
    with pytest.raises(adm.AdmissionRefused):
        check_panel(data_dir=tmp_path, n_permutations=1, symbols=("HOLED",))


def test_xauusd_is_admitted_with_its_declared_broker_hole():
    """The tracked file, so this runs on CI."""
    a = adm.admit("XAUUSD", "H1")
    assert a.verdict == adm.ADMIT
    assert a.census["declared_holes"]
    assert not a.census["undeclared_holes"]
