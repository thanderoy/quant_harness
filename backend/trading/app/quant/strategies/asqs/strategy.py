"""
ASQ SafeScalping v1.20 — production live-trading adapter.

Faithful translation of the MT5 EA by AlgoSphere Quant (Robin2.0):
  https://www.mql5.com/en/code/71189

Phase 1 preset (harness-validated over 21.6 years, 33 WF folds):
  OOS Sharpe 5.14 | OOS PF 1.55 | OOS Max DD 5.5% | 11,497 trades

Key implementation decisions vs the MQL5 EA:
  - SL/TP: FIXED POINTS (300pt / 450pt), not ATR multiples.
  - Exit management (breakeven, trailing, partial close) runs at bar-level
    (every M5 close via Celery). The EA runs in OnTick — live will be
    slightly better than the harness modelled.
  - Spread filter: implemented via live tick at order time.
  - Drawdown halt: persistent peak tracking via JsonPeakStore, not
    per-evaluation balance/equity comparison.
  - Daily trade count: queried from DB so it survives task restarts.
"""

from __future__ import annotations

import json
import logging
import math
import os
import time as _time
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

from app.quant.strategies.base import BaseStrategy
from app.quant.strategies.indicators import atr as calc_atr
from app.quant.strategies.drawdown_guard import DrawdownGuard, JsonPeakStore
from app.adapters.mt5_api import MT5APIClient
from app.adapters.utils.create import create_trade as create_trade_record
from app.config import settings


LOGGER = logging.getLogger(__name__)

SYMBOL = "XAUUSD"
MAGIC_NUMBER = 1500020

# Pepperstone XAUUSD instrument constants
XAUUSD_POINT = 0.01          # 1 point = $0.01/oz (SYMBOL_DIGITS=2)
XAUUSD_CONTRACT = 100.0      # oz per standard lot
XAUUSD_MIN_LOT = 0.01
XAUUSD_MAX_LOT = 0.10
XAUUSD_LOT_STEP = 0.01

# Phase 1 preset — fixed SL/TP in points
SL_POINTS = 300              # $3.00/oz
TP_POINTS = 450              # $4.50/oz

# Exit management thresholds
BREAKEVEN_START = 150        # points profit → move SL to BE
BREAKEVEN_OFFSET = 20        # SL = entry + 20pt (long) or entry - 20pt (short)
TRAIL_START = 200            # points profit → activate trailing
TRAIL_STEP = 100             # trailing SL distance in points
TP1_POINTS = 200             # points profit → partial close trigger
TP1_PCT = 0.50               # fraction to close at TP1


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


class _PartialCloseTracker:
    """Persists which position tickets have already had the TP1 partial close."""

    def __init__(self, filepath: str) -> None:
        self.filepath = filepath
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    def _load(self) -> list[int]:
        try:
            with open(self.filepath) as f:
                return json.load(f).get("done", [])
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return []

    def has_partial(self, ticket: int) -> bool:
        return ticket in self._load()

    def mark_partial(self, ticket: int) -> None:
        done = self._load()
        if ticket not in done:
            done.append(ticket)
        tmp = self.filepath + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"done": done}, f)
        os.replace(tmp, self.filepath)


