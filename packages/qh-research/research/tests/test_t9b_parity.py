"""T9b — the post/ mask-off parity fixture, and that a failure localises.

Three jobs. The first is the parity check itself: the seq=49 walk-forward still
reproduces, trade for trade. The second is the part that is easy to get wrong
and invisible when you do — that a break at an early layer *stops*, instead of
reporting three more failures caused by the first one. The third is the ULP
policy, which is the whole reason this file can assert in CI at all: prices
descend from a `np.dot` reduction whose summation order belongs to the CPU, so
the bound has to absorb a kernel difference while still catching a logic
change.
"""

from __future__ import annotations

import json
import math

import pytest

from research import log as research_log
from research.parity import t9b_crest_n_keel as t9b

#: Acceptance coverage (docs/REWRITE.md §7). Read by
#: tests/test_x_coverage.py — keep in step with what this file asserts.
pytestmark = [pytest.mark.x("X15b"), pytest.mark.x("X15d")]


@pytest.fixture(scope="module")
def fixture() -> dict:
    return t9b.load_fixture()


@pytest.fixture(scope="module")
def report():
    """The full six-layer check. ~4s; every test below reads this one run."""
    return t9b.check_mask_off()


# -- the parity check ------------------------------------------------------

def test_mask_off_parity_holds(report):
    assert report.passed, (
        f"stopped at {report.stopped_at}: "
        f"{[(l.layer, l.failures[:3]) for l in report.layers if not l.passed]}")


def test_every_layer_the_spec_names_is_checked(report):
    assert [l.layer for l in report.layers] == [
        "bars_hash", "fold_geometry", "trade_counts", "trade_records",
        "trade_prices", "sharpe"]


def test_the_layers_are_checked_in_dependency_order(report):
    orders = [l.order for l in report.layers]
    assert orders == sorted(orders)


def test_trades_are_compared_trade_for_trade_not_in_aggregate(report):
    """X15b asks for trade-for-trade. A count check would also pass a run
    where every trade shifted a bar, so the element-wise layer has to carry
    a comparison per trade per field, not one per fold."""
    records = next(l for l in report.layers if l.layer == "trade_records")
    n_trades = sum(len(arm["trades"])
                   for tf in t9b.TIMEFRAMES
                   for fold in t9b.load_fixture()["folds"][tf]
                   for _, arm in t9b._arms(fold))
    assert records.n_compared == n_trades * 5


def test_timestamps_direction_and_volume_are_compared_exactly(report):
    """Discrete fields. An approximate comparison here would only hide a break:
    a timestamp is an index, a direction a label, a volume a lot-step multiple.
    """
    records = next(l for l in report.layers if l.layer == "trade_records")
    assert records.passed
    assert records.max_ulp is None  # no tolerance applied to this layer


def test_prices_and_sharpe_carry_a_ulp_bound_and_report_the_worst(report):
    for name in ("trade_prices", "sharpe"):
        layer = next(l for l in report.layers if l.layer == name)
        assert layer.passed
        assert layer.max_ulp is not None, (
            f"{name} must report drift even when it passes, or a slow walk "
            f"toward the bound is invisible until the day it breaks")
        assert layer.max_ulp <= t9b.PRICE_ULP_TOLERANCE


def test_the_aggregate_sharpe_is_checked_and_not_only_the_folds(report):
    layer = next(l for l in report.layers if l.layer == "sharpe")
    n_arms = sum(len(t9b._arms(fold))
                 for tf in t9b.TIMEFRAMES
                 for fold in t9b.load_fixture()["folds"][tf])
    assert layer.n_compared == n_arms + 1  # per-fold, plus the aggregate


# -- the ULP policy --------------------------------------------------------

def test_a_nan_reproduces_a_nan():
    """A fold whose config takes one trade reports NaN for every ratio metric.
    Under IEEE-754 `nan != nan`, which would report a break where the runs
    agree — this is not hypothetical, H4 fold 11 is exactly that fold."""
    assert t9b.ulp_distance(float("nan"), float("nan")) == 0
    assert t9b.ulp_distance(float("nan"), 1.0) > t9b.PRICE_ULP_TOLERANCE


