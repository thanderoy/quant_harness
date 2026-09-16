"""research.engines.strategies.cnk_momentum — Config A from the TradingView LAB.

crest_n_keel MOMENTUM variant. Two changes vs the live HMAStoch1H:
  1. Entry: HMA-slope-flip momentum (trend-following), LONG-ONLY — replaces the
     stochastic-pullback trigger that was structurally short-biased and faded
     the gold bull.
  2. Exit: ATR chandelier trailing stop (let winners run) — replaces fixed
     1.5x/3.0x SL/TP.

This is the config that BEAT buy-and-hold on the TradingView Strategy Tester
(in-sample: +68.4% vs +56.2% B&H, 10.6% max DD). Brought here for the honest
walk-forward OOS + DSR verdict — TradingView numbers are in-sample and mean
nothing until they survive this gate.

NOT a live strategy. A candidate under validation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from backtesting import Strategy

from research.engines.indicators import hma, atr
from research.engines.sizer import calculate_lot_size


class CrestNKeelMomentum(Strategy):
    """HMA-momentum long-only with ATR chandelier trailing exit. XAUUSD H1."""

    hma_period: int = 55
    atr_period: int = 14
    trail_atr_mult: float = 3.0
    risk_pct: float = 0.02
    min_atr_for_signal: float = 1.0
    max_drawdown_halt: float = 0.30
    _peak_equity: float = 0.0

    def init(self):
        close = pd.Series(self.data.Close)
        high = pd.Series(self.data.High)
        low = pd.Series(self.data.Low)

        hma_vals = hma(close, self.hma_period).ffill().values
        atr_vals = atr(high, low, close, self.atr_period).ffill().values

        self._hma = self.I(lambda: hma_vals, name='HMA')
        self._atr = self.I(lambda: atr_vals, name='ATR')
        self._peak_equity = float(self.equity)

    def next(self):
        if len(self._hma) < 4:
            return

        hma_cur   = float(self._hma[-1])
        hma_prev  = float(self._hma[-2])
        hma_prev2 = float(self._hma[-3])
        atr_cur   = float(self._atr[-1])
        high_cur  = float(self.data.High[-1])
        close     = float(self.data.Close[-1])

        if any(np.isnan(v) for v in [hma_cur, hma_prev, hma_prev2, atr_cur]):
            return

        # Drawdown halt (mirrors HMAStoch1H).
        if self.equity > self._peak_equity:
            self._peak_equity = float(self.equity)
        if self.equity < self._peak_equity * (1.0 - self.max_drawdown_halt):
            return

        # Manage open long: raise the chandelier trailing stop only.
        if self.position:
            chandelier = high_cur - atr_cur * self.trail_atr_mult
            for trade in self.trades:
                if trade.is_long and (trade.sl is None or chandelier > trade.sl):
                    trade.sl = chandelier
            return

        if atr_cur < self.min_atr_for_signal:
            return

        # Momentum long entry: HMA slope flips from non-rising to rising.
        rising_now = hma_cur > hma_prev
        rising_prev = hma_prev > hma_prev2
        if rising_now and not rising_prev:
            lots, effective_atr = calculate_lot_size(
                account_balance=float(self.equity),
                atr_value=atr_cur,
                risk_pct=self.risk_pct,
                sl_atr_multiplier=self.trail_atr_mult,
            )
            size_oz = round(lots * 100, 2)
            init_stop = close - effective_atr * self.trail_atr_mult
            if size_oz > 0:
                self.buy(size=size_oz, sl=init_stop)
