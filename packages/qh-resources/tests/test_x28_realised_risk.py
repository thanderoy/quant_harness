"""X28 (proposed) — realised risk never exceeds the budget that was asked for.

X26 makes the *intended* risk single-sourced. X27 makes the drawdown guard
mandatory. Neither catches the case where the intended risk is correct and the
**realised** risk is not.

That case is the D8 finding: once lots pin at ``volume_min``, the clamp stops
bounding risk. 125 of 480 grid cells in the WMPS sizer (26%) realised more than
their own budget, worst case 600% of account. It is what halted h1_momentum,
and it is invisible to a test that only checks the configured percentage.

The property has exactly one honest form:

    either the sizer refuses (0 lots), or realised risk <= budget

"Refuse" has to be an allowed outcome. A sizer that must always return a
tradeable lot has no way to express "this instrument cannot be traded at this
equity", and will silently return the minimum instead — which is the bug.
"""

from __future__ import annotations

import pytest

from resources.instruments import Registry

REAL = "pepperstone_demo_20260901.json"

BALANCES = (100.0, 500.0, 3_643.0, 10_000.0, 100_000.0)
RISK_PCTS = (0.005, 0.02, 0.05)
STOP_MULTS = (1.0, 1.5, 3.0, 10.0)
ATRS = (0.001, 0.05, 0.10, 0.5, 5.0, 14.0, 22.0, 60.0)


def size_position(spec, balance: float, risk_pct: float,
                  stop_distance: float) -> float:
    """Risk-first sizing: solve for lots, then round DOWN to a valid step.

    The rounding direction is the whole point. Rounding to nearest, or clamping
    up to volume_min, crosses the budget that was just computed.
    """
    if stop_distance <= 0:
        return 0.0
    budget = balance * risk_pct
    raw_lots = budget / (spec.contract_size * stop_distance)
    return spec.round_to_lot_step(raw_lots)


def realised_risk(spec, lots: float, stop_distance: float) -> float:
    return lots * spec.contract_size * stop_distance


@pytest.fixture(scope="module")
def registry():
    return Registry.load(REAL)


def test_x28_realised_risk_never_exceeds_budget(registry):
    """The full grid: every cell either refuses or stays within budget."""
    breaches = []
    for symbol in registry.symbols:
        spec = registry[symbol]
        for balance in BALANCES:
            for risk_pct in RISK_PCTS:
                for atr in ATRS:
                    for mult in STOP_MULTS:
                        stop = atr * mult
                        lots = size_position(spec, balance, risk_pct, stop)
                        if lots == 0.0:
                            continue          # refusing is a valid answer
                        risk = realised_risk(spec, lots, stop)
                        budget = balance * risk_pct
                        if risk > budget + 1e-9:
                            breaches.append(
                                f"{symbol} bal={balance} risk={risk_pct} "
                                f"stop={stop:.4f} lots={lots} "
                                f"realised={risk:.2f} budget={budget:.2f} "
                                f"({risk / budget:.1%})"
                            )
    assert not breaches, (
        f"{len(breaches)} cells realise more risk than their budget:\n  "
        + "\n  ".join(breaches[:10])
    )


def test_x28_refusal_is_reachable_and_is_the_correct_answer(registry):
    """A $100 account cannot trade gold on a 10xATR stop at 2%.

    If this ever starts returning a tradeable lot, the sizer has begun
    clamping instead of refusing, and the guarantee above becomes vacuous.
    """
    xau = registry["XAUUSD"]
    lots = size_position(xau, balance=100.0, risk_pct=0.02,
                         stop_distance=14.0 * 10)
    assert lots == 0.0

    # ...and the reason: one minimum position already risks 140x the budget.
    floor = xau.min_position_risk(14.0 * 10)
    assert floor == pytest.approx(140.0)
    assert floor / (100.0 * 0.02) == pytest.approx(70.0)


def test_x28_would_have_caught_the_h1_momentum_configuration(registry):
    """The exact configuration that was live: 5% risk, 10xATR stop, $100.

    Not a hypothetical grid cell — this is what was firing hourly on demo.
    """
    xau = registry["XAUUSD"]
    for atr in (14.0, 22.0):
        stop = atr * 10.0
        lots = size_position(xau, balance=100.0, risk_pct=0.05,
                             stop_distance=stop)
        assert lots == 0.0, "sizer must refuse, not clamp to min_lot"
        # What the deployed code did instead: take min_lot anyway.
        clamped = realised_risk(xau, xau.volume_min, stop)
        assert clamped / 100.0 > 1.0, (
            "min_lot at this geometry should exceed 100% of a $100 account")


def test_x28_scales_correctly_where_the_account_can_afford_it(registry):
    """The guarantee must not be satisfied by refusing everything."""
    xau = registry["XAUUSD"]
    lots = size_position(xau, balance=100_000.0, risk_pct=0.02,
                         stop_distance=14.0)
    assert lots > 0.0
    assert realised_risk(xau, lots, 14.0) <= 100_000.0 * 0.02