def test_an_infinity_does_not_quietly_match_a_finite_number():
    """A profit factor with no losing trade is legitimately infinite. Treating
    that as a match to a finite number would hide the change this exists to
    catch."""
    assert t9b.ulp_distance(float("inf"), float("inf")) == 0
    assert t9b.ulp_distance(float("inf"), 1e308) > t9b.PRICE_ULP_TOLERANCE


def test_one_ulp_apart_is_one_ulp():
    x = 1993.4567
    assert t9b.ulp_distance(x, math.nextafter(x, math.inf)) == 1


def test_the_bound_is_far_below_a_tick():
    """The bound absorbs a BLAS kernel, not a decision. At a gold price near
    2000 the whole tolerance is well under a nanodollar, so no price inside it
    can move a fill, a bracket, or a comparison."""
    price = 2000.0
    drifted = price
    for _ in range(t9b.PRICE_ULP_TOLERANCE):
        drifted = math.nextafter(drifted, math.inf)
    assert abs(drifted - price) < 1e-9


def test_a_break_larger_than_the_bound_still_fails(fixture):
    """The tolerance must not be wide enough to swallow a real change. One
    cent on one entry price is the smallest thing anyone would call a bug."""
    import copy
    broken = copy.deepcopy(fixture)
    arm = broken["folds"]["H1"][0]["selected"]
    arm["trades"][0]["entry_px"] += 0.01
    r = t9b.check_mask_off(fixture=broken)
    assert not r.passed
    assert r.stopped_at == "trade_prices"


# -- failure localisation --------------------------------------------------

def test_a_fold_geometry_break_reports_nothing_downstream(fixture):
    """If the folds moved, a trade differing tells you nothing new."""
    import copy
    broken = copy.deepcopy(fixture)
    broken["folds"]["H1"][0]["test_end"] = "1999-01-01"
    r = t9b.check_mask_off(fixture=broken)
    assert not r.passed
    assert r.stopped_at == "fold_geometry"
    assert [l.layer for l in r.layers] == ["bars_hash", "fold_geometry"]


def test_a_missing_trade_stops_before_the_elementwise_comparison(fixture):
    """"One trade vanished" and "every trade shifted a bar" both break the
    element-wise layer and want different investigations, so the count is
    called out on its own."""
    import copy
    broken = copy.deepcopy(fixture)
    broken["folds"]["H1"][0]["selected"]["trades"].pop()
    r = t9b.check_mask_off(fixture=broken)
    assert r.stopped_at == "trade_counts"
    assert [l.layer for l in r.layers] == [
        "bars_hash", "fold_geometry", "trade_counts"]


def test_a_shifted_trade_names_the_fold_arm_and_trade(fixture):
    import copy
    broken = copy.deepcopy(fixture)
    broken["folds"]["H4"][0]["fixed"]["trades"][3]["entry_ts"] = "1999-01-01 00:00:00+00:00"
    r = t9b.check_mask_off(fixture=broken)
    assert r.stopped_at == "trade_records"
    assert any("H4 fold 0 fixed trade 3" in f for f in r.layers[-1].failures)


def test_a_direction_flip_is_caught(fixture):
    import copy
    broken = copy.deepcopy(fixture)
    t = broken["folds"]["H1"][0]["selected"]["trades"][0]
    t["direction"] = "short" if t["direction"] == "long" else "long"
    r = t9b.check_mask_off(fixture=broken)
    assert r.stopped_at == "trade_records"


def test_a_volume_change_is_caught(fixture):
    """T5 changes the sizer's signature. Without an assertion on volume a
    sizing regression would never surface here, which is the whole reason
    X15b was not relaxed to fold-level statistics."""
    import copy
    broken = copy.deepcopy(fixture)
    broken["folds"]["H1"][0]["selected"]["trades"][0]["lots"] += 0.01
    r = t9b.check_mask_off(fixture=broken)
    assert r.stopped_at == "trade_records"
    assert any("lots" in f for f in r.layers[-1].failures)


# -- the fixture's own provenance ------------------------------------------

def test_the_fixture_is_stamped_as_derived_and_never_as_the_original(fixture):
    assert fixture["provenance"] == "REGENERATED_FROM"
    assert "DERIVED" in fixture["provenance_note"]
    regen = fixture["regenerated"]
    assert regen["commit"]
    assert regen["date"]
    assert "not_the_original_stack" in regen
    assert "what_was_not_reproduced" in regen


