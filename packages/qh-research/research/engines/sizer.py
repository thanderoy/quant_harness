"""research.engines.sizer — position sizer for backtesting.py strategies.

Mirrors the v1.1 sizer logic (sizer_v1_1_revised.py) used in the live
strategies. Kept here as a standalone module so the engine layer has no
dependency on the live-trading app.

Key v1.1 change: returns (lot_size, effective_atr) together so the caller
can use the SAME effective_atr for both sizing and SL/TP placement.
"""

from __future__ import annotations

import math
from typing import Tuple

XAUUSD_POINT_VALUE_PER_LOT = 100.0   # oz per lot
XAUUSD_MIN_LOT = 0.01
XAUUSD_MAX_LOT = 0.10
XAUUSD_LOT_STEP = 0.01
LOT_SAFETY_FLOOR_ATR = 0.10           # numerical guard only, not a regime filter


def calculate_lot_size(
    account_balance: float,
    atr_value: float,
    risk_pct: float = 0.02,
    sl_atr_multiplier: float = 1.5,
    min_lot: float = XAUUSD_MIN_LOT,
    max_lot: float = XAUUSD_MAX_LOT,
    lot_step: float = XAUUSD_LOT_STEP,
    safety_floor_atr: float = LOT_SAFETY_FLOOR_ATR,
    point_value_per_lot: float = XAUUSD_POINT_VALUE_PER_LOT,
) -> Tuple[float, float]:
    """Return (lot_size, effective_atr).

    The caller MUST use `effective_atr` for SL/TP distances, not raw
    `atr_value`, to keep the sizer and broker SL in sync.
    """
    if account_balance <= 0:
        raise ValueError(f"account_balance must be > 0, got {account_balance}")
    if risk_pct <= 0:
        raise ValueError(f"risk_pct must be > 0, got {risk_pct}")

    effective_atr = max(atr_value, safety_floor_atr)
    risk_amount = account_balance * risk_pct
    sl_distance = effective_atr * sl_atr_multiplier
    raw_lots = risk_amount / (sl_distance * point_value_per_lot)

    stepped = math.floor(raw_lots / lot_step) * lot_step
    lots = max(min_lot, min(max_lot, round(stepped, 2)))
    return lots, effective_atr
