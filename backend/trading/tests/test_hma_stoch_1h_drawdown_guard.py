"""
Regression tests for the ``crest_n_keel`` (hma_stoch_1h) drawdown-guard call
chain in ``evaluate()``.

These prove the guard runs on EVERY evaluation (before any session / bar /
signal work) and halts all entry/signal work the moment a 15% drawdown from
peak is breached, while still seeding and advancing the peak 24/7.

MT5 is fully mocked; no broker or DB access. The on-disk peak store key is
``peak_equity`` (JsonPeakStore format) — do not change it here.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.quant.strategies.hma_stoch_1h.strategy import HMAStoch1HStrategy


def _build(peak_file: Path) -> HMAStoch1HStrategy:
    """Construct a strategy with MT5 mocked. Caller pre-seeds mock returns."""
    return HMAStoch1HStrategy(
        environment="test",
        peak_store_path=str(peak_file),
        mt5_base_url="http://mock:5001",
    )


@patch("app.quant.strategies.hma_stoch_1h.strategy.MT5APIClient")
def test_evaluate_seeds_peak_on_first_call(mock_mt5_cls, tmp_path: Path) -> None:
    peak_file = tmp_path / "peak.json"
    mock_mt5 = mock_mt5_cls.return_value
    mock_mt5.get_account_info.return_value = {"equity": 100.0, "balance": 100.0}
    # No candles → evaluation bails after the guard has already seeded the peak.
    mock_mt5.get_market_rates.return_value = {"rates": []}

    strat = _build(peak_file)
    strat.evaluate()

    assert peak_file.exists()
    assert json.loads(peak_file.read_text())["peak_equity"] == pytest.approx(100.0)


@patch("app.quant.strategies.hma_stoch_1h.strategy.MT5APIClient")
def test_evaluate_halts_before_signal_work_when_tripped(
    mock_mt5_cls, tmp_path: Path
) -> None:
    peak_file = tmp_path / "peak.json"
    peak_file.write_text(json.dumps({"peak_equity": 100.0}))

    mock_mt5 = mock_mt5_cls.return_value
    mock_mt5.get_account_info.return_value = {"equity": 84.0, "balance": 84.0}  # 16% dd
    mock_mt5.get_open_positions.return_value = []
    mock_mt5.get_market_rates.side_effect = AssertionError(
        "get_market_rates must not be called when guard is tripped"
    )
    mock_mt5.send_order.side_effect = AssertionError(
        "send_order must not be called when guard is tripped"
    )

    strat = _build(peak_file)
    result = strat.evaluate()

    assert result is None
    mock_mt5.get_market_rates.assert_not_called()
    mock_mt5.send_order.assert_not_called()
    # A breach must never advance the peak.
    assert json.loads(peak_file.read_text())["peak_equity"] == pytest.approx(100.0)


@patch("app.quant.strategies.hma_stoch_1h.strategy.MT5APIClient")
def test_evaluate_does_not_trip_just_below_threshold(
    mock_mt5_cls, tmp_path: Path
) -> None:
    """14% drawdown is within the 15% tolerance — signal work must be reached."""
    peak_file = tmp_path / "peak.json"
    peak_file.write_text(json.dumps({"peak_equity": 100.0}))

    mock_mt5 = mock_mt5_cls.return_value
    mock_mt5.get_account_info.return_value = {"equity": 86.0, "balance": 86.0}  # 14% dd
    mock_mt5.get_open_positions.return_value = []
    mock_mt5.get_market_rates.return_value = {"rates": []}

    strat = _build(peak_file)
    strat.evaluate()

    mock_mt5.get_market_rates.assert_called()  # signal work was reached


@patch("app.quant.strategies.hma_stoch_1h.strategy.MT5APIClient")
def test_guard_advances_peak_before_candle_fetch(
    mock_mt5_cls, tmp_path: Path
) -> None:
    """The peak must track new equity highs even when there is no tradeable data.

    The guard sits ABOVE the candle fetch / session filter, so the peak tracks
    equity 24/7 rather than only on cycles that reach signal evaluation.
    """
    peak_file = tmp_path / "peak.json"
    peak_file.write_text(json.dumps({"peak_equity": 100.0}))

    mock_mt5 = mock_mt5_cls.return_value
    mock_mt5.get_account_info.return_value = {"equity": 130.0, "balance": 130.0}
    mock_mt5.get_market_rates.return_value = {"rates": []}  # no tradeable data

    strat = _build(peak_file)
    strat.evaluate()

    assert json.loads(peak_file.read_text())["peak_equity"] == pytest.approx(130.0)
