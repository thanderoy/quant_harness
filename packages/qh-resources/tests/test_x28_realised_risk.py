"""X28 — realised risk never exceeds budget. Plus X7, X8, X9 (T5 sizer).

X26 makes the *intended* risk single-sourced. X27 makes the drawdown guard
mandatory. Neither catches intended-correct, **realised**-wrong, which is the
D8 finding: once lots pin at ``volume_min`` the clamp stops bounding risk, and
125 of 480 WMPS grid cells (26%) breached their own budget, worst case 600% of
account. That is what put ``h1_momentum`` on a live schedule.

These exercise ``resources.risk.sizer.size_position`` — the production
function. An earlier draft of X28 tested a helper defined inside this file,
which proved the property held for code nothing calls.
"""

from __future__ import annotations

import itertools

import pytest

from resources.instruments import Registry
from resources.risk import (
    PositionSize,
    SizingReason,
    StaticFxRates,
    size_position,
)

#: Acceptance coverage (docs/REWRITE.md §7). Read by
#: tests/test_x_coverage.py — keep in step with what this file asserts.
pytestmark = [pytest.mark.x("X7"), pytest.mark.x("X8"), pytest.mark.x("X9"), pytest.mark.x("X26"), pytest.mark.x("X27"), pytest.mark.x("X28")]


REAL = "pepperstone_demo_20260901.json"
ACCOUNT_CCY = "USD"

# Rates at the D1 capture, so FX-quoted instruments size against something
# real rather than 1.0.
RATES = StaticFxRates({
    ("JPY", "USD"): 1 / 160.149,
    ("CHF", "USD"): 1 / 0.81019,
    ("CAD", "USD"): 1 / 1.38824,
})

BALANCES = (100.0, 500.0, 3_643.0, 10_000.0, 100_000.0)
RISK_PCTS = (0.005, 0.02, 0.05)
STOP_MULTS = (1.0, 1.5, 3.0, 10.0)
ATRS = (0.001, 0.05, 0.10, 0.5, 5.0, 14.0, 22.0, 60.0)


@pytest.fixture(scope="module")
def registry():
    return Registry.load(REAL)


def _size(spec, balance, risk_pct, stop) -> PositionSize:
    return size_position(spec, balance, ACCOUNT_CCY, risk_pct, stop, RATES)


# --------------------------------------------------------------------------- #
# X28 — the guarantee                                                          #
# --------------------------------------------------------------------------- #
def test_x28_realised_risk_never_exceeds_budget(registry):
    """Every cell either refuses or stays within budget. 1,440 cells."""
    breaches = []
    for symbol in registry.symbols:
        spec = registry[symbol]
        for balance, risk_pct, atr, mult in itertools.product(
                BALANCES, RISK_PCTS, ATRS, STOP_MULTS):
            r = _size(spec, balance, risk_pct, atr * mult)
            if not r.tradable:
                continue
            budget = balance * risk_pct
            if r.risk_actual_ccy > budget + 1e-9:
                breaches.append(
                    f"{symbol} bal={balance} risk={risk_pct} stop={atr * mult:.4f} "
                    f"lots={r.lots} realised={r.risk_actual_ccy:.2f} "
                    f"budget={budget:.2f} ({r.risk_actual_ccy / budget:.1%})")
    assert not breaches, (
        f"{len(breaches)} cells exceed budget:\n  " + "\n  ".join(breaches[:10]))


def test_x28_refusal_is_reachable(registry):
    """If nothing ever refuses, the guarantee above is vacuous."""
    r = _size(registry["XAUUSD"], 100.0, 0.02, 14.0 * 10)
    assert not r.tradable
    assert r.reason is SizingReason.MIN_POSITION_EXCEEDS_RISK_BUDGET
    assert r.granularity_flag


def test_x28_would_have_caught_h1_momentum(registry):
    """The exact configuration that was firing hourly on demo: 5%, 10xATR, $100."""
    xau = registry["XAUUSD"]
    for atr in (14.0, 22.0):
        r = _size(xau, 100.0, 0.05, atr * 10.0)
        assert not r.tradable, "must refuse, not clamp to min_lot"
        # What the old sizer did instead: take min_lot anyway.
        clamped = xau.volume_min * xau.contract_size * (atr * 10.0)
        assert clamped / 100.0 > 1.0


def test_x28_not_satisfied_by_refusing_everything(registry):
    r = _size(registry["XAUUSD"], 100_000.0, 0.02, 14.0)
    assert r.tradable and r.lots > 0
    assert r.risk_actual_ccy <= 100_000.0 * 0.02
    assert r.reason is SizingReason.OK


