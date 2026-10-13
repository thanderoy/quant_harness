"""cot_residual: synthetic checks only. No real outcome is computed."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.pre import cot_positioning as cp
from research.pre import cot_residual as cr


def _world(n: int = 700, seed: int = 0, info: float = 0.0):
    """Weekly intervals where returns mean-revert and positioning chases them.

    ``info`` adds a positioning component, independent of past returns, that
    moves the next interval contrarian-wise. info=0: any raw effect is pure
    price reversal and the residual must find nothing.
    """
    rng = np.random.default_rng(seed)
    eps = rng.normal(0, 1, n)
    own = rng.normal(0, 1, n)
    r = np.zeros(n)
    for t in range(1, n):
        r[t] = -0.35 * r[t - 1] - info * 0.35 * own[t - 1] + eps[t]
    r13 = pd.Series(r).rolling(13).sum().to_numpy()
    z = np.nan_to_num(0.8 * r + 0.3 * r13) + info * own + 0.3 * rng.normal(0, 1, n)
    # Build H1 bars whose interval returns are r, one interval per 120 bars.
    per = 120
    idx = pd.date_range("2011-01-03", periods=n * per, freq="h", tz="UTC")
    bar = np.repeat(r * 1e-3 / per, per)
    close = 100 * np.exp(np.cumsum(bar))
    df = pd.DataFrame({"open": close, "high": close, "low": close,
                       "close": close, "volume": 1.0}, index=idx)
    # Bar labels are server time; a release 30 minutes into each interval's
    # last bar is that server wall-clock instant, expressed in UTC.
    last = idx[np.arange(n) * per + per - 1].tz_localize(None)
    release = ((last + pd.Timedelta(minutes=30))
               .tz_localize(cp.SERVER_TZ, ambiguous="NaT", nonexistent="NaT")
               .tz_convert("UTC"))
    sig = pd.DataFrame({"report_date": last, "release": release, "signal": z})
    sig = sig[sig["release"].notna()].reset_index(drop=True)
    return df, sig


def _test(info: float, use_raw: bool) -> dict:
    frames, labels, st = {}, {}, {}
    for k, s in enumerate(cp.STRUCTURES):
        df, sig = _world(seed=k, info=info)
        fr = cr.instrument_frame(df, sig, with_outcomes=True)
        frames[s] = fr
        labels[s] = cp.label_terciles(fr["raw"] if use_raw else fr["signal"])
        st[s] = s
    return cp.rotation_test(frames, labels, st, 1, n_permutations=200)


def test_residualise_is_causal():
    rng = np.random.default_rng(0)
    z, x = rng.normal(size=400), rng.normal(size=(400, 2))
    a = cr.residualise(z, x)
    z2 = z.copy()
    z2[300:] += 10
    b = cr.residualise(z2, x)
    np.testing.assert_array_equal(a[:300], b[:300])


def test_residual_removes_a_linear_dependence_on_past_returns():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(600, 2))
    z = 2 * x[:, 0] - x[:, 1] + 0.1 * rng.normal(size=600)
    res = cr.residualise(z, x)
    ok = np.isfinite(res)
    assert abs(np.corrcoef(res[ok], x[ok, 0])[0, 1]) < 0.1
    assert np.nanstd(res) < 0.2


def test_pure_price_reversal_is_found_raw_and_not_in_the_residual():
    """The case the test exists for: positioning only chases returns."""
    raw, res = _test(0.0, use_raw=True), _test(0.0, use_raw=False)
    assert raw["p"] < 0.05 and raw["observed"] < 0
    assert res["p"] > 0.05


def test_information_beyond_past_returns_survives_the_residual():
    res = _test(1.0, use_raw=False)
    assert res["p"] < 0.05 and res["observed"] < 0


def test_counting_computes_no_outcome():
    df, sig = _world()
    fr = cr.instrument_frame(df, sig)
    assert not [c for c in fr if c.startswith("y_h")]


def test_count_and_run_select_the_same_rows():
    df, sig = _world()
    a = cr.instrument_frame(df, sig)
    b = cr.instrument_frame(df, sig, with_outcomes=True)
    assert a["pos"].tolist() == b["pos"].tolist()


def test_run_refuses_before_registration(tmp_path):
    (tmp_path / "entries.jsonl").write_text("")
    with pytest.raises(RuntimeError, match="not registered"):
        cr.run(data_dir=tmp_path, log_dir=tmp_path)


def test_preregister_supplies_every_v2_field(tmp_path):
    from research import log as research_log
    (tmp_path / "entries.jsonl").write_text("")
    entry = cr.preregister(5000, 0.02, log_dir=tmp_path)
    for f in research_log.SCHEMA_V2_FIELDS:
        assert getattr(entry, f) is not None, f
    assert entry.parameters["decisive_stream"] == "pooled_p_h1"