class ASQSafeScalpingStrategy(BaseStrategy):
    """
    ASQ SafeScalping v1.20 — 7-condition breakout scalper for XAUUSD M5.

    Entry: EMA trend + ATR separation + price above both EMAs + N-bar breakout
           + RSI zone + momentum + H1 EMA confirmation.
    Exit: partial close at TP1, breakeven SL, trailing stop (bar-level).
    Risk: fixed-point SL (300pt = $3.00), 0.5% equity sizing, persistent 8% DD halt.
    """

    def __init__(
        self,
        *,
        environment: str = "test",
        # EMA trend filter (Phase 1)
        ema_fast_period: int = 50,
        ema_slow_period: int = 200,
        atr_period: int = 50,
        ema_sep_atr_mult: float = 0.3,
        # Breakout
        breakout_lookback: int = 15,
        breakout_atr_buffer: float = 0.3,
        # RSI filter
        rsi_period: int = 14,
        rsi_buy_lo: float = 45.0,
        rsi_buy_hi: float = 65.0,
        rsi_sell_lo: float = 35.0,
        rsi_sell_hi: float = 55.0,
        # MTF H1 confirmation (Phase 1: EMA 20/50 on H1)
        use_h1_filter: bool = True,
        h1_ema_fast: int = 20,
        h1_ema_slow: int = 50,
        # SL/TP (fixed points, not ATR)
        sl_points: int = SL_POINTS,
        tp_points: int = TP_POINTS,
        # Exit management
        use_breakeven: bool = True,
        breakeven_start: int = BREAKEVEN_START,
        breakeven_offset: int = BREAKEVEN_OFFSET,
        use_trailing: bool = True,
        trail_start: int = TRAIL_START,
        trail_step: int = TRAIL_STEP,
        use_partial: bool = True,
        tp1_points: int = TP1_POINTS,
        tp1_pct: float = TP1_PCT,
        # Position sizing
        risk_pct: float = 0.005,
        # Safety
        max_drawdown_pct: float = 0.08,
        max_daily_trades: int = 4,
        session_start_hour: int = 8,
        session_end_hour: int = 17,
        friday_cutoff_hour: int = 14,
        use_spread_filter: bool = True,
        max_spread_points: int = 25,
        # Infrastructure
        timeframe: str = "M5",
        candle_count: int = 600,
        magic_number: int = MAGIC_NUMBER,
        peak_store_path: str = "/var/lib/qhf/peak_equity_ASQS.json",
        partial_store_path: str = "/var/lib/qhf/partial_done_ASQS.json",
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
        self.sl_points = sl_points
        self.tp_points = tp_points
        self.use_breakeven = use_breakeven
        self.breakeven_start = breakeven_start
        self.breakeven_offset = breakeven_offset
        self.use_trailing = use_trailing
        self.trail_start = trail_start
        self.trail_step = trail_step
        self.use_partial = use_partial
        self.tp1_points = tp1_points
        self.tp1_pct = tp1_pct
        self.risk_pct = risk_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.max_daily_trades = max_daily_trades
        self.session_start_hour = session_start_hour
        self.session_end_hour = session_end_hour
        self.friday_cutoff_hour = friday_cutoff_hour
        self.use_spread_filter = use_spread_filter
        self.max_spread_points = max_spread_points
        self.timeframe = timeframe
        self.candle_count = candle_count
        self.magic_number = magic_number

        self.drawdown_guard = DrawdownGuard(
            store=JsonPeakStore(peak_store_path),
            max_drawdown_pct=max_drawdown_pct,
        )
        self.partial_tracker = _PartialCloseTracker(partial_store_path)

        base_url = mt5_base_url or settings.get_mt5_url(self.environment)
        self.mt5_client = MT5APIClient(base_url=base_url)
        try:
            self.mt5_client.connect()
        except Exception as e:
            LOGGER.warning(f"Could not connect MT5 at init: {e}")

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

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
        """Fetch OHLCV from MT5."""
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
                LOGGER.error(f"Missing columns: {df.columns.tolist()}")
                return None
            if not pd.api.types.is_datetime64_any_dtype(df["time"]):
                df["time"] = pd.to_datetime(df["time"])
            return df.sort_values("time").reset_index(drop=True)
        except Exception as e:
            LOGGER.error(f"Error fetching {tf} candles: {e}")
            return None

    # ------------------------------------------------------------------
    # Guard checks
    # ------------------------------------------------------------------

    def _check_session(self, now: datetime) -> bool:
        """False on weekend, outside 08:00–16:59 UTC."""
        dow = now.weekday()   # Mon=0, Fri=4, Sat=5, Sun=6
        if dow >= 5:
            return False
        return self.session_start_hour <= now.hour < self.session_end_hour

    def _check_friday_cutoff(self, now: datetime) -> bool:
        """False if Friday and at or past the cutoff hour."""
        if now.weekday() == 4 and now.hour >= self.friday_cutoff_hour:
            LOGGER.info("Friday cutoff active, blocking entry")
            return False
        return True

    def _count_today_trades(self) -> int:
        """Count today's entries for this strategy from the DB."""
        from django.utils import timezone as dj_tz
        from app.trades.models import Trade
        today = dj_tz.now().date()
        return Trade.objects.filter(
            strategy=self.__class__.__name__,
            environment=self.environment.upper(),
            entry_time__date=today,
        ).count()

    def _has_open_position(self, positions: list) -> bool:
        """True if there is already an open position for this magic number."""
        if positions:
            LOGGER.info(f"Open position exists: magic={self.magic_number}, skipping entry")
            return True
        return False

    def _check_spread(self) -> bool:
        """False if current spread exceeds the maximum allowed."""
        try:
            tick = self.mt5_client.get_tick(SYMBOL)
            spread_pts = round((float(tick["ask"]) - float(tick["bid"])) / XAUUSD_POINT)
            if spread_pts > self.max_spread_points:
                LOGGER.info(
                    f"Spread filter: {spread_pts}pt > max {self.max_spread_points}pt, skipping"
                )
                return False
        except Exception as e:
            LOGGER.warning(f"Could not check spread: {e}")
        return True

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def _generate_signal(self, df: pd.DataFrame) -> tuple[Optional[str], float]:
        """
        Evaluate the last CLOSED candle (iloc[-2]).
        Returns (signal, atr_value). All 6 M5-level conditions must pass.
        """
        close = df["close"]
        high = df["high"]
        low = df["low"]

        ema_fast = _ema(close, self.ema_fast_period)
        ema_slow = _ema(close, self.ema_slow_period)
        atr_series = calc_atr(high, low, close, self.atr_period)
        rsi_series = _rsi(close, self.rsi_period)

        # shift(1) excludes the signal bar, matching MQL5's i=2..lookback+1
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
        if atr_val == 0:
            return None, 0.0

        ef = float(ef)
        es = float(es)
        rsi_val = float(rsi_val)
        brk_hi = float(brk_hi)
        brk_lo = float(brk_lo)

        atr_buffer = self.breakout_atr_buffer * atr_val
        ema_gap = abs(ef - es)
        min_gap = self.ema_sep_atr_mult * atr_val

        # BUY gate
        c1_buy = ef > es
        c2_buy = ema_gap > min_gap
        c3_buy = c > ef and c > es
        c4_buy = (c > brk_hi - atr_buffer) and (c_prev <= brk_hi)
        c5_buy = self.rsi_buy_lo <= rsi_val <= self.rsi_buy_hi
        c6_buy = c > c_prev

        if all([c1_buy, c2_buy, c3_buy, c4_buy, c5_buy, c6_buy]):
            LOGGER.debug(
                f"BUY gate: EMA_f={ef:.2f} EMA_s={es:.2f} RSI={rsi_val:.1f} "
                f"brkHi={brk_hi:.2f} ATR={atr_val:.4f}"
            )
            return "BUY", atr_val

        # SELL gate
        c1_sell = ef < es
        c2_sell = ema_gap > min_gap
        c3_sell = c < ef and c < es
        c4_sell = (c < brk_lo + atr_buffer) and (c_prev >= brk_lo)
        c5_sell = self.rsi_sell_lo <= rsi_val <= self.rsi_sell_hi
        c6_sell = c < c_prev

        if all([c1_sell, c2_sell, c3_sell, c4_sell, c5_sell, c6_sell]):
            LOGGER.debug(
                f"SELL gate: EMA_f={ef:.2f} EMA_s={es:.2f} RSI={rsi_val:.1f} "
                f"brkLo={brk_lo:.2f} ATR={atr_val:.4f}"
            )
            return "SELL", atr_val

        return None, atr_val

    def _check_h1_confirmation(self, signal: str) -> bool:
        """Condition 7: H1 EMA(20/50) must agree with signal direction."""
        if not self.use_h1_filter:
            return True

        h1_df = self._fetch_candles(tf="H1")
        if h1_df is None or len(h1_df) < self.h1_ema_slow + 5:
            LOGGER.warning("Insufficient H1 data for confirmation — blocking signal")
            return False

        h1_ef = float(_ema(h1_df["close"], self.h1_ema_fast).iloc[-2])
        h1_es = float(_ema(h1_df["close"], self.h1_ema_slow).iloc[-2])

        if signal == "BUY" and h1_ef > h1_es:
            return True
        if signal == "SELL" and h1_ef < h1_es:
            return True

        LOGGER.info(
            f"H1 confirmation failed: signal={signal} H1_EMA_f={h1_ef:.2f} H1_EMA_s={h1_es:.2f}"
        )
        return False

    # ------------------------------------------------------------------
    # Sizing and SL/TP
    # ------------------------------------------------------------------

    def _calc_lot(self, equity: float) -> float:
        """
        Fixed-point sizing matching MQL5 CalcLot().
        risk_amount = equity * 0.005
        sl_distance  = sl_points * 0.01 = $3.00/oz
        raw_lots     = risk_amount / (sl_distance * 100)
        """
        risk_amount = equity * self.risk_pct
        sl_distance = self.sl_points * XAUUSD_POINT
        raw_lots = risk_amount / (sl_distance * XAUUSD_CONTRACT)
        stepped = math.floor(raw_lots / XAUUSD_LOT_STEP) * XAUUSD_LOT_STEP
        return max(XAUUSD_MIN_LOT, min(XAUUSD_MAX_LOT, round(stepped, 2)))

    def _compute_sl_tp(self, signal: str, entry_price: float) -> tuple[float, float]:
        """Fixed-point SL/TP: 300pt SL ($3.00), 450pt TP ($4.50)."""
        sl_d = self.sl_points * XAUUSD_POINT
        tp_d = self.tp_points * XAUUSD_POINT
        if signal == "BUY":
            return round(entry_price - sl_d, 2), round(entry_price + tp_d, 2)
        return round(entry_price + sl_d, 2), round(entry_price - tp_d, 2)

    # ------------------------------------------------------------------
    # Exit management (runs every evaluation for all open positions)
    # ------------------------------------------------------------------

    def _manage_exits(self, positions: list) -> None:
        """
        Bar-level approximation of OnTick exit management.
        Order: partial close → breakeven → trailing stop.
        """
        if not positions:
            return

        try:
            tick = self.mt5_client.get_tick(SYMBOL)
            bid = float(tick["bid"])
            ask = float(tick["ask"])
        except Exception as e:
            LOGGER.error(f"Failed to get tick for exit management: {e}")
            return

        for pos in positions:
            ticket = int(pos["ticket"])
            is_long = pos.get("type", 0) == 0   # 0=BUY, 1=SELL
            entry = float(pos["price_open"])
            current_sl = pos.get("sl")
            volume = float(pos["volume"])

            cur_price = bid if is_long else ask
            profit_pts = ((cur_price - entry) if is_long else (entry - cur_price)) / XAUUSD_POINT

            new_sl = current_sl

            # 1. Partial close at TP1 (once per trade)
            if self.use_partial and not self.partial_tracker.has_partial(ticket):
                if profit_pts >= self.tp1_points:
                    close_vol = round(
                        math.floor(volume * self.tp1_pct / XAUUSD_LOT_STEP) * XAUUSD_LOT_STEP, 2
                    )
                    if close_vol >= XAUUSD_MIN_LOT:
                        try:
                            self.mt5_client.close_position(
                                ticket,
                                volume=close_vol,
                                magic=self.magic_number,
                                comment="ASQSS_TP1",
                            )
                            self.partial_tracker.mark_partial(ticket)
                            LOGGER.info(
                                f"Partial close: ticket={ticket} vol={close_vol} "
                                f"profit_pts={profit_pts:.0f}"
                            )
                        except Exception as e:
                            LOGGER.error(f"Partial close failed: ticket={ticket}: {e}")

            # 2. Breakeven
            if self.use_breakeven and profit_pts >= self.breakeven_start:
                be_sl = (
                    round(entry + self.breakeven_offset * XAUUSD_POINT, 2)
                    if is_long
                    else round(entry - self.breakeven_offset * XAUUSD_POINT, 2)
                )
                if is_long and (current_sl is None or current_sl < be_sl):
                    new_sl = be_sl
                elif not is_long and (current_sl is None or current_sl > be_sl):
                    new_sl = be_sl

            # 3. Trailing stop
            if self.use_trailing and profit_pts >= self.trail_start:
                trail_sl = (
                    round(cur_price - self.trail_step * XAUUSD_POINT, 2)
                    if is_long
                    else round(cur_price + self.trail_step * XAUUSD_POINT, 2)
                )
                if is_long and (new_sl is None or trail_sl > new_sl):
                    new_sl = trail_sl
                elif not is_long and (new_sl is None or trail_sl < new_sl):
                    new_sl = trail_sl

            if new_sl != current_sl:
                try:
                    self.mt5_client.modify_position(ticket, sl=new_sl)
                    LOGGER.info(
                        f"SL updated: ticket={ticket} {current_sl} → {new_sl} "
                        f"profit_pts={profit_pts:.0f}"
                    )
                except Exception as e:
                    LOGGER.error(f"SL modify failed: ticket={ticket}: {e}")

    # ------------------------------------------------------------------
    # Order placement
    # ------------------------------------------------------------------

    def _place_order(
        self,
        signal: str,
        lot_size: float,
        sl: float,
        tp: float,
        login: Optional[int],
    ) -> None:
        """Send market order and record in DB. Logs all outcomes including failures."""
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

    # ------------------------------------------------------------------
    # Main evaluation loop
    # ------------------------------------------------------------------

    def evaluate(self) -> Optional[str]:
        """
        Full evaluation cycle. Runs every M5 bar close (every 5 minutes).
        Exit management always runs; entry is gated by all seven filters.
        Returns the signal string ('BUY'/'SELL') or None.
        """
        start = _time.monotonic()
        LOGGER.info("ASQSafeScalping evaluation started")

        # -- Fetch open positions once; used for exit management AND dedup --
        try:
            positions = self.mt5_client.get_open_positions(
                magic=self.magic_number, symbol=SYMBOL
            )
        except Exception as e:
            LOGGER.error(f"Failed to fetch positions: {e}")
            positions = []

        # Exit management runs regardless of entry filters
        self._manage_exits(positions)

        # -- Session filter (includes weekend) --
        now = datetime.now(timezone.utc)
        if not self._check_session(now):
            LOGGER.info("Outside session, skipping entry")
            return None
        if not self._check_friday_cutoff(now):
            return None

        # -- Account info (needed for drawdown guard and sizing) --
        account_info = self._get_account_info()
        if account_info is None:
            return None
        balance, equity, login = account_info

        # -- Persistent drawdown halt --
        if self.drawdown_guard.is_tripped(equity=equity):
            LOGGER.warning(
                f"Drawdown guard tripped: {self.drawdown_guard.diagnostics()}, "
                f"equity={equity:.2f}"
            )
            return None
        self.drawdown_guard.update(equity=equity)

        # -- Daily trade cap (DB query — survives task restarts) --
        if self._count_today_trades() >= self.max_daily_trades:
            LOGGER.info(f"Daily trade cap reached ({self.max_daily_trades})")
            return None

        # -- One position at a time --
        if self._has_open_position(positions):
            return None

        # -- Fetch M5 candles --
        min_bars = self.ema_slow_period + self.breakout_lookback + 20
        df = self._fetch_candles()
        if df is None or len(df) < min_bars:
            LOGGER.warning(
                f"Insufficient candle data: got {len(df) if df is not None else 0}, "
                f"need {min_bars}"
            )
            return None

        # -- 6-condition M5 signal --
        signal, atr_value = self._generate_signal(df)
        LOGGER.info(f"Signal={signal} ATR={atr_value:.4f}")
        if signal is None:
            LOGGER.info(f"No signal. Duration={_time.monotonic() - start:.2f}s")
            return None

        # -- Condition 7: H1 EMA confirmation --
        if not self._check_h1_confirmation(signal):
            return None

        # -- Spread filter (live only) --
        if self.use_spread_filter and not self._check_spread():
            return None

        # -- Sizing and SL/TP (fixed points, not ATR) --
        entry_price = float(df.iloc[-2]["close"])
        lot_size = self._calc_lot(equity)
        sl, tp = self._compute_sl_tp(signal, entry_price)

        LOGGER.info(
            f"Placing {signal}: symbol={SYMBOL} lots={lot_size} sl={sl:.2f} tp={tp:.2f} "
            f"equity={equity:.2f} peak={self.drawdown_guard.peak_equity}"
        )
        self._place_order(signal, lot_size, sl, tp, login)

        LOGGER.info(
            f"Evaluation complete. Signal={signal} "
            f"Duration={_time.monotonic() - start:.2f}s"
        )
        return signal
