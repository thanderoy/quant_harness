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

def all_strategies() -> list[Strategy]:
    """Fresh instances of every strategy defined here, on default parameters.

    X5 and X6 are properties of *every* strategy in the repo, so they are
    parametrised over this rather than over a hand-listed pair — a new
    strategy inherits the look-ahead tests by existing.

    Deliberately not the verdict-aware registry X29 calls for: that one has to
    refuse to schedule a KILLED or SHELVED mechanism, which is an execution
    concern and belongs to T12 / Phase 3. This list makes no claim about
    whether anything in it should be traded. Nothing in it should.
    """
    return [FloodTide()]


__all__ = [
    "HOLD",
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
