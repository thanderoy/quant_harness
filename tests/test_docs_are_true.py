"""The documentation gate: prose about this repo must match this repo.

`test_x_coverage.py` exists because "X1-X32 pass in CI" is only worth
something if something checks it. This file exists for the same reason and a
worse failure: on 2026-09-20 an audit found five docs stale, and two of them
wrong in ways a reader hits immediately. The README's Quick start did not
work — `python -m unittest discover tests -v` gave 7 errors on 19 collected
tests against a suite of 549, and the advertised calibration demo could not
import at all. `docs/STATUS.md` described the pre-rewrite package layout and
reported 82 tests. `docs/hardcoded_audit.md` summarised 17 RESOLVED / 13
DEFERRED where its own table said 19 / 11.

None of that was caught by anything, because nothing was looking. Docs drift
silently: no import breaks, no test reddens, and the reader who finds out is
the one following the instructions.

What is checkable is checked here. What is not — whether a paragraph is still
a good explanation — is not, and no test should pretend otherwise. The scope
is deliberately narrow: **facts about this repository that the repository can
re-derive.**
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
README = REPO / "README.md"
STATUS = REPO / "docs" / "STATUS.md"
AUDIT = REPO / "docs" / "hardcoded_audit.md"

DOCS = [p for p in (README, STATUS, AUDIT) if p.exists()]


#: A doc line can instruct the reader, or describe the spec's target state or
#: the repo's past. Only the first kind makes a claim about what is true now,
#: and only that kind should fail these checks. The distinction is explicit
#: rather than a loosened pattern, because "make the red go green" would
#: otherwise be indistinguishable from it.
HISTORICAL_OR_SPEC = re.compile(
    r"^\s*>|until \d{4}-\d{2}-\d{2}|\bused to\b|\bwas\b|\bsaid\b|"
    r"\bspec\b|\bplanned\b|\btarget\b|does not exist|not built|supersed",
    re.I)


def describes_rather_than_instructs(lines: list[str], i: int,
                                    radius: int = 1) -> bool:
    """True when the line at 1-based ``i`` sits in descriptive context."""
    window = lines[max(0, i - 1 - radius): i + radius]
    return any(HISTORICAL_OR_SPEC.search(w) for w in window)


def read(path: pathlib.Path) -> str:
    return path.read_text(errors="ignore")


# -- packages ---------------------------------------------------------------

def actual_packages() -> set[str]:
    root = REPO / "packages"
    return {p.name for p in root.iterdir() if p.is_dir()} if root.exists() else set()


def test_no_doc_claims_a_package_that_does_not_exist():
    """The exact error this file was written after.

    A `qh-platform` that exists in the spec and in pytest's path list, but not
    on disk, was written into STATUS.md as a built package. Aspirational and
    actual are both fine to state; stating one as the other is not.
    """
    real = actual_packages()
    named = re.compile(r"`(qh-[a-z]+)`")
    offenders = []
    for doc in DOCS:
        text = read(doc)
        for m in named.finditer(text):
            pkg = m.group(1)
            if pkg in real:
                continue
            lines = text.splitlines()
            line = text[: m.start()].count("\n") + 1
            # A doc may name a package that is not built yet — the spec does —
            # but the surrounding sentence has to make that clear.
            if describes_rather_than_instructs(lines, line):
                continue
            offenders.append(f"{doc.name}:{line}: {lines[line-1].strip()[:90]}")
    assert not offenders, (
        "docs name packages that are not in packages/ and do not say so:\n  "
        + "\n  ".join(offenders)
        + f"\nactual: {sorted(real)}")


# -- the acceptance frontier ------------------------------------------------

def test_stated_x_coverage_matches_the_manifest():
    """"35 of 35 X ids" in prose must be what the manifest says."""
    import sys
    sys.path.insert(0, str(REPO / "tests"))
    import test_x_coverage as cov

    total = len(cov.ALL_X_IDS)
    covered = total - len(cov.DEFERRED)
    pattern = re.compile(r"(\d+)\s*(?:of|/)\s*(\d+)\s*X ids", re.I)
    found = 0
    for doc in DOCS:
        for m in pattern.finditer(read(doc)):
            found += 1
            assert (int(m.group(1)), int(m.group(2))) == (covered, total), (
                f"{doc.name} says {m.group(0)}; the manifest says "
                f"{covered} of {total}")
    assert found, (
        "no doc states the X coverage. This assertion is what keeps the "
        "number honest, so if the sentence is dropped, drop this too rather "
        "than leaving a check that can never fire.")


# -- the audit's own arithmetic ---------------------------------------------

@pytest.mark.skipif(not AUDIT.exists(), reason="no hardcoded audit")
def test_the_audit_summary_matches_its_own_table():
    """A summary line that disagrees with the table above it is worse than no
    summary: it is the number a reader quotes without scrolling."""
    text = read(AUDIT)
    resolved = len(re.findall(r"^\|[^|]*\|.*\|\s*RESOLVED", text, re.M))
    deferred = len(re.findall(r"^\|[^|]*\|.*\|\s*DEFERRED", text, re.M))

    m = re.search(r"(\d+)\s+RESOLVED,\s*(\d+)\s+DEFERRED", text)
    assert m, "the audit no longer states a RESOLVED/DEFERRED summary"
    assert (int(m.group(1)), int(m.group(2))) == (resolved, deferred), (
        f"summary says {m.group(1)} RESOLVED / {m.group(2)} DEFERRED; "
        f"the table has {resolved} / {deferred}")


# -- documented commands ----------------------------------------------------

def workflow_text() -> str:
    wf = REPO / ".github" / "workflows"
    if not wf.exists():
        return ""
    return "\n".join(read(p) for p in wf.glob("*.yml"))


def test_the_readme_does_not_document_a_test_runner_ci_does_not_use():
    """The README told readers to run `unittest discover`, which collects 19
    of 549 tests and errors on 7. It said so for months because nothing
    compared it to how the suite is actually run."""
    if not README.exists():
        pytest.skip("no README")
    lines = read(README).splitlines()
    live = [f"line {i}" for i, l in enumerate(lines, 1)
            if "unittest discover" in l
            and not describes_rather_than_instructs(lines, i)]
    assert not live, (
        f"the README documents `unittest discover` at {live}, which does not "
        "run this suite — the package paths are set in pytest's config. "
        "(A historical note saying it used to is fine; an instruction is not.)")
    text = read(README)
    wf = workflow_text()
    if wf and "pytest" in wf:
        assert "pytest" in text, (
            "CI runs pytest and the README does not mention it")


def test_paths_the_readme_tells_you_to_run_exist():
    """A quick-start command naming a file that is not there is the cheapest
    possible documentation bug and the most annoying to hit."""
    if not README.exists():
        pytest.skip("no README")
    text = read(README)
    missing = []
    for m in re.finditer(r"python -m (examples\.[a-z_0-9.]+)", text):
        rel = m.group(1).replace(".", "/") + ".py"
        if not (REPO / rel).exists():
            missing.append(rel)
    for m in re.finditer(r"PYTHONPATH=([^\s\\]+)", text):
        for part in m.group(1).split(":"):
            if part and not (REPO / part).exists():
                missing.append(part)
    assert not missing, f"README references paths that do not exist: {missing}"


# -- test counts ------------------------------------------------------------

#: A bare "N passed" is the mistake that produced a wrong number in STATUS.md:
#: 525/24 was true on a feature branch and false on `develop`, where a
#: branch-comparison test skips. The count depends on conditions, so a doc
#: that states one must state the condition.
CONDITIONS = re.compile(
    r"CI|out-of-repo|QH_PARITY_DATA_DIR|QH_WMPS_DIR|locally|with the .* data|"
    r"data present|data hidden", re.I)


def test_a_stated_test_count_names_the_condition_it_holds_under():
    offenders = []
    for doc in DOCS:
        lines = read(doc).splitlines()
        for i, line in enumerate(lines, 1):
            if not re.search(r"\b\d{2,4}\s+passed\b", line):
                continue
            window = " ".join(lines[max(0, i - 3): i + 2])
            if describes_rather_than_instructs(lines, i):
                continue
            if not CONDITIONS.search(window):
                offenders.append(f"{doc.name}:{i}: {line.strip()[:90]}")
    assert not offenders, (
        "test counts stated without the condition they hold under:\n  "
        + "\n  ".join(offenders)
        + "\nThe suite reports different numbers with and without the "
          "out-of-repo data; an unqualified count is true somewhere and "
          "false elsewhere.")


# -- provenance -------------------------------------------------------------

def test_no_constant_claims_a_source_it_does_not_carry():
    """`cost_model.py` carried the header "Constants from Pepperstone
    published docs" while the Phase 0 memo recorded the commission as
    HAND_ENTERED. Both were in the repo at once, and the claim of sourcing was
    the one a reader would believe.

    A module that asserts its numbers are sourced must expose a provenance
    record saying which, so the claim is data rather than a header.
    """
    cost = (REPO / "packages" / "qh-research" / "research" / "datasets"
            / "cost_model.py")
    if not cost.exists():
        pytest.skip("cost_model not present")
    text = read(cost)
    claims_source = re.search(r"from .{0,30}published docs", text, re.I)
    if not claims_source:
        return
    tree = ast.parse(text)
    names = {t.id for node in ast.walk(tree)
             if isinstance(node, ast.Assign)
             for t in node.targets if isinstance(t, ast.Name)}
    assert names & {"COMMISSION_PROVENANCE", "COMMISSION_MEASURED"}, (
        "the module claims its constants come from published docs but exposes "
        "no provenance record; a header is not a citation")
