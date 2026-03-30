"""
London Breakout with EMA Filter Strategy

Asset: Configurable (default XAUUSD)
Timeframe: 15 Minutes

Strategy Logic:
1. Track Asian session (01:00-07:00 UTC) high/low range
2. During London window (08:00-11:00 UTC), look for breakouts
3. BUY if: Close > Range High AND Close > 200 EMA AND breakout >= min size
4. SELL if: Close < Range Low AND Close < 200 EMA AND breakout >= min size
5. SL = 2x ATR, TP = 3x risk (1:3 RR)
6. Only one trade per day
"""
import logging
from datetime import datetime, time, timezone
from typing import Optional, Dict, Any, List

import numpy as np
import pandas as pd

from app.quant.strategies.base import BaseStrategy
from app.adapters.mt5_api import MT5APIClient
from app.adapters.utils.create import create_trade as create_trade_record
from app.config import settings


LOGGER = logging.getLogger(__name__)


class LondonBreakoutStrategy(BaseStrategy):
    """
    London Breakout with EMA Filter strategy.
    
    Identifies breakouts of the Asian session range during London open,
    filtered by 200 EMA for trend direction.
    """

    # Default session times (UTC)
    DEFAULT_ASIAN_START = time(1, 0)   # 01:00 UTC
    DEFAULT_ASIAN_END = time(7, 0)     # 07:00 UTC
    DEFAULT_TRADE_START = time(8, 0)   # 08:00 UTC (London open)
    DEFAULT_TRADE_END = time(11, 0)    # 11:00 UTC

    def __init__(
        self,
        *,
        symbol: str = "XAUUSD",
        timeframe: str = "M15",
        mt5_base_url: Optional[str] = None,
        volume_per_order: float = 0.01,
        deviation: int = 20,
        magic_number: int = 2470000,
        # Strategy parameters
        ema_period: int = 200,
        atr_period: int = 14,
        min_breakout_pips: float = 2.0,
        risk_reward_ratio: float = 3.0,
        atr_multiplier: float = 2.0,
        # Session times (configurable)
        asian_start: Optional[time] = None,
        asian_end: Optional[time] = None,
        trade_window_start: Optional[time] = None,
        trade_window_end: Optional[time] = None,
    ):
        super().__init__()
        
        # Symbol and timeframe
        self.symbol = symbol
        self.timeframe = timeframe
        
        # Trading parameters
        self.volume_per_order = volume_per_order
        self.deviation = deviation
        self.magic_number = magic_number
        
        # Strategy parameters
        self.ema_period = ema_period
        self.atr_period = atr_period
        self.min_breakout_pips = min_breakout_pips
        self.risk_reward_ratio = risk_reward_ratio
        self.atr_multiplier = atr_multiplier
        
        # Pip value: For XAUUSD, 1 pip = 0.10 (gold uses 0.01 price increments)
        # For forex pairs like EURUSD, 1 pip = 0.0001
        self.pip_value = self._get_pip_value(symbol)
        self.min_breakout_price = min_breakout_pips * self.pip_value
        
        # Session times
        self.asian_start = asian_start or self.DEFAULT_ASIAN_START
        self.asian_end = asian_end or self.DEFAULT_ASIAN_END
        self.trade_window_start = trade_window_start or self.DEFAULT_TRADE_START
        self.trade_window_end = trade_window_end or self.DEFAULT_TRADE_END
        
        # State variables (reset daily)
        self.range_high: float = 0.0
        self.range_low: float = float('inf')
        self.is_range_set: bool = False
        self.daily_trade_taken: bool = False
        self.current_atr: float = 0.0
        self.current_ema: float = 0.0
        self._last_reset_date: Optional[datetime] = None
        
        # MT5 client
        base_url = mt5_base_url or settings.MT5_API_URL
        self.mt5_client = MT5APIClient(base_url=base_url)
        
        # Try to connect
        try:
            self.mt5_client.connect()
        except Exception as e:
            LOGGER.warning(f"Could not connect MT5 at init: {e}")
        
        self.account_leverage: float = 500.0
        self.account_login = None
        try:
            info = self.mt5_client.get_account_info()
            self.account_leverage = float(info.get("leverage", self.account_leverage))
            self.account_login = int(info.get("login")) if info.get("login") else None
        except Exception as e:
            LOGGER.warning(f"Failed to get MT5 account info: {e}")

    def _get_pip_value(self, symbol: str) -> float:
        """Get pip value for a symbol."""
        symbol_upper = symbol.upper()
        if "XAU" in symbol_upper or "GOLD" in symbol_upper:
            return 0.10  # Gold: 1 pip = 0.10
        elif "JPY" in symbol_upper:
            return 0.01  # JPY pairs: 1 pip = 0.01
        else:
            return 0.0001  # Standard forex: 1 pip = 0.0001

    def _get_current_time_utc(self) -> datetime:
        """Get current UTC time."""
        return datetime.now(timezone.utc)

    def _is_asian_session(self, current_time: datetime) -> bool:
        """Check if current time is within Asian session."""
        t = current_time.time()
        return self.asian_start <= t <= self.asian_end

    def _is_trade_window(self, current_time: datetime) -> bool:
        """Check if current time is within London trade window."""
        t = current_time.time()
        return self.trade_window_start <= t <= self.trade_window_end

    def _should_reset_daily(self, current_time: datetime) -> bool:
        """Check if we should reset daily state (at Asian session start)."""
        if self._last_reset_date is None:
            return True
        return current_time.date() != self._last_reset_date.date()

    def _reset_daily_state(self, current_time: datetime):
        """Reset state for a new trading day."""
        LOGGER.info(f"Resetting daily state for {current_time.date()}")
        self.range_high = 0.0
        self.range_low = float('inf')
        self.is_range_set = False
        self.daily_trade_taken = False
        self._last_reset_date = current_time

    def _fetch_candles(self) -> Optional[pd.DataFrame]:
        """Fetch OHLC candles from MT5 API and convert to DataFrame."""
        try:
            data = self.mt5_client.get_market_rates(self.symbol, self.timeframe)
            
            if not data or "rates" not in data:
                LOGGER.warning(f"No rate data received for {self.symbol}")
                return None
            
            rates = data["rates"]
            if not rates:
                return None
            
            df = pd.DataFrame(rates)
            
            # Ensure required columns exist
            required = ["time", "open", "high", "low", "close"]
            if not all(col in df.columns for col in required):
                LOGGER.warning(f"Missing required columns: {df.columns.tolist()}")
                return None
            
            # Convert time to datetime if needed
            if not pd.api.types.is_datetime64_any_dtype(df["time"]):
                df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
            
            df = df.sort_values("time").reset_index(drop=True)
            return df
            
        except Exception as e:
            LOGGER.error(f"Error fetching candles: {e}")
            return None

    def _calculate_indicators(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate EMA and ATR using numpy (no external TA library needed)."""
        result = {"ema": 0.0, "atr": 0.0}
        
        try:
            closes = df["close"].values
            highs = df["high"].values
            lows = df["low"].values
            
            # Calculate EMA
            if len(closes) >= self.ema_period:
                result["ema"] = self._calculate_ema(closes, self.ema_period)
            
            # Calculate ATR
            if len(df) >= self.atr_period + 1:
                result["atr"] = self._calculate_atr(highs, lows, closes, self.atr_period)
            
        except Exception as e:
            LOGGER.error(f"Error calculating indicators: {e}")
        
        return result

    def _calculate_ema(self, prices: np.ndarray, period: int) -> float:
        """
        Calculate Exponential Moving Average using numpy.
        
        EMA = (Price * k) + (Previous EMA * (1 - k))
        where k = 2 / (period + 1)
        """
        if len(prices) < period:
            return 0.0
        
        k = 2.0 / (period + 1)
        
        # Start with SMA for first EMA value
        ema = np.mean(prices[:period])
        
        # Apply EMA formula for remaining prices
        for price in prices[period:]:
            ema = (price * k) + (ema * (1 - k))
        
        return float(ema)

    def _calculate_atr(
        self, 
        highs: np.ndarray, 
        lows: np.ndarray, 
        closes: np.ndarray, 
        period: int
    ) -> float:
        """
        Calculate Average True Range using numpy.
        
        True Range = max(
            high - low,
            abs(high - previous_close),
            abs(low - previous_close)
        )
        ATR = SMA of True Range over period
        """
        if len(highs) < period + 1:
            return 0.0
        
        # Calculate True Range for each bar (starting from index 1)
        true_ranges = []
        for i in range(1, len(highs)):
            high_low = highs[i] - lows[i]
            high_prev_close = abs(highs[i] - closes[i - 1])
            low_prev_close = abs(lows[i] - closes[i - 1])
            tr = max(high_low, high_prev_close, low_prev_close)
            true_ranges.append(tr)
        
        # Return average of last 'period' true ranges
        if len(true_ranges) < period:
            return float(np.mean(true_ranges))
        
        return float(np.mean(true_ranges[-period:]))

    def _update_range(self, candle_high: float, candle_low: float):
        """Update Asian session range high/low."""
        self.range_high = max(self.range_high, candle_high)
        self.range_low = min(self.range_low, candle_low)
        self.is_range_set = True
        LOGGER.debug(f"Range updated: High={self.range_high}, Low={self.range_low}")

    def _check_buy_signal(self, close: float) -> bool:
        """
        Check BUY signal conditions:
        1. Close > Asian Range High
        2. Close > 200 EMA (uptrend)
        3. Breakout strength >= min breakout size
        """
        if close <= self.range_high:
            return False
        if close <= self.current_ema:
            return False
        
        breakout_strength = close - self.range_high
        if breakout_strength < self.min_breakout_price:
            LOGGER.debug(f"BUY: Breakout too small: {breakout_strength} < {self.min_breakout_price}")
            return False
        
        LOGGER.info(f"BUY signal: Close={close}, RangeHigh={self.range_high}, EMA={self.current_ema}")
        return True

    def _check_sell_signal(self, close: float) -> bool:
        """
        Check SELL signal conditions:
        1. Close < Asian Range Low
        2. Close < 200 EMA (downtrend)
        3. Breakout strength >= min breakout size
        """
        if close >= self.range_low:
            return False
        if close >= self.current_ema:
            return False
        
        breakout_strength = self.range_low - close
        if breakout_strength < self.min_breakout_price:
            LOGGER.debug(f"SELL: Breakout too small: {breakout_strength} < {self.min_breakout_price}")
            return False
        
        LOGGER.info(f"SELL signal: Close={close}, RangeLow={self.range_low}, EMA={self.current_ema}")
        return True

    def _execute_buy_order(self, entry_price: float):
        """Execute BUY order with ATR-based SL and RR-based TP."""
        # SL = Entry - 2x ATR
        stop_loss = entry_price - (self.atr_multiplier * self.current_atr)
        stop_distance = entry_price - stop_loss
        
        # TP = Entry + (SL distance * RR ratio)
        take_profit = entry_price + (stop_distance * self.risk_reward_ratio)
        
        LOGGER.info(
            f"Executing BUY: Entry={entry_price}, SL={stop_loss}, TP={take_profit}, "
            f"ATR={self.current_atr}"
        )
        
        self._send_order("BUY", entry_price, stop_loss, take_profit)

    def _execute_sell_order(self, entry_price: float):
        """Execute SELL order with ATR-based SL and RR-based TP."""
        # SL = Entry + 2x ATR
        stop_loss = entry_price + (self.atr_multiplier * self.current_atr)
        stop_distance = stop_loss - entry_price
        
        # TP = Entry - (SL distance * RR ratio)
        take_profit = entry_price - (stop_distance * self.risk_reward_ratio)
        
        LOGGER.info(
            f"Executing SELL: Entry={entry_price}, SL={stop_loss}, TP={take_profit}, "
            f"ATR={self.current_atr}"
        )
        
        self._send_order("SELL", entry_price, stop_loss, take_profit)

    def _send_order(self, action: str, entry: float, sl: float, tp: float):
        """Send order to MT5 and record in database."""
        try:
            order = self.mt5_client.send_order(
                action=action,
                symbol=self.symbol,
                volume=self.volume_per_order,
                order_type="MARKET",
                sl=sl,
                tp=tp,
                deviation=self.deviation,
                magic=self.magic_number,
                comment=f"LB_{action}",
            )
            
            if order and order.get("success") is True:
                self.daily_trade_taken = True
                executed_price = order.get("price", entry)
                executed_volume = order.get("volume", self.volume_per_order)
                account_instance = None
                if getattr(self, "account_login", None):
                    from app.trades.models import Account
                    account_instance = Account.objects.filter(login=self.account_login).first()
                
                try:
                    create_trade_record(
                        order,
                        symbol=self.symbol,
                        direction=action,
                        entry_price=float(executed_price),
                        order_volume=float(executed_volume),
                        account=account_instance,
                        market_type="FOREX" if "XAU" not in self.symbol.upper() else "COMMODITIES",
                        strategy=self.__class__.__name__,
                        timeframe=self.timeframe,
                        sl=sl,
                        tp=tp,
                    )
                    LOGGER.info(f"Trade record created for order {order.get('order')}")
                except Exception as e:
                    LOGGER.error(f"Failed to create trade record: {e}")
            else:
                retcode = order.get("retcode", "unknown") if order else "no response"
                LOGGER.error(f"Order failed: {retcode}")
                
        except Exception as e:
            LOGGER.error(f"Order execution error: {e}")

    def run(self):
        """
        Main strategy execution - called on every 15-min candle close.
        
        Phases:
        1. Reset state at Asian session start
        2. Build range during Asian session
        3. Hunt for breakouts during London window
        """
        current_time = self._get_current_time_utc()
        LOGGER.info(f"Running London Breakout strategy at {current_time}")
        
        # Reset at start of new day (Asian session start)
        if self._should_reset_daily(current_time) and self._is_asian_session(current_time):
            self._reset_daily_state(current_time)
        
        # Fetch candle data
        df = self._fetch_candles()
        if df is None or df.empty:
            LOGGER.warning("No candle data available, skipping")
            return
        
        # Get latest candle
        latest = df.iloc[-1]
        candle_high = float(latest["high"])
        candle_low = float(latest["low"])
        candle_close = float(latest["close"])
        
        # Calculate indicators
        indicators = self._calculate_indicators(df)
        self.current_ema = indicators["ema"]
        self.current_atr = indicators["atr"]
        
        LOGGER.debug(
            f"Candle: H={candle_high}, L={candle_low}, C={candle_close}, "
            f"EMA={self.current_ema}, ATR={self.current_atr}"
        )
        
        # === PHASE 1: BUILD THE RANGE (Asian Session) ===
        if self._is_asian_session(current_time):
            self._update_range(candle_high, candle_low)
            LOGGER.info(f"Asian session: Range H={self.range_high}, L={self.range_low}")
            return
        
        # === PHASE 2: HUNT FOR BREAKOUT (London Window) ===
        if self._is_trade_window(current_time):
            # Only proceed if range is set and no trade taken today
            if not self.is_range_set:
                LOGGER.info("Trade window but range not set, skipping")
                return
            
            if self.daily_trade_taken:
                LOGGER.info("Daily trade already taken, skipping")
                return
            
            # Validate ATR is available
            if self.current_atr <= 0:
                LOGGER.warning("ATR not available, cannot calculate SL/TP")
                return
            
            # Check for BUY signal
            if self._check_buy_signal(candle_close):
                self._execute_buy_order(candle_close)
                return
            
            # Check for SELL signal
            if self._check_sell_signal(candle_close):
                self._execute_sell_order(candle_close)
                return
            
            LOGGER.info("No breakout signal detected")
        else:
            LOGGER.debug(f"Outside trading windows: {current_time.time()}")
