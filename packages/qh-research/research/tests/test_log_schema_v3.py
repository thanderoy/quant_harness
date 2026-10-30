"""Schema v3 — the mechanism fields, demanded at registration.

Same contract as v2: additive (the chain verifies across the marker and no
earlier line re-serialises), optional before the marker, required after it.
The new part is the prior, which has to be a probability and is read back
by ``prior_calibration``.
"""

from __future__ import annotations

import json

import pytest

from research import log
from research.log import (
    SchemaFieldsRequired,
    SelectionRule,
    Stage,
    Verdict,
)

REAL_LOG = log.DEFAULT_LOG_DIR

V2 = dict(universe=["XAUUSD"], selection_rule=SelectionRule.POOLED_ALL,
          null_baseline_structure="regime-eligible random entries",
          benchmark_sharpe=0.0, min_decidable_sharpe=1.2,
          registry_snapshot="pepperstone_live_20261009b")

V3 = dict(counterparty="Benchmark desks that must fill at the fix price",
          information_source="LBMA auction schedule, outside the price series",
          failure_condition="No reversal on days the auction is cancelled",
          prior_survival=0.1)


@pytest.fixture
def pre_v3(tmp_path):
    """The real log as it stood immediately before the v3 marker."""
    d = tmp_path / "log"
    d.mkdir()
    keep = []
    for line in (REAL_LOG / log.ENTRIES_FILENAME).read_text().splitlines():
        if json.loads(line).get("hypothesis_id") == log.SCHEMA_V3_MIGRATION_ID:
            break
        keep.append(line)
    (d / log.ENTRIES_FILENAME).write_text("\n".join(keep) + "\n")
    return d


@pytest.fixture
def v3(pre_v3):
    log.migrate_schema_v3(log_dir=pre_v3)
    return pre_v3


def _register(d, hid, **kw):
    return log.register_hypothesis(hid, f"title {hid}", "mechanism",
                                   log_dir=d, **{**V2, **kw})


def test_the_marker_is_additive(pre_v3):
    before_hashes = [json.loads(l)["entry_hash"] for l in
                     (pre_v3 / log.ENTRIES_FILENAME).read_text().splitlines()]
    n = log.trial_count(log_dir=pre_v3)
    log.migrate_schema_v3(log_dir=pre_v3)
    ok, msg = log.verify(log_dir=pre_v3)
    assert ok, msg
    assert log.trial_count(log_dir=pre_v3) == n
    after = [e.entry_hash for e in log._read_all(pre_v3)]
    assert after[:len(before_hashes)] == before_hashes
    assert log.schema_v3_migrated(log_dir=pre_v3)


def test_an_entry_without_v3_fields_stores_none_of_them(pre_v3):
    e = _register(pre_v3, "h_before")
    stored = json.loads((pre_v3 / log.ENTRIES_FILENAME).read_text()
                        .splitlines()[-1])
    assert e.counterparty is None
    assert not set(log.SCHEMA_V3_FIELDS) & set(stored)


def test_after_the_marker_every_field_is_required(v3):
    with pytest.raises(SchemaFieldsRequired) as exc:
        _register(v3, "h_bare")
    for name in log.SCHEMA_V3_FIELDS:
        assert name in str(exc.value)
    partial = {k: v for k, v in V3.items() if k != "prior_survival"}
    with pytest.raises(SchemaFieldsRequired, match="prior_survival"):
        _register(v3, "h_partial", **partial)


def test_a_full_registration_round_trips_and_verifies(v3):
    _register(v3, "h_full", **V3)
    got = [e for e in log._read_all(v3) if e.hypothesis_id == "h_full"][0]
    for k, v in V3.items():
        assert getattr(got, k) == v, k
    ok, msg = log.verify(log_dir=v3)
    assert ok, msg
    assert "_Prior that it survives_: 0.1" in log.render_markdown(log_dir=v3)


@pytest.mark.parametrize("prior", [0.0, 1.0, 1.2, -0.1])
def test_a_certainty_is_not_a_prior(v3, prior):
    with pytest.raises(ValueError, match="strictly in"):
        _register(v3, "h_prior", **{**V3, "prior_survival": prior})


def test_a_field_must_be_a_sentence_even_before_the_marker(pre_v3):
    with pytest.raises(ValueError, match="counterparty"):
        _register(pre_v3, "h_short", counterparty="retail")


def test_the_marker_is_appended_once_and_after_v2(v3, fresh_dir):
    with pytest.raises(ValueError, match="already present"):
        log.migrate_schema_v3(log_dir=v3)
    with pytest.raises(ValueError, match="v2 marker first"):
        log.migrate_schema_v3(log_dir=fresh_dir)


def test_prior_calibration_scores_resolved_verdicts_only(v3):
    for hid, prior in (("h_kill", 0.2), ("h_win", 0.6), ("h_open", 0.3)):
        _register(v3, hid, **{**V3, "prior_survival": prior})
    log.update_hypothesis("h_kill", stage=Stage.HYPOTHESIS,
                          verdict=Verdict.KILLED, log_dir=v3)
    log.update_hypothesis("h_win", stage=Stage.HYPOTHESIS,
                          verdict=Verdict.PROMOTED, log_dir=v3)
    cal = log.prior_calibration(log_dir=v3)
    assert cal["n_with_prior"] == 3
    assert cal["n_resolved"] == 2
    assert cal["mean_prior"] == 0.4
    assert cal["survival_rate"] == 0.5
    # (0.2 - 0)^2 and (0.6 - 1)^2, averaged.
    assert cal["brier"] == 0.1


def test_entries_before_the_marker_are_not_scored(pre_v3):
    """No earlier registration carries a prior, so none is calibrated."""
    assert log.prior_calibration(log_dir=pre_v3) == {
        "n_with_prior": 0, "n_resolved": 0}


@pytest.fixture
def fresh_dir(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    return d
