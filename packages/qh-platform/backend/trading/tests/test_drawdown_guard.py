"""
Unit tests for DrawdownGuard / JsonPeakStore.

No MT5 or DB access — pure persistence + drawdown-math coverage.
Store key on disk is ``peak_equity`` (not ``peak``); tests match that format.
"""

import json
from pathlib import Path

import pytest

from app.quant.strategies.drawdown_guard import DrawdownGuard, JsonPeakStore

MAX_DD = 0.08  # ASQS uses an 8% drawdown halt


def _guard(path: Path, max_dd: float = MAX_DD) -> DrawdownGuard:
    return DrawdownGuard(JsonPeakStore(str(path)), max_drawdown_pct=max_dd)


def test_first_evaluation_never_trips(tmp_path: Path) -> None:
    guard = _guard(tmp_path / "peak.json")
    assert guard.is_tripped(equity=1.0) is False
    assert guard.is_tripped(equity=1_000_000.0) is False


def test_peak_advances_on_higher_equity(tmp_path: Path) -> None:
    peak_file = tmp_path / "peak.json"
    guard = _guard(peak_file)
    for equity in (100.0, 105.0, 102.0, 110.0, 108.0):
        guard.update(equity=equity)
    assert guard.peak_equity == pytest.approx(110.0)
    assert json.loads(peak_file.read_text())["peak_equity"] == pytest.approx(110.0)


def test_peak_does_not_retreat(tmp_path: Path) -> None:
    guard = _guard(tmp_path / "peak.json")
    guard.update(equity=100.0)
    guard.update(equity=90.0)   # drop
    guard.update(equity=95.0)   # partial recovery, still below peak
    assert guard.peak_equity == pytest.approx(100.0)


def test_trips_below_threshold(tmp_path: Path) -> None:
    guard = _guard(tmp_path / "peak.json")
    guard.update(equity=100.0)
    # threshold = 100 * (1 - 0.08) = 92.0; strictly-below trips.
    assert guard.is_tripped(equity=91.99) is True


def test_does_not_trip_at_exact_threshold(tmp_path: Path) -> None:
    """is_tripped uses strict ``<`` — equity == threshold does NOT trip."""
    guard = _guard(tmp_path / "peak.json")
    guard.update(equity=100.0)
    assert guard.trigger_threshold() == pytest.approx(92.0)
    assert guard.is_tripped(equity=92.0) is False


def test_does_not_trip_just_above_threshold(tmp_path: Path) -> None:
    guard = _guard(tmp_path / "peak.json")
    guard.update(equity=100.0)
    assert guard.is_tripped(equity=92.01) is False


def test_state_survives_new_instance(tmp_path: Path) -> None:
    peak_file = tmp_path / "peak.json"
    guard1 = _guard(peak_file)
    guard1.update(equity=100.0)

    guard2 = _guard(peak_file)
    assert guard2.peak_equity == pytest.approx(100.0)
    assert guard2.is_tripped(equity=91.0) is True


def test_does_not_advance_peak_past_breach(tmp_path: Path) -> None:
    """Guard contract: check is_tripped before update so a breach equity
    never becomes the new peak."""
    guard = _guard(tmp_path / "peak.json")
    guard.update(equity=100.0)
    breach_equity = 90.0
    if not guard.is_tripped(equity=breach_equity):
        guard.update(equity=breach_equity)  # would only run if not tripped
    assert guard.peak_equity == pytest.approx(100.0)


def test_current_drawdown(tmp_path: Path) -> None:
    guard = _guard(tmp_path / "peak.json")
    assert guard.current_drawdown(equity=100.0) == 0.0  # no peak yet
    guard.update(equity=100.0)
    assert guard.current_drawdown(equity=92.0) == pytest.approx(0.08)
    assert guard.current_drawdown(equity=110.0) == 0.0  # above peak clamps to 0


# -- state loss is loud (Phase 3 step 6) --------------------------------------

import logging  # noqa: E402

from app.quant.strategies.drawdown_guard import JsonPeakStore  # noqa: E402


def _criticals(caplog):
    return [r for r in caplog.records if r.levelno == logging.CRITICAL]


def test_missing_peak_file_is_reported_once_as_critical(tmp_path, caplog):
    """A missing peak is either a first deployment or lost state, and lost
    state hands the drawdown budget back. It must not look like nothing."""
    store = JsonPeakStore(str(tmp_path / "peak.json"))
    with caplog.at_level(logging.INFO):
        assert store.read() is None
        assert store.read() is None
    crit = _criticals(caplog)
    assert len(crit) == 1, "reported once per store, not on every read"
    assert "fresh peak" in crit[0].getMessage()
    assert "peak.json" in crit[0].getMessage()


@pytest.mark.parametrize("body", ["{not json", '{"other": 1}', '{"peak_equity": "x"}',
                                  '{"peak_equity": null}'])
def test_unreadable_peak_file_is_critical(tmp_path, caplog, body):
    path = tmp_path / "peak.json"
    path.write_text(body)
    with caplog.at_level(logging.INFO):
        assert JsonPeakStore(str(path)).read() is None
    assert len(_criticals(caplog)) == 1


def test_a_present_peak_is_read_silently(tmp_path, caplog):
    path = tmp_path / "peak.json"
    JsonPeakStore(str(path)).write(3643.21)
    with caplog.at_level(logging.INFO):
        assert JsonPeakStore(str(path)).read() == 3643.21
    assert not _criticals(caplog)


def test_partial_close_tracker_missing_is_routine_corrupt_is_critical(tmp_path, caplog):
    from app.quant.strategies.asqs.strategy import _PartialCloseTracker

    with caplog.at_level(logging.INFO):
        _PartialCloseTracker(str(tmp_path / "missing.json"))
    assert not _criticals(caplog)

    bad = tmp_path / "partial.json"
    bad.write_text("{truncated")
    caplog.clear()
    with caplog.at_level(logging.INFO):
        t = _PartialCloseTracker(str(bad))
    assert not t.is_closed(101)
    crit = _criticals(caplog)
    assert len(crit) == 1 and "repeat its TP1" in crit[0].getMessage()
