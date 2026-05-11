"""qhf.engines.strategies.asq_safe_scalping — ASQ SafeScalping v1.20 adapter.

Faithful backtesting.py translation of the MQL5 EA by AlgoSphere Quant
(Robin2.0): https://www.mql5.com/en/code/71189

Ground-truth source: the MQL5 .mq5 file (full EA source, not the Pine Script
recreation). Default parameters match the Phase 1 optimized preset.

IMPORTANT DIFFERENCES FROM THE PYTHON CLASS (qhf/strategies in the live app)
-------------------------------------------------------------------------------
1. SL/TP: The MQL5 EA uses FIXED POINTS, not ATR multiples. The live Python
   class (ASQSafeScalpingStrategy) incorrectly uses ATR-based exits. This
   adapter uses fixed points, matching the real EA. For Pepperstone XAUUSD
   (SYMBOL_DIGITS=2): 1 point = $0.01/oz.

2. Exit management: The real EA runs breakeven, trailing stop, and partial
   close in OnTick. This adapter runs them at bar-close (in next()), which
   is a bar-level approximation. For M5 bars, this is reasonable — the
   maximum one-bar error is bounded by the bar's range.

3. MTF confirmation: Computed by resampling the M5 close series to H1 and
   computing EMA(20) and EMA(50) on the H1 series, then forward-filling back
   to M5 frequency. This approximates what the EA does via H1 indicator handles.
   Small differences arise from the EMA seed bar calculation.

4. Session filter: Implemented in next() using bar timestamps, NOT via pre-
   filtering bars. Friday cutoff is included.

5. Spread filter: Not modelled (requires real-time tick data).

6. News filter: Not modelled.

PHASE 1 PRESET PARAMETERS (AlgoSphere Quant optimized, all fixed)
------------------------------------------------------------------
EMA: 50 / 200 (M5 basis)
RSI: 14, buy 45-65, sell 35-55
Breakout: lookback 15, buffer 0.3, ATR period 50
SL/TP: 300pt / 450pt = $3.00 / $4.50 (R:R = 1.5:1)
Breakeven: start 150pt, offset 20pt
Trailing: start 200pt, step 100pt
Partial close: TP1 at 200pt, close 50%
MTF: H1 EMA(20) / EMA(50)
Session: 08:00-17:00, Friday cutoff 14:00
Risk: 0.5% per trade

Note: PHASE 2-4 optimization should be run in MT5's own Strategy Tester,
then the winning parameters loaded into this class for OOS validation via
the qhf harness.
"""

from __future__ import annotations

from typing import Set

import numpy as np
import pandas as pd
from backtesting import Strategy

from qhf.engines.indicators import atr as calc_atr

# Pepperstone XAUUSD: 2 decimal places, 1 point = $0.01/oz
XAUUSD_POINT = 0.01
XAUUSD_CONTRACT_SIZE = 100.0  # oz per standard lot
XAUUSD_MIN_LOT = 0.01
XAUUSD_MAX_LOT = 0.10
XAUUSD_LOT_STEP = 0.01


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


