"""`strategies` — instrument-neutral strategy definitions.

Imports `resources` and nothing else from this repository (X19). A strategy
here emits target positions in risk units: a side, a stop distance in price,
and a multiple of the caller's risk budget. It never names a lot size, a
symbol, a tick or an account balance — those belong to `resources`, which is
the only package that knows what an instrument is.
"""

from .base import (
    HOLD,
    ClosedBars,
    EntryIntent,
    ManagementIntent,
    Position,
    Side,
    Strategy,
    run,
)
from .flood_tide import FloodTide, FloodTideParams
from .registry import (
    Lifecycle,
    NotSchedulable,
    Registration,
    registered,
    schedule_entries,
    schedule_entry,
)

def all_strategies() -> list[Strategy]:
    """Fresh instances of every strategy defined here, on default parameters.

    X5 and X6 are properties of *every* strategy in the repo, so they are
    parametrised over this rather than over a hand-listed pair — a new
    strategy inherits the look-ahead tests by existing.

    Deliberately not verdict-aware, which is now a division of labour
    rather than a gap: :mod:`strategies.registry` carries the lifecycle and
    refuses to schedule a KILLED or SHELVED mechanism (X29). This list makes
    no claim about whether anything in it should be traded — ask
    ``registry.schedule_entries()``, which currently returns nothing.
    """
    return [FloodTide()]


__all__ = [
    "HOLD",
    "Lifecycle",
    "NotSchedulable",
    "Registration",
    "registered",
    "schedule_entries",
    "schedule_entry",
    "all_strategies",
    "ClosedBars",
    "EntryIntent",
    "FloodTide",
    "FloodTideParams",
    "ManagementIntent",
    "Position",
    "Side",
    "Strategy",
    "run",
]
