"""
The beat schedule after the Phase 3 demo week (R13, X29).

crest_n_keel and asqs ran as engineering fixtures for the demo week and came
off at its end, 2026-10-13. These tests keep them off, keep h1_momentum
halted, and hold the operational canary that replaced them to the demo
terminal: a killed mechanism must not sit on a live schedule, and the only
thing scheduled against a terminal is a check that cannot signal or order.
"""

import importlib

from app.config import settings

RETIRED = ("quant.crest_n_keel.run", "quant.asqs.run", "quant.asqs.audit",
           "quant.h1_momentum.run")


def _schedule() -> dict:
    return settings.CELERY_BEAT_SCHEDULE


def test_retired_strategies_are_off_the_schedule():
    """R13 time-boxed them to the demo week; X29 keeps killed mechanisms off."""
    scheduled = {e["task"] for e in _schedule().values()}
    assert not scheduled & set(RETIRED), sorted(scheduled & set(RETIRED))


def test_h1_momentum_stays_halted():
    """R6. Its halt needs a fresh pre-registration record, not a schedule edit."""
    scheduled = {e["task"] for e in _schedule().values()}
    assert not any("h1_momentum" in t for t in scheduled)


def test_every_scheduled_task_name_is_registered():
    """Celery routes by string. A typo here is a task that never runs and
    raises nothing."""
    from app.config.celery import app as current_app

    importlib.import_module("app.quant.tasks")
    registered = set(current_app.tasks)
    missing = [e["task"] for e in _schedule().values() if e["task"] not in registered]
    assert not missing, f"scheduled but not registered: {missing}"


def test_the_canary_is_scheduled_against_the_demo_terminal():
    entry = _schedule()["ops-canary"]
    assert entry["task"] == "quant.canary.run"
    env = entry["kwargs"]["environment"]
    assert env == "test"
    assert settings.get_mt5_url(env) == settings.MT5_TEST_API_URL
    assert settings.MT5_TEST_API_URL != settings.MT5_API_URL


def test_canary_runs_expire_before_the_next_fire():
    """Fires every 15 minutes; a run not picked up in 10 is dropped, not queued."""
    assert _schedule()["ops-canary"]["options"]["expires"] == 600
