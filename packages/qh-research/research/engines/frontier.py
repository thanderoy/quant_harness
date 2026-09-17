"""T12 — the four-configuration fill frontier, and the door X23 guards.

The reporting requirement in the spec is blunt: *no backtest result is
logged under a single fill assumption*. This module is how that is enforced
rather than remembered. :class:`FillFrontier` cannot be constructed with
fewer than all four configurations, and :func:`write_backtest_artifact`
is the only sanctioned way to put a backtest on disk.

Why a constructor-level refusal rather than a review habit: a single-
assumption result is not merely incomplete, it is *systematically
optimistic*. The assumption a researcher reaches for under time pressure is
the one that ran last and looked best, and the resulting number is
indistinguishable on the page from one that survived costs. The frontier
makes the comparison mandatory and therefore unflattering by default.

The verdict rule is equally blunt, and comes straight from the spec: a
mechanism whose edge disappears between ``NEXT_OPEN`` and ``REALISTIC`` is
reported **failed**, not conditional. "Works with tight execution" is the
phrasing that keeps a dead strategy alive for another month.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Mapping, Optional, Type

import pandas as pd

from resources.execution import FRONTIER, FillConfig, SlipModel, load_spreads

from research.engines.btpy_runner import BtRunResult, run_backtest

__all__ = [
    "FillFrontier",
    "FrontierVerdict",
    "run_fill_frontier",
    "write_backtest_artifact",
]


class FrontierVerdict(str):
    """Deliberately a plain string subclass: it is written into artifacts and
    read by eye, and an enum's ``.value`` dance adds nothing here."""


SURVIVES = FrontierVerdict("SURVIVES_REALISTIC")
FAILED = FrontierVerdict("FAILED_ON_EXECUTION")
NO_EDGE = FrontierVerdict("NO_EDGE_AT_ANY_CONFIG")


class IncompleteFrontier(ValueError):
    """Raised when a backtest is about to be recorded under fewer than all
    four fill configurations."""


@dataclass(frozen=True)
class FillFrontier:
    """All four results for one mechanism on one symbol.

    ``__post_init__`` is the X23 gate. It refuses construction rather than
    refusing serialisation, so an incomplete frontier cannot exist long
    enough to be passed to something that does not check.
    """

    strategy_name: str
    symbol: str
    results: Mapping[FillConfig, BtRunResult]
    cost_to_atr: Optional[float] = None

    def __post_init__(self) -> None:
        missing = set(FRONTIER) - set(self.results)
        if missing:
            raise IncompleteFrontier(
                f"{self.strategy_name} on {self.symbol} has results for "
                f"{sorted(c.value for c in self.results)} but the frontier "
                f"requires all four; missing "
                f"{sorted(c.value for c in missing)}. A result under a "
                "single fill assumption is systematically optimistic and "
                "X23 forbids recording one.")
        unknown = set(self.results) - set(FRONTIER)
        if unknown:
            raise IncompleteFrontier(f"unknown fill configurations: {unknown}")

    def sharpe(self, config: FillConfig) -> float:
        return self.results[config].sharpe

    @property
    def verdict(self) -> FrontierVerdict:
        """Where the edge dies, in the spec's vocabulary."""
        optimistic = self.sharpe(FillConfig.NEXT_OPEN)
        realistic = self.sharpe(FillConfig.REALISTIC)
        if not (optimistic > 0):
            return NO_EDGE
        if not (realistic > 0):
            return FAILED
        return SURVIVES

    def to_record(self) -> Dict:
        spreads = load_spreads()
        return {
            "strategy": self.strategy_name,
            "symbol": self.symbol,
            "verdict": str(self.verdict),
            "cost_to_atr": self.cost_to_atr,
            "spread_snapshot": spreads.snapshot_id,
            "spread_provenance": spreads.provenance,
            "broker": spreads.broker,
            "fill_frontier": {
                config.value: {
                    "sharpe": self.results[config].sharpe,
                    "max_dd": self.results[config].max_dd,
                    "pf": self.results[config].pf,
                    "n_trades": self.results[config].n_trades,
                }
                for config in FRONTIER
            },
        }


def _cost_to_atr(bars: pd.DataFrame, symbol: str, slip: SlipModel,
                 period: int = 14) -> Optional[float]:
    """Round-trip adverse cost as a fraction of one ATR.

    The ratio the spec asks to be reported alongside the frontier. It is the
    quantity that decides whether a timeframe is viable at all — seq=40's
    finding that M5/M15 are structurally cost-destroyed is this number and
    nothing else.
    """
    try:
        stats = load_spreads()[symbol]
    except KeyError:
        return None
    from resources.indicators import atr

    frame = bars.rename(columns=str.lower)
    if not {"high", "low", "close"} <= set(frame.columns):
        return None
    a = atr(frame["high"], frame["low"], frame["close"], period=period)
    median_atr = float(a.median())
    if not (median_atr > 0):
        return None
    from research.engines.btpy_runner import _tick_size
    try:
        slip_price = slip.ticks * _tick_size(symbol)
    except KeyError:
        slip_price = 0.0
    # One round trip crosses the spread once and slips on both legs.
    return (stats.p95 + 2 * slip_price) / median_atr


def run_fill_frontier(
    bars: pd.DataFrame,
    strategy_cls: Type,
    *,
    symbol: str = "XAUUSD",
    slip: Optional[SlipModel] = None,
    **kwargs,
) -> FillFrontier:
    """Run the same mechanism under all four execution assumptions."""
    slip = slip or SlipModel()
    results = {
        config: run_backtest(bars, strategy_cls, fill_config=config,
                             symbol=symbol, slip=slip, **kwargs)
        for config in FRONTIER
    }
    return FillFrontier(
        strategy_name=strategy_cls.__name__,
        symbol=symbol,
        results=results,
        cost_to_atr=_cost_to_atr(bars, symbol, slip),
    )


def write_backtest_artifact(path: "Path | str", frontier: FillFrontier,
                            extra: Optional[Mapping] = None) -> Path:
    """Write a backtest artifact. The type signature is the enforcement:
    nothing but a complete :class:`FillFrontier` can be passed."""
    if not isinstance(frontier, FillFrontier):
        raise IncompleteFrontier(
            f"a backtest artifact must be written from a FillFrontier, got "
            f"{type(frontier).__name__}; X23 exists because a single-"
            "configuration result is not a reportable backtest.")
    record = frontier.to_record()
    if extra:
        record.update(dict(extra))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return path
