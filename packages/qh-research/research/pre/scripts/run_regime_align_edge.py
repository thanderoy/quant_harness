"""Driver: E-Ratio HARD_GATE for regime_align_h1 (seq=37), prediction P1 / kill K1.

Runs the frozen P1_entry_edge test:
    E-Ratio > 1.15 AND p < 0.05 at H in {20, 50, 100}, N = 1000 permutations,
    measured against the **bias-eligible** permutation null.

Two nulls are run and reported:

  decisive     entries drawn only from bars with trend_location >= 0, so gold's
               secular uptrend is baked into the null. This is what P1/K1 are
               judged on.
  diagnostic   entries drawn from all finite-ATR bars. Reported only to
               quantify P2 — how much apparent edge is drift rather than regime.

Usage:
    python -m research.pre.scripts.run_regime_align_edge
    python -m research.pre.scripts.run_regime_align_edge --h1 research/data/XAUUSD_H1.csv

Writes research/pre/artifacts/regime_align_h1_seq37_p1_<UTC>.json and prints a
verdict. Exits nonzero on any non-PASS verdict.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from research.pre.regime import RegimeParams, regime_frame
from research.pre.signal_edge import signal_edge_report

HYPOTHESIS_ID = "regime_align_h1"
SEQ = 37
HORIZONS = (20, 50, 100)
E_RATIO_THRESHOLD = 1.15       # frozen pre-reg (CLAUDE.md HARD_GATE bar)
P_VALUE_THRESHOLD = 0.05       # frozen pre-reg
N_PERMUTATIONS = 1000
ATR_PERIOD = 14
RANDOM_SEED = 20260726         # frozen — do not vary on re-runs (trial inflation)

# Frozen thresholds (mirror regime_align_h1.FROZEN_PARAMS).
ER_THRESHOLD = 0.30
VOL_THRESHOLD = 1.10
BIAS_THRESHOLD = 0.0

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_H1 = REPO_ROOT / "research" / "data" / "XAUUSD_H1.csv"
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


def build_signal(h1: pd.DataFrame) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (signal, aligned_mask, bias_eligible_mask).

    ``signal`` is +1 on the bar where the three-way alignment first becomes
    true (entry at next open, enforced downstream by signal_edge_report), 0
    elsewhere. No look-ahead: every regime column at bar t depends on bars
    [0, t] only, and the transition uses only t and t-1.
    """
    rf = regime_frame(h1, RegimeParams())

    trend = rf["trend_quality"] >= ER_THRESHOLD
    vol = rf["vol_regime"] >= VOL_THRESHOLD
    bias = rf["trend_location"] >= BIAS_THRESHOLD
    ready = rf[["trend_quality", "vol_regime", "trend_location"]].notna().all(axis=1)

    aligned = ready & trend & vol & bias
    entry = aligned & ~aligned.shift(1, fill_value=False)

    signal = pd.Series(0, index=h1.index, dtype=int)
    signal[entry] = 1
    return signal, aligned, (ready & bias)


def _horizon_results(report, horizons) -> list[HorizonResult]:
    pw = report.per_window.set_index("window")
    perm = report.permutation.set_index("window")
    base = report.baseline.set_index("window")
    out: list[HorizonResult] = []
    for h in horizons:
        e_ratio = float(pw.loc[h, "e_ratio"])
        p_value = float(perm.loc[h, "p_value"])
        out.append(
            HorizonResult(
                horizon=h,
                n_signals=int(pw.loc[h, "n_signals"]),
                e_ratio=e_ratio,
                p_value=p_value,
                null_mean=float(perm.loc[h, "e_ratio_null_mean"]),
                null_p95=float(perm.loc[h, "e_ratio_null_p95"]),
                baseline_e_ratio=float(base.loc[h, "e_ratio"]),
                passes_e_ratio=bool(e_ratio > E_RATIO_THRESHOLD),
                passes_p_value=bool(p_value < P_VALUE_THRESHOLD),
            )
        )
    return out


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except (subprocess.CalledProcessError, OSError):
        return "unknown"


