"""
Unit tests for app.quant.strategies.sizer
"""
import pytest

from app.quant.strategies.sizer import (
    XAUUSD_MAX_LOT,
    XAUUSD_MIN_ATR,
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


def test_atr_below_floor_uses_floor():
    # When atr < min_atr, sizer should use min_atr, not raw atr
    # balance=5000, risk_pct=0.02, atr_floor=5.0, sl_mult=1.5
    # risk_amount = 5000 * 0.02 = 100
    # sl_distance = 5.0 * 1.5 = 7.5  (floor, not raw 2.0)
    # raw_lots = 100 / (7.5 * 100) = 100/750 ≈ 0.1333 → rounds to 0.13
    # clamped to max_lot = 0.10
    result_low_atr = calculate_lot_size(account_balance=5000.0, atr_value=2.0)
    result_floor_atr = calculate_lot_size(account_balance=5000.0, atr_value=XAUUSD_MIN_ATR)
    assert result_low_atr == result_floor_atr


def test_result_never_exceeds_max_lot():
    # Very large balance, tiny ATR → without cap would be huge
    result = calculate_lot_size(
        account_balance=1_000_000.0,
        atr_value=50.0,
        risk_pct=0.10,
    )
    assert result <= XAUUSD_MAX_LOT


def test_result_never_below_min_lot():
    # Very small balance → without floor would round to zero
    result = calculate_lot_size(
        account_balance=10.0,
        atr_value=50.0,
        risk_pct=0.01,
    )
    assert result >= XAUUSD_MIN_LOT


def test_known_numeric_example():
    # balance=5000, risk_pct=0.02, atr=10.0, sl_mult=1.5
    # risk_amount = 100, sl_distance = 15, raw_lots = 100/1500 ≈ 0.0667 → 0.07
    result = calculate_lot_size(
        account_balance=5000.0,
        atr_value=10.0,
        risk_pct=0.02,
        sl_atr_multiplier=1.5,
        point_value_per_lot=XAUUSD_POINT_VALUE_PER_LOT,
    )
    assert result == pytest.approx(0.07, abs=1e-9)


def test_result_clamped_to_max():
    # balance=10000, risk=5%, atr=10 → raw_lots=0.333 → rounded 0.33 → clamped to 0.10
    result = calculate_lot_size(
        account_balance=10000.0,
        atr_value=10.0,
        risk_pct=0.05,
        sl_atr_multiplier=1.5,
    )
    assert result == XAUUSD_MAX_LOT


def test_result_rounded_to_two_decimal_places():
    result = calculate_lot_size(account_balance=1234.56, atr_value=8.7)
    # Verify result has at most 2 decimal places
    assert round(result, 2) == result


def test_custom_min_max_lot():
    result = calculate_lot_size(
        account_balance=100.0,
        atr_value=5.0,
        risk_pct=0.02,
        min_lot=0.05,
        max_lot=0.20,
    )
    assert 0.05 <= result <= 0.20
