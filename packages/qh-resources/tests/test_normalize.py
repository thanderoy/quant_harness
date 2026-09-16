"""T4 — instrument neutrality, and mechanical disjointness.

Two families of test. The first asserts that a constant means the same thing
on USDJPY as on gold, which is what makes one strategy module runnable across
the universe. The second asserts that the seq=69 contamination cannot be
reproduced without the check firing -- including the case where provenance
has gone missing, which must fail rather than pass.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from resources.features.normalize import (
    ContaminationError,
    UntaggedSeries,
    assert_disjoint,
    atr_normalise,
    inputs_of,
    log_return,
    range_pct,
    tag,
    vol_zscore,
)

IDX = pd.date_range("2026-01-05", periods=40, freq="h", tz="UTC")


def _walk(level: float, scale: float) -> pd.Series:
    """A price path of a given level and proportional volatility."""
    rng = np.random.default_rng(0)
    steps = rng.normal(0, scale, len(IDX))
    return pd.Series(level * np.exp(np.cumsum(steps) ), index=IDX, name="close")


# -- instrument neutrality -------------------------------------------------


def test_log_return_is_identical_across_price_levels():
    """147 and 4,389 are the same market once expressed as log returns."""
    jpy = _walk(147.0, 0.002)
    gold = _walk(4389.0, 0.002)
    assert log_return(jpy).dropna().values == pytest.approx(
        log_return(gold).dropna().values)


def test_atr_normalise_is_identical_across_price_levels():
    """A 1.5-ATR stop is the same statement on both instruments."""
    move_jpy = pd.Series(np.full(len(IDX), 0.30), index=IDX, name="move")
    atr_jpy = tag(pd.Series(np.full(len(IDX), 0.20), index=IDX), "atr14")
    move_gold = pd.Series(np.full(len(IDX), 9.0), index=IDX, name="move")
    atr_gold = tag(pd.Series(np.full(len(IDX), 6.0), index=IDX), "atr14")

    assert atr_normalise(move_jpy, atr_jpy).values == pytest.approx(
        atr_normalise(move_gold, atr_gold).values)


def test_range_pct_is_identical_across_price_levels():
    h = pd.Series([147.3] * 5, index=IDX[:5], name="high")
    l = pd.Series([147.0] * 5, index=IDX[:5], name="low")
    c = pd.Series([147.1] * 5, index=IDX[:5], name="close")
    scale = 4389.0 / 147.0
    got = range_pct(h, l, c)
    scaled = range_pct(h * scale, l * scale, c * scale)
    assert got.values == pytest.approx(scaled.values)


def test_vol_zscore_is_scale_and_shift_invariant():
    x = _walk(147.0, 0.002).rename("x")
    z = vol_zscore(x, 10)
    z_shifted = vol_zscore((x * 30.0 + 1000.0).rename("x"), 10)
    assert z.dropna().values == pytest.approx(z_shifted.dropna().values)


# -- numerical guards ------------------------------------------------------


def test_zero_atr_gives_nan_not_an_explosion():
    move = pd.Series([1.0, 1.0, 1.0], index=IDX[:3], name="move")
    atr = tag(pd.Series([0.5, 0.0, -1.0], index=IDX[:3]), "atr14")
    out = atr_normalise(move, atr)
    assert out.iloc[0] == pytest.approx(2.0)
    assert out.iloc[1:].isna().all()


def test_non_positive_price_gives_nan_not_minus_inf():
    p = pd.Series([1.0, 0.0, 2.0, -3.0], index=IDX[:4], name="close")
    out = log_return(p)
    assert np.isfinite(out.dropna()).all()
    # A bad price poisons the return into it and the return out of it, so
    # every value here is NaN. That is the intended blast radius: -inf would
    # have been one "number" flowing into every downstream mean.
    assert out.isna().all()


def test_flat_window_zscore_is_nan_not_divide_by_zero():
    flat = pd.Series([5.0] * 12, index=IDX[:12], name="x")
    assert vol_zscore(flat, 5).isna().all()


def test_inverted_bar_is_refused():
    h = pd.Series([1.0, 0.5], index=IDX[:2], name="high")
    l = pd.Series([0.9, 0.9], index=IDX[:2], name="low")
    c = pd.Series([1.0, 1.0], index=IDX[:2], name="close")
    with pytest.raises(ValueError, match="high < low"):
        range_pct(h, l, c)


def test_masked_nan_bars_survive_normalisation():
    """A NaN from the panel mask must stay NaN, not become a number."""
    x = pd.Series([1.0, np.nan, 3.0, 4.0], index=IDX[:4], name="close")
    assert log_return(x).isna().iloc[:3].all()
    atr = tag(pd.Series([1.0] * 4, index=IDX[:4]), "atr14")
    assert atr_normalise(x, atr).isna().iloc[1]


def test_zscore_is_causal():
    """A spike at the end must not move an earlier value."""
    base = pd.Series(np.arange(20, dtype=float), index=IDX[:20], name="x")
    spiked = base.copy()
    spiked.iloc[-1] = 1000.0
    a, b = vol_zscore(base, 5), vol_zscore(spiked, 5)
    assert a.iloc[:-1].dropna().values == pytest.approx(
        b.iloc[:-1].dropna().values)


# -- mechanical disjointness ----------------------------------------------


def test_provenance_accumulates_through_composition():
    atr14 = tag(pd.Series([1.0] * 5, index=IDX[:5]), "atr14")
    atr100 = tag(pd.Series([2.0] * 5, index=IDX[:5]), "atr100")
    ratio = atr_normalise(atr14, atr100)
    assert inputs_of(ratio) == frozenset({"atr14", "atr100"})


def test_the_seq69_contamination_is_caught_without_being_declared():
    """vol_ratio = ATR(14)/ATR(100) against a target normalised by ATR(14)."""
    atr14 = tag(pd.Series([1.0] * 5, index=IDX[:5]), "atr14")
    atr100 = tag(pd.Series([2.0] * 5, index=IDX[:5]), "atr100")
    forward_move = pd.Series([0.3] * 5, index=IDX[:5], name="fwd_move")

    feature = atr_normalise(atr14, atr100)
    target = atr_normalise(forward_move, atr14)

    with pytest.raises(ContaminationError, match="atr14"):
        assert_disjoint(feature, target, name="vol_ratio")


def test_a_raw_units_target_is_the_escape_hatch():
    atr14 = tag(pd.Series([1.0] * 5, index=IDX[:5]), "atr14")
    atr100 = tag(pd.Series([2.0] * 5, index=IDX[:5]), "atr100")
    feature = atr_normalise(atr14, atr100)
    target_usd = pd.Series([0.3] * 5, index=IDX[:5], name="fwd_move_usd")
    assert_disjoint(feature, target_usd, name="vol_ratio")


def test_a_series_with_no_provenance_fails_rather_than_passes():
    """The check must not be able to succeed by default."""
    orphan = pd.Series([1.0, 2.0], index=IDX[:2])
    named = pd.Series([1.0, 2.0], index=IDX[:2], name="fwd_move")
    with pytest.raises(UntaggedSeries):
        assert_disjoint(orphan, named)


def test_arithmetic_outside_the_module_loses_provenance_loudly():
    atr14 = tag(pd.Series([1.0] * 5, index=IDX[:5]), "atr14")
    # Rebuilt from values, the way a numpy round-trip or a groupby result
    # arrives: same numbers, no provenance, no name.
    smuggled = pd.Series(atr14.to_numpy() * 2.0, index=IDX[:5])
    target = atr_normalise(
        pd.Series([0.3] * 5, index=IDX[:5], name="fwd"), atr14)
    with pytest.raises(UntaggedSeries):
        assert_disjoint(smuggled, target)


def test_tag_restores_provenance_after_outside_arithmetic():
    atr14 = tag(pd.Series([1.0] * 5, index=IDX[:5]), "atr14")
    restored = tag(atr14 * 2.0, "atr14")
    target = atr_normalise(
        pd.Series([0.3] * 5, index=IDX[:5], name="fwd"), atr14)
    with pytest.raises(ContaminationError):
        assert_disjoint(restored, target)


def test_a_zscore_is_qualified_by_its_window():
    x = pd.Series(np.arange(30, dtype=float), index=IDX[:30], name="x")
    assert inputs_of(vol_zscore(x, 20)) == frozenset({"x@z20"})


def test_the_same_series_over_different_windows_is_not_a_collision():
    x = pd.Series(np.arange(30, dtype=float), index=IDX[:30], name="x")
    assert_disjoint(vol_zscore(x, 5), vol_zscore(x, 20))


def test_the_same_series_over_the_same_window_is_a_collision():
    x = pd.Series(np.arange(30, dtype=float), index=IDX[:30], name="x")
    with pytest.raises(ContaminationError, match="z20"):
        assert_disjoint(vol_zscore(x, 20), vol_zscore(x, 20))


def test_a_named_raw_input_is_self_describing():
    s = pd.Series([1.0], index=IDX[:1], name="close")
    assert inputs_of(s) == frozenset({"close"})


def test_tag_requires_a_name():
    with pytest.raises(ValueError):
        tag(pd.Series([1.0], index=IDX[:1]))


def test_bad_windows_are_refused():
    x = pd.Series(np.arange(10, dtype=float), index=IDX[:10], name="x")
    with pytest.raises(ValueError, match="window"):
        vol_zscore(x, 1)
    with pytest.raises(ValueError, match="periods"):
        log_return(x, 0)
