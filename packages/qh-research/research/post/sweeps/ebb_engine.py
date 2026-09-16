"""research.post.sweeps.ebb_engine — fast vectorised backtest for ebb_n_flow.

Canonical implementation is research.engines.strategies.ebb_n_flow.EbbNFlow run under
research.engines.btpy_runner. That is a per-bar Python loop; this module reimplements
the same semantics as an event loop over entry candidates so an exhaustive grid
is tractable. Validated by run_ebb_parity.py -- if the two disagree, the harness
is right.

Strategy recap: fade a Bollinger band excursion back to the midline, but only in
a balanced regime (Kaufman Efficiency Ratio below a ceiling). TP = the midline
(which MOVES bar to bar), SL = sl_atr_mult * max(ATR, floor) beyond entry, plus
a hard time stop.

Harness semantics replicated exactly:
  - trade_on_close=False -> signal on bar s fills at open[s+1]
  - time stop fires at the first bar u with u - entry_bar >= time_stop_bars,
    and that close order fills at open[u+1]
  - spread applied to the ENTRY fill only; commission $3.50/side/lot
  - swap applied post-hoc, so the sizer never sees it
  - sizing: lots = equity*risk_pct/(sl_dist*100), CLIPPED to [0.01, 0.10],
    then size_oz = max(1, int(round(lots*100)))  -- note round, not floor
  - EbbNFlow.atr_wilder is ewm(alpha=1/n, adjust=False, min_periods=n), which
    is NOT the SMA-seeded Wilder ATR used by zlch. Do not share that helper.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from research.post.sweeps.zlch_engine import (
    CONTRACT_SIZE, COMMISSION_PER_LOT_RT, SPREAD_REF_PRICE, SPREAD_USD_PER_OZ,
    _swap_usd,
)

MIN_LOT, MAX_LOT = 0.01, 0.10


# --------------------------------------------------------------------------- #
# Indicators — ported verbatim from research.engines.strategies.ebb_n_flow          #
# --------------------------------------------------------------------------- #
def bollinger(close: np.ndarray, n: int, k: float):
    s = pd.Series(close)
    mid = s.rolling(n).mean()
    sd = s.rolling(n).std(ddof=0)
    return mid.to_numpy(), (mid + k * sd).to_numpy(), (mid - k * sd).to_numpy()


def kaufman_er(close: np.ndarray, n: int) -> np.ndarray:
    s = pd.Series(close)
    direction = s.diff(n).abs()
    volatility = s.diff().abs().rolling(n).sum()
    return (direction / volatility.replace(0.0, np.nan)).to_numpy()


def atr_wilder_ewm(high, low, close, n: int) -> np.ndarray:
    h, l, c = pd.Series(high), pd.Series(low), pd.Series(close)
    prev_c = c.shift(1)
    tr = pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean().to_numpy()


def true_range(high, low, close) -> np.ndarray:
    h, l, c = pd.Series(high), pd.Series(low), pd.Series(close)
    prev_c = c.shift(1)
    return pd.concat([(h - l), (h - prev_c).abs(), (l - prev_c).abs()],
                     axis=1).max(axis=1).to_numpy()


def session_mask(index: pd.DatetimeIndex, start: int, end: int,
                 friday_cutoff: int) -> np.ndarray:
    wd = index.weekday.to_numpy()
    hr = index.hour.to_numpy()
    ok = (wd <= 4) & (hr >= start) & (hr < end)
    return ok & ~((wd == 4) & (hr >= friday_cutoff))


class EbbBars:
    """Per-timeframe arrays shared across every config."""

    def __init__(self, df: pd.DataFrame):
        self.index = df.index
        self.open = df["open"].to_numpy(float)
        self.high = df["high"].to_numpy(float)
        self.low = df["low"].to_numpy(float)
        self.close = df["close"].to_numpy(float)
        self.n = len(df)
        self.tr = true_range(self.high, self.low, self.close)
        self.session = session_mask(df.index, 8, 17, 14)
        self.all_hours = np.ones(self.n, dtype=bool)


def _size_oz(equity: float, sl_dist: float, risk_pct: float) -> int:
    lots = equity * risk_pct / (sl_dist * CONTRACT_SIZE)
    lots = float(np.clip(lots, MIN_LOT, MAX_LOT))
    return max(1, int(round(lots * CONTRACT_SIZE)))


def simulate(bars: EbbBars, mid, upper, lower, er, atr, *,
             er_max: float, sl_atr_mult: float, atr_floor: float,
             time_stop_bars: int, atr_spike_mult: float, min_r: float,
             enable_long: bool, enable_short: bool, use_session: bool,
             risk_pct: float = 0.01, cash: float = 10_000.0,
             entry_override: tuple[np.ndarray, np.ndarray] | None = None,
             return_gate: bool = False):
    n = bars.n
    op, hi, lo, cl, tr = bars.open, bars.high, bars.low, bars.close, bars.tr
    idx = bars.index
    sess = bars.session if use_session else bars.all_hours

    spread_frac = SPREAD_USD_PER_OZ / SPREAD_REF_PRICE
    comm_per_oz_side = (COMMISSION_PER_LOT_RT / 2.0) / CONTRACT_SIZE

    finite = np.isfinite(atr) & np.isfinite(er) & np.isfinite(mid)
    gate = finite & sess & (er < er_max) & (tr <= atr_spike_mult * atr)
    if return_gate:
        # Eligible pool for the drift control: every bar passing the regime
        # gate, with the band-touch condition removed. Randomising within this
        # pool isolates the Bollinger signal while holding the KER filter,
        # session and spike rejection fixed.
        return gate
    if entry_override is None:
        short_sig = gate & (cl > upper) & enable_short
        long_sig = gate & (cl < lower) & enable_long
    else:
        long_sig, short_sig = entry_override
    cand = np.flatnonzero(short_sig | long_sig)
    if cand.size == 0:
        return {"n_trades": 0, "returns": np.array([]), "px_returns": np.array([]),
                "pnls": np.array([]), "entry_ts": [], "exit_ts": [],
                "dirs": np.array([]), "equity_final": cash}

    cash_bt = equity = cash
    rets, px_rets, pnls, entry_ts, exit_ts, dirs = [], [], [], [], [], []
    ptr = 0
    ncand = cand.size

    while ptr < ncand:
        s = int(cand[ptr])
        f = s + 1
        if f >= n - 1:
            break
        is_long = bool(long_sig[s])
        a = atr[s]
        sl_dist = sl_atr_mult * max(a, atr_floor)
        close_s = cl[s]
        tp = mid[s]
        # R-floor: reward leg (to the midline) vs risk leg (the ATR stop).
        tp_dist = (tp - close_s) if is_long else (close_s - tp)
        if not (tp_dist > 0 and sl_dist > 0 and (tp_dist / sl_dist) >= min_r):
            ptr += 1
            continue
        sl = close_s - sl_dist if is_long else close_s + sl_dist
        size = _size_oz(cash_bt, sl_dist, risk_pct)

        # -- scan forward for SL / TP / time stop -----------------------------
        # Time stop fires at u = f + time_stop_bars and fills at open[u+1].
        last_scan = min(f + time_stop_bars, n - 2)
        exit_bar = None
        raw_exit = None
        for u in range(f, last_scan + 1):
            if is_long:
                if lo[u] <= sl:
                    exit_bar, raw_exit = u, min(op[u], sl)
                    break
                if hi[u] >= tp:
                    exit_bar, raw_exit = u, max(op[u], tp)
                    break
            else:
                if hi[u] >= sl:
                    exit_bar, raw_exit = u, max(op[u], sl)
                    break
                if lo[u] <= tp:
                    exit_bar, raw_exit = u, min(op[u], tp)
                    break
        if exit_bar is None:
            exit_bar = min(last_scan + 1, n - 1)
            raw_exit = op[exit_bar]

        entry_px = op[f] * (1 + spread_frac) if is_long else op[f] * (1 - spread_frac)
        exit_px = raw_exit
        gross = ((exit_px - entry_px) if is_long else (entry_px - exit_px)) * size
        commission = 2.0 * size * comm_per_oz_side
        lots = size / CONTRACT_SIZE
        swap = _swap_usd(lots, is_long, idx[f], idx[exit_bar])
        pnl_bt = gross - commission
        pnl = pnl_bt + swap

        px = ((exit_px / entry_px - 1.0) * (1.0 if is_long else -1.0)
              - commission / (size * entry_px))
        px_rets.append(px * (pnl / pnl_bt) if pnl_bt != 0 else px)
        rets.append(pnl / equity if equity > 0 else 0.0)
        pnls.append(pnl)
        entry_ts.append(idx[f])
        exit_ts.append(idx[exit_bar])
        dirs.append(1 if is_long else -1)
        cash_bt += pnl_bt
        equity += pnl

        ptr = int(np.searchsorted(cand, exit_bar, side="left"))

    return {"n_trades": len(rets),
            "returns": np.asarray(rets, float),
            "px_returns": np.asarray(px_rets, float),
            "pnls": np.asarray(pnls, float),
            "entry_ts": entry_ts, "exit_ts": exit_ts,
            "dirs": np.asarray(dirs, int),
            "equity_final": equity}


def build_indicators(bars: EbbBars, bb_n: int, bb_k: float, er_n: int, atr_n: int):
    mid, up, lo = bollinger(bars.close, bb_n, bb_k)
    er = kaufman_er(bars.close, er_n)
    atr = atr_wilder_ewm(bars.high, bars.low, bars.close, atr_n)
    return mid, up, lo, er, atr
