"""T9a — the mask-off parity fixture, and that a failure localises.

Two jobs. The first is the parity check itself: the seq=31 numbers still
reproduce. The second is the part that is easy to get wrong and invisible
when you do — that a break at an early layer *stops*, instead of reporting
four more failures caused by the first one.
"""

from __future__ import annotations

import json

import pytest

from research import log as research_log
from research.parity import t9a_flood_tide as t9a

#: Acceptance coverage (docs/REWRITE.md §7). Read by
#: tests/test_x_coverage.py — keep in step with what this file asserts.
pytestmark = [pytest.mark.x("X15a"), pytest.mark.x("X15d")]



#: Recomputation needs seq=31's OHLC CSVs. They live in the WMPS repo and are
#: not in this one, so on a CI runner they are simply absent — which is how
#: the first CI run failed with a FileNotFoundError on an absolute path from
#: my laptop. Those tests skip; the fixture-validation tests below do not,
#: so X15a keeps a real assertion in CI rather than disappearing from it.
needs_source_data = pytest.mark.skipif(
    not t9a.source_data_available(),
    reason=(f"seq=31 OHLC inputs not present; set ${t9a.DATA_DIR_ENV} to the "
            f"directory holding XAUUSD_H1.csv and XAUUSD_H4.csv"))


@pytest.fixture(scope="module")
def report():
    if not t9a.source_data_available():
        pytest.skip("seq=31 OHLC inputs not present")
    return t9a.check_mask_off()


@needs_source_data
def test_mask_off_parity_holds(report):
    assert report.passed, (
        f"stopped at {report.stopped_at}: "
        f"{[l.detail for l in report.layers if not l.passed]}")


@needs_source_data
def test_every_layer_the_spec_names_is_checked(report):
    layers = [l.layer for l in report.layers]
    assert layers[:4] == [
        "ohlc_hash", "signal_hash", "n_long_signals", "signal_timestamps"]
    assert {"e_ratio_h20", "e_ratio_h50", "e_ratio_h100"} <= set(layers)


@needs_source_data
def test_the_layers_are_checked_in_dependency_order(report):
    orders = [l.order for l in report.layers]
    assert orders == sorted(orders)


@needs_source_data
def test_the_signal_count_is_the_adjudicated_one(report):
    n = next(l for l in report.layers if l.layer == "n_long_signals")
    assert n.expected == 1669
    assert n.actual == 1669


@needs_source_data
def test_e_ratios_match_at_float_equality(report):
    ref = t9a.load_reference()
    want = {int(r["horizon"]): r["e_ratio"] for r in ref["results_by_horizon"]}
    for h, expected in want.items():
        layer = next(l for l in report.layers if l.layer == f"e_ratio_h{h}")
        assert layer.actual == expected  # not approx — float equality
        assert isinstance(layer.actual, float)


@needs_source_data
def test_horizons_are_recorded_as_tradable_bars(report):
    """R4. Mask-off it makes no difference; recorded so it isn't inferred."""
    assert report.horizon_unit == "tradable_bars"


def test_the_fixture_pins_the_timestamps_elementwise():
    fx = json.loads(t9a.FIXTURE.read_text())
    assert len(fx["signal_timestamps"]) == 1669
    assert fx["horizon_unit"] == "tradable_bars"
    assert fx["mode"] == "mask_off"
    assert fx["signal_hash"] == t9a.load_reference()[
        "edge_report_metadata"]["signal_hash"]


# -- failure localisation --------------------------------------------------

def _stub(monkeypatch, **overrides):
    real = t9a.recompute

    def fake(h1, h4, n_permutations=1):
        got = dict(real(h1, h4, n_permutations))
        got.update(overrides)
        return got

    monkeypatch.setattr(t9a, "recompute", fake)


@needs_source_data
def test_a_data_loader_break_reports_nothing_downstream(monkeypatch):
    """If the OHLC moved, the signal hash differing tells you nothing new."""
    _stub(monkeypatch, ohlc_hash="deadbeefdeadbeef")
    r = t9a.check_mask_off()
    assert not r.passed
    assert r.stopped_at == "ohlc_hash"
    assert len(r.layers) == 1


