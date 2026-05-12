"""
ATR-based position sizing for XAUUSD on Pepperstone.

v1.1 changes (REVISED -- supersedes the first v1.1):
  - Conceptually separates two distinct concerns that v1.0 conflated:

        1. SIGNAL-LEVEL ATR FILTER (in strategy.py)
           "Don't trade in dead-quiet regimes." Strategy-level decision.
           Configurable per timeframe, per strategy.

        2. SIZER-LEVEL ATR FLOOR (here)
           "Defend the lot calculation against pathological near-zero ATRs."
           Pure numerical safety net. Should be small.

    v1.0 used a single XAUUSD_MIN_ATR=5.0 constant for both purposes which
    (a) silently distorts H1 sizing in normal vol regimes and
    (b) makes the M15 trade-skip filter look like a sizer concern.

  - Sizer floor is now `LOT_SAFETY_FLOOR_ATR = 0.10` (a near-zero guard,
    not a regime filter). At this level a $1 risk on a $1.5/oz stop = 0.067
    raw lots, well within sane bounds.

  - calculate_lot_size() returns (lot_size, effective_atr) so the caller
    can use the SAME ATR for both sizing AND SL placement, eliminating the
    v1.0 inconsistency.

  - math.floor used instead of round() for clean step-down to lot_step.

Risk model (unchanged conceptually):
  risk_amount   = account_balance * risk_pct
  effective_atr = max(atr_value, LOT_SAFETY_FLOOR_ATR)   # safety only
  sl_distance   = effective_atr * sl_atr_multiplier
  raw_lots      = risk_amount / (sl_distance * point_value_per_lot)
  lots          = floor_to_step(raw_lots, lot_step), clamped [min_lot, max_lot]

The CALLER is responsible for any signal-level ATR filtering BEFORE
calling this. See strategy_patch_*_v1_1_revised.txt.
"""

import math
from typing import Tuple

XAUUSD_POINT_VALUE_PER_LOT = 100.0  # 1 lot = 100 oz
XAUUSD_MIN_LOT = 0.01
XAUUSD_MAX_LOT = 0.10
XAUUSD_LOT_STEP = 0.01

# Pure numerical safety floor: stops the lot formula from exploding when
# ATR is anomalously near zero. Not a strategy decision.
LOT_SAFETY_FLOOR_ATR = 0.10


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
    """
    Returns (lot_size, effective_atr).

    The caller MUST use `effective_atr` (not the raw `atr_value`) when
    computing SL/TP distances, otherwise the sizer's risk-per-trade
    estimate diverges from what the broker actually executes.

    `safety_floor_atr` is a numerical guard only (default 0.10 USD/oz).
    It exists to prevent division by tiny ATR values exploding the lot
    formula. Use a strategy-level signal filter for regime decisions.

    Lot size is floored to lot_step and clamped between min_lot and max_lot.

    Raises:
        ValueError if account_balance <= 0 or risk_pct <= 0 or invalid bounds.
    """
    if account_balance <= 0:
        raise ValueError(f"account_balance must be > 0, got {account_balance}")
    if risk_pct <= 0:
        raise ValueError(f"risk_pct must be > 0, got {risk_pct}")
    if min_lot <= 0 or max_lot < min_lot:
        raise ValueError(f"invalid lot bounds: min={min_lot}, max={max_lot}")
    if safety_floor_atr <= 0:
        raise ValueError(f"safety_floor_atr must be > 0, got {safety_floor_atr}")

    effective_atr = max(atr_value, safety_floor_atr)
    risk_amount = account_balance * risk_pct
    sl_distance = effective_atr * sl_atr_multiplier
    raw_lots = risk_amount / (sl_distance * point_value_per_lot)

    # Floor to lot_step (never round up past max_lot).
    stepped = math.floor(raw_lots / lot_step) * lot_step
    lots = max(min_lot, min(max_lot, round(stepped, 2)))
    return lots, effective_atr
