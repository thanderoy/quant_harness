"""Tests for research.log — the JSONL hash-chained research log."""

from __future__ import annotations

import json

import pytest

from research.log import (
    RECORD_EVENT_TYPES,
    EdgeGateRole,
    EventType,
    Stage,
    Verdict,
    append_record,
    current_state,
    history,
    register_hypothesis,
    render_markdown,
    trial_count,
    update_hypothesis,
    verify,
    ENTRIES_FILENAME,
    RENDERED_FILENAME,
)

#: Acceptance coverage (docs/REWRITE.md §7). Read by
#: tests/test_x_coverage.py — keep in step with what this file asserts.
pytestmark = [pytest.mark.x("X10"), pytest.mark.x("X21")]



def test_register_and_read_back(tmp_path):
    register_hypothesis(
        "h1", title="Test idea", mechanism="Because reasons.",
        market="XAUUSD", timeframe="M5", family="breakout",
        edge_gate_role=EdgeGateRole.HARD_GATE, log_dir=tmp_path,
    )
    hist = history("h1", log_dir=tmp_path)
    assert len(hist) == 1
    e = hist[0]
    assert e.seq == 0
    assert e.prev_hash == ""
    assert e.title == "Test idea"
    assert e.mechanism == "Because reasons."
    assert e.market == "XAUUSD"
    assert e.edge_gate_role is EdgeGateRole.HARD_GATE
    assert e.event_type is EventType.HYPOTHESIS
    assert e.counts_as_trial is True


def test_update_carries_forward(tmp_path):
    register_hypothesis(
        "h1", title="MR idea", mechanism="Liquidity vacuum.",
        family="mean_reversion", edge_gate_role=EdgeGateRole.DIAGNOSTIC,
        log_dir=tmp_path,
    )
    update_hypothesis("h1", stage=Stage.SIGNAL_EDGE, log_dir=tmp_path)

    state = current_state(log_dir=tmp_path)
    assert "h1" in state
    s = state["h1"]
    # New stage took effect
    assert s.stage is Stage.SIGNAL_EDGE
    # Identity fields carried forward from HYPOTHESIS
    assert s.title == "MR idea"
    assert s.mechanism == "Liquidity vacuum."
    assert s.family == "mean_reversion"
    assert s.edge_gate_role is EdgeGateRole.DIAGNOSTIC


def test_trial_counting(tmp_path):
    for hid in ("h1", "h2", "h3"):
        register_hypothesis(hid, title=hid, mechanism="m", log_dir=tmp_path)
    # Two ordinary updates — should NOT add to trial count
    update_hypothesis("h1", stage=Stage.SIGNAL_EDGE, log_dir=tmp_path)
    update_hypothesis("h2", verdict=Verdict.KILLED, log_dir=tmp_path)
    # One re-test update — explicit counts_as_trial=True
    update_hypothesis(
        "h3", stage=Stage.SIGNAL_EDGE, counts_as_trial=True,
        note="re-tested with new signal threshold", log_dir=tmp_path,
    )
    assert trial_count(log_dir=tmp_path) == 4


def test_duplicate_registration_rejected(tmp_path):
    register_hypothesis("h1", title="t", mechanism="m", log_dir=tmp_path)
    with pytest.raises(ValueError, match="already registered"):
        register_hypothesis("h1", title="t2", mechanism="m2", log_dir=tmp_path)


def test_update_without_hypothesis_rejected(tmp_path):
    with pytest.raises(ValueError, match="no HYPOTHESIS event"):
        update_hypothesis("ghost", stage=Stage.SIGNAL_EDGE, log_dir=tmp_path)


def test_hash_chain_verifies(tmp_path):
    register_hypothesis("h1", title="t", mechanism="m", log_dir=tmp_path)
    register_hypothesis("h2", title="t", mechanism="m", log_dir=tmp_path)
    update_hypothesis("h1", stage=Stage.SIGNAL_EDGE, log_dir=tmp_path)
    update_hypothesis("h2", verdict=Verdict.KILLED, log_dir=tmp_path)

    ok, msg = verify(log_dir=tmp_path)
    assert ok, msg
    assert "4 entries" in msg


def test_tamper_detection(tmp_path):
    for hid in ("h1", "h2", "h3"):
        register_hypothesis(hid, title=hid, mechanism="m", log_dir=tmp_path)
    update_hypothesis("h2", note="original", log_dir=tmp_path)

    path = tmp_path / ENTRIES_FILENAME
    lines = path.read_text().splitlines()
    # Corrupt entry at index 1: change a content field
    payload = json.loads(lines[1])
    payload["note"] = "tampered text — adversary edit"
    lines[1] = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n")

    ok, msg = verify(log_dir=tmp_path)
    assert not ok
    assert "seq=1" in msg


