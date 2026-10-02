"""A function must not accept a parameter it ignores.

`WalkForwardResult.to_scorecard_result` accepted `num_trials`,
`sr_variance_annualised` and `periods_per_year`, documented all three, and
read none of them. `Result` carries nine fields and not one is a trial count,
a Sharpe variance or an annualisation basis, so every value a caller passed
was discarded. All five call sites omitted them and got defaults that were
discarded too, which is why nothing ever failed.

This is a worse shape than a wrong default. A wrong default produces a wrong
number, which can be caught by comparing against a recorded run. A dead
parameter produces the *right* number while the signature advertises control
that does not exist, so there is nothing to compare and nothing to notice.

The two that mattered here both named load-bearing machinery:
`periods_per_year` documented itself "use 6048 for H1" and changed no
annualisation, and `num_trials` named the honest trial count behind the DSR
haircut and fed nothing.

Scope is deliberately narrow. Unused parameters are legitimate in plenty of
places — interface conformance, callbacks, overridden methods, `**kwargs`
passthroughs — so this checks the public entry points that assemble or score
results, where a silently ignored argument is a false claim about the
measurement rather than a harmless stub.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

#: (module path, qualified function name). Entry points whose parameters are
#: claims about how a number was produced.
WATCHED = [
    ("packages/qh-research/research/engines/btpy_runner.py", "to_scorecard_result"),
    ("packages/qh-research/research/reports/power.py", "power_curve"),
    ("packages/qh-research/research/metrics/returns.py", "resolve_periods_per_year"),
]

IGNORED = {"self", "cls", "args", "kwargs"}


def _find_func(tree: ast.AST, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _params(fn) -> list[str]:
    a = fn.args
    names = [p.arg for p in (*a.posonlyargs, *a.args, *a.kwonlyargs)]
    return [n for n in names if n not in IGNORED]


def _names_used_in_body(fn) -> set[str]:
    used: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            pass  # attribute access on a param still shows the Name node
    # the signature's own annotations and defaults are not "use"
    return used


@pytest.mark.parametrize("relpath,func", WATCHED,
                         ids=[f"{Path(p).stem}:{f}" for p, f in WATCHED])
def test_every_parameter_is_read(relpath, func):
    path = REPO / relpath
    assert path.exists(), relpath
    tree = ast.parse(path.read_text(encoding="utf-8"))
    fn = _find_func(tree, func)
    assert fn is not None, f"{func} not found in {relpath}"

    declared = _params(fn)
    body = ast.Module(body=fn.body, type_ignores=[])
    used = _names_used_in_body(body)
    dead = [p for p in declared if p not in used]

    assert not dead, (
        f"{func} accepts {dead} and never reads them. A parameter that is "
        "documented but ignored advertises control the function does not "
        "have, and produces a correct-looking number while doing so.")


def test_the_scorecard_builder_no_longer_claims_what_it_cannot_do():
    """Named so the specific regression stays recognisable."""
    from research.engines.btpy_runner import WalkForwardResult
    sig = inspect.signature(WalkForwardResult.to_scorecard_result)
    for gone in ("num_trials", "sr_variance_annualised", "periods_per_year"):
        assert gone not in sig.parameters, (
            f"{gone} is back on to_scorecard_result; Result has no field for "
            "it, so it would be discarded again")


def test_result_still_has_no_field_the_removed_parameters_would_feed():
    """If Result ever grows a trial count or annualisation basis, the
    parameters should come back wired up rather than stay removed."""
    import dataclasses
    from research.reports.scorecard import Result
    fields = {f.name for f in dataclasses.fields(Result)}
    assert not (fields & {"num_trials", "periods_per_year", "sr_variance",
                          "sr_variance_annualised"}), (
        "Result gained a field the removed parameters were meant to feed; "
        "re-add them wired to it instead of leaving the gap")
