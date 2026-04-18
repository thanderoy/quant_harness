"""
ATR-based position sizing for XAUUSD on Pepperstone.

Risk model:
  risk_amount  = account_balance * risk_pct          (e.g. 0.02 for 2%)
  sl_distance  = atr_value * sl_atr_multiplier       (e.g. 1.5x ATR)
  raw_lots     = risk_amount / (sl_distance * point_value_per_lot)
  lots         = clamp(round(raw_lots, 2), min_lot, max_lot)
"""

XAUUSD_POINT_VALUE_PER_LOT = 100.0
XAUUSD_MIN_LOT = 0.01
XAUUSD_MAX_LOT = 0.10
XAUUSD_MIN_ATR = 5.0


def calculate_lot_size(
    account_balance: float,
    atr_value: float,
    risk_pct: float = 0.02,
    sl_atr_multiplier: float = 1.5,
    min_lot: float = XAUUSD_MIN_LOT,
    max_lot: float = XAUUSD_MAX_LOT,
    min_atr: float = XAUUSD_MIN_ATR,
    point_value_per_lot: float = XAUUSD_POINT_VALUE_PER_LOT,
) -> float:
    """
    Returns lot size rounded to 2dp, clamped between min_lot and max_lot.
    ATR is floored at min_atr before calculation.
    Raises ValueError if account_balance <= 0 or risk_pct <= 0.
    """
    if account_balance <= 0:
        raise ValueError(f"account_balance must be > 0, got {account_balance}")
    if risk_pct <= 0:
        raise ValueError(f"risk_pct must be > 0, got {risk_pct}")

    effective_atr = max(atr_value, min_atr)
    risk_amount = account_balance * risk_pct
    sl_distance = effective_atr * sl_atr_multiplier
    raw_lots = risk_amount / (sl_distance * point_value_per_lot)
    lots = round(raw_lots, 2)
    return max(min_lot, min(max_lot, lots))
