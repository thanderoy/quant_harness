"""X1, X2, X20 — the properties that make `resources` the instrument-neutral core.

None of these test behaviour. They test that the package cannot quietly stop
being what the architecture claims it is: no instrument knowledge outside the
registry, and no hidden dependency on a network or a Django settings module.

They are cheap and they only ever fail when someone has introduced exactly
the coupling the layering exists to prevent, which is the point.
"""

from __future__ import annotations

import ast
import pathlib
import re
import socket
import subprocess
import sys

import pytest

RESOURCES = pathlib.Path(__file__).resolve().parents[1] / "resources"

#: A currency pair or metal ticker: six uppercase letters. Deliberately broad —
#: a false positive is a five-second conversation, a false negative is an
#: instrument assumption living in the symbol-agnostic core.
SYMBOL_LITERAL = re.compile(r"^[A-Z]{6}$")

#: Six-letter uppercase strings that are not instruments.
ALLOWED = frozenset({"SELECT", "COMMIT", "SILENT", "ORACLE"})


def _source_files(exclude: str | None = None):
    for p in sorted(RESOURCES.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        if exclude and exclude in p.parts:
            continue
        yield p


@pytest.mark.x("X1")
def test_no_symbol_literal_outside_the_registry():
    """AST-level, not grep: a comment mentioning EURUSD is fine, a string is not.

    Every instrument-specific fact belongs in exactly one declarative place.
    A bare "XAUUSD" in the sizer or the mask is the single-instrument
    assumption growing back, and it is invisible in review because it looks
    like an ordinary default.
    """
    offenders = []
    for path in _source_files(exclude="instruments"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and SYMBOL_LITERAL.match(node.value)
                    and node.value not in ALLOWED):
                offenders.append(
                    f"{path.relative_to(RESOURCES)}:{node.lineno} {node.value!r}")
    assert not offenders, (
        "instrument literals outside instruments/:\n  " + "\n  ".join(offenders))


@pytest.mark.x("X2")
def test_importing_the_registry_opens_no_socket(monkeypatch):
    """The registry loads from a pinned snapshot, so a backtest is offline
    and reproducible. A network call at import time would make it neither."""
    import importlib

    def refuse(*a, **k):
        raise AssertionError("resources.instruments opened a socket at import")

    monkeypatch.setattr(socket, "socket", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    for name in [m for m in list(sys.modules) if m.startswith("resources")]:
        del sys.modules[name]
    importlib.import_module("resources.instruments")


@pytest.mark.x("X20")
def test_resources_imports_in_a_bare_interpreter():
    """No Django settings, no package install, no path tricks beyond the one
    the layering permits.

    Run in a subprocess rather than in-process: by the time this test runs,
    pytest has already imported half the world, so an in-process import would
    prove nothing about what `resources` needs on its own.
    """
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "import resources, resources.instruments, resources.data.mask, "
        "resources.data.panel, resources.features.normalize, resources.risk.sizer\n"
        "assert 'django' not in sys.modules\n"
        "assert 'research' not in sys.modules\n"
        "print('ok')\n" % str(RESOURCES.parent)
    )
    proc = subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True, timeout=120,
                          env={"PATH": "/usr/bin:/bin"})
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "ok"


@pytest.mark.x("X20")
def test_resources_imports_nothing_from_the_other_packages():
    """The import-direction contract, checked at the package's own boundary.

    tests/test_import_direction.py (X19) enforces this repo-wide from the
    outside; this asserts it from inside the package that must hold it most
    strictly, so a violation fails here first with a clearer message.
    """
    forbidden = {"research", "strategies", "platform", "django", "celery"}
    offenders = []
    for path in _source_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = ([node.module.split(".")[0]]
                         if node.level == 0 and node.module else [])
            else:
                continue
            for n in names:
                if n in forbidden:
                    offenders.append(
                        f"{path.relative_to(RESOURCES)}:{node.lineno} imports {n}")
    assert not offenders, "\n  ".join(offenders)