# --------------------------------------------------------------------------- #
# X7 — granularity                                                             #
# --------------------------------------------------------------------------- #
def test_x7_gold_at_100_usd_2pct_1p5_atr_refuses(registry):
    """Spec's named case. Median H1 gold ATR ~ $5.5 over the D2 window."""
    r = _size(registry["XAUUSD"], 100.0, 0.02, 1.5 * 5.5)
    assert r.lots == 0.0
    assert r.reason is SizingReason.MIN_POSITION_EXCEEDS_RISK_BUDGET


# --------------------------------------------------------------------------- #
# X8 — property-based risk ceiling                                             #
# --------------------------------------------------------------------------- #
def test_x8_randomised_sweep_never_exceeds_budget(registry):
    import random
    rng = random.Random(20260901)
    for _ in range(4000):
        spec = registry[rng.choice(registry.symbols)]
        balance = rng.uniform(50.0, 500_000.0)
        risk_pct = rng.uniform(0.001, 0.10)
        stop = rng.uniform(1e-5, 200.0)
        r = _size(spec, balance, risk_pct, stop)
        if r.tradable:
            assert r.risk_actual_ccy <= balance * risk_pct + 1e-9
            assert r.risk_actual_pct <= risk_pct + 1e-9


# --------------------------------------------------------------------------- #
# X9 — FX conversion against a hand-computed reference                         #
# --------------------------------------------------------------------------- #
def test_x9_usdjpy_matches_hand_computed_reference(registry):
    """USDJPY, $10,000 account, 2% budget, 0.5 JPY stop.

    By hand: risk per lot = 100,000 x 0.5 JPY = 50,000 JPY.
    At 160.149 JPY/USD that is 312.21 USD. Budget 200 USD.
    200 / 312.21 = 0.6406 lots -> rounds DOWN to 0.64.
    """
    r = _size(registry["USDJPY"], 10_000.0, 0.02, 0.5)
    assert r.lots == pytest.approx(0.64)
    assert r.risk_actual_ccy == pytest.approx(0.64 * 100_000 * 0.5 / 160.149,
                                              rel=1e-9)
    assert r.risk_actual_ccy < 200.0


def test_x9_usdchf_matches_hand_computed_reference(registry):
    """USDCHF, $10,000, 2%, 0.0050 CHF stop.

    risk per lot = 100,000 x 0.005 = 500 CHF = 617.14 USD at 0.81019.
    200 / 617.14 = 0.3241 -> 0.32 lots.
    """
    r = _size(registry["USDCHF"], 10_000.0, 0.02, 0.0050)
    assert r.lots == pytest.approx(0.32)
    assert r.risk_actual_ccy == pytest.approx(0.32 * 100_000 * 0.005 / 0.81019,
                                              rel=1e-9)


def test_x9_missing_rate_raises_rather_than_guessing(registry):
    """Guessing a rate would silently mis-size every position in that currency."""
    with pytest.raises(KeyError, match="no rate"):
        size_position(registry["USDJPY"], 10_000.0, "EUR", 0.02, 0.5,
                      StaticFxRates({}))


# --------------------------------------------------------------------------- #
# Guards and edges                                                             #
# --------------------------------------------------------------------------- #
def test_atr_floor_is_per_instrument_in_ticks(registry):
    """WMPS used a single 0.10 price-unit floor — ten gold ticks, ten thousand
    EURUSD ticks. In tick units it means the same thing everywhere."""
    eur, xau = registry["EURUSD"], registry["XAUUSD"]
    r_eur = _size(eur, 10_000.0, 0.02, 1e-9)
    r_xau = _size(xau, 10_000.0, 0.02, 1e-9)
    assert r_eur.effective_stop_distance == pytest.approx(10 * eur.tick_size)
    assert r_xau.effective_stop_distance == pytest.approx(10 * xau.tick_size)
    assert r_eur.effective_stop_distance != r_xau.effective_stop_distance


def test_non_positive_inputs_refuse_rather_than_raise(registry):
    xau = registry["XAUUSD"]
    assert _size(xau, 0.0, 0.02, 5.0).reason is SizingReason.NON_POSITIVE_BALANCE
    assert _size(xau, 100.0, 0.02, 0.0).reason is SizingReason.NON_POSITIVE_STOP
    assert _size(xau, 100.0, 0.02, -1.0).reason is SizingReason.NON_POSITIVE_STOP


def test_volume_max_cap_is_reported(registry):
    r = _size(registry["XAUUSD"], 1e12, 0.05, 1.0)
    assert r.lots == registry["XAUUSD"].volume_max
    assert r.reason is SizingReason.CAPPED_AT_VOLUME_MAX
