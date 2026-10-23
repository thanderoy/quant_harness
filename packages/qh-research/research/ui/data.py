"""research.ui.data — read-only views of the research log, STATUS and artifacts.

Everything here reads; nothing writes. Each function returns plain JSON-able
data so the server is a thin router and the views can be tested on their own.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

from research import log as research_log

RESEARCH_DIR = Path(__file__).resolve().parents[1]
ARTIFACTS_DIR = RESEARCH_DIR / "pre" / "artifacts"
STATUS_MD = RESEARCH_DIR.parents[2] / "docs" / "STATUS.md"

#: A ``metrics`` key on a later record that withdraws earlier readings.
SUPERSEDES_KEYS = ("supersedes_reading_of", "supersedes_seq")
ARTIFACT_NAME = re.compile(r"^[A-Za-z0-9_.-]+\.json$")


def _entries(log_dir: Path) -> list[research_log.LogEntry]:
    return research_log._read_all(log_dir)


def _payload(e: research_log.LogEntry) -> dict:
    return json.loads(json.dumps(research_log._entry_to_payload(e), default=str))


def _withdrawn(entries: list[research_log.LogEntry]) -> dict[int, int]:
    """seq of a withdrawn entry -> seq of the record that withdrew it."""
    out: dict[int, int] = {}
    for e in entries:
        for key in SUPERSEDES_KEYS:
            ref = (e.metrics or {}).get(key)
            for s in (ref if isinstance(ref, list) else [ref]):
                if isinstance(s, int):
                    out[s] = e.seq
    return out


def _label(e: research_log.LogEntry) -> str:
    """The most specific verdict an entry states: its own label, else the enum."""
    v = (e.metrics or {}).get("verdict")
    return v.upper() if isinstance(v, str) and v else e.verdict.value.upper()


def summary(log_dir: Path = research_log.DEFAULT_LOG_DIR) -> dict:
    entries = _entries(log_dir)
    ok, msg = research_log.verify(log_dir)
    by_type: dict[str, int] = {}
    for e in entries:
        by_type[e.event_type.value] = by_type.get(e.event_type.value, 0) + 1
    last = entries[-1] if entries else None
    return {"chain_ok": ok, "chain_message": msg, "n_entries": len(entries),
            "trial_count": research_log.trial_count(log_dir),
            "by_event_type": by_type,
            "last_seq": last.seq if last else None,
            "last_timestamp": last.timestamp if last else None,
            "last_hash": last.entry_hash if last else None}


def hypotheses(log_dir: Path = research_log.DEFAULT_LOG_DIR) -> list[dict]:
    """One row per registered hypothesis, newest registration first."""
    entries = _entries(log_dir)
    withdrawn = _withdrawn(entries)
    regs = [e for e in entries
            if e.event_type == research_log.EventType.HYPOTHESIS]
    rows = []
    for reg in regs:
        hist = [e for e in entries if e.hypothesis_id == reg.hypothesis_id]
        latest = hist[-1]
        label = _label(latest) if latest is not reg else "REGISTERED"
        withdrawn_by = withdrawn.get(latest.seq)
        params = reg.parameters or {}
        stream = params.get("decisive_stream")
        streams = (latest.metrics or {}).get("streams") or {}
        rows.append({
            "hypothesis_id": reg.hypothesis_id, "title": reg.title,
            "family": reg.family, "market": reg.market,
            "timeframe": reg.timeframe, "registered_seq": reg.seq,
            "registered_at": reg.timestamp,
            "edge_gate_role": reg.edge_gate_role.value,
            "latest_seq": latest.seq, "latest_at": latest.timestamp,
            "stage": latest.stage.value, "verdict": latest.verdict.value,
            "label": "WITHDRAWN" if withdrawn_by else label,
            "withdrawn_by": withdrawn_by,
            "decisive_stream": stream,
            "decisive_threshold": params.get("decisive_threshold"),
            "decisive_value": streams.get(stream) if stream else None,
            "n_events": len(hist),
            "trials": sum(research_log._trials_for(e) for e in hist),
        })
    return sorted(rows, key=lambda r: r["registered_seq"], reverse=True)


def hypothesis(hypothesis_id: str,
               log_dir: Path = research_log.DEFAULT_LOG_DIR) -> Optional[dict]:
    entries = _entries(log_dir)
    hist = [e for e in entries if e.hypothesis_id == hypothesis_id]
    if not hist:
        return None
    withdrawn = _withdrawn(entries)
    events = []
    for e in hist:
        p = _payload(e)
        p["label"] = _label(e)
        p["withdrawn_by"] = withdrawn.get(e.seq)
        events.append(p)
    refs = {e["withdrawn_by"] for e in events if e["withdrawn_by"]}
    records = [_payload(e) for e in entries if e.seq in refs]
    return {"hypothesis_id": hypothesis_id, "events": events,
            "withdrawing_records": records}


def ledger(log_dir: Path = research_log.DEFAULT_LOG_DIR) -> list[dict]:
    """Every entry, lightly: what the hash chain holds, in order."""
    withdrawn = _withdrawn(_entries(log_dir))
    return [{"seq": e.seq, "timestamp": e.timestamp,
             "event_type": e.event_type.value,
             "hypothesis_id": e.hypothesis_id, "title": e.title,
             "label": _label(e), "counts_as_trial": e.counts_as_trial,
             "trials": research_log._trials_for(e),
             "withdrawn_by": withdrawn.get(e.seq),
             "note": e.note, "entry_hash": e.entry_hash,
             "prev_hash": e.prev_hash}
            for e in _entries(log_dir)]


def trial_timeline(log_dir: Path = research_log.DEFAULT_LOG_DIR) -> list[dict]:
    """Cumulative trial count at each entry that added trials."""
    total, out = 0, []
    for e in _entries(log_dir):
        n = research_log._trials_for(e)
        if n:
            total += n
            out.append({"seq": e.seq, "timestamp": e.timestamp,
                        "hypothesis_id": e.hypothesis_id, "added": n,
                        "total": total})
    return out


def _md_table(lines: list[str]) -> list[list[str]]:
    rows = []
    for ln in lines:
        if not ln.startswith("|") or re.match(r"^\|\s*-", ln):
            continue
        rows.append([c.strip() for c in ln.strip().strip("|").split("|")])
    return rows


def status(path: Path = STATUS_MD) -> dict:
    """The STATUS headline and phase table, as written (Markdown inline)."""
    if not path.exists():
        return {"available": False}
    text = path.read_text()
    head = next((ln for ln in text.splitlines()
                 if ln.startswith("**Last updated:**")), "")
    phases: list[list[str]] = []
    m = re.search(r"^## Phase progress\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if m:
        rows = _md_table(m.group(1).splitlines())
        phases = rows[1:] if rows else []
    return {"available": True, "headline": head.replace("**Last updated:**", "").strip(),
            "phases": [{"phase": r[0], "scope": r[1], "status": r[2]}
                       for r in phases if len(r) >= 3]}


def pending(today: Optional[date] = None,
            log_dir: Path = research_log.DEFAULT_LOG_DIR) -> list[dict]:
    """Registered tests that are waiting for data before their single look."""
    from research.pre import cot_oos
    today = today or datetime.now(timezone.utc).date()
    due = date.fromisoformat(cot_oos.EARLIEST_RUN)
    hist = research_log.history(cot_oos.HYPOTHESIS_ID, log_dir=log_dir)
    if not hist or len(hist) > 1:
        return []
    return [{"hypothesis_id": cot_oos.HYPOTHESIS_ID, "registered_seq": hist[0].seq,
             "title": hist[0].title, "earliest_run": cot_oos.EARLIEST_RUN,
             "days_remaining": max(0, (due - today).days),
             "min_intervals": cot_oos.OOS_MIN_INTERVALS,
             "in_sample_last_report": cot_oos.IN_SAMPLE_LAST_REPORT,
             "before_the_look": [
                 "Rebuild cot_positions.csv with build_cot.py (append only; run() checks the in-sample digest)",
                 "Save the 2027 CFTC release-schedule page while it is live",
                 "Re-dump the ten H1 files from the live terminal (GET-only)"]}]


def artifacts(directory: Path = ARTIFACTS_DIR) -> list[dict]:
    if not directory.exists():
        return []
    return sorted(({"name": p.name, "bytes": p.stat().st_size,
                    "modified": datetime.fromtimestamp(
                        p.stat().st_mtime, timezone.utc).isoformat(timespec="seconds")}
                   for p in directory.glob("*.json")),
                  key=lambda a: a["name"])


def artifact(name: str, directory: Path = ARTIFACTS_DIR) -> Optional[dict]:
    """One artifact's JSON, by bare file name only."""
    if not ARTIFACT_NAME.match(name):
        return None
    p = directory / name
    if p.resolve().parent != directory.resolve() or not p.is_file():
        return None
    return json.loads(p.read_text())
