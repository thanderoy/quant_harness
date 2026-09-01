"""Measure the raw edge of an entry signal *before* any exit logic exists.

This module implements the **E-Ratio** (Edge Ratio) from Curtis Faith's
*Way of the Turtle*, augmented with a permutation-based significance test, a
random-entry baseline, and conditional forward-return statistics.

The E-Ratio asks a single question: *after this signal fires, does price move
more in our favour than against us, relative to volatility?* It deliberately
ignores stops, targets, position sizing and R:R rules. Those belong to the
strategy layer; here we are gating the entry idea itself.

Why this exists
---------------
Our research pipeline historically conflated *entry-signal edge* with
*full-strategy performance*. When a strategy failed we could not tell whether
the entry was bad or the exit rules destroyed a real edge; when one passed we
could not tell whether the entry or the exit was doing the work. This tool
isolates the entry's contribution so we can fail bad ideas cheaply (in a
notebook) and diagnose underperforming strategies.

This is a **pre-strategy diagnostic**. It does not replace the
``btpy_runner.py`` backtest harness — it precedes it. A signal should clear this
stage before we invest in building entry/exit/sizing rules around it.

This module is intentionally upstream of ``strategies/`` and imports nothing
from it. It re-implements Wilder ATR locally to keep coupling low.

Usage
-----
>>> import pandas as pd
>>> from research.pre.signal_edge import signal_edge_report
>>>
>>> ohlc = pd.read_csv(
...     "XAUUSD_H1.csv", parse_dates=["time"], index_col="time"
... )[["open", "high", "low", "close"]]
>>>
>>> # Build a +1/-1/0 signal aligned to ohlc.index. A signal at bar t means
>>> # "enter at the bar t+1 open"; the report enforces that convention.
>>> def crest_n_keel_signal(ohlc: pd.DataFrame) -> pd.Series:
...     ...  # HMA direction + stochastic cross
>>>
>>> signal = crest_n_keel_signal(ohlc)
>>> report = signal_edge_report(signal, ohlc, forward_windows=[10, 30, 70])
>>> print(report.per_window)        # E-Ratio per forward window
>>> print(report.permutation)       # p-values vs the permuted null
>>> print(report.baseline)          # what "no edge" looks like
>>> print(report.metadata)          # hashes + params for reproducibility

Interpretation rule of thumb
----------------------------
* E-Ratio ~ 1.0 with p > 0.05  -> no exploitable asymmetry; kill the idea.
* E-Ratio > 1.15 with p < 0.05 -> the entry has structure worth building on.
* Strong full-strategy result but weak E-Ratio -> the *exit* logic is the
  source of profit (or the entry edge is fragile); investigate before trusting.
"""

from __future__ import annotations

import hashlib
import warnings
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

__all__ = ["SignalEdgeReport", "signal_edge_report", "wilder_atr"]

# Per-signal excursions are normalised by ATR. Guard against division blow-ups
# when ATR is (near) zero in a degenerate / flat-price regime.
ATR_FLOOR: float = 1e-8

# Below this many signals the E-Ratio is statistically unstable (Faith's
# observation, and consistent with small-sample variance of a ratio of means).
MIN_SIGNALS_FOR_STABILITY: int = 30


@dataclass
class SignalEdgeReport:
    """Container for the output of :func:`signal_edge_report`.

    Attributes
    ----------
    per_window:
        One row per forward window. Columns: ``window``, ``n_signals``,
        ``mean_norm_mfe``, ``mean_norm_mae``, ``e_ratio``, ``mean_fwd_return``,
        ``hit_rate``, ``std_fwd_return``.
    per_signal:
        One row per (valid signal instance x window). Columns: ``signal_time``,
        ``direction``, ``window``, ``norm_mfe``, ``norm_mae``, ``fwd_return``,
        ``atr_at_signal``.
    permutation:
        One row per window. Columns: ``window``, ``e_ratio_actual``,
        ``e_ratio_null_mean``, ``e_ratio_null_p05``, ``e_ratio_null_p95``,
        ``p_value``, ``n_permutations``.
    baseline:
        Same columns as ``per_window`` but computed on a single random-entry
        signal at the same long/short frequency on the same OHLC data.
    metadata:
        Reproducibility metadata (hashes, parameters, signal counts).
    """

    per_window: pd.DataFrame
    per_signal: pd.DataFrame
    permutation: pd.DataFrame
    baseline: pd.DataFrame
    metadata: dict


