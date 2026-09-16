"""
ASQ SafeScalping v1.20 — backtesting.py Adapter
================================================
Source  : mql5.com/en/code/71189 (AlgoSphere Quant / Robin2.0)
Adapter : research.engines harness, compatible with btpy_runner.py

BUG FIXES vs MQL5 original
───────────────────────────
BUG-2  Partial-close ticket array never pruned on the original.
       After an EA restart, any trade that already received a partial
       close would get partial-closed again.
       FIX: replaced with a two-leg entry (TP1 leg + remainder leg).
       No ticket tracking required — each leg has its own independent TP.
       P&L is equivalent when TP1 is hit cleanly; minor divergence if SL
       hits before TP1 (both legs stop out, which is correct behaviour).

BUG-3  DD guard compared equity vs. peak *balance* (not peak equity).
       During a drawdown with open positions, equity could fall well below
       the configured threshold without triggering the halt.
       FIX: g_peakEquity is updated every bar from self.equity; the DD
       ratio is computed against that, not against a stale balance figure.

KNOWN DIVERGENCES FROM MT5 ORIGINAL
─────────────────────────────────────
1. Breakeven / trailing applied at bar close, not every tick.
   Conservative bias: some intra-bar activations are missed.
   Effect on metrics: slightly lower win rate, slightly wider realised DD
   vs MT5 Strategy Tester in "Every Tick" mode.

2. Partial close implemented as two simultaneous legs at entry time.
   (See BUG-2 fix above.)

3. Spread filter: a fixed spread cost is deducted via backtesting.Backtest()
   commission arg. Dynamic intra-bar spread widening is not modelled.

4. News filter: NOT modelled — no real-time news feed available.

5. MTF confirmation: H1 data must be resampled from M5 bars and passed in
   as `h1_close` class attribute before running. If omitted, MTF is
   automatically disabled regardless of use_mtf setting.

6. Session timezone: assumes the DataFrame index is UTC.
   Caller is responsible for ensuring this.

7. `point` is hardcoded to 0.01 for XAUUSD (5-digit broker pricing).
   Override _get_point() if your data feed uses different precision.

SIZING NOTE
───────────
size = risk_amount / sl_distance (both in price terms).
In backtesting.py this means: P&L = size × Δprice.
For XAUUSD at $3000/oz, 0.5% risk on $100 equity with a 300-pt SL:
  risk_amount = $0.50
  sl_distance = 300 × $0.01 = $3.00
  size        = 0.167 oz  ≈ 0.00167 MT5 lots (below min 0.01 lot)
This is expected at $100 capital — the harness measures Sharpe/DD
in return-space, not absolute $ terms, so sub-lot sizing is fine
for validation purposes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from backtesting import Strategy


# ─────────────────────────────────────────────────────────────────────────────
# Indicator helpers (self-contained, no external dependency)
# ─────────────────────────────────────────────────────────────────────────────

def _ema(series: pd.Series, period: int) -> np.ndarray:
    return series.ewm(span=period, adjust=False).mean().to_numpy()


def _rsi(close: pd.Series, period: int) -> np.ndarray:
    delta = close.diff()
    gain  = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss  = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
    rs    = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).to_numpy()


def _atr(high: pd.Series, low: pd.Series, close: pd.Series,
         period: int) -> np.ndarray:
    prev = close.shift(1)
    tr   = pd.concat([high - low,
                      (high - prev).abs(),
                      (low  - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean().to_numpy()


def _rolling_high(high: pd.Series, lookback: int) -> np.ndarray:
    """
    N-bar rolling high of bars *prior* to the signal bar.
    Mirrors MQL5 loop: for(i=2; i<=lookback+1; i++) which starts at bar[2].
    shift(1) excludes bar[0] (current forming bar);
    rolling(lookback) then covers bars [1..lookback].
    """
    return high.shift(1).rolling(lookback).max().to_numpy()


def _rolling_low(low: pd.Series, lookback: int) -> np.ndarray:
    return low.shift(1).rolling(lookback).min().to_numpy()


# ─────────────────────────────────────────────────────────────────────────────
# Strategy
# ─────────────────────────────────────────────────────────────────────────────

class ASQSafeScalping(Strategy):
    """
    backtesting.py adapter for ASQ SafeScalping v1.20.

    Default parameters match the Phase 1 preset (structural baseline).
    To run the optimised Phase 2 / grid preset, override via
    Backtest(...).optimize() or pass **params to the constructor.
    """

    # ── EMA trend ──────────────────────────────────────────────────────────
    ema_fast       : int   = 50
    ema_slow       : int   = 200
    # 0 = weak (0.1×ATR), 1 = moderate (0.3×ATR), 2 = strong (0.6×ATR)
    trend_strength : int   = 1

    # ── RSI ────────────────────────────────────────────────────────────────
    rsi_period     : int   = 14
    rsi_buy_min    : float = 45.0
    rsi_buy_max    : float = 65.0
    rsi_sell_min   : float = 35.0
    rsi_sell_max   : float = 55.0

    # ── Breakout ───────────────────────────────────────────────────────────
    breakout_lookback : int   = 15
    breakout_buffer   : float = 0.3    # fraction of ATR
    atr_period        : int   = 50

    # ── SL / TP (in price points — for XAUUSD: 1 point = $0.01) ───────────
    sl_points : int = 300
    tp_points : int = 450

    # ── Breakeven ──────────────────────────────────────────────────────────
    use_breakeven    : bool = True
    breakeven_start  : int  = 150     # points of profit before activation
    breakeven_offset : int  = 20      # points above/below open for BE SL

    # ── Trailing stop ──────────────────────────────────────────────────────
    use_trailing : bool = True
    trail_start  : int  = 200         # points of profit before activation
    trail_step   : int  = 100         # trail distance in points

    # ── Partial close (two-leg approximation — see BUG-2 fix) ─────────────
    use_partial_close : bool  = True
    tp1_points        : int   = 200
    tp1_close_pct     : float = 50.0  # % of position closed at TP1

    # ── Risk ───────────────────────────────────────────────────────────────
    risk_pct       : float = 0.5   # % equity risked per trade (signal)
    max_day_trades : int   = 4     # 0 = unlimited
    max_dd_pct     : float = 8.0   # % peak-equity drawdown halt

    # ── Session ────────────────────────────────────────────────────────────
    use_session    : bool = True
    session_start  : int  = 8      # UTC hour, inclusive
    session_end    : int  = 17     # UTC hour, exclusive
    avoid_friday   : bool = True
    friday_cutoff  : int  = 14     # UTC hour

    # ── MTF ────────────────────────────────────────────────────────────────
    # Set use_mtf=True AND assign h1_close (np.ndarray, same length as bars)
    # as a class attribute before running. Example:
    #   ASQSafeScalping.h1_close = resample_to_h1(df['Close'])
    #   ASQSafeScalping.use_mtf  = True
    use_mtf      : bool = False
    mtf_ema_fast : int  = 20
    mtf_ema_slow : int  = 50

    # ──────────────────────────────────────────────────────────────────────
    # init
    # ──────────────────────────────────────────────────────────────────────

    def init(self) -> None:
        close = pd.Series(self.data.Close, dtype=float)
        high  = pd.Series(self.data.High,  dtype=float)
        low   = pd.Series(self.data.Low,   dtype=float)

        # Core indicators
        self.i_ema_fast = self.I(_ema, close, self.ema_fast,
                                 name='EMA_fast', overlay=True)
        self.i_ema_slow = self.I(_ema, close, self.ema_slow,
                                 name='EMA_slow', overlay=True)
        self.i_rsi      = self.I(_rsi, close, self.rsi_period, name='RSI')
        self.i_atr      = self.I(_atr, high, low, close,
                                 self.atr_period, name='ATR')
        self.i_hi       = self.I(_rolling_high, high,
                                 self.breakout_lookback, name='RollingHigh',
                                 overlay=True)
        self.i_lo       = self.I(_rolling_low,  low,
                                 self.breakout_lookback, name='RollingLow',
                                 overlay=True)

        # MTF indicators — require h1_close to be set externally
        self._mtf_active = False
        if self.use_mtf and hasattr(self.__class__, 'h1_close'):
            h1 = pd.Series(self.__class__.h1_close, dtype=float)
            if len(h1) == len(close):
                self.i_mtf_fast = self.I(_ema, h1, self.mtf_ema_fast,
                                         name='MTF_EMA_fast')
                self.i_mtf_slow = self.I(_ema, h1, self.mtf_ema_slow,
                                         name='MTF_EMA_slow')
                self._mtf_active = True
            else:
                import warnings
                warnings.warn(
                    f"[ASQ] h1_close length {len(h1)} != bars {len(close)}. "
                    "MTF disabled.", RuntimeWarning)

        # ── State (BUG-3 fix: peak equity, not peak balance) ──────────────
        self._peak_equity  : float    = float(self.equity)
        self._today_date   : object   = None
        self._today_trades : int      = 0

    # ──────────────────────────────────────────────────────────────────────
    # next  (called once per bar close)
    # ──────────────────────────────────────────────────────────────────────

    def next(self) -> None:
        # ── Tick-level management approximated at bar close ────────────────
        if self.use_breakeven:
            self._manage_breakeven()
        if self.use_trailing:
            self._manage_trailing()

        # ── BUG-3 fix: update peak equity every bar ────────────────────────
        eq = float(self.equity)
        if eq > self._peak_equity:
            self._peak_equity = eq

        # ── Drawdown halt ──────────────────────────────────────────────────
        if self._peak_equity > 0:
            dd_pct = (self._peak_equity - eq) / self._peak_equity * 100.0
            if dd_pct >= self.max_dd_pct:
                return

        # ── Day cap ────────────────────────────────────────────────────────
        today = self.data.index[-1].date()
        if today != self._today_date:
            self._today_date   = today
            self._today_trades = 0
        if self.max_day_trades > 0 and self._today_trades >= self.max_day_trades:
            return

        # ── One signal at a time ───────────────────────────────────────────
        if self.position:
            return

        # ── Session filter ─────────────────────────────────────────────────
        if self.use_session and not self._pass_session():
            return

        # ── Indicator reads — use bar[-1] (last closed bar) ───────────────
        ema_f = float(self.i_ema_fast[-1])
        ema_s = float(self.i_ema_slow[-1])
        rsi   = float(self.i_rsi[-1])
        atr   = float(self.i_atr[-1])
        hi_n  = float(self.i_hi[-1])   # N-bar rolling high, bars prior to [-1]
        lo_n  = float(self.i_lo[-1])
        c1    = float(self.data.Close[-1])
        c2    = float(self.data.Close[-2])

        if any(np.isnan(v) for v in (ema_f, ema_s, rsi, atr, hi_n, lo_n)):
            return
        if atr == 0:
            return

        # ── Condition 1: EMA trend direction ──────────────────────────────
        bull_trend = ema_f > ema_s
        bear_trend = ema_f < ema_s

        # ── Condition 2: Trend strength ────────────────────────────────────
        _mult_map  = {0: 0.1, 1: 0.3, 2: 0.6}
        min_sep    = atr * _mult_map.get(int(self.trend_strength), 0.3)
        if abs(ema_f - ema_s) < min_sep:
            return

        # ── Condition 3: Price position relative to both EMAs ─────────────
        above_both = c1 > ema_f and c1 > ema_s
        below_both = c1 < ema_f and c1 < ema_s

        # ── Condition 4: Breakout detection ───────────────────────────────
        buf        = atr * float(self.breakout_buffer)
        bull_break = (c1 > hi_n - buf) and (c2 <= hi_n)
        bear_break = (c1 < lo_n + buf) and (c2 >= lo_n)

        # ── Condition 5: RSI filter ────────────────────────────────────────
        rsi_buy  = float(self.rsi_buy_min)  <= rsi <= float(self.rsi_buy_max)
        rsi_sell = float(self.rsi_sell_min) <= rsi <= float(self.rsi_sell_max)

        # ── Condition 6: Momentum (bar-over-bar) ──────────────────────────
        bull_mom = c1 > c2
        bear_mom = c1 < c2

        # ── Condition 7: MTF EMA agreement (optional) ─────────────────────
        mtf_buy = mtf_sell = True
        if self._mtf_active:
            mf = float(self.i_mtf_fast[-1])
            ms = float(self.i_mtf_slow[-1])
            if not (np.isnan(mf) or np.isnan(ms)):
                mtf_buy  = mf > ms
                mtf_sell = mf < ms

        # ── Position sizing ────────────────────────────────────────────────
        pt      = self._get_point()
        sl_dist = self.sl_points * pt
        tp_dist = self.tp_points * pt
        size    = self._calc_size(sl_dist)
        if size <= 0:
            return

        # ── Entries ────────────────────────────────────────────────────────
        long_signal  = (bull_trend and above_both and bull_break
                        and rsi_buy and bull_mom and mtf_buy)
        short_signal = (bear_trend and below_both and bear_break
                        and rsi_sell and bear_mom and mtf_sell)

        if long_signal:
            self._enter_long(size, sl_dist, tp_dist, pt)

        elif short_signal:
            self._enter_short(size, sl_dist, tp_dist, pt)

    # ──────────────────────────────────────────────────────────────────────
    # Entry helpers
    # ──────────────────────────────────────────────────────────────────────

    def _enter_long(self, size: float, sl_dist: float,
                    tp_dist: float, pt: float) -> None:
        entry = float(self.data.Close[-1])
        sl    = entry - sl_dist
        tp    = entry + tp_dist

        if self.use_partial_close:
            tp1      = entry + self.tp1_points * pt
            size_tp1 = self._coerce_size(size * float(self.tp1_close_pct) / 100.0)
            size_rem = self._coerce_size(size - size * float(self.tp1_close_pct) / 100.0)
            if size_tp1 > 0 and size_rem > 0:
                self.buy(size=size_tp1, sl=sl, tp=tp1)   # TP1 leg
                self.buy(size=size_rem,  sl=sl, tp=tp)   # Remainder leg
                self._today_trades += 1
                return

        self.buy(size=size, sl=sl, tp=tp)
        self._today_trades += 1

    def _enter_short(self, size: float, sl_dist: float,
                     tp_dist: float, pt: float) -> None:
        entry = float(self.data.Close[-1])
        sl    = entry + sl_dist
        tp    = entry - tp_dist

        if self.use_partial_close:
            tp1      = entry - self.tp1_points * pt
            size_tp1 = self._coerce_size(size * float(self.tp1_close_pct) / 100.0)
            size_rem = self._coerce_size(size - size * float(self.tp1_close_pct) / 100.0)
            if size_tp1 > 0 and size_rem > 0:
                self.sell(size=size_tp1, sl=sl, tp=tp1)
                self.sell(size=size_rem,  sl=sl, tp=tp)
                self._today_trades += 1
                return

        self.sell(size=size, sl=sl, tp=tp)
        self._today_trades += 1

    @staticmethod
    def _coerce_size(size: float) -> float:
        """
        Enforce backtesting.py size constraints:
          0 < size < 1  → fractional equity (keep as-is)
          size >= 1     → must be a whole number (floor)
          otherwise     → invalid, return 0
        """
        if size <= 0:
            return 0.0
        if size < 1.0:
            return size
        return float(int(size))

    # ──────────────────────────────────────────────────────────────────────
    # Exit management (bar-close approximation of tick-level MT5 handlers)
    # ──────────────────────────────────────────────────────────────────────

    def _manage_breakeven(self) -> None:
        """
        Move SL to breakeven (open ± offset) once price has moved
        breakeven_start points in our favour.
        Applied to all open trades (both legs if partial close is active).
        """
        pt = self._get_point()
        for trade in self.trades:
            op = float(trade.entry_price)
            if trade.is_long:
                be_trigger = op + self.breakeven_start * pt
                be_sl      = op + self.breakeven_offset * pt
                if (float(self.data.Close[-1]) >= be_trigger
                        and (trade.sl is None or float(trade.sl) < be_sl)):
                    trade.sl = be_sl
            else:
                be_trigger = op - self.breakeven_start * pt
                be_sl      = op - self.breakeven_offset * pt
                if (float(self.data.Close[-1]) <= be_trigger
                        and (trade.sl is None or float(trade.sl) > be_sl)):
                    trade.sl = be_sl

    def _manage_trailing(self) -> None:
        """
        Once price has moved trail_start points in our favour, trail the SL
        by trail_step points from the current close.
        Applied to all open trades (both legs).
        """
        pt  = self._get_point()
        bar = float(self.data.Close[-1])
        for trade in self.trades:
            op = float(trade.entry_price)
            if trade.is_long:
                if bar >= op + self.trail_start * pt:
                    new_sl = bar - self.trail_step * pt
                    if trade.sl is None or new_sl > float(trade.sl) + pt:
                        trade.sl = new_sl
            else:
                if bar <= op - self.trail_start * pt:
                    new_sl = bar + self.trail_step * pt
                    if trade.sl is None or new_sl < float(trade.sl) - pt:
                        trade.sl = new_sl

    # ──────────────────────────────────────────────────────────────────────
    # Sizing
    # ──────────────────────────────────────────────────────────────────────

    def _calc_size(self, sl_dist: float) -> float:
        """
        Risk-percent position sizing.

        size  = risk_amount / sl_dist
        P&L   = size × Δprice   (backtesting.py convention)

        backtesting.py requires size to be either:
          - a fraction strictly between 0 and 1, OR
          - a positive whole number >= 1

        We floor to int when size >= 1 (typical at harness cash=10_000),
        and keep as fraction when size < 1 (typical at cash=100).
        Risk_pct is soft-capped at 5% to mirror CalcLot() guard.
        """
        if sl_dist <= 0:
            return 0.0
        capped_risk = min(float(self.risk_pct), 5.0)
        risk_amount = float(self.equity) * capped_risk / 100.0
        size = risk_amount / sl_dist
        if size >= 1.0:
            size = float(int(size))   # floor — must be whole number
            if size < 1.0:
                return 0.0
        elif size <= 0.0:
            return 0.0
        return size

    # ──────────────────────────────────────────────────────────────────────
    # Filters
    # ──────────────────────────────────────────────────────────────────────

    def _pass_session(self) -> bool:
        """
        Mirrors PassSession() in the MQL5 source.
        Assumes index is UTC. Weekends always blocked.
        """
        dt  = self.data.index[-1]
        dow = dt.dayofweek          # 0=Mon … 4=Fri, 5=Sat, 6=Sun
        if dow >= 5:
            return False
        if self.avoid_friday and dow == 4 and dt.hour >= int(self.friday_cutoff):
            return False
        return int(self.session_start) <= dt.hour < int(self.session_end)

    # ──────────────────────────────────────────────────────────────────────
    # Utility
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def _get_point() -> float:
        """
        XAUUSD point size. MT5 SYMBOL_POINT = 0.01 for 5-digit brokers.
        Override this method if your data uses different precision.
        """
        return 0.01


# ─────────────────────────────────────────────────────────────────────────────
# MTF helper — call this before running if use_mtf=True
# ─────────────────────────────────────────────────────────────────────────────

def attach_h1_mtf(strategy_cls: type, m5_df: pd.DataFrame) -> None:
    """
    Resample M5 OHLCV data to H1 and attach the H1 close series to the
    strategy class so MTF indicators can be computed.

    Usage:
        attach_h1_mtf(ASQSafeScalping, df)
        ASQSafeScalping.use_mtf = True
        bt = Backtest(df, ASQSafeScalping, ...)
    """
    h1 = (m5_df['Close']
          .resample('1h')
          .last()
          .reindex(m5_df.index, method='ffill'))
    strategy_cls.h1_close = h1.to_numpy()


# ─────────────────────────────────────────────────────────────────────────────
# Quick smoke test (run file directly: python asq_scalping.py)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import sys
    import os

    print("ASQ SafeScalping adapter — smoke test")
    print("Loading sample data...")

    # Try to load from the standard harness data location
    csv_candidates = [
        os.path.expanduser('~/Downloads/quant_harness/XAUUSD_M5.csv'),
        os.path.expanduser('~/Downloads/XAUUSD_M5.csv'),
    ]
    df = None
    for p in csv_candidates:
        if os.path.exists(p):
            df = pd.read_csv(p, index_col=0, parse_dates=True)
            print(f"Loaded: {p}  ({len(df):,} rows)")
            break

    if df is None:
        print("No data file found at expected paths.")
        print("Expected columns: Open, High, Low, Close, Volume")
        print("Adapter loaded OK — import and use ASQSafeScalping in your harness.")
        sys.exit(0)

    # Standardise column names
    df.columns = [c.capitalize() for c in df.columns]
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()

    # Use 6 months of data for the smoke test
    df = df.iloc[-int(6 * 21 * 24 * 12):]   # ~6 months of M5

    from backtesting import Backtest

    # Pepperstone Razor cost model: $7 RT/lot commission
    # For sizing at ~0.167 oz per trade: commission ≈ $7 × 0.00167 ≈ $0.012
    # Expressed as fraction: 0.012 / 3000 ≈ 0.000004
    # Spread: $0.22/oz ÷ 3000 ≈ 0.000073
    # Combined ≈ 0.00008 per unit per side → pass as commission= per-unit total
    bt = Backtest(
        df,
        ASQSafeScalping,
        cash        = 100,
        commission  = 0.00008,  # approximate; use cost_model.py for precision
        exclusive_orders = False,   # allow two-leg entries
    )

    stats = bt.run()
    print("\n── Smoke test results (6-month window) ──")
    print(stats[['Return [%]', 'Sharpe Ratio', 'Max. Drawdown [%]',
                 '# Trades', 'Win Rate [%]', 'Profit Factor']])
    print("\nAdapter OK.")
