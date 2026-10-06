import time as _time
from datetime import datetime, timezone
from typing import Optional

import pandas as pd

from app.quant.strategies.base import BaseStrategy
from app.quant.strategies.indicators import hma, stochastic, atr
from app.quant.strategies.logging_utils import get_strategy_logger
from app.quant.strategies.sizer import size_order
from app.adapters.mt5_api import MT5APIClient
from app.adapters.broker import MT5Broker, side_from_action
from resources.execution.broker import OrderRequest
from app.adapters.utils.create import create_trade as create_trade_record
from app.config import settings
from app.quant.strategies.drawdown_guard import (
    DrawdownGuard,
    JsonPeakStore,
)


SHORT_NAME = "CNK"
LOGGER = get_strategy_logger(__name__, SHORT_NAME)

SYMBOL = "XAUUSD"
MAGIC_NUMBER = 1100001
XAUUSD_POINT = 0.01  # 1 point = $0.01/oz on XAUUSD

# ── Deployment defaults (crest_n_keel demo) ───────────────────────────────
# Separate peak file per strategy — never share drawdown state across strategies.
DEFAULT_PEAK_STORE_PATH = "/var/lib/quant_harness/peak_hma_stoch_1h.json"
# OOS MDD is ~15.6%; halt only on tail events worse than the backtest tail.
DEFAULT_MAX_DRAWDOWN_PCT = 0.15
# H1 with wide SL/TP → low spread sensitivity; 50pt is cheap insurance vs news.
DEFAULT_MAX_SPREAD_POINTS = 50
# London + NY, by bar OPEN time in UTC. 08:00 opens are in, 17:00 opens are out.
SESSION_START_HOUR = 8
SESSION_END_HOUR = 17
# No new entries after Friday 15:00 UTC (avoid weekend-gap-held late entries).
FRIDAY_CUTOFF_HOUR = 15


