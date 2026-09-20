"""research.metrics.pbo — Probability of Backtest Overfitting via CSCV.

Implements Combinatorially Symmetric Cross-Validation per
Bailey, Borwein, Lopez de Prado, & Zhu (2017), "The Probability of
Backtest Overfitting", Journal of Computational Finance 20(4).

Algorithm
---------
Given a returns matrix M (T x N: T periods, N strategy variants):

1. Slice M row-wise into S equal-length submatrices M_1, ..., M_S
   (S even).
2. For every combination J of S/2 submatrices forming the in-sample (IS):
       - J^c is the remaining S/2 submatrices (OOS).
       - Compute Sharpe of each strategy on IS; let n* = argmax.
       - Compute relative rank of strategy n* on OOS.
       - Logit: lambda = log(w / (1 - w)), w = OOS rank in [0, 1].
3. PBO = Pr( lambda < 0 ) -- the fraction of combinations where the
   IS-best strategy ranks BELOW the OOS median.

Interpretation
--------------
- PBO ~ 0     : selecting on IS performance is robust (low overfitting).
- PBO ~ 0.5   : IS rank carries no information about OOS rank (pure
                noise in the ranking).
- PBO ~ 1     : the IS winner is systematically OOS-mediocre
                (severe overfitting).

Threshold convention used in this harness:
    PBO < 0.5  : minimum bar -- otherwise IS rankings are coin-flips.
    PBO < 0.3  : production target.

Performance note
----------------
S=16 -> C(16,8) = 12,870 combinations. Per-combination work is
O(N * T_block) for IS+OOS Sharpe vectors. Vectorised over strategies.
For T=2000, N=50: ~2-5 sec on a modern laptop.
"""

from __future__ import annotations

import itertools
import math
from typing import Optional

import numpy as np
import pandas as pd


def pbo(returns_matrix: pd.DataFrame,
        S: int = 16,
        periods_per_year: 'int | float | None' = None,
        return_distribution: bool = False) -> dict:
    """Compute the Probability of Backtest Overfitting via CSCV.

    Parameters
    ----------
    returns_matrix : pd.DataFrame
        T x N: per-period returns for N strategy variants. Strategies
        should have the SAME timestamps; missing rows are dropped.
    S : int
        Number of submatrices (must be even). Default 16
        -> C(16, 8) = 12,870 combinations.
    periods_per_year : int
        Annualisation factor; cancels out in ranks but kept for clarity
        and to surface IS/OOS Sharpe distributions if requested.
    return_distribution : bool
        If True, also return the array of logits across all combinations.

    Returns
    -------
    dict with:
        pbo            : float, fraction of combinations with logit < 0
        n_combinations : int
        S              : int, the chosen S
        median_logit   : float
        mean_logit     : float
        verdict        : plain-language interpretation
        logits         : np.ndarray (only if return_distribution=True)
    """
    if S % 2 != 0:
        raise ValueError("S must be even.")
    M = returns_matrix.dropna(how="any").to_numpy(dtype=float)
    T, N = M.shape
    if T < S:
        raise ValueError(f"Need T >= S; got T={T}, S={S}.")
    if N < 2:
        raise ValueError("Need at least 2 strategies (columns).")

    # Trim to whole-S divisibility.
    block_size = T // S
    M_trim = M[: block_size * S]
    blocks = [M_trim[i * block_size:(i + 1) * block_size] for i in range(S)]

    half = S // 2
    all_idx = list(range(S))
    combos = list(itertools.combinations(all_idx, half))

    if periods_per_year is None:
        raise ValueError(
            "pbo: periods_per_year is required. It used to default to "
            "252, which is right for daily bars and wrong for every "
            "other frequency this repo uses — and nothing said which "
            "you had. A returns MATRIX cannot carry frequency the way "
            "a Returns series does, so here it must be stated.")
    sqrt_K = math.sqrt(periods_per_year)
    logits = np.empty(len(combos), dtype=float)
    n_overfit = 0

    for c, is_idx in enumerate(combos):
        oos_idx = tuple(i for i in all_idx if i not in is_idx)
        is_data = np.concatenate([blocks[i] for i in is_idx], axis=0)
        oos_data = np.concatenate([blocks[i] for i in oos_idx], axis=0)

        # Sharpe per strategy on IS / OOS (vectorised over columns).
        is_mu = is_data.mean(axis=0)
        is_sd = is_data.std(axis=0, ddof=1)
        oos_mu = oos_data.mean(axis=0)
        oos_sd = oos_data.std(axis=0, ddof=1)

        # Guard against zero-std columns (degenerate).
        with np.errstate(divide="ignore", invalid="ignore"):
            is_sr = np.where(is_sd > 0, is_mu / is_sd * sqrt_K, -np.inf)
            oos_sr = np.where(oos_sd > 0, oos_mu / oos_sd * sqrt_K, -np.inf)

        n_star = int(np.argmax(is_sr))

        # Relative rank of n* in OOS, in (0, 1).
        # rank = (#{j: oos_sr[j] <= oos_sr[n*]}) / (N + 1)
        # (the +1 prevents w=1 exactly, avoiding log(0) at boundary)
        rank = float((oos_sr <= oos_sr[n_star]).sum()) / (N + 1)
        # Clip strictly inside (0, 1).
        w = min(max(rank, 1.0 / (N + 1)), N / (N + 1))
        lam = math.log(w / (1.0 - w))
        logits[c] = lam
        if lam < 0:
            n_overfit += 1

    pbo_value = n_overfit / len(combos)

    if pbo_value < 0.30:
        verdict = "Low overfitting risk; IS selection is reliable."
    elif pbo_value < 0.50:
        verdict = "Moderate overfitting; treat IS rankings with caution."
    else:
        verdict = ("HIGH overfitting; IS-best strategies are essentially "
                   "noise vs. OOS performance.")

    out = {
        "pbo": pbo_value,
        "n_combinations": len(combos),
        "S": S,
        "median_logit": float(np.median(logits)),
        "mean_logit": float(np.mean(logits)),
        "verdict": verdict,
    }
    if return_distribution:
        out["logits"] = logits
    return out
