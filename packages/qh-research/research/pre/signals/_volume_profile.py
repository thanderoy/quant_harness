"""Rolling Volume Profile over H1 bars, no look-ahead.

For each H1 bar T, compute the volume profile over the trailing window
``[T-lookback, T-1]`` (exclusive of T itself) using percentage-of-price
binning. POC is the bin with maximum volume; HVNs are interior local maxima.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = ["rolling_volume_profile_levels"]


def _profile_window(
    w_lo: np.ndarray,
    w_hi: np.ndarray,
    w_vol: np.ndarray,
    bin_width: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (bin_centres, bin_volumes) for one window. Bins span [low_min, high_max]."""
    bin_min = float(w_lo.min())
    bin_max = float(w_hi.max())
    if bin_width <= 0 or bin_max <= bin_min:
        return np.array([]), np.array([])
    n_bins = max(int(np.ceil((bin_max - bin_min) / bin_width)), 1)
    edges = bin_min + np.arange(n_bins + 1) * bin_width
    centres = (edges[:-1] + edges[1:]) / 2.0
    bin_lo = edges[:-1]
    bin_hi = edges[1:]

    bar_range = np.maximum(w_hi - w_lo, 1e-12)
    # overlap[i, b] = max(0, min(bar_hi, bin_hi) - max(bar_lo, bin_lo))
    overlap = np.maximum(
        0.0,
        np.minimum(w_hi[:, None], bin_hi[None, :])
        - np.maximum(w_lo[:, None], bin_lo[None, :]),
    )
    contrib = (overlap / bar_range[:, None]) * w_vol[:, None]
    bin_volumes = contrib.sum(axis=0)
    return centres, bin_volumes


def rolling_volume_profile_levels(
    h1_df: pd.DataFrame,
    lookback_bars: int = 120,
    bin_width_pct: float = 0.00025,
) -> pd.DataFrame:
    required = ["high", "low", "close", "volume"]
    missing = [c for c in required if c not in h1_df.columns]
    if missing:
        raise ValueError(f"h1_df missing columns: {missing}")

    high = h1_df["high"].to_numpy(dtype=float)
    low = h1_df["low"].to_numpy(dtype=float)
    close = h1_df["close"].to_numpy(dtype=float)
    volume = h1_df["volume"].to_numpy(dtype=float)
    n = len(h1_df)

    poc = np.full(n, np.nan)
    hvn_prices: list[list[float]] = [[] for _ in range(n)]
    hvn_volumes: list[list[float]] = [[] for _ in range(n)]

    for t in range(lookback_bars, n):
        # CRITICAL: window strictly before T — t itself is NOT in the slice.
        w_lo = low[t - lookback_bars : t]
        w_hi = high[t - lookback_bars : t]
        w_vol = volume[t - lookback_bars : t]
        # Bin width is locked at the H1 bar that closed the window (t-1), not t.
        bin_width = close[t - 1] * bin_width_pct

        centres, bin_volumes = _profile_window(w_lo, w_hi, w_vol, bin_width)
        if centres.size == 0 or bin_volumes.sum() <= 0:
            continue

        poc_idx = int(np.argmax(bin_volumes))
        poc[t] = float(centres[poc_idx])

        # HVNs: interior local maxima (strict >); boundary bins excluded.
        if centres.size >= 3:
            interior = np.arange(1, centres.size - 1)
            mask = (
                (bin_volumes[interior] > bin_volumes[interior - 1])
                & (bin_volumes[interior] > bin_volumes[interior + 1])
            )
            peak_idx = interior[mask]
            if peak_idx.size > 0:
                order = peak_idx[np.argsort(-bin_volumes[peak_idx])]
                hvn_prices[t] = [float(centres[i]) for i in order]
                hvn_volumes[t] = [float(bin_volumes[i]) for i in order]

    return pd.DataFrame(
        {"poc": poc, "hvn_prices": hvn_prices, "hvn_volumes": hvn_volumes},
        index=h1_df.index,
    )
