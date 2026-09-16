"""T6 — the schema extension, and the two things it must not break.

The migration is additive, so the tests that matter are the ones that would
fail if it quietly stopped being additive: the chain must still verify across
the boundary, and the D7 baseline must not move. Everything else here is the
trial arithmetic, which is the whole point of the extension.
"""

from __future__ import annotations

import json

import pytest

from research import log
from research.log import (
    EventType,
    PerInstrumentTuningError,
    SchemaFieldsRequired,
    SelectionRule,
    Stage,
)

REAL_LOG = log.DEFAULT_LOG_DIR


@pytest.fixture
def live(tmp_path):
    """The real log as it stood immediately BEFORE the v2 marker.

    A plain copy would couple these tests to whether the real log has been
    migrated yet -- they passed before the migration ran and failed the
    moment it did. Truncating at the marker gives a genuine v1 chain to test
    the boundary against, whatever state the real log is in. The real log is
    never written to either way.
    """
    d = tmp_path / "log"
    d.mkdir()
    lines = (REAL_LOG / log.ENTRIES_FILENAME).read_text().splitlines()
    keep = []
    for line in lines:
        if json.loads(line).get("hypothesis_id") == log.SCHEMA_MIGRATION_ID:
            break
        keep.append(line)
    assert keep, "no pre-marker entries to test the boundary against"
    (d / log.ENTRIES_FILENAME).write_text("\n".join(keep) + "\n")
    return d


@pytest.fixture
def fresh(tmp_path):
    d = tmp_path / "empty"
    d.mkdir()
    return d


# -- the two invariants ----------------------------------------------------


def test_the_real_log_still_verifies_under_the_new_schema():
    """verify() rehashes from the dataclass, so a new always-serialised field
    would have broken all 93 entries at once."""
    ok, msg = log.verify(REAL_LOG)
    assert ok, msg


def test_the_real_log_trial_count_is_unchanged():
    assert log.trial_count(REAL_LOG) == 26


def test_verify_passes_across_the_migration_boundary(live):
    before = log.trial_count(live)
    log.migrate_schema(log_dir=live)
    ok, msg = log.verify(live)
    assert ok, msg
    assert log.trial_count(live) == before


def test_migration_does_not_rewrite_prior_entries(live):
    original = (live / log.ENTRIES_FILENAME).read_text().splitlines()
    log.migrate_schema(log_dir=live)
    after = (live / log.ENTRIES_FILENAME).read_text().splitlines()
    assert after[:len(original)] == original
    assert len(after) == len(original) + 1


def test_a_v1_entry_carries_no_v2_keys_on_disk(live):
    """Unset fields are omitted, which is what preserves the hashes."""
    first = json.loads((live / log.ENTRIES_FILENAME).read_text().splitlines()[0])
    for key in log.SCHEMA_V2_FIELDS:
        assert key not in first


def test_the_marker_records_the_terminal_hash_and_the_reading(live):
    entries = log._read_all(live)
    terminal = entries[-1].entry_hash
    m = log.migrate_schema(log_dir=live)
    assert m.event_type == EventType.SCHEMA_MIGRATION
    assert m.metrics["terminal_hash_before_migration"] == terminal
    assert m.metrics["prior_entries_rewritten"] is False
    assert m.metrics["prior_entries_read_as"] == {
        "universe": ["XAUUSD"], "selection_rule": "pooled_all"}
    assert m.counts_as_trial is False


def test_migrating_twice_is_refused(live):
    log.migrate_schema(log_dir=live)
    with pytest.raises(ValueError, match="already present"):
        log.migrate_schema(log_dir=live)


# -- trial arithmetic ------------------------------------------------------


def _register(d, hid, **kw):
    base = dict(
        title="t", mechanism="m",
        universe=["EURUSD", "GBPUSD", "USDJPY"],
        selection_rule=SelectionRule.POOLED_ALL,
        null_baseline_structure="regime_filtered_random_entry",
        benchmark_sharpe=0.31, min_decidable_sharpe=0.48,
        registry_snapshot="pepperstone_live_20260906",
        log_dir=d,
    )
    base.update(kw)
    return log.register_hypothesis(hid, **base)


def test_pooled_all_costs_one_trial(fresh):
    log.migrate_schema(log_dir=fresh)
    _register(fresh, "h1")
    assert log.trial_count(fresh) == 1


def test_pre_specified_subset_costs_one_trial(fresh):
    log.migrate_schema(log_dir=fresh)
    _register(fresh, "h1", selection_rule=SelectionRule.PRE_SPECIFIED_SUBSET)
    assert log.trial_count(fresh) == 1


