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
from enum import Enum
from datetime import datetime
from typing import Optional

from resources.execution import SlipModel


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

#: MEASURED 2026-09-20 (seq=105) — and it does not match the constant.
#:
#: The resolver named below was finally run: every deal on the live account,
#: `/api/v1/deals` on PepperstoneKE-MT5-Live01. **358 trade deals across five
#: symbols over fourteen months carry commission exactly 0.00.** Not gold
#: alone — EURUSD, GBPUSD, AUDUSD and NZDUSD too, where the published Razor
#: schedule is unambiguous.
#:
#: It is not a reporting artifact:
#:   - ``swap`` is populated on 24 of the same deals, so the field plumbing
#:     from MT5 works;
#:   - twelve deals are 0.03 lots, where a Razor charge would be $0.105 a
#:     side — far too large to round to 0.00 at two decimal places;
#:   - both DEAL_ENTRY_IN and DEAL_ENTRY_OUT legs are present, 179 each, so
#:     commission is not simply being booked on the other side.
#:
#: The conclusion is about the ACCOUNT, not the instrument: this one pays no
#: separate commission on anything, which is what a Standard account does —
#: the cost is in a marked-up spread instead. That also dissolves the gold
#: dispute below, which is a Razor-only question and moot here.
#:
#: **The constant is still 7.0 and this is now a known over-cost.** Zeroing it
#: would improve every metric already recorded, which is the direction that
#: deserves the most scrutiny, and it is only half the change: the D3b spread
#: (XAUUSD median 0.17 USD/oz over 117M ticks) is measured from this same
#: account and therefore already carries whatever markup pays for the missing
#: commission, while backtests use the assumed 0.22. Setting commission to
#: zero without settling which spread the model should use would under-cost
#: rather than correct. That pairing is a decision for the user, recorded at
#: seq=105 rather than taken here.
COMMISSION_MEASURED = {
    "measured_usd_per_lot_round_turn": 0.0,
    "provenance": "MEASURED",
    "source": "/api/v1/deals on PepperstoneKE-MT5-Live01",
    "measured_on": "2026-09-20",
    "n_trade_deals": 358,
    "symbols": ["XAUUSD", "EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"],
    "span": "2025-02-10 .. 2026-04-13",
    "non_zero_commission_deals": 0,
    "non_zero_swap_deals": 24,
    "largest_lot": 0.03,
    "implies_account_type": "Standard (no separate commission)",
    "constant_unchanged": True,
    "why_unchanged": ("zeroing it flatters every recorded metric and is only "
                      "half the change — the measured spread that would pay "
                      "for it is 0.17 USD/oz where the model assumes 0.22"),
}

