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
