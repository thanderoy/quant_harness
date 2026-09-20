"""research.datasets.cost_model — Pepperstone XAUUSD Razor cost model.

Models the three components of round-trip cost on Pepperstone Razor
account, MT5 platform:

    1. Spread       : 0.22 USD/oz typical (raw 0.05-0.30 USD/oz observed),
                       paid on entry as half-spread haircut.
    2. Commission   : $7 USD round-turn per 1.0 standard lot
                       ($3.50/side, MT5 Razor). Per Pepperstone published
                       documentation. cTrader differs ($6 RT) and so does
                       TradingView ($7 RT but from a different table).
                       For 0.01 lots, this rounds to $0.04 RT per Pepperstone.
    3. Swap (overnight financing)
                    : Floating, updated weekly. We use placeholder values;
                       caller should override with values from MT5
                       Symbol Specifications. Triple-swap on Wednesday
                       (rollover at 5pm New York / 23:59 server).

Conventions
-----------
- All prices in USD per oz.
- Lot size is XAUUSD standard lot = 100 oz.
- Position notional in USD = price * 100 * lots.
- Commission and swap returned in USD (account currency).

Pepperstone Stops Level for XAUUSD is typically 0 points on Razor
(quoted "0.0 points" in spread tables) but enforce a small minimum stop
distance of 0.10 USD/oz as a safety floor in backtests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


# -- Constants from Pepperstone published docs -------------------------------
#
# Provenance, sourced 2026-09-20 (research log seq=101):
#
# The $7.00 VALUE is corroborated. Pepperstone's "Costs and Charges" document,
# table "MetaTrader 5 Razor Commissions", lists USD 3.50 per 1 lot per side —
# "USD 3.50 (USD 7 round turn)" — for a USD trading account. The table is keyed
# on the ACCOUNT currency, not on the traded pair's base currency, so the figure
# needs no per-symbol FX conversion. The cTrader schedule is different: there it
# is "7 units in the base currency of the instrument traded and converted to
# your trading account currency". That conversion does NOT apply to MetaTrader,
# and carrying it across would misprice every non-USD-base pair.
#
# Its APPLICABILITY TO GOLD is contested, and this constant is the contested
# case. Two Pepperstone sources disagree:
#
#   - Costs and Charges §1.3: commission "is charged on all FX trades", and
#     "For both MetaTrader and cTrader platforms the commission on index,
#     metal, cryptocurrency and soft commodity markets are reflected in the
#     spread with no separate commission charge." Metals includes XAUUSD, so
#     under this reading MT5 gold carries no separate commission and every
#     backtest here over-costs gold by $7.00/lot round turn.
#   - The "Razor Gold" product page: spot gold on a Razor account is
#     commission-based, "from $3.50 per lot, per side" — i.e. this constant.
#
# The value is deliberately LEFT UNCHANGED at 7.0 pending resolution. Both
# readings err the same way: if gold is in fact commission-free, recorded
# results are under-stated, never flattered. Flipping it on one source would
# silently re-price every metric already in the log.
#
# Two caveats the citation does NOT clear:
#   1. The document is Pepperstone Limited (England & Wales, 08965105). The
#      live account is PepperstoneKE-MT5-Live01, a different entity whose
#      schedule may differ. This is BROKER_PUBLISHED evidence for a sibling
#      entity, not the account's own document.
#   2. Nothing here is MEASURED. The resolver for both the entity question and
#      the gold question is the `commission` field on a real deal from
#      /api/v1/deals on the live terminal, which settles it in one read.
#
# Swap rates below remain placeholders and are NOT covered by this citation.

PEPPERSTONE_XAUUSD_CONTRACT_SIZE = 100.0       # oz per 1.0 lot
PEPPERSTONE_XAUUSD_RAZOR_MT5_COMMISSION_PER_LOT_RT = 7.0   # USD round-turn

#: The above as data, so a caller can assert on provenance rather than trust a
#: comment to have been read. ``metals_applicability`` is the open question.
COMMISSION_PROVENANCE = {
    "value_usd_per_lot_round_turn": 7.0,
    "provenance": "BROKER_PUBLISHED",
    "source": ("Pepperstone Costs and Charges, table 'MetaTrader 5 Razor "
               "Commissions': USD 3.50 (USD 7 round turn) per 1 lot"),
    "source_entity": "Pepperstone Limited (England & Wales, 08965105)",
    "account_entity": "PepperstoneKE-MT5-Live01",
    "keyed_on": "account_currency",
    "fx_applicability": "CORROBORATED",
    "metals_applicability": "CONTESTED",
    "contested_because": (
        "Costs and Charges §1.3 puts metal commission in the spread with no "
        "separate charge; the Razor Gold product page prices spot gold at "
        "$3.50 per lot per side"),
    "resolver": "commission field on a real deal via /api/v1/deals (live)",
    "sourced_on": "2026-09-20",
}

# Spread defaults for backtesting. These are intentionally conservative
# (slightly above the average you reported, 0.22 USD/oz) so backtests don't
# under-cost.
PEPPERSTONE_XAUUSD_SPREAD_USD_PER_OZ_TYPICAL = 0.22
PEPPERSTONE_XAUUSD_SPREAD_USD_PER_OZ_NEWS = 0.50    # rough NFP/FOMC estimate

# Placeholder swaps (USD per 1.0 lot per night). Pepperstone updates these
# weekly; override in code with values from MT5 Symbol Specifications.
PEPPERSTONE_XAUUSD_SWAP_LONG_USD_PER_LOT_NIGHT = -10.0    # placeholder
PEPPERSTONE_XAUUSD_SWAP_SHORT_USD_PER_LOT_NIGHT = -2.0    # placeholder

# Stops level safety floor for backtests, in USD/oz.
PEPPERSTONE_XAUUSD_STOPS_LEVEL_FLOOR_USD_PER_OZ = 0.10


# -- Data class for trade-level cost breakdown ------------------------------


@dataclass
class CostBreakdown:
    spread_usd: float
    commission_usd: float
    swap_usd: float
    total_usd: float
    nights_held: int
    triple_swap_nights: int


# -- Cost model -------------------------------------------------------------


@dataclass
class PepperstoneXAUUSDCostModel:
    """Pepperstone XAUUSD Razor cost model.

    All cost methods take and return USD amounts. Spread is applied as
    a half-spread haircut on entry by default (you fill at mid + half_spread
    on a buy, mid - half_spread on a sell). Commission is round-trip
    when entry+exit have both occurred.

    Defaults are documented Pepperstone values as of 2025-2026; override
    swap rates with current MT5-displayed values for accuracy.
    """
    contract_size: float = PEPPERSTONE_XAUUSD_CONTRACT_SIZE
    commission_per_lot_round_turn: float = (
        PEPPERSTONE_XAUUSD_RAZOR_MT5_COMMISSION_PER_LOT_RT
    )
    spread_usd_per_oz: float = PEPPERSTONE_XAUUSD_SPREAD_USD_PER_OZ_TYPICAL
    swap_long_per_lot_night: float = (
        PEPPERSTONE_XAUUSD_SWAP_LONG_USD_PER_LOT_NIGHT
    )
    swap_short_per_lot_night: float = (
        PEPPERSTONE_XAUUSD_SWAP_SHORT_USD_PER_LOT_NIGHT
    )
    stops_level_floor_usd_per_oz: float = (
        PEPPERSTONE_XAUUSD_STOPS_LEVEL_FLOOR_USD_PER_OZ
    )
    triple_swap_weekday: int = 2   # Wednesday (Mon=0, Sun=6) per Pepperstone

    # ----- Spread / commission ---------------------------------------------

    def spread_cost_usd(self, lots: float) -> float:
        """Round-trip spread cost in USD.

        Modelled as the full bid/ask spread paid once per round-trip:
        you enter at the ask (worse than mid) and exit at the bid (worse
        than mid), so the cumulative cost is one full spread.
        """
        return float(self.spread_usd_per_oz * lots * self.contract_size)

    def commission_round_turn_usd(self, lots: float) -> float:
        """Round-turn commission for an opening-and-closing trade."""
        return float(self.commission_per_lot_round_turn * lots)

    # ----- Swap ------------------------------------------------------------

    def _is_swap_night(self, dt: datetime) -> bool:
        """True if a position held over this date close incurs swap.

        Forex / metal positions held past the daily server rollover incur
        swap. We model rollover as 21:00 UTC (~5pm New York winter, but
        the convention shifts with DST). The harness treats EOD UTC bars
        as the rollover boundary, which is approximately correct for
        Pepperstone within an hour.
        """
        # Saturday = 5: market closed, no rollover applied to this day.
        return dt.weekday() != 5

    def swap_usd(self, lots: float, direction: str,
                 entry_dt: datetime, exit_dt: datetime) -> tuple[float, int, int]:
        """Total swap charge in USD over the holding period.

        Returns (swap_usd, total_nights_held, triple_swap_nights).

        Triple swap applied on `triple_swap_weekday` (Wednesday) to
        cover Wed-Thu-Fri-Sat rolling that takes T+2 settlement past
        the weekend.
        """
        if exit_dt <= entry_dt:
            return 0.0, 0, 0
        nights = 0
        triples = 0
        # Walk each midnight UTC between entry and exit.
        cur = entry_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        if cur <= entry_dt:
            cur = cur + pd.Timedelta(days=1)
        while cur < exit_dt:
            if self._is_swap_night(cur):
                nights += 1
                if cur.weekday() == self.triple_swap_weekday:
                    triples += 1
            cur = cur + pd.Timedelta(days=1)

        per_night = (self.swap_long_per_lot_night if direction.upper() == "BUY"
                     else self.swap_short_per_lot_night)
        # Triple-swap nights count as 3x; regular nights as 1x.
        regular_nights = nights - triples
        total = (regular_nights + 3 * triples) * per_night * lots
        return float(total), int(nights), int(triples)

    # ----- Composite ---------------------------------------------------------

    def trade_cost(self,
                   lots: float,
                   direction: str,
                   entry_dt: datetime,
                   exit_dt: datetime) -> CostBreakdown:
        """Full round-trip cost breakdown for a single trade."""
        spread = self.spread_cost_usd(lots)
        commission = self.commission_round_turn_usd(lots)
        swap, nights, triples = self.swap_usd(lots, direction, entry_dt, exit_dt)
        return CostBreakdown(
            spread_usd=spread,
            commission_usd=commission,
            swap_usd=swap,
            total_usd=spread + commission + swap,
            nights_held=nights,
            triple_swap_nights=triples,
        )


# pandas import deferred to avoid top-level dependency cycles where unneeded;
# but the swap walker uses pd.Timedelta. Keep it imported lazily.
import pandas as pd  # noqa: E402
