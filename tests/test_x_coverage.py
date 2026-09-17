"""The acceptance-criteria gate: X1-X32, and what is honestly not done yet.

Phase 1 acceptance criterion 4 is "X1-X32 pass in CI". That sentence is only
worth something if something checks it, otherwise it degrades into a claim
somebody remembers making. This file is the check.

Coverage is declared with a **marker**, never prose::

    pytestmark = [pytest.mark.x("X28")]      # module-level
    @pytest.mark.x("X1")                      # or per test

A docstring that happens to mention X28 does not count. That distinction is
the whole design: the first version of this gate scanned docstrings and
reported twelve X ids as covered, of which eleven were module docstrings
mentioning a number in passing. Prose drifts from what a file asserts; a
marker is a statement someone had to write on purpose.

The manifest below carries the deferred items with a reason and the task
that unblocks each. Three properties are enforced, and the third is the one
that stops this file becoming decoration:

1. Every X id in the spec is accounted for — covered or explicitly deferred.
2. Nothing claimed as covered is missing its marker.
3. **Nothing deferred has quietly gained coverage.** If a deferred item picks
   up a marker, this fails and demands the manifest be updated. Without it the
   deferred list only ever grows stale in the flattering direction.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]

#: Every acceptance test the spec defines (docs/REWRITE.md §7).
#: X15 is counted as X15a-d, per acceptance criterion 4.
ALL_X_IDS: tuple[str, ...] = (
    "X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8", "X9", "X10",
    "X11", "X12", "X13", "X14", "X15a", "X15b", "X15c", "X15d",
    "X16", "X17", "X18", "X19", "X20", "X21", "X22", "X23", "X24",
    "X25", "X26", "X27", "X28", "X29", "X30", "X31", "X32",
)

#: X id -> (why it is not covered, the task that unblocks it).
#: Every entry here is a known hole in Phase 1 acceptance, stated rather than
#: quietly absent. Removing an entry is how the phase closes.
DEFERRED: dict[str, tuple[str, str]] = {}


#: X id -> what CI cannot exercise, and why. Coverage that depends on data
#: outside this repository is real on a developer machine and absent on a
#: runner, and a green tick that hides that is exactly the reassurance this
#: file exists to refuse.
CI_LIMITED: dict[str, str] = {
    "X15a": ("recomputation needs seq=31's OHLC CSVs, which live in the WMPS "
             "repo; on a runner those tests skip and only the committed "
             "fixture is validated against the adjudicated artifact. Set "
             "$QH_PARITY_DATA_DIR to exercise the full check."),
    "X22": ("the fixture is only bit-reproducible on the machine that made "
            "it. `wma` reduces its window with `np.dot`, so the summation "
            "order comes from the OpenBLAS kernel, not from the source; all "
            "five `wma`/`hma` columns land within a few ULP rather than "
            "equal, and `hma` inherits it. CI asserts the pandas-only columns "
            "exactly, bounds the rest, and shows the difference cannot move a "
            "signal. The direct port-vs-WMPS comparison, which is exact on "
            "every column, needs the WMPS checkout and skips on a runner. Set "
            "$QH_WMPS_DIR to run it."),
    "X17": ("behaviour-neutrality is proven two ways and CI sees one of "
            "them. The commit-vs-parent comparison cannot be re-run from a "
            "later commit, so it is recorded in the seq=96 metrics; the "
            "recomputation needs the same out-of-repo CSVs as X15a and "
            "skips on a runner. What CI asserts is that the pinned fixture "
            "still loads and still matches the seq=31 artifact."),
}


def _marked_ids() -> dict[str, set[str]]:
    """X ids declared by a marker, mapped to the files declaring them.

    Parsed from source rather than collected from pytest, so the result does
    not depend on test ordering, on a plugin, or on anything having run.
    """
    found: dict[str, set[str]] = {}

    def record(value: str, path: pathlib.Path) -> None:
        found.setdefault(value, set()).add(str(path.relative_to(REPO)))

    def ids_from_call(node: ast.AST, path: pathlib.Path) -> None:
        """Pull "X28" out of pytest.mark.x("X28")."""
        if not isinstance(node, ast.Call):
            return
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "x"):
            return
        owner = func.value
        if not (isinstance(owner, ast.Attribute) and owner.attr == "mark"):
            return
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                record(arg.value, path)

    for path in sorted(REPO.rglob("test_*.py")):
        if "__pycache__" in path.parts or ".venv" in path.parts:
            continue
        try:
            tree = ast.parse(path.read_text(), filename=str(path))
        except SyntaxError:  # pragma: no cover - a broken test file fails elsewhere
            continue
        for node in ast.walk(tree):
            ids_from_call(node, path)
    return found


@pytest.fixture(scope="module")
def marked() -> dict[str, set[str]]:
    return _marked_ids()


def test_the_manifest_only_defers_real_x_ids():
    unknown = sorted(set(DEFERRED) - set(ALL_X_IDS))
    assert not unknown, f"DEFERRED names ids the spec does not define: {unknown}"


def test_every_x_id_is_covered_or_explicitly_deferred(marked):
    """No silent holes. An id that is neither marked nor deferred fails here."""
    unaccounted = [x for x in ALL_X_IDS
                   if x not in marked and x not in DEFERRED]
    assert not unaccounted, (
        "X ids with neither a covering test nor a DEFERRED entry: "
        f"{unaccounted}. Either mark a test with pytest.mark.x(...) or add "
        "the id to DEFERRED with a reason and the task that unblocks it.")


def test_no_deferred_item_has_quietly_gained_coverage(marked):
    """The anti-rot check.

    Without this, DEFERRED only ever grows stale in the flattering direction:
    work gets done, the entry stays, and the phase looks further from
    complete than it is — or worse, the entry is trusted as still true.
    """
    now_covered = sorted(x for x in DEFERRED if x in marked)
    assert not now_covered, (
        f"{now_covered} are marked as covered but still listed in DEFERRED. "
        "Remove them from the manifest — that is what closing the phase "
        "looks like.")


def test_the_covered_set_is_what_we_think_it_is(marked):
    """Pins the current frontier, so progress and regression are both visible."""
    expected = sorted(set(ALL_X_IDS) - set(DEFERRED))
    assert sorted(marked) == expected, (
        f"marked={sorted(marked)}\nexpected={expected}\n"
        "A new marker is good news — update this expectation and DEFERRED.")


def test_acceptance_criterion_four_is_met():
    """Criterion 4 is "X1-X32 pass in CI". Every X id now has a covering test.

    Its predecessor asserted the opposite and was written to fail the moment
    DEFERRED emptied, so the phase could not quietly be declared complete. T9b
    emptied it. What is left to say is narrower and still worth pinning: the
    criterion is about CI, so an id covered only by a test that skips on a
    runner has not met it — CI_LIMITED is where that distinction is kept
    honest, and it is not empty.
    """
    assert not DEFERRED, f"still deferred: {sorted(DEFERRED)}"
    assert CI_LIMITED, (
        "CI_LIMITED is empty. Either every check really does run on a runner — "
        "in which case say so and delete this assertion — or a limitation was "
        "dropped without being resolved.")


def test_ci_limitations_name_real_covered_ids(marked):
    """A limitation on an id that is deferred or absent is a stale note."""
    for x in CI_LIMITED:
        assert x in marked, (
            f"{x} is listed in CI_LIMITED but has no covering test")
        assert x not in DEFERRED, (
            f"{x} cannot be both deferred and CI-limited")


def test_partially_exercised_coverage_is_declared_not_implied():
    """X15a is the current case: green in CI does not mean fully checked.

    Recorded so the distinction survives being forgotten. If the data ever
    becomes available to CI, delete the entry — the test above will not let
    it linger on an id that stopped needing it.
    """
    assert "X15a" in CI_LIMITED
    assert "QH_PARITY_DATA_DIR" in CI_LIMITED["X15a"]


def test_markers_are_registered_so_they_cannot_be_typos():
    """An unregistered mark is a warning, not an error, so a typo'd
    pytest.mark.xx(...) would silently cover nothing."""
    cfg = (REPO / "pyproject.toml").read_text()
    assert "\"x(id):" in cfg or "'x(id):" in cfg, (
        "the x marker must be registered in [tool.pytest.ini_options] markers")
