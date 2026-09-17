"""X29 — a beat schedule is generated from the registry, and verdicts bind it.

The incident this encodes: at seq=65 a mechanism was killed in the research
log while the Celery beat schedule was a separate hand-maintained dict, and
the strategy went on running. Neither artefact was wrong. The gap between
them was, and a gap is not something a test of either one alone can find.

So what is asserted here is the *connection*: that no path exists from a
KILLED or SHELVED registration to a schedule entry.
"""

from __future__ import annotations

import pytest

from strategies.registry import (
    REGISTRY,
    Lifecycle,
    NotSchedulable,
    Registration,
    registered,
    schedule_entries,
    schedule_entry,
)

pytestmark = [pytest.mark.x("X29")]

FORBIDDEN = (Lifecycle.KILLED, Lifecycle.SHELVED, Lifecycle.OPEN)


def test_a_killed_or_shelved_mechanism_never_reaches_a_schedule():
    for lifecycle in FORBIDDEN:
        assert not lifecycle.may_be_scheduled
        assert not lifecycle.may_place_orders


def test_only_live_may_place_orders():
    """SHADOW is the whole point of the state: scheduled, evaluated, mute."""
    assert Lifecycle.LIVE.may_place_orders
    assert Lifecycle.SHADOW.may_be_scheduled
    assert not Lifecycle.SHADOW.may_place_orders


def test_asking_for_a_forbidden_entry_raises_rather_than_returning_nothing():
    """Filtering is something a caller can forget; raising is not. A helper
    that returned ``None`` here would be silently dropped into a dict
    comprehension and the strategy would simply vanish from the schedule
    with no one told why."""
    shelved = [r for r in REGISTRY if r.lifecycle in FORBIDDEN]
    assert shelved, "fixture assumption: the repo has an unschedulable entry"
    for reg in shelved:
        with pytest.raises(NotSchedulable, match="cannot appear"):
            schedule_entry(reg.name)


def test_the_generated_schedule_contains_no_forbidden_mechanism():
    names = {r.name for r in REGISTRY if r.lifecycle in FORBIDDEN}
    assert names.isdisjoint(schedule_entries())


def test_every_registration_cites_logged_evidence():
    """A lifecycle state with no recorded basis is an opinion, and the point
    of deriving the schedule is that it follows findings."""
    for reg in registered():
        assert reg.evidence, f"{reg.name} has no evidence reference"
        assert "seq=" in reg.evidence


def test_the_schedule_carries_the_order_permission_into_the_entry():
    """If ``places_orders`` were dropped at this boundary, SHADOW and LIVE
    would be indistinguishable to whatever runs the task."""
    entry = schedule_entry_for(Lifecycle.SHADOW)
    assert entry["places_orders"] is False
    assert schedule_entry_for(Lifecycle.LIVE)["places_orders"] is True


def schedule_entry_for(lifecycle: Lifecycle) -> dict:
    """Build a one-off registration at ``lifecycle`` and schedule it."""
    import strategies.registry as mod
    from strategies.flood_tide import FloodTide

    reg = Registration(name="probe", factory=FloodTide, lifecycle=lifecycle,
                       magic=999_999, evidence="seq=0 (test fixture)")
    original = mod.REGISTRY
    mod.REGISTRY = original + (reg,)
    try:
        return schedule_entry("probe")
    finally:
        mod.REGISTRY = original


def test_the_registry_instantiates_what_it_registers():
    for reg in registered():
        assert reg.instantiate() is not None


def test_no_mechanism_in_this_repo_is_currently_schedulable():
    """Not a design assertion — a factual one, and it should fail loudly the
    day something legitimately earns a schedule. flood_tide was shelved at
    seq=34 and nothing else has cleared a gate."""
    assert dict(schedule_entries()) == {}


def test_lifecycle_does_not_drift_from_the_research_logs_vocabulary():
    """The two enums are deliberately separate — ``strategies`` may not
    import ``research`` (X19) — but they must not come to disagree about
    what a shared word means."""
    from research.log import Verdict

    shared = {m.name for m in Lifecycle} & {m.name for m in Verdict}
    assert {"KILLED", "SHELVED"} <= shared
    for name in shared:
        assert Lifecycle[name].value == Verdict[name].value, (
            f"{name} means {Lifecycle[name].value!r} to strategies and "
            f"{Verdict[name].value!r} to the research log")