def run(h1_path: Path = DEFAULT_H1, output_dir: Path = ARTIFACT_DIR) -> dict:
    h1 = load_ohlcv(h1_path)
    signal, aligned, bias_eligible = build_signal(h1)

    n_entries = int((signal != 0).sum())
    if n_entries == 0:
        raise ValueError("no entry signals generated — check thresholds")

    decisive = signal_edge_report(
        signal=signal,
        ohlc=h1,
        forward_windows=HORIZONS,
        atr_period=ATR_PERIOD,
        n_permutations=N_PERMUTATIONS,
        random_seed=RANDOM_SEED,
        eligible_pool=bias_eligible,
    )
    diagnostic = signal_edge_report(
        signal=signal,
        ohlc=h1,
        forward_windows=HORIZONS,
        atr_period=ATR_PERIOD,
        n_permutations=N_PERMUTATIONS,
        random_seed=RANDOM_SEED,
        eligible_pool=None,
    )

    dec_results = _horizon_results(decisive, HORIZONS)
    dia_results = _horizon_results(diagnostic, HORIZONS)

    passes = all(r.passes_e_ratio and r.passes_p_value for r in dec_results)
    # K2: apparent edge under the loose null that vanishes under the strict one.
    drift_only = (not passes) and all(
        r.e_ratio > E_RATIO_THRESHOLD for r in dia_results
    )

    if passes:
        verdict = "PASS"
    elif drift_only:
        verdict = "SHELVE_K2_DRIFT_ONLY"
    else:
        verdict = "SHELVE_K1"

    payload = {
        "hypothesis_id": HYPOTHESIS_ID,
        "seq": SEQ,
        "prediction": "P1_entry_edge",
        "run_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "data": {
            "path": str(h1_path.relative_to(REPO_ROOT)),
            "bars": int(len(h1)),
            "start": h1.index[0].isoformat(),
            "end": h1.index[-1].isoformat(),
        },
        "frozen_test": {
            "horizons": list(HORIZONS),
            "e_ratio_threshold": E_RATIO_THRESHOLD,
            "p_value_threshold": P_VALUE_THRESHOLD,
            "n_permutations": N_PERMUTATIONS,
            "atr_period": ATR_PERIOD,
            "random_seed": RANDOM_SEED,
        },
        "signal": {
            "n_entries": n_entries,
            "aligned_bars": int(aligned.sum()),
            "aligned_pct": round(float(aligned.mean()) * 100, 3),
            "bias_eligible_bars": int(bias_eligible.sum()),
        },
        "decisive_null_bias_eligible": [asdict(r) for r in dec_results],
        "diagnostic_null_unconditional": [asdict(r) for r in dia_results],
        "verdict": verdict,
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = output_dir / f"{HYPOTHESIS_ID}_seq{SEQ}_p1_{stamp}.json"
    out_path.write_text(json.dumps(payload, indent=2))
    payload["_artifact"] = str(out_path)
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--h1", type=Path, default=DEFAULT_H1)
    args = ap.parse_args()

    p = run(args.h1)

    print(f"{HYPOTHESIS_ID} seq={SEQ}  P1_entry_edge")
    print(f"  data      {p['data']['bars']:,} bars  "
          f"{p['data']['start'][:10]} -> {p['data']['end'][:10]}")
    print(f"  entries   {p['signal']['n_entries']:,}   "
          f"aligned {p['signal']['aligned_pct']}% of bars")
    print(f"  gate      E-Ratio > {E_RATIO_THRESHOLD} AND p < {P_VALUE_THRESHOLD}")
    print()
    for label, key in (
        ("DECISIVE  (bias-eligible null)", "decisive_null_bias_eligible"),
        ("diagnostic (unconditional null)", "diagnostic_null_unconditional"),
    ):
        print(f"  {label}")
        print(f"    {'H':>5} {'n':>7} {'E-Ratio':>9} {'p':>8} "
              f"{'null_mu':>8} {'base':>7}  gate")
        for r in p[key]:
            ok = "PASS" if (r["passes_e_ratio"] and r["passes_p_value"]) else "fail"
            print(f"    {r['horizon']:>5} {r['n_signals']:>7,} "
                  f"{r['e_ratio']:>9.3f} {r['p_value']:>8.3f} "
                  f"{r['null_mean']:>8.3f} {r['baseline_e_ratio']:>7.3f}  {ok}")
        print()
    print(f"  VERDICT   {p['verdict']}")
    print(f"  artifact  {Path(p['_artifact']).name}")
    return 0 if p["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
