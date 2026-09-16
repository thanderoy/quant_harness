"""X16, X17, X18 — the `qhf` split, and what it was not allowed to touch.

A rename is the cheapest possible way to break a research record. Every
logged artifact path, every note describing what ran, every provenance key
is a string that a careless sweep will happily rewrite into something that
never existed. The chain would still verify — the hashes are over the
entries, not over whether the entries are true — and the damage would be
invisible until someone tried to resolve a path and could not.

So these tests check two opposite things at once:

- **X16:** nothing that names a module you would import today still says
  ``qhf``.
- and the inverse: everything that records what a *past* run used still says
  ``qhf``, exactly as written. :data:`HISTORICAL` is that list, and it is
  asserted to be non-empty and still accurate — a stale allowlist that has
  quietly stopped matching anything is how an exemption becomes a licence.

X17 is behaviour-neutrality and X18 is that the log survived.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

import pytest

pytestmark = [pytest.mark.x("X16"), pytest.mark.x("X17"), pytest.mark.x("X18")]

REPO = pathlib.Path(__file__).resolve().parents[1]
RESEARCH = REPO / "packages" / "qh-research" / "research"

sys.path.insert(0, str(REPO / "packages" / "qh-research"))

#: X16's own carve-outs, from docs/REWRITE.md §7: the log and the stored
#: artifacts are intentionally preserved, and so is git history.
EXCLUDED_TREES = (
    RESEARCH / "log",
    RESEARCH / "pre" / "artifacts",
    RESEARCH / "post" / "artifacts",
)

#: Documentation that records the project's own history, including the spec
#: that *defines* the rename. Rewriting these would falsify the record of what
#: was decided and why. X16 names code, config, Compose files and env-var
#: names — not prose about the past.
EXCLUDED_DOCS = {
    "docs/REWRITE.md",
    "docs/d9_migration_plan.md",
    "docs/STATUS.md",
    "packages/qh-research/research/audit_seed_metrics.md",
}

#: Source files that still contain `qhf` **on purpose**, with the reason.
#: Each is a string recording what a past run used, not a module anyone can
#: import. The registration notes are verbatim in the hash chain; rewriting
#: them would leave those scripts unable to reproduce the entries they wrote.
HISTORICAL: dict[str, str] = {
    "packages/qh-research/research/data_manifest.py":
        "GRANDFATHERED names a path at commit cb48e00",
    "packages/qh-research/research/post/sweeps/registration.py":
        "note text verbatim in the chain",
    "packages/qh-research/research/post/sweeps/cnk_registration.py":
        "note text verbatim in the chain",
    "packages/qh-research/research/post/sweeps/ebb_registration.py":
        "note text verbatim in the chain",
    "packages/qh-research/research/post/sweeps/asqs_registration.py":
        "note text verbatim in the chain",
    "packages/qh-research/research/post/sweeps/cnk_nested_registration.py":
        "narrative about the seq=46 run",
    "packages/qh-research/research/post/sweeps/build_report.py":
        "HTML report prose describing a completed run",
    "packages/qh-research/research/post/sweeps/build_asqs_report.py":
        "HTML report prose describing a completed run",
    "packages/qh-research/research/post/sweeps/cnk_narrative.py":
        "HTML report prose describing a completed run",
    "packages/qh-research/research/post/sweeps/cnk_nested_wf.py":
        "narrative about the seq=46 run",
}

#: The mapping the PROJECT_RENAME event records. Duplicated here so the test
#: fails if the event and the tree ever disagree.
EXPECTED_MODULES = (
    "research.metrics",
    "research.validation",
    "research.reports",
    "research.engines",
    "research.datasets",
)

#: Plain substring, not a word boundary: the old *repo* name `qhf_harness`
#: has an underscore, which `\b` treats as a word character and would miss
#: entirely. Broad on purpose — a false positive costs one allowlist line.
QHF = re.compile(r"qhf", re.IGNORECASE)


def _scanned_files() -> list[pathlib.Path]:
    """Code and config, excluding the trees X16 exempts."""
    # .md included even though X16 names only code and config: a README that
    # tells a reader to `from qhf.data import load_bars` is wrong in a way
    # that costs someone an afternoon, and it is the first thing they read.
    suffixes = {".py", ".toml", ".yml", ".yaml", ".cfg", ".ini", ".env", ".md"}
    out = []
    for path in REPO.rglob("*"):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        parts = path.parts
        if "__pycache__" in parts or ".venv" in parts or ".git" in parts:
            continue
        if any(str(path).startswith(str(t)) for t in EXCLUDED_TREES):
            continue
        if path == pathlib.Path(__file__).resolve():
            continue   # this file defines the check; it must name the string
        if str(path.relative_to(REPO)) in EXCLUDED_DOCS:
            continue
        out.append(path)
    return sorted(out)


# --------------------------------------------------------------------------- #
# X16                                                                          #
# --------------------------------------------------------------------------- #

@pytest.mark.x("X16")
def test_no_live_qhf_identifier_survives():
    """The rename is complete everywhere it is supposed to be."""
    offenders = []
    for path in _scanned_files():
        rel = str(path.relative_to(REPO))
        if rel in HISTORICAL:
            continue
        text = path.read_text(errors="ignore")
        for n, line in enumerate(text.splitlines(), 1):
            if QHF.search(line):
                offenders.append(f"{rel}:{n}: {line.strip()[:90]}")
    assert not offenders, (
        "live `qhf` references remain:\n  " + "\n  ".join(offenders))


@pytest.mark.x("X16")
def test_the_qhf_package_is_gone():
    assert not (REPO / "qhf").exists()
    for name in EXPECTED_MODULES:
        __import__(name)


@pytest.mark.x("X16")
def test_every_historical_exemption_is_still_accurate():
    """The anti-rot check, in both directions.

    An allowlist entry for a file that no longer contains the string is a
    licence nobody is checking — and the next sweep past it will take the
    exemption at face value. Same failure shape as a DEFERRED entry that
    quietly gained coverage.
    """
    assert HISTORICAL, "an empty allowlist would make the scan above vacuous"

    stale, missing = [], []
    for rel, reason in HISTORICAL.items():
        path = REPO / rel
        if not path.exists():
            missing.append(rel)
            continue
        if not QHF.search(path.read_text(errors="ignore")):
            stale.append(f"{rel} ({reason})")

    assert not missing, f"allowlisted files that no longer exist: {missing}"
    assert not stale, (
        "allowlisted as historical but no longer containing `qhf` — remove "
        f"the entry: {stale}")


@pytest.mark.x("X16")
def test_registration_notes_still_match_the_chain():
    """Why those files are exempt, asserted rather than asserted-in-a-comment.

    If a note string in a registration script no longer appears verbatim in
    the chain, then either the sweep rewrote it after all, or the script has
    drifted from the entry it produced. Both are worth failing over.
    """
    # Decoded, not raw: entries.jsonl escapes non-ASCII, so an em-dash in a
    # note is "\u2014" on disk and a raw substring search misses every line
    # containing one. That is a false negative on exactly the prose-heavy
    # notes this probe exists to check.
    entries = "\n".join(
        json.loads(line)["note"]
        for line in (RESEARCH / "log" / "entries.jsonl").read_text().splitlines()
        if line.strip())
    checked = 0
    for rel in HISTORICAL:
        if not rel.endswith("registration.py"):
            continue
        for line in (REPO / rel).read_text().splitlines():
            if not QHF.search(line):
                continue
            fragment = line.strip().strip('",').strip('"').strip()
            fragment = fragment.lstrip('"').rstrip('"')
            if len(fragment) < 25:      # too short to be a meaningful probe
                continue
            assert fragment in entries, (
                f"{rel}: this note text is not in the chain verbatim, so it "
                f"is not the historical fact its exemption claims:\n  "
                f"{fragment[:100]}")
            checked += 1
    assert checked >= 4, (
        f"only {checked} note strings probed; the exemption is barely tested")


# --------------------------------------------------------------------------- #
# X17                                                                          #
# --------------------------------------------------------------------------- #

@pytest.mark.x("X17")
def test_the_parity_fixture_still_reproduces():
    """Behaviour neutrality, in the form that survives the commit.

    X17 as written compares the rename commit against its parent, which is a
    one-time check; its result is recorded in the PROJECT_RENAME entry and
    asserted below. What stays testable afterwards is the fixture: the same
    signal set, through the moved modules, still matches the artifact
    adjudicated at seq=31.
    """
    from research.parity import t9a_flood_tide as t9a

    report = t9a.check_mask_off()
    failed = [layer for layer in report.layers if not layer.passed]
    assert not failed, f"parity layers failed after the move: {failed}"


@pytest.mark.x("X17")
def test_the_commit_comparison_was_actually_run():
    """The one-time check, recorded where it cannot be quietly forgotten.

    A claim of behaviour-neutrality that lives only in a PR description is
    worth nothing six months later. This asserts the evidence is in the
    chain.
    """
    from research import log

    entry = _rename_entry(log)
    assert entry["metrics"]["parity_t9a_identical"] == "yes"
    assert entry["metrics"]["tests_before"] == entry["metrics"]["tests_after"]


# --------------------------------------------------------------------------- #
# X18                                                                          #
# --------------------------------------------------------------------------- #

@pytest.mark.x("X18")
def test_the_log_survived_the_rename():
    from research import log

    ok, msg = log.verify()
    assert ok, msg
    assert log.trial_count() == 26, (
        "a namespace split must not move the DSR haircut denominator")


@pytest.mark.x("X18")
def test_the_rename_event_records_the_full_mapping():
    """A PROJECT_RENAME that does not carry the mapping is a note, not a
    resolution mechanism — which is exactly how three artifact paths became
    unresolvable before seq=85."""
    from research import log

    entry = _rename_entry(log)
    assert entry["counts_as_trial"] is False
    recorded = entry["metrics"]["namespaces_new"]
    for module in EXPECTED_MODULES:
        assert module in recorded, f"{module} missing from the mapping"
        assert module in entry["note"], f"{module} not in the note mapping"
    assert "qhf" in entry["note"], "the old namespace is not in the mapping"


@pytest.mark.x("X18")
def test_no_pre_existing_entry_was_rewritten():
    """The chain would verify just as happily over a falsified history, so
    the check is against git, not against the hashes."""
    proc = subprocess.run(
        ["git", "diff", "--numstat", "origin/develop", "--",
         "packages/qh-research/research/log/entries.jsonl"],
        cwd=REPO, capture_output=True, text=True)
    if proc.returncode != 0 or not proc.stdout.strip():
        pytest.skip("no origin/develop to compare against")
    added, removed, _ = proc.stdout.split()
    assert removed == "0", (
        f"{removed} lines were removed from the append-only log; a rename "
        "may only append")


def _rename_entry(log) -> dict:
    for line in (RESEARCH / "log" / "entries.jsonl").read_text().splitlines():
        entry = json.loads(line)
        if entry["hypothesis_id"] == "record:t10-qhf-package-split":
            return entry
    raise AssertionError("no PROJECT_RENAME entry for the T10 split")