def test_reorder_detection(tmp_path):
    for hid in ("h1", "h2", "h3"):
        register_hypothesis(hid, title=hid, mechanism="m", log_dir=tmp_path)

    path = tmp_path / ENTRIES_FILENAME
    lines = path.read_text().splitlines()
    lines[1], lines[2] = lines[2], lines[1]
    path.write_text("\n".join(lines) + "\n")

    ok, msg = verify(log_dir=tmp_path)
    assert not ok


def test_markdown_renders_and_is_pure(tmp_path):
    register_hypothesis(
        "alpha", title="Alpha idea", mechanism="m",
        edge_gate_role=EdgeGateRole.HARD_GATE, log_dir=tmp_path,
    )
    register_hypothesis(
        "beta", title="Beta idea", mechanism="m",
        edge_gate_role=EdgeGateRole.DIAGNOSTIC, log_dir=tmp_path,
    )

    jsonl_before = (tmp_path / ENTRIES_FILENAME).read_text()
    text = render_markdown(log_dir=tmp_path)
    jsonl_after = (tmp_path / ENTRIES_FILENAME).read_text()

    assert "Alpha idea" in text
    assert "Beta idea" in text
    assert "Principles" in text
    assert "hard_gate" in text
    assert "diagnostic" in text
    assert (tmp_path / RENDERED_FILENAME).read_text() == text
    # Rendering must not touch the source of truth.
    assert jsonl_before == jsonl_after


def test_enum_round_trip(tmp_path):
    register_hypothesis(
        "h1", title="t", mechanism="m", family="breakout",
        edge_gate_role=EdgeGateRole.HARD_GATE, log_dir=tmp_path,
    )
    update_hypothesis(
        "h1", stage=Stage.OOS, verdict=Verdict.PROMOTED,
        edge_gate_role=EdgeGateRole.DIAGNOSTIC, log_dir=tmp_path,
    )

    hist = history("h1", log_dir=tmp_path)
    assert hist[0].edge_gate_role is EdgeGateRole.HARD_GATE
    assert hist[0].event_type is EventType.HYPOTHESIS
    assert hist[1].event_type is EventType.UPDATE
    assert hist[1].stage is Stage.OOS
    assert hist[1].verdict is Verdict.PROMOTED
    assert hist[1].edge_gate_role is EdgeGateRole.DIAGNOSTIC


# --------------------------------------------------------------------------- #
# Record events (T6)                                                           #
# --------------------------------------------------------------------------- #
def test_append_record_does_not_count_as_trial(tmp_path):
    """A record event must never move the DSR haircut denominator."""
    register_hypothesis("h1", title="h1", mechanism="m", log_dir=tmp_path)
    before = trial_count(log_dir=tmp_path)

    for et in RECORD_EVENT_TYPES:
        append_record(
            et, record_id=f"record:{et.value}", title=et.value,
            log_dir=tmp_path,
        )

    assert trial_count(log_dir=tmp_path) == before
    ok, msg = verify(log_dir=tmp_path)
    assert ok, msg


def test_append_record_rejects_research_event_types(tmp_path):
    """HYPOTHESIS/UPDATE have their own entry points and trial semantics."""
    for et in (EventType.HYPOTHESIS, EventType.UPDATE):
        with pytest.raises(ValueError, match="not a record event type"):
            append_record(et, record_id="r", title="t", log_dir=tmp_path)


def test_append_record_needs_no_prior_hypothesis(tmp_path):
    """A migration is not about a hypothesis, so it must not require one."""
    entry = append_record(
        EventType.REPO_MIGRATION, record_id="record:move", title="moved",
        log_dir=tmp_path,
    )
    assert entry.seq == 0
    assert entry.counts_as_trial is False
    ok, _ = verify(log_dir=tmp_path)
    assert ok


def test_record_events_absent_from_hypothesis_state(tmp_path):
    """current_state() is a view of hypotheses, not of the log's own history."""
    register_hypothesis("h1", title="h1", mechanism="m", log_dir=tmp_path)
    append_record(
        EventType.AUDIT, record_id="record:baseline", title="baseline",
        log_dir=tmp_path,
    )
    assert set(current_state(log_dir=tmp_path)) == {"h1"}
