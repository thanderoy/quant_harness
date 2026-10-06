"""
Unit tests for app.quant.strategies.sizer

The platform sizer is a thin adapter over ``resources.risk.size_position``
(Phase 3 step 4.3). These tests pin what the adapter adds — the pinned
snapshot, the account currency, the hard lot cap, the effective-ATR contract
and the configuration errors — and the one behaviour that changed on purpose:
refusing when the minimum position exceeds the budget (REWRITE.md T5, X7).
The arithmetic itself is tested in qh-resources.
"""

import json
from pathlib import Path

import pytest

from app.quant.strategies.sizer import (
    ACCOUNT_CCY,
    MAX_LOT,
    REGISTRY_SNAPSHOT,
    SizingReason,
    instrument,
    size_order,
)

SYMBOL = "XAUUSD"


def test_account_currency_matches_the_pinned_snapshot():
    import resources.instruments.registry as registry

    payload = json.loads(
        (Path(registry.SNAPSHOT_DIR) / REGISTRY_SNAPSHOT).read_text()
    )
    assert payload["account_currency"] == ACCOUNT_CCY


def test_xauusd_terms_come_from_the_snapshot():
    spec = instrument(SYMBOL)
    assert spec.contract_size == 100.0
    assert spec.volume_min == 0.01
    assert spec.volume_step == 0.01


def test_unpinned_symbol_raises():
    with pytest.raises(Exception, match="not in snapshot"):
        size_order("NOTASYMBOL", 1000.0, 10.0, 0.02, 1.5)


@pytest.mark.parametrize("kwargs, match", [
    (dict(risk_pct=0.0), "risk_pct"),
    (dict(risk_pct=-0.01), "risk_pct"),
    (dict(sl_atr_multiplier=0.0), "sl_atr_multiplier"),
    (dict(max_lot=0.0), "max_lot"),
])
def test_configuration_errors_raise(kwargs, match):
    args = dict(account_balance=1000.0, atr_value=10.0, risk_pct=0.02,
                sl_atr_multiplier=1.5)
    args.update(kwargs)
    with pytest.raises(ValueError, match=match):
        size_order(SYMBOL, **args)


def test_non_positive_balance_is_a_refusal_not_an_exception():
    sized = size_order(SYMBOL, 0.0, 10.0, 0.02, 1.5)
    assert not sized.tradable
    assert sized.reason is SizingReason.NON_POSITIVE_BALANCE


def test_x7_min_position_over_budget_is_refused():
    """$100, 2% budget, 1.5xATR(H1) stop. One 0.01 lot at a $15 stop risks
    $15, 7.5x the $2 budget. The old sizer clamped up to 0.01 and traded it."""
    sized = size_order(SYMBOL, 100.0, 10.0, 0.02, 1.5)
    assert sized.lots == 0.0
    assert sized.reason is SizingReason.MIN_POSITION_EXCEEDS_RISK_BUDGET
    assert sized.risk_actual_pct == 0.0


def test_known_value_and_floor_rounding():
    # $5,000 x 2% = $100 budget; stop 1.5 x 12.5 = $18.75; per lot $1,875.
    # raw 0.0533 -> floored to 0.05, never rounded up to 0.06.
    sized = size_order(SYMBOL, 5000.0, 12.5, 0.02, 1.5)
    assert sized.lots == 0.05
    assert sized.reason is SizingReason.OK
    assert sized.effective_atr == pytest.approx(12.5)
    assert sized.risk_actual_pct == pytest.approx(0.05 * 1875.0 / 5000.0)
    assert sized.risk_actual_pct <= 0.02


def test_hard_cap_holds_and_lowers_risk():
    sized = size_order(SYMBOL, 1_000_000.0, 10.0, 0.02, 1.5)
    assert sized.lots == MAX_LOT
    assert sized.capped
    assert sized.risk_actual_pct < 0.02


def test_custom_cap_is_respected():
    sized = size_order(SYMBOL, 1_000_000.0, 10.0, 0.02, 1.5, max_lot=0.05)
    assert sized.lots == 0.05


def test_effective_atr_carries_the_floor():
    """The stop is floored at 10 ticks ($0.10). The caller places SL/TP from
    effective_atr, so it must reflect the floored stop, not the raw ATR."""
    sized = size_order(SYMBOL, 1000.0, 0.01, 0.02, 1.0)
    assert sized.position.effective_stop_distance == pytest.approx(0.10)
    assert sized.effective_atr == pytest.approx(0.10)


@pytest.mark.parametrize("balance", [100.0, 600.0, 1234.56, 3643.0, 10_000.0])
@pytest.mark.parametrize("atr_value", [0.5, 6.0, 9.72, 19.9, 45.0])
@pytest.mark.parametrize("risk_pct", [0.005, 0.02, 0.05])
def test_either_refuses_or_stays_within_budget(balance, atr_value, risk_pct):
    """REWRITE.md's one honest form of the property."""
    sized = size_order(SYMBOL, balance, atr_value, risk_pct, 1.5)
    assert (not sized.tradable) or sized.risk_actual_pct <= risk_pct + 1e-12