def test_post_hoc_selection_costs_one_trial_per_instrument(fresh):
    log.migrate_schema(log_dir=fresh)
    _register(fresh, "h1", selection_rule=SelectionRule.POST_HOC_SELECTION)
    assert log.trial_count(fresh) == 3


def test_trial_count_is_not_a_row_count(fresh):
    log.migrate_schema(log_dir=fresh)
    _register(fresh, "pooled")
    _register(fresh, "posthoc", selection_rule=SelectionRule.POST_HOC_SELECTION,
              universe=["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD"])
    rows = sum(1 for e in log._read_all(fresh) if e.counts_as_trial)
    assert rows == 2
    assert log.trial_count(fresh) == 6


def test_breakdown_attributes_a_jump_in_n(fresh):
    log.migrate_schema(log_dir=fresh)
    _register(fresh, "pooled")
    _register(fresh, "posthoc", selection_rule=SelectionRule.POST_HOC_SELECTION)
    b = log.trial_breakdown(fresh)
    assert b["total"] == 4
    assert b["by_rule"] == {"pooled_all": 1, "post_hoc_selection": 3}
    assert b["entries"][0]["hypothesis_id"] == "posthoc"


def test_a_v1_entry_keeps_one_row_one_trial(live):
    """What holds the D7 baseline fixed across the boundary."""
    entries = log._read_all(live)
    v1 = [e for e in entries if e.counts_as_trial]
    assert all(e.selection_rule is None for e in v1)
    assert log.trial_count(live) == len(v1)


# -- enforcement -----------------------------------------------------------


def test_v2_fields_are_required_after_the_marker(fresh):
    log.migrate_schema(log_dir=fresh)
    with pytest.raises(SchemaFieldsRequired, match="selection_rule"):
        log.register_hypothesis(
            "h1", title="t", mechanism="m",
            universe=["EURUSD"], log_dir=fresh)


def test_the_error_names_every_missing_field(fresh):
    log.migrate_schema(log_dir=fresh)
    with pytest.raises(SchemaFieldsRequired) as ei:
        log.register_hypothesis("h1", title="t", mechanism="m", log_dir=fresh)
    for f in log.SCHEMA_V2_FIELDS:
        assert f in str(ei.value)


def test_v2_fields_are_optional_before_the_marker(fresh):
    e = log.register_hypothesis("h1", title="t", mechanism="m", log_dir=fresh)
    assert e.selection_rule is None
    assert log.trial_count(fresh) == 1


def test_per_instrument_parameters_are_refused(fresh):
    log.migrate_schema(log_dir=fresh)
    with pytest.raises(PerInstrumentTuningError, match="keyed by instrument"):
        _register(fresh, "h1",
                  parameters={"EURUSD": {"n": 20}, "GBPUSD": {"n": 55}})


def test_one_parameter_set_for_the_whole_universe_is_accepted(fresh):
    log.migrate_schema(log_dir=fresh)
    e = _register(fresh, "h1", parameters={"n": 20, "atr_mult": 1.5})
    assert e.parameters == {"n": 20, "atr_mult": 1.5}


def test_a_single_instrument_universe_is_not_per_instrument_tuning(fresh):
    """One instrument cannot be a selection among instruments."""
    log.migrate_schema(log_dir=fresh)
    e = _register(fresh, "h1", universe=["XAUUSD"],
                  parameters={"XAUUSD": {"n": 20}})
    assert e.universe == ["XAUUSD"]


def test_the_refusal_survives_a_round_trip(fresh):
    log.migrate_schema(log_dir=fresh)
    _register(fresh, "h1", selection_rule=SelectionRule.POST_HOC_SELECTION)
    reread = log._read_all(fresh)[-1]
    assert reread.selection_rule is SelectionRule.POST_HOC_SELECTION
    assert reread.universe == ["EURUSD", "GBPUSD", "USDJPY"]
    ok, msg = log.verify(fresh)
    assert ok, msg


def test_updates_still_default_to_not_counting(fresh):
    log.migrate_schema(log_dir=fresh)
    _register(fresh, "h1")
    log.update_hypothesis("h1", stage=Stage.SIGNAL_EDGE, log_dir=fresh)
    assert log.trial_count(fresh) == 1


def test_render_markdown_survives_the_new_schema(live):
    log.migrate_schema(log_dir=live)
    text = log.render_markdown(live)
    assert "chain ok" in text
