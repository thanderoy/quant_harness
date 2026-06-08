"""
ASQ SafeScalping v1.20 — Python port for XAUUSD M5.

Faithful translation of the MQL5 EA by AlgoSphere Quant (Robin2.0):
  https://www.mql5.com/en/code/71189

Entry requires ALL seven conditions to align simultaneously:
  1. EMA(50) vs EMA(200) trend direction
  2. ATR(50)-based minimum EMA separation (chop filter)
  3. Close on correct side of both EMAs
  4. 15-bar breakout with ATR buffer
  5. RSI(14) in healthy zone (45–65 buy, 35–55 sell)
  6. Momentum: close vs prior close
  7. H1 EMA(20/50) higher-timeframe confirmation

Risk: single position, fixed SL/TP (300/450pt), 0.5% equity sizing,
      8% drawdown auto-pause, max 4 trades/day, 25pt spread filter.
      No martingale, no grid, no hedging.

Exit management (runs every M5 cycle for all open positions):
  - Partial close 50% at TP1 (+200pt), tracked via _PartialCloseTracker
  - Breakeven: SL → entry + 20pt when profit >= 150pt
  - Trailing: SL trails 100pt behind price when profit >= 200pt

LIMITATIONS vs the MT5 EA:
  - News filter: not modeled (requires external calendar)
"""

import json
import logging
import os
import time as _time
from datetime import datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd

from app.quant.strategies.base import BaseStrategy
from app.quant.strategies.drawdown_guard import DrawdownGuard, JsonPeakStore
from app.quant.strategies.indicators import atr as calc_atr
from app.adapters.mt5_api import MT5APIClient
from app.adapters.utils.create import create_trade as create_trade_record
from app.config import settings


LOGGER = logging.getLogger(__name__)


class _PartialCloseTracker:
    """
    Tracks which position tickets have already received their TP1 partial close.
    Persisted to JSON via atomic os.replace() to survive worker restarts.
    This is the Python equivalent of the v1.20 ticket-tracking fix that
    prevented repeated TP1 closes on every tick.
    """

    def __init__(self, path: str):
        self._path = path
        self._closed_tickets: set[int] = set()
        self._load()

    def _load(self) -> None:
        try:
            with open(self._path, "r") as f:
                data = json.load(f)
            self._closed_tickets = set(data.get("closed_tickets", []))
        except (FileNotFoundError, json.JSONDecodeError):
            self._closed_tickets = set()

    def _save(self) -> None:
        tmp = self._path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self._path), exist_ok=True)
            with open(tmp, "w") as f:
                json.dump({"closed_tickets": list(self._closed_tickets)}, f)
            os.replace(tmp, self._path)
        except OSError as e:
            LOGGER.error(f"Failed to save partial close tracker: {e}")

    def is_closed(self, ticket: int) -> bool:
        return ticket in self._closed_tickets

    def mark_closed(self, ticket: int) -> None:
        self._closed_tickets.add(ticket)
        self._save()

    def purge_stale(self, active_tickets: set[int]) -> None:
        """Remove tickets that are no longer open (position was closed)."""
        stale = self._closed_tickets - active_tickets
        if stale:
            self._closed_tickets -= stale
            self._save()

# ── XAUUSD constants (Pepperstone Razor) ──────────────────────────────────
SYMBOL = "XAUUSD"
MAGIC_NUMBER = 1500020
XAUUSD_POINT = 0.01
XAUUSD_CONTRACT = 100.0  # oz per standard lot
XAUUSD_MIN_LOT = 0.01
XAUUSD_MAX_LOT = 0.10
XAUUSD_LOT_STEP = 0.01

# ── Fixed SL/TP (Phase 1 preset) ─────────────────────────────────────────
SL_POINTS = 300   # $3.00/oz
TP_POINTS = 450   # $4.50/oz

