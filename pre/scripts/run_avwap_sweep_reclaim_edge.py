"""Orchestrator: run signal_edge over the avwap_sweep_reclaim_m15 signal.

Usage:
    research/.venv/bin/python -m research.scripts.run_avwap_sweep_reclaim_edge

DIAGNOSTIC role — this produces a reference E-Ratio for the entry. No verdict
is rendered against edge magnitude.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from research.pre.signal_edge import signal_edge_report
from research.pre.signals.avwap_sweep_reclaim_m15 import emit_signals


REPO_ROOT = Path(__file__).resolve().parents[3]
M15_CSV = REPO_ROOT / "research" / "data" / "XAUUSD_M15.csv"
ARTIFACTS_DIR = REPO_ROOT / "research" / "pre" / "artifacts"

START = "2018-01-01 00:00"
END = "2025-12-31 23:59"
PRIMARY_WINDOW = 16
SENSITIVITY_WINDOWS = [8, 32]
ATR_PERIOD = 14
PERMUTATIONS = 1000
RANDOM_SEED = 42


def load_m15() -> pd.DataFrame:
    df = pd.read_csv(
        M15_CSV,
        sep=";",
        header=0,
        names=["datetime", "open", "high", "low", "close", "volume"],
        parse_dates=["datetime"],
        date_format="%Y.%m.%d %H:%M",
    )
    df = df.set_index("datetime").sort_index()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df[["open", "high", "low", "close", "volume"]].astype(float)


def slice_period(df: pd.DataFrame) -> pd.DataFrame:
    start = pd.Timestamp(START, tz="UTC")
    end = pd.Timestamp(END, tz="UTC")
    return df.loc[(df.index >= start) & (df.index <= end)]


def to_pm_signal(triggers: pd.DataFrame, ohlc_index: pd.DatetimeIndex) -> pd.Series:
    s = pd.Series(0, index=ohlc_index, dtype=np.int64)
    mask = triggers["signal"].to_numpy()
    s.iloc[np.where(mask)[0]] = triggers["direction"].to_numpy()[mask]
    return s


def _er(sub: pd.DataFrame) -> float:
    if len(sub) == 0:
        return float("nan")
    mae = float(sub["norm_mae"].mean())
    if mae <= 1e-12:
        return float("nan")
    return float(sub["norm_mfe"].mean()) / mae


def run_window(signal: pd.Series, ohlc: pd.DataFrame, window: int,
               triggers: pd.DataFrame | None = None) -> dict:
    report = signal_edge_report(
        signal=signal,
        ohlc=ohlc[["open", "high", "low", "close"]],
        forward_windows=[window],
        atr_period=ATR_PERIOD,
        n_permutations=PERMUTATIONS,
        random_seed=RANDOM_SEED,
    )
    pw = report.per_window.iloc[0].to_dict()
    perm = report.permutation.iloc[0].to_dict()
    base = report.baseline.iloc[0].to_dict()

    ps = report.per_signal
    ps_w = ps[ps["window"] == window]
    e_long = _er(ps_w[ps_w["direction"] > 0])
    e_short = _er(ps_w[ps_w["direction"] < 0])

    out = {
        "window": window,
        "e_ratio_combined": pw["e_ratio"],
        "e_ratio_long": e_long,
        "e_ratio_short": e_short,
        "n_signals_eligible": int(pw["n_signals"]),
        "n_long_eligible": int((ps_w["direction"] > 0).sum()),
        "n_short_eligible": int((ps_w["direction"] < 0).sum()),
        "mean_norm_mfe": pw["mean_norm_mfe"],
        "mean_norm_mae": pw["mean_norm_mae"],
        "mean_fwd_return": pw["mean_fwd_return"],
        "hit_rate": pw["hit_rate"],
        "p_value": perm["p_value"],
        "null_mean": perm["e_ratio_null_mean"],
        "null_p05": perm["e_ratio_null_p05"],
        "null_p95": perm["e_ratio_null_p95"],
        "baseline_e_ratio": base["e_ratio"],
    }

    # Per-level-type decomposition (only for primary window).
    if triggers is not None and window == PRIMARY_WINDOW:
        # Map per_signal.signal_time to triggering_level via the triggers frame.
        level_at_t = triggers.set_index(triggers.index)["triggering_level"]
        ps_w = ps_w.copy()
        ps_w["level"] = level_at_t.reindex(ps_w["signal_time"]).to_numpy()
        out["e_ratio_avwap"] = _er(ps_w[ps_w["level"] == "avwap"])
        out["e_ratio_poc"] = _er(ps_w[ps_w["level"] == "poc"])
        out["e_ratio_hvn"] = _er(ps_w[ps_w["level"] == "hvn"])
        out["n_avwap"] = int((ps_w["level"] == "avwap").sum())
        out["n_poc"] = int((ps_w["level"] == "poc").sum())
        out["n_hvn"] = int((ps_w["level"] == "hvn").sum())
    return out


def main() -> Path:
    print(f"Loading M15 from {M15_CSV} ...")
    m15 = slice_period(load_m15())
    print(f"  bars in period: {len(m15)}  [{m15.index[0]} .. {m15.index[-1]}]")

    print("Emitting signals ...")
    triggers = emit_signals(m15)
    n_total = int(triggers["signal"].sum())
    n_long = int(((triggers["signal"]) & (triggers["direction"] == 1)).sum())
    n_short = int(((triggers["signal"]) & (triggers["direction"] == -1)).sum())
    n_avwap = int(((triggers["signal"]) & (triggers["triggering_level"] == "avwap")).sum())
    n_poc = int(((triggers["signal"]) & (triggers["triggering_level"] == "poc")).sum())
    n_hvn = int(((triggers["signal"]) & (triggers["triggering_level"] == "hvn")).sum())
    print(f"  triggers: total={n_total} long={n_long} short={n_short}")
    print(f"  by level: avwap={n_avwap} poc={n_poc} hvn={n_hvn}")

    signal = to_pm_signal(triggers, m15.index)

    print(f"Running signal_edge primary window={PRIMARY_WINDOW} ...")
    primary = run_window(signal, m15, PRIMARY_WINDOW, triggers=triggers)
    print(f"  E-Ratio={primary['e_ratio_combined']:.4f}  p={primary['p_value']:.4f}  "
          f"baseline={primary['baseline_e_ratio']:.4f}")

    sensitivity = {}
    for w in SENSITIVITY_WINDOWS:
        print(f"Running sensitivity window={w} ...")
        sensitivity[w] = run_window(signal, m15, w)
        print(f"  E-Ratio={sensitivity[w]['e_ratio_combined']:.4f}  p={sensitivity[w]['p_value']:.4f}")

    signal_hash = hashlib.sha256(signal.to_csv().encode("utf-8")).hexdigest()[:16]

    artifact = {
        "hypothesis_id": "avwap_sweep_reclaim_m15",
        "period": {"start": str(m15.index[0]), "end": str(m15.index[-1]), "n_bars": int(len(m15))},
        "params": {
            "h1_hma_period": 50,
            "vp_lookback_bars": 120,
            "vp_bin_width_pct": 0.00025,
            "sweep_threshold_atr_mult": 0.2,
            "stoch_k": 14, "stoch_d": 3, "stoch_smooth": 3,
            "atr_period": ATR_PERIOD,
            "forward_window_primary": PRIMARY_WINDOW,
            "forward_windows_sensitivity": SENSITIVITY_WINDOWS,
            "permutations": PERMUTATIONS,
            "random_seed": RANDOM_SEED,
        },
        "trigger_count_total": n_total,
        "trigger_count_long": n_long,
        "trigger_count_short": n_short,
        "trigger_count_avwap": n_avwap,
        "trigger_count_poc": n_poc,
        "trigger_count_hvn": n_hvn,
        "signal_hash": signal_hash,
        "primary": primary,
        "sensitivity": {str(w): r for w, r in sensitivity.items()},
    }

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = ARTIFACTS_DIR / f"avwap_sweep_reclaim_signal_edge_{ts}.json"
    out_path.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
    print(f"Wrote artifact: {out_path}")
    return out_path


if __name__ == "__main__":
    main()
