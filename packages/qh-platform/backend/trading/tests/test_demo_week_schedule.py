"""
The Phase 3 demo-week schedule (ruling R13).

crest_n_keel and asqs are back on the beat schedule as engineering fixtures
for one week against the demo terminal. These tests hold the conditions that
keep that from drifting into a redeployment of two strategies whose evidence
was refuted: every scheduled strategy resolves to the demo terminal, every
scheduled task name is a real registered task, and h1_momentum stays halted.
"""

import inspect
from unittest.mock import patch

import pytest
from app.config import settings

STRATEGY_TASKS = {
    "crest-n-keel": ("app.quant.strategies.crest_n_keel.tasks", "run_crest_n_keel",
                     "CrestNKeelStrategy"),
    "asqs": ("app.quant.strategies.asqs.tasks", "run_asqs",
             "ASQSafeScalpingStrategy"),
}


def _schedule() -> dict:
    return settings.CELERY_BEAT_SCHEDULE


def test_the_demo_week_strategies_are_scheduled():
    assert set(STRATEGY_TASKS) <= set(_schedule())
    assert "asqs-audit" in _schedule()


def test_h1_momentum_stays_halted():
    """R6. Its halt needs a fresh pre-registration record, not a schedule edit."""
    scheduled = {e["task"] for e in _schedule().values()}
    assert not any("h1_momentum" in t for t in scheduled)


def test_every_scheduled_task_name_is_registered():
    """Celery routes by string. A typo here is a task that never runs and
    raises nothing — which on a demo week reads as 'no signals'."""
    import importlib

    from app.config.celery import app as current_app

    for mod in ("app.quant.tasks",
                "app.quant.strategies.crest_n_keel.tasks",
                "app.quant.strategies.asqs.tasks"):
        importlib.import_module(mod)
    registered = set(current_app.tasks)
    missing = [e["task"] for e in _schedule().values() if e["task"] not in registered]
    assert not missing, f"scheduled but not registered: {missing}"


@pytest.mark.parametrize("entry", sorted(STRATEGY_TASKS))
def test_each_scheduled_strategy_resolves_to_the_demo_terminal(entry):
    """The task builds its strategy with no arguments, so the class default
    decides the terminal. Drive the task with the class patched and check what
    it was built with, then check that the default resolves to mt5-test."""
    import importlib

    mod_path, func_name, cls_name = STRATEGY_TASKS[entry]
    mod = importlib.import_module(mod_path)
    real_cls = getattr(mod, cls_name)
    default_env = inspect.signature(real_cls.__init__).parameters["environment"].default

    with patch.object(mod, cls_name) as fake:
        fake.return_value.environment = default_env
        fake.return_value.evaluate.return_value = None
        task = getattr(mod, func_name)
        (task.run if hasattr(task, "run") else task)()
    kwargs = fake.call_args.kwargs
    env = kwargs.get("environment", default_env)
    assert env == "test", f"{entry} would trade on '{env}'"
    assert settings.get_mt5_url(env) == settings.MT5_TEST_API_URL
    assert settings.MT5_TEST_API_URL != settings.MT5_API_URL


def test_asqs_discards_stale_signals():
    assert _schedule()["asqs"]["options"]["expires"] == 240
