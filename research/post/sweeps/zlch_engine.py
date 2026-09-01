"""research.post.sweeps.zlch_engine — fast vectorised backtest for zerolag_chandelier.

Purpose
-------
The canonical implementation is ``qhf.engines.strategies.zlch.ZeroLagChandelier``
running under ``backtesting.py``. That engine is a per-bar Python loop and takes
tens of seconds per config on M15 — far too slow for an exhaustive parameter
sweep (~10^4 configs x 5 timeframes).

This module reimplements the SAME strategy semantics as an event-driven loop
over trade events rather than bars, and is validated against the canonical
engine by ``run_parity.py``. It is a sweep accelerator, NOT a new strategy
definition. If the two ever disagree, the harness is right.

Semantics replicated from the harness (btpy_runner.run_backtest):
  - trade_on_close=False -> signals on bar t fill at open[t+1]
  - exclusive_orders=True -> at most one position at a time
  - spread applied at BOTH fills as a fraction of price (backtesting.py
    convention): buy fills at p*(1+s), sell fills at p*(1-s),
    s = spread_usd_per_oz / 2400
  - commission $3.50 per side per lot (= $0.035/oz per order)
  - swap applied post-hoc per trade via the cost model
  - ReturnPct = PnL / equity_at_entry
  - protective SL at chandelier stop distance, checked intrabar
  - primary exit is the chandelier direction flip against the position
  - drawdown halt at max_drawdown_halt below peak equity blocks NEW entries
"""
from __future__ import annotations

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


# --------------------------------------------------------------------------- #
# Indicators                                                                   #
# --------------------------------------------------------------------------- #
def wilder_atr(high: pd.Series, low: pd.Series, close: pd.Series,
               period: int) -> np.ndarray:
    """Wilder ATR (RMA). Matches qhf.engines.indicators.atr."""
    h, l, c = high.to_numpy(float), low.to_numpy(float), close.to_numpy(float)
    prev_c = np.concatenate(([np.nan], c[:-1]))
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    tr[0] = h[0] - l[0]
    out = np.full(len(tr), np.nan)
    if len(tr) < period:
        return out
    seed = tr[:period].mean()
    out[period - 1] = seed
    alpha = 1.0 / period
    prev = seed
    tr_l = tr.tolist()
    for i in range(period, len(tr)):
        prev = prev + alpha * (tr_l[i] - prev)
        out[i] = prev
    return out


def _linreg_endpoint(vals: np.ndarray, length: int) -> np.ndarray:
    n = length
    x = np.arange(n, dtype=float)
    x_mean = (n - 1) / 2.0
    sxx = float(((x - x_mean) ** 2).sum())
    out = np.full(vals.shape, np.nan)
    if len(vals) < n:
        return out
    sw = np.lib.stride_tricks.sliding_window_view(vals, n)
    y_mean = sw.mean(axis=1)
    sxy = (sw * (x - x_mean)).sum(axis=1)
    slope = sxy / sxx
    out[n - 1:] = y_mean + slope * (n - 1 - x_mean)
    return out


def zlsma(vals: np.ndarray, length: int) -> np.ndarray:
    """ZLSMA = 2*LSMA - LSMA(LSMA).

    NaN must PROPAGATE through the second regression exactly as it does in the
    harness (which runs sliding_window_view over a NaN-prefixed pandas Series,
    so any window touching a NaN yields NaN). Zero-filling the warmup instead
    manufactures spurious early bias signals.
    """
    lsma = _linreg_endpoint(vals, length)
    lsma2 = np.full(lsma.shape, np.nan)
    valid = lsma[length - 1:]
    if valid.size >= length:
        lsma2[length - 1:] = _linreg_endpoint(valid, length)
    return lsma + (lsma - lsma2)


