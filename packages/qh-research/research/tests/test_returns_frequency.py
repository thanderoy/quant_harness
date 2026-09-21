"""Returns carry their own frequency — closing a class, not an instance.

Five wrong numbers in this repo came from one mechanism: a numeric parameter
that could be defaulted or passed without anyone saying where it came from.
Three already have guards (X14, X24, X31). This is the fix for the other two,
and the test that matters is not that the guard fires — it is that the mistake
**cannot be expressed**.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from research.metrics.core import sharpe_ratio
from research.metrics.returns import (
    BAR_PERIODS_PER_YEAR,
    FrequencyConflict,
    Returns,
    resolve_periods_per_year,
)


def _v(n=2500, seed=0):
    return np.random.default_rng(seed).normal(0.001, 0.01, n)


# -- the case that started it ----------------------------------------------

def test_a_bar_frequency_cannot_be_applied_to_trade_returns():
    """The 7.01 case, made unreachable.

    2,497 trade returns over 21.6 years annualised with periods_per_year=6048
    produced a Sharpe of 7.01. The right factor was trades per year, about
    116, and sqrt(6048/116) is about 7 — the whole figure was the constant.
    The returns now know they are trades, so the constant has nowhere to go.
    """
    trades = Returns.from_trades(_v(), span_days=21.6 * 365.25)
    assert trades.kind == "trade"
    assert trades.periods_per_year == pytest.approx(116, rel=0.05)
    with pytest.raises(FrequencyConflict, match="6048"):
        sharpe_ratio(trades, 6048)


def test_the_conflict_names_both_claims():
    """An error that says only "conflict" leaves the reader to guess which
    number was wrong."""
    trades = Returns.from_trades(_v(), span_days=7889.4)
    with pytest.raises(FrequencyConflict) as e:
        sharpe_ratio(trades, 6048)
    msg = str(e.value)
    assert "trades over" in msg      # what the returns say
    assert "6048" in msg             # what was passed


def test_trade_frequency_is_derived_from_the_span_not_asserted():
    ten_years = Returns.from_trades(np.zeros(1000) + 0.001,
                                    span_days=10 * 365.25)
    one_year = Returns.from_trades(np.zeros(1000) + 0.001, span_days=365.25)
    assert one_year.periods_per_year == pytest.approx(
        10 * ten_years.periods_per_year, rel=1e-6)


# -- bar returns ------------------------------------------------------------

@pytest.mark.parametrize("tf,expected", list(BAR_PERIODS_PER_YEAR.items()))
def test_each_known_timeframe_has_its_documented_frequency(tf, expected):
    assert Returns.from_bars(_v(10), tf).periods_per_year == expected


def test_h1_matches_the_readme_table():
    assert Returns.from_bars(_v(10), "H1").periods_per_year == 6048


def test_an_unknown_timeframe_fails_at_construction():
    """A typo should be a KeyError where it is written, not a plausible
    Sharpe three calls later."""
    with pytest.raises(KeyError):
        Returns.from_bars(_v(10), "H3")


# -- the resolver -----------------------------------------------------------

def test_a_bare_array_without_a_frequency_is_refused_not_defaulted():
    """The default is the defect. Refusing is the whole point."""
    with pytest.raises(ValueError, match="required"):
        sharpe_ratio(_v())


def test_a_bare_array_with_an_explicit_frequency_still_works():
    """The type is the better path, not the only one — existing call sites
    that state their frequency stay valid."""
    assert math.isfinite(sharpe_ratio(_v(), 252))


def test_agreeing_values_are_not_a_conflict():
    bars = Returns.from_bars(_v(), "D1")
    assert sharpe_ratio(bars, 252) == pytest.approx(sharpe_ratio(bars))


def test_the_resolver_reports_what_it_resolved():
    bars = Returns.from_bars(_v(), "H4")
    values, ppy = resolve_periods_per_year(bars, None)
    assert ppy == 1512
    assert len(values) == 2500


# -- overriding -------------------------------------------------------------

def test_an_override_must_give_a_reason():
    bars = Returns.from_bars(_v(), "H1")
    with pytest.raises(ValueError, match="why"):
        bars.with_periods_per_year(252, "")


def test_an_override_is_recorded_rather_than_silent():
    bars = Returns.from_bars(_v(), "H1")
    o = bars.with_periods_per_year(252, "resampled to daily downstream")
    assert o.periods_per_year == 252
    assert o.overridden
    assert "resampled to daily" in o.provenance
    assert o.meta["overridden_from"] == 6048
    assert not bars.overridden          # the original is untouched


def test_an_override_stops_the_conflict_it_was_asked_for():
    bars = Returns.from_bars(_v(), "H1")
    o = bars.with_periods_per_year(252, "deliberate")
    assert math.isfinite(sharpe_ratio(o, 252))


# -- interop ----------------------------------------------------------------

def test_returns_behave_as_an_array_where_one_is_expected():
    bars = Returns.from_bars(_v(), "D1")
    assert np.asarray(bars).shape == (2500,)
    assert len(bars) == 2500


def test_a_zero_or_negative_span_is_refused():
    with pytest.raises(ValueError, match="span_days"):
        Returns.from_trades(_v(), span_days=0)
