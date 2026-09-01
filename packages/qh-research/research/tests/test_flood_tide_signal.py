"""Tests for research.pre.signals.flood_tide.generate_signals.

Emphasis is on look-ahead: the Donchian breakout must compare the current close
to the *prior* N-bar high (not a channel that includes the current bar — the
exact bug documented for crest_n_keel), the H4 filter must consult only the
prior closed H4 bar, and every per-bar output must be invariant to truncating
the data after that bar.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from research.pre.signals.flood_tide import (
    FloodTideParams,
    _apply_reentry_cooldown,
    generate_signals,
)


# --------------------------------------------------------------------------- #
# Data helpers                                                                 #
# --------------------------------------------------------------------------- #
def _make_h1(n: int, seed: int, trend: float = 0.0, start: float = 1800.0) -> pd.DataFrame:
    idx = pd.date_range("2020-01-01", periods=n, freq="h", tz="UTC")
    rng = np.random.default_rng(seed)
    close = start + np.cumsum(rng.normal(trend, 0.5, n))
    open_ = np.empty(n)
    open_[0] = start
    open_[1:] = close[:-1]
    high = np.maximum(open_, close) + np.abs(rng.normal(0, 0.3, n))
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 0.3, n))
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=idx)


def _make_h4(n: int, seed: int, start: float = 1800.0, const: float | None = None) -> pd.DataFrame:
    idx = pd.date_range("2019-12-25", periods=n, freq="4h", tz="UTC")
    if const is not None:
        close = np.full(n, const)
    else:
        rng = np.random.default_rng(seed)
        close = start + np.cumsum(rng.normal(0, 1.0, n))
    return pd.DataFrame(
        {"open": close, "high": close + 0.5, "low": close - 0.5, "close": close}, index=idx
    )


def _flat_then_breakout_h1(n: int = 200) -> pd.DataFrame:
    """Flat at 100, then a rising staircase so each late bar makes a new high."""
    idx = pd.date_range("2020-01-01", periods=n, freq="h", tz="UTC")
    flat = n // 2
    close = np.concatenate([np.full(flat, 100.0), 100.0 + np.arange(n - flat, dtype=float)])
    high = close + 0.1
    low = close - 0.1
    open_ = np.empty(n)
    open_[0] = close[0]
    open_[1:] = close[:-1]
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=idx)


# --------------------------------------------------------------------------- #
# 1. Determinism                                                              #
# --------------------------------------------------------------------------- #
def test_deterministic_output():
    h1 = _make_h1(1500, seed=1)
    h4 = _make_h4(600, seed=2)
    a = generate_signals(h1, h4)
    b = generate_signals(h1, h4)
    pd.testing.assert_frame_equal(a, b)


# --------------------------------------------------------------------------- #
# 2. No look-ahead: truncation invariance (the crest_n_keel-class guard)      #
# --------------------------------------------------------------------------- #
def test_no_lookahead_truncation_invariance():
    h1 = _make_h1(1500, seed=7, trend=0.02)
    h4 = _make_h4(700, seed=8)
    full = generate_signals(h1, h4)

    cols = ["upper_entry", "er", "htf_ema", "htf_ok", "er_ok",
            "regime_ok", "breakout_long", "candidate_entry", "entry_signal"]
    for t in (400, 800, 1200, 1499):
        # Truncate the H1 history after bar t; future bars cannot be visible.
        trunc = generate_signals(h1.iloc[: t + 1], h4)
        for col in cols:
            a = full[col].iloc[t]
            b = trunc[col].iloc[t]
            assert (a == b) or (pd.isna(a) and pd.isna(b)), (
                f"{col} at t={t} changed under truncation: full={a} trunc={b}"
            )


# --------------------------------------------------------------------------- #
# 3. Breakout excludes the current bar (prior-N-high, not incl. self)         #
# --------------------------------------------------------------------------- #
def test_breakout_uses_prior_bar_donchian():
    n = 120
    idx = pd.date_range("2020-01-01", periods=n, freq="h", tz="UTC")
    close = np.full(n, 100.0)
    high = np.full(n, 100.2)
    low = np.full(n, 99.8)
    # A single tall breakout bar at t=100: its close clears the prior 55-bar high.
    close[100] = 115.0
    high[100] = 115.0
    low[100] = 100.0
    open_ = np.empty(n)
    open_[0] = 100.0
    open_[1:] = close[:-1]
    h1 = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close}, index=idx)
    h4 = _make_h4(120, seed=0, const=1.0)

    out = generate_signals(h1, h4)
    # The breakout bar fires only because the channel excludes its own high.
    assert bool(out["breakout_long"].iloc[100])
    # Flat bars before it never break out.
    assert not out["breakout_long"].iloc[60:100].any()


# --------------------------------------------------------------------------- #
# 4. Regime filter gates entries                                              #
# --------------------------------------------------------------------------- #
def test_entry_implies_regime_and_breakout():
    h1 = _make_h1(1500, seed=11, trend=0.03)
    h4 = _make_h4(700, seed=12)
    out = generate_signals(h1, h4)
    # entry_signal is a strict subset of (regime_ok AND breakout_long).
    assert (out["entry_signal"] <= (out["regime_ok"] & out["breakout_long"])).all()


def test_regime_blocks_entry_when_htf_bearish():
    h1 = _flat_then_breakout_h1(200)
    h4 = _make_h4(200, seed=0, const=3000.0)  # H4 EMA far above price -> htf_ok False
    out = generate_signals(h1, h4)
    assert out["breakout_long"].any()          # breakouts do occur
    assert not out["htf_ok"].any()             # but trend filter forbids longs
    assert not out["entry_signal"].any()


# --------------------------------------------------------------------------- #
# 5. Reentry cooldown                                                         #
# --------------------------------------------------------------------------- #
def test_reentry_cooldown_helper():
    candidate = np.array([False, True, True, True, True, True, True, True, True])
    out = _apply_reentry_cooldown(candidate, cooldown_bars=2)
    expected = np.array([False, True, False, False, True, False, False, True, False])
    assert np.array_equal(out, expected)


def test_reentry_cooldown_spaces_entries():
    params = FloodTideParams()
    h1 = _flat_then_breakout_h1(200)          # new high every late bar -> many candidates
    h4 = _make_h4(200, seed=0, const=1.0)     # htf_ok True everywhere
    out = generate_signals(h1, h4, params)
    entries = np.flatnonzero(out["entry_signal"].to_numpy())
    assert entries.size >= 2
    assert (np.diff(entries) > params.reentry_cooldown_bars).all()


# --------------------------------------------------------------------------- #
# 6. H4 filter consults only the prior closed H4 bar                          #
# --------------------------------------------------------------------------- #
def test_htf_merge_uses_prior_closed_h4():
    h1 = _make_h1(1000, seed=21)
    h4 = _make_h4(500, seed=22)
    out = generate_signals(h1, h4)
    ema = h4["close"].ewm(span=200, adjust=False).mean()
    for t in (300, 600, 900):
        prior = ema[ema.index < h1.index[t]]
        expected = prior.iloc[-1] if len(prior) else np.nan
        got = out["htf_ema"].iloc[t]
        assert (got == expected) or (pd.isna(got) and pd.isna(expected)), (
            f"htf_ema at t={t}: got {got}, expected strict-prior H4 EMA {expected}"
        )
