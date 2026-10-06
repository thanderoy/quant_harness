"""X19 — import-direction contract, and X32 — stdlib shadowing.

    resources  <-  strategies  <-  { research, platform }

AST-level, not import-time: the check must fail the build for a forbidden
import that sits inside a function body or a try/except, which an import-time
probe would never execute. Fails the build, not a warning — this is the one
rule not relaxed for convenience, because it is what makes backtest/live parity
structural rather than aspirational.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

#: Acceptance coverage (docs/REWRITE.md §7). Read by
#: tests/test_x_coverage.py — keep in step with what this file asserts.
pytestmark = [pytest.mark.x("X19"), pytest.mark.x("X32")]


PACKAGES_DIR = Path(__file__).resolve().parents[1] / "packages"

#: distribution directory -> import name
DISTRIBUTIONS = {
    "qh-resources": "resources",
    "qh-strategies": "strategies",
    "qh-research": "research",
    "qh-platform": "platform",
}

#: What each package is permitted to import from the others.
ALLOWED: dict[str, set[str]] = {
    "resources": set(),
    "strategies": {"resources"},
    "research": {"resources", "strategies"},
    "platform": {"resources", "strategies"},
}

INTERNAL = set(DISTRIBUTIONS.values())


def _source_files(pkg_dir: Path, import_name: str) -> list[Path]:
    root = pkg_dir / import_name
    if not root.exists():
        return []
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def _imported_top_levels(path: Path) -> set[str]:
    """Top-level module names imported by this file, from anywhere in it."""
    tree = ast.parse(path.read_text(), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # level > 0 is a relative import — same package by construction.
            if node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return found


def _existing_packages() -> list[tuple[str, Path]]:
    out = []
    for dist, name in DISTRIBUTIONS.items():
        d = PACKAGES_DIR / dist
        if (d / name).exists():
            out.append((name, d))
    return out


def test_x19_import_direction():
    existing = _existing_packages()
    assert existing, "no packages found — the guard would vacuously pass"

    violations: list[str] = []
    for name, pkg_dir in existing:
        permitted = ALLOWED[name]
        for src in _source_files(pkg_dir, name):
            for imported in _imported_top_levels(src) & INTERNAL:
                if imported == name or imported in permitted:
                    continue
                rel = src.relative_to(PACKAGES_DIR)
                violations.append(f"{rel}: {name} must not import {imported}")

    assert not violations, "import-direction violations:\n  " + "\n  ".join(violations)


def test_x19_guard_detects_a_planted_violation(tmp_path):
    """The guard must fail on a real violation.

    Without this, an over-permissive ALLOWED table or a broken walker gives a
    green build that checks nothing — the failure mode of every guard that is
    never seen to fail.
    """
    src = tmp_path / "bad.py"
    src.write_text("def f():\n    from research.log import verify\n    return verify\n")
    assert "research" in _imported_top_levels(src)
    assert "research" not in ALLOWED["resources"]


def test_x32_platform_still_resolves_to_stdlib():
    """A top-level package named `platform` shadows the stdlib module.

    Accepted deliberately, but the failure is silent and surfaces far from its
    cause, so it is tested rather than trusted.
    """
    import platform as platform_mod

    assert hasattr(platform_mod, "python_version"), (
        "`import platform` did not resolve to the stdlib module — qh-platform "
        "is shadowing it"
    )
    assert platform_mod.python_version().startswith(
        f"{sys.version_info.major}.{sys.version_info.minor}")


@pytest.mark.parametrize("name", sorted(DISTRIBUTIONS.values()))
def test_allowed_table_covers_every_declared_package(name):
    assert name in ALLOWED, f"{name} has no declared import policy"


# -- no second definition ----------------------------------------------------
#
# Import direction says `platform` may import `resources`. It does not say
# `platform` must *stop defining its own copy*, and until Phase 3 step 4 it
# had one: four indicator functions duplicated verbatim, except `wma`, which
# had silently diverged — the live app reduced with `np.dot` while the
# backtester reduced with `math.fsum`. Two copies of a formula is two chances
# for the backtest to disagree with the account, and the one that diverged is
# the one nobody noticed.
#
# The names below are owned by `resources`. The platform may re-export them;
# it may not define them again.

#: import name in `resources` -> the callables it is the single home of
SINGLY_DEFINED: dict[str, frozenset[str]] = {
    "resources.indicators": frozenset({"atr", "hma", "stochastic", "wma"}),
    "resources.risk.drawdown_guard": frozenset({"DrawdownGuard", "PeakStore"}),
}

#: Deliberate exceptions, each with the reason it is not a duplicate.
#: `JsonPeakStore` is a *platform* concern — it persists to a path on the
#: container's volume, which `resources` has no business knowing about — so
#: it is an implementation of a `resources` interface, not a second copy of
#: one. See seq=116, which first mistook it for a feature gap.
NOT_DUPLICATES: frozenset[str] = frozenset({"JsonPeakStore"})


def _toplevel_defs(path: Path) -> set[str]:
    """Names bound by a `def`/`class` at module level in this file.

    Module level only: a name defined inside a function is a local, not a
    second public definition, and flagging those would make the guard noisy
    enough to be switched off.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }


@pytest.mark.parametrize("owner,names", sorted(SINGLY_DEFINED.items()))
def test_the_platform_imports_these_rather_than_defining_them_again(owner, names):
    """A name `resources` owns must not be redefined under qh-platform.

    This is the guard Phase 3 step 4 exists to leave behind. Deleting the
    duplicate is a one-off; stopping the next one is what keeps the property.

    It reads the source rather than importing it, so a redefinition inside a
    module the test environment cannot import — anything needing Django
    settings or a database, which is most of the platform — is still caught.
    """
    platform_dir = PACKAGES_DIR / "qh-platform"
    if not platform_dir.exists():
        pytest.skip("qh-platform not present")

    offenders: list[str] = []
    for path in platform_dir.rglob("*.py"):
        if "__pycache__" in path.parts or ".venv" in path.parts:
            continue
        if "/tests/" in str(path) or path.name.startswith("test_"):
            continue
        clash = (_toplevel_defs(path) & names) - NOT_DUPLICATES
        for name in sorted(clash):
            offenders.append(f"{path.relative_to(platform_dir)}:{name}")

    assert not offenders, (
        f"{owner} is the single definition of {sorted(names)}, but qh-platform "
        f"defines its own: {offenders}. Import it instead. If this really is a "
        f"platform-specific implementation rather than a copy, add it to "
        f"NOT_DUPLICATES with the reason.")