@needs_source_data
def test_a_signal_break_stops_before_the_e_ratios(monkeypatch):
    _stub(monkeypatch, signal_hash="0000000000000000")
    r = t9a.check_mask_off()
    assert not r.passed
    assert r.stopped_at == "signal_hash"
    assert [l.layer for l in r.layers] == ["ohlc_hash", "signal_hash"]


@needs_source_data
def test_a_count_break_is_separated_from_a_shift(monkeypatch):
    """Both break the hash; they want different investigations."""
    _stub(monkeypatch, n_long_signals=1670)
    r = t9a.check_mask_off()
    assert r.stopped_at == "n_long_signals"
    assert r.layers[-1].expected == 1669


@needs_source_data
def test_a_shifted_timestamp_names_the_index(monkeypatch):
    fx = json.loads(t9a.FIXTURE.read_text())
    shifted = list(fx["signal_timestamps"])
    shifted[7] = "1999-01-01T00:00:00+00:00"
    _stub(monkeypatch, signal_timestamps=shifted)
    r = t9a.check_mask_off()
    assert r.stopped_at == "signal_timestamps"
    assert "index 7" in r.layers[-1].detail


@needs_source_data
def test_an_e_ratio_break_names_the_horizon(monkeypatch):
    ref = t9a.load_reference()
    e = {int(x["horizon"]): x["e_ratio"] for x in ref["results_by_horizon"]}
    e[50] = e[50] + 1e-12
    _stub(monkeypatch, e_ratios=e)
    r = t9a.check_mask_off()
    assert r.stopped_at == "e_ratio_h50"


# -- the log event ---------------------------------------------------------

@needs_source_data
def test_the_fixture_event_never_counts_as_a_trial(tmp_path, report):
    research_log.register_hypothesis("seed", title="t", mechanism="m",
                                     log_dir=tmp_path)
    before = research_log.trial_count(tmp_path)
    entry = t9a.log_parity_fixture(report, log_dir=tmp_path)
    assert entry.event_type == research_log.EventType.PARITY_FIXTURE
    assert entry.counts_as_trial is False
    assert research_log.trial_count(tmp_path) == before
    ok, msg = research_log.verify(tmp_path)
    assert ok, msg


@needs_source_data
def test_the_event_says_the_verdict_is_not_reopened(tmp_path, report):
    entry = t9a.log_parity_fixture(report, log_dir=tmp_path)
    assert "not reopened" in entry.note or "not a new trial" in entry.note
    assert entry.metrics["mode"] == "mask_off"


# -- runnable without the source data -------------------------------------
# These validate the committed fixture against the committed reference
# artifact. No CSV, no recomputation — so X15a is still genuinely asserted on
# a runner, rather than skipped into a green tick that means nothing.


def test_the_fixture_agrees_with_the_adjudicated_artifact():
    fx = json.loads(t9a.FIXTURE.read_text())
    meta = t9a.load_reference()["edge_report_metadata"]
    assert fx["ohlc_hash"] == meta["ohlc_hash"]
    assert fx["signal_hash"] == meta["signal_hash"]
    assert fx["n_long_signals"] == int(meta["n_long_signals"]) == 1669


def test_the_fixture_pins_every_horizon_at_float_equality():
    fx = json.loads(t9a.FIXTURE.read_text())
    want = {str(r["horizon"]): r["e_ratio"]
            for r in t9a.load_reference()["results_by_horizon"]}
    assert fx["e_ratios"] == want


def test_the_fixture_timestamp_count_matches_the_signal_count():
    fx = json.loads(t9a.FIXTURE.read_text())
    assert len(fx["signal_timestamps"]) == fx["n_long_signals"]
    assert fx["signal_timestamps"] == sorted(fx["signal_timestamps"])


def test_the_fixture_records_the_horizon_convention():
    fx = json.loads(t9a.FIXTURE.read_text())
    assert fx["horizon_unit"] == "tradable_bars"
    assert fx["mode"] == "mask_off"