def test_the_fixture_names_its_source_artifacts_by_hash(fixture):
    """The source artifacts are gitignored and carry no SHA of their own, so
    the only thing tying this fixture to them is the digest recorded here."""
    ids = {a["id"] for a in fixture["source_artifacts"]}
    assert ids == {"cnk_nested_wf_H1.json", "cnk_nested_wf_H4.json"}
    for a in fixture["source_artifacts"]:
        assert len(a["sha256"]) == 64
        assert a["tracked_in_git"] is False


def test_the_fixture_records_that_the_gate_passed(fixture):
    v = fixture["verification"]
    assert v["fold_boundaries_matched"] is True
    assert v["statistics_matched"] is True
    assert v["float_equality"] is True
    assert v["folds_checked"] == 33
    assert v["trade_records"] == 5277


def test_the_fixture_holds_trades_for_every_arm_of_every_fold(fixture):
    for tf in t9b.TIMEFRAMES:
        for fold in fixture["folds"][tf]:
            for name, arm in t9b._arms(fold):
                assert isinstance(arm["trades"], list)
                for t in arm["trades"]:
                    assert set(t) >= {"entry_ts", "exit_ts", "direction",
                                      "entry_px", "exit_px", "lots", "size_oz"}


# -- the log event ---------------------------------------------------------

def test_the_fixture_event_never_counts_as_a_trial(tmp_path, report):
    research_log.register_hypothesis("seed", title="t", mechanism="m",
                                     log_dir=tmp_path)
    before = research_log.trial_count(tmp_path)
    entry = t9b.log_parity_fixture(report, log_dir=tmp_path)
    assert entry.event_type == research_log.EventType.PARITY_FIXTURE
    assert entry.counts_as_trial is False
    assert research_log.trial_count(tmp_path) == before
    ok, msg = research_log.verify(tmp_path)
    assert ok, msg


def test_the_event_says_the_verdict_is_not_reopened(tmp_path, report):
    entry = t9b.log_parity_fixture(report, log_dir=tmp_path)
    assert "not reopened" in entry.note or "not a new trial" in entry.note
    assert entry.metrics["mode"] == "mask_off"


def test_the_event_carries_the_fixtures_derived_provenance(tmp_path, report):
    """A green parity run against a derived fixture means less than one against
    an original artifact. The log should not let a reader forget which it was."""
    entry = t9b.log_parity_fixture(report, log_dir=tmp_path)
    assert entry.metrics["fixture_provenance"] == "REGENERATED_FROM"
    assert "DERIVED" in entry.note


# -- the recording hook ----------------------------------------------------

def test_recording_is_opt_in_and_changes_no_metric():
    """`record_trades` appends dicts and touches nothing a metric reads. If it
    ever did, this fixture would be pinning the instrumented arithmetic rather
    than the real one."""
    from research.post.sweeps import cnk_engine as engine
    from research.post.sweeps import run_cnk_sweep as sweep
    from research.post.sweeps.data import load

    df = load("H4")
    bars = engine.Bars(df.iloc[:4000])
    hma_v = engine.hma(bars.close, 55)
    atr_v = engine.atr(bars.high, bars.low, bars.close, 14)
    long_sig, short_sig = engine.momentum_signals(bars, hma_v)
    kw = dict(enable_long=True, enable_short=False, sl_mult=0.0, tp_mult=0.0,
              trail_mult=3.0, risk_pct=sweep.RISK_PCT, min_atr=0.0,
              max_dd_halt=1.0)

    off = engine.simulate(bars, "momentum", hma_v, atr_v, long_sig, short_sig,
                          **kw)
    on = engine.simulate(bars, "momentum", hma_v, atr_v, long_sig, short_sig,
                         record_trades=True, **kw)

    assert off["records"] == []
    assert len(on["records"]) == on["n_trades"] > 0
    assert engine.metrics(off, basis="price") == engine.metrics(on, basis="price")
    assert (off["px_returns"] == on["px_returns"]).all()
    assert off["equity_final"] == on["equity_final"]
