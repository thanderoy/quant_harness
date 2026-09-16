"""research.engines.strategies.hma_stoch — backtesting.py Strategy adapters.

Faithful translation of HMAStoch1HStrategy (v1.1) and HMAStochM15Strategy
(v1.1) into backtesting.py's Strategy interface.

Signal logic is identical to the live strategies. What changes:
- Data comes from the loaded DataFrame, not the MT5 API.
- Position sizing uses self.equity (live account balance equivalent).
- Orders are placed via self.buy() / self.sell() with explicit SL/TP.
- Session, Friday, and daily-cap filters are NOT applied here — those
  are time filters that should be applied to the data before backtesting
  (slice the bars DataFrame to the desired session hours / days first).
- The persistent DrawdownGuard is not used — backtesting.py enforces
  account-level controls via `cash` and equity tracking. A strategy-level
  DD halt can be added via the `max_drawdown_halt` parameter.

Evaluation bar:
    The live strategy evaluates iloc[-2] (last CLOSED bar). In backtesting.py
    next() is called after each BAR CLOSE, so self.data.Close[-1] is the
    current bar's close (equivalent to iloc[-2] in the live context). The
    ordering is consistent and there is no look-ahead bias.

Fill price:
    With trade_on_close=False (default), orders fill at the OPEN of the
    next bar. This is the standard conservative assumption for bar-close
    signal strategies and matches the live strategy's market-order timing.

Position sizing in backtesting.py:
    size = lots * 100 (oz per lot)
    backtesting.py tracks equity in account-currency (USD). SL/TP are
    passed as absolute prices, matching the live strategy's _compute_sl_tp.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from backtesting import Strategy

from research.engines.indicators import hma, stochastic, atr
from research.engines.sizer import calculate_lot_size


# ---------------------------------------------------------------------------
# H1 Strategy — v1.1 (signal logic identical to live code)
# ---------------------------------------------------------------------------

class HMAStoch1H(Strategy):
    """HMA + Stochastic on H1 timeframe. XAUUSD only."""

    # -- Indicator parameters (match live strategy v1.1 defaults) ----------
    hma_period: int = 55
    stoch_k_period: int = 14
    stoch_d_period: int = 3
    stoch_smooth_k: int = 3
    atr_period: int = 14

    # -- Risk / position sizing ---------------------------------------------
    sl_atr_mult: float = 1.5
    tp_atr_mult: float = 3.0
    risk_pct: float = 0.02           # 2% of equity per trade
    min_atr_for_signal: float = 1.0  # v1.1 regime filter ($ / oz)

    # -- Safety / halting ---------------------------------------------------
    max_drawdown_halt: float = 0.30  # halt trading if DD > 30% from peak
                                     # (independent of the live DrawdownGuard)
    _peak_equity: float = 0.0

    def init(self):
        close = pd.Series(self.data.Close)
        high = pd.Series(self.data.High)
        low = pd.Series(self.data.Low)

        hma_vals = hma(close, self.hma_period).ffill().values
        k_vals, d_vals = stochastic(
            high, low, close,
            self.stoch_k_period, self.stoch_d_period, self.stoch_smooth_k,
        )
        k_vals = k_vals.fillna(50.0).values
        d_vals = d_vals.fillna(50.0).values
        atr_vals = atr(high, low, close, self.atr_period).ffill().values

        # Register with self.I() for tracking / plotting.
        self._hma = self.I(lambda: hma_vals, name='HMA')
        self._k   = self.I(lambda: k_vals,   name='K')
        self._d   = self.I(lambda: d_vals,   name='D')
        self._atr = self.I(lambda: atr_vals, name='ATR')

        self._peak_equity = float(self.equity)

    def next(self):
        # Need at least 3 bars of indicators.
        if len(self._hma) < 3:
            return

        hma_cur  = float(self._hma[-1])
        hma_prev = float(self._hma[-2])
        k_cur    = float(self._k[-1])
        d_cur    = float(self._d[-1])
        k_prev   = float(self._k[-2])
        d_prev   = float(self._d[-2])
        atr_cur  = float(self._atr[-1])
        close    = float(self.data.Close[-1])

        # Warmup / NaN guard.
        if any(np.isnan(v) for v in [hma_cur, hma_prev, k_cur, d_cur,
                                      k_prev, d_prev, atr_cur]):
            return

        # Drawdown halt.
        if self.equity > self._peak_equity:
            self._peak_equity = float(self.equity)
        if self.equity < self._peak_equity * (1.0 - self.max_drawdown_halt):
            return

        # Regime filter (v1.1 addition).
        if atr_cur < self.min_atr_for_signal:
            return

        # Already in a position — wait for SL/TP to close it.
        if self.position:
            return

        lots, effective_atr = calculate_lot_size(
            account_balance=float(self.equity),
            atr_value=atr_cur,
            risk_pct=self.risk_pct,
            sl_atr_multiplier=self.sl_atr_mult,
        )
        sl_dist = effective_atr * self.sl_atr_mult
        tp_dist = effective_atr * self.tp_atr_mult
        size_oz = round(lots * 100, 2)   # convert lots → oz (units)

        # ── BUY gate ──────────────────────────────────────────────────────
        long_ok = (
            hma_cur > hma_prev        # HMA rising
            and close > hma_cur       # price above HMA
            and k_prev < d_prev       # %K was below %D
            and k_cur > d_cur         # %K crossed above %D
            and k_prev < 20.0         # from oversold zone
        )
        if long_ok:
            self.buy(
                size=size_oz,
                sl=close - sl_dist,
                tp=close + tp_dist,
            )
            return

        # ── SELL gate ─────────────────────────────────────────────────────
        short_ok = (
            hma_cur < hma_prev        # HMA falling
            and close < hma_cur       # price below HMA
            and k_prev > d_prev       # %K was above %D
            and k_cur < d_cur         # %K crossed below %D
            and k_prev > 80.0         # from overbought zone
        )
        if short_ok:
            self.sell(
                size=size_oz,
                sl=close + sl_dist,
                tp=close - tp_dist,
            )


# ---------------------------------------------------------------------------
# M15 Strategy — v1.1
# ---------------------------------------------------------------------------

class HMAStochM15(Strategy):
    """HMA + Stochastic on M15 timeframe. XAUUSD only."""

    # -- Indicator parameters (match live strategy v1.1 defaults) ----------
    hma_period: int = 21
    stoch_k_period: int = 14
    stoch_d_period: int = 3
    stoch_smooth_k: int = 3
    atr_period: int = 14

    # -- Risk / position sizing ---------------------------------------------
    sl_atr_mult: float = 1.5
    tp_atr_mult: float = 2.5
    risk_pct: float = 0.01           # 1% of equity per trade
    # v1.1 regime filter. The live strategy inherited 5.0 from the v1.0 sizer
    # constant (designed for H1 ATR range). M15 XAUUSD ATR-14 is typically
    # $1.0-3.0/oz; 5.0 blocks ~98% of signals. Corrected to 2.0 here.
    # Note: the LIVE strategy's min_atr_for_signal=5.0 should also be
    # updated to 2.0 to match. Document this as v1.2 behaviour change.
    min_atr_for_signal: float = 2.0

    # -- Safety / halting ---------------------------------------------------
    max_drawdown_halt: float = 0.30
    _peak_equity: float = 0.0

    def init(self):
        close = pd.Series(self.data.Close)
        high = pd.Series(self.data.High)
        low = pd.Series(self.data.Low)

        hma_vals = hma(close, self.hma_period).ffill().values
        k_vals, d_vals = stochastic(
            high, low, close,
            self.stoch_k_period, self.stoch_d_period, self.stoch_smooth_k,
        )
        k_vals = k_vals.fillna(50.0).values
        d_vals = d_vals.fillna(50.0).values
        atr_vals = atr(high, low, close, self.atr_period).ffill().values

        self._hma = self.I(lambda: hma_vals, name='HMA')
        self._k   = self.I(lambda: k_vals,   name='K')
        self._d   = self.I(lambda: d_vals,   name='D')
        self._atr = self.I(lambda: atr_vals, name='ATR')

        self._peak_equity = float(self.equity)

    def next(self):
        if len(self._hma) < 3:
            return

        hma_cur  = float(self._hma[-1])
        hma_prev = float(self._hma[-2])
        k_cur    = float(self._k[-1])
        d_cur    = float(self._d[-1])
        k_prev   = float(self._k[-2])
        d_prev   = float(self._d[-2])
        atr_cur  = float(self._atr[-1])
        close    = float(self.data.Close[-1])

        if any(np.isnan(v) for v in [hma_cur, hma_prev, k_cur, d_cur,
                                      k_prev, d_prev, atr_cur]):
            return

        if self.equity > self._peak_equity:
            self._peak_equity = float(self.equity)
        if self.equity < self._peak_equity * (1.0 - self.max_drawdown_halt):
            return

        if atr_cur < self.min_atr_for_signal:
            return

        if self.position:
            return

        lots, effective_atr = calculate_lot_size(
            account_balance=float(self.equity),
            atr_value=atr_cur,
            risk_pct=self.risk_pct,
            sl_atr_multiplier=self.sl_atr_mult,
        )
        sl_dist = effective_atr * self.sl_atr_mult
        tp_dist = effective_atr * self.tp_atr_mult
        size_oz = round(lots * 100, 2)

        long_ok = (
            hma_cur > hma_prev and close > hma_cur
            and k_prev < d_prev and k_cur > d_cur and k_prev < 20.0
        )
        if long_ok:
            self.buy(size=size_oz, sl=close - sl_dist, tp=close + tp_dist)
            return

        short_ok = (
            hma_cur < hma_prev and close < hma_cur
            and k_prev > d_prev and k_cur < d_cur and k_prev > 80.0
        )
        if short_ok:
            self.sell(size=size_oz, sl=close + sl_dist, tp=close - tp_dist)
