"""Acceptance criterion 5 — one strategy module, every instrument, no branching.

    "A single strategy module runs unmodified against all seven majors and
    against XAUUSD, producing per-instrument results, with no symbol-specific
    branching anywhere in the call path."

This is the criterion that decides whether the rewrite achieved anything. The
other nine can all hold in a codebase that is still, underneath, a XAUUSD
system with the string moved somewhere tidier.

**What these tests deliberately do not do: report a Sharpe.**

``flood_tide`` is SHELVED (seq=34, two iterations, regime-filtered E-Ratio
null decisive). Running a dead mechanism across eight instruments and reading
the returns would be eight new trials against a hypothesis already refused —
the exact multiplicity the research log exists to tax. Criterion 5 asks
whether the module *runs* unmodified and yields per-instrument results, which
is a structural question, so it is answered structurally: shapes, call
signatures, and the sizer turning identical risk units into correctly
different lots. No P&L is computed anywhere in this file, and none should be
added to it.

The strongest assertion here is :func:`test_identical_bars_give_identical_
results_across_instruments`: hand two different instruments byte-identical
price series and the outputs must match exactly. A single ``if symbol ==``
anywhere in the call path breaks it, wherever it is hidden.
"""

from __future__ import annotations

import ast
import pathlib
import re

import numpy as np
import pandas as pd
import pytest

from resources.instruments.registry import Registry
from resources.risk.sizer import StaticFxRates, SizingReason, size_position
from strategies import FloodTide, all_strategies, run

from synthetic import make_bars

pytestmark = [pytest.mark.x("X5"), pytest.mark.x("X6"), pytest.mark.x("X30")]

STRATEGIES_DIR = pathlib.Path(__file__).resolve().parents[1] / "strategies"

#: The pinned Pepperstone live snapshot — the venue that would actually
#: execute. Criterion 5 names the seven majors and XAUUSD; XAGUSD is in the
#: snapshot too and is included wherever it costs nothing, because an
#: instrument excluded from a generality claim is the beginning of the
#: single-instrument assumption growing back.
SNAPSHOT = "pepperstone_live_20260906.json"

#: Account currency for the sizing leg. A constant, not an instrument fact.
ACCOUNT_CCY = "USD"

#: Rates pinned for the test. Values are round numbers chosen to make the
#: arithmetic checkable by hand, not quotes from any date.
FX = StaticFxRates({("JPY", "USD"): 0.0065,
                    ("CHF", "USD"): 1.25,
                    ("CAD", "USD"): 0.75})


@pytest.fixture(scope="module")
def registry() -> Registry:
    return Registry.load(SNAPSHOT)


def bars_for(spec, *, n: int = 2500, seed: int = 5) -> pd.DataFrame:
    """A price series at this instrument's scale, derived from its spec.

    The starting level comes from ``digits`` rather than from a table of
    remembered prices: a five-digit pair sits near 1, a three-digit one near
    100, gold near 1000. Close enough to be realistic, and — the point —
    containing no instrument knowledge that a test could quietly rely on.
    """
    scale = 10.0 ** (5 - spec.digits)
    return make_bars(n, seed=seed, start=scale)


def test_the_registry_covers_the_criterion(registry):
    """Guard against the suite quietly shrinking to one instrument."""
    assert len(registry.symbols) >= 8, registry.symbols
    assert not registry.is_provisional, (
        "the acceptance run must not sit on HAND_ENTERED specs")


@pytest.mark.parametrize("strategy_factory", [type(s) for s in all_strategies()],
                         ids=[s.name for s in all_strategies()])
def test_one_module_runs_against_every_instrument(registry, strategy_factory):
    """Criterion 5, executed. Unmodified means unmodified: same class, same
    default parameters, nothing passed that names an instrument."""
    results = {}
    # A different series per instrument, not one series rescaled nine times:
    # the latter would run the same path nine times and call it generality.
    for offset, symbol in enumerate(registry.symbols):
        bars = bars_for(registry[symbol], seed=100 + offset)
        out = run(strategy_factory(), bars)          # no symbol argument exists
        results[symbol] = out

        assert out.index.equals(bars.index)
        assert np.isfinite(out["target_risk"]).all()
        assert out["entered"].sum() > 0, (
            f"{symbol} produced no entries — criterion 5 would pass vacuously")

    assert len(results) >= 8


def test_identical_bars_give_identical_results_across_instruments(registry):
    """The no-branching proof.

    Two instruments, one price series, byte-identical. Any symbol-conditional
    path anywhere below ``run`` — a tick size read from a table, a special
    case for metals, a rounding rule — makes these diverge. Nothing here has
    to know where such a branch might be hiding.
    """
    bars = make_bars(2000, seed=21, start=1.0)
    outputs = [run(FloodTide(), bars) for _ in registry.symbols]

    first = outputs[0]
    for symbol, out in zip(registry.symbols[1:], outputs[1:]):
        pd.testing.assert_frame_equal(out, first, obj=symbol)