def chandelier_direction(high: pd.Series, low: pd.Series, close: pd.Series,
                         atr_period: int, atr_mult: float) -> np.ndarray:
    """Ratcheting Chandelier direction (+1/-1), seed +1.

    Faithful port of qhf.engines.strategies.zlch._chandelier_direction.
    Optimised with list access; the recursion is genuinely sequential.
    """
    atr_vals = wilder_atr(high, low, close, atr_period)
    close_arr = close.to_numpy(dtype=float)
    n = len(close_arr)
    roll_max = close.rolling(atr_period, min_periods=atr_period).max().to_numpy()
    roll_min = close.rolling(atr_period, min_periods=atr_period).min().to_numpy()

    direction = np.ones(n, dtype=np.int64)
    a_l = atr_vals.tolist()
    c_l = close_arr.tolist()
    rmax_l = roll_max.tolist()
    rmin_l = roll_min.tolist()
    dir_l = [1] * n

    ls_prev = float("nan")
    ss_prev = float("nan")
    prev_dir = 1
    isfin = np.isfinite
    for t in range(n):
        atr_t = a_l[t]
        if atr_t != atr_t:                       # NaN
            dir_l[t] = prev_dir
            continue
        band = atr_mult * atr_t
        ls_raw = rmax_l[t] - band
        ss_raw = rmin_l[t] + band

        if ls_prev != ls_prev:                   # no valid previous stop
            ls_cur, ss_cur = ls_raw, ss_raw
            dir_l[t] = prev_dir
            ls_prev, ss_prev = ls_cur, ss_cur
            continue

        c_prev = c_l[t - 1]
        ls_cur = max(ls_raw, ls_prev) if c_prev > ls_prev else ls_raw
        ss_cur = min(ss_raw, ss_prev) if c_prev < ss_prev else ss_raw

        c_t = c_l[t]
        if c_t > ss_prev:
            prev_dir = 1
        elif c_t < ls_prev:
            prev_dir = -1
        dir_l[t] = prev_dir
        ls_prev, ss_prev = ls_cur, ss_cur

    direction[:] = dir_l
    return direction


def htf_bias(close: pd.Series, index: pd.DatetimeIndex, rule: str,
             zlsma_len: int,
             origin: pd.Timestamp | None = None) -> tuple[np.ndarray, np.ndarray]:
    """(rising, falling) HTF ZLSMA-slope masks aligned to the entry index.

    Resample right-labelled/right-closed, evaluate the slope on the PRIOR
    closed HTF bar (.shift(1)), reindex with forward-fill. No look-ahead.

    ``origin`` pins the resample bin edges to a fixed absolute timestamp. It
    defaults to None (pandas' default binning) so existing callers are
    unchanged. Pass it when bins must be identical across differently-sliced
    windows -- a walk-forward, where each fold starts on a different date,
    would otherwise shift every HTF bin between folds. Under pandas 2.1.4 the
    default binning also raises "Values falls before first bin" for the 7D
    (W1) rule, so an explicit origin is required to evaluate W1 bias at all.
    """
    s = pd.Series(close.to_numpy(dtype=float), index=index)
    kw = {} if origin is None else {"origin": origin}
    htf = s.resample(rule, label="right", closed="right", **kw).last().dropna()
    if len(htf) < zlsma_len + 2:
        z = np.full(len(htf), np.nan)
    else:
        z = zlsma(htf.to_numpy(float), zlsma_len)
    zs = pd.Series(z, index=htf.index).shift(1)
    rising = (zs > zs.shift(1)).reindex(index, method="ffill").fillna(False).to_numpy()
    falling = (zs < zs.shift(1)).reindex(index, method="ffill").fillna(False).to_numpy()
    return rising, falling


# --------------------------------------------------------------------------- #
# Sizing / costs                                                               #
# --------------------------------------------------------------------------- #
def _lot_size(equity: float, atr_value: float, risk_pct: float,
              sl_mult: float) -> tuple[float, float]:
    effective_atr = max(atr_value, LOT_SAFETY_FLOOR_ATR)
    risk_amount = equity * risk_pct
    sl_distance = effective_atr * sl_mult
    raw = risk_amount / (sl_distance * CONTRACT_SIZE)
    stepped = np.floor(raw / LOT_STEP) * LOT_STEP
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
# Simulation                                                                   #
# --------------------------------------------------------------------------- #
def _next_index_where(mask: np.ndarray) -> np.ndarray:
    """next_idx[i] = smallest u >= i with mask[u] True, else len(mask)."""
    n = len(mask)
    idx = np.arange(n)
    big = np.where(mask, idx, n)
    return np.minimum.accumulate(big[::-1])[::-1].copy()


