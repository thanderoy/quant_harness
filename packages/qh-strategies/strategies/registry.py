"""X29 — the registry a schedule is generated from, not a list maintained by hand.

This exists because a KILLED mechanism reached the live path. At seq=65 the
research log recorded a verdict; the Celery beat schedule was a separate,
hand-maintained dict; and nothing connected them. Both artefacts were
individually correct and the system still traded a strategy that had been
killed, because "remember to remove it from beat" is not a control.

So the schedule is *derived*. :func:`schedule_entries` is the only sanctioned
source of beat entries, and it cannot emit one for a mechanism whose
lifecycle is KILLED or SHELVED — not by filtering after the fact, but by
refusing at the point the entry would be built.

``SHADOW`` is the state that makes the control usable rather than merely
strict. A shadow strategy is evaluated and logged on schedule and places no
orders, which is how a mechanism earns its way back without anyone needing
to comment a line out and remember to restore it.

Lifecycle vs the research log's ``Verdict``
-------------------------------------------

The vocabulary is deliberately duplicated rather than imported. ``strategies``
may not import ``research`` (X19), and the two concepts are not the same one:
``research.log.Verdict`` adjudicates *hypotheses*, which include screens and
features that were never strategies and can never be scheduled. What they do
share is the words, and ``tests/test_t12_lifecycle_parity.py`` asserts the
shared members keep identical string values, so the duplication cannot drift
into two vocabularies that disagree about what "shelved" means.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, Mapping, Tuple

from strategies.base import Strategy
from strategies.flood_tide import FloodTide

__all__ = [
    "Lifecycle",
    "NotSchedulable",
    "REGISTRY",
    "Registration",
    "registered",
    "schedule_entries",
]


class Lifecycle(str, Enum):
    """Where a mechanism stands with respect to being run.

    Ordered by how much licence each state grants, least to most.
    """

    KILLED = "killed"      # refuted; must never run again
    SHELVED = "shelved"    # not refuted, not carried; must not run
    OPEN = "open"          # under research; not schedulable either
    SHADOW = "shadow"      # evaluated and logged on schedule, places no orders
    LIVE = "live"          # evaluated and permitted to order

    @property
    def may_be_scheduled(self) -> bool:
        return self in (Lifecycle.SHADOW, Lifecycle.LIVE)

    @property
    def may_place_orders(self) -> bool:
        return self is Lifecycle.LIVE


class NotSchedulable(ValueError):
    """Raised when a schedule entry is requested for a mechanism whose
    lifecycle forbids running."""


@dataclass(frozen=True)
class Registration:
    """One mechanism and the licence it currently holds.

    ``evidence`` is a research-log sequence number rather than free prose:
    a lifecycle state with no logged basis is an opinion, and the whole
    point of this module is that the schedule follows recorded findings.
    """

    name: str
    factory: Callable[[], Strategy]
    lifecycle: Lifecycle
    magic: int
    evidence: str
    note: str = ""

    def instantiate(self) -> Strategy:
        return self.factory()


#: The mechanisms this repo knows about. Every one of them is currently
#: unschedulable, which is the honest state: flood_tide was shelved at
#: seq=34 and nothing else has cleared a gate. A registry whose entries were
#: all LIVE by default would be the hand-maintained list this replaces.
REGISTRY: Tuple[Registration, ...] = (
    Registration(
        name="flood_tide_h1",
        factory=FloodTide,
        lifecycle=Lifecycle.SHELVED,
        magic=310_001,
        evidence="seq=31-34",
        note=("Donchian breakout shelved after two iterations; the "
              "regime-filtered E-Ratio null was decisive."),
    ),
)


def registered() -> Tuple[Registration, ...]:
    """Everything known, regardless of lifecycle."""
    return REGISTRY


def _by_name() -> Dict[str, Registration]:
    return {r.name: r for r in REGISTRY}


def schedule_entries() -> Mapping[str, dict]:
    """Generate the beat schedule. The only sanctioned source of one.

    Returns a mapping of task name to an entry carrying ``places_orders``,
    so the SHADOW/LIVE distinction survives into the thing that actually
    runs rather than being lost at the boundary.
    """
    entries: Dict[str, dict] = {}
    for reg in REGISTRY:
        if not reg.lifecycle.may_be_scheduled:
            continue
        entries[reg.name] = {
            "strategy": reg.name,
            "magic": reg.magic,
            "lifecycle": reg.lifecycle.value,
            "places_orders": reg.lifecycle.may_place_orders,
            "evidence": reg.evidence,
        }
    return entries


def schedule_entry(name: str) -> dict:
    """Build one entry, refusing outright for a forbidden lifecycle.

    The refusal is the control. Filtering a list is something a caller can
    forget to do; raising is not.
    """
    try:
        reg = _by_name()[name]
    except KeyError:
        raise NotSchedulable(
            f"{name!r} is not registered; a schedule may only be built from "
            f"registered mechanisms, which are {sorted(_by_name())}") from None
    if not reg.lifecycle.may_be_scheduled:
        raise NotSchedulable(
            f"{name!r} is {reg.lifecycle.value.upper()} ({reg.evidence}) and "
            "cannot appear in a generated schedule. This refusal is X29: a "
            "KILLED strategy reached the live path once because the verdict "
            "and the beat schedule were maintained separately.")
    return dict(schedule_entries()[name])
