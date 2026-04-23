import logging
import time as _time
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import numpy as np

from app.quant.strategies.base import BaseStrategy
from app.quant.strategies.indicators import atr as calc_atr
from app.quant.strategies.sizer import calculate_lot_size
from app.adapters.mt5_api import MT5APIClient
from app.adapters.utils.create import create_trade as create_trade_record
from app.config import settings


LOGGER = logging.getLogger(__name__)

SYMBOL = "XAUUSD"
MAGIC_NUMBER = 1500020


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


class ASQSafeScalpingStrategy(BaseStrategy):
    """
    ASQ SafeScalping v1.20 — 7-condition breakout scalper for XAUUSD.

    Faithfully translates the MT5 EA by AlgoSphere Quant (Robin2.0):
      https://www.mql5.com/en/code/71189

    Entry requires ALL seven conditions to align simultaneously:
      1. EMA(fast) vs EMA(slow) trend direction
      2. ATR-based minimum EMA separation (chop filter)
      3. Close on correct side of both EMAs
      4. N-bar breakout with ATR buffer
      5. RSI in healthy zone (not overbought/oversold)
      6. Momentum: close vs prior close
      7. (Optional) H1 EMA(50/200) higher-timeframe confirmation

    Risk: single position, ATR-based SL/TP, percent equity sizing,
          drawdown auto-pause, daily trade cap, session & Friday filters.
          No martingale, no grid, no hedging.

    LIMITATIONS vs the MT5 EA:
      - Spread filter: not modeled (requires real-time bid/ask)
      - News filter: not modeled (requires external calendar)
      - Breakeven, trailing stop, partial close at TP1: post-entry management
        handled by MT5's OnTick loop. This class handles ENTRY ONLY.
    """

    def __init__(
        self,
        *,
        environment: str = "test",
        # EMA trend — optimized v2 preset (50/200 outperforms generic 150/510 on XAUUSD M5)
        ema_fast_period: int = 50,
        ema_slow_period: int = 200,
        atr_period: int = 50,
        ema_sep_atr_mult: float = 0.3,
        breakout_lookback: int = 15,
        breakout_atr_buffer: float = 0.3,
        rsi_period: int = 14,
        rsi_buy_lo: float = 45.0,
        rsi_buy_hi: float = 65.0,
        rsi_sell_lo: float = 35.0,
        rsi_sell_hi: float = 55.0,
        # MTF on with tighter H1 EMAs per optimized preset (20/50, not 50/200)
        use_h1_filter: bool = True,
        h1_ema_fast: int = 20,
        h1_ema_slow: int = 50,
        sl_atr_mult: float = 1.5,
        tp_atr_mult: float = 3.0,
        risk_pct: float = 0.005,
        max_drawdown_pct: float = 8.0,
        max_daily_trades: int = 4,
        session_start_hour: int = 8,
        session_end_hour: int = 17,
        friday_cutoff_hour: int = 14,
        timeframe: str = "M5",
        candle_count: int = 600,
        magic_number: int = MAGIC_NUMBER,
        mt5_base_url: Optional[str] = None,
    ):
        super().__init__(environment=environment)

        self.ema_fast_period = ema_fast_period
        self.ema_slow_period = ema_slow_period
        self.atr_period = atr_period
        self.ema_sep_atr_mult = ema_sep_atr_mult
        self.breakout_lookback = breakout_lookback
        self.breakout_atr_buffer = breakout_atr_buffer
        self.rsi_period = rsi_period
        self.rsi_buy_lo = rsi_buy_lo
        self.rsi_buy_hi = rsi_buy_hi
        self.rsi_sell_lo = rsi_sell_lo
        self.rsi_sell_hi = rsi_sell_hi
        self.use_h1_filter = use_h1_filter
        self.h1_ema_fast = h1_ema_fast
        self.h1_ema_slow = h1_ema_slow
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult
        self.risk_pct = risk_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.max_daily_trades = max_daily_trades
        self.session_start_hour = session_start_hour
        self.session_end_hour = session_end_hour
        self.friday_cutoff_hour = friday_cutoff_hour
        self.timeframe = timeframe
        self.candle_count = candle_count
        self.magic_number = magic_number

        self._daily_trades: int = 0
        self._last_trade_date: Optional[str] = None

        base_url = mt5_base_url or settings.get_mt5_url(self.environment)
        self.mt5_client = MT5APIClient(base_url=base_url)
        try:
            self.mt5_client.connect()
        except Exception as e:
            LOGGER.warning(f"Could not connect MT5 at init: {e}")

    def _get_account_info(self) -> Optional[tuple[float, float, Optional[int]]]:
        """Returns (balance, equity, login) or None on error."""
        try:
            info = self.mt5_client.get_account_info()
            return (
                float(info.get("balance", 0.0)),
                float(info.get("equity", 0.0)),
                info.get("login"),
            )
        except Exception as e:
            LOGGER.error(f"Failed to get account info: {e}")
            return None

    def _fetch_candles(self, tf: Optional[str] = None) -> Optional[pd.DataFrame]:
        """Fetch OHLCV from MT5. Uses self.timeframe if tf is None."""
        tf = tf or self.timeframe
        count = self.candle_count if tf == self.timeframe else 300
        try:
            data = self.mt5_client.get_market_rates(SYMBOL, tf, count=count)
            if not data or "rates" not in data:
                LOGGER.warning(f"No rate data for {SYMBOL} {tf}")
                return None
            rates = data["rates"]
            if not rates:
                return None
            df = pd.DataFrame(rates)
            required = ["time", "open", "high", "low", "close"]
            if not all(c in df.columns for c in required):
                LOGGER.error(f"Missing columns in rate data: {df.columns.tolist()}")
                return None
            if not pd.api.types.is_datetime64_any_dtype(df["time"]):
                df["time"] = pd.to_datetime(df["time"])
            return df.sort_values("time").reset_index(drop=True)
        except Exception as e:
            LOGGER.error(f"Error fetching {tf} candles: {e}")
            return None

    def _has_open_position(self) -> bool:
        """Returns True if a position with this magic number is already open."""
        try:
            positions = self.mt5_client.get_open_positions(
                magic=self.magic_number, symbol=SYMBOL
            )
            if positions:
                LOGGER.info(f"Open position exists: magic={self.magic_number}, skipping")
                return True
            return False
        except Exception as e:
            LOGGER.error(f"Failed to check open positions: {e}")
            return True  # conservative: block if check fails

    def _check_session(self, now: datetime) -> bool:
        """True if current hour is within the trading session window."""
        hour = now.hour
        if self.session_start_hour < self.session_end_hour:
            return self.session_start_hour <= hour < self.session_end_hour
        # Handle overnight sessions (e.g. 22–06)
        return hour >= self.session_start_hour or hour < self.session_end_hour

    def _check_friday_cutoff(self, now: datetime) -> bool:
        """True if it is NOT past the Friday cutoff."""
        if now.weekday() == 4 and now.hour >= self.friday_cutoff_hour:
            LOGGER.info("Friday cutoff active, blocking trade")
            return False
        return True

    def _check_daily_cap(self, now: datetime) -> bool:
        """True if daily trade count is below the cap. Resets on a new day."""
        today = now.strftime("%Y-%m-%d")
        if self._last_trade_date != today:
            self._daily_trades = 0
            self._last_trade_date = today
        if self._daily_trades >= self.max_daily_trades:
            LOGGER.info(f"Daily trade cap reached ({self.max_daily_trades})")
            return False
        return True

    def _check_drawdown(self, balance: float, equity: float) -> bool:
        """True if drawdown is below the auto-pause threshold."""
        if balance <= 0:
            return False
        dd_pct = ((balance - equity) / balance) * 100
        if dd_pct >= self.max_drawdown_pct:
            LOGGER.warning(
                f"Drawdown auto-pause: {dd_pct:.2f}% >= {self.max_drawdown_pct}%"
            )
            return False
        return True

    def _generate_signal(self, df: pd.DataFrame) -> tuple[Optional[str], float]:
        """
        Evaluate the last CLOSED candle (iloc[-2]).
        Returns (signal, atr_value) where signal is 'BUY', 'SELL', or None.

        All 6 M5-level conditions must pass; condition 7 (H1) is checked separately.
        """
        close = df["close"]
        high = df["high"]
        low = df["low"]

        ema_fast = _ema(close, self.ema_fast_period)
        ema_slow = _ema(close, self.ema_slow_period)
        atr_series = calc_atr(high, low, close, self.atr_period)
        rsi_series = _rsi(close, self.rsi_period)

        # Rolling breakout levels, shifted to exclude the current forming candle
        breakout_hi = high.rolling(self.breakout_lookback).max().shift(1)
        breakout_lo = low.rolling(self.breakout_lookback).min().shift(1)

        idx = -2

        ef = ema_fast.iloc[idx]
        es = ema_slow.iloc[idx]
        atr_val = float(atr_series.iloc[idx])
        rsi_val = rsi_series.iloc[idx]
        c = float(close.iloc[idx])
        c_prev = float(close.iloc[idx - 1])
        brk_hi = breakout_hi.iloc[idx]
        brk_lo = breakout_lo.iloc[idx]

        if any(pd.isna(v) for v in [ef, es, atr_val, rsi_val, brk_hi, brk_lo]):
            LOGGER.warning("NaN in indicators — insufficient data for signal")
            return None, 0.0

        ef = float(ef)
        es = float(es)
        rsi_val = float(rsi_val)
        brk_hi = float(brk_hi)
        brk_lo = float(brk_lo)

        atr_buffer = self.breakout_atr_buffer * atr_val
        ema_gap = abs(ef - es)
        min_gap = self.ema_sep_atr_mult * atr_val

        # ── BUY gate ──────────────────────────────────────────────────
        # Condition 4 mirrors the original EA: c1 > hiH - buf (tolerance, not strict
        # overshoot) AND c2 <= hiH (candle just crossed — fresh breakout only).
        c1_buy = ef > es
        c2_buy = ema_gap > min_gap
        c3_buy = c > ef and c > es
        c4_buy = (c > brk_hi - atr_buffer) and (c_prev <= brk_hi)
        c5_buy = self.rsi_buy_lo <= rsi_val <= self.rsi_buy_hi
        c6_buy = c > c_prev

        if all([c1_buy, c2_buy, c3_buy, c4_buy, c5_buy, c6_buy]):
            LOGGER.debug(
                f"BUY gate passed: EMA_f={ef:.2f} EMA_s={es:.2f} "
                f"RSI={rsi_val:.1f} brkHi={brk_hi:.2f} ATR={atr_val:.4f}"
            )
            return "BUY", atr_val

        # ── SELL gate ─────────────────────────────────────────────────
        c1_sell = ef < es
        c2_sell = ema_gap > min_gap
        c3_sell = c < ef and c < es
        c4_sell = (c < brk_lo + atr_buffer) and (c_prev >= brk_lo)
        c5_sell = self.rsi_sell_lo <= rsi_val <= self.rsi_sell_hi
        c6_sell = c < c_prev

        if all([c1_sell, c2_sell, c3_sell, c4_sell, c5_sell, c6_sell]):
            LOGGER.debug(
                f"SELL gate passed: EMA_f={ef:.2f} EMA_s={es:.2f} "
                f"RSI={rsi_val:.1f} brkLo={brk_lo:.2f} ATR={atr_val:.4f}"
            )
            return "SELL", atr_val

        return None, atr_val

    def _check_h1_confirmation(self, signal: str) -> bool:
        """
        Condition 7: H1 EMA(50/200) higher-timeframe filter.
        Returns True if H1 trend agrees with signal direction, or if filter is disabled.
        """
        if not self.use_h1_filter:
            return True

        h1_df = self._fetch_candles(tf="H1")
        if h1_df is None or len(h1_df) < self.h1_ema_slow + 5:
            LOGGER.warning("Insufficient H1 data for confirmation — blocking signal")
            return False

        h1_ema_fast = _ema(h1_df["close"], self.h1_ema_fast)
        h1_ema_slow = _ema(h1_df["close"], self.h1_ema_slow)

        ef = float(h1_ema_fast.iloc[-2])
        es = float(h1_ema_slow.iloc[-2])

        if signal == "BUY" and ef > es:
            return True
        if signal == "SELL" and ef < es:
            return True

        LOGGER.info(
            f"H1 confirmation failed: signal={signal} "
            f"H1_EMA_fast={ef:.2f} H1_EMA_slow={es:.2f}"
        )
        return False

    def _compute_sl_tp(
        self, signal: str, entry_price: float, atr_value: float
    ) -> tuple[float, float]:
        sl_dist = atr_value * self.sl_atr_mult
        tp_dist = atr_value * self.tp_atr_mult
        if signal == "BUY":
            return entry_price - sl_dist, entry_price + tp_dist
        return entry_price + sl_dist, entry_price - tp_dist

    def _place_order(
        self,
        signal: str,
        lot_size: float,
        sl: float,
        tp: float,
        login: Optional[int],
    ) -> None:
        """Send market order and record in DB."""
        try:
            order = self.mt5_client.send_order(
                action=signal,
                symbol=SYMBOL,
                volume=lot_size,
                order_type="MARKET",
                sl=sl,
                tp=tp,
                deviation=20,
                magic=self.magic_number,
                comment="ASQSS",
            )

            if order and order.get("success") is True:
                account_instance = None
                if login:
                    from app.trades.models import Account
                    account_instance = Account.objects.filter(login=login).first()
                create_trade_record(
                    order,
                    symbol=SYMBOL,
                    direction=signal,
                    entry_price=float(order.get("price", 0.0)),
                    order_volume=lot_size,
                    account=account_instance,
                    market_type="COMMODITIES",
                    strategy=self.__class__.__name__,
                    timeframe=self.timeframe,
                    sl=sl,
                    tp=tp,
                    environment=self.environment,
                )
            else:
                retcode = order.get("retcode", "unknown") if order else "no response"
                retcode_desc = order.get("retcode_description", "") if order else ""
                LOGGER.error(
                    f"Order failed: retcode={retcode} - {retcode_desc}, order={order}"
                )
        except Exception as e:
            LOGGER.error(f"Order execution error: {e}")

    def evaluate(self) -> Optional[str]:
        """
        Full evaluation cycle: filters → data → 7-condition gate → order.
        Returns signal string ('BUY'/'SELL') or None.
        """
        start = _time.monotonic()
        LOGGER.info("ASQSafeScalping evaluation started")

        now = datetime.now(timezone.utc)

        if not self._check_session(now):
            LOGGER.info("Outside trading session, skipping")
            return None

        if not self._check_friday_cutoff(now):
            return None

        if not self._check_daily_cap(now):
            return None

        account_info = self._get_account_info()
        if account_info is None:
            return None
        balance, equity, login = account_info

        if not self._check_drawdown(balance, equity):
            return None

        if balance > 0 and equity < balance * 0.90:
            LOGGER.warning(
                f"Equity safety check failed: equity={equity:.2f}, balance={balance:.2f}"
            )
            return None

        min_bars = self.ema_slow_period + self.breakout_lookback + 20
        df = self._fetch_candles()
        if df is None or len(df) < min_bars:
            LOGGER.warning(
                f"Insufficient candle data: got {len(df) if df is not None else 0}, "
                f"need {min_bars}"
            )
            return None

        signal, atr_value = self._generate_signal(df)
        LOGGER.info(f"Signal={signal} ATR={atr_value:.4f}")

        if signal is None:
            LOGGER.info(f"No signal. Duration={_time.monotonic() - start:.2f}s")
            return None

        if not self._check_h1_confirmation(signal):
            return None

        if self._has_open_position():
            return None

        entry_price = float(df.iloc[-2]["close"])
        lot_size = calculate_lot_size(
            account_balance=balance,
            atr_value=atr_value,
            risk_pct=self.risk_pct,
            sl_atr_multiplier=self.sl_atr_mult,
        )
        sl, tp = self._compute_sl_tp(signal, entry_price, atr_value)

        LOGGER.info(
            f"Placing {signal}: symbol={SYMBOL} lots={lot_size} "
            f"sl={sl:.2f} tp={tp:.2f} atr={atr_value:.4f} balance={balance:.2f}"
        )
        self._place_order(signal, lot_size, sl, tp, login)
        self._daily_trades += 1

        LOGGER.info(
            f"Evaluation complete. Signal={signal} "
            f"Duration={_time.monotonic() - start:.2f}s"
        )
        return signal
