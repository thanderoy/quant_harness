"""examples/run_cnk_sweep_oos.py — OOS walk-forward for the cnk sweep leaders.

Runs the two MOMENTUM long-only leaders that came out of the seq=44 sweep
(research/data/crest_n_keel) through the harness walk-forward, on their own
timeframes, with the sweep's own settings.

WHAT THIS TEST DOES AND DOES NOT SHOW
-------------------------------------
`run_walk_forward` applies FIXED parameters to every fold; it does not
re-optimise inside the training window. The parameters here were selected from
a sweep over the FULL history, which includes every OOS fold below. So this is
NOT a clean out-of-sample test of the selection procedure -- the selection saw
this data.

What it does test is TEMPORAL STABILITY: whether the config's full-history
Sharpe is spread across sub-periods or carried by one regime. That is worth
knowing and is a necessary condition for promotion, but it cannot rescue the
DSR failure and must not be reported as "OOS validation" without this caveat.

Settings match the sweep so the comparison is like-for-like:
  * 24/7 (session_hours=None)
  * max_drawdown_halt disabled -- an absorbing barrier truncates a config's
    record at a path-dependent point and makes folds incomparable
  * min_atr_for_signal = 0.0, risk_pct = 0.02

Usage:
    python -m examples.run_cnk_sweep_oos
    python -m examples.run_cnk_sweep_oos --tf H4
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from research.datasets import load_bars, PepperstoneXAUUSDCostModel
from research.engines import run_walk_forward, PEPPERSTONE_XAUUSD_KNOWN_GAPS
from research.engines.strategies.cnk_momentum import CrestNKeelMomentum
from research.metrics import dsr
from research.reports import evaluate, Thresholds

DATA_ROOT = Path("packages/qh-research/research/data")

# Frozen from the seq=44 sweep leaders -- declared before this script was run.
CONFIGS = {
    "H4": {"hma_period": 13, "atr_period": 7, "trail_atr_mult": 1.5,
           "min_atr_for_signal": 0.0, "risk_pct": 0.02,
           "max_drawdown_halt": 1.0},
    "H1": {"hma_period": 55, "atr_period": 14, "trail_atr_mult": 3.0,
           "min_atr_for_signal": 0.0, "risk_pct": 0.02,
           "max_drawdown_halt": 1.0},
}
# In-sample sweep figures, for the IS/OOS gap.
SWEEP_IS = {"H4": {"sharpe": 0.9850, "n_trades": 2141},
            "H1": {"sharpe": 0.9711, "n_trades": 2497}}

# Windows scale with the timeframe: H4 has ~1/4 the bars per day of H1, so a
# fold short enough to be meaningful on H1 is too thin on H4.
WINDOWS = {"H4": ("1825D", "365D", "365D"), "H1": ("1460D", "365D", "365D")}


def _dsr_for(wf, num_trials: int) -> dict | None:
    oos = wf.oos_return_pct
    if oos.empty or len(oos) < 30:
        return None
    sr_var = (pd.Series(wf.is_sharpes).var(ddof=1)
              if len(wf.is_sharpes) > 1 else 0.5)
    return dsr(oos, num_trials=num_trials,
               sr_variance_annualised=max(sr_var, 1e-6),
               periods_per_year=int(len(oos) / max(len(wf.folds), 1)))


def run_one(tf: str, cash: float, trial_ns: list[int]) -> dict:
    path = DATA_ROOT / f"XAUUSD_{tf}.csv"
    if not path.exists():
        print(f"[FATAL] {path} not found.", file=sys.stderr)
        return {}
    params = CONFIGS[tf]
    train, test, step = WINDOWS[tf]

    print(f"\n{'=' * 72}\n{tf} momentum long-only  "
          f"hma{params['hma_period']} atr{params['atr_period']} "
          f"trail{params['trail_atr_mult']}\n{'=' * 72}")
    res = load_bars(str(path), expected_timeframe=tf)
    print(f"{res.rows:,} rows, {res.span_years:.1f} years  "
          f"| train {train} test {test} step {step}")

    wf = run_walk_forward(
        res.df, CrestNKeelMomentum, params=params,
        session_hours=None,
        train_size=train, test_size=test, step_size=step,
        exclude_ranges=PEPPERSTONE_XAUUSD_KNOWN_GAPS,
        cash=cash, cost_model=PepperstoneXAUUSDCostModel(),
        periods_per_year=None, verbose=True)
    print()
    print(wf.summary_str())

    out = {"timeframe": tf, "params": params}
    is_s = np.asarray(wf.is_sharpes, float)
    oos_s = np.asarray(wf.oos_sharpes, float)
    is_s, oos_s = is_s[np.isfinite(is_s)], oos_s[np.isfinite(oos_s)]
    if oos_s.size:
        out.update(
            n_folds=len(wf.folds),
            oos_sharpe_mean=float(oos_s.mean()),
            oos_sharpe_median=float(np.median(oos_s)),
            oos_sharpe_min=float(oos_s.min()),
            oos_sharpe_max=float(oos_s.max()),
            oos_folds_positive=int((oos_s > 0).sum()),
            is_sharpe_mean=float(is_s.mean()) if is_s.size else None,
            sweep_is_sharpe=SWEEP_IS[tf]["sharpe"],
        )
        out["is_oos_gap"] = (out["is_sharpe_mean"] - out["oos_sharpe_mean"]
                             if out["is_sharpe_mean"] is not None else None)
        print(f"\n  OOS folds        : {out['oos_folds_positive']}/{oos_s.size} positive")
        print(f"  OOS Sharpe       : mean {out['oos_sharpe_mean']:+.3f}  "
              f"median {out['oos_sharpe_median']:+.3f}  "
              f"range [{out['oos_sharpe_min']:+.3f}, {out['oos_sharpe_max']:+.3f}]")
        print(f"  IS Sharpe (folds): {out['is_sharpe_mean']:+.3f}"
              if out["is_sharpe_mean"] is not None else "")
        print(f"  sweep IS Sharpe  : {SWEEP_IS[tf]['sharpe']:+.3f}  "
              f"-> gap vs OOS mean {SWEEP_IS[tf]['sharpe'] - out['oos_sharpe_mean']:+.3f}")

    out["dsr"] = {}
    for n in trial_ns:
        d = _dsr_for(wf, n)
        if d:
            out["dsr"][n] = float(d["dsr_probability"])
            print(f"  DSR @ N={n:<8,}: {d['dsr_probability']:.4f}  "
                  f"(obs {d['sharpe_obs_annualised']:.3f} vs "
                  f"benchmark {d['sr_benchmark_annualised']:.3f})")

    r = wf.to_scorecard_result(name=f"cnk_momentum_{tf}_sweep_leader", num_trials=1)
    dmax = _dsr_for(wf, max(trial_ns))
    if dmax is not None:
        r.dsr_probability = dmax["dsr_probability"]
    gate = evaluate(r, Thresholds())
    print("\n--- GATE (research tier) ---")
    print(gate)
    out["gate_passed"] = bool(gate.passed)
    out["gate_failures"] = [str(f) for f in gate.failures]
    print("\n  PASS" if gate.passed
          else f"\n  FAIL {len(gate.failures)} gate(s). Do not promote.")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tf", choices=["H4", "H1", "both"], default="both")
    ap.add_argument("--cash", type=float, default=10_000)
    ap.add_argument("--trial-ns", default="1,17,119917",
                    help="Comma-separated N values for the DSR haircut.")
    args = ap.parse_args()
    trial_ns = [int(x) for x in args.trial_ns.split(",")]

    tfs = ["H4", "H1"] if args.tf == "both" else [args.tf]
    results = [run_one(tf, args.cash, trial_ns) for tf in tfs]

    print(f"\n{'=' * 72}\nSUMMARY\n{'=' * 72}")
    for r in results:
        if not r.get("dsr"):
            continue
        print(f"{r['timeframe']:>3}  OOS mean {r['oos_sharpe_mean']:+.3f}  "
              f"folds+ {r['oos_folds_positive']}/{r['n_folds']}  "
              f"gap {r['sweep_is_sharpe'] - r['oos_sharpe_mean']:+.3f}  "
              f"DSR@grid {r['dsr'].get(max(trial_ns), float('nan')):.4f}  "
              f"gate {'PASS' if r['gate_passed'] else 'FAIL'}")
    print("\nReminder: parameters were selected on the full history, which "
          "includes these folds.\nThis measures temporal stability, not clean "
          "out-of-sample selection performance.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
