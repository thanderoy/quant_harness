"""Append-only, tamper-evident research log.

The canonical store is ``research/log/entries.jsonl`` — one JSON object per
line, append-only, with a SHA-256 hash chain. Every entry carries the hash of
the previous entry; rewriting history breaks the chain and :func:`verify`
detects it.

This module exists for one structural reason: **to make the multiple-testing
tax honest.** Every hypothesis we test is one trial in a larger search.
:func:`trial_count` reports the floor N that feeds Deflated Sharpe Ratio
calculations. That count is only trustworthy if the log is append-only and
tamper-evident — hence the chain.

A secondary purpose is to carry forward hard-won principles so they resurface
automatically. The first such principle is the gate-vs-diagnostic rule, made
first-class via :class:`EdgeGateRole`: the E-Ratio is a **hard gate** for
breakout/continuation entries, a **diagnostic only** for pullback/mean-
reversion entries (the edge lives in the exit there — a flat entry E-Ratio is
expected and must NOT trigger a kill).

Design rules
------------
- JSONL is source of truth; ``log.md`` is a *rendered view*, regenerated on
  demand and never hand-edited.
- Stdlib only — no pandas, no numpy. Runs anywhere.
- UPDATE events do not edit prior events; they append new events that
  reference the same ``hypothesis_id``. :func:`current_state` merges them.
- ``counts_as_trial`` defaults to True for HYPOTHESIS, False for UPDATE.
  Setting it True on an UPDATE is the explicit signal "this is a materially
  different re-test, count it." Be generous: the floor is a floor.

Usage
-----
>>> from research.log import register_hypothesis, update_hypothesis, Stage, Verdict, EdgeGateRole
>>> register_hypothesis(
...     "asian_session_fade",
...     title="Asian-session ATR-channel fade",
...     mechanism="Liquidity vacuum 22:00-05:00 GMT lets price overshoot HLPeak channel; "
...               "MR back to channel midline once London opens.",
...     market="XAUUSD", timeframe="M5", family="mean_reversion",
...     edge_gate_role=EdgeGateRole.DIAGNOSTIC,
... )
>>> update_hypothesis(
...     "asian_session_fade", stage=Stage.SIGNAL_EDGE,
...     metrics={"e_ratio_w30": 0.97}, note="Entry E-Ratio flat as expected for MR.",
... )
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

__all__ = [
    "EventType", "Stage", "Verdict", "EdgeGateRole",
    "LogEntry", "PRINCIPLES",
    "register_hypothesis", "update_hypothesis",
    "trial_count", "history", "current_state",
    "verify", "render_markdown",
    "DEFAULT_LOG_DIR", "ENTRIES_FILENAME", "RENDERED_FILENAME",
]


DEFAULT_LOG_DIR: Path = Path(__file__).resolve().parent / "log"
ENTRIES_FILENAME: str = "entries.jsonl"
RENDERED_FILENAME: str = "log.md"


class EventType(str, Enum):
    """What kind of event a line records.

    Two families. ``HYPOTHESIS``/``UPDATE`` are *research* events, attached to
    a hypothesis and subject to trial accounting. The rest are *record* events
    (see ``RECORD_EVENT_TYPES``): facts about the log or the repository that
    governs it, appended via ``append_record()``. Record events never count as
    trials — recording that the schema changed is not a new hypothesis test.

    Record events exist so that structural changes live inside the chain they
    govern. A repository migration or a schema extension that is only visible
    in git history is exactly the kind of unrecorded change that already broke
    three logged artifact paths (the ``research/artifacts/`` ->
    ``research/{pre,post}/artifacts/`` move, made without an event).
    """

    # research events — attached to a hypothesis
    HYPOTHESIS = "hypothesis"
    UPDATE = "update"

    # record events — facts about the log or its repository
    AUDIT = "audit"                      # a verified baseline of the chain itself
    REPO_MIGRATION = "repo_migration"    # the log moved repository or path
    PROJECT_RENAME = "project_rename"    # module/import paths remapped
    SCHEMA_MIGRATION = "schema_migration"  # this enum, or LogEntry, changed
    PARITY_FIXTURE = "parity_fixture"    # a golden fixture pinned or reproduced


#: Event types that describe the log/repository rather than a hypothesis.
#: These are appended with :func:`append_record` and never count as trials.
RECORD_EVENT_TYPES: frozenset[EventType] = frozenset({
    EventType.AUDIT,
    EventType.REPO_MIGRATION,
    EventType.PROJECT_RENAME,
    EventType.SCHEMA_MIGRATION,
    EventType.PARITY_FIXTURE,
})


class Stage(str, Enum):
    HYPOTHESIS = "0_hypothesis"
    SIGNAL_EDGE = "1_signal_edge"
    POWER = "2_power"
    IS_BACKTEST = "3_is_backtest"
    OOS = "4_oos"
    WALK_FORWARD = "5_walk_forward"
    STRESS = "6_stress"
    PORTFOLIO = "7_portfolio"
    DEPLOYED = "8_deployed"


class Verdict(str, Enum):
    OPEN = "open"
    KILLED = "killed"
    SHELVED = "shelved"
    PROMOTED = "promoted"
    DEPLOYED = "deployed"


class EdgeGateRole(str, Enum):
    """How the E-Ratio signal-edge gate applies to this hypothesis."""
    HARD_GATE = "hard_gate"     # breakout/continuation: kill on flat E-Ratio
    DIAGNOSTIC = "diagnostic"   # pullback/MR: edge in exit; do NOT kill on flat E-Ratio
    UNSET = "unset"


PRINCIPLES: list[dict[str, str]] = [
    {
        "title": "E-Ratio: hard gate vs diagnostic",
        "body": (
            "The E-Ratio is a **hard gate** for breakout/continuation entries "
            "(the entry itself should do the work — kill on a flat E-Ratio). "
            "It is a **diagnostic only** for pullback/mean-reversion entries "
            "(the edge legitimately lives in the exit — a flat entry E-Ratio "
            "is expected and must NOT trigger a kill). Set `edge_gate_role` "
            "at registration time so this rule travels with the hypothesis."
        ),
    },
    {
        "title": "Log generously; the trial count is a floor",
        "body": (
            "`trial_count()` is the N that feeds Deflated Sharpe Ratio. It "
            "cannot capture ideas considered and discarded before logging, so "
            "the true multiple-testing burden is always ≥ this number. "
            "Register early, even for vague ideas — it's cheaper to log a "
            "trial than to under-haircut a future Sharpe."
        ),
    },
]


@dataclass
class LogEntry:
    # identity & chain
    seq: int
    timestamp: str
    prev_hash: str
    entry_hash: str

    # event
    event_type: EventType
    hypothesis_id: str

    # content
    title: str = ""
    mechanism: str = ""
    market: str = ""
    timeframe: str = ""
    family: str = ""
    edge_gate_role: EdgeGateRole = EdgeGateRole.UNSET
    predictions: list[str] = field(default_factory=list)

    # progress
    stage: Stage = Stage.HYPOTHESIS
    verdict: Verdict = Verdict.OPEN
    metrics: dict = field(default_factory=dict)
    note: str = ""

    # multiple-testing accounting
    counts_as_trial: bool = True


# ---------------------------------------------------------------------------
# Serialisation + hashing
# ---------------------------------------------------------------------------

_ENUM_FIELDS = {
    "event_type": EventType,
    "edge_gate_role": EdgeGateRole,
    "stage": Stage,
    "verdict": Verdict,
}


def _entry_to_payload(entry: LogEntry) -> dict:
    """Serialisable dict for storage — enums become their .value strings."""
    d = asdict(entry)
    for name in _ENUM_FIELDS:
        v = d[name]
        if isinstance(v, Enum):
            d[name] = v.value
    return d


def _payload_to_entry(payload: dict) -> LogEntry:
    p = dict(payload)
    for name, enum_cls in _ENUM_FIELDS.items():
        if name in p and not isinstance(p[name], Enum):
            p[name] = enum_cls(p[name])
    return LogEntry(**p)


def _canonical(payload: dict) -> str:
    """Canonical JSON for hashing — excludes entry_hash, sorts keys, no spaces."""
    without_hash = {k: v for k, v in payload.items() if k != "entry_hash"}
    return json.dumps(without_hash, sort_keys=True, separators=(",", ":"))


def _hash(payload: dict) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

def _entries_path(log_dir: Path) -> Path:
    return Path(log_dir) / ENTRIES_FILENAME


def _read_all(log_dir: Path) -> list[LogEntry]:
    path = _entries_path(log_dir)
    if not path.exists():
        return []
    entries: list[LogEntry] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entries.append(_payload_to_entry(json.loads(line)))
    return entries


def _append(log_dir: Path, entry: LogEntry) -> None:
    path = _entries_path(log_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(_entry_to_payload(entry), sort_keys=True,
                           separators=(",", ":")) + "\n")


def _next_seq_and_prev_hash(entries: list[LogEntry]) -> tuple[int, str]:
    if not entries:
        return 0, ""
    last = entries[-1]
    return last.seq + 1, last.entry_hash


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def register_hypothesis(
    hypothesis_id: str,
    title: str,
    mechanism: str,
    *,
    market: str = "",
    timeframe: str = "",
    family: str = "",
    edge_gate_role: EdgeGateRole = EdgeGateRole.UNSET,
    predictions: Optional[list[str]] = None,
    note: str = "",
    log_dir: Path = DEFAULT_LOG_DIR,
) -> LogEntry:
    """Append a new HYPOTHESIS event. Counts as a trial.

    Raises
    ------
    ValueError
        If ``hypothesis_id`` already has a HYPOTHESIS event in the log.
    """
    entries = _read_all(log_dir)
    if any(e.event_type == EventType.HYPOTHESIS and e.hypothesis_id == hypothesis_id
           for e in entries):
        raise ValueError(
            f"hypothesis_id {hypothesis_id!r} already registered; "
            f"use update_hypothesis() to record progress."
        )

    seq, prev_hash = _next_seq_and_prev_hash(entries)
    entry = LogEntry(
        seq=seq, timestamp=_now_iso(), prev_hash=prev_hash, entry_hash="",
        event_type=EventType.HYPOTHESIS, hypothesis_id=hypothesis_id,
        title=title, mechanism=mechanism, market=market, timeframe=timeframe,
        family=family, edge_gate_role=edge_gate_role,
        predictions=list(predictions) if predictions else [],
        stage=Stage.HYPOTHESIS, verdict=Verdict.OPEN, metrics={}, note=note,
        counts_as_trial=True,
    )
    entry.entry_hash = _hash(_entry_to_payload(entry))
    _append(log_dir, entry)
    return entry


def update_hypothesis(
    hypothesis_id: str,
    *,
    stage: Optional[Stage] = None,
    verdict: Optional[Verdict] = None,
    metrics: Optional[dict] = None,
    note: str = "",
    counts_as_trial: bool = False,
    edge_gate_role: Optional[EdgeGateRole] = None,
    log_dir: Path = DEFAULT_LOG_DIR,
) -> LogEntry:
    """Append an UPDATE event for an existing hypothesis.

    Set ``counts_as_trial=True`` only when this update represents a materially
    different parameterisation re-tested — that is genuinely a new trial.

    Raises
    ------
    ValueError
        If ``hypothesis_id`` has no prior HYPOTHESIS event.
    """
    entries = _read_all(log_dir)
    prior = [e for e in entries if e.hypothesis_id == hypothesis_id]
    if not any(e.event_type == EventType.HYPOTHESIS for e in prior):
        raise ValueError(
            f"hypothesis_id {hypothesis_id!r} has no HYPOTHESIS event; "
            f"call register_hypothesis() first."
        )

    seq, prev_hash = _next_seq_and_prev_hash(entries)
    last_state = _merge(prior)
    entry = LogEntry(
        seq=seq, timestamp=_now_iso(), prev_hash=prev_hash, entry_hash="",
        event_type=EventType.UPDATE, hypothesis_id=hypothesis_id,
        # carry identity fields forward so an UPDATE line is self-describing
        title=last_state.title, mechanism="", market="", timeframe="",
        family="",
        edge_gate_role=edge_gate_role if edge_gate_role is not None
                       else EdgeGateRole.UNSET,
        predictions=[],
        stage=stage if stage is not None else last_state.stage,
        verdict=verdict if verdict is not None else last_state.verdict,
        metrics=dict(metrics) if metrics else {},
        note=note, counts_as_trial=counts_as_trial,
    )
    entry.entry_hash = _hash(_entry_to_payload(entry))
    _append(log_dir, entry)
    return entry


def append_record(
    event_type: EventType,
    *,
    record_id: str,
    title: str,
    note: str = "",
    metrics: Optional[dict] = None,
    log_dir: Path = DEFAULT_LOG_DIR,
) -> LogEntry:
    """Append a record event — a fact about the log or the repo that holds it.

    Unlike :func:`update_hypothesis` this requires no prior HYPOTHESIS event,
    because a repository migration or a schema change is not about a
    hypothesis. ``record_id`` occupies the ``hypothesis_id`` slot so the line
    stays self-describing and the existing chain format is unchanged; use a
    namespaced value such as ``"record:phase0-d7-baseline"``.

    ``counts_as_trial`` is forced False and is not a parameter. Recording that
    the schema changed is not a new hypothesis test, and allowing it to be set
    would let structural bookkeeping inflate the DSR haircut denominator.

    Raises
    ------
    ValueError
        If ``event_type`` is not a record type — HYPOTHESIS and UPDATE have
        their own entry points and their own trial semantics.
    """
    if event_type not in RECORD_EVENT_TYPES:
        raise ValueError(
            f"{event_type.value!r} is not a record event type. "
            f"Use register_hypothesis() or update_hypothesis(). "
            f"Record types: {sorted(e.value for e in RECORD_EVENT_TYPES)}"
        )

    entries = _read_all(log_dir)
    seq, prev_hash = _next_seq_and_prev_hash(entries)
    entry = LogEntry(
        seq=seq, timestamp=_now_iso(), prev_hash=prev_hash, entry_hash="",
        event_type=event_type, hypothesis_id=record_id,
        title=title, mechanism="", market="", timeframe="", family="",
        edge_gate_role=EdgeGateRole.UNSET, predictions=[],
        stage=Stage.HYPOTHESIS, verdict=Verdict.OPEN,
        metrics=dict(metrics) if metrics else {},
        note=note,
        counts_as_trial=False,
    )
    entry.entry_hash = _hash(_entry_to_payload(entry))
    _append(log_dir, entry)
    return entry


def history(hypothesis_id: str, log_dir: Path = DEFAULT_LOG_DIR) -> list[LogEntry]:
    """All events for one hypothesis, in append order."""
    return [e for e in _read_all(log_dir) if e.hypothesis_id == hypothesis_id]


def trial_count(log_dir: Path = DEFAULT_LOG_DIR) -> int:
    """Sum of counts_as_trial across all entries — the floor N for DSR."""
    return sum(1 for e in _read_all(log_dir) if e.counts_as_trial)


def current_state(log_dir: Path = DEFAULT_LOG_DIR) -> dict[str, LogEntry]:
    """Latest merged state of every hypothesis."""
    by_id: dict[str, list[LogEntry]] = {}
    for e in _read_all(log_dir):
        if e.event_type in RECORD_EVENT_TYPES:
            continue  # record events describe the log, not a hypothesis
        by_id.setdefault(e.hypothesis_id, []).append(e)
    return {hid: _merge(events) for hid, events in by_id.items()}


def _merge(events: list[LogEntry]) -> LogEntry:
    """Fold a hypothesis's event stream into a single view.

    UPDATE events overwrite only the fields they explicitly set; everything
    else carries forward from the HYPOTHESIS event (and prior updates).
    Metrics are merged dict-style.
    """
    hypo = next((e for e in events if e.event_type == EventType.HYPOTHESIS), None)
    if hypo is None:
        # Shouldn't reach here in normal flow; return the last raw event.
        return events[-1]

    merged = LogEntry(
        seq=events[-1].seq, timestamp=events[-1].timestamp,
        prev_hash=events[-1].prev_hash, entry_hash=events[-1].entry_hash,
        event_type=events[-1].event_type, hypothesis_id=hypo.hypothesis_id,
        title=hypo.title, mechanism=hypo.mechanism, market=hypo.market,
        timeframe=hypo.timeframe, family=hypo.family,
        edge_gate_role=hypo.edge_gate_role, predictions=list(hypo.predictions),
        stage=hypo.stage, verdict=hypo.verdict, metrics=dict(hypo.metrics),
        note=hypo.note, counts_as_trial=hypo.counts_as_trial,
    )
    for e in events:
        if e.event_type == EventType.HYPOTHESIS:
            continue
        if e.stage != Stage.HYPOTHESIS or merged.stage == Stage.HYPOTHESIS:
            # UPDATE always sets stage explicitly (defaulted to current at append)
            merged.stage = e.stage
        merged.verdict = e.verdict
        if e.edge_gate_role != EdgeGateRole.UNSET:
            merged.edge_gate_role = e.edge_gate_role
        if e.metrics:
            merged.metrics.update(e.metrics)
        if e.note:
            merged.note = e.note
    return merged


def verify(log_dir: Path = DEFAULT_LOG_DIR) -> tuple[bool, str]:
    """Walk the hash chain. Detect tampering or reordering.

    Returns
    -------
    (ok, message)
        ``ok=True`` and a confirmation string if the chain is intact;
        ``ok=False`` and a description of the first break otherwise.
    """
    entries = _read_all(log_dir)
    if not entries:
        return True, "empty log"

    prev_hash = ""
    for i, e in enumerate(entries):
        if e.seq != i:
            return False, f"seq mismatch at index {i}: stored seq={e.seq}"
        if e.prev_hash != prev_hash:
            return False, (
                f"prev_hash mismatch at seq={e.seq} "
                f"(hypothesis_id={e.hypothesis_id!r}): chain broken"
            )
        recomputed = _hash(_entry_to_payload(e))
        if recomputed != e.entry_hash:
            return False, (
                f"entry_hash mismatch at seq={e.seq} "
                f"(hypothesis_id={e.hypothesis_id!r}): contents tampered"
            )
        prev_hash = e.entry_hash
    return True, f"chain ok ({len(entries)} entries)"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def render_markdown(log_dir: Path = DEFAULT_LOG_DIR) -> str:
    """Generate ``log.md`` from the JSONL. Returns the text and writes the file.

    Never the source of truth; always regenerated.
    """
    entries = _read_all(log_dir)
    state = current_state(log_dir)
    ok, msg = verify(log_dir)

    lines: list[str] = []
    lines.append("# Research Log (rendered view)")
    lines.append("")
    lines.append(
        "> **Generated artifact** — do not edit. Source: `entries.jsonl`. "
        "Regenerate with `render_markdown()`."
    )
    lines.append("")
    lines.append(f"- **Entries:** {len(entries)}")
    lines.append(f"- **Trial count (floor N for DSR):** {trial_count(log_dir)}")
    lines.append(f"- **Hash chain:** {'OK' if ok else 'BROKEN'} — {msg}")
    lines.append("")

    lines.append("## Principles")
    lines.append("")
    for i, p in enumerate(PRINCIPLES, 1):
        lines.append(f"**{i}. {p['title']}** — {p['body']}")
        lines.append("")

    lines.append("## Current state by hypothesis")
    lines.append("")
    lines.append(
        "Edge-gate role is shown on every row: a **hard_gate** entry must "
        "show E-Ratio edge; a **diagnostic** entry may legitimately have a "
        "flat E-Ratio (edge lives in the exit) and must not be killed on it."
    )
    lines.append("")
    lines.append(
        "| hypothesis | family | role | stage | verdict | latest metrics |"
    )
    lines.append("|---|---|---|---|---|---|")
    for hid in sorted(state):
        s = state[hid]
        metrics_str = (
            ", ".join(f"{k}={v}" for k, v in s.metrics.items())
            if s.metrics else "—"
        )
        lines.append(
            f"| `{hid}` — {s.title} | {s.family or '—'} | "
            f"{s.edge_gate_role.value} | {s.stage.value} | {s.verdict.value} "
            f"| {metrics_str} |"
        )
    lines.append("")

    lines.append("## Full event stream (oldest first)")
    lines.append("")
    for e in entries:
        lines.append(
            f"### seq {e.seq} · {e.timestamp} · {e.event_type.value} · "
            f"`{e.hypothesis_id}`"
        )
        lines.append("")
        if e.event_type == EventType.HYPOTHESIS:
            lines.append(f"**{e.title}**")
            lines.append("")
            if e.mechanism:
                lines.append(f"_Mechanism_: {e.mechanism}")
                lines.append("")
            meta = []
            if e.market: meta.append(f"market={e.market}")
            if e.timeframe: meta.append(f"timeframe={e.timeframe}")
            if e.family: meta.append(f"family={e.family}")
            meta.append(f"edge_gate_role={e.edge_gate_role.value}")
            meta.append(f"counts_as_trial={e.counts_as_trial}")
            lines.append("· ".join(meta))
            lines.append("")
            if e.predictions:
                lines.append("_Predictions_:")
                for p in e.predictions:
                    lines.append(f"- {p}")
                lines.append("")
        else:
            lines.append(
                f"stage={e.stage.value} · verdict={e.verdict.value} · "
                f"counts_as_trial={e.counts_as_trial}"
            )
            lines.append("")
            if e.metrics:
                lines.append("_Metrics_: " +
                             ", ".join(f"`{k}`={v}" for k, v in e.metrics.items()))
                lines.append("")
        if e.note:
            lines.append(f"> {e.note}")
            lines.append("")
        lines.append(f"_hash_: `{e.entry_hash[:16]}…` · _prev_: "
                     f"`{e.prev_hash[:16] + '…' if e.prev_hash else '(genesis)'}`")
        lines.append("")

    text = "\n".join(lines).rstrip() + "\n"
    out = Path(log_dir) / RENDERED_FILENAME
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return text
