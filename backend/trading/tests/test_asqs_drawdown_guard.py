"""
Regression tests for the ASQS drawdown-guard call chain in ``evaluate()``.

These prove the guard runs on EVERY evaluation (not just signal cycles) and
halts all entry/signal work the moment an 8% drawdown from peak is breached,
while still allowing existing-position management to run.

MT5 is fully mocked; no broker or DB access. The on-disk peak store key is
``peak_equity`` (JsonPeakStore format) — do not change it here.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.quant.strategies.asqs.strategy import ASQSafeScalpingStrategy


def _build(mock_mt5_cls: MagicMock, peak_file: Path) -> ASQSafeScalpingStrategy:
    """Construct a strategy with MT5 mocked. Caller pre-seeds mock returns."""
    return ASQSafeScalpingStrategy(
        environment="test",
        peak_store_path=str(peak_file),
        mt5_base_url="http://mock:5001",
    )


@patch("app.quant.strategies.asqs.strategy.MT5APIClient")
def test_evaluate_seeds_peak_on_first_call(mock_mt5_cls, tmp_path: Path) -> None:
    peak_file = tmp_path / "peak.json"
    mock_mt5 = mock_mt5_cls.return_value
    mock_mt5.get_account_info.return_value = {"equity": 100.0, "balance": 100.0}
    mock_mt5.get_open_positions.return_value = []

    strat = _build(mock_mt5_cls, peak_file)
    # Stop right after the guard so we never reach the DB-backed daily cap.
    strat._check_session = MagicMock(return_value=False)

    strat.evaluate()

    assert peak_file.exists()
    assert json.loads(peak_file.read_text())["peak_equity"] == pytest.approx(100.0)


@patch("app.quant.strategies.asqs.strategy.MT5APIClient")
def test_evaluate_halts_before_signal_work_when_tripped(mock_mt5_cls, tmp_path: Path) -> None:
    peak_file = tmp_path / "peak.json"
    peak_file.write_text(json.dumps({"peak_equity": 100.0}))

    mock_mt5 = mock_mt5_cls.return_value
    mock_mt5.get_account_info.return_value = {"equity": 91.0, "balance": 91.0}  # 9% dd
    mock_mt5.get_open_positions.return_value = []  # manage_positions no-ops
    mock_mt5.get_market_rates.side_effect = AssertionError(
        "get_market_rates must not be called when guard is tripped"
    )
    mock_mt5.send_order.side_effect = AssertionError(
        "send_order must not be called when guard is tripped"
    )

    strat = _build(mock_mt5_cls, peak_file)
    result = strat.evaluate()

    assert result is None
    mock_mt5.get_market_rates.assert_not_called()
    mock_mt5.send_order.assert_not_called()
    # A breach must never advance the peak.
    assert json.loads(peak_file.read_text())["peak_equity"] == pytest.approx(100.0)


@patch("app.quant.strategies.asqs.strategy.MT5APIClient")
def test_evaluate_continues_when_not_tripped(mock_mt5_cls, tmp_path: Path) -> None:
    peak_file = tmp_path / "peak.json"
    peak_file.write_text(json.dumps({"peak_equity": 100.0}))

    mock_mt5 = mock_mt5_cls.return_value
    mock_mt5.get_account_info.return_value = {"equity": 95.0, "balance": 95.0}  # 5% dd
    mock_mt5.get_open_positions.return_value = []
    mock_mt5.get_market_rates.return_value = {"rates": []}

    strat = _build(mock_mt5_cls, peak_file)
    # Pass the gates between the guard and the candle fetch (daily cap hits the DB).
    strat._check_session = MagicMock(return_value=True)
    strat._check_friday_cutoff = MagicMock(return_value=True)
    strat._check_daily_cap = MagicMock(return_value=True)

    strat.evaluate()

    mock_mt5.get_market_rates.assert_called()  # signal work was reached


@patch("app.quant.strategies.asqs.strategy.MT5APIClient")
def test_guard_runs_outside_session(mock_mt5_cls, tmp_path: Path) -> None:
    """The peak must update even when the session filter would reject the cycle.

    This is the core failure-mode-2 fix: the guard sits ABOVE the session
    filter, so the peak tracks equity 24/7 rather than only during sessions.
    """
    peak_file = tmp_path / "peak.json"
    mock_mt5 = mock_mt5_cls.return_value
    mock_mt5.get_account_info.return_value = {"equity": 100.0, "balance": 100.0}
    mock_mt5.get_open_positions.return_value = []

    strat = _build(mock_mt5_cls, peak_file)
    strat._check_session = MagicMock(return_value=False)  # outside session

    strat.evaluate()

    assert json.loads(peak_file.read_text())["peak_equity"] == pytest.approx(100.0)