class Bars:
    """Pre-computed per-timeframe arrays shared across every config."""

    def __init__(self, df: pd.DataFrame):
        self.index = df.index
        self.open = df["open"].to_numpy(float)
        self.high = df["high"].to_numpy(float)
        self.low = df["low"].to_numpy(float)
        self.close = df["close"].to_numpy(float)
        self.n = len(df)
        self.high_s = df["high"]
        self.low_s = df["low"]
        self.close_s = df["close"]


def simulate(bars: Bars, direction: np.ndarray, atr_vals: np.ndarray,
             rising: np.ndarray, falling: np.ndarray,
             enable_long: bool, enable_short: bool,
             atr_mult: float, risk_pct: float, min_atr: float,
             cash: float = 10_000.0,
             max_dd_halt: float = 0.30,
             entry_override: tuple[np.ndarray, np.ndarray] | None = None) -> dict:
    """Event-driven simulation. Returns per-trade records + summary."""
    n = bars.n
    op, hi, lo, cl = bars.open, bars.high, bars.low, bars.close
    idx = bars.index

    spread_frac = SPREAD_USD_PER_OZ / SPREAD_REF_PRICE
    comm_per_oz_side = (COMMISSION_PER_LOT_RT / 2.0) / CONTRACT_SIZE

    # Entry candidate bars: chandelier flip, bias-aligned, ATR filter passed.
    d_prev = np.concatenate(([direction[0]], direction[:-1]))
    atr_ok = np.nan_to_num(atr_vals, nan=-1.0) >= min_atr
    if entry_override is None:
        long_flip = (direction == 1) & (d_prev == -1) & rising & atr_ok & enable_long
        short_flip = (direction == -1) & (d_prev == 1) & falling & atr_ok & enable_short
    else:
        # Control mode: caller supplies the entry bars (e.g. randomised).
        # Exit logic, sizing and costs stay identical, so the comparison
        # isolates ENTRY TIMING and nothing else.
        long_flip, short_flip = entry_override
    entry_mask = long_flip | short_flip
    entry_bars = np.flatnonzero(entry_mask)
    if entry_bars.size == 0:
        return {"n_trades": 0, "returns": np.array([]),
                "px_returns": np.array([]), "pnls": np.array([]),
                "entry_ts": [], "exit_ts": [], "equity_final": cash}

    next_dn = _next_index_where(direction == -1)   # next bar where dir is short
    next_up = _next_index_where(direction == 1)

    # btpy_runner applies swap POST-HOC, so backtesting.py's own equity (and
    # therefore the ATR sizer and the drawdown halt) never sees swap.
    # `cash_bt` replicates that swap-free path for sizing/halt decisions;
    # `equity` is the true account value including carry, used for returns.
    cash_bt = cash
    equity = cash
    peak = cash
    rets, pnls, entry_ts, exit_ts = [], [], [], []
    px_rets = []          # harness basis: backtesting.py per-unit price return
    t_ptr = 0
    n_entries = entry_bars.size

    while t_ptr < n_entries:
        t = int(entry_bars[t_ptr])
        f = t + 1                                   # fill bar (next open)
        if f >= n:
            break
        if cash_bt > peak:
            peak = cash_bt
        if cash_bt < peak * (1.0 - max_dd_halt) or cash_bt <= 0:
            t_ptr += 1
            continue

        is_long = bool(long_flip[t])
        atr_cur = atr_vals[t]
        if not np.isfinite(atr_cur):
            t_ptr += 1
            continue
        lots, eff_atr = _lot_size(cash_bt, float(atr_cur), risk_pct, atr_mult)
        size_oz = round(lots * CONTRACT_SIZE, 2)
        if size_oz <= 0:
            t_ptr += 1
            continue
        stop_dist = eff_atr * atr_mult
        sl = cl[t] - stop_dist if is_long else cl[t] + stop_dist

        # -- locate exit -----------------------------------------------------
        flip_bar = int(next_dn[f]) if is_long else int(next_up[f])
        scan_hi = min(flip_bar, n - 1)
        seg = slice(f, scan_hi + 1)
        if is_long:
            run = np.minimum.accumulate(lo[seg])
            hit = np.flatnonzero(run <= sl)
        else:
            run = np.maximum.accumulate(hi[seg])
            hit = np.flatnonzero(run >= sl)

        if hit.size:
            u = f + int(hit[0])
            # Gap-through fills at the open, else at the stop price.
            raw_exit = min(op[u], sl) if is_long else max(op[u], sl)
            exit_bar = u
        else:
            u = flip_bar
            if u >= n - 1:
                exit_bar = n - 1
                raw_exit = cl[n - 1]
            else:
                exit_bar = u + 1
                raw_exit = op[exit_bar]

        # -- fills with spread ----------------------------------------------
        # backtesting.py 0.6.5 applies `spread` to the ENTRY fill only; the
        # exit fills at the raw price. Verified against harness trade records
        # (exit price / raw open ratio is exactly 1.0). This is one full
        # spread per round-trip, which is what the cost model intends.
        entry_px = op[f] * (1 + spread_frac) if is_long else op[f] * (1 - spread_frac)
        exit_px = raw_exit

        gross = (exit_px - entry_px) * size_oz if is_long else (entry_px - exit_px) * size_oz
        commission = 2.0 * size_oz * comm_per_oz_side
        swap = _swap_usd(lots, is_long, idx[f], idx[exit_bar])
        pnl = gross - commission + swap

        # Harness basis: backtesting.py Trade.pl_pct is the per-unit PRICE
        # return (size-agnostic), then scaled by btpy_runner._apply_swap's
        # PnL ratio. Reproduced so sweep results stay comparable with the
        # numbers already recorded in the research log.
        # backtesting.py Trade.pl_pct:
        #   sign*(exit/entry - 1) - commissions/(|size| * entry)
        pnl_bt = gross - commission
        px_ret = ((exit_px / entry_px - 1.0) * (1.0 if is_long else -1.0)
                  - commission / (size_oz * entry_px))
        px_rets.append(px_ret * (pnl / pnl_bt) if pnl_bt != 0 else px_ret)

        ret = pnl / equity if equity > 0 else 0.0
        cash_bt += pnl_bt
        equity += pnl
        rets.append(ret)
        pnls.append(pnl)
        entry_ts.append(idx[f])
        exit_ts.append(idx[exit_bar])

        # Next entry candidate at or after the exit bar. On the bar the
        # position closes, the harness's next() already sees itself flat and
        # may take a fresh signal that same bar, so this is >= not >.
        # exit_bar >= t+1 always, so this cannot revisit the current entry.
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
# Metrics (mirror qhf.metrics.core)                                            #
# --------------------------------------------------------------------------- #
def metrics(sim: dict, basis: str = "account") -> dict:
    """Compute metrics.

    basis="account"  -> per-trade PnL / equity_at_entry. Economically correct:
                        reflects position sizing and compounding.
    basis="price"    -> per-unit price return, reproducing what
                        qhf.engines.btpy_runner feeds its metrics. Size-agnostic.
    Both are reported by the sweep; they are NOT interchangeable.
    """
    r = sim["px_returns"] if basis == "price" else sim["returns"]
    r = r[~np.isnan(r)]
    out = {
        "n_trades": int(sim["n_trades"]),
        "sharpe": float("nan"), "max_dd": float("nan"),
        "profit_factor": float("nan"), "win_rate": float("nan"),
        "cagr": float("nan"), "expectancy": float("nan"),
        "total_return": float("nan"), "trades_per_year": float("nan"),
    }
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
