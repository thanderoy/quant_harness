"""Measured spreads, and a refusal for everything that was never measured.

The ``NEXT_OPEN_SPREAD`` and ``REALISTIC`` legs of the fill frontier are
defined in terms of a median and a 95th-percentile spread. Those are
measurements, not parameters, and this module exists so the difference stays
visible: a symbol D3b did not sample has no spread here, and asking for one
raises :class:`UnmeasuredSpread`.

That refusal is the whole point. The alternative — defaulting an unmeasured
symbol to zero — produces a ``REALISTIC`` frontier leg that is silently
identical to ``NEXT_OPEN``, so a mechanism appears to survive costs it was
never charged. A frontier that cannot fail is not evidence, and it would
fail exactly where it looks most reassuring: on a new instrument.

D3b covers XAUUSD and XAGUSD. Everything else in the nine-symbol universe is
unmeasured, and this module says so rather than guessing from the eight
other symbols.
"""

from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass

__all__ = [
    "SpreadSnapshot",
    "SpreadStats",
    "UnmeasuredSpread",
    "load_spreads",
]

SNAPSHOT_DIR = pathlib.Path(__file__).resolve().parent / "snapshots"

#: The D3b distillation currently shipped. Named explicitly rather than
#: globbed for "newest", so a snapshot dropped into the directory cannot
#: silently change every backtest in the repo.
DEFAULT_SNAPSHOT = "spreads_d3b_20260907"


class UnmeasuredSpread(KeyError):
    """Raised for a symbol the snapshot has no measurement for."""


@dataclass(frozen=True)
class SpreadStats:
    """Full bid-ask widths in price units. Consumers charge half per side."""

    median: float
    p95: float
    n_ticks: int

    def __post_init__(self) -> None:
        if self.median < 0 or self.p95 < 0:
            raise ValueError(f"spreads must be >= 0, got {self!r}")
        if self.p95 < self.median:
            raise ValueError(
                f"p95 {self.p95} is below the median {self.median}; the "
                "snapshot is malformed or the percentiles are swapped")


@dataclass(frozen=True)
class SpreadSnapshot:
    """A pinned set of spread measurements, with the broker that produced it.

    The broker is carried because spread is broker policy, not a property of
    the instrument — the same nine symbols quote differently on
    MetaQuotes-Demo than on Pepperstone, and a snapshot that did not record
    which terminal answered is how a demo dump gets filed as a live one.
    """

    snapshot_id: str
    as_of_utc: str
    provenance: str
    broker: str
    source_artifact: str
    stats: dict[str, SpreadStats]

    def __getitem__(self, symbol: str) -> SpreadStats:
        try:
            return self.stats[symbol]
        except KeyError:
            raise UnmeasuredSpread(
                f"no measured spread for {symbol!r} in snapshot "
                f"{self.snapshot_id!r} (broker {self.broker}); measured "
                f"symbols are {sorted(self.stats)}. Charging a fabricated "
                "spread would make the REALISTIC frontier leg meaningless, "
                "so this refuses instead. Run the D3b collector for this "
                "symbol, or run the frontier only on measured symbols."
            ) from None

    def __contains__(self, symbol: object) -> bool:
        return symbol in self.stats

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted(self.stats))


def load_spreads(snapshot: str = DEFAULT_SNAPSHOT) -> SpreadSnapshot:
    """Load a committed spread snapshot by id. No network, no filesystem
    outside this package (X2/X20)."""
    path = SNAPSHOT_DIR / f"{snapshot}.json"
    if not path.exists():
        available = sorted(p.stem for p in SNAPSHOT_DIR.glob("spreads_*.json"))
        raise FileNotFoundError(
            f"no spread snapshot {snapshot!r}; available: {available}")
    raw = json.loads(path.read_text())
    stats = {
        symbol: SpreadStats(median=s["median_spread"], p95=s["p95_spread"],
                            n_ticks=s["n_ticks"])
        for symbol, s in raw["symbols"].items()
    }
    return SpreadSnapshot(
        snapshot_id=raw["snapshot_id"],
        as_of_utc=raw["as_of_utc"],
        provenance=raw["provenance"],
        broker=raw["broker"],
        source_artifact=raw["source_artifact"],
        stats=stats,
    )
