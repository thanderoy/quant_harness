"""research.ui: the read-only views and the router, on a throwaway log."""

from __future__ import annotations

import json
from datetime import date
from http import HTTPStatus

import pytest

from research import log as research_log
from research.ui import data, server


@pytest.fixture
def log_dir(tmp_path):
    (tmp_path / "entries.jsonl").write_text("")
    research_log.register_hypothesis("h_a", "A", "m", family="f", log_dir=tmp_path)
    research_log.update_hypothesis(
        "h_a", stage=research_log.Stage.SIGNAL_EDGE,
        verdict=research_log.Verdict.OPEN,
        metrics={"verdict": "ALIVE", "streams": {"p": 0.01}}, log_dir=tmp_path)
    research_log.register_hypothesis("h_b", "B", "m", family="f", log_dir=tmp_path)
    research_log.update_hypothesis(
        "h_b", verdict=research_log.Verdict.KILLED,
        metrics={"verdict": "DEAD"}, log_dir=tmp_path)
    research_log.append_record(
        research_log.EventType.AUDIT, record_id="record:withdraw-a",
        title="withdraw", metrics={"supersedes_reading_of": [1]}, log_dir=tmp_path)
    research_log.register_hypothesis("h_c", "C", "m", log_dir=tmp_path)
    return tmp_path


def test_summary_reports_the_chain_and_the_trial_count(log_dir):
    s = data.summary(log_dir)
    assert s["chain_ok"] and s["n_entries"] == 6
    assert s["trial_count"] == research_log.trial_count(log_dir) == 3


def test_a_withdrawn_reading_is_shown_as_withdrawn(log_dir):
    rows = {r["hypothesis_id"]: r for r in data.hypotheses(log_dir)}
    assert rows["h_a"]["label"] == "WITHDRAWN" and rows["h_a"]["withdrawn_by"] == 4
    assert rows["h_b"]["label"] == "DEAD"
    assert rows["h_c"]["label"] == "REGISTERED"


def test_hypotheses_are_newest_first(log_dir):
    assert [r["hypothesis_id"] for r in data.hypotheses(log_dir)] == ["h_c", "h_b", "h_a"]


def test_detail_carries_the_withdrawing_record(log_dir):
    d = data.hypothesis("h_a", log_dir)
    assert [e["seq"] for e in d["events"]] == [0, 1]
    assert d["events"][1]["withdrawn_by"] == 4
    assert [r["seq"] for r in d["withdrawing_records"]] == [4]
    assert data.hypothesis("missing", log_dir) is None


def test_trial_timeline_ends_at_trial_count(log_dir):
    tl = data.trial_timeline(log_dir)
    assert tl[-1]["total"] == research_log.trial_count(log_dir)


def test_trial_timeline_matches_the_real_log():
    assert data.trial_timeline()[-1]["total"] == research_log.trial_count()


def test_ledger_lists_every_entry_in_order(log_dir):
    led = data.ledger(log_dir)
    assert [e["seq"] for e in led] == list(range(6))
    assert led[1]["withdrawn_by"] == 4


def test_status_reads_the_phase_table():
    st = data.status()
    assert st["available"] and st["headline"]
    assert {p["phase"] for p in st["phases"]} >= {"0", "1", "2"}
    assert st["invariants"] and all(i and not i[0].isdigit() for i in st["invariants"])


def test_numbered_joins_continuation_lines():
    text = "## Rules\n\nIntro.\n\n1. **One** first\n   continued.\n2. Two.\n\n---\n3. not this\n"
    assert data._numbered(text, "Rules") == ["**One** first continued.", "Two."]
    assert data._numbered(text, "Missing") == []


def test_pending_counts_down_to_the_cot_look():
    p = data.pending(today=date(2027, 10, 8))
    assert p and p[0]["days_remaining"] == 10


def test_artifact_refuses_anything_but_a_bare_name(tmp_path):
    (tmp_path / "ok.json").write_text(json.dumps({"a": 1}))
    assert data.artifact("ok.json", tmp_path) == {"a": 1}
    for bad in ("../ok.json", "..%2Fok.json", "/etc/passwd", "ok.txt", ""):
        assert data.artifact(bad, tmp_path) is None


def test_router(monkeypatch, log_dir):
    monkeypatch.setitem(server.ROUTES, "/api/summary", lambda: data.summary(log_dir))
    assert server.resolve("/api/summary")[0] == HTTPStatus.OK
    assert server.resolve("/api/hypothesis/definitely-missing")[0] == HTTPStatus.NOT_FOUND
    assert server.resolve("/api/artifact/..%2F..%2Flog.py")[0] == HTTPStatus.NOT_FOUND
    assert server.resolve("/api/nope")[0] == HTTPStatus.NOT_FOUND


def test_static_files_exist():
    for name in server.STATIC_FILES.values():
        assert (server.STATIC_DIR / name).is_file()


def test_every_page_serves_the_shell():
    for page in server.PAGES:
        assert server.STATIC_FILES[page] == "index.html"


def test_trial_breakdown_totals_trial_count(log_dir):
    assert data.trial_breakdown(log_dir)["total"] == research_log.trial_count(log_dir)