#: The published schedule, kept because it is what the constant still encodes.
#: Superseded as a description of THIS account by COMMISSION_MEASURED above.
COMMISSION_PROVENANCE = {
    "value_usd_per_lot_round_turn": 7.0,
    "provenance": "BROKER_PUBLISHED",
    "superseded_by": "COMMISSION_MEASURED (seq=105)",
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

# -- Slip / execution cost per fill -----------------------------------------
#
# Slip was the last cost input with no source: ``SlipModel`` charges one tick,
# provenance HAND_ENTERED. Measured 2026-10-11 from the same account and the
# same 358 trade deals as COMMISSION_MEASURED, using the tick quotes around
# each fill (phase0.collectors.execution_fills -> research.datasets.
# execution_cost; aggregate artifact phase0/execution_cost_20261011.json).
#
# Method. A deal carries the fill price but not the requested price, so classic
# slip (fill - requested) is unavailable. Each fill is compared instead with
# the tick quote around it, signed by side (positive = adverse):
#
#   slip_vs_touch  = side * (fill - touch)      ask for a buy, bid for a sell
#   cost_vs_mid    = side * (fill - mid)        half spread + slip, per side
#
# against two quotes that bracket the fill, because /api/v1/ticks resolves time
# only to the second: ``same_second`` (last tick in the fill's own second —
# closest in time, may postdate the fill) and ``pre`` (last tick in a strictly
# earlier second — unambiguously before it, ~1 s stale at the median).
#
# Entry-conditional (R7): IN legs only, 179 of the 358. Exits (TP/SL/stop-out
# fills) are a different mechanism and are in the artifact, not here.
#
# Which quote is primary. ``same_second`` — chosen AFTER seeing both, for a
# mechanical reason: on XAUUSD the ``pre`` estimator differs by who sent the
# order (EXPERT median -27 ticks, MOBILE 0), which a broker execution property
# cannot do. It is 1-2 s of price drift correlated with the entry direction of
# the strategies that traded, not slip. ``pre`` is kept as the bracket.
#
# Clock alignment, verified not assumed: deal ``time_msc`` and tick/bar times
# are compared with no offset. 98.5% of fills lie inside the admitted M5 bar
# containing them at offset 0, against 7-19% at every offset in +/-1..3 h; and
# the XAUUSD same-second slip has median -0.5 ticks, p75 +1 tick, which a
# mis-clocked quote could not produce.
#
# What it measures and what it does not:
#   - Slip past the touch at FILL time. Drift between the request and the fill
#     is in it only inside the one-second tick resolution. Latency before that
#     is not measured, because the request price is not recorded anywhere.
#   - The M5 fill-vs-bar cross-check (bid bars; a buy carries the full spread
#     against a bid bar, a sell none) cannot separate spread from slip at all
#     and is dominated by intrabar drift; fills sit mid-range (median range
#     position 0.44-0.69). It agrees nothing is grossly wrong and is too noisy
#     to supply a number.
#   - Small samples. FX: 14-21 entries per symbol, 2-7 of them buys, all
#     from 2025-02..2026-04, lots <= 0.03. Nothing here speaks to size impact.
#
# Finding, stated without interpretation:
#   - XAUUSD: slip past the same-second touch is ~0 (p50 -0.5 ticks, p75 +1,
#     p90 +5.3; n=108 of 113 entries had a same-second tick). Per-side cost vs
#     mid p50 0.075 USD/oz (7.5 ticks), p90 0.187 — about half the spread at
#     the fills (p50 0.16). The 1-tick HAND_ENTERED value sits between the
#     measured p50 and p75.
#   - FX (EURUSD, GBPUSD, AUDUSD, NZDUSD): fills sit a near-constant ~5 ticks
#     (0.5 pip) beyond the same-second touch, on both sides, on all four pairs,
#     while the tick-feed spread at the fills is 0-2 ticks. Per-side cost vs mid
#     p50 5-6 ticks. The tick stream does not show this cost; only the fills do.
#
# No default moves. SlipModel() is still 1 tick, HAND_ENTERED:
#   - XAUUSD: the measured median (0 after SlipModel's floor) is BELOW 1 tick,
#     so adopting it lowers every REALISTIC cost — the flattering direction,
#     which is a choice for the user, not a side effect of a measurement.
#   - FX: the measured ~5 ticks is ABOVE 1 tick, but every FX symbol has no
#     measured spread (resources.execution.spreads refuses them), so REALISTIC
#     cannot run on FX and the slip value changes nothing today. The
#     measurement also says an FX spread taken from the tick feed would miss
#     the ~5 tick markup; spread and slip are not separable from it.
# Use ``measured_slip_model(symbol)`` to ask for the measured value by name.
EXECUTION_COST_MEASURED = {
    "provenance": "MEASURED",
    "source": ("/api/v1/deals + /api/v1/ticks on PepperstoneKE-MT5-Live01 "
               "(GET only)"),
    "artifact": "phase0/execution_cost_20261011.json",
    "measured_on": "2026-10-11",
    "n_trade_deals": 358,
    "n_entries": 179,
    "span": "2025-02-10 .. 2026-04-13",
    "largest_lot": 0.03,
    "estimator": "entry-conditional (IN legs only, R7)",
    "method": ("fill vs tick quote, signed by side; primary quote = last tick "
               "in the fill's own second, bracket = last tick strictly before"),
    "cross_check": "fill vs admitted M5 bid bar (noisy; not a source)",
    "caveat": ("measured against the quote at fill time, not the requested "
               "price; request-to-fill latency beyond 1 s is not captured; "
               "the M5 fill-vs-bar cross-check cannot separate spread from "
               "slip"),
    #: Ticks. ``slip_vs_touch`` is primary (same-second quote); ``_pre`` is
    #: the bracket. ``cost_vs_mid_per_side_price`` is in price units.
    "per_symbol": {
        "XAUUSD": {
            "tick_size": 0.01, "n_entries": 113, "n_same_second": 108,
            "slip_vs_touch": {"p50": -0.5, "p75": 1.0, "p90": 5.3},
            "slip_vs_touch_pre": {"p50": -6.0, "p75": 0.0, "p90": 10.8},
            "cost_vs_mid_per_side_price": {"p50": 0.075, "p75": 0.1025,
                                           "p90": 0.1865},
            "spread_at_fill_price_p50": 0.16,
        },
        "EURUSD": {
            "tick_size": 1e-05, "n_entries": 21, "n_same_second": 20,
            "slip_vs_touch": {"p50": 5.0, "p75": 6.25, "p90": 8.2},
            "slip_vs_touch_pre": {"p50": 3.0, "p75": 5.0, "p90": 5.0},
            "cost_vs_mid_per_side_price": {"p50": 5e-05, "p75": 7.125e-05,
                                           "p90": 8.2e-05},
            "spread_at_fill_price_p50": 0.0,
        },
        "GBPUSD": {
            "tick_size": 1e-05, "n_entries": 16, "n_same_second": 16,
            "slip_vs_touch": {"p50": 5.0, "p75": 5.25, "p90": 6.5},
            "slip_vs_touch_pre": {"p50": 1.0, "p75": 3.0, "p90": 4.5},
            "cost_vs_mid_per_side_price": {"p50": 5.75e-05, "p75": 6.625e-05,
                                           "p90": 7.5e-05},
            "spread_at_fill_price_p50": 2e-05,
        },
        "AUDUSD": {
            "tick_size": 1e-05, "n_entries": 15, "n_same_second": 15,
            "slip_vs_touch": {"p50": 5.0, "p75": 6.5, "p90": 7.6},
            "slip_vs_touch_pre": {"p50": 1.0, "p75": 3.5, "p90": 7.4},
            "cost_vs_mid_per_side_price": {"p50": 5.5e-05, "p75": 6.75e-05,
                                           "p90": 8.5e-05},
            "spread_at_fill_price_p50": 1e-05,
        },
        "NZDUSD": {
            "tick_size": 1e-05, "n_entries": 14, "n_same_second": 14,
            "slip_vs_touch": {"p50": 5.0, "p75": 6.0, "p90": 6.0},
            "slip_vs_touch_pre": {"p50": 3.0, "p75": 4.0, "p90": 4.0},
            "cost_vs_mid_per_side_price": {"p50": 6e-05, "p75": 7e-05,
                                           "p90": 7e-05},
            "spread_at_fill_price_p50": 2e-05,
        },
    },
    "default_changed": False,
}

#: The value SlipModel() still charges. Superseded as EVIDENCE by
#: EXECUTION_COST_MEASURED — it is no longer the only number — but still the
#: default VALUE, for the reasons above.
SLIP_HAND_ENTERED = {
    "ticks": 1.0,
    "provenance": "HAND_ENTERED",
    "superseded_as_evidence_by": "EXECUTION_COST_MEASURED (2026-10-11)",
    "still_default": True,
}


def measured_slip_model(symbol: str, quantile: str = "p50",
                        estimator: str = "slip_vs_touch") -> SlipModel:
    """A ``SlipModel`` carrying the measured slip for ``symbol``, by name.

    ``estimator`` is ``slip_vs_touch`` (same-second quote, primary) or
    ``slip_vs_touch_pre`` (the bracket). A negative measured value is floored
    at 0 ticks: the simulator never lets a cost improve a fill, and the floor
    is recorded in the returned model's provenance rather than hidden.

    Raises ``KeyError`` for a symbol with no live fills — there is no
    measurement to borrow from another instrument.
    """
    try:
        rec = EXECUTION_COST_MEASURED["per_symbol"][symbol]
    except KeyError:
        raise KeyError(
            f"no live fills measured for {symbol!r}; measured symbols are "
            f"{sorted(EXECUTION_COST_MEASURED['per_symbol'])}") from None
    ticks = float(rec[estimator][quantile])
    provenance = "MEASURED" if ticks >= 0 else "MEASURED_FLOORED_AT_ZERO"
    return SlipModel(ticks=max(0.0, ticks), provenance=provenance)


# Placeholder swaps (USD per 1.0 lot per night). Pepperstone updates these
# weekly; override in code with values from MT5 Symbol Specifications.
PEPPERSTONE_XAUUSD_SWAP_LONG_USD_PER_LOT_NIGHT = -10.0    # placeholder
PEPPERSTONE_XAUUSD_SWAP_SHORT_USD_PER_LOT_NIGHT = -2.0    # placeholder

# Stops level safety floor for backtests, in USD/oz.
PEPPERSTONE_XAUUSD_STOPS_LEVEL_FLOOR_USD_PER_OZ = 0.10


# -- Cost scenarios ---------------------------------------------------------
#
# Cost uncertainty is an axis, not a hidden multiplier. Keeping a known-false
# 7.00 in the model "for conservatism" put a wrong number where a reader sees
# a documented constant, with the reasoning in a README rather than in the
# code that returns it — the same defect class as a seeded Sharpe, differing
# only in pointing somewhere safe.
#
# So the measured values are the model's, and conservatism becomes a declared
# scenario. Nothing is silently re-priced, because every result carries the
# scenario that produced it, and MEASURED and CONSERVATIVE can be reported
# side by side.


class CostScenario(str, Enum):
    """Which cost assumptions a result was produced under."""

    #: What this account actually pays. Commission measured at 0.00 across 358
    #: live deals (seq=105); spread measured at 0.17 USD/oz median over 117M
    #: XAUUSD ticks (D3b). The two belong together: the account is not on the
    #: Razor schedule, and its spread already carries whatever markup pays for
    #: the absent commission.
    MEASURED = "measured"

    #: The published Razor schedule plus the model's older assumed spread.
    #: This account is not billed under it, so it is a stress case rather than
    #: a description — useful precisely because it over-costs.
    CONSERVATIVE = "conservative"


#: Measured, from the live account.
MEASURED_COMMISSION_PER_LOT_RT = 0.0
MEASURED_SPREAD_USD_PER_OZ = 0.17

#: Conservative: the published MT5 Razor schedule and the older assumed spread.
CONSERVATIVE_COMMISSION_PER_LOT_RT = 7.0
CONSERVATIVE_SPREAD_USD_PER_OZ = 0.22

SCENARIO_VALUES = {
    CostScenario.MEASURED: (MEASURED_COMMISSION_PER_LOT_RT,
                            MEASURED_SPREAD_USD_PER_OZ),
    CostScenario.CONSERVATIVE: (CONSERVATIVE_COMMISSION_PER_LOT_RT,
                                CONSERVATIVE_SPREAD_USD_PER_OZ),
}


# -- Data class for trade-level cost breakdown ------------------------------


@dataclass
class CostBreakdown:
    spread_usd: float
    commission_usd: float
    swap_usd: float
    total_usd: float
    nights_held: int
    triple_swap_nights: int
    #: Which assumptions produced this. Present so a figure cannot be quoted
    #: without them.
    scenario: str = CostScenario.MEASURED.value


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
    #: Defaults are MEASURED. The published-schedule figures are a scenario,
    #: not the model — see CostScenario.
    commission_per_lot_round_turn: float = MEASURED_COMMISSION_PER_LOT_RT
    spread_usd_per_oz: float = MEASURED_SPREAD_USD_PER_OZ
    scenario: CostScenario = CostScenario.MEASURED
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

    @classmethod
    def for_scenario(cls, scenario: "CostScenario | str",
                     **overrides) -> "PepperstoneXAUUSDCostModel":
        """Build the model under a named cost scenario.

        The way to get conservative costs is to ask for them by name, so the
        result says which assumptions produced it.
        """
        sc = CostScenario(scenario)
        commission, spread = SCENARIO_VALUES[sc]
        return cls(commission_per_lot_round_turn=commission,
                   spread_usd_per_oz=spread, scenario=sc, **overrides)

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
            scenario=self.scenario.value,
            nights_held=nights,
            triple_swap_nights=triples,
        )


# pandas import deferred to avoid top-level dependency cycles where unneeded;
# but the swap walker uses pd.Timedelta. Keep it imported lazily.
import pandas as pd  # noqa: E402
