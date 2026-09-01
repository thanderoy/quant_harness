"""research.post.sweeps.asqs_engine — fast port of ASQSafeScalping v1.20.

Mirrors qhf.engines.strategies.asq_safe_scalping closely enough to sweep it.
backtesting.py is a per-bar Python loop and cannot cover a grid this size.

FIDELITY NOTES -- the places this is easy to get wrong
------------------------------------------------------
1. ATR here is a SPAN EMA of true range (`tr.ewm(span=period)`), NOT the Wilder
   ATR used by cnk_engine/zlch_engine. Using the Wilder variant changes every
   breakout buffer and trend-separation threshold.
2. RSI is Wilder-style via `ewm(com=period-1)`, and the harness divides by a
   loss series with zeros replaced by NaN -- so RSI is NaN, not 100, on a run
   with no down closes. NaN fails every comparison, which blocks entry. That
   is reproduced rather than "fixed".
3. Rolling high/low are `high.shift(1).rolling(lookback).max()` -- the window
   EXCLUDES the signal bar.
4. Entry is decided on the closed bar t and filled at open[t+1]; contingent
   SL/TP are live from the fill bar itself (established by the cnk parity work).
5. Breakeven then trailing run at each bar CLOSE, so a stop moved on bar b only
   binds from bar b+1. Order matters: breakeven first, then trailing.
6. Partial close creates TWO legs sharing one SL with different TPs, and the
   harness records each leg as a separate trade. Returns are recorded per leg
   so trade counts and per-trade metrics line up.
7. The drawdown halt is NOT absorbing -- it blocks new entries while the
   drawdown holds and releases if equity recovers. It also tracks PEAK EQUITY
   including unrealised P&L, so the peak can be set mid-trade.
8. The session filter reads hour-of-day, so bars MUST be loaded with
   tz="server_eet". The raw CSVs are broker server time; the harness's own
   docstring says "Assumes index is UTC" and that assumption is wrong.

Costs and the two return bases match cnk_engine exactly so the sweeps are
directly comparable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from research.post.sweeps.cnk_engine import (
    Bars, metrics, CONTRACT_SIZE, SPREAD_USD_PER_OZ, SPREAD_REF_PRICE,
    COMMISSION_PER_LOT_RT, _swap_usd)

POINT = 0.01                      # XAUUSD SYMBOL_POINT on a 5-digit broker
TREND_MULT = {0: 0.1, 1: 0.3, 2: 0.6}
_SCAN_BLOCK = 4096


# --------------------------------------------------------------------------- #
# Indicators                                                                    #
# --------------------------------------------------------------------------- #
def ema(x: np.ndarray, period: int) -> np.ndarray:
    return pd.Series(x).ewm(span=period, adjust=False).mean().to_numpy()


def rsi(close: np.ndarray, period: int) -> np.ndarray:
    s = pd.Series(close)
    delta = s.diff()
    gain = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).to_numpy()


def atr_span(high, low, close, period: int) -> np.ndarray:
    prev = pd.Series(close).shift(1)
    tr = pd.concat([pd.Series(high) - pd.Series(low),
                    (pd.Series(high) - prev).abs(),
                    (pd.Series(low) - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean().to_numpy()


def rolling_hl(high, low, lookback: int) -> tuple[np.ndarray, np.ndarray]:
    h = pd.Series(high).shift(1).rolling(lookback).max().to_numpy()
    l = pd.Series(low).shift(1).rolling(lookback).min().to_numpy()
    return h, l


def indicators(bars: Bars, ema_fast: int, ema_slow: int, rsi_period: int,
               atr_period: int, breakout_lookback: int) -> dict:
    return {
        "ef": ema(bars.close, ema_fast), "es": ema(bars.close, ema_slow),
        "rsi": rsi(bars.close, rsi_period),
        "atr": atr_span(bars.high, bars.low, bars.close, atr_period),
        **dict(zip(("hi", "lo"), rolling_hl(bars.high, bars.low, breakout_lookback))),
    }


# --------------------------------------------------------------------------- #
# Entry signals (conditions 1-6; MTF is off by default and not swept)          #
# --------------------------------------------------------------------------- #
def entry_signals(bars: Bars, ind: dict, trend_strength: int,
                  breakout_buffer: float, rsi_buy_min: float, rsi_buy_max: float,
                  rsi_sell_min: float, rsi_sell_max: float
                  ) -> tuple[np.ndarray, np.ndarray]:
    ef, es, r, a, hi_n, lo_n = (ind["ef"], ind["es"], ind["rsi"], ind["atr"],
                                ind["hi"], ind["lo"])
    c1 = bars.close
    c2 = np.roll(c1, 1); c2[0] = np.nan

    finite = (np.isfinite(ef) & np.isfinite(es) & np.isfinite(r)
              & np.isfinite(a) & np.isfinite(hi_n) & np.isfinite(lo_n)
              & np.isfinite(c2) & (a != 0))

    sep_ok = np.abs(ef - es) >= a * TREND_MULT.get(int(trend_strength), 0.3)
    buf = a * float(breakout_buffer)

    long_ok = (finite & sep_ok & (ef > es) & (c1 > ef) & (c1 > es)
               & (c1 > hi_n - buf) & (c2 <= hi_n)
               & (r >= rsi_buy_min) & (r <= rsi_buy_max) & (c1 > c2))
    short_ok = (finite & sep_ok & (ef < es) & (c1 < ef) & (c1 < es)
                & (c1 < lo_n + buf) & (c2 >= lo_n)
                & (r >= rsi_sell_min) & (r <= rsi_sell_max) & (c1 < c2))
    long_ok[:2] = short_ok[:2] = False
    return long_ok, short_ok


def session_mask(bars: Bars, use_session: bool, session_start: int,
                 session_end: int, avoid_friday: bool, friday_cutoff: int
                 ) -> np.ndarray:
    """Hour-of-day gate. Requires a true-UTC index (tz='server_eet').

    NOTE ASQSafeScalping.next() calls _pass_session() only when use_session is
    True, so switching the session off also disables the weekend AND the Friday
    cutoff that live inside that method. Reproduced: use_session=False means no
    time filtering of any kind, not "no hour filter but keep Friday".
    """
    if not use_session:
        return np.ones(bars.n, dtype=bool)
    dow = bars.index.dayofweek.to_numpy()
    hour = bars.index.hour.to_numpy()
    ok = dow < 5
    if avoid_friday:
        ok &= ~((dow == 4) & (hour >= int(friday_cutoff)))
    ok &= (hour >= int(session_start)) & (hour < int(session_end))
    return ok


def _calc_size(equity: float, sl_dist: float, risk_pct: float) -> float:
    """Reproduces ASQSafeScalping._calc_size including the 5% soft cap and the
    backtesting.py rule that a size >= 1 must be a whole number."""
    if sl_dist <= 0:
        return 0.0
    risk_amount = equity * min(float(risk_pct), 5.0) / 100.0
    size = risk_amount / sl_dist
    if size >= 1.0:
        size = float(int(size))
        return size if size >= 1.0 else 0.0
    return size if size > 0.0 else 0.0


def simulate(bars: Bars, ind: dict, long_sig: np.ndarray, short_sig: np.ndarray,
             sess_ok: np.ndarray, *, sl_points: int, tp_points: int,
             use_breakeven: bool, breakeven_start: int, breakeven_offset: int,
             use_trailing: bool, trail_start: int, trail_step: int,
             use_partial_close: bool, tp1_points: int, tp1_close_pct: float,
             partial_mode: str = "harness",
             risk_pct: float, max_day_trades: int, max_dd_pct: float,
             enable_long: bool = True, enable_short: bool = True,
             cash: float = 10_000.0) -> dict:
    n = bars.n
    op, hi, lo, cl = bars.open, bars.high, bars.low, bars.close
    idx = bars.index
    dates = idx.normalize().to_numpy()

    spread_frac = SPREAD_USD_PER_OZ / SPREAD_REF_PRICE
    comm_per_oz_side = (COMMISSION_PER_LOT_RT / 2.0) / CONTRACT_SIZE

    long_e = long_sig & sess_ok & bool(enable_long)
    short_e = short_sig & sess_ok & bool(enable_short)
    entry_bars = np.flatnonzero(long_e | short_e)
    empty = {"n_trades": 0, "returns": np.array([]), "px_returns": np.array([]),
             "pnls": np.array([]), "entry_ts": [], "exit_ts": [],
             "equity_final": cash}
    if entry_bars.size == 0:
        return empty

    sl_dist = sl_points * POINT
    tp_dist = tp_points * POINT
    tp1_dist = tp1_points * POINT
    be_trig, be_off = breakeven_start * POINT, breakeven_offset * POINT
    tr_trig, tr_step = trail_start * POINT, trail_step * POINT

    cash_bt = cash
    peak = cash
    rets, pnls, px_rets, entry_ts, exit_ts = [], [], [], [], []
    cur_date, day_count = None, 0
    t_ptr = 0

    while t_ptr < entry_bars.size:
        t = int(entry_bars[t_ptr])
        f = t + 1
        if f >= n:
            break

        d = dates[t]
        if cur_date is None or d != cur_date:
            cur_date, day_count = d, 0
        if max_day_trades > 0 and day_count >= max_day_trades:
            t_ptr += 1
            continue
        # Drawdown halt: blocks new entries, does not close anything, and
        # releases if equity recovers. Flat here, so equity == realised cash.
        if peak > 0 and (peak - cash_bt) / peak * 100.0 >= max_dd_pct:
            t_ptr += 1
            continue

        is_long = bool(long_e[t])
        size = _calc_size(cash_bt, sl_dist, risk_pct)
        if size <= 0:
            t_ptr += 1
            continue

        entry_px = op[f] * (1 + spread_frac) if is_long else op[f] * (1 - spread_frac)
        # ASQSafeScalping._enter_long/_enter_short anchor the initial SL/TP to
        # the SIGNAL BAR CLOSE (`self.data.Close[-1]`), not to the fill price.
        # Breakeven and trailing then anchor to `trade.entry_price`, which IS
        # the fill. Two different anchors in one strategy -- reproduced, not
        # tidied, because tidying it silently changes every exit level.
        anchor = cl[t]
        stop = anchor - sl_dist if is_long else anchor + sl_dist
        legs = []
        if use_partial_close:
            s1 = size * float(tp1_close_pct) / 100.0
            s2 = size - s1
            s1 = float(int(s1)) if s1 >= 1 else s1
            s2 = float(int(s2)) if s2 >= 1 else s2
            if s1 > 0 and s2 > 0:
                if partial_mode == "harness":
                    # btpy_runner sets exclusive_orders=True, so the SECOND
                    # order cancels the first. The TP1 leg never exists and the
                    # only surviving effect of "partial close" is that size is
                    # halved. Verified against harness trades: 349 trades, all
                    # unique entry times, all size s2, normal durations.
                    # This is what every recorded ASQS harness figure actually
                    # measured, seq=30 included.
                    legs = [[s2, anchor + tp_dist if is_long else anchor - tp_dist]]
                else:
                    # What the MQL5 EA actually does: two real legs sharing one
                    # stop, first taking profit at tp1.
                    legs = [[s1, anchor + tp1_dist if is_long else anchor - tp1_dist],
                            [s2, anchor + tp_dist if is_long else anchor - tp_dist]]
        if not legs:
            legs = [[size, anchor + tp_dist if is_long else anchor - tp_dist]]

        open_legs = [[sz, tp, True] for sz, tp in legs]
        last_exit = f
        for b in range(f, n):
            # 1. contingent orders on this bar's range, SL wins a same-bar tie
            for leg in open_legs:
                if not leg[2]:
                    continue
                sz, tp = leg[0], leg[1]
                hit_sl = lo[b] <= stop if is_long else hi[b] >= stop
                hit_tp = hi[b] >= tp if is_long else lo[b] <= tp
                if hit_sl or hit_tp:
                    if hit_sl:
                        px = min(op[b], stop) if is_long else max(op[b], stop)
                    else:
                        px = max(op[b], tp) if is_long else min(op[b], tp)
                    gross = (px - entry_px) * sz if is_long else (entry_px - px) * sz
                    comm = 2.0 * sz * comm_per_oz_side
                    swap = _swap_usd(sz / CONTRACT_SIZE, is_long, idx[f], idx[b])
                    cash_bt += gross - comm
                    pnls.append(gross - comm + swap)
                    rets.append((gross - comm + swap) / max(cash_bt, 1e-9))
                    px_rets.append(
                        ((px / entry_px - 1.0) if is_long else (entry_px / px - 1.0))
                        - comm / (sz * entry_px))
                    entry_ts.append(idx[f]); exit_ts.append(idx[b])
                    leg[2] = False
                    last_exit = b
            if not any(l[2] for l in open_legs):
                break
            # 2. mark-to-market peak, then stop management at this bar's close
            unreal = sum((cl[b] - entry_px) * l[0] if is_long
                         else (entry_px - cl[b]) * l[0] for l in open_legs if l[2])
            if cash_bt + unreal > peak:
                peak = cash_bt + unreal
            if use_breakeven:
                if is_long and cl[b] >= entry_px + be_trig:
                    stop = max(stop, entry_px + be_off)
                elif not is_long and cl[b] <= entry_px - be_trig:
                    stop = min(stop, entry_px - be_off)
            if use_trailing:
                if is_long and cl[b] >= entry_px + tr_trig:
                    ns = cl[b] - tr_step
                    if ns > stop + POINT:
                        stop = ns
                elif not is_long and cl[b] <= entry_px - tr_trig:
                    ns = cl[b] + tr_step
                    if ns < stop - POINT:
                        stop = ns
        else:
            # never exited -- close the remaining legs at the final bar
            for leg in open_legs:
                if not leg[2]:
                    continue
                sz, px = leg[0], cl[n - 1]
                gross = (px - entry_px) * sz if is_long else (entry_px - px) * sz
                comm = 2.0 * sz * comm_per_oz_side
                cash_bt += gross - comm
                pnls.append(gross - comm)
                rets.append((gross - comm) / max(cash_bt, 1e-9))
                px_rets.append(
                    ((px / entry_px - 1.0) if is_long else (entry_px / px - 1.0))
                    - comm / (sz * entry_px))
                entry_ts.append(idx[f]); exit_ts.append(idx[n - 1])
            last_exit = n - 1

        if cash_bt > peak:
            peak = cash_bt
        day_count += 1
        t_ptr = int(np.searchsorted(entry_bars, last_exit, side="left"))
        if t_ptr < entry_bars.size and int(entry_bars[t_ptr]) <= t:
            t_ptr = np.searchsorted(entry_bars, t, side="right")

    return {"n_trades": len(px_rets), "returns": np.asarray(rets, float),
            "px_returns": np.asarray(px_rets, float),
            "pnls": np.asarray(pnls, float), "entry_ts": entry_ts,
            "exit_ts": exit_ts, "equity_final": cash_bt,
            "index": idx}
