"""lbma_fix_reversal: synthetic checks only. No real outcome is computed."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from research.pre import lbma_fix_reversal as lf


def _table(reversal: float, which: str = "pm", n_days: int = 1200,
           seed: int = 0) -> pd.DataFrame:
    """London-minute opens; post-auction return loads on the pre-auction one."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-06", periods=n_days)
    minutes = np.arange(0, 24 * 60, 5)
    steps = rng.normal(0, 5e-4, (n_days, len(minutes)))
    auction = lf.anchors(which)[0]
    i = {m: k for k, m in enumerate(minutes)}
    logp = np.cumsum(steps, axis=1)
    pre = logp[:, i[auction - 5]] - logp[:, i[auction - 30]]
    shift = reversal * pre
    logp[:, i[auction] + 1:] += 0.0
    for k in range(i[auction] + 1, i[auction + 30] + 1):
        frac = (k - i[auction]) / 6
        logp[:, k] += shift * frac
    logp[:, i[auction + 30] + 1:] += shift[:, None]
    return pd.DataFrame(2000 * np.exp(logp), index=dates, columns=minutes)


def test_placebos_never_touch_either_auction_window():
    for which in lf.AUCTIONS:
        auction, placebos = lf.anchors(which)
        assert len(placebos) == 31 and auction not in placebos
        for f in ("10:30", "15:00"):
            assert all(abs(t - lf._minutes(f)) > 60 for t in placebos)


def test_a_planted_reversal_is_ranked_first():
    res = lf.placebo_test(_table(-0.8), "pm")
    assert res["observed"] < 0
    assert res["streams"]["p_placebo_rank"] == pytest.approx(1 / 32)


def test_a_planted_continuation_does_not_pass_the_one_sided_rank():
    res = lf.placebo_test(_table(+0.8), "pm")
    assert res["streams"]["p_placebo_rank"] > 0.9
    assert res["streams"]["p_placebo_rank_two_sided"] == pytest.approx(1 / 32)


def test_no_planted_effect_is_not_ranked_first():
    res = lf.placebo_test(_table(0.0, seed=3), "am")
    assert res["streams"]["p_placebo_rank"] > 1 / 32


def test_missing_auction_days_are_void():
    t = _table(-0.8, n_days=lf.MIN_DAYS - 1)
    res = lf.placebo_test(t, "pm")
    assert lf.verdict(res, lf.decisive_stream())[0] == "VOID"


@pytest.mark.parametrize("p,fade,label", [
    (0.20, 5.0, "DEAD"), (0.03, 0.10, "UNTRADEABLE"), (0.03, 1.0, "ALIVE")])
def test_the_verdict_applies_the_registered_rule(p, fade, label):
    res = {"decidable": True, "streams": {"p_placebo_rank": p},
           "fade_gross_usd": fade}
    assert lf.verdict(res, lf.decisive_stream())[0] == label


@pytest.mark.parametrize("which", sorted(lf.AUCTIONS))
def test_run_refuses_before_registration(tmp_path, which):
    with pytest.raises(RuntimeError, match="not registered"):
        lf.run(which, log_dir=tmp_path)


def test_feature_inputs_are_disjoint_from_the_target_normalizer():
    spec = lf.feature_spec()
    assert not set(spec["feature_inputs"]) & set(spec["target_normalizer"])
