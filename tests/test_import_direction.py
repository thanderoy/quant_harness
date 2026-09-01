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
