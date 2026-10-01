"""Two things are called `strategies`, and that is safe for reasons worth pinning.

`strategies` (the qh-strategies package) is the symbol-agnostic strategy
interface. `research.engines.strategies` holds the frozen backtest-engine
implementations that exist to generate parity fixtures. Both sit on pytest's
pythonpath, and STATUS.md has carried the overlap as an unresolved risk.

Measured rather than assumed: no module imports both, and nothing inside
`research/` uses a bare `import strategies`. Every import there is fully
qualified, so the interpreter never has to choose. The overlap is a naming
wart, not an ambiguity.

That makes a rename the wrong fix — it would touch ten files and move real
risk around to remove a cosmetic one. What was actually missing is a guard on
the property that keeps it safe, so the wart cannot quietly become a bug. The
hazard is specific and this is what guards it: a bare `import strategies` from
inside `research/engines/strategies/` resolves to the *top-level* package, not
the sibling module, and would do so silently.
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
RESEARCH = REPO / "packages" / "qh-research" / "research"


def _py_files(root: Path):
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def _toplevel_imports(path: Path) -> set[str]:
    """Absolute module roots this file imports, ignoring relative imports."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:                      # not ours to police here
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                out.add(node.module.split(".")[0])
    return out


# -- the two names are genuinely different things ---------------------------

def test_the_two_strategies_modules_are_distinct():
    top = importlib.import_module("strategies")
    eng = importlib.import_module("research.engines.strategies")
    assert Path(top.__file__).resolve() != Path(eng.__file__).resolve()


def test_each_holds_what_its_name_promises():
    top = importlib.import_module("strategies")
    eng = importlib.import_module("research.engines.strategies")
    assert hasattr(top, "__path__")
    # The engine package exports the frozen parity generators.
    assert any(hasattr(eng, n) for n in
               ("HMAStoch1H", "ASQSafeScalping", "EbbNFlow")), dir(eng)
    # The interface package does not.
    assert not hasattr(top, "HMAStoch1H")


# -- the property that makes the overlap safe -------------------------------

def test_nothing_under_research_imports_the_top_level_strategies_package():
    """The hazard, guarded.

    A bare `import strategies` inside research/ binds the qh-strategies
    package, not the sibling engine module, and nothing in the import would
    say so. Every import under research/ is fully qualified today; this keeps
    it that way.
    """
    offenders = [
        str(p.relative_to(REPO)) for p in _py_files(RESEARCH)
        if "strategies" in _toplevel_imports(p)
    ]
    assert not offenders, (
        "these modules under research/ import the top-level `strategies` "
        f"package, which shadows research.engines.strategies: {offenders}")


def test_no_module_anywhere_imports_both_namespaces():
    both = []
    for p in _py_files(REPO / "packages") + _py_files(REPO / "tests"):
        src = p.read_text(encoding="utf-8", errors="ignore")
        roots = _toplevel_imports(p)
        if "strategies" in roots and "research.engines.strategies" in src:
            both.append(str(p.relative_to(REPO)))
    assert not both, (
        "a module reading both namespaces has to disambiguate by eye: " + str(both))


def test_the_engine_package_is_reached_only_through_its_parent():
    """`research.engines.strategies` is always imported fully qualified, so
    the interpreter never resolves a bare name against two candidates."""
    bad = []
    for p in _py_files(RESEARCH):
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            s = line.strip()
            if s.startswith("import strategies") or s.startswith("from strategies "):
                bad.append(f"{p.relative_to(REPO)}: {s}")
    assert not bad, bad
