import logging
import time as _time
from typing import Optional

import pandas as pd

from app.quant.strategies.base import BaseStrategy
from app.quant.strategies.indicators import hma, stochastic, atr
from app.quant.strategies.sizer import calculate_lot_size
from app.adapters.mt5_api import MT5APIClient
from app.adapters.utils.create import create_trade as create_trade_record
from app.config import settings
from app.quant.strategies.drawdown_guard import (
    DrawdownGuard,
    JsonPeakStore,
)


LOGGER = logging.getLogger(__name__)

SYMBOL = "XAUUSD"
MAGIC_NUMBER = 1500015


class HMAStochM15Strategy(BaseStrategy):
    """
    HMA + Stochastic strategy on the M15 timeframe for XAUUSD.

    Entry: HMA direction + price side + stochastic cross from oversold/overbought.
    Additional guard: raw ATR must be >= XAUUSD_MIN_ATR (rejects low-volatility signals).
    Risk: ATR-based position sizing at half the 1H risk level.
    """

    def __init__(
        self,
        *,
        environment: str = "test",
        hma_period: int = 21,
        stoch_k_period: int = 14,
        stoch_d_period: int = 3,
        stoch_smooth_k: int = 3,
        atr_period: int = 14,
        sl_atr_mult: float = 1.5,
        tp_atr_mult: float = 2.5,
        risk_pct: float = 0.01,
        magic_number: int = MAGIC_NUMBER,
        candle_count: int = 200,
        mt5_base_url: Optional[str] = None,
        min_atr_for_signal: float = 5.0,  # M15: same regime filter as v1.0 had
        max_drawdown_pct: float = 0.20,
        peak_store_path: str = "/var/lib/qhf/peak_equity_HMAM15.json",
    ):
        super().__init__(environment=environment)
        self.hma_period = hma_period
        self.stoch_k_period = stoch_k_period
        self.stoch_d_period = stoch_d_period
        self.stoch_smooth_k = stoch_smooth_k
        self.atr_period = atr_period
        self.sl_atr_mult = sl_atr_mult
        self.tp_atr_mult = tp_atr_mult
        self.risk_pct = risk_pct
        self.magic_number = magic_number
        self.candle_count = candle_count
        self.min_atr_for_signal = min_atr_for_signal

        self.drawdown_guard = DrawdownGuard(
            store=JsonPeakStore(peak_store_path),
            max_drawdown_pct=max_drawdown_pct,
        )

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

    def _fetch_candles(self) -> Optional[pd.DataFrame]:
        """Fetch OHLCV from MT5 and return as sorted DataFrame."""
        try:
            data = self.mt5_client.get_market_rates(
                SYMBOL, "M15", count=self.candle_count
            )
            if not data or "rates" not in data:
                LOGGER.warning(f"No rate data for {SYMBOL} M15")
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
            LOGGER.error(f"Error fetching candles: {e}")
            return None

    def _generate_signal(self, df: pd.DataFrame) -> tuple[Optional[str], float]:
        """
        Evaluate last CLOSED candle (iloc[-2]).
        Returns (signal, atr_value) where signal is 'BUY', 'SELL', or None.
        """
        hma_series = hma(df["close"], self.hma_period)
        k, d = stochastic(
            df["high"],
            df["low"],
            df["close"],
            self.stoch_k_period,
            self.stoch_d_period,
            self.stoch_smooth_k,
        )
        atr_series = atr(df["high"], df["low"], df["close"], self.atr_period)

        hma_cur = hma_series.iloc[-2]
        hma_prev = hma_series.iloc[-3]
        k_cur = k.iloc[-2]
        d_cur = d.iloc[-2]
        k_prev = k.iloc[-3]
        d_prev = d.iloc[-3]
        atr_cur = float(atr_series.iloc[-2])
        close_cur = float(df.iloc[-2]["close"])

        if any(
            pd.isna(v) for v in [hma_cur, hma_prev, k_cur, d_cur, k_prev, d_prev]
        ) or pd.isna(atr_cur):
            LOGGER.warning("NaN in indicators — insufficient data for signal")
            return None, 0.0

        hma_cur = float(hma_cur)
        hma_prev = float(hma_prev)
        k_cur = float(k_cur)
        d_cur = float(d_cur)
        k_prev = float(k_prev)
        d_prev = float(d_prev)

        # LONG: HMA rising, price above HMA, stoch %K crossed above %D from below 20
        if (
            hma_cur > hma_prev
            and close_cur > hma_cur
            and k_prev < d_prev
            and k_cur > d_cur
            and k_prev < 20.0
        ):
            return "BUY", atr_cur

        # SHORT: HMA falling, price below HMA, stoch %K crossed below %D from above 80
        if (
            hma_cur < hma_prev
            and close_cur < hma_cur
            and k_prev > d_prev
            and k_cur < d_cur
            and k_prev > 80.0
        ):
            return "SELL", atr_cur

        return None, atr_cur

    def _has_open_position(self) -> bool:
        """Returns True if a position with this magic number is already open."""
        try:
            positions = self.mt5_client.get_open_positions(
                magic=self.magic_number, symbol=SYMBOL
            )
            if positions:
                LOGGER.info(f"Duplicate position: magic={self.magic_number}, skipping")
                return True
            return False
        except Exception as e:
            LOGGER.error(f"Failed to check open positions: {e}")
            return True  # conservative: block order if check fails

    def _compute_sl_tp(
        self, signal: str, entry_price: float, effective_atr: float
    ) -> tuple[float, float]:
        sl_distance = effective_atr * self.sl_atr_mult
        tp_distance = effective_atr * self.tp_atr_mult
        if signal == "BUY":
            return entry_price - sl_distance, entry_price + tp_distance
        return entry_price + sl_distance, entry_price - tp_distance

    def _place_order(
        self,
        signal: str,
        lot_size: float,
        sl: float,
        tp: float,
        login: Optional[int],
    ) -> None:
        """Send market order and record in DB. Logs all outcomes."""
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
                comment="HMAM15",
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
                    timeframe="15M",
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
        start = _time.monotonic()
        LOGGER.info("HMAStochM15 v1.1 evaluation started")

        account_info = self._get_account_info()
        if account_info is None:
            return None
        balance, equity, login = account_info

        if self.drawdown_guard.is_tripped(equity=equity):
            LOGGER.warning(
                f"Drawdown guard tripped: {self.drawdown_guard.diagnostics()}, "
                f"current_equity={equity:.2f}"
            )
            return None
        self.drawdown_guard.update(equity=equity)

        df = self._fetch_candles()
        if df is None or len(df) < self.hma_period + 10:
            LOGGER.warning("Insufficient candle data")
            return None

        signal, atr_value = self._generate_signal(df)
        LOGGER.info(f"Signal={signal} ATR={atr_value:.4f}")

        if signal is None:
            LOGGER.info(f"No signal. Duration={_time.monotonic() - start:.2f}s")
            return None

        if atr_value < self.min_atr_for_signal:
            LOGGER.info(
                f"Signal rejected: ATR {atr_value:.4f} < min_atr_for_signal "
                f"{self.min_atr_for_signal} (regime filter)"
            )
            return None

        if self._has_open_position():
            return None

        entry_price = float(df.iloc[-2]["close"])

        lot_size, effective_atr = calculate_lot_size(
            account_balance=balance,
            atr_value=atr_value,
            risk_pct=self.risk_pct,
            sl_atr_multiplier=self.sl_atr_mult,
        )
        sl, tp = self._compute_sl_tp(signal, entry_price, effective_atr)

        LOGGER.info(
            f"Placing {signal}: symbol={SYMBOL} lots={lot_size} sl={sl:.2f} "
            f"tp={tp:.2f} raw_atr={atr_value:.4f} eff_atr={effective_atr:.4f} "
            f"balance={balance:.2f} peak={self.drawdown_guard.peak_equity}"
        )
        self._place_order(signal, lot_size, sl, tp, login)

        LOGGER.info(
            f"Evaluation complete. Signal={signal} "
            f"Duration={_time.monotonic() - start:.2f}s"
        )
        return signal
