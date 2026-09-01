"""examples/run_zlch.py — validate the ZeroLag Chandelier candidate.

Runs the M15 Chandelier-flip + H4 ZLSMA-bias strategy through the same
walk-forward + DSR + gate pipeline as run_walk_forward.py. 24/7 (session off)
to match the TradingView LAB config.

The `--config` flag selects the component variant under test:
    both   — faithful both-directions signal (default)
    long   — long-only (E-Ratio-preferred, bull-friendly)
    short  — short-only (regime-fit control; expected to fail long-run)

Usage:
    python -m examples.run_zlch --config both  --num-trials 22
    python -m examples.run_zlch --config long  --num-trials 22
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import pandas as pd

from qhf.data import load_bars, PepperstoneXAUUSDCostModel
from qhf.engines import run_walk_forward, PEPPERSTONE_XAUUSD_KNOWN_GAPS
from qhf.engines.strategies.zlch import ZeroLagChandelier
from qhf.metrics import dsr
from qhf.reports import evaluate, Thresholds

DATA_ROOT = Path("qhf/data/raw")

CONFIGS = {
    "both":  {"enable_long": True,  "enable_short": True},
    "long":  {"enable_long": True,  "enable_short": False},
    "short": {"enable_long": False, "enable_short": True},
}


def _dsr_for(wf, num_trials: int) -> dict | None:
    oos = wf.oos_return_pct
    if oos.empty or len(oos) < 30:
        return None
    sr_var = (pd.Series(wf.is_sharpes).var(ddof=1)
              if len(wf.is_sharpes) > 1 else 0.5)
    return dsr(
        oos,
        num_trials=num_trials,
        sr_variance_annualised=max(sr_var, 1e-6),
        periods_per_year=int(len(oos) / max(len(wf.folds), 1)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", choices=list(CONFIGS), default="both")
    parser.add_argument("--chand-mult", type=float, default=2.5)
    parser.add_argument("--train", default="1460D")
    parser.add_argument("--test", default="365D")
    parser.add_argument("--step", default="180D")
    parser.add_argument("--cash", type=float, default=10_000)
    parser.add_argument("--num-trials", type=int, default=22,
                        help="Honest count of variants tested on this idea.")
    args = parser.parse_args()

    path = DATA_ROOT / "XAUUSD_M15.csv"
    if not path.exists():
        print(f"[FATAL] {path} not found.", file=sys.stderr)
        return 1

    params = dict(CONFIGS[args.config])
    params["chand_atr_mult"] = args.chand_mult

    print(f"qhf walk-forward — ZeroLag Chandelier  [config={args.config}, "
          f"chand_mult={args.chand_mult}]")
    print(f"Gaps excluded: {PEPPERSTONE_XAUUSD_KNOWN_GAPS}")
    print("Loading M15 bars ...", end=" ")
    result = load_bars(str(path), expected_timeframe="M15")
    bars = result.df
    print(f"{result.rows:,} rows, {result.span_years:.1f} years")

    cost_model = PepperstoneXAUUSDCostModel()
    wf = run_walk_forward(
        bars, ZeroLagChandelier,
        session_hours=None,            # 24/7, matches TradingView config
        params=params,
        train_size=args.train, test_size=args.test, step_size=args.step,
        exclude_ranges=PEPPERSTONE_XAUUSD_KNOWN_GAPS,
        cash=args.cash, cost_model=cost_model,
        periods_per_year=None, verbose=True,
    )
    print()
    print(wf.summary_str())

    dsr_res = _dsr_for(wf, args.num_trials)
    if dsr_res:
        print(f"\nDSR: obs Sharpe {dsr_res['sharpe_obs_annualised']:.3f} "
              f"vs expected max {dsr_res['sr_benchmark_annualised']:.3f} "
              f"(prob={dsr_res['dsr_probability']:.3f}, num_trials={args.num_trials})")

    r = wf.to_scorecard_result(name=f"zlch_{args.config}", num_trials=1)
    if dsr_res is not None:
        r.dsr_probability = dsr_res["dsr_probability"]
    gate = evaluate(r, Thresholds())
    print("\n--- GATE (research tier) ---")
    print(gate)
    print("\n  ✅ PASS" if gate.passed
          else f"\n  ❌ FAIL {len(gate.failures)} gate(s). Do not promote.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
