"""Position sizing for the live app — `resources.risk.sizer` plus a hard cap.

This module used to carry its own XAUUSD-hardcoded sizer,
``calculate_lot_size()``. Phase 3 step 4.3 replaces it with
``resources.risk.size_position`` reading the pinned broker snapshot, so the
live app and the backtester size a position with one piece of arithmetic.
What stays here is what is genuinely the platform's: which snapshot is
pinned, the account currency, and the hard lot ceiling CLAUDE.md rule 5
requires of every strategy.

**This changes live behaviour in one way, deliberately.** The old sizer
clamped up to ``min_lot`` when the minimum position already exceeded the risk
budget, and traded it. ``resources`` refuses instead: ``lots == 0`` with
``MIN_POSITION_EXCEEDS_RISK_BUDGET``. That is REWRITE.md T5's ruling, made
before any data — "silently trading an oversized position is the current
behaviour and is a live risk bug" — and X7 asserts it. Measured at step 4.3
on H1 gold since 2025, at crest_n_keel's own 0.5% / 1.5xATR geometry, it
refuses every signal below a ~$1,000 balance and 34.8% at the $3,643 demo
balance. Each of those is a signal the old sizer would have placed at more
than its budget.

**One other difference exists and cannot be reached on gold.** The old floor
was ``max(atr, 0.10)`` applied before the stop multiplier; ``resources``
floors the *stop* at 10 ticks (also $0.10 for XAUUSD) after it. They differ
only when ATR(14) < $0.10. Across 650,769 bars of XAUUSD H1, H4 and M15
history the lowest ATR(14) is $0.14 (M15) and $0.47 (H1), so no bar has ever
been in that region.

Over a 4,080-cell grid every other cell is identical in both lot size and
effective ATR, and no tradable cell realises more than its budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from resources.instruments.registry import InstrumentSpec, Registry
from resources.risk.sizer import (
    FxRateProvider,
    PositionSize,
    SizingReason,
    StaticFxRates,
    size_position,
)

#: The broker snapshot every live size is computed against. Pinned rather than
#: read from a running terminal so the record of which broker answered is the
#: file itself — see CLAUDE.md rule 6 on how a MetaQuotes dump was once filed
#: as a Pepperstone one.
REGISTRY_SNAPSHOT = "pepperstone_live_20260906.json"

#: Account currency of the pinned account. A test asserts it matches the
#: snapshot's own `account_currency`.
ACCOUNT_CCY = "USD"

#: Hard lot ceiling (CLAUDE.md rule 5). `resources` caps only at the broker's
#: `volume_max` (50 lots for XAUUSD), which is not a safety limit for a small
#: account. Capping lowers realised risk; it can never raise it.
MAX_LOT = 0.10

__all__ = [
    "ACCOUNT_CCY", "MAX_LOT", "REGISTRY_SNAPSHOT",
    "SizedOrder", "SizingReason", "instrument", "size_order",
]


@dataclass(frozen=True)
class SizedOrder:
    """What a strategy needs to place, or decline, one order.

    ``effective_atr`` is the ATR the stop was actually sized against. The
    caller must use it, not the raw ATR, for SL and TP — sizing against one
    distance and placing against another reintroduces the risk the floor
    removed.

    ``position`` is the uncapped `resources` result, kept for its reason and
    fx rate. When ``capped`` is true its risk fields describe the uncapped
    size; use ``risk_actual_pct`` here instead.
    """

    lots: float
    effective_atr: float
    risk_actual_pct: float
    capped: bool
    position: PositionSize

    @property
    def tradable(self) -> bool:
        return self.lots > 0.0

    @property
    def reason(self) -> SizingReason:
        return self.position.reason


@lru_cache(maxsize=1)
def _registry() -> Registry:
    return Registry.load(REGISTRY_SNAPSHOT)


def instrument(symbol: str) -> InstrumentSpec:
    """The pinned contract terms for ``symbol``; raises if it is not pinned."""
    return _registry()[symbol]


def size_order(
    symbol: str,
    account_balance: float,
    atr_value: float,
    risk_pct: float,
    sl_atr_multiplier: float,
    max_lot: float = MAX_LOT,
    fx_rates: FxRateProvider | None = None,
) -> SizedOrder:
    """Size one order, refusing when the minimum position exceeds the budget.

    Raises ``ValueError`` for a non-positive ``risk_pct``, multiplier or cap,
    as the old sizer did: those are configuration errors, not market states,
    and refusing would hide them. A non-positive balance or stop is a market
    state and comes back as a refusal with its reason.
    """
    if risk_pct <= 0:
        raise ValueError(f"risk_pct must be > 0, got {risk_pct}")
    if sl_atr_multiplier <= 0:
        raise ValueError(f"sl_atr_multiplier must be > 0, got {sl_atr_multiplier}")
    if max_lot <= 0:
        raise ValueError(f"max_lot must be > 0, got {max_lot}")

    spec = instrument(symbol)
    position = size_position(
        spec, account_balance, ACCOUNT_CCY, risk_pct,
        atr_value * sl_atr_multiplier, fx_rates or StaticFxRates(),
    )
    effective_atr = position.effective_stop_distance / sl_atr_multiplier

    lots = position.lots
    capped = lots > max_lot
    if capped:
        lots = spec.round_to_lot_step(max_lot)

    risk_pct_actual = (
        lots * spec.contract_size * position.effective_stop_distance
        * position.fx_rate / account_balance
        if lots > 0 else 0.0
    )
    return SizedOrder(
        lots=lots,
        effective_atr=effective_atr,
        risk_actual_pct=risk_pct_actual,
        capped=capped,
        position=position,
    )
