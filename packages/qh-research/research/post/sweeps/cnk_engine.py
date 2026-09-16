"""research.post.sweeps.cnk_engine — fast backtest for crest_n_keel (both modes).

Purpose
-------
Canonical implementations are ``research.engines.strategies.hma_stoch.HMAStoch1H``
(PULLBACK mode) and ``research.engines.strategies.cnk_momentum.CrestNKeelMomentum``
(MOMENTUM mode), both running under ``backtesting.py``. Those are per-bar Python
loops, far too slow for an exhaustive sweep. This module reimplements the SAME
semantics as an event-driven loop and is validated against the canonical engines
by ``run_cnk_parity.py``. Sweep accelerator, NOT a new strategy definition.
If the two disagree, the harness is right.

Two entry modes, one shared exit/sizing/cost core:

  PULLBACK  (seq=0)   HMA slope + price side + stochastic cross from the
                      oversold/overbought zone. Fixed SL/TP bracket.
                      Long and short.
  MOMENTUM  (seq=35)  HMA slope FLIP (non-rising -> rising). ATR chandelier
                      trailing stop, raise-only. Long-only upstream; this
                      engine can also mirror it short so the sweep can test
                      whether long-only was the right call.

Semantics replicated from the harness:
  - trade_on_close=False -> a signal on bar t fills at open[t+1]
  - exclusive_orders=True -> at most one position at a time
  - spread applied to the ENTRY fill only (backtesting.py 0.6.5)
  - commission $3.50 per side per lot (= $0.035/oz per order)
  - swap applied post-hoc per trade, so backtesting.py's own equity (and hence
    the ATR sizer and the DD halt) never sees it -> `cash_bt` mirrors that
    swap-free path while `equity` carries the true account value
  - protective SL/TP checked intrabar; SL wins a same-bar tie (conservative)
  - contingent SL/TP orders ARE checked on the fill bar itself (verified by
    run_cnk_parity: the bar-after variant costs 100% -> <100% entry match and
    moves Sharpe by up to 0.057)
  - MOMENTUM trail is updated at the close of each bar the position is open,
    using that bar's high and ATR, taking effect from the next bar; the stop
    is checked before that bar's trail update
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

CONTRACT_SIZE = 100.0          # oz per lot
MIN_LOT, MAX_LOT, LOT_STEP = 0.01, 0.10, 0.01
LOT_SAFETY_FLOOR_ATR = 0.10
SPREAD_USD_PER_OZ = 0.22
SPREAD_REF_PRICE = 2400.0
COMMISSION_PER_LOT_RT = 7.0
SWAP_LONG_PER_LOT_NIGHT = -10.0
SWAP_SHORT_PER_LOT_NIGHT = -2.0
TRIPLE_SWAP_WEEKDAY = 2        # Wednesday
_SCAN_BLOCK = 4096             # forward-scan block for the fixed-bracket exit


# --------------------------------------------------------------------------- #
# Indicators — exact ports of research.engines.indicators                           #
# --------------------------------------------------------------------------- #
def _wma(vals: np.ndarray, period: int) -> np.ndarray:
    """Linear WMA. NaN propagates through any window that touches one."""
    out = np.full(vals.shape, np.nan)
    if period <= 0 or len(vals) < period:
        return out
    w = np.arange(1, period + 1, dtype=float)
    w /= w.sum()
    sw = np.lib.stride_tricks.sliding_window_view(vals, period)
    out[period - 1:] = sw @ w
    return out


def hma(close: np.ndarray, period: int) -> np.ndarray:
    """Hull MA = WMA(2*WMA(n/2) - WMA(n), round(sqrt(n))).

    Mirrors research.engines.indicators.hma, including its integer half-period
    (``period // 2``) and ``round(math.sqrt(period))`` smoothing length.
    """
    half = period // 2
    sqrt_p = int(round(math.sqrt(period)))
    diff = 2.0 * _wma(close, half) - _wma(close, period)
    return _wma(diff, sqrt_p)


def stochastic(high: np.ndarray, low: np.ndarray, close: np.ndarray,
               k_period: int, d_period: int, smooth_k: int,
               fill: float = 50.0) -> tuple[np.ndarray, np.ndarray]:
    """Slow stochastic (%K, %D), NaN-filled with `fill`.

    The harness applies ``.fillna(50.0)`` to both series in init(), so the
    warmup reads as a flat 50/50. That matters: it means the strategy's NaN
    guard never trips on %K/%D, and no signal can fire during warmup because
    every comparison is a strict inequality against an equal value.
    """
    n = len(close)
    if n < k_period:
        f = np.full(n, fill)
        return f, f.copy()
    sw_l = np.lib.stride_tricks.sliding_window_view(low, k_period)
    sw_h = np.lib.stride_tricks.sliding_window_view(high, k_period)
    ll = np.full(n, np.nan)
    hh = np.full(n, np.nan)
    ll[k_period - 1:] = sw_l.min(axis=1)
    hh[k_period - 1:] = sw_h.max(axis=1)
    rng = hh - ll
    with np.errstate(invalid="ignore", divide="ignore"):
        raw_k = (close - ll) / rng * 100.0
    # pandas `.where(hl_range > 0, 50.0)` treats a NaN condition as False, so
    # the warmup (NaN range) becomes 50.0 rather than NaN. Forcing NaN here
    # instead would delay %K by k_period bars and shift every cross.
    raw_k = np.where(rng > 0, raw_k, fill)

    def _sma(v: np.ndarray, p: int) -> np.ndarray:
        o = np.full(v.shape, np.nan)
        if len(v) < p:
            return o
        o[p - 1:] = np.lib.stride_tricks.sliding_window_view(v, p).mean(axis=1)
        return o

    k = _sma(raw_k, smooth_k)
    d = _sma(k, d_period)
    return np.nan_to_num(k, nan=fill), np.nan_to_num(d, nan=fill)


def atr(high: np.ndarray, low: np.ndarray, close: np.ndarray,
        period: int) -> np.ndarray:
    """Wilder ATR, exact port of research.engines.indicators.atr.

    NOTE the seeding differs from research.post.sweeps.zlch_engine.wilder_atr:
    here the first value lands at index `period` (not period-1) and is seeded
    with mean(tr[1:period+1]) — tr[0] is excluded because prev_close is NaN
    there. Using the zlch variant would shift every ATR by one bar.
    """
    n = len(close)
    out = np.full(n, np.nan)
    if n < period + 1:
        return out
    prev_c = np.concatenate(([np.nan], close[:-1]))
    tr = np.nanmax(np.vstack([high - low,
                              np.abs(high - prev_c),
                              np.abs(low - prev_c)]), axis=0)
    out[period] = tr[1:period + 1].mean()
    prev = out[period]
    tr_l = tr.tolist()
    inv = 1.0 / period
    pm1 = period - 1
    for i in range(period + 1, n):
        prev = (prev * pm1 + tr_l[i]) * inv
        out[i] = prev
    return out


# --------------------------------------------------------------------------- #
# Sizing / costs                                                               #
# --------------------------------------------------------------------------- #
def _lot_size(equity: float, atr_value: float, risk_pct: float,
              sl_mult: float) -> tuple[float, float]:
    """Port of research.engines.sizer.calculate_lot_size."""
    effective_atr = max(atr_value, LOT_SAFETY_FLOOR_ATR)
    risk_amount = equity * risk_pct
    sl_distance = effective_atr * sl_mult
    raw = risk_amount / (sl_distance * CONTRACT_SIZE)
    stepped = math.floor(raw / LOT_STEP) * LOT_STEP
    return float(max(MIN_LOT, min(MAX_LOT, round(stepped, 2)))), float(effective_atr)


def _swap_usd(lots: float, is_long: bool, entry_dt, exit_dt) -> float:
    """Match PepperstoneXAUUSDCostModel.swap_usd (midnight-UTC walk)."""
    if exit_dt <= entry_dt:
        return 0.0
    cur = entry_dt.normalize()
    if cur <= entry_dt:
        cur = cur + pd.Timedelta(days=1)
    nights = triples = 0
    while cur < exit_dt:
        if cur.weekday() != 5:                       # Saturday: no rollover
            nights += 1
            if cur.weekday() == TRIPLE_SWAP_WEEKDAY:
                triples += 1
        cur = cur + pd.Timedelta(days=1)
    per_night = SWAP_LONG_PER_LOT_NIGHT if is_long else SWAP_SHORT_PER_LOT_NIGHT
    return float((nights - triples + 3 * triples) * per_night * lots)


# --------------------------------------------------------------------------- #
# Bars container                                                               #
# --------------------------------------------------------------------------- #
class Bars:
    """Pre-computed per-timeframe arrays shared across every config."""

    def __init__(self, df: pd.DataFrame):
        self.index = df.index
        self.open = df["open"].to_numpy(float)
        self.high = df["high"].to_numpy(float)
        self.low = df["low"].to_numpy(float)
        self.close = df["close"].to_numpy(float)
        self.n = len(df)


# --------------------------------------------------------------------------- #
# Entry signals                                                                #
# --------------------------------------------------------------------------- #
def pullback_signals(bars: Bars, hma_v: np.ndarray, k: np.ndarray, d: np.ndarray,
                     oversold: float, overbought: float
                     ) -> tuple[np.ndarray, np.ndarray]:
    """HMAStoch1H entry gates, evaluated on bar t (cur) vs t-1 (prev)."""
    cl = bars.close
    hma_prev = np.roll(hma_v, 1)
    k_prev, d_prev = np.roll(k, 1), np.roll(d, 1)
    hma_prev[0] = np.nan
    k_prev[0] = d_prev[0] = np.nan

    long_ok = ((hma_v > hma_prev) & (cl > hma_v)
               & (k_prev < d_prev) & (k > d) & (k_prev < oversold))
    short_ok = ((hma_v < hma_prev) & (cl < hma_v)
                & (k_prev > d_prev) & (k < d) & (k_prev > overbought))
    # len(self._hma) < 3 guard: the first two bars can never signal.
    long_ok[:2] = short_ok[:2] = False
    return np.nan_to_num(long_ok, nan=False), np.nan_to_num(short_ok, nan=False)


def momentum_signals(bars: Bars, hma_v: np.ndarray
                     ) -> tuple[np.ndarray, np.ndarray]:
    """HMA slope FLIP. Long: non-rising -> rising. Short: mirror."""
    p1 = np.roll(hma_v, 1)
    p2 = np.roll(hma_v, 2)
    p1[0] = np.nan
    p2[:2] = np.nan
    rising_now, rising_prev = hma_v > p1, p1 > p2
    falling_now, falling_prev = hma_v < p1, p1 < p2
    long_ok = rising_now & ~rising_prev
    short_ok = falling_now & ~falling_prev
    # len(self._hma) < 4 guard.
    long_ok[:3] = short_ok[:3] = False
    valid = np.isfinite(hma_v) & np.isfinite(p1) & np.isfinite(p2)
    return long_ok & valid, short_ok & valid


# --------------------------------------------------------------------------- #
# Simulation                                                                   #
# --------------------------------------------------------------------------- #
def simulate(bars: Bars, mode: str, hma_v: np.ndarray, atr_v: np.ndarray,
             long_sig: np.ndarray, short_sig: np.ndarray,
             *, enable_long: bool, enable_short: bool,
             sl_mult: float, tp_mult: float, trail_mult: float,
             risk_pct: float, min_atr: float,
             cash: float = 10_000.0, max_dd_halt: float = 1.0,
             sl_checked_from_fill_bar: bool = True) -> dict:
    """Event-driven simulation over trade events.

    `max_dd_halt` defaults to 1.0 (effectively off). The harness's 0.30 halt is
    an ABSORBING barrier — once tripped it truncates the record at a
    path-dependent point, which makes cross-config comparison meaningless.
    The sweep disables it on both sides and reports drawdown as a metric.
    """
    n = bars.n
    op, hi, lo, cl = bars.open, bars.high, bars.low, bars.close
    idx = bars.index
    is_mom = mode == "momentum"

    spread_frac = SPREAD_USD_PER_OZ / SPREAD_REF_PRICE
    comm_per_oz_side = (COMMISSION_PER_LOT_RT / 2.0) / CONTRACT_SIZE

    atr_ok = np.nan_to_num(atr_v, nan=-1.0) >= min_atr
    hma_ok = np.isfinite(hma_v) & np.isfinite(atr_v)
    long_e = long_sig & atr_ok & hma_ok & bool(enable_long)
    short_e = short_sig & atr_ok & hma_ok & bool(enable_short)
    entry_mask = long_e | short_e
    entry_bars = np.flatnonzero(entry_mask)
    empty = {"n_trades": 0, "returns": np.array([]), "px_returns": np.array([]),
             "pnls": np.array([]), "entry_ts": [], "exit_ts": [],
             "equity_final": cash}
    if entry_bars.size == 0:
        return empty

    cash_bt = cash
    equity = cash
    peak = cash
    rets, pnls, px_rets, entry_ts, exit_ts = [], [], [], [], []
    lo_l, hi_l, op_l, atr_l = lo.tolist(), hi.tolist(), op.tolist(), atr_v.tolist()
    t_ptr, n_entries = 0, entry_bars.size

    while t_ptr < n_entries:
        t = int(entry_bars[t_ptr])
        f = t + 1                                    # fill bar (next open)
        if f >= n:
            break
        if cash_bt > peak:
            peak = cash_bt
        if cash_bt < peak * (1.0 - max_dd_halt) or cash_bt <= 0:
            t_ptr += 1
            continue

        is_long = bool(long_e[t])
        atr_cur = atr_v[t]
        stop_mult = trail_mult if is_mom else sl_mult
        lots, eff_atr = _lot_size(cash_bt, float(atr_cur), risk_pct, stop_mult)
        size_oz = round(lots * CONTRACT_SIZE, 2)
        if size_oz <= 0:
            t_ptr += 1
            continue

        sl_dist = eff_atr * stop_mult
        sl = cl[t] - sl_dist if is_long else cl[t] + sl_dist
        tp = (cl[t] + eff_atr * tp_mult) if is_long else (cl[t] - eff_atr * tp_mult)

        start = f if sl_checked_from_fill_bar else f + 1
        exit_bar, raw_exit = n - 1, cl[n - 1]

        if is_mom:
            # Sequential: the trail is raised at each bar's close using that
            # bar's high and ATR, and only takes effect from the next bar.
            if not sl_checked_from_fill_bar:
                a_f = atr_l[f]
                if a_f == a_f:
                    cand = (hi_l[f] - a_f * trail_mult) if is_long else (lo_l[f] + a_f * trail_mult)
                    if is_long:
                        sl = max(sl, cand)
                    else:
                        sl = min(sl, cand)
            u = start
            while u < n:
                if is_long:
                    if lo_l[u] <= sl:
                        exit_bar, raw_exit = u, min(op_l[u], sl)
                        break
                else:
                    if hi_l[u] >= sl:
                        exit_bar, raw_exit = u, max(op_l[u], sl)
                        break
                a_u = atr_l[u]
                if a_u == a_u:
                    cand = (hi_l[u] - a_u * trail_mult) if is_long else (lo_l[u] + a_u * trail_mult)
                    if is_long:
                        if cand > sl:
                            sl = cand
                    else:
                        if cand < sl:
                            sl = cand
                u += 1
        else:
            # Fixed bracket: first bar touching SL or TP. SL wins a same-bar
            # tie, matching backtesting.py's conservative ordering.
            # Scanned in BLOCKS so the cost is proportional to the trade's
            # duration rather than to the length of the remaining series.
            # Scanning the whole tail per trade is O(n) each and made M5
            # ~40x slower, which alone would have made the sweep infeasible.
            b = start
            while b < n:
                e = min(b + _SCAN_BLOCK, n)
                if is_long:
                    m_sl = lo[b:e] <= sl
                    m_tp = hi[b:e] >= tp
                else:
                    m_sl = hi[b:e] >= sl
                    m_tp = lo[b:e] <= tp
                any_sl, any_tp = m_sl.any(), m_tp.any()
                if any_sl or any_tp:
                    i_sl = int(m_sl.argmax()) if any_sl else (e - b)
                    i_tp = int(m_tp.argmax()) if any_tp else (e - b)
                    if i_sl <= i_tp:
                        u = b + i_sl
                        raw_exit = min(op[u], sl) if is_long else max(op[u], sl)
                    else:
                        u = b + i_tp
                        raw_exit = max(op[u], tp) if is_long else min(op[u], tp)
                    exit_bar = u
                    break
                b = e

        # -- fills with spread (ENTRY fill only) -----------------------------
        entry_px = op[f] * (1 + spread_frac) if is_long else op[f] * (1 - spread_frac)
        exit_px = raw_exit
        gross = ((exit_px - entry_px) if is_long else (entry_px - exit_px)) * size_oz
        commission = 2.0 * size_oz * comm_per_oz_side
        swap = _swap_usd(lots, is_long, idx[f], idx[exit_bar])
        pnl = gross - commission + swap

        pnl_bt = gross - commission
        px_ret = ((exit_px / entry_px - 1.0) * (1.0 if is_long else -1.0)
                  - commission / (size_oz * entry_px))
        px_rets.append(px_ret * (pnl / pnl_bt) if pnl_bt != 0 else px_ret)

        rets.append(pnl / equity if equity > 0 else 0.0)
        pnls.append(pnl)
        entry_ts.append(idx[f])
        exit_ts.append(idx[exit_bar])
        cash_bt += pnl_bt
        equity += pnl

        # On the bar the position closes the harness already sees itself flat
        # and may take a fresh signal that same bar -> `left`, not `right`.
        t_ptr = int(np.searchsorted(entry_bars, exit_bar, side="left"))

    return {
        "n_trades": len(rets),
        "returns": np.asarray(rets, dtype=float),
        "px_returns": np.asarray(px_rets, dtype=float),
        "pnls": np.asarray(pnls, dtype=float),
        "entry_ts": entry_ts,
        "exit_ts": exit_ts,
        "equity_final": equity,
    }


# --------------------------------------------------------------------------- #
# Metrics                                                                      #
# --------------------------------------------------------------------------- #
def metrics(sim: dict, basis: str = "account") -> dict:
    """basis="account" -> PnL/equity_at_entry (economically correct).
    basis="price" -> per-unit price return, reproducing what
    research.engines.btpy_runner feeds its metrics (position-size agnostic).
    Both are reported; they are NOT interchangeable.
    """
    r = sim["px_returns"] if basis == "price" else sim["returns"]
    r = r[~np.isnan(r)]
    out = {"n_trades": int(sim["n_trades"]), "sharpe": float("nan"),
           "max_dd": float("nan"), "profit_factor": float("nan"),
           "win_rate": float("nan"), "cagr": float("nan"),
           "expectancy": float("nan"), "total_return": float("nan"),
           "trades_per_year": float("nan")}
    if r.size < 2:
        return out
    span_days = (sim["exit_ts"][-1] - sim["entry_ts"][0]).days
    ppy = max(r.size / (span_days / 365.25), 1.0) if span_days > 0 else 252.0
    sd = r.std(ddof=1)
    out["trades_per_year"] = float(ppy)
    out["sharpe"] = float(r.mean() / sd * np.sqrt(ppy)) if sd > 0 else float("nan")
    eq = np.cumprod(1.0 + r)
    dd = eq / np.maximum.accumulate(eq) - 1.0
    out["max_dd"] = float(-dd.min())
    gains = r[r > 0].sum()
    losses = -r[r < 0].sum()
    out["profit_factor"] = float(gains / losses) if losses > 0 else float("inf")
    out["win_rate"] = float((r > 0).sum() / r.size)
    out["expectancy"] = float(r.mean())
    out["total_return"] = float(eq[-1] - 1.0)
    years = span_days / 365.25 if span_days > 0 else 1.0
    out["cagr"] = float(eq[-1] ** (1.0 / years) - 1.0) if eq[-1] > 0 and years > 0 else float("nan")
    return out
