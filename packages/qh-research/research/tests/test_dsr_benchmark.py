"""T8 — the economic benchmark, and what its absence was costing.

Before T8 the DSR asked "did this beat nothing?". The question is "did this
beat the alternative?", and on gold those are very different: D5 puts XAUUSD
buy-and-hold at 0.6343 annualised over 2013-2026, so a zero benchmark handed
every gold strategy that entire Sharpe for free.

The tests that matter are the ones that would pass again if someone restored
a default.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

from research import log as research_log
from research.post.dsr import (
    MissingBenchmark,
    benchmark_from_d5,
    benchmark_from_registration,
    deflated_sharpe_ratio,
    log_dsr_evaluation,
)
from research.log import SelectionRule

#: D5, XAUUSD buy-and-hold, 2013-10 to 2026-08.
XAUUSD_BH_ANNUALISED = 0.6343
XAUUSD_BH_PER_OBS = XAUUSD_BH_ANNUALISED / math.sqrt(252)

REPO = Path(__file__).resolve().parents[4]


def _returns(mu=0.0008, sd=0.01, n=2000, seed=0):
    return np.random.default_rng(seed).normal(mu, sd, n)


def test_benchmark_sharpe_has_no_default():
    """A default would silently preserve the pre-T8 leniency."""
    with pytest.raises(TypeError, match="benchmark_sharpe"):
        deflated_sharpe_ratio(_returns(), n_trials=26)


def test_a_real_benchmark_is_strictly_harder_than_zero():
    r = _returns()
    lenient = deflated_sharpe_ratio(r, benchmark_sharpe=0.0, n_trials=26)
    honest = deflated_sharpe_ratio(
        r, benchmark_sharpe=XAUUSD_BH_PER_OBS, n_trials=26)
    assert honest.dsr < lenient.dsr


def test_the_gold_benchmark_moves_a_verdict():
    """Not a rounding difference — this is the size of the effect."""
    r = _returns()
    lenient = deflated_sharpe_ratio(r, benchmark_sharpe=0.0, n_trials=26)
    honest = deflated_sharpe_ratio(
        r, benchmark_sharpe=XAUUSD_BH_PER_OBS, n_trials=26)
    assert lenient.dsr > 0.5
    assert honest.dsr < 0.15


def test_sr_star_splits_into_benchmark_and_selection():
    r = _returns()
    res = deflated_sharpe_ratio(
        r, benchmark_sharpe=XAUUSD_BH_PER_OBS, n_trials=26)
    assert res.sr_star == pytest.approx(
        res.benchmark_sharpe + res.sr_star_selection)
    assert res.benchmark_sharpe == pytest.approx(XAUUSD_BH_PER_OBS)


def test_the_split_distinguishes_two_different_failures():
    """Beaten by the haircut is not the same as beaten by the alternative."""
    r = _returns()
    searched = deflated_sharpe_ratio(r, benchmark_sharpe=0.0, n_trials=10_000)
    benched = deflated_sharpe_ratio(
        r, benchmark_sharpe=XAUUSD_BH_PER_OBS, n_trials=1)
    assert searched.sr_star_selection > searched.benchmark_sharpe
    assert benched.benchmark_sharpe > benched.sr_star_selection


def test_a_zero_benchmark_reproduces_the_old_numbers():
    """Kept so historical sweep outputs still verify against the new code."""
    r = _returns()
    res = deflated_sharpe_ratio(r, benchmark_sharpe=0.0, n_trials=26)
    assert res.sr_star == pytest.approx(res.sr_star_selection)
    assert res.benchmark_sharpe == 0.0


def test_a_grossly_annualised_benchmark_is_refused():
    with pytest.raises(ValueError, match="divide by sqrt"):
        deflated_sharpe_ratio(_returns(), benchmark_sharpe=1.76, n_trials=26)


def test_the_guard_cannot_catch_golds_annualised_value():
    """Pinned as a known limitation, not an oversight.

    XAUUSD's 0.6343 annualised is a perfectly plausible per-observation
    Sharpe, so nothing in the number distinguishes the two. The guard catches
    1.76 and lets this through 16x too large. That is precisely why
    benchmark_from_d5() exists: the conversion happens once, in one place,
    rather than being remembered at each call site.
    """
    res = deflated_sharpe_ratio(
        _returns(), benchmark_sharpe=XAUUSD_BH_ANNUALISED, n_trials=26)
    assert res.benchmark_sharpe == XAUUSD_BH_ANNUALISED  # accepted, and wrong


def test_benchmark_from_d5_reads_and_converts(tmp_path):
    art = tmp_path / "phase0.json"
    art.write_text(json.dumps({"d5_benchmark_sharpe": {"per_instrument": [
        {"symbol": "XAUUSD", "buy_and_hold_sharpe_annualised": 0.6343},
        {"symbol": "EURUSD", "buy_and_hold_sharpe_annualised": -0.1571},
    ]}}))
    assert benchmark_from_d5("XAUUSD", art) == pytest.approx(XAUUSD_BH_PER_OBS)
    assert benchmark_from_d5("EURUSD", art) < 0


def test_benchmark_from_d5_names_what_it_has(tmp_path):
    art = tmp_path / "phase0.json"
    art.write_text(json.dumps({"d5_benchmark_sharpe": {"per_instrument": [
        {"symbol": "XAUUSD", "buy_and_hold_sharpe_annualised": 0.6343}]}}))
    with pytest.raises(KeyError, match="XAUUSD"):
        benchmark_from_d5("BTCUSD", art)


def test_the_real_d5_artifact_still_parses():
    """The conversion path works against the committed Phase 0 artifact."""
    art = sorted(REPO.glob("phase0/phase0_universe_*.json"))[-1]
    got = benchmark_from_d5("XAUUSD", art)
    assert got == pytest.approx(XAUUSD_BH_PER_OBS, abs=1e-4)
    assert benchmark_from_d5("EURUSD", art) < 0


def test_psr_vs_zero_is_still_measured_against_zero():
    """It is the unconditional diagnostic; the benchmark must not enter it."""
    r = _returns()
    a = deflated_sharpe_ratio(r, benchmark_sharpe=0.0, n_trials=26)
    b = deflated_sharpe_ratio(
        r, benchmark_sharpe=XAUUSD_BH_PER_OBS, n_trials=26)
    assert a.psr_vs_zero == pytest.approx(b.psr_vs_zero)


# -- sourcing it from the pre-registration --------------------------------

def test_benchmark_comes_from_the_registration(tmp_path):
    research_log.migrate_schema(log_dir=tmp_path)
    research_log.register_hypothesis(
        "h1", title="t", mechanism="m",
        universe=["XAUUSD"], selection_rule=SelectionRule.POOLED_ALL,
        null_baseline_structure="regime_filtered_random_entry",
        benchmark_sharpe=XAUUSD_BH_PER_OBS,
        min_decidable_sharpe=0.05,
        registry_snapshot="pepperstone_live_20260906",
        log_dir=tmp_path)
    assert benchmark_from_registration("h1", tmp_path) == pytest.approx(
        XAUUSD_BH_PER_OBS)


def test_a_v1_registration_has_no_benchmark_to_read(tmp_path):
    research_log.register_hypothesis(
        "old", title="t", mechanism="m", log_dir=tmp_path)
    with pytest.raises(MissingBenchmark, match="schema v1"):
        benchmark_from_registration("old", tmp_path)


def test_an_unknown_hypothesis_is_refused(tmp_path):
    with pytest.raises(MissingBenchmark, match="no HYPOTHESIS event"):
        benchmark_from_registration("nope", tmp_path)


def test_the_evaluation_records_the_benchmark_it_used(tmp_path):
    research_log.migrate_schema(log_dir=tmp_path)
    research_log.register_hypothesis(
        "h1", title="t", mechanism="m",
        universe=["XAUUSD"], selection_rule=SelectionRule.POOLED_ALL,
        null_baseline_structure="random_entry",
        benchmark_sharpe=XAUUSD_BH_PER_OBS, min_decidable_sharpe=0.05,
        registry_snapshot="snap", log_dir=tmp_path)
    res = deflated_sharpe_ratio(
        _returns(), benchmark_sharpe=XAUUSD_BH_PER_OBS, n_trials=26)
    entry = log_dsr_evaluation("h1", res, log_dir=tmp_path)

    assert entry.metrics["benchmark_sharpe_per_obs"] == pytest.approx(
        XAUUSD_BH_PER_OBS, abs=1e-6)
    assert "sr_star_selection_per_obs" in entry.metrics
    assert "benchmark" in entry.note
    ok, msg = research_log.verify(tmp_path)
    assert ok, msg