# --------------------------------------------------------------------------- #
# ATR (Wilder smoothing)                                                       #
# --------------------------------------------------------------------------- #
def wilder_atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """Average True Range using Wilder's smoothing (RMA/SMMA).

    This mirrors ``strategies/indicators.atr`` bit-for-bit so the research and
    live layers agree, but is re-implemented here so ``research/`` stays
    independent of ``strategies/``.

    PITFALL #1 (no look-ahead): ``atr[t]`` is a function of bars ``[0, t]``
    only. The seed at index ``period`` is the SMA of ``TR[1..period]`` and the
    recursion ``atr[i] = (atr[i-1] * (period - 1) + tr[i]) / period`` only ever
    looks backward. Truncating the data after bar ``t`` therefore cannot change
    ``atr[t]`` — :func:`signal_edge_report` relies on this and a test asserts it.
    """
    n = len(close)
    prev_close = close.shift(1)
    tr = pd.concat(
        [high - low, (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)

    atr_vals = np.full(n, np.nan)
    if n < period + 1:
        return pd.Series(atr_vals, index=close.index)

    # Seed: SMA of the first `period` TR values (TR is NaN at index 0).
    atr_vals[period] = tr.iloc[1 : period + 1].mean()
    for i in range(period + 1, n):
        atr_vals[i] = (atr_vals[i - 1] * (period - 1) + tr.iloc[i]) / period

    return pd.Series(atr_vals, index=close.index)


# --------------------------------------------------------------------------- #
# Forward extremes                                                             #
# --------------------------------------------------------------------------- #
def _forward_extremes(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    window: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorised forward MFE/MAE/return inputs for a single window.

    For a signal at bar ``t`` the forward slice is ``ohlc.iloc[t+1 : t+1+w]``
    (the ``w`` bars *after* the signal bar). We return, aligned to ``t``:

    * ``fwd_high[t]`` = max high over bars ``[t+1, t+1+w)``
    * ``fwd_low[t]``  = min low  over bars ``[t+1, t+1+w)``
    * ``fwd_close[t]``= close at bar ``t+w`` (last bar of the slice)

    Entries where the slice would run past the data (``t + 1 + w > n``) are left
    as NaN and dropped downstream.
    """
    n = len(high)
    fwd_high = np.full(n, np.nan)
    fwd_low = np.full(n, np.nan)
    fwd_close = np.full(n, np.nan)

    if n < window:
        return fwd_high, fwd_low, fwd_close

    # sliding_window_view(x, w)[j] == x[j : j + w]
    sw_high = np.lib.stride_tricks.sliding_window_view(high, window)
    sw_low = np.lib.stride_tricks.sliding_window_view(low, window)
    max_high = sw_high.max(axis=1)  # length n - w + 1
    min_low = sw_low.min(axis=1)

    # Slice starts at t+1, so window j = t+1. Valid t: 0 <= t+1 <= n - w
    # i.e. t in [0, n - w - 1]. close[t+w] is then always in range.
    valid_t = np.arange(0, n - window)
    fwd_high[valid_t] = max_high[valid_t + 1]
    fwd_low[valid_t] = min_low[valid_t + 1]
    fwd_close[valid_t] = close[valid_t + window]
    return fwd_high, fwd_low, fwd_close


# --------------------------------------------------------------------------- #
# Excursion + return mechanics                                                 #
# --------------------------------------------------------------------------- #
def _excursions(
    idx: np.ndarray,
    dirs: np.ndarray,
    open_: np.ndarray,
    fwd_high: np.ndarray,
    fwd_low: np.ndarray,
    fwd_close: np.ndarray,
    atr_arr: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (norm_mfe, norm_mae, fwd_return) for the given signal indices.

    PITFALL #2 (no look-ahead at entry): entry price is ``open[t+1]``, the open
    of the bar *after* the signal — never ``close[t]``. In live trading a signal
    confirmed on the closed bar ``t`` can only be acted on at the next bar's
    open, so measuring excursions from ``close[t]`` would credit the signal with
    a move it could not have captured.

    MFE and MAE are *excursions* and are floored at 0: if price never traded
    against the position, the adverse excursion is 0, not negative.
    """
    entry = open_[idx + 1]
    fh = fwd_high[idx]
    fl = fwd_low[idx]
    fc = fwd_close[idx]
    atr_at = atr_arr[idx]

    long_mask = dirs > 0
    mfe = np.where(long_mask, fh - entry, entry - fl)
    mae = np.where(long_mask, entry - fl, fh - entry)
    mfe = np.maximum(mfe, 0.0)
    mae = np.maximum(mae, 0.0)

    norm_mfe = mfe / atr_at
    norm_mae = mae / atr_at
    fwd_return = (fc - entry) / entry * dirs
    return norm_mfe, norm_mae, fwd_return


def _e_ratio(norm_mfe: np.ndarray, norm_mae: np.ndarray) -> float:
    """E-Ratio = mean(norm_MFE) / mean(norm_MAE) across signals."""
    if norm_mfe.size == 0:
        return float("nan")
    mean_mae = float(np.mean(norm_mae))
    if mean_mae <= 1e-12:
        return float("nan")
    return float(np.mean(norm_mfe)) / mean_mae


def _window_pool(finite_atr_idx: np.ndarray, n: int, window: int) -> np.ndarray:
    """Bar indices eligible to *hold* a signal at this window.

    A bar is eligible if its ATR is finite/above-floor (so excursions can be
    normalised) and its forward slice fits in the data (``t <= n - w - 1``).
    """
    return finite_atr_idx[finite_atr_idx <= n - window - 1]


# --------------------------------------------------------------------------- #
# Per-window aggregation                                                       #
# --------------------------------------------------------------------------- #
def _aggregate_window(
    idx: np.ndarray,
    dirs: np.ndarray,
    window: int,
    open_: np.ndarray,
    fwd_high: np.ndarray,
    fwd_low: np.ndarray,
    fwd_close: np.ndarray,
    atr_arr: np.ndarray,
    index: pd.Index,
    collect_per_signal: bool,
) -> tuple[dict, list[dict]]:
    """Aggregate one forward window into a per_window row (+ per_signal rows)."""
    norm_mfe, norm_mae, fwd_return = _excursions(
        idx, dirs, open_, fwd_high, fwd_low, fwd_close, atr_arr
    )

    n_signals = int(idx.size)
    if n_signals == 0:
        row = {
            "window": window,
            "n_signals": 0,
            "mean_norm_mfe": float("nan"),
            "mean_norm_mae": float("nan"),
            "e_ratio": float("nan"),
            "mean_fwd_return": float("nan"),
            "hit_rate": float("nan"),
            "std_fwd_return": float("nan"),
        }
        return row, []

    row = {
        "window": window,
        "n_signals": n_signals,
        "mean_norm_mfe": float(np.mean(norm_mfe)),
        "mean_norm_mae": float(np.mean(norm_mae)),
        "e_ratio": _e_ratio(norm_mfe, norm_mae),
        "mean_fwd_return": float(np.mean(fwd_return)),
        "hit_rate": float(np.mean(fwd_return > 0.0)),
        # ddof=1 sample std; falls back to 0.0 for a single observation.
        "std_fwd_return": float(np.std(fwd_return, ddof=1)) if n_signals > 1 else 0.0,
    }

    per_signal_rows: list[dict] = []
    if collect_per_signal:
        atr_at = atr_arr[idx]
        for k in range(n_signals):
            per_signal_rows.append(
                {
                    "signal_time": index[idx[k]],
                    "direction": int(dirs[k]),
                    "window": window,
                    "norm_mfe": float(norm_mfe[k]),
                    "norm_mae": float(norm_mae[k]),
                    "fwd_return": float(fwd_return[k]),
                    "atr_at_signal": float(atr_at[k]),
                }
            )
    return row, per_signal_rows


def _compute_per_window(
    signal_idx: np.ndarray,
    signal_dir: np.ndarray,
    forward_windows: list[int],
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    atr_arr: np.ndarray,
    finite_atr_idx: np.ndarray,
    index: pd.Index,
    collect_per_signal: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[int, np.ndarray]]:
    """Build the per_window (and per_signal) frames for a set of signals.

    Returns the per_window frame, the per_signal frame, and a dict mapping each
    window -> eligible bar pool (reused by the permutation test).
    """
    n = len(close)
    per_window_rows: list[dict] = []
    per_signal_rows: list[dict] = []
    pools: dict[int, np.ndarray] = {}

    for window in forward_windows:
        fwd_high, fwd_low, fwd_close = _forward_extremes(high, low, close, window)
        pool = _window_pool(finite_atr_idx, n, window)
        pools[window] = pool

        # Keep only signals that land on an eligible bar for this window.
        eligible = np.isin(signal_idx, pool)
        idx = signal_idx[eligible]
        dirs = signal_dir[eligible]

        row, ps_rows = _aggregate_window(
            idx, dirs, window, open_, fwd_high, fwd_low, fwd_close,
            atr_arr, index, collect_per_signal,
        )
        per_window_rows.append(row)
        per_signal_rows.extend(ps_rows)

        if row["n_signals"] < MIN_SIGNALS_FOR_STABILITY:
            # PITFALL #4 (tiny sample): the E-Ratio is a ratio of means and is
            # unstable below ~30 observations.
            warnings.warn(
                f"window={window}: only {row['n_signals']} valid signals "
                f"(< {MIN_SIGNALS_FOR_STABILITY}); E-Ratio is unstable. "
                "Use more data before trusting this result.",
                UserWarning,
                stacklevel=3,
            )

    per_window = pd.DataFrame(per_window_rows)
    per_signal = pd.DataFrame(
        per_signal_rows,
        columns=[
            "signal_time", "direction", "window",
            "norm_mfe", "norm_mae", "fwd_return", "atr_at_signal",
        ],
    )
    return per_window, per_signal, pools


# --------------------------------------------------------------------------- #
# Permutation test                                                             #
# --------------------------------------------------------------------------- #
def _e_ratio_for_indices(
    idx: np.ndarray,
    dirs: np.ndarray,
    open_: np.ndarray,
    fwd_high: np.ndarray,
    fwd_low: np.ndarray,
    fwd_close: np.ndarray,
    atr_arr: np.ndarray,
) -> float:
    norm_mfe, norm_mae, _ = _excursions(
        idx, dirs, open_, fwd_high, fwd_low, fwd_close, atr_arr
    )
    return _e_ratio(norm_mfe, norm_mae)


def _permutation_test(
    per_window: pd.DataFrame,
    signal_idx: np.ndarray,
    signal_dir: np.ndarray,
    forward_windows: list[int],
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    atr_arr: np.ndarray,
    pools: dict[int, np.ndarray],
    null_pools: dict[int, np.ndarray],
    n_permutations: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """One-sided permutation test of the actual E-Ratio against a shuffled null.

    For each window we hold the long/short *counts fixed* and scatter that many
    signals at random over the null bar pool, recomputing the E-Ratio each time.
    The null answers: "how large an E-Ratio would this many random entries on
    this data produce by chance?"

    ``pools`` (finite-ATR, window-fit) is used only to *count* how many actual
    signals contribute at each window. ``null_pools`` is the universe the random
    entries are drawn from — identical to ``pools`` by default, but restricted to
    a caller-supplied eligible universe (e.g. regime-filtered bars) when a
    ``eligible_pool`` is passed to :func:`signal_edge_report`. Restricting the
    null this way stops a separate regime filter's directional drift from leaking
    into — and inflating — the entry's measured E-Ratio.

    PITFALL #3 (window overlap): signals within ``w`` bars share overlapping
    forward windows and are therefore *not independent*. We do not try to
    de-overlap them. The permutation test is the right tool precisely because it
    permutes signals on the *same* overlap-prone data, so the null distribution
    inherits the same dependence structure as the actual statistic.

    We re-count the long/short signals that are *eligible at each window* (rather
    than using the raw totals) so the null places exactly as many contributing
    signals as the actual statistic was computed over.
    """
    rows: list[dict] = []

    for window in forward_windows:
        fwd_high, fwd_low, fwd_close = _forward_extremes(high, low, close, window)
        pool = pools[window]
        sample_pool = null_pools[window]

        eligible = np.isin(signal_idx, pool)
        dirs = signal_dir[eligible]
        n_long = int(np.sum(dirs > 0))
        n_short = int(np.sum(dirs < 0))
        n_place = n_long + n_short

        actual = float(
            per_window.loc[per_window["window"] == window, "e_ratio"].iloc[0]
        )

        null = np.full(n_permutations, np.nan)
        if n_place > 0 and sample_pool.size >= n_place and np.isfinite(actual):
            perm_dirs = np.empty(n_place, dtype=np.int64)
            perm_dirs[:n_long] = 1
            perm_dirs[n_long:] = -1
            for p in range(n_permutations):
                chosen = rng.choice(sample_pool, size=n_place, replace=False)
                null[p] = _e_ratio_for_indices(
                    chosen, perm_dirs, open_, fwd_high, fwd_low, fwd_close, atr_arr
                )

        null_valid = null[np.isfinite(null)]
        if null_valid.size > 0 and np.isfinite(actual):
            # One-sided: is the actual E-Ratio in the right tail of the null?
            p_value = float(np.mean(null_valid >= actual))
            null_mean = float(np.mean(null_valid))
            null_p05 = float(np.percentile(null_valid, 5))
            null_p95 = float(np.percentile(null_valid, 95))
        else:
            p_value = null_mean = null_p05 = null_p95 = float("nan")

        rows.append(
            {
                "window": window,
                "e_ratio_actual": actual,
                "e_ratio_null_mean": null_mean,
                "e_ratio_null_p05": null_p05,
                "e_ratio_null_p95": null_p95,
                "p_value": p_value,
                "n_permutations": n_permutations,
            }
        )

    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Random-entry baseline                                                        #
# --------------------------------------------------------------------------- #
def _random_baseline(
    n_long: int,
    n_short: int,
    forward_windows: list[int],
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    atr_arr: np.ndarray,
    finite_atr_idx: np.ndarray,
    sampling_pool_idx: np.ndarray,
    index: pd.Index,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """A single random-entry signal report at the same long/short frequency.

    This is a tangible "what does no edge look like" reference, distinct from
    the permutation null (which is a distribution). Bars are sampled from
    ``sampling_pool_idx`` (the finite-ATR pool by default, or a caller-supplied
    eligible universe such as regime-filtered bars) intersected with the room
    needed for the *largest* forward window, so the same random signal is
    evaluable at every window. ``finite_atr_idx`` is still used to normalise the
    chosen bars' excursions.
    """
    n = len(close)
    n_place = n_long + n_short
    max_window = max(forward_windows)
    base_pool = sampling_pool_idx[sampling_pool_idx <= n - max_window - 1]

    if n_place == 0 or base_pool.size < n_place:
        empty = pd.DataFrame(
            [
                {
                    "window": w, "n_signals": 0,
                    "mean_norm_mfe": float("nan"), "mean_norm_mae": float("nan"),
                    "e_ratio": float("nan"), "mean_fwd_return": float("nan"),
                    "hit_rate": float("nan"), "std_fwd_return": float("nan"),
                }
                for w in forward_windows
            ]
        )
        return empty

    chosen = rng.choice(base_pool, size=n_place, replace=False)
    base_dir = np.empty(n_place, dtype=np.int64)
    base_dir[:n_long] = 1
    base_dir[n_long:] = -1
    order = np.argsort(chosen)
    base_idx = chosen[order]
    base_dir = base_dir[order]

    # The baseline mutes the tiny-sample warning: it intentionally mirrors the
    # actual signal count and any warning was already emitted for the actual.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        baseline, _, _ = _compute_per_window(
            base_idx, base_dir, forward_windows,
            open_, high, low, close, atr_arr, finite_atr_idx, index,
            collect_per_signal=False,
        )
    return baseline


# --------------------------------------------------------------------------- #
# Validation + metadata                                                        #
# --------------------------------------------------------------------------- #
def _validate_inputs(signal: pd.Series, ohlc: pd.DataFrame) -> None:
    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in ohlc.columns]
    if missing:
        raise ValueError(f"ohlc is missing required columns: {missing}")
    if len(signal) != len(ohlc):
        raise ValueError(
            f"signal length ({len(signal)}) != ohlc length ({len(ohlc)})"
        )
    if not signal.index.equals(ohlc.index):
        raise ValueError("signal.index must be identical to ohlc.index")
    bad = set(np.unique(signal.dropna().to_numpy())) - {-1, 0, 1, -1.0, 0.0, 1.0}
    if bad:
        raise ValueError(f"signal must contain only -1, 0, +1; found {sorted(bad)}")


def _coerce_eligible_mask(
    eligible_pool: pd.Series | np.ndarray, n: int
) -> np.ndarray:
    """Coerce a caller-supplied eligible universe to a boolean mask of length n.

    Accepts either a boolean mask (Series or ndarray) aligned to ``ohlc.index``,
    or an array of integer bar positions. Returns a length-``n`` boolean mask.
    """
    arr = eligible_pool.to_numpy() if isinstance(eligible_pool, pd.Series) else np.asarray(eligible_pool)
    if arr.dtype == bool:
        if arr.shape[0] != n:
            raise ValueError(
                f"eligible_pool boolean mask length ({arr.shape[0]}) != n_bars ({n})"
            )
        return arr
    mask = np.zeros(n, dtype=bool)
    positions = arr.astype(np.int64)
    if positions.size and (positions.min() < 0 or positions.max() >= n):
        raise ValueError("eligible_pool integer positions out of range [0, n_bars)")
    mask[positions] = True
    return mask


def _sha16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# --------------------------------------------------------------------------- #
# Public entry point                                                           #
# --------------------------------------------------------------------------- #
def signal_edge_report(
    signal: pd.Series,
    ohlc: pd.DataFrame,
    forward_windows: Iterable[int] = (10, 30, 70),
    atr_period: int = 14,
    n_permutations: int = 1000,
    random_seed: int = 42,
    eligible_pool: pd.Series | np.ndarray | None = None,
) -> SignalEdgeReport:
    """Measure raw signal edge before any exit logic exists.

    Parameters
    ----------
    signal:
        ``+1`` for a long signal, ``-1`` for short, ``0`` for no signal. The
        index must be identical to ``ohlc.index``. A signal at bar ``t`` means
        "enter at bar ``t+1`` open" — the report enforces this (no look-ahead).
    ohlc:
        Columns ``['open', 'high', 'low', 'close']`` with a ``DatetimeIndex``
        aligned to ``signal``.
    forward_windows:
        Bar counts at which to measure MFE / MAE / forward return.
    atr_period:
        Lookback for the Wilder ATR used to normalise MFE / MAE.
    n_permutations:
        Number of permutations for the significance test.
    random_seed:
        Seed for the permutation and baseline sampling (reproducibility). The
        baseline uses ``random_seed + 1`` so it is independent of the null.
    eligible_pool:
        Optional universe the permutation null *and* random baseline draw their
        random entries from — a boolean mask aligned to ``ohlc.index`` or an
        array of integer bar positions. It is intersected with the finite-ATR
        pool. Default ``None`` samples from all finite-ATR bars (unchanged
        behaviour). Pass a regime-filtered mask when the entry is preceded by a
        separate filter, so the filter's directional drift is baked into the
        null instead of inflating the entry's measured E-Ratio. The *actual*
        signals are never restricted by this — only the null they are tested
        against.

    Returns
    -------
    SignalEdgeReport

    Notes
    -----
    Signals closer together than a window overlap and are not independent; see
    :func:`_permutation_test` (PITFALL #3). This is expected and handled by the
    permutation test, not "corrected" away.
    """
    forward_windows = list(forward_windows)
    if not forward_windows:
        raise ValueError("forward_windows must contain at least one window")
    if any(w <= 0 for w in forward_windows):
        raise ValueError("forward_windows must be positive")
    _validate_inputs(signal, ohlc)

    index = ohlc.index
    open_ = ohlc["open"].to_numpy(dtype=float)
    high = ohlc["high"].to_numpy(dtype=float)
    low = ohlc["low"].to_numpy(dtype=float)
    close = ohlc["close"].to_numpy(dtype=float)
    n = len(close)

    atr_series = wilder_atr(ohlc["high"], ohlc["low"], ohlc["close"], atr_period)
    atr_arr = atr_series.to_numpy(dtype=float)

    # Bars whose ATR is finite and above the floor — the only bars on which an
    # excursion can be normalised. (PITFALL: skip NaN / near-zero ATR.)
    finite_atr_idx = np.where(np.isfinite(atr_arr) & (atr_arr >= ATR_FLOOR))[0]

    # Universe the null / baseline sample from. Restricted to the caller's
    # eligible bars (intersected with finite ATR) when provided.
    if eligible_pool is None:
        eligible_atr_idx = finite_atr_idx
    else:
        elig_mask = _coerce_eligible_mask(eligible_pool, n)
        eligible_atr_idx = finite_atr_idx[elig_mask[finite_atr_idx]]

    sig_arr = signal.fillna(0).to_numpy()
    signal_idx = np.where(sig_arr != 0)[0]
    signal_dir = np.sign(sig_arr[signal_idx]).astype(np.int64)
    n_long_total = int(np.sum(signal_dir > 0))
    n_short_total = int(np.sum(signal_dir < 0))

    # --- per-window + per-signal -------------------------------------------- #
    per_window, per_signal, pools = _compute_per_window(
        signal_idx, signal_dir, forward_windows,
        open_, high, low, close, atr_arr, finite_atr_idx, index,
        collect_per_signal=True,
    )

    # --- permutation test --------------------------------------------------- #
    # Null-sampling pools restricted to the eligible universe (== `pools` when
    # no eligible_pool was supplied).
    null_pools = {w: _window_pool(eligible_atr_idx, n, w) for w in forward_windows}
    rng = np.random.default_rng(random_seed)
    permutation = _permutation_test(
        per_window, signal_idx, signal_dir, forward_windows,
        open_, high, low, close, atr_arr, pools, null_pools, n_permutations, rng,
    )

    # --- random-entry baseline (independent seed) --------------------------- #
    baseline_rng = np.random.default_rng(random_seed + 1)
    baseline = _random_baseline(
        n_long_total, n_short_total, forward_windows,
        open_, high, low, close, atr_arr, finite_atr_idx, eligible_atr_idx,
        index, baseline_rng,
    )

    # --- metadata ----------------------------------------------------------- #
    metadata = {
        "signal_hash": _sha16(signal.to_csv()),
        "ohlc_hash": _sha16(ohlc.to_csv()),
        "ohlc_start": index[0].isoformat() if n else None,
        "ohlc_end": index[-1].isoformat() if n else None,
        "n_bars": n,
        "atr_period": atr_period,
        "forward_windows": forward_windows,
        "n_permutations": n_permutations,
        "random_seed": random_seed,
        "n_long_signals": n_long_total,
        "n_short_signals": n_short_total,
        "eligible_pool_restricted": eligible_pool is not None,
        "n_eligible_pool_bars": int(eligible_atr_idx.size),
    }

    return SignalEdgeReport(
        per_window=per_window,
        per_signal=per_signal,
        permutation=permutation,
        baseline=baseline,
        metadata=metadata,
    )
