"""Tests for research.signal_edge.

Build/read these in order — each is a checkpoint:

1. Random signal       -> E-Ratio ~ 1.0, p > 0.05   (sanity: no false edge)
2. Synthetic +2/-0.5   -> E-Ratio ~ 4.0             (MFE/MAE mechanics correct)
3. crest_n_keel        -> tool sees edge on a control; entry itself has none
                          (reframed after investigation; see calibration_results.md)
4. ebb_n_flow          -> weak edge                 (calibration, needs data)
5. Determinism         -> identical outputs on same seed
6. Look-ahead probe    -> truncation invariance (incl. ATR[t])

Tests 3 and 4 need the real 2004-2020 XAUUSD H1 dataset. Point the env var
``XAUUSD_H1_CSV`` at a CSV with columns time/open/high/low/close (or drop the
file at research/data/XAUUSD_H1.csv); otherwise they skip with a clear message.
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from research.signal_edge import signal_edge_report, wilder_atr


# --------------------------------------------------------------------------- #
# Synthetic data helpers                                                       #
# --------------------------------------------------------------------------- #
def make_gbm_ohlc(
    n_bars: int,
    *,
    seed: int,
    sigma: float = 0.004,
    drift: float = 0.0,
    start_price: float = 1800.0,
    freq: str = "h",
) -> pd.DataFrame:
    """Geometric-Brownian-motion OHLC with well-formed high/low wicks.

    No drift by default so a random entry has no directional advantage — the
    foundation of the Test 1 sanity check.
    """
    rng = np.random.default_rng(seed)
    log_ret = rng.normal(drift, sigma, size=n_bars)
    close = start_price * np.exp(np.cumsum(log_ret))
    open_ = np.empty(n_bars)
    open_[0] = start_price
    open_[1:] = close[:-1]  # open at previous close (continuous)

    # Symmetric intrabar wicks so highs/lows do not bias MFE vs MAE.
    body_hi = np.maximum(open_, close)
    body_lo = np.minimum(open_, close)
    wick = np.abs(rng.normal(0.0, sigma, size=n_bars)) * close
    high = body_hi + wick
    low = body_lo - wick

    idx = pd.date_range("2000-01-03", periods=n_bars, freq=freq)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close}, index=idx
    )


def make_random_signal(
    ohlc: pd.DataFrame,
    *,
    n_signals: int,
    seed: int,
    warmup: int = 50,
    tail: int = 80,
) -> pd.Series:
    """Random +-1 signal at `n_signals` distinct bars, avoiding edges."""
    rng = np.random.default_rng(seed)
    n = len(ohlc)
    pool = np.arange(warmup, n - tail)
    idx = rng.choice(pool, size=n_signals, replace=False)
    sig = np.zeros(n, dtype=int)
    sig[idx] = rng.choice([-1, 1], size=n_signals)
    return pd.Series(sig, index=ohlc.index)


def build_edge_ohlc(
    n_signals: int = 50,
    *,
    spacing: int = 20,
    warmup: int = 40,
    mfe_atr: float = 2.0,
    mae_atr: float = 0.5,
    atr_unit: float = 1.0,
    start_price: float = 1800.0,
) -> tuple[pd.DataFrame, pd.Series]:
    """OHLC where every long signal is followed by a deterministic move.

    Over the 10 bars after each signal: price dips ``mae_atr`` (creating the
    MAE), rallies to ``+mfe_atr`` (the MFE), then pulls back. Because both MFE
    and MAE are *absolute* price moves, the per-signal ratio is exactly
    ``mfe_atr / mae_atr`` regardless of the ATR level, so the aggregate E-Ratio
    is exactly that ratio (~4.0 here). Window must be 10.
    """
    mfe = mfe_atr * atr_unit
    mae = mae_atr * atr_unit
    window = 10
    n = warmup + n_signals * spacing + window + 5

    o = np.zeros(n)
    h = np.zeros(n)
    low = np.zeros(n)
    c = np.zeros(n)

    # Calm baseline: flat bar with +-0.5*atr_unit wicks => true range == atr_unit.
    half = 0.5 * atr_unit
    price = start_price
    o[0] = h[0] = low[0] = c[0] = price

    signal_bars: list[int] = []
    next_signal = warmup
    i = 1
    while i < n:
        if i == next_signal and len(signal_bars) < n_signals and i + window + 1 < n:
            # Signal fires on bar i; we shape the forward path starting at i+1.
            signal_bars.append(i)
            entry = c[i - 1]
            o[i] = entry
            h[i] = entry + half
            low[i] = entry - half
            c[i] = entry  # signal bar itself is calm

            e = o[i + 1] if False else c[i]  # entry price = open[i+1] (== c[i])
            # Forward 10 bars (i+1 .. i+10):
            path = [
                # (open,        low,        high,       close)
                (e,            e - mae,    e + 0.2,    e + 0.1),   # i+1: sets MAE
                (e + 0.1,      e + 0.0,    e + 1.0,    e + 1.0),   # i+2
                (e + 1.0,      e + 0.9,    e + mfe,    e + 1.8),   # i+3: sets MFE
                (e + 1.8,      e + 1.5,    e + 1.9,    e + 1.7),   # i+4
                (e + 1.7,      e + 1.5,    e + 1.9,    e + 1.6),   # i+5
                (e + 1.6,      e + 1.4,    e + 1.8,    e + 1.5),   # i+6
                (e + 1.5,      e + 1.4,    e + 1.7,    e + 1.5),   # i+7
                (e + 1.5,      e + 1.4,    e + 1.6,    e + 1.5),   # i+8
                (e + 1.5,      e + 1.4,    e + 1.6,    e + 1.5),   # i+9
                (e + 1.5,      e + 1.4,    e + 1.6,    e + 1.5),   # i+10
            ]
            for k, (po, pl, ph, pc) in enumerate(path, start=1):
                j = i + k
                o[j], low[j], h[j], c[j] = po, pl, ph, pc
            i = i + window + 1
            next_signal = i + (spacing - window - 1)
            continue

        # Calm bar.
        prev = c[i - 1]
        o[i] = prev
        c[i] = prev
        h[i] = prev + half
        low[i] = prev - half
        i += 1

    idx = pd.date_range("2004-01-01", periods=n, freq="h")
    ohlc = pd.DataFrame({"open": o, "high": h, "low": low, "close": c}, index=idx)
    sig = pd.Series(0, index=idx, dtype=int)
    sig.iloc[signal_bars] = 1
    return ohlc, sig


# --------------------------------------------------------------------------- #
# Real-data discovery for Tests 3 & 4                                          #
# --------------------------------------------------------------------------- #
def _load_real_xauusd_h1() -> pd.DataFrame:
    """Locate and load the 2004-2020 XAUUSD H1 dataset, or skip the test."""
    candidates = []
    env = os.environ.get("XAUUSD_H1_CSV")
    if env:
        candidates.append(Path(env))
    here = Path(__file__).resolve().parent
    candidates += [
        here.parent / "data" / "XAUUSD_H1.csv",
        here.parent / "data" / "XAUUSD_H1_2004_2020.csv",
    ]
    path = next((p for p in candidates if p.exists()), None)
    if path is None:
        pytest.skip(
            "Real XAUUSD H1 dataset not found. Set XAUUSD_H1_CSV or place a CSV "
            "at research/data/XAUUSD_H1.csv (columns: time,open,high,low,close)."
        )

    # MetaTrader exports are usually ';'-separated; fall back to ',' otherwise.
    df = pd.read_csv(path, sep=";")
    if df.shape[1] == 1:
        df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    time_col = next(
        (c for c in ("time", "date", "datetime", "timestamp") if c in df.columns),
        None,
    )
    if time_col is None:
        pytest.skip(f"{path} has no recognisable time column")
    df[time_col] = pd.to_datetime(df[time_col], format="mixed", dayfirst=False)
    df = df.set_index(time_col).sort_index()
    need = ["open", "high", "low", "close"]
    if any(c not in df.columns for c in need):
        pytest.skip(f"{path} missing OHLC columns; has {list(df.columns)}")
    df = df[(df.index >= "2004-01-01") & (df.index <= "2020-12-31")]
    return df[need]


# --------------------------------------------------------------------------- #
# Local signal generators (mirrors of the calibration strategies' ENTRIES).    #
# Re-implemented here so research/ never imports strategies/.                  #
# --------------------------------------------------------------------------- #
def _wma(series: pd.Series, period: int) -> pd.Series:
    weights = np.arange(1, period + 1, dtype=float)
    return series.rolling(period).apply(
        lambda x: np.dot(x, weights) / weights.sum(), raw=True
    )


def _hma(series: pd.Series, period: int) -> pd.Series:
    half = period // 2
    sqrtp = int(round(np.sqrt(period)))
    return _wma(2.0 * _wma(series, half) - _wma(series, period), sqrtp)


def _stochastic(high, low, close, k_period=14, d_period=3, smooth_k=3):
    ll = low.rolling(k_period).min()
    hh = high.rolling(k_period).max()
    rng = hh - ll
    raw_k = ((close - ll) / rng * 100).where(rng > 0, 50.0)
    k = raw_k.rolling(smooth_k).mean()
    d = k.rolling(d_period).mean()
    return k, d


def crest_n_keel_signal(ohlc: pd.DataFrame, hma_period: int = 55) -> pd.Series:
    """HMA direction + stochastic cross out of oversold/overbought.

    Long  : HMA rising, close above HMA, %K crosses up over %D from < 20.
    Short : HMA falling, close below HMA, %K crosses down under %D from > 80.
    """
    # Mirrors backend/.../crest_n_keel/strategy.py::_generate_signal exactly.
    h = _hma(ohlc["close"], hma_period)
    k, d = _stochastic(ohlc["high"], ohlc["low"], ohlc["close"])
    k_prev, d_prev, h_prev = k.shift(1), d.shift(1), h.shift(1)
    cross_up = (k_prev < d_prev) & (k > d) & (k_prev < 20.0)
    cross_dn = (k_prev > d_prev) & (k < d) & (k_prev > 80.0)
    long = (h > h_prev) & (ohlc["close"] > h) & cross_up
    short = (h < h_prev) & (ohlc["close"] < h) & cross_dn
    sig = pd.Series(0, index=ohlc.index, dtype=int)
    sig[long] = 1
    sig[short] = -1
    return sig


def donchian_breakout_signal(ohlc: pd.DataFrame, period: int = 50) -> pd.Series:
    """Positive control: long when close makes a new `period`-bar high.

    A trend-continuation entry *should* show forward asymmetry (MFE > MAE) at
    the signal itself — unlike a pullback entry. Used to prove the tool detects
    genuine edge on the same real XAUUSD series it judges crest_n_keel on.
    """
    hh = ohlc["close"].rolling(period).max()
    brk = (ohlc["close"] >= hh) & (ohlc["close"].shift(1) < hh.shift(1))
    sig = pd.Series(0, index=ohlc.index, dtype=int)
    sig[brk] = 1
    return sig


def _efficiency_ratio(close: pd.Series, period: int = 10) -> pd.Series:
    change = close.diff(period).abs()
    volatility = close.diff().abs().rolling(period).sum()
    return (change / volatility).where(volatility > 0, 0.0)


def ebb_n_flow_signal(
    ohlc: pd.DataFrame, bb_period: int = 20, bb_std: float = 2.0
) -> pd.Series:
    """Bollinger lower-band touch while the market is ranging (ER < 0.30).

    Long-only mean-reversion entry — the strategy that failed full backtesting
    (PF 0.76, SQN -2.36). Its signal edge should be visibly weak.
    """
    ma = ohlc["close"].rolling(bb_period).mean()
    sd = ohlc["close"].rolling(bb_period).std(ddof=0)
    lower = ma - bb_std * sd
    er = _efficiency_ratio(ohlc["close"], 10)
    long = (ohlc["low"] <= lower) & (er < 0.30)
    sig = pd.Series(0, index=ohlc.index, dtype=int)
    sig[long] = 1
    return sig


# --------------------------------------------------------------------------- #
# Test 1: random signal -> no edge                                             #
# --------------------------------------------------------------------------- #
def test_random_signal_has_no_edge():
    ohlc = make_gbm_ohlc(24_000, seed=7)
    signal = make_random_signal(ohlc, n_signals=1000, seed=11)

    report = signal_edge_report(
        signal, ohlc, forward_windows=[10, 30, 70], n_permutations=400, random_seed=42
    )

    for _, row in report.per_window.iterrows():
        assert 0.85 <= row["e_ratio"] <= 1.15, (
            f"window={row['window']} E-Ratio={row['e_ratio']:.3f} "
            "should be ~1.0 for random entries"
        )
    for _, row in report.permutation.iterrows():
        assert row["p_value"] > 0.05, (
            f"window={row['window']} p={row['p_value']:.3f}; random entries "
            "should not be significant"
        )


# --------------------------------------------------------------------------- #
# Test 2: synthetic known edge -> E-Ratio ~ 4.0                                #
# --------------------------------------------------------------------------- #
def test_synthetic_known_edge_ratio():
    ohlc, signal = build_edge_ohlc(n_signals=50)

    report = signal_edge_report(
        signal, ohlc, forward_windows=[10], n_permutations=100, random_seed=42
    )

    e_ratio = report.per_window.loc[
        report.per_window["window"] == 10, "e_ratio"
    ].iloc[0]
    assert 3.5 <= e_ratio <= 4.5, f"expected ~4.0, got {e_ratio:.3f}"

    # MFE and MAE are constructed as fixed absolute moves (+2.0 / -0.5), so the
    # per-signal ratio is exactly 4.0 regardless of the (varying) ATR level.
    ps = report.per_signal[report.per_signal["window"] == 10]
    assert np.allclose(ps["norm_mfe"] / ps["norm_mae"], 4.0, atol=1e-6)
    # ATR cancels: MFE/ATR is 2x MAE/ATR for every signal.
    assert np.allclose(ps["norm_mfe"], 4.0 * ps["norm_mae"], atol=1e-6)


# --------------------------------------------------------------------------- #
# Test 3: crest_n_keel calibration (needs real data)                           #
#                                                                              #
# Reframed from the original spec after investigation (see                     #
# research/calibration_results.md). The spec expected E-Ratio > 1.15 because   #
# crest_n_keel underpins a Sharpe~1.76 strategy. Clean measurement shows the   #
# HMA+Stochastic *entry* has E-Ratio ~0.9 (no standalone edge): the strategy's #
# profit lives in its asymmetric ATR exit, not the entry. The tool is correct  #
# — proven here by a positive control on the SAME data that DOES show edge.    #
# So this test now asserts the validated reality:                              #
#   (a) the tool detects real edge on real XAUUSD (Donchian control), and      #
#   (b) the crest_n_keel entry shows no significant standalone edge.           #
# --------------------------------------------------------------------------- #
def test_crest_n_keel_entry_and_positive_control():
    ohlc = _load_real_xauusd_h1()

    # (a) Positive control: the tool must detect edge where it genuinely exists.
    control = donchian_breakout_signal(ohlc, period=50)
    assert int(control.abs().sum()) >= 30
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        ctrl = signal_edge_report(
            control, ohlc, forward_windows=[10, 30, 70],
            n_permutations=1000, random_seed=42,
        )
    ctrl_best = ctrl.per_window["e_ratio"].max()
    ctrl_sig = ctrl.permutation[ctrl.permutation["p_value"] < 0.05]
    assert ctrl_best > 1.15, (
        f"positive control E-Ratio {ctrl_best:.3f} should exceed 1.15 — if it "
        "does not, the tool cannot see edge on real data and is untrustworthy"
    )
    assert not ctrl_sig.empty, "positive control should be significant (p < 0.05)"

    # (b) crest_n_keel entry: no significant standalone edge.
    signal = crest_n_keel_signal(ohlc)
    if int(signal.abs().sum()) < 30:
        pytest.skip("crest_n_keel produced too few signals on the provided data")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        report = signal_edge_report(
            signal, ohlc, forward_windows=[10, 30, 70],
            n_permutations=1000, random_seed=42,
        )
    best = report.per_window["e_ratio"].max()
    min_p = report.permutation["p_value"].min()
    assert (best < 1.15) and (min_p > 0.05), (
        f"crest_n_keel entry now looks edged (best E-Ratio {best:.3f}, "
        f"min p {min_p:.3f}). The calibration baseline has shifted — re-run the "
        "investigation in calibration_results.md before trusting downstream use."
    )


# --------------------------------------------------------------------------- #
# Test 4: ebb_n_flow calibration (needs real data)                             #
# --------------------------------------------------------------------------- #
def test_ebb_n_flow_weak_edge():
    ohlc = _load_real_xauusd_h1()
    signal = ebb_n_flow_signal(ohlc)
    if int(signal.abs().sum()) < 30:
        pytest.skip("ebb_n_flow produced too few signals on the provided data")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        report = signal_edge_report(
            signal, ohlc, forward_windows=[10, 30, 70],
            n_permutations=1000, random_seed=42,
        )

    best = report.per_window["e_ratio"].max()
    min_p = report.permutation["p_value"].min()
    # A genuinely weak entry: either no meaningful asymmetry, or not significant.
    assert (best < 1.10) or (min_p > 0.10), (
        f"ebb_n_flow looks strong (best E-Ratio {best:.3f}, min p {min_p:.3f}); "
        "if real, the entry has edge and the exits destroyed it — investigate."
    )


# --------------------------------------------------------------------------- #
# Test 5: determinism                                                          #
# --------------------------------------------------------------------------- #
def test_determinism():
    ohlc = make_gbm_ohlc(8_000, seed=3)
    signal = make_random_signal(ohlc, n_signals=300, seed=5)

    kwargs = dict(forward_windows=[10, 30], n_permutations=200, random_seed=99)
    r1 = signal_edge_report(signal, ohlc, **kwargs)
    r2 = signal_edge_report(signal, ohlc, **kwargs)

    pd.testing.assert_frame_equal(r1.per_window, r2.per_window)
    pd.testing.assert_frame_equal(r1.per_signal, r2.per_signal)
    pd.testing.assert_frame_equal(r1.permutation, r2.permutation)
    pd.testing.assert_frame_equal(r1.baseline, r2.baseline)
    assert r1.metadata == r2.metadata


# --------------------------------------------------------------------------- #
# Test 6: look-ahead probe                                                     #
# --------------------------------------------------------------------------- #
def test_no_look_ahead_under_truncation():
    windows = [10, 30, 70]
    trunc = 100
    ohlc = make_gbm_ohlc(8_000, seed=21)
    signal = make_random_signal(ohlc, n_signals=300, seed=23)

    # ATR[t] must not depend on future bars (PITFALL #1).
    atr_full = wilder_atr(ohlc["high"], ohlc["low"], ohlc["close"], 14)
    atr_trunc = wilder_atr(
        ohlc["high"].iloc[:-trunc],
        ohlc["low"].iloc[:-trunc],
        ohlc["close"].iloc[:-trunc],
        14,
    )
    common = ohlc.index[: -trunc]
    pd.testing.assert_series_equal(
        atr_full.reindex(common), atr_trunc, check_names=False
    )

    # Per-signal MFE/MAE must be identical for signals safely inside both runs.
    kwargs = dict(forward_windows=windows, n_permutations=1, random_seed=1)
    r_full = signal_edge_report(signal, ohlc, **kwargs)
    r_trunc = signal_edge_report(
        signal.iloc[:-trunc], ohlc.iloc[:-trunc], **kwargs
    )

    safe_cutoff = ohlc.index[len(ohlc) - trunc - max(windows) - 1]
    a = r_full.per_signal[r_full.per_signal["signal_time"] <= safe_cutoff]
    b = r_trunc.per_signal[r_trunc.per_signal["signal_time"] <= safe_cutoff]

    merged = a.merge(
        b, on=["signal_time", "window"], suffixes=("_full", "_trunc")
    )
    assert not merged.empty
    assert np.allclose(merged["norm_mfe_full"], merged["norm_mfe_trunc"])
    assert np.allclose(merged["norm_mae_full"], merged["norm_mae_trunc"])
    assert np.allclose(merged["fwd_return_full"], merged["fwd_return_trunc"])


# --------------------------------------------------------------------------- #
# Pitfall #4: tiny-sample warning                                              #
# --------------------------------------------------------------------------- #
def test_tiny_sample_emits_warning():
    ohlc = make_gbm_ohlc(4_000, seed=4)
    signal = make_random_signal(ohlc, n_signals=12, seed=6)  # < 30 -> unstable

    with pytest.warns(UserWarning, match="unstable"):
        signal_edge_report(
            signal, ohlc, forward_windows=[10], n_permutations=50, random_seed=42
        )


# --------------------------------------------------------------------------- #
# Pitfall #5: direction symmetry is exposed, not assumed                       #
# --------------------------------------------------------------------------- #
def test_metadata_exposes_direction_split():
    ohlc = make_gbm_ohlc(6_000, seed=8)
    rng = np.random.default_rng(8)
    sig = np.zeros(len(ohlc), dtype=int)
    longs = rng.choice(np.arange(50, 5900), size=120, replace=False)
    shorts = rng.choice(
        np.setdiff1d(np.arange(50, 5900), longs), size=80, replace=False
    )
    sig[longs] = 1
    sig[shorts] = -1
    signal = pd.Series(sig, index=ohlc.index)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        report = signal_edge_report(
            signal, ohlc, forward_windows=[10], n_permutations=50, random_seed=42
        )

    # One-sided sources of edge must be auditable from metadata.
    assert report.metadata["n_long_signals"] == 120
    assert report.metadata["n_short_signals"] == 80


# --------------------------------------------------------------------------- #
# Input validation                                                             #
# --------------------------------------------------------------------------- #
def test_rejects_misaligned_or_invalid_signal():
    ohlc = make_gbm_ohlc(500, seed=1)
    good = pd.Series(0, index=ohlc.index, dtype=int)

    with pytest.raises(ValueError, match="length"):
        signal_edge_report(good.iloc[:-1], ohlc)

    bad_values = good.copy()
    bad_values.iloc[5] = 2
    with pytest.raises(ValueError, match="only -1, 0"):
        signal_edge_report(bad_values, ohlc)

    missing_col = ohlc.drop(columns=["high"])
    with pytest.raises(ValueError, match="missing required columns"):
        signal_edge_report(good, missing_col)
