"""Orchestrator: run signal_edge over the zerolag_chandelier signal.

Usage:
    research/.venv/bin/python -m research.scripts.run_zlch_edge

Output:
    research/pre/artifacts/zlch_signal_edge_<UTC_timestamp>.json
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from research.pre.signal_edge import signal_edge_report
from research.pre.signals.zerolag_chandelier import emit_signals


REPO_ROOT = Path(__file__).resolve().parents[3]
M15_CSV = REPO_ROOT / "research" / "data" / "XAUUSD_M15.csv"
ARTIFACTS_DIR = REPO_ROOT / "research" / "pre" / "artifacts"

START = "2018-01-01 00:00"
END = "2025-12-31 23:59"
PRIMARY_WINDOW = 32
SENSITIVITY_WINDOWS = [16, 64]
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
    return df[["open", "high", "low", "close"]].astype(float)


def slice_period(df: pd.DataFrame) -> pd.DataFrame:
    start = pd.Timestamp(START, tz="UTC")
    end = pd.Timestamp(END, tz="UTC")
    return df.loc[(df.index >= start) & (df.index <= end)]


def to_pm_signal(triggers: pd.DataFrame, ohlc_index: pd.DatetimeIndex) -> pd.Series:
    """Convert emit_signals output to the +1/-1/0 series signal_edge expects."""
    s = pd.Series(0, index=ohlc_index, dtype=np.int64)
    mask = triggers["signal"].to_numpy()
    s.iloc[np.where(mask)[0]] = triggers["direction"].to_numpy()[mask]
    return s


def run_window(signal: pd.Series, ohlc: pd.DataFrame, window: int) -> dict:
    report = signal_edge_report(
        signal=signal,
        ohlc=ohlc,
        forward_windows=[window],
        atr_period=ATR_PERIOD,
        n_permutations=PERMUTATIONS,
        random_seed=RANDOM_SEED,
    )
    pw = report.per_window.iloc[0].to_dict()
    perm = report.permutation.iloc[0].to_dict()
    base = report.baseline.iloc[0].to_dict()

    # Long-only / short-only E-Ratios at this window
    ps = report.per_signal
    ps_w = ps[ps["window"] == window]
    def _er(sub: pd.DataFrame) -> float:
        if len(sub) == 0:
            return float("nan")
        mae_mean = float(sub["norm_mae"].mean())
        if mae_mean <= 1e-12:
            return float("nan")
        return float(sub["norm_mfe"].mean()) / mae_mean

    e_long = _er(ps_w[ps_w["direction"] > 0])
    e_short = _er(ps_w[ps_w["direction"] < 0])
    n_long = int((ps_w["direction"] > 0).sum())
    n_short = int((ps_w["direction"] < 0).sum())

    return {
        "window": window,
        "e_ratio_combined": pw["e_ratio"],
        "e_ratio_long": e_long,
        "e_ratio_short": e_short,
        "n_signals_eligible": int(pw["n_signals"]),
        "n_long_eligible": n_long,
        "n_short_eligible": n_short,
        "mean_norm_mfe": pw["mean_norm_mfe"],
        "mean_norm_mae": pw["mean_norm_mae"],
        "mean_fwd_return": pw["mean_fwd_return"],
        "hit_rate": pw["hit_rate"],
        "p_value": perm["p_value"],
        "null_mean": perm["e_ratio_null_mean"],
        "null_p05": perm["e_ratio_null_p05"],
        "null_p95": perm["e_ratio_null_p95"],
        "baseline_e_ratio": base["e_ratio"],
        "metadata": report.metadata,
    }


def main() -> Path:
    print(f"Loading M15 from {M15_CSV} ...")
    m15 = slice_period(load_m15())
    print(f"  bars in period: {len(m15)}  [{m15.index[0]} .. {m15.index[-1]}]")

    print("Emitting signals ...")
    triggers = emit_signals(m15)
    n_trig_total = int(triggers["signal"].sum())
    n_trig_long = int(((triggers["signal"]) & (triggers["direction"] == 1)).sum())
    n_trig_short = int(((triggers["signal"]) & (triggers["direction"] == -1)).sum())
    print(f"  triggers: total={n_trig_total} long={n_trig_long} short={n_trig_short}")

    signal = to_pm_signal(triggers, m15.index)

    print(f"Running signal_edge primary window={PRIMARY_WINDOW} ...")
    primary = run_window(signal, m15, PRIMARY_WINDOW)
    print(f"  E-Ratio={primary['e_ratio_combined']:.4f}  p={primary['p_value']:.4f}  "
          f"baseline={primary['baseline_e_ratio']:.4f}")

    sensitivity = {}
    for w in SENSITIVITY_WINDOWS:
        print(f"Running sensitivity window={w} ...")
        sensitivity[w] = run_window(signal, m15, w)
        print(f"  E-Ratio={sensitivity[w]['e_ratio_combined']:.4f}  "
              f"p={sensitivity[w]['p_value']:.4f}")

    # Compute signal hash from the signal Series alone (deterministic and lighter
    # than the full ohlc hash baked into metadata).
    import hashlib
    signal_hash = hashlib.sha256(signal.to_csv().encode("utf-8")).hexdigest()[:16]

    artifact = {
        "hypothesis_id": "zerolag_chandelier",
        "period": {"start": str(m15.index[0]), "end": str(m15.index[-1]), "n_bars": int(len(m15))},
        "params": {
            "chandelier_atr_period": 14,
            "chandelier_atr_mult": 2.5,
            "h4_zlsma_length": 50,
            "forward_window_primary": PRIMARY_WINDOW,
            "forward_windows_sensitivity": SENSITIVITY_WINDOWS,
            "atr_period": ATR_PERIOD,
            "permutations": PERMUTATIONS,
            "random_seed": RANDOM_SEED,
        },
        "trigger_count_total": n_trig_total,
        "trigger_count_long": n_trig_long,
        "trigger_count_short": n_trig_short,
        "signal_hash": signal_hash,
        "primary": primary,
        "sensitivity": {str(w): r for w, r in sensitivity.items()},
    }

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = ARTIFACTS_DIR / f"zlch_signal_edge_{ts}.json"
    out_path.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
    print(f"Wrote artifact: {out_path}")
    return out_path


if __name__ == "__main__":
    main()
