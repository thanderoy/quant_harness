"""research.engines.strategies.zlch — ZeroLag Chandelier (research/pre hypothesis).

M15 Chandelier direction-flip entry, gated by an H4 ZLSMA slope bias, with a
pure chandelier-flip exit (flat when the chandelier direction turns against the
open position). This is the harness translation of

    research/pre/signals/zerolag_chandelier.py   (wine-mt5-python-setup)

and of the TradingView "ZeroLag Chandelier LAB" strategy used for in-sample
parameter search.

Context (why this exists)
-------------------------
The zerolag_chandelier signal was registered as a HARD_GATE hypothesis and
KILLED at the signal-edge stage: combined E-Ratio ~0.98 (p=0.77), sitting inside
the random band. But the E-Ratio *breakdown* was long=1.03 / short=0.93 — the
short side is anti-edge on a secular-bull instrument (gold), exactly the
crest_n_keel signature. This module lets the honest walk-forward + DSR gate
arbitrate three configs over 21.6 years:
  - both-directions (the faithful signal),
  - long-only       (E-Ratio-preferred, bull-friendly),
  - short-only       (regime-fit control; expected to fail long-run).

Direction logic is a faithful port of _chandelier_direction in the research
signal: rolling max/min of CLOSE over `chand_atr_period`, Wilder ATR, ratcheting
long/short stops, seed dir=+1. All references are backward-looking (close[t] vs
stop[t-1], stop uses close[t-1]) so there is no look-ahead. The H4 ZLSMA bias is
resampled from the M15 bars (label='right', closed='right'), taken at .shift(1)
(prior closed H4 bar only), then reindexed to M15 with forward-fill.

NOT a live strategy. A candidate under validation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from backtesting import Strategy

from research.engines.indicators import atr
from research.engines.sizer import calculate_lot_size


# --------------------------------------------------------------------------- #
# Indicator helpers (ported from research/pre/signals/zerolag_chandelier.py)   #
# --------------------------------------------------------------------------- #
def _linreg_endpoint(series: pd.Series, length: int) -> pd.Series:
    """Endpoint of the OLS line over trailing `length` bars — Pine ta.linreg(src, length, 0)."""
    n = length
    if n < 2:
        raise ValueError("length must be >= 2")
    x = np.arange(n, dtype=float)
    x_mean = (n - 1) / 2.0
    sxx = float(((x - x_mean) ** 2).sum())

    vals = series.to_numpy(dtype=float)
    out = np.full(vals.shape, np.nan)
    if len(vals) < n:
        return pd.Series(out, index=series.index)

    sw = np.lib.stride_tricks.sliding_window_view(vals, n)
    y_mean = sw.mean(axis=1)
    sxy = (sw * (x - x_mean)).sum(axis=1)
    slope = sxy / sxx
    endpoint = y_mean + slope * (n - 1 - x_mean)
    out[n - 1:] = endpoint
    return pd.Series(out, index=series.index)


def _zlsma(close: pd.Series, length: int) -> pd.Series:
    lsma = _linreg_endpoint(close, length)
    lsma2 = _linreg_endpoint(lsma, length)
    return lsma + (lsma - lsma2)


def _chandelier_direction(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    atr_period: int,
    atr_mult: float,
) -> np.ndarray:
    """Ratcheting Chandelier direction (+1/-1), seed +1. Faithful to the research signal."""
    atr_vals = atr(high, low, close, atr_period).to_numpy()
    close_arr = close.to_numpy(dtype=float)
    n = len(close_arr)

    roll_max = close.rolling(atr_period, min_periods=atr_period).max().to_numpy()
    roll_min = close.rolling(atr_period, min_periods=atr_period).min().to_numpy()

    long_stop = np.full(n, np.nan)
    short_stop = np.full(n, np.nan)
    direction = np.ones(n, dtype=np.int64)

    for t in range(n):
        atr_t = atr_vals[t]
        if not np.isfinite(atr_t):
            continue
        band = atr_mult * atr_t
        ls_raw = roll_max[t] - band
        ss_raw = roll_min[t] + band

        if t == 0 or not np.isfinite(long_stop[t - 1]):
            long_stop[t] = ls_raw
            short_stop[t] = ss_raw
        else:
            long_stop[t] = (max(ls_raw, long_stop[t - 1])
                            if close_arr[t - 1] > long_stop[t - 1] else ls_raw)
            short_stop[t] = (min(ss_raw, short_stop[t - 1])
                             if close_arr[t - 1] < short_stop[t - 1] else ss_raw)

        if t == 0 or not np.isfinite(short_stop[t - 1]) or not np.isfinite(long_stop[t - 1]):
            direction[t] = 1 if t == 0 else direction[t - 1]
            continue

        if close_arr[t] > short_stop[t - 1]:
            direction[t] = 1
        elif close_arr[t] < long_stop[t - 1]:
            direction[t] = -1
        else:
            direction[t] = direction[t - 1]

    return direction


def _h4_bias(close: pd.Series, index: pd.DatetimeIndex, zlsma_len: int) -> tuple[np.ndarray, np.ndarray]:
    """Return (h4_rising, h4_falling) boolean arrays aligned to the M15 index.

    Resamples M15 close -> H4 (right-labelled/closed), computes ZLSMA slope on the
    PRIOR closed H4 bar (.shift(1)), then reindexes to M15 with forward-fill.
    """
    s = pd.Series(close.to_numpy(dtype=float), index=index)
    h4 = s.resample("4h", label="right", closed="right").last().dropna()
    z = _zlsma(h4, zlsma_len)
    z_lag = z.shift(1)
    rising = (z_lag > z_lag.shift(1))
    falling = (z_lag < z_lag.shift(1))
    rising_m15 = rising.reindex(index, method="ffill").fillna(False).to_numpy()
    falling_m15 = falling.reindex(index, method="ffill").fillna(False).to_numpy()
    return rising_m15, falling_m15


# --------------------------------------------------------------------------- #
# Strategy                                                                     #
# --------------------------------------------------------------------------- #
class ZeroLagChandelier(Strategy):
    """M15 Chandelier flip entry, H4 ZLSMA bias, chandelier-flip exit. XAUUSD."""

    # -- Signal parameters (match the research signal / TV canonical defaults) --
    chand_atr_period: int = 14
    chand_atr_mult: float = 2.5
    zlsma_len: int = 50

    # -- Component toggles (the experiment levers) --------------------------
    enable_long: bool = True
    enable_short: bool = True
    use_h4_bias: bool = True

    # -- Risk / sizing ------------------------------------------------------
    risk_pct: float = 0.01            # 1% of equity per trade (M15 frequency)
    min_atr_for_signal: float = 1.0
    max_drawdown_halt: float = 0.30
    _peak_equity: float = 0.0

    def init(self):
        index = self.data.index
        close = pd.Series(self.data.Close, index=index)
        high = pd.Series(self.data.High, index=index)
        low = pd.Series(self.data.Low, index=index)

        direction = _chandelier_direction(
            high, low, close, self.chand_atr_period, self.chand_atr_mult,
        ).astype(float)
        atr_vals = atr(high, low, close, self.chand_atr_period).ffill().values

        if self.use_h4_bias:
            rising, falling = _h4_bias(close, index, self.zlsma_len)
        else:
            rising = np.ones(len(index), dtype=bool)
            falling = np.ones(len(index), dtype=bool)

        self._dir = self.I(lambda: direction, name="ChandDir")
        self._atr = self.I(lambda: atr_vals, name="ATR")
        self._rising = self.I(lambda: rising.astype(float), name="H4Rise")
        self._falling = self.I(lambda: falling.astype(float), name="H4Fall")
        self._peak_equity = float(self.equity)

    def next(self):
        if len(self._dir) < 2:
            return

        dir_cur = float(self._dir[-1])
        dir_prev = float(self._dir[-2])
        atr_cur = float(self._atr[-1])
        close = float(self.data.Close[-1])

        if any(np.isnan(v) for v in [dir_cur, dir_prev, atr_cur]):
            return

        # Drawdown halt (mirrors HMAStoch1H).
        if self.equity > self._peak_equity:
            self._peak_equity = float(self.equity)
        if self.equity < self._peak_equity * (1.0 - self.max_drawdown_halt):
            return

        # --- Manage open position: flat when the chandelier turns against it ---
        if self.position:
            if self.position.is_long and dir_cur == -1:
                self.position.close()
            elif self.position.is_short and dir_cur == 1:
                self.position.close()
            return

        if atr_cur < self.min_atr_for_signal:
            return

        long_flip = dir_cur == 1 and dir_prev == -1
        short_flip = dir_cur == -1 and dir_prev == 1

        bias_long = (not self.use_h4_bias) or bool(self._rising[-1])
        bias_short = (not self.use_h4_bias) or bool(self._falling[-1])

        lots, effective_atr = calculate_lot_size(
            account_balance=float(self.equity),
            atr_value=atr_cur,
            risk_pct=self.risk_pct,
            sl_atr_multiplier=self.chand_atr_mult,
        )
        size_oz = round(lots * 100, 2)
        stop_dist = effective_atr * self.chand_atr_mult
        if size_oz <= 0:
            return

        # Protective SL at the chandelier stop distance; primary exit is the flip.
        if self.enable_long and long_flip and bias_long:
            self.buy(size=size_oz, sl=close - stop_dist)
        elif self.enable_short and short_flip and bias_short:
            self.sell(size=size_oz, sl=close + stop_dist)