class ASQSafeScalping(Strategy):
    """ASQ SafeScalping v1.20 — Phase 1 preset.

    Run on M5 XAUUSD bars filtered to session hours (08:00-17:00 UTC)
    using session_hours=(8, 17) in run_backtest / run_walk_forward.
    The session filter in this class provides redundant safety for Friday
    cutoff (which can't be expressed as a simple hour range).
    """

    # -- EMA trend filter (Phase 1 fixed) -----------------------------------
    ema_fast: int = 50
    ema_slow: int = 200
    trend_strength: str = "MODERATE"   # "WEAK", "MODERATE", "STRONG" → 0.1/0.3/0.6 × ATR

    # -- ATR (for trend strength calculation, not for SL/TP) ----------------
    atr_period: int = 50

    # -- MTF H1 confirmation (Phase 1 enabled) ------------------------------
    use_mtf: bool = True
    mtf_ema_fast: int = 20
    mtf_ema_slow: int = 50

    # -- RSI filter (Phase 1 fixed) -----------------------------------------
    rsi_period: int = 14
    rsi_buy_lo: float = 45.0
    rsi_buy_hi: float = 65.0
    rsi_sell_lo: float = 35.0
    rsi_sell_hi: float = 55.0

    # -- Breakout detection (Phase 1 fixed) ---------------------------------
    breakout_lookback: int = 15
    breakout_buffer: float = 0.3    # × ATR

    # -- SL / TP in POINTS (Pepperstone XAUUSD: 1 pt = $0.01) ---------------
    sl_points: int = 300             # $3.00
    tp_points: int = 450             # $4.50

    # -- Breakeven (Phase 1 enabled) ----------------------------------------
    use_breakeven: bool = True
    breakeven_start: int = 150       # points profit before moving SL to BE
    breakeven_offset: int = 20       # points above entry for BE SL (BE + offset)

    # -- Trailing stop (Phase 1 enabled) ------------------------------------
    use_trailing: bool = True
    trail_start: int = 200           # points profit before trailing activates
    trail_step: int = 100            # trail distance in points

    # -- Partial close (Phase 1 enabled) ------------------------------------
    use_partial: bool = True
    tp1_points: int = 200            # points profit to trigger partial close
    tp1_pct: float = 0.50            # fraction to close at TP1

    # -- Position sizing ----------------------------------------------------
    use_risk_pct: bool = True
    risk_pct: float = 0.005          # 0.5% of equity
    fixed_lots: float = 0.01

    # -- Daily trade cap & drawdown halt ------------------------------------
    max_day_trades: int = 4
    max_dd_pct: float = 8.0          # halt if DD from peak ≥ 8%

    # -- Session filter (in addition to runner's session_hours pre-filter) --
    session_start: int = 8           # UTC hour
    session_end: int = 17            # UTC hour (exclusive)
    friday_cutoff: int = 14          # stop on Friday at this hour

    # -- Internal state (reset each backtest run) ---------------------------
    _peak_equity: float = 0.0
    _day_trades: int = 0
    _last_day: str = ""
    _partial_done: Set[int] = None   # trade entry_bar indices that had TP1 partial close

    def init(self):
        close = pd.Series(self.data.Close, index=self.data.df.index)
        high  = pd.Series(self.data.High,  index=self.data.df.index)
        low   = pd.Series(self.data.Low,   index=self.data.df.index)

        # -- M5 indicators --------------------------------------------------
        ef = _ema(close, self.ema_fast).ffill().values
        es = _ema(close, self.ema_slow).ffill().values
        rsi_arr = _rsi(close, self.rsi_period).fillna(50.0).values
        atr_arr = calc_atr(high, low, close, self.atr_period).ffill().values

        # Rolling breakout high/low: max/min over lookback bars BEFORE the
        # signal bar. shift(1) so that at bar t, we have the max/min of
        # bars t-1 down to t-lookback (matching MQL5's i=2..lookback+1).
        brk_hi = high.rolling(self.breakout_lookback).max().shift(1).ffill().values
        brk_lo = low.rolling(self.breakout_lookback).min().shift(1).ffill().values

        self._ef      = self.I(lambda: ef,      name="EMA_fast")
        self._es      = self.I(lambda: es,       name="EMA_slow")
        self._rsi     = self.I(lambda: rsi_arr,  name="RSI")
        self._atr     = self.I(lambda: atr_arr,  name="ATR")
        self._brk_hi  = self.I(lambda: brk_hi,   name="BrkHi")
        self._brk_lo  = self.I(lambda: brk_lo,   name="BrkLo")

        # -- MTF H1 EMA (resample M5 → H1, forward-fill back to M5) --------
        if self.use_mtf:
            h1_close = close.resample("h").last().ffill()
            htf_ef = _ema(h1_close, self.mtf_ema_fast).ffill()
            htf_es = _ema(h1_close, self.mtf_ema_slow).ffill()
            # Forward-fill back to M5 frequency
            htf_ef_m5 = htf_ef.reindex(close.index, method="ffill").ffill().values
            htf_es_m5 = htf_es.reindex(close.index, method="ffill").ffill().values
            self._htf_ef = self.I(lambda: htf_ef_m5, name="HTF_EMA_fast")
            self._htf_es = self.I(lambda: htf_es_m5, name="HTF_EMA_slow")
        else:
            self._htf_ef = None
            self._htf_es = None

        # -- State ----------------------------------------------------------
        self._peak_equity = float(self.equity)
        self._day_trades = 0
        self._last_day = ""
        self._partial_done = set()

    def next(self):
        bar_dt = self.data.index[-1]   # current bar's timestamp

        # -- Drawdown halt --------------------------------------------------
        eq = float(self.equity)
        if eq > self._peak_equity:
            self._peak_equity = eq
        dd = ((self._peak_equity - eq) / self._peak_equity * 100.0
              if self._peak_equity > 0 else 0.0)
        if dd >= self.max_dd_pct:
            return

        # -- Exit management for open positions (bar-level approximation) ---
        # Order matters: partial close first, then breakeven, then trailing.
        if self.trades:
            self._manage_exits(bar_dt)

        # -- Session filter -------------------------------------------------
        if not self._pass_session(bar_dt):
            return

        # -- Day cap --------------------------------------------------------
        today = bar_dt.strftime("%Y-%m-%d")
        if today != self._last_day:
            self._last_day = today
            self._day_trades = 0
        if self.max_day_trades > 0 and self._day_trades >= self.max_day_trades:
            return

        # -- One position at a time -----------------------------------------
        if self.position:
            return

        # -- Indicator values at last CLOSED bar ([-1] in next() = current) -
        # MQL5 convention: c1 = bar[1] = last closed bar.
        # In backtesting.py's next(), [-1] IS the current (just closed) bar.
        if len(self._ef) < 3:
            return

        ef    = float(self._ef[-1])
        es    = float(self._es[-1])
        rsi   = float(self._rsi[-1])
        atr   = float(self._atr[-1])
        brk_h = float(self._brk_hi[-1])
        brk_l = float(self._brk_lo[-1])
        c1    = float(self.data.Close[-1])   # close[1] in MQL5 = last closed bar
        c2    = float(self.data.Close[-2])   # close[2] in MQL5 = bar before that

        if any(np.isnan(v) for v in [ef, es, rsi, atr, brk_h, brk_l]):
            return
        if atr == 0:
            return

        # -- Trend strength filter ------------------------------------------
        sep = abs(ef - es)
        mult = {"WEAK": 0.1, "MODERATE": 0.3, "STRONG": 0.6}.get(
            self.trend_strength, 0.3
        )
        if sep < atr * mult:
            return

        # -- MTF filter -----------------------------------------------------
        mtf_buy = mtf_sell = True
        if self.use_mtf and self._htf_ef is not None:
            htf_ef = float(self._htf_ef[-1])
            htf_es = float(self._htf_es[-1])
            if not np.isnan(htf_ef) and not np.isnan(htf_es):
                mtf_buy  = htf_ef > htf_es
                mtf_sell = htf_ef < htf_es

        # -- Derived conditions (mirrors MQL5 OnTick logic exactly) ---------
        bull_trend   = ef > es
        bear_trend   = ef < es
        above_both   = c1 > ef and c1 > es
        below_both   = c1 < ef and c1 < es
        buf          = atr * self.breakout_buffer
        bull_break   = (c1 > brk_h - buf) and (c2 <= brk_h)
        bear_break   = (c1 < brk_l + buf) and (c2 >= brk_l)
        rsi_buy      = self.rsi_buy_lo  <= rsi <= self.rsi_buy_hi
        rsi_sell     = self.rsi_sell_lo <= rsi <= self.rsi_sell_hi
        bull_mom     = c1 > c2
        bear_mom     = c1 < c2

        pt  = XAUUSD_POINT
        ask = c1          # use close as fill price (bar-close convention)
        bid = c1

        lot = self._calc_lot(ask)
        if lot <= 0:
            return
        # Convert lots → oz (units). backtesting.py size < 1.0 is interpreted
        # as a fraction of maximum position — always pass as oz (integer-ish).
        size_oz = round(lot * 100, 2)

        sl_d = self.sl_points * pt
        tp_d = self.tp_points * pt

        if bull_trend and above_both and bull_break and rsi_buy and bull_mom and mtf_buy:
            self.buy(
                size=size_oz,
                sl=round(ask - sl_d, 2),
                tp=round(ask + tp_d, 2),
            )
            self._day_trades += 1

        elif bear_trend and below_both and bear_break and rsi_sell and bear_mom and mtf_sell:
            self.sell(
                size=size_oz,
                sl=round(bid + sl_d, 2),
                tp=round(bid - tp_d, 2),
            )
            self._day_trades += 1

    # -- Exit management helpers --------------------------------------------

    def _manage_exits(self, bar_dt) -> None:
        """Update open trades for breakeven, trailing, and partial close."""
        for trade in list(self.trades):
            entry  = trade.entry_price
            is_long = trade.is_long
            cur    = float(self.data.Close[-1])
            pt     = XAUUSD_POINT

            profit_pts = ((cur - entry) if is_long else (entry - cur)) / pt

            # Partial close at TP1 (only once per trade)
            if self.use_partial and trade.entry_bar not in self._partial_done:
                if profit_pts >= self.tp1_points:
                    try:
                        trade.close(self.tp1_pct)
                        self._partial_done.add(trade.entry_bar)
                    except Exception:
                        pass  # trade may have closed between checks

            # Breakeven — move SL to entry + offset if profit ≥ start
            if self.use_breakeven and profit_pts >= self.breakeven_start:
                be_sl = (round(entry + self.breakeven_offset * pt, 2)
                         if is_long
                         else round(entry - self.breakeven_offset * pt, 2))
                if is_long and (trade.sl is None or trade.sl < be_sl):
                    try:
                        trade.sl = be_sl
                    except Exception:
                        pass
                elif not is_long and (trade.sl is None or trade.sl > be_sl):
                    try:
                        trade.sl = be_sl
                    except Exception:
                        pass

            # Trailing stop
            if self.use_trailing and profit_pts >= self.trail_start:
                trail_sl = (round(cur - self.trail_step * pt, 2)
                            if is_long
                            else round(cur + self.trail_step * pt, 2))
                if is_long and (trade.sl is None or trail_sl > trade.sl):
                    try:
                        trade.sl = trail_sl
                    except Exception:
                        pass
                elif not is_long and (trade.sl is None or trail_sl < trade.sl):
                    try:
                        trade.sl = trail_sl
                    except Exception:
                        pass

    def _pass_session(self, bar_dt) -> bool:
        """Session + Friday filter — matches MQL5 PassSession() logic."""
        dow  = bar_dt.weekday()   # Mon=0, Fri=4, Sat=5, Sun=6
        hour = bar_dt.hour
        if dow >= 5:              # weekend
            return False
        if dow == 4 and hour >= self.friday_cutoff:   # Friday cutoff
            return False
        return self.session_start <= hour < self.session_end

    def _calc_lot(self, entry_price: float) -> float:
        """Position sizing matching MQL5 CalcLot() with risk % mode."""
        if self.use_risk_pct and self.risk_pct > 0:
            risk_amount = float(self.equity) * min(self.risk_pct, 0.05)
            sl_distance = self.sl_points * XAUUSD_POINT   # $/oz
            # risk_amount = lot × contract_size × sl_distance
            raw_lots = risk_amount / (sl_distance * XAUUSD_CONTRACT_SIZE)
        else:
            raw_lots = self.fixed_lots

        # Floor to lot step, clamp
        import math
        stepped = math.floor(raw_lots / XAUUSD_LOT_STEP) * XAUUSD_LOT_STEP
        lot = max(XAUUSD_MIN_LOT, min(XAUUSD_MAX_LOT, round(stepped, 2)))
        return lot