class CrestNKeelStrategy(BaseStrategy):
    """
    ``crest_n_keel`` — HMA + Stochastic strategy on the 1H timeframe for XAUUSD.

    Entry: HMA direction + price side + stochastic cross from oversold/overbought.
    Exit: asymmetric ATR SL/TP placed broker-side at entry (the edge lives here,
    not in the trigger — entry E-Ratio ~0.9).
    Risk: ATR-based position sizing, persistent peak-tracking drawdown guard.

    Filters (applied in ``evaluate`` after the guard): session window by bar
    open time, Friday cutoff by wall-clock, live spread, ATR regime floor,
    position dedup by magic number.
    """

    SHORT_NAME = SHORT_NAME

    def __init__(
        self,
        *,
        environment: str = "test",
        hma_period: int = 55,
        stoch_k_period: int = 14,
        stoch_d_period: int = 3,
        stoch_smooth_k: int = 3,
        atr_period: int = 14,
        sl_atr_mult: float = 1.5,
        tp_atr_mult: float = 3.0,
        risk_pct: float = 0.005,
        magic_number: int = MAGIC_NUMBER,
        candle_count: int = 200,
        mt5_base_url: Optional[str] = None,
        min_atr_for_signal: float = 1.0,
        max_drawdown_pct: float = DEFAULT_MAX_DRAWDOWN_PCT,
        peak_store_path: str = DEFAULT_PEAK_STORE_PATH,
        session_start_hour: int = SESSION_START_HOUR,
        session_end_hour: int = SESSION_END_HOUR,
        friday_cutoff_hour: int = FRIDAY_CUTOFF_HOUR,
        max_spread_points: int = DEFAULT_MAX_SPREAD_POINTS,
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

        # Session / cutoff / spread filter parameters
        self.session_start_hour = session_start_hour
        self.session_end_hour = session_end_hour
        self.friday_cutoff_hour = friday_cutoff_hour
        self.max_spread_points = max_spread_points

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
        """Fetch OHLCV from MT5 and return as sorted DataFrame.

        NOTE: ``time`` is the bar OPEN time. MT5/broker timestamps are assumed
        UTC; the post-deploy smoke check (VALIDATION.md) verifies this against
        the live broker before relying on the session filter.
        """
        try:
            data = self.mt5_client.get_market_rates(
                SYMBOL, "H1", count=self.candle_count
            )
            if not data or "rates" not in data:
                LOGGER.warning(f"No rate data for {SYMBOL} H1")
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

    # ──────────────────────────────────────────────────────────────────────
    # Filters
    # ──────────────────────────────────────────────────────────────────────

    def _check_session(self, bar_open: datetime) -> bool:
        """True if the closed bar's OPEN time falls within the session window.

        Bar-based (not wall-clock) so live matches backtest: an 08:00 open is
        in-session, a 17:00 open is not.
        """
        hour = bar_open.hour
        if self.session_start_hour < self.session_end_hour:
            return self.session_start_hour <= hour < self.session_end_hour
        return hour >= self.session_start_hour or hour < self.session_end_hour

    def _check_friday_cutoff(self, now: datetime) -> bool:
        """True if it's NOT past the Friday entry cutoff (wall-clock UTC).

        Wall-clock, not bar-based: the goal is to avoid *opening* a position
        late Friday that would be carried over the weekend gap.
        """
        if now.weekday() == 4 and now.hour >= self.friday_cutoff_hour:
            LOGGER.info(
                "crest_n_keel friday cutoff active (now=%s), blocking entry",
                now.isoformat(),
            )
            return False
        return True

    def _check_spread(self) -> tuple[bool, Optional[float], Optional[dict]]:
        """True if live spread is within limit. Returns (ok, spread_points, tick)."""
        try:
            tick = self.mt5_client.get_tick(SYMBOL)
            if not tick:
                LOGGER.warning("Could not fetch tick for spread check — blocking")
                return False, None, None
            spread_points = (tick["ask"] - tick["bid"]) / XAUUSD_POINT
            if spread_points > self.max_spread_points:
                LOGGER.info(
                    "Spread %.0fpt > %dpt, blocking",
                    spread_points,
                    self.max_spread_points,
                )
                return False, spread_points, tick
            return True, spread_points, tick
        except Exception as e:
            LOGGER.error(f"Spread check failed: {e}")
            return True, None, None  # allow trade if check fails

    def _log_evaluation(
        self,
        *,
        now: datetime,
        bar_open: Optional[datetime],
        equity: float,
        peak: Optional[float],
        dd: float,
        in_session: bool,
        spread: Optional[float],
        signal: Optional[str],
        halt: bool,
    ) -> None:
        """Emit the single structured per-evaluation monitoring line.

        Logs both reference clocks: ``bar_open_utc`` (drives the bar-based
        session filter) and ``wall_clock_utc`` (drives the Friday cutoff and
        is the moment of order placement). They differ by design — keep both
        for edge-case debugging.
        """
        LOGGER.info(
            "crest_n_keel.evaluation env=%s bar_open_utc=%s wall_clock_utc=%s "
            "equity=%.2f peak=%s dd=%.4f in_session=%s spread=%s signal=%s halt=%s",
            self.environment,
            bar_open.isoformat() if bar_open is not None else "n/a",
            now.isoformat(),
            equity,
            f"{peak:.2f}" if peak is not None else "n/a",
            dd,
            in_session,
            f"{spread:.0f}" if spread is not None else "n/a",
            (signal or "none").lower(),
            halt,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Sizing and order management
    # ──────────────────────────────────────────────────────────────────────

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
        *,
        expected_entry: float = 0.0,
        spread_points: Optional[float] = None,
    ) -> None:
        """Send market order and record in DB. Logs all outcomes."""
        try:
            order = MT5Broker(self.mt5_client).submit(OrderRequest(
                symbol=SYMBOL,
                side=side_from_action(signal),
                volume=lot_size,
                sl=sl,
                tp=tp,
                magic=self.magic_number,
                comment="HMA1H",
            ))

            if order and order.get("success") is True:
                fill_price = float(order.get("price", 0.0))
                slippage = fill_price - expected_entry if expected_entry else 0.0
                slippage_pts = slippage / XAUUSD_POINT
                ticket = (
                    order.get("ticket")
                    or order.get("order")
                    or order.get("deal")
                )
                LOGGER.info(
                    "crest_n_keel.order_placed magic=%s direction=%s volume=%s "
                    "entry=%.2f sl=%.2f tp=%.2f spread=%s slippage=%.2f",
                    self.magic_number,
                    signal,
                    lot_size,
                    expected_entry,
                    sl,
                    tp,
                    f"{spread_points:.0f}" if spread_points is not None else "n/a",
                    slippage,
                )
                LOGGER.info(
                    "crest_n_keel.order_filled ticket=%s fill_price=%.2f "
                    "slippage=%.2f(%.0fpt) expected=%.2f",
                    ticket,
                    fill_price,
                    slippage,
                    slippage_pts,
                    expected_entry,
                )

                account_instance = None
                if login:
                    from app.trades.models import Account

                    account_instance = Account.objects.filter(login=login).first()
                create_trade_record(
                    order,
                    symbol=SYMBOL,
                    direction=signal,
                    entry_price=fill_price,
                    order_volume=lot_size,
                    account=account_instance,
                    market_type="COMMODITIES",
                    strategy=self.__class__.__name__,
                    timeframe="1H",
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
        now = datetime.now(timezone.utc)
        LOGGER.info("crest_n_keel v1.2 evaluation started")

        # ── Account info + drawdown guard ─────────────────────────
        # Runs on EVERY evaluation, before session / bar / signal logic, so the
        # peak tracks equity 24/7 and the halt can never be skipped. is_tripped()
        # is checked before update() so the peak is never advanced past a breach.
        account_info = self._get_account_info()
        if account_info is None:
            return None
        balance, equity, login = account_info

        dd = self.drawdown_guard.current_drawdown(equity)
        if self.drawdown_guard.is_tripped(equity=equity):
            LOGGER.warning(
                "crest_n_keel.drawdown_halt active equity=%.2f peak=%.2f dd=%.4f",
                equity,
                self.drawdown_guard.peak_equity,
                self.drawdown_guard.current_drawdown(equity),
            )
            self._log_evaluation(
                now=now, bar_open=None, equity=equity,
                peak=self.drawdown_guard.peak_equity,
                dd=dd, in_session=False, spread=None, signal=None, halt=True,
            )
            return None
        self.drawdown_guard.update(equity=equity)
        peak = self.drawdown_guard.peak_equity

        # ── Candles ───────────────────────────────────────────────
        df = self._fetch_candles()
        if df is None or len(df) < self.hma_period + 10:
            LOGGER.warning("Insufficient candle data")
            return None

        bar_open = df.iloc[-2]["time"]
        if hasattr(bar_open, "to_pydatetime"):
            bar_open = bar_open.to_pydatetime()
        in_session = self._check_session(bar_open)

        signal, atr_value = self._generate_signal(df)
        self._log_evaluation(
            now=now, bar_open=bar_open, equity=equity, peak=peak, dd=dd,
            in_session=in_session, spread=None, signal=signal, halt=False,
        )

        # ── Entry-gating filters (guard/peak already updated above) ──
        if not in_session:
            LOGGER.info("Outside trading session (bar_open=%s), skipping entry",
                        bar_open.isoformat())
            return None

        if not self._check_friday_cutoff(now):
            return None

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

        spread_ok, spread_points, _tick = self._check_spread()
        if not spread_ok:
            return None

        entry_price = float(df.iloc[-2]["close"])

        sized = size_order(
            SYMBOL,
            account_balance=balance,
            atr_value=atr_value,
            risk_pct=self.risk_pct,
            sl_atr_multiplier=self.sl_atr_mult,
        )
        if not sized.tradable:
            # A refusal, not an order attempt: nothing reaches the broker, so
            # there is no retcode to record. Logged at WARNING so a run of
            # them on a small account is visible rather than looking like
            # "no signal".
            LOGGER.warning(
                f"Signal {signal} declined by sizer: reason={sized.reason.value} "
                f"balance={balance:.2f} raw_atr={atr_value:.4f} "
                f"risk_pct={self.risk_pct}"
            )
            return None
        lot_size, effective_atr = sized.lots, sized.effective_atr
        sl, tp = self._compute_sl_tp(signal, entry_price, effective_atr)

        LOGGER.info(
            f"Placing {signal}: symbol={SYMBOL} lots={lot_size} sl={sl:.2f} "
            f"tp={tp:.2f} raw_atr={atr_value:.4f} eff_atr={effective_atr:.4f} "
            f"balance={balance:.2f} peak={self.drawdown_guard.peak_equity}"
        )
        self._place_order(
            signal, lot_size, sl, tp, login,
            expected_entry=entry_price, spread_points=spread_points,
        )

        LOGGER.info(
            f"Evaluation complete. Signal={signal} "
            f"Duration={_time.monotonic() - start:.2f}s"
        )
        return signal