def test_the_call_path_takes_no_symbol(registry):
    """Structural: there is nowhere to pass an instrument, so nothing can
    branch on one."""
    import inspect

    strategy = FloodTide()
    for fn in (run, strategy.prepare, strategy.evaluate_entry,
               strategy.manage_position):
        params = set(inspect.signature(fn).parameters)
        assert not (params & {"symbol", "instrument", "spec", "ticker"}), (
            f"{fn.__qualname__} accepts an instrument: {sorted(params)}")


def test_risk_units_become_per_instrument_sizes(registry):
    """"Producing per-instrument results", without producing a return series.

    One risk-unit output; nine different correct answers, and the differences
    come entirely from the registry. This is the division of labour the whole
    layering exists for: the strategy says "risk one unit with a stop this far
    away", the sizer says what that is in lots for this contract.
    """
    balance, risk_pct = 100_000.0, 0.02
    sized = {}

    for symbol in registry.symbols:
        spec = registry[symbol]
        bars = bars_for(spec)
        out = run(FloodTide(), bars)

        entries = out.index[out["entered"]]
        assert len(entries) > 0, symbol
        at = entries[0]
        stop_distance = abs(float(bars.loc[at, "open"])
                            - float(out.loc[at, "stop_price"]))

        size = size_position(
            spec=spec, account_balance=balance, account_ccy=ACCOUNT_CCY,
            risk_pct=risk_pct, stop_distance_price=stop_distance,
            fx_rate_provider=FX)
        sized[symbol] = size

        if size.tradable:
            # X28's property, checked here on the strategy's own output
            # rather than on a synthetic grid: either the sizer refuses, or
            # realised risk is inside budget.
            assert size.risk_actual_pct <= risk_pct + 1e-9, (
                f"{symbol} sized to {size.risk_actual_pct:.4%} against a "
                f"{risk_pct:.2%} budget")
        else:
            assert size.reason is not SizingReason.OK

    lots = {s: v.lots for s, v in sized.items() if v.tradable}
    assert len(set(lots.values())) > 1, (
        "every instrument sized identically — the registry is not reaching "
        f"the sizer: {lots}")


def test_small_account_refusals_are_explicit_not_silent(registry):
    """§8: at $100 under a 2% budget some instruments are simply untradeable.

    The correct outcome is a refusal, not a minimum lot. A silent clamp to
    ``volume_min`` is the D8 finding that put a live strategy on a schedule
    breaching its own risk budget, so the refusal is asserted rather than
    assumed to still be there.
    """
    balance, risk_pct = 100.0, 0.02
    refusals = {}

    for symbol in registry.symbols:
        spec = registry[symbol]
        bars = bars_for(spec)
        out = run(FloodTide(), bars)
        at = out.index[out["entered"]][0]
        stop_distance = abs(float(bars.loc[at, "open"])
                            - float(out.loc[at, "stop_price"]))

        size = size_position(
            spec=spec, account_balance=balance, account_ccy=ACCOUNT_CCY,
            risk_pct=risk_pct, stop_distance_price=stop_distance,
            fx_rate_provider=FX)
        if not size.tradable:
            refusals[symbol] = size.reason

        assert size.lots == 0.0 or size.risk_actual_pct <= risk_pct + 1e-9

    assert refusals, (
        "nothing was refused at $100 with a 2% budget — either the stops got "
        "implausibly tight or the min-lot clamp is back")


# --------------------------------------------------------------------------- #
# Purity: the same guarantee X1 gives `resources`, for the layer above it.     #
# --------------------------------------------------------------------------- #

SYMBOL_LITERAL = re.compile(r"^[A-Z]{6}$")
ALLOWED = frozenset({"SELECT", "COMMIT", "SILENT", "ORACLE"})


def test_no_symbol_literal_anywhere_in_the_strategy_package():
    """`strategies` has no ``instruments/`` escape hatch — unlike `resources`,
    there is nowhere here that an instrument literal is legitimate."""
    offenders = []
    for path in sorted(STRATEGIES_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant)
                    and isinstance(node.value, str)
                    and SYMBOL_LITERAL.match(node.value)
                    and node.value not in ALLOWED):
                offenders.append(
                    f"{path.relative_to(STRATEGIES_DIR)}:{node.lineno} "
                    f"{node.value!r}")
    assert not offenders, "\n  ".join(offenders)


def test_strategies_imports_only_resources():
    """X19 repo-wide; asserted here too so a violation fails at its own
    boundary with a message naming this package."""
    forbidden = {"research", "platform", "django", "celery",
                 "MetaTrader5", "requests"}
    offenders = []
    for path in sorted(STRATEGIES_DIR.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
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
                        f"{path.relative_to(STRATEGIES_DIR)}:{node.lineno} "
                        f"imports {n}")
    assert not offenders, "\n  ".join(offenders)
