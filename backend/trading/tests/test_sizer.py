"""
Unit tests for app.quant.strategies.sizer

Tracks the v1.1 (revised) API:
  - calculate_lot_size() returns (lot_size, effective_atr).
  - The single v1.0 XAUUSD_MIN_ATR=5.0 constant was retired; the sizer now
    carries only a numerical safety floor, LOT_SAFETY_FLOOR_ATR, and the lot
    is floored to the step (math.floor), never rounded up.
"""

import pytest

from app.quant.strategies.sizer import (
    LOT_SAFETY_FLOOR_ATR,
    XAUUSD_MAX_LOT,
    XAUUSD_MIN_LOT,
    XAUUSD_POINT_VALUE_PER_LOT,
    calculate_lot_size,
)


def test_zero_balance_raises():
    with pytest.raises(ValueError, match="account_balance"):
        calculate_lot_size(account_balance=0.0, atr_value=10.0)


def test_negative_balance_raises():
    with pytest.raises(ValueError, match="account_balance"):
        calculate_lot_size(account_balance=-100.0, atr_value=10.0)


def test_zero_risk_pct_raises():
    with pytest.raises(ValueError, match="risk_pct"):
        calculate_lot_size(account_balance=1000.0, atr_value=10.0, risk_pct=0.0)


def test_negative_risk_pct_raises():
    with pytest.raises(ValueError, match="risk_pct"):
        calculate_lot_size(account_balance=1000.0, atr_value=10.0, risk_pct=-0.01)


def test_atr_below_floor_uses_safety_floor():
    # An ATR below LOT_SAFETY_FLOOR_ATR must be lifted to the floor for sizing,
    # so a near-zero ATR sizes identically to an ATR exactly at the floor and the
    # returned effective_atr is the floor (not the raw value).
    # balance=50, risk_pct=0.02 → risk_amount=1.0; floor=0.10, sl_mult=1.5 →
    # sl_distance=0.15; raw_lots = 1.0/(0.15*100)=0.0667 → floor to 0.06.
    result_tiny_atr = calculate_lot_size(account_balance=50.0, atr_value=0.01)
    result_floor_atr = calculate_lot_size(
        account_balance=50.0, atr_value=LOT_SAFETY_FLOOR_ATR
    )
    assert result_tiny_atr == result_floor_atr
    lots, effective_atr = result_tiny_atr
    assert effective_atr == LOT_SAFETY_FLOOR_ATR
    assert lots == pytest.approx(0.06, abs=1e-9)


def test_atr_above_floor_is_passed_through():
    # When ATR exceeds the safety floor it is used unchanged for sizing.
    _, effective_atr = calculate_lot_size(account_balance=5000.0, atr_value=12.5)
    assert effective_atr == 12.5


def test_result_never_exceeds_max_lot():
    # Very large balance, tiny ATR → without cap would be huge
    lots, _ = calculate_lot_size(
        account_balance=1_000_000.0,
        atr_value=50.0,
        risk_pct=0.10,
    )
    assert lots <= XAUUSD_MAX_LOT


def test_result_never_below_min_lot():
    # Very small balance → without floor would round to zero
    lots, _ = calculate_lot_size(
        account_balance=10.0,
        atr_value=50.0,
        risk_pct=0.01,
    )
    assert lots >= XAUUSD_MIN_LOT


def test_known_numeric_example():
    # balance=5000, risk_pct=0.02, atr=10.0, sl_mult=1.5
    # risk_amount=100, sl_distance=15, raw_lots=100/1500≈0.0667
    # → floored to lot_step (NOT rounded) → 0.06
    lots, effective_atr = calculate_lot_size(
        account_balance=5000.0,
        atr_value=10.0,
        risk_pct=0.02,
        sl_atr_multiplier=1.5,
        point_value_per_lot=XAUUSD_POINT_VALUE_PER_LOT,
    )
    assert lots == pytest.approx(0.06, abs=1e-9)
    assert effective_atr == 10.0


def test_result_clamped_to_max():
    # balance=10000, risk=5%, atr=10 → raw_lots=0.333 → floored 0.33 → clamp 0.10
    lots, _ = calculate_lot_size(
        account_balance=10000.0,
        atr_value=10.0,
        risk_pct=0.05,
        sl_atr_multiplier=1.5,
    )
    assert lots == XAUUSD_MAX_LOT


def test_result_rounded_to_two_decimal_places():
    lots, _ = calculate_lot_size(account_balance=1234.56, atr_value=8.7)
    # Verify result has at most 2 decimal places
    assert round(lots, 2) == lots


def test_custom_min_max_lot():
    lots, _ = calculate_lot_size(
        account_balance=100.0,
        atr_value=5.0,
        risk_pct=0.02,
        min_lot=0.05,
        max_lot=0.20,
    )
    assert 0.05 <= lots <= 0.20
