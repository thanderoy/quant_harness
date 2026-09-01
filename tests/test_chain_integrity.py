"""X21-adjacent — the research chain must exist and verify in the working tree.

This exists because of a real incident, not a hypothetical one. Switching from
the graft branch back to a `main` that predated the graft deleted the whole
migrated tree (correct git behaviour); the subsequent fast-forward restored
most of it but left 16 files absent, including `entries.jsonl`, `log.md` and
the tracked `XAUUSD_H1.csv`. A `git add -A` then recorded those absences as
deletions, and the commit looked entirely normal.

The remote was never at risk and everything was recoverable. What was missing
was any check that would have *noticed*. A hash chain proves its contents
were not altered; it says nothing about whether the file is still there. This
is the "is it still there" half.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

RESEARCH_PKG = Path(__file__).resolve().parents[1] / "packages" / "qh-research"
RESEARCH = RESEARCH_PKG / "research"

#: Files whose absence is a loss rather than an inconvenience.
LOAD_BEARING = (
    "log/entries.jsonl",
    "log/log.md",
    "log.py",
    "seed_log.py",
    "post/dsr.py",
    "data_manifest.py",
    "data_manifest.json",
    "data/XAUUSD_H1.csv",   # tracked deliberately: not reproducible from broker
)


@pytest.mark.skipif(not RESEARCH.exists(),
                    reason="research package not present in this checkout")
@pytest.mark.parametrize("rel", LOAD_BEARING)
def test_load_bearing_file_present_and_nonempty(rel):
    p = RESEARCH / rel
    assert p.exists(), f"{rel} is missing from the working tree"
    assert p.stat().st_size > 0, f"{rel} is present but empty"


@pytest.mark.skipif(not RESEARCH.exists(),
                    reason="research package not present in this checkout")
def test_chain_verifies_and_trial_count_is_monotonic():
    """The chain verifies, and `trial_count()` never goes backwards.

    The trial count is the one artifact that cannot be reconstructed: it is the
    N that feeds the DSR haircut, and a silently-dropped losing trial inflates
    every future Sharpe. It may rise as research proceeds; it must never fall.
    """
    sys.path.insert(0, str(RESEARCH_PKG))
    try:
        from research.log import _read_all, trial_count, verify, DEFAULT_LOG_DIR

        ok, msg = verify()
        assert ok, f"hash chain broken: {msg}"

        entries = _read_all(DEFAULT_LOG_DIR)
        assert len(entries) >= 87, (
            f"entry count fell to {len(entries)}; the log is append-only and "
            f"was at 87 when this guard was written"
        )
        assert trial_count() >= 26, (
            f"trial_count fell to {trial_count()}; it was 26 at the Phase 0 D7 "
            f"baseline and must never decrease"
        )
        # seq must be dense and ordered — a gap means a line was removed.
        seqs = [e.seq for e in entries]
        assert seqs == list(range(len(entries))), "seq numbers are not dense"
    finally:
        sys.path.remove(str(RESEARCH_PKG))
