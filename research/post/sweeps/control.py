"""research.post.sweeps.control — drift controls for the zerolag_chandelier sweep.

Why this exists
---------------
A long-only trend follower on XAUUSD over 2004-2026 inherits gold's secular
bull market. Ranked in isolation it will look good for free. This is the exact
failure mode that shelved flood_tide_h1 (log seq=32), flood_tide_h1_iter2
(seq=34) and regime_align_h1 (seq=38) -- in every case the measured edge
survived an unconditional null and vanished against a drift-matched one.

Two controls are provided:

random_entry_control
    Replaces the chandelier's entry bars with uniformly random bars in the
    SAME direction, keeping the exit rule, sizing and cost model identical.
    Isolates entry timing: "does the chandelier pick better moments than
    chance, given the same exit design and market exposure?"

buy_and_hold
    Passive long benchmark over the same window, for context on how much of
    any positive result is simply gold going up.

Usage:  python -m research.post.sweeps.control
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.post.sweeps import zlch_engine as E
from research.post.sweeps.data import RESAMPLE_RULE, load

REPO_ROOT = Path(__file__).resolve().parents[3]
ART = REPO_ROOT / "research" / "post" / "artifacts"
N_PERMUTATIONS = 1000
RANDOM_SEED = 20260820


def buy_and_hold(df: pd.DataFrame) -> dict:
    """Passive long benchmark on bar-close returns.

    Annualised with the ACTUAL bar frequency of this timeframe. Using the
    strategy's trades-per-year here would be a unit error: bar returns and
    per-trade returns are different observation streams.
    """
    c = df["close"].to_numpy(float)
    r = np.diff(c) / c[:-1]
    r = r[np.isfinite(r)]
    eq = np.cumprod(1.0 + r)
    dd = eq / np.maximum.accumulate(eq) - 1.0
    years = (df.index[-1] - df.index[0]).days / 365.25
    bars_per_year = len(df) / years
    return {
        "bars_per_year": float(bars_per_year),
        "sharpe": float(r.mean() / r.std(ddof=1) * np.sqrt(bars_per_year)),
        "max_dd": float(-dd.min()),
        "total_return": float(eq[-1] - 1.0),
        "cagr": float(eq[-1] ** (1.0 / years) - 1.0),
        "years": float(years),
    }


def random_entry_control(bars: E.Bars, direction: np.ndarray, atr_vals: np.ndarray,
                         is_long: bool, atr_mult: float, min_atr: float,
                         n_entries: int, n_perm: int = N_PERMUTATIONS,
                         seed: int = RANDOM_SEED) -> dict:
    """Sharpe distribution under randomised entry bars, same exit/costs."""
    rng = np.random.default_rng(seed)
    n = bars.n
    ones = np.ones(n, dtype=bool)
    empty = np.zeros(n, dtype=bool)

    # Eligible bars: anywhere the indicators are warm and the ATR filter passes.
    eligible = np.flatnonzero(
        np.isfinite(atr_vals) & (np.nan_to_num(atr_vals, nan=-1.0) >= min_atr)
    )
    eligible = eligible[(eligible > 0) & (eligible < n - 2)]

    sharpes = np.full(n_perm, np.nan)
    for i in range(n_perm):
        pick = rng.choice(eligible, size=min(n_entries, eligible.size),
                          replace=False)
        mask = np.zeros(n, dtype=bool)
        mask[pick] = True
        override = (mask, empty) if is_long else (empty, mask)
        sim = E.simulate(bars, direction, atr_vals, ones, ones,
                         is_long, not is_long, atr_mult, 0.01, min_atr,
                         max_dd_halt=1.0, entry_override=override)
        m = E.metrics(sim, basis="price")
        sharpes[i] = m["sharpe"]
    return {
        "n_perm": n_perm,
        "null_mean": float(np.nanmean(sharpes)),
        "null_std": float(np.nanstd(sharpes)),
        "null_p95": float(np.nanpercentile(sharpes, 95)),
        "sharpes": sharpes,
    }


def evaluate(row: pd.Series, n_perm: int = N_PERMUTATIONS) -> dict:
    """Full control evaluation for one swept config."""
    df = load(row["timeframe"])
    bars = E.Bars(df)
    d = E.chandelier_direction(bars.high_s, bars.low_s, bars.close_s,
                               int(row["atr_period"]), float(row["atr_mult"]))
    a = E.wilder_atr(bars.high_s, bars.low_s, bars.close_s, int(row["atr_period"]))
    if row["bias_tf"] == "none":
        rise = fall = np.ones(len(df), dtype=bool)
    else:
        rise, fall = E.htf_bias(bars.close_s, df.index,
                                RESAMPLE_RULE[row["bias_tf"]], int(row["zlsma_len"]))
    is_long = row["direction"] == "long"
    sim = E.simulate(bars, d, a, rise, fall,
                     row["direction"] in ("both", "long"),
                     row["direction"] in ("both", "short"),
                     float(row["atr_mult"]), 0.01, float(row["min_atr"]),
                     max_dd_halt=1.0)
    actual = E.metrics(sim, basis="price")

    ctrl = random_entry_control(bars, d, a, is_long, float(row["atr_mult"]),
                                float(row["min_atr"]), actual["n_trades"],
                                n_perm=n_perm)
    sh = ctrl["sharpes"]
    p_value = float(np.nanmean(sh >= actual["sharpe"]))
    bh = buy_and_hold(df)
    return {
        "config": {k: row[k] for k in
                   ["timeframe", "atr_period", "atr_mult", "bias_tf",
                    "zlsma_len", "direction", "min_atr"]},
        "actual_sharpe": actual["sharpe"],
        "actual_pf": actual["profit_factor"],
        "actual_dd": actual["max_dd"],
        "actual_win_rate": actual["win_rate"],
        "n_trades": actual["n_trades"],
        "null_mean": ctrl["null_mean"],
        "null_std": ctrl["null_std"],
        "null_p95": ctrl["null_p95"],
        "p_value": p_value,
        "buy_and_hold": bh,
    }


# --------------------------------------------------------------------------- #
# Count-matched control (supersedes random_entry_control)                      #
# --------------------------------------------------------------------------- #
def matched_random_control(run_masked, pool: np.ndarray, n_target: int,
                           n_bars: int, *, is_long: bool | None, ppy: float,
                           n_perm: int = N_PERMUTATIONS,
                           seed: int = RANDOM_SEED,
                           tol: float = 0.10, max_tries: int = 4) -> dict:
    """Random-entry null with the REALIZED trade count matched to the strategy.

    Why this is not optional: entries are consumed sequentially (a position
    blocks later signals until it exits), and some candidate bars are rejected
    outright by a strategy's own feasibility rules. So sampling `n_target` bars
    does NOT produce `n_target` trades. The shortfall matters because these
    Sharpes are annualised by trades-per-year -- a null that trades less often
    gets a mechanically smaller sqrt(ppy) factor and therefore a deflated
    Sharpe, which flatters the strategy.

    Observed severity before this fix: mild for zerolag_chandelier (705-734
    realized against a target of 890, ~10% Sharpe deflation) and fatal for
    ebb_n_flow, where the R-floor rejects almost every random bar (1-4 realized
    against 151) leaving Sharpe undefined or wild.

    This scales the number of sampled bars until the realized count lands within
    `tol` of the target, so both sides are annualised on the same footing.

    run_masked(long_mask, short_mask) -> sim dict
    is_long: True/False for a single-sided strategy, None to split ~50/50.
    """
    rng = np.random.default_rng(seed)
    empty = np.zeros(n_bars, dtype=bool)
    sharpes = np.full(n_perm, np.nan)
    realized = np.zeros(n_perm, dtype=int)

    def draw(k: float):
        pick = rng.choice(pool, size=int(min(max(k, 1), pool.size)), replace=False)
        m = np.zeros(n_bars, dtype=bool)
        m[pick] = True
        if is_long is None:
            side = rng.random(n_bars) < 0.5
            return run_masked(m & side, m & ~side)
        return run_masked(m, empty) if is_long else run_masked(empty, m)

    k = float(n_target)
    for i in range(n_perm):
        sim = None
        for _ in range(max_tries):
            sim = draw(k)
            r = sim["n_trades"]
            if r == 0:
                k = min(pool.size, k * 2.0)
                continue
            # Proportional correction that may shrink as well as grow; `k`
            # persists across permutations so it self-tunes after the first few.
            if abs(r - n_target) <= tol * n_target or k >= pool.size:
                break
            k = min(float(pool.size), max(1.0, k * n_target / r))
        if sim is not None and sim["n_trades"] >= 2:
            r_arr = sim["px_returns"]
            r_arr = r_arr[~np.isnan(r_arr)]
            sd = r_arr.std(ddof=1)
            if sd > 0:
                # Annualise with the STRATEGY's periods-per-year, not the
                # control's. Otherwise any residual trade-count mismatch moves
                # the null purely through sqrt(ppy) rather than through skill.
                sharpes[i] = float(r_arr.mean() / sd * np.sqrt(ppy))
                realized[i] = sim["n_trades"]
    ok = ~np.isnan(sharpes)
    return {"null_mean": float(np.nanmean(sharpes)),
            "null_p95": float(np.nanpercentile(sharpes[ok], 95)) if ok.any() else float("nan"),
            "sharpes": sharpes, "pool_size": int(pool.size),
            "median_realized": int(np.median(realized[ok])) if ok.any() else 0,
            "n_valid": int(ok.sum()), "target": int(n_target)}
