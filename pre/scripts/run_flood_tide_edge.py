"""Driver: E-Ratio HARD_GATE for flood_tide_h1 (seq=31), prediction P1 / kill K1.

Runs the frozen P1_entry_edge test:
    E-Ratio > 1.10 AND p < 0.05 at H in {20, 50, 100}, N = 1000 permutations.

The E-Ratio, permutation null and random baseline are computed by the vetted
``research.pre.signal_edge.signal_edge_report`` — the module the frozen
pre-registration names as the P1 test. The one flood_tide-specific twist is the
null universe: random entries are drawn only from **regime-eligible** bars
(``regime_ok == True``) via ``signal_edge``'s ``eligible_pool`` parameter, so the
H4-EMA + Efficiency-Ratio filter's directional drift is baked into the null
instead of leaking into — and inflating — the breakout's measured E-Ratio. This
is what makes P1 a genuinely hard gate for a HARD_GATE entry.

Usage:
    research/.venv/bin/python -m research.pre.scripts.run_flood_tide_edge
    research/.venv/bin/python -m research.pre.scripts.run_flood_tide_edge \
        --h1 research/data/XAUUSD_H1.csv --h4 research/data/XAUUSD_H4.csv

Writes research/pre/artifacts/flood_tide_h1_seq31_p1_<UTC>.json and prints a
verdict. Exits nonzero on any non-PASS verdict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from research.pre.signal_edge import signal_edge_report
from research.pre.signals.flood_tide import FloodTideParams, generate_signals


HYPOTHESIS_ID = "flood_tide_h1"
SEQ = 31
HORIZONS = (20, 50, 100)
E_RATIO_THRESHOLD = 1.10       # P1 threshold (frozen pre-reg)
P_VALUE_THRESHOLD = 0.05       # P1 threshold (frozen pre-reg)
N_PERMUTATIONS = 1000          # >= 500 per pre-reg; 1000 for tighter p resolution
ATR_PERIOD = 14                # house E-Ratio normalisation window
RANDOM_SEED = 20260706         # frozen — do not vary on re-runs (trial inflation)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_H1 = REPO_ROOT / "research" / "data" / "XAUUSD_H1.csv"
DEFAULT_H4 = REPO_ROOT / "research" / "data" / "XAUUSD_H4.csv"
ARTIFACT_DIR = REPO_ROOT / "research" / "pre" / "artifacts"


@dataclass
class HorizonResult:
    horizon: int
    n_signals: int
    e_ratio: float
    p_value: float
    null_mean: float
    null_p95: float
    baseline_e_ratio: float
    passes_e_ratio: bool
    passes_p_value: bool


# --------------------------------------------------------------------------- #
# Data                                                                         #
# --------------------------------------------------------------------------- #
def load_ohlcv(path: Path) -> pd.DataFrame:
    """Load a house ``;``-separated OHLCV CSV (Date;Open;High;Low;Close;Volume)."""
    df = pd.read_csv(
        path,
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


# --------------------------------------------------------------------------- #
# Runner                                                                       #
# --------------------------------------------------------------------------- #
def run(
    h1_path: Path,
    h4_path: Path,
    params: FloodTideParams = FloodTideParams(),
    hypothesis_id: str = HYPOTHESIS_ID,
    seq: int = SEQ,
    output_dir: Path = ARTIFACT_DIR,
) -> dict:
    h1 = load_ohlcv(h1_path)
    h4 = load_ohlcv(h4_path)

    sig = generate_signals(h1, h4, params)

    # +1 long / 0 flat signal for signal_edge (long-only mechanism).
    signal = pd.Series(0, index=h1.index, dtype=np.int64)
    signal[sig["entry_signal"].to_numpy()] = 1

    # Null universe: regime-eligible bars with a populated breakout lookback.
    eligible_mask = (sig["regime_ok"] & sig["upper_entry"].notna()).to_numpy()

    n_entries = int(sig["entry_signal"].sum())
    n_eligible = int(eligible_mask.sum())

    report = signal_edge_report(
        signal=signal,
        ohlc=h1,
        forward_windows=list(HORIZONS),
        atr_period=ATR_PERIOD,
        n_permutations=N_PERMUTATIONS,
        random_seed=RANDOM_SEED,
        eligible_pool=eligible_mask,
    )

    results = _collect_results(report)
    verdict = _verdict(results)
    artifact = _build_artifact(
        hypothesis_id, seq, h1_path, h4_path, params, results, verdict,
        n_entries, n_eligible, report.metadata,
    )
    artifact_path = _write_artifact(artifact, hypothesis_id, seq, output_dir)

    _print_report(hypothesis_id, seq, params, h1, n_entries, n_eligible,
                  results, verdict, artifact_path)
    return {"verdict": verdict, "artifact_path": str(artifact_path), "results": results}


def _collect_results(report) -> list[HorizonResult]:
    pw = report.per_window.set_index("window")
    perm = report.permutation.set_index("window")
    base = report.baseline.set_index("window")
    out: list[HorizonResult] = []
    for h in HORIZONS:
        e_ratio = float(pw.loc[h, "e_ratio"])
        p_value = float(perm.loc[h, "p_value"])
        out.append(HorizonResult(
            horizon=h,
            n_signals=int(pw.loc[h, "n_signals"]),
            e_ratio=e_ratio,
            p_value=p_value,
            null_mean=float(perm.loc[h, "e_ratio_null_mean"]),
            null_p95=float(perm.loc[h, "e_ratio_null_p95"]),
            baseline_e_ratio=float(base.loc[h, "e_ratio"]),
            passes_e_ratio=bool(e_ratio > E_RATIO_THRESHOLD),
            passes_p_value=bool(p_value < P_VALUE_THRESHOLD),
        ))
    return out


def _verdict(results: list[HorizonResult]) -> str:
    """Map results onto the frozen kill criteria.

    K1 (TERMINAL_KILL): E-Ratio <= 1.0 (or undefined) at ANY horizon.
    K2 (SHELVE):        E-Ratio > 1.0 everywhere but p >= 0.05 at some horizon.
    PASS:               E-Ratio > 1.10 AND p < 0.05 at ALL horizons.
    Otherwise:          marginal E-Ratio in (1.0, 1.10] — shelve.
    """
    if any(np.isnan(r.e_ratio) or r.e_ratio <= 1.0 for r in results):
        return "TERMINAL_KILL"
    if all(r.passes_e_ratio and r.passes_p_value for r in results):
        return "PASS_PROCEED_TO_WALK_FORWARD"
    if any(not r.passes_p_value for r in results):
        return "SHELVE_INSUFFICIENT_SIGNIFICANCE"
    return "SHELVE_MARGINAL_E_RATIO"


def _build_artifact(
    hypothesis_id: str,
    seq: int,
    h1_path: Path,
    h4_path: Path,
    params: FloodTideParams,
    results: list[HorizonResult],
    verdict: str,
    n_entries: int,
    n_eligible: int,
    edge_metadata: dict,
) -> dict:
    return {
        "hypothesis_id": hypothesis_id,
        "seq": seq,
        "test": "P1_entry_edge",
        "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "thresholds": {
            "e_ratio_min": E_RATIO_THRESHOLD,
            "p_value_max": P_VALUE_THRESHOLD,
            "n_permutations_min": 500,
            "k1_terminal_kill_e_ratio": 1.0,
        },
        "config": {
            "n_permutations": N_PERMUTATIONS,
            "atr_period": ATR_PERIOD,
            "random_seed": RANDOM_SEED,
            "horizons": list(HORIZONS),
            "engine": "research.pre.signal_edge.signal_edge_report",
            "baseline": "regime_filtered_random_entries (eligible_pool=regime_ok)",
            "entry_reference": "open[t+1] (house signal_edge no-look-ahead convention)",
        },
        "frozen_params": asdict(params),
        "inputs": {
            "h1_path": str(h1_path),
            "h1_sha256": _file_sha256(h1_path),
            "h4_path": str(h4_path),
            "h4_sha256": _file_sha256(h4_path),
        },
        "entry_universe": {
            "n_observed_entries": n_entries,
            "n_regime_eligible_bars": n_eligible,
        },
        "results_by_horizon": [asdict(r) for r in results],
        "edge_report_metadata": edge_metadata,
        "code_provenance": {
            "signal_module": "research.pre.signals.flood_tide",
            "driver_module": "research.pre.scripts.run_flood_tide_edge",
            "git_sha": _git_sha(),
            "git_dirty": _git_dirty(),
        },
    }


def _write_artifact(artifact: dict, hypothesis_id: str, seq: int, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = output_dir / f"{hypothesis_id}_seq{seq}_p1_{ts}.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(artifact, indent=2, sort_keys=True, default=str))
    tmp.replace(path)   # atomic
    return path


def _print_report(
    hypothesis_id: str,
    seq: int,
    params: FloodTideParams,
    h1: pd.DataFrame,
    n_entries: int,
    n_eligible: int,
    results: list[HorizonResult],
    verdict: str,
    path: Path,
) -> None:
    print(f"\n=== {hypothesis_id} seq={seq} :: P1_entry_edge (HARD_GATE) ===")
    print(f"entry_len : {params.entry_len}  (Donchian breakout channel)")
    print(f"data      : {h1.index[0]} .. {h1.index[-1]}  ({len(h1)} H1 bars)")
    print(f"entries   : {n_entries}   regime-eligible bars: {n_eligible}")
    print(f"null       : regime-filtered random entries; seed={RANDOM_SEED}\n")
    print(f"{'H':>4}  {'N':>5}  {'E-Ratio':>8}  {'p':>7}  "
          f"{'null_mean':>9}  {'null_p95':>8}  {'baseline':>8}  E>1.10  p<.05")
    for r in results:
        print(
            f"{r.horizon:>4}  {r.n_signals:>5}  {r.e_ratio:>8.3f}  "
            f"{r.p_value:>7.4f}  {r.null_mean:>9.3f}  {r.null_p95:>8.3f}  "
            f"{r.baseline_e_ratio:>8.3f}  "
            f"{'YES' if r.passes_e_ratio else 'no ':>6}  "
            f"{'YES' if r.passes_p_value else 'no'}"
        )
    print(f"\nVERDICT  : {verdict}")
    print(f"Artifact : {path}")
    if verdict.startswith("PASS"):
        print("Next     : record UPDATE on seq=31 with this artifact as "
              "reproducibility_artifact_path, then btpy_runner walk-forward (P2).")
    print()


# --------------------------------------------------------------------------- #
# Provenance helpers                                                           #
# --------------------------------------------------------------------------- #
def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, cwd=REPO_ROOT
        ).strip()
    except Exception:
        return "unknown"


def _git_dirty() -> bool:
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain"], text=True, cwd=REPO_ROOT
        )
        return bool(out.strip())
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--h1", type=Path, default=DEFAULT_H1, help="XAUUSD H1 OHLCV CSV")
    parser.add_argument("--h4", type=Path, default=DEFAULT_H4, help="XAUUSD H4 OHLCV CSV")
    parser.add_argument("--entry-len", type=int, default=FloodTideParams().entry_len,
                        help="Donchian breakout channel length (Iteration 2: 20)")
    parser.add_argument("--hypothesis-id", default=HYPOTHESIS_ID)
    parser.add_argument("--seq", type=int, default=SEQ)
    parser.add_argument("--output-dir", type=Path, default=ARTIFACT_DIR)
    args = parser.parse_args()

    params = FloodTideParams(entry_len=args.entry_len)
    result = run(args.h1, args.h4, params, args.hypothesis_id, args.seq, args.output_dir)
    return 0 if result["verdict"].startswith("PASS") else 1


if __name__ == "__main__":
    sys.exit(main())