# ── Exit management defaults ──────────────────────────────────────────────
TP1_TRIGGER_POINTS = 200   # partial close at +$2.00 profit
TP1_CLOSE_PCT = 0.50       # close 50% of position
BE_TRIGGER_POINTS = 150    # breakeven when +$1.50 profit
BE_OFFSET_POINTS = 20      # move SL to entry + $0.20
TRAIL_TRIGGER_POINTS = 200 # start trailing at +$2.00
TRAIL_DISTANCE_POINTS = 100  # trail $1.00 behind price

# ── Risk defaults ─────────────────────────────────────────────────────────
DEFAULT_MAX_SPREAD_POINTS = 25
DEFAULT_PEAK_STORE_PATH = "/var/lib/qhf/asqs_peak.json"
DEFAULT_PARTIAL_STORE_PATH = "/var/lib/qhf/asqs_partial.json"


# ── Indicator helpers ─────────────────────────────────────────────────────

def _ema(series: pd.Series, period: int) -> pd.Series:
    """Standard EMA via pandas ewm."""
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int) -> pd.Series:
    """Wilder-style RSI."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


class ASQSafeScalpingStrategy(BaseStrategy):
    """ASQ SafeScalping v1.20 — 7-condition breakout scalper for XAUUSD M5."""

    def __init__(
        self,
        *,
        environment: str = "test",
        # ── Condition 1 & 3: EMA trend ──
        ema_fast_period: int = 50,
        ema_slow_period: int = 200,
        # ── Condition 2: ATR-based EMA separation ──
        atr_period: int = 50,
        ema_sep_atr_mult: float = 0.3,
        # ── Condition 4: N-bar breakout ──
        breakout_lookback: int = 15,
        breakout_atr_buffer: float = 0.2,
        # ── Condition 5: RSI zone ──
        rsi_period: int = 14,
        rsi_buy_lo: float = 45.0,
        rsi_buy_hi: float = 65.0,
        rsi_sell_lo: float = 35.0,
        rsi_sell_hi: float = 55.0,
        # ── Condition 7: H1 confirmation ──
        use_h1_filter: bool = True,
        h1_ema_fast: int = 20,
        h1_ema_slow: int = 50,
        # ── Risk ──
        risk_pct: float = 0.005,
        max_drawdown_pct: float = 0.08,
        max_daily_trades: int = 4,
        max_spread_points: int = DEFAULT_MAX_SPREAD_POINTS,
        # ── Exit management ──
        use_breakeven: bool = True,
        use_trailing: bool = True,
        use_partial_close: bool = True,
        # ── Session ──
        session_start_hour: int = 8,
        session_end_hour: int = 17,
        friday_cutoff_hour: int = 14,
        # ── Infra ──
        timeframe: str = "M5",
        candle_count: int = 300,
        magic_number: int = MAGIC_NUMBER,
        peak_store_path: str = DEFAULT_PEAK_STORE_PATH,
        partial_store_path: str = DEFAULT_PARTIAL_STORE_PATH,
        mt5_base_url: Optional[str] = None,
    ):
        super().__init__(environment=environment)

        # Condition parameters
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

        # Risk parameters
        self.risk_pct = risk_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.max_daily_trades = max_daily_trades
        self.max_spread_points = max_spread_points

        # Exit management
        self.use_breakeven = use_breakeven
        self.use_trailing = use_trailing
        self.use_partial_close = use_partial_close

        # Session parameters
        self.session_start_hour = session_start_hour
        self.session_end_hour = session_end_hour
        self.friday_cutoff_hour = friday_cutoff_hour

        # Infra
        self.timeframe = timeframe
        self.candle_count = candle_count
        self.magic_number = magic_number

        # Persistent state
        self.drawdown_guard = DrawdownGuard(
            JsonPeakStore(peak_store_path),
            max_drawdown_pct=self.max_drawdown_pct,
        )
        self.partial_tracker = _PartialCloseTracker(partial_store_path)

        base_url = mt5_base_url or settings.get_mt5_url(self.environment)
        self.mt5_client = MT5APIClient(base_url=base_url)
        try:
            self.mt5_client.connect()
        except Exception as e:
            LOGGER.warning(f"Could not connect MT5 at init: {e}")

    # ──────────────────────────────────────────────────────────────────────
    # Infrastructure
    # ──────────────────────────────────────────────────────────────────────

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
        count = self.candle_count if tf == self.timeframe else 100
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
                magic=self.magic_number, symbol=SYMBOL,
            )
            if positions:
                LOGGER.info(f"Open position exists: magic={self.magic_number}, skipping")
                return True
            return False
        except Exception as e:
            LOGGER.error(f"Failed to check open positions: {e}")
            return True  # conservative: block if check fails

    # ──────────────────────────────────────────────────────────────────────
    # Filters
    # ──────────────────────────────────────────────────────────────────────

    def _check_session(self, now: datetime) -> bool:
        """True if current hour is within the trading session window."""
        hour = now.hour
        if self.session_start_hour < self.session_end_hour:
            return self.session_start_hour <= hour < self.session_end_hour
        return hour >= self.session_start_hour or hour < self.session_end_hour

    def _check_friday_cutoff(self, now: datetime) -> bool:
        """True if it's NOT past the Friday cutoff."""
        if now.weekday() == 4 and now.hour >= self.friday_cutoff_hour:
            LOGGER.info("Friday cutoff active, blocking trade")
            return False
        return True

    def _check_daily_cap(self) -> bool:
        """True if daily trade count is below the cap. DB-queried."""
        from app.trades.models import Trade
        from django.utils import timezone as dj_tz

        today = dj_tz.now().date()
        count = Trade.objects.filter(
            strategy=self.__class__.__name__,
            entry_time__date=today,
        ).count()
        if count >= self.max_daily_trades:
            LOGGER.info(f"Daily cap reached ({count}/{self.max_daily_trades})")
            return False
        return True

    def _check_spread(self) -> tuple[bool, Optional[dict]]:
        """
        True if live spread is within limit. Returns (ok, tick_data).
        The tick_data is reused for entry price anchoring.
        """
        try:
            tick = self.mt5_client.get_tick(SYMBOL)
            if not tick:
                LOGGER.warning("Could not fetch tick for spread check — blocking")
                return False, None
            spread_points = (tick["ask"] - tick["bid"]) / XAUUSD_POINT
            if spread_points > self.max_spread_points:
                LOGGER.info(f"Spread {spread_points:.0f}pt > {self.max_spread_points}pt, blocking")
                return False, tick
            return True, tick
        except Exception as e:
            LOGGER.error(f"Spread check failed: {e}")
            return True, None  # allow trade if check fails

    # ──────────────────────────────────────────────────────────────────────
    # Signal generation: the 7-condition gate (conditions 1–6)
    # ──────────────────────────────────────────────────────────────────────

    def _generate_signal(self, df: pd.DataFrame) -> tuple[Optional[str], float]:
        """
        Evaluate the last CLOSED candle (iloc[-2]).
        Returns (signal, atr_value) where signal is 'BUY', 'SELL', or None.

        All 6 chart-based conditions must pass. Condition 7 (H1) is
        checked separately in _check_h1_confirmation().
        """
        close = df["close"]
        high = df["high"]
        low = df["low"]

        ema_fast = _ema(close, self.ema_fast_period)
        ema_slow = _ema(close, self.ema_slow_period)
        atr_series = calc_atr(high, low, close, self.atr_period)
        rsi_series = _rsi(close, self.rsi_period)

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

        vals = [ef, es, atr_val, rsi_val, brk_hi, brk_lo]
        if any(pd.isna(v) for v in vals):
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

        # ── BUY gate ──────────────────────────────────────────────
        c1_buy = ef > es
        c2_buy = ema_gap > min_gap
        c3_buy = c > ef and c > es
        c4_buy = c > brk_hi - atr_buffer      # MINUS buffer (per project spec)
        c5_buy = self.rsi_buy_lo <= rsi_val <= self.rsi_buy_hi
        c6_buy = c > c_prev

        buy_conds = {
            "①EMA_dir": c1_buy, "②EMA_sep": c2_buy, "③close_pos": c3_buy,
            "④breakout": c4_buy, "⑤RSI_zone": c5_buy, "⑥momentum": c6_buy,
        }

        # ── SELL gate ─────────────────────────────────────────────
        c1_sell = ef < es
        c2_sell = ema_gap > min_gap
        c3_sell = c < ef and c < es
        c4_sell = c < brk_lo + atr_buffer      # PLUS buffer (per project spec)
        c5_sell = self.rsi_sell_lo <= rsi_val <= self.rsi_sell_hi
        c6_sell = c < c_prev

        sell_conds = {
            "①EMA_dir": c1_sell, "②EMA_sep": c2_sell, "③close_pos": c3_sell,
            "④breakdown": c4_sell, "⑤RSI_zone": c5_sell, "⑥momentum": c6_sell,
        }

        # ── Diagnostic logging ────────────────────────────────────
        buy_pass = sum(buy_conds.values())
        sell_pass = sum(sell_conds.values())

        LOGGER.info(
            f"DIAGNOSTIC | close={c:.2f} EMA_f={ef:.2f} EMA_s={es:.2f} "
            f"gap={ema_gap:.2f}(min={min_gap:.2f}) RSI={rsi_val:.1f} "
            f"ATR={atr_val:.4f} | BUY={buy_pass}/6 SELL={sell_pass}/6"
        )

        if all(buy_conds.values()):
            LOGGER.info("ALL BUY conditions passed — signal fired")
            return "BUY", atr_val

        if all(sell_conds.values()):
            LOGGER.info("ALL SELL conditions passed — signal fired")
            return "SELL", atr_val

        best_side = "BUY" if buy_pass >= sell_pass else "SELL"
        blockers = [
            n for n, v in (buy_conds if best_side == "BUY" else sell_conds).items()
            if not v
        ]
        LOGGER.info(f"Closest: {best_side} ({max(buy_pass, sell_pass)}/6), blocked by {blockers}")

        return None, atr_val

    def _check_h1_confirmation(self, signal: str) -> bool:
        """
        Condition ⑦: H1 EMA(20/50) higher-timeframe filter.
        Returns True if H1 trend agrees, or if filter is disabled.
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
            f"H1_EMA{self.h1_ema_fast}={ef:.2f} H1_EMA{self.h1_ema_slow}={es:.2f}"
        )
        return False

    # ──────────────────────────────────────────────────────────────────────
    # Exit management (breakeven, trailing, partial close)
    # ──────────────────────────────────────────────────────────────────────

    def manage_positions(self) -> None:
        """
        Manage all open positions with this magic number.
        Runs every M5 bar close, regardless of whether a new signal fires.

        Order of operations per position:
          1. Partial close at TP1 (one-time, tracked by _PartialCloseTracker)
          2. Breakeven move (SL → entry + offset)
          3. Trailing stop (SL follows price at fixed distance)

        Uses modify_position for SL changes and close_position for partials.
        """
        try:
            positions = self.mt5_client.get_open_positions(
                magic=self.magic_number, symbol=SYMBOL,
            )
        except Exception as e:
            LOGGER.error(f"Failed to fetch positions for management: {e}")
            return

        if not positions:
            return

        active_tickets = set()

        for pos in positions:
            ticket = pos.get("ticket")
            if not ticket:
                continue
            active_tickets.add(ticket)

            entry_price = float(pos.get("price_open", 0.0))
            current_sl = float(pos.get("sl", 0.0))
            volume = float(pos.get("volume", 0.0))
            direction = pos.get("type")  # 0 = BUY, 1 = SELL

            # Fetch current price for this position
            try:
                tick = self.mt5_client.get_tick(SYMBOL)
                if not tick:
                    continue
            except Exception:
                continue

            is_buy = direction == 0
            current_price = tick["bid"] if is_buy else tick["ask"]
            profit_points = (
                (current_price - entry_price) / XAUUSD_POINT if is_buy
                else (entry_price - current_price) / XAUUSD_POINT
            )

            # ── 1. Partial close at TP1 (one-time) ───────────────
            if (
                self.use_partial_close
                and profit_points >= TP1_TRIGGER_POINTS
                and not self.partial_tracker.is_closed(ticket)
            ):
                close_vol = round(volume * TP1_CLOSE_PCT / XAUUSD_LOT_STEP) * XAUUSD_LOT_STEP
                close_vol = max(XAUUSD_MIN_LOT, close_vol)
                if close_vol < volume:  # don't close entire position
                    try:
                        self.mt5_client.close_position(
                            ticket, volume=close_vol,
                            magic=self.magic_number, comment="TP1",
                        )
                        self.partial_tracker.mark_closed(ticket)
                        volume -= close_vol  # adjust for subsequent SL calcs
                        LOGGER.info(
                            f"TP1 partial close: ticket={ticket} "
                            f"closed={close_vol} remaining={volume:.2f}"
                        )
                    except Exception as e:
                        LOGGER.error(f"TP1 partial close failed: ticket={ticket} {e}")

            # ── 2. Breakeven ──────────────────────────────────────
            if self.use_breakeven and profit_points >= BE_TRIGGER_POINTS:
                be_sl = (
                    entry_price + BE_OFFSET_POINTS * XAUUSD_POINT if is_buy
                    else entry_price - BE_OFFSET_POINTS * XAUUSD_POINT
                )
                # Only move SL if it improves the position
                sl_improved = (
                    (is_buy and be_sl > current_sl)
                    or (not is_buy and (current_sl == 0 or be_sl < current_sl))
                )
                if sl_improved:
                    try:
                        self.mt5_client.modify_position(ticket, sl=be_sl)
                        current_sl = be_sl
                        LOGGER.info(
                            f"Breakeven: ticket={ticket} SL→{be_sl:.2f}"
                        )
                    except Exception as e:
                        LOGGER.error(f"Breakeven modify failed: ticket={ticket} {e}")

            # ── 3. Trailing stop ──────────────────────────────────
            if self.use_trailing and profit_points >= TRAIL_TRIGGER_POINTS:
                trail_sl = (
                    current_price - TRAIL_DISTANCE_POINTS * XAUUSD_POINT if is_buy
                    else current_price + TRAIL_DISTANCE_POINTS * XAUUSD_POINT
                )
                # Only trail if it moves SL in the right direction
                sl_improved = (
                    (is_buy and trail_sl > current_sl)
                    or (not is_buy and (current_sl == 0 or trail_sl < current_sl))
                )
                if sl_improved:
                    try:
                        self.mt5_client.modify_position(ticket, sl=trail_sl)
                        LOGGER.info(
                            f"Trailing: ticket={ticket} SL→{trail_sl:.2f} "
                            f"(price={current_price:.2f}, profit={profit_points:.0f}pt)"
                        )
                    except Exception as e:
                        LOGGER.error(f"Trail modify failed: ticket={ticket} {e}")

        # Clean up tracker for closed positions
        self.partial_tracker.purge_stale(active_tickets)

    # ──────────────────────────────────────────────────────────────────────
    # Sizing and order management
    # ──────────────────────────────────────────────────────────────────────

    def _compute_lot_size(self, balance: float) -> float:
        """
        Fixed-SL position sizing.
        Lot = risk_amount / (SL_dollars × contract_size).
        Clamped to [MIN_LOT, MAX_LOT], rounded to LOT_STEP.
        """
        sl_dollars = SL_POINTS * XAUUSD_POINT  # 300 × 0.01 = $3.00
        risk_amount = balance * self.risk_pct   # balance × 0.005
        raw_lots = risk_amount / (sl_dollars * XAUUSD_CONTRACT)
        rounded = round(raw_lots / XAUUSD_LOT_STEP) * XAUUSD_LOT_STEP
        return max(XAUUSD_MIN_LOT, min(rounded, XAUUSD_MAX_LOT))

    def _compute_sl_tp(
        self, signal: str, entry_price: float,
    ) -> tuple[float, float]:
        """Fixed-point SL/TP anchored to live entry price."""
        sl_dist = SL_POINTS * XAUUSD_POINT  # $3.00
        tp_dist = TP_POINTS * XAUUSD_POINT  # $4.50
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

    # ──────────────────────────────────────────────────────────────────────
    # Main entry point
    # ──────────────────────────────────────────────────────────────────────

    def evaluate(self) -> Optional[str]:
        """
        Full evaluation cycle.

        Filter order matches the project's risk management layers:
          1. Session filter
          2. Friday cutoff
          3. Drawdown guard (persistent peak tracking)
          4. Daily trade cap (DB-queried)
          5. Position dedup (magic number)
          6. Spread filter (live tick)

        Returns signal string ('BUY'/'SELL') or None.
        """
        start = _time.monotonic()
        LOGGER.info("ASQSafeScalping evaluation started")

        now = datetime.now(timezone.utc)

        # ── Manage existing positions (always, even outside session) ──
        self.manage_positions()

        # ── 1. Session filter (gates new entries only) ────────────
        if not self._check_session(now):
            LOGGER.info("Outside trading session, skipping")
            return None

        # ── 2. Friday cutoff ──────────────────────────────────────
        if not self._check_friday_cutoff(now):
            return None

        # ── Account info ──────────────────────────────────────────
        account_info = self._get_account_info()
        if account_info is None:
            return None
        balance, equity, login = account_info

        # ── 3. Drawdown guard (persistent peak tracking) ──────────
        if self.drawdown_guard.is_tripped(equity=equity):
            LOGGER.warning("Drawdown guard tripped — halting")
            return None
        self.drawdown_guard.update(equity=equity)

        # ── 4. Daily trade cap (DB-queried) ───────────────────────
        if not self._check_daily_cap():
            return None

        # ── Fetch candles ─────────────────────────────────────────
        min_bars = self.ema_slow_period + self.breakout_lookback + 20
        df = self._fetch_candles()
        if df is None or len(df) < min_bars:
            LOGGER.warning(
                f"Insufficient candle data: got {len(df) if df is not None else 0}, "
                f"need {min_bars}"
            )
            return None

        # ── Signal generation (conditions 1–6) ────────────────────
        signal, atr_value = self._generate_signal(df)
        LOGGER.info(f"Signal={signal} ATR={atr_value:.4f}")

        if signal is None:
            LOGGER.info(f"No signal. Duration={_time.monotonic() - start:.2f}s")
            return None

        # ── Condition 7: H1 confirmation ──────────────────────────
        if not self._check_h1_confirmation(signal):
            return None

        # ── 5. Position dedup ─────────────────────────────────────
        if self._has_open_position():
            return None

        # ── 6. Spread filter (also fetches tick for entry price) ──
        spread_ok, tick = self._check_spread()
        if not spread_ok:
            return None

        # ── Size & execute ────────────────────────────────────────
        # Anchor SL/TP to live ask (BUY) or bid (SELL), not signal bar close
        if tick:
            entry_price = tick["ask"] if signal == "BUY" else tick["bid"]
        else:
            entry_price = float(df.iloc[-2]["close"])

        lot_size = self._compute_lot_size(balance)
        sl, tp = self._compute_sl_tp(signal, entry_price)

        LOGGER.info(
            f"Placing {signal}: symbol={SYMBOL} lots={lot_size} "
            f"sl={sl:.2f} tp={tp:.2f} entry={entry_price:.2f} "
            f"atr={atr_value:.4f} balance={balance:.2f}"
        )
        self._place_order(signal, lot_size, sl, tp, login)

        LOGGER.info(
            f"Evaluation complete. Signal={signal} "
            f"Duration={_time.monotonic() - start:.2f}s"
        )
        return signal
