"""T5 — position sizing, symbol-agnostic.

Port of the WMPS sizer with three behavioural changes, each of which exists
because the original was measurably wrong.

1. **Refusal is a first-class outcome.** When one minimum position already
   risks more than the budget, this returns ``lots=0`` with
   ``MIN_POSITION_EXCEEDS_RISK_BUDGET``. The original rounded down to
   ``min_lot`` and traded anyway. Across the D8 grid that put 125 of 480 cells
   (26%) over their own budget, worst case 600% of account, and it is what put
   ``h1_momentum`` on a live schedule sizing positions a $100 account could not
   carry. A sizer with no way to say "not at this equity" will always say
   "minimum" instead, and that is the bug.

2. **Currency conversion is explicit and mandatory.** Risk is computed in the
   quote currency and converted to the account currency through a supplied
   rate provider. The registry's ``tick_value`` is deliberately not used: D1
   measured that it embeds the spot rate at capture time, so a snapshot pinned
   in January would size every JPY position against a January rate.

3. **The ATR floor is per-instrument, in tick units.** WMPS used a single
   ``LOT_SAFETY_FLOOR_ATR = 0.10``, a gold-shaped constant. 0.10 is ten ticks
   of gold and ten thousand ticks of EURUSD; as a universal floor it is either
   meaningless or catastrophic depending on the instrument.

Rounding is always **down**. Rounding to nearest crosses the budget that was
just computed, and doing so silently is how a 2% intention becomes 3%.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from resources.instruments.registry import InstrumentSpec

#: Numerical guard only — NOT a regime filter. Expressed in TICKS so it means
#: the same thing on every instrument, unlike WMPS's price-unit constant.
DEFAULT_ATR_FLOOR_TICKS = 10.0


class SizingReason(str, Enum):
    OK = "OK"
    MIN_POSITION_EXCEEDS_RISK_BUDGET = "MIN_POSITION_EXCEEDS_RISK_BUDGET"
    NON_POSITIVE_STOP = "NON_POSITIVE_STOP"
    NON_POSITIVE_BALANCE = "NON_POSITIVE_BALANCE"
    CAPPED_AT_VOLUME_MAX = "CAPPED_AT_VOLUME_MAX"


class FxRateProvider(Protocol):
    """Supplies quote-currency -> account-currency rates.

    A protocol rather than a concrete class so a backtest can pin historical
    rates and live trading can read current ones through the same call. Using
    a live rate in a backtest is a look-ahead bug that this shape makes
    visible instead of implicit.
    """

    def rate(self, quote_ccy: str, account_ccy: str) -> float:
        """Account-currency units per ONE unit of quote currency.

        Direction is stated explicitly because getting it backwards is
        silent: it produces a plausible lot size that is wrong by the square
        of the rate. For CHF->USD at USDCHF 0.81019 this returns 1.2343
        (one franc is 1.23 dollars), not 0.81019.
        """
        ...


@dataclass(frozen=True)
class StaticFxRates:
    """Fixed rates, for tests and for single-currency accounts."""

    rates: dict[tuple[str, str], float] = None  # type: ignore[assignment]

    def rate(self, quote_ccy: str, account_ccy: str) -> float:
        if quote_ccy == account_ccy:
            return 1.0
        table = self.rates or {}
        key = (quote_ccy, account_ccy)
        if key in table:
            return table[key]
        inverse = table.get((account_ccy, quote_ccy))
        if inverse:
            return 1.0 / inverse
        raise KeyError(
            f"no rate for {quote_ccy}->{account_ccy}. Sizing cannot proceed "
            f"without it: guessing a rate would silently mis-size every "
            f"position in this currency."
        )


@dataclass(frozen=True)
class PositionSize:
    lots: float
    risk_actual_ccy: float
    risk_actual_pct: float
    granularity_flag: bool
    reason: SizingReason
    effective_stop_distance: float
    fx_rate: float

    @property
    def tradable(self) -> bool:
        return self.lots > 0.0


def _refusal(reason: SizingReason, stop: float, fx: float = 1.0) -> PositionSize:
    return PositionSize(
        lots=0.0, risk_actual_ccy=0.0, risk_actual_pct=0.0,
        granularity_flag=reason is SizingReason.MIN_POSITION_EXCEEDS_RISK_BUDGET,
        reason=reason, effective_stop_distance=stop, fx_rate=fx,
    )


def effective_stop(spec: InstrumentSpec, stop_distance_price: float,
                   atr_floor_ticks: float = DEFAULT_ATR_FLOOR_TICKS) -> float:
    """Apply the per-instrument floor, in tick units.

    Pure numerical guard against a near-zero stop exploding the lot formula.
    It is not a volatility filter — that belongs in the strategy layer, where
    it can be configured per timeframe.
    """
    floor = atr_floor_ticks * spec.tick_size
    return max(stop_distance_price, floor)


def size_position(
    spec: InstrumentSpec,
    account_balance: float,
    account_ccy: str,
    risk_pct: float,
    stop_distance_price: float,
    fx_rate_provider: FxRateProvider,
    atr_floor_ticks: float = DEFAULT_ATR_FLOOR_TICKS,
) -> PositionSize:
    """Size a position to a risk budget, refusing when it cannot be met.

    The returned ``effective_stop_distance`` — not the raw one — is what the
    caller must use for SL placement. Sizing against the floored stop and
    placing against the raw one would reintroduce the risk the floor removed.
    """
    if account_balance <= 0:
        return _refusal(SizingReason.NON_POSITIVE_BALANCE, stop_distance_price)
    if not math.isfinite(stop_distance_price) or stop_distance_price <= 0:
        return _refusal(SizingReason.NON_POSITIVE_STOP, stop_distance_price)

    stop = effective_stop(spec, stop_distance_price, atr_floor_ticks)
    fx = fx_rate_provider.rate(spec.currency_profit, account_ccy)
    if fx <= 0:
        raise ValueError(f"fx rate must be > 0, got {fx}")

    budget = account_balance * risk_pct

    # Risk per lot, in the account currency. Derived from contract_size, never
    # from tick_value — see the module docstring.
    #
    # MULTIPLY: fx is account units per quote unit. A 500 CHF risk at
    # USDCHF 0.81019 is 500 * 1.2343 = 617 USD, not 500 / 1.2343 = 405.
    # Dividing here produced a plausible-looking lot size wrong by the square
    # of the rate, and was caught only by X9's hand-computed reference.
    risk_per_lot = spec.contract_size * stop * fx
    if risk_per_lot <= 0:
        return _refusal(SizingReason.NON_POSITIVE_STOP, stop, fx)

    raw_lots = budget / risk_per_lot
    lots = spec.round_to_lot_step(raw_lots)

    if lots == 0.0:
        # The minimum position already exceeds the budget. Say so; do not
        # round up to min_lot and trade it anyway.
        return _refusal(SizingReason.MIN_POSITION_EXCEEDS_RISK_BUDGET, stop, fx)

    risk_ccy = lots * risk_per_lot
    reason = (SizingReason.CAPPED_AT_VOLUME_MAX
              if raw_lots > spec.volume_max else SizingReason.OK)

    return PositionSize(
        lots=lots,
        risk_actual_ccy=risk_ccy,
        risk_actual_pct=risk_ccy / account_balance,
        granularity_flag=False,
        reason=reason,
        effective_stop_distance=stop,
        fx_rate=fx,
    )
