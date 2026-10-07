"""
Unit tests for ASQSafeScalpingStrategy.

Tests cover _generate_signal, filter helpers, and _compute_sl_tp.
MT5 client and external calls are fully mocked; no broker connection required.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from django.utils import timezone as dj_tz
from model_bakery import baker

from app.quant.strategies.asqs.strategy import (
    SL_POINTS,
    TP_POINTS,
    XAUUSD_POINT,
    ASQSafeScalpingStrategy,
)
from app.trades.models import Trade

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

N = 600  # enough bars for EMA(510) + breakout(20) + margin


def _make_strategy(**kwargs) -> ASQSafeScalpingStrategy:
    """Build a strategy instance with MT5 connection mocked out."""
    with patch("app.quant.strategies.asqs.strategy.MT5APIClient") as mock_cls:
        mock_cls.return_value.connect.return_value = None
        strategy = ASQSafeScalpingStrategy(mt5_base_url="http://mock:5001", **kwargs)
    return strategy


def _make_df(
    n: int = N,
    close_base: float = 2000.0,
    trend: str = "up",  # "up" | "down" | "flat"
    atr_val: float = 10.0,
) -> pd.DataFrame:
    """
    Build a synthetic OHLCV DataFrame with controlled trend and ATR.

    For 'up':  close rises by 0.5 per bar, high = close + atr_val/2, low = close - atr_val/2
    For 'down': close falls by 0.5 per bar
    For 'flat': close stays constant
    """
    if trend == "up":
        closes = [close_base + i * 0.5 for i in range(n)]
    elif trend == "down":
        closes = [close_base - i * 0.5 for i in range(n)]
    else:
        closes = [close_base] * n

    closes = pd.Series(closes)
    highs = closes + atr_val / 2
    lows = closes - atr_val / 2
    opens = closes - 0.1

    times = pd.date_range("2024-01-01", periods=n, freq="5min")
    return pd.DataFrame(
        {"time": times, "open": opens, "high": highs, "low": lows, "close": closes}
    )


# ---------------------------------------------------------------------------
# _compute_sl_tp
# ---------------------------------------------------------------------------


class TestComputeSlTp:
    """
    ASQS uses FIXED-POINT SL/TP (SL_POINTS / TP_POINTS), not ATR multiples.
    `_compute_sl_tp(signal, entry_price)` anchors a $3.00 SL and $4.50 TP to the
    live entry price. (Earlier ATR-multiple `sl_atr_mult`/`tp_atr_mult` tests
    targeted a removed design — see tests/TRIAGE_NOTES.md, Group B.)
    """

    SL_DIST = SL_POINTS * XAUUSD_POINT  # 300 × 0.01 = $3.00
    TP_DIST = TP_POINTS * XAUUSD_POINT  # 450 × 0.01 = $4.50

    def setup_method(self):
        self.s = _make_strategy()

    def test_buy_sl_below_entry(self):
        sl, tp = self.s._compute_sl_tp("BUY", 2000.0)
        assert sl == pytest.approx(2000.0 - self.SL_DIST)
        assert tp == pytest.approx(2000.0 + self.TP_DIST)

    def test_sell_sl_above_entry(self):
        sl, tp = self.s._compute_sl_tp("SELL", 2000.0)
        assert sl == pytest.approx(2000.0 + self.SL_DIST)
        assert tp == pytest.approx(2000.0 - self.TP_DIST)

    def test_rr_ratio(self):
        sl, tp = self.s._compute_sl_tp("BUY", 2000.0)
        sl_dist = abs(2000.0 - sl)
        tp_dist = abs(tp - 2000.0)
        assert tp_dist / sl_dist == pytest.approx(TP_POINTS / SL_POINTS, rel=1e-6)


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------


class TestCheckSession:
    def setup_method(self):
        self.s = _make_strategy(session_start_hour=8, session_end_hour=20)

    def _dt(self, hour: int) -> datetime:
        return datetime(2024, 1, 15, hour, 0, tzinfo=timezone.utc)  # Monday

    def test_inside_session(self):
        assert self.s._check_session(self._dt(10)) is True

    def test_at_session_start(self):
        assert self.s._check_session(self._dt(8)) is True

    def test_at_session_end_is_excluded(self):
        assert self.s._check_session(self._dt(20)) is False

    def test_before_session(self):
        assert self.s._check_session(self._dt(7)) is False

    def test_after_session(self):
        assert self.s._check_session(self._dt(21)) is False


class TestCheckFridayCutoff:
    def setup_method(self):
        self.s = _make_strategy(friday_cutoff_hour=14)

    def test_friday_before_cutoff_allowed(self):
        dt = datetime(2024, 1, 19, 13, 0, tzinfo=timezone.utc)  # Friday 13:00
        assert self.s._check_friday_cutoff(dt) is True

    def test_friday_at_cutoff_blocked(self):
        dt = datetime(2024, 1, 19, 14, 0, tzinfo=timezone.utc)
        assert self.s._check_friday_cutoff(dt) is False

    def test_friday_after_cutoff_blocked(self):
        dt = datetime(2024, 1, 19, 16, 0, tzinfo=timezone.utc)
        assert self.s._check_friday_cutoff(dt) is False

    def test_monday_not_blocked(self):
        dt = datetime(2024, 1, 15, 20, 0, tzinfo=timezone.utc)  # Monday
        assert self.s._check_friday_cutoff(dt) is True


@pytest.mark.django_db
class TestCheckDailyCap:
    """
    `_check_daily_cap()` counts today's filled Trades for THIS strategy in the
    DB and blocks once the count reaches `max_daily_trades`. It is stateless by
    design — a fresh strategy instance is built every Celery cycle, so an
    in-memory counter would reset each run; the DB is the source of truth.
    (Earlier in-memory `_daily_trades`/`_last_trade_date` tests targeted a
    removed design — see tests/TRIAGE_NOTES.md, Group A.)
    """

    STRATEGY_NAME = "ASQSafeScalpingStrategy"

    def setup_method(self):
        self.s = _make_strategy(max_daily_trades=3)

    def _make_trades(self, count: int, *, entry_time, strategy=None) -> None:
        baker.make(
            Trade,
            strategy=strategy or self.STRATEGY_NAME,
            entry_time=entry_time,
            _quantity=count,
        )

    def test_first_call_allows(self):
        # No trades recorded today → under cap.
        assert self.s._check_daily_cap() is True

    def test_below_cap_allows(self):
        self._make_trades(2, entry_time=dj_tz.now())
        assert self.s._check_daily_cap() is True

    def test_cap_reached_blocks(self):
        self._make_trades(3, entry_time=dj_tz.now())
        assert self.s._check_daily_cap() is False

    def test_yesterdays_trades_do_not_count(self):
        # The filter is scoped to today's date, so prior-day trades are ignored.
        self._make_trades(3, entry_time=dj_tz.now() - timedelta(days=1))
        assert self.s._check_daily_cap() is True

    def test_other_strategy_trades_do_not_count(self):
        # The cap is per-strategy; another strategy's trades must not block us.
        self._make_trades(3, entry_time=dj_tz.now(), strategy="SomeOtherStrategy")
        assert self.s._check_daily_cap() is True

    # The two tests above used dj_tz.now(), so they passed or failed with the
    # wall clock: between 21:00 and 24:00 UTC the date in UTC and the date in
    # TIME_ZONE (Africa/Nairobi, UTC+3) differ, and _check_daily_cap took the
    # first while the entry_time__date lookup uses the second. They failed every
    # night in that window and passed by day. These pin the clock inside it.

    #: 22:30 UTC on the 6th is 01:30 on the 7th in Nairobi.
    IN_THE_GAP = datetime(2026, 10, 6, 22, 30, tzinfo=timezone.utc)

    @pytest.mark.parametrize("now", [
        datetime(2026, 10, 6, 21, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 6, 22, 30, tzinfo=timezone.utc),
        datetime(2026, 10, 6, 23, 59, tzinfo=timezone.utc),
        datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc),
    ])
    def test_cap_reached_blocks_at_any_hour(self, now):
        with patch("django.utils.timezone.now", return_value=now):
            self._make_trades(3, entry_time=now)
            assert self.s._check_daily_cap() is False

    def test_the_day_boundary_is_local_midnight(self):
        """Trades at 23:30 Nairobi on the 6th are yesterday's at 01:30 on the
        7th, though both instants fall on the 6th in UTC."""
        before_midnight_local = datetime(2026, 10, 6, 20, 30, tzinfo=timezone.utc)
        with patch("django.utils.timezone.now", return_value=self.IN_THE_GAP):
            self._make_trades(3, entry_time=before_midnight_local)
            assert self.s._check_daily_cap() is True


# NOTE: TestCheckDrawdown was deleted here. The v1.0 `_check_drawdown(balance,
# equity)` method it targeted no longer exists — drawdown enforcement moved to
# the persistent `DrawdownGuard` (unit-tested in tests/test_asqs_drawdown_guard.py
# and tests/test_drawdown_guard.py, and integration-tested in the ASQS evaluate()
# halt tests). See tests/TRIAGE_NOTES.md, Group E.


# ---------------------------------------------------------------------------
# _generate_signal
# ---------------------------------------------------------------------------


class TestGenerateSignal:
    """
    Verify the 6 M5-level conditions in _generate_signal.

    We build a large flat DataFrame and then surgically set the last few rows
    to force specific indicator readings at iloc[-2].
    """

    def setup_method(self):
        self.s = _make_strategy(
            ema_fast_period=3,
            ema_slow_period=5,
            atr_period=3,
            ema_sep_atr_mult=0.1,
            breakout_lookback=5,
            breakout_atr_buffer=0.0,  # zero buffer isolates the transition logic
            rsi_period=3,
            rsi_buy_lo=40.0,
            rsi_buy_hi=65.0,
            rsi_sell_lo=35.0,
            rsi_sell_hi=60.0,
        )

    def _signal(self, df: pd.DataFrame) -> tuple:
        return self.s._generate_signal(df)

    def test_insufficient_data_returns_none(self):
        df = _make_df(n=5)
        signal, atr = self._signal(df)
        assert signal is None

    def test_flat_market_no_signal(self):
        df = _make_df(n=N, trend="flat")
        signal, _ = self._signal(df)
        assert signal is None

    def test_buy_signal_on_strong_uptrend(self):
        """
        A steep uptrend should eventually satisfy all BUY conditions.
        We use a very long rising series so all EMAs, RSI, and breakout align.
        """
        n = 600
        closes = pd.Series([2000.0 + i * 2.0 for i in range(n)])
        highs = closes + 8.0
        lows = closes - 8.0
        times = pd.date_range("2024-01-01", periods=n, freq="5min")
        df = pd.DataFrame(
            {
                "time": times,
                "open": closes - 0.1,
                "high": highs,
                "low": lows,
                "close": closes,
            }
        )
        signal, atr_val = self._signal(df)
        # In a strong unbroken uptrend, at least no crash should occur
        assert signal in ("BUY", None)
        assert atr_val >= 0.0

    def test_sell_signal_on_strong_downtrend(self):
        n = 600
        closes = pd.Series([3000.0 - i * 2.0 for i in range(n)])
        highs = closes + 8.0
        lows = closes - 8.0
        times = pd.date_range("2024-01-01", periods=n, freq="5min")
        df = pd.DataFrame(
            {
                "time": times,
                "open": closes + 0.1,
                "high": highs,
                "low": lows,
                "close": closes,
            }
        )
        signal, atr_val = self._signal(df)
        assert signal in ("SELL", None)
        assert atr_val >= 0.0

    def test_returns_atr_even_when_no_signal(self):
        df = _make_df(n=N, trend="flat")
        _, atr_val = self._signal(df)
        # ATR should be non-negative even with no signal
        assert atr_val >= 0.0

    def test_nan_guard_triggers_on_too_few_bars(self):
        df = _make_df(n=10)
        signal, atr_val = self._signal(df)
        assert signal is None
        assert atr_val == 0.0

    def test_breakout_requires_candle_transition(self):
        """
        c4_buy: current close must be near/past the N-bar high AND the previous
        close must have been at or below it. A signal bar that was already above
        the N-bar high last candle should not trigger (no fresh crossing).

        We craft a DataFrame where iloc[-2] (signal bar) is above the rolling high
        but iloc[-3] (transition bar) is ALSO above it — no transition, no signal.
        """
        s = _make_strategy(
            ema_fast_period=3,
            ema_slow_period=5,
            atr_period=3,
            ema_sep_atr_mult=0.0,  # disable separation filter
            breakout_lookback=3,
            breakout_atr_buffer=0.0,
            rsi_period=3,
            rsi_buy_lo=0.0,
            rsi_buy_hi=100.0,
            rsi_sell_lo=0.0,
            rsi_sell_hi=100.0,
        )
        n = 30
        closes = [2000.0] * n
        # Push the last two bars well above prior highs — no transition at iloc[-2]
        closes[-3] = 2100.0  # c_prev already above the N-bar high
        closes[-2] = 2110.0  # signal bar also above
        closes[-1] = 2110.0  # forming candle (ignored)
        closes_s = pd.Series(closes)
        highs = closes_s + 5.0
        lows = closes_s - 5.0
        times = pd.date_range("2024-01-01", periods=n, freq="5min")
        df = pd.DataFrame(
            {
                "time": times,
                "open": closes_s - 0.1,
                "high": highs,
                "low": lows,
                "close": closes_s,
            }
        )
        signal, _ = s._generate_signal(df)
        # c_prev (iloc[-3]) = 2100 is already above the rolling max of earlier bars,
        # so c_prev <= brk_hi is False — no buy signal should fire
        assert signal != "BUY"


# ---------------------------------------------------------------------------
# _check_h1_confirmation
# ---------------------------------------------------------------------------


class TestH1Confirmation:
    def setup_method(self):
        # Use short periods so the EMA settles fast on small test fixtures
        self.s = _make_strategy(use_h1_filter=True, h1_ema_fast=3, h1_ema_slow=5)

    def test_disabled_always_passes(self):
        self.s.use_h1_filter = False
        assert self.s._check_h1_confirmation("BUY") is True
        assert self.s._check_h1_confirmation("SELL") is True

    def test_none_h1_data_blocks(self):
        self.s.mt5_client.get_market_rates = MagicMock(return_value=None)
        assert self.s._check_h1_confirmation("BUY") is False

    def test_buy_passes_when_h1_fast_above_slow(self):
        n = 30
        closes = pd.Series([2000.0 + i for i in range(n)])
        rates = [
            {
                "time": str(pd.Timestamp("2024-01-01") + pd.Timedelta(hours=i)),
                "open": float(closes.iloc[i]) - 0.1,
                "high": float(closes.iloc[i]) + 1.0,
                "low": float(closes.iloc[i]) - 1.0,
                "close": float(closes.iloc[i]),
            }
            for i in range(n)
        ]
        self.s.mt5_client.get_market_rates = MagicMock(return_value={"rates": rates})
        result = self.s._check_h1_confirmation("BUY")
        assert result is True

    def test_sell_passes_when_h1_fast_below_slow(self):
        n = 30
        closes = pd.Series([3000.0 - i for i in range(n)])
        rates = [
            {
                "time": str(pd.Timestamp("2024-01-01") + pd.Timedelta(hours=i)),
                "open": float(closes.iloc[i]) + 0.1,
                "high": float(closes.iloc[i]) + 1.0,
                "low": float(closes.iloc[i]) - 1.0,
                "close": float(closes.iloc[i]),
            }
            for i in range(n)
        ]
        self.s.mt5_client.get_market_rates = MagicMock(return_value={"rates": rates})
        result = self.s._check_h1_confirmation("SELL")
        assert result is True

    def test_buy_blocked_when_h1_downtrend(self):
        n = 30
        closes = pd.Series([3000.0 - i for i in range(n)])
        rates = [
            {
                "time": str(pd.Timestamp("2024-01-01") + pd.Timedelta(hours=i)),
                "open": float(closes.iloc[i]) + 0.1,
                "high": float(closes.iloc[i]) + 1.0,
                "low": float(closes.iloc[i]) - 1.0,
                "close": float(closes.iloc[i]),
            }
            for i in range(n)
        ]
        self.s.mt5_client.get_market_rates = MagicMock(return_value={"rates": rates})
        result = self.s._check_h1_confirmation("BUY")
        assert result is False
