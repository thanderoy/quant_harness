"""examples/run_cnk_momentum.py — validate the TradingView Config A candidate.

Runs the crest_n_keel MOMENTUM variant (HMA-slope-flip, long-only, ATR
chandelier trailing exit) through the same walk-forward + DSR + gate pipeline
as run_walk_forward.py. 24/7 (session off) to match the TradingView config.

Usage:
    python -m examples.run_cnk_momentum --num-trials 20
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import pandas as pd

from research.datasets import load_bars, PepperstoneXAUUSDCostModel
from research.engines import run_walk_forward, PEPPERSTONE_XAUUSD_KNOWN_GAPS
from research.engines.strategies.cnk_momentum import CrestNKeelMomentum
from research.metrics import dsr
from research.reports import evaluate, Thresholds

DATA_ROOT = Path("packages/qh-research/research/data")


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
    parser.add_argument("--train", default="1460D")
    parser.add_argument("--test", default="365D")
    parser.add_argument("--step", default="180D")
    parser.add_argument("--cash", type=float, default=10_000)
    parser.add_argument("--num-trials", type=int, default=20,
                        help="Honest count of variants tested on this idea.")
    args = parser.parse_args()

    path = DATA_ROOT / "XAUUSD_H1.csv"
    if not path.exists():
        print(f"[FATAL] {path} not found.", file=sys.stderr)
        return 1

    print("quant_harness walk-forward — crest_n_keel MOMENTUM (TradingView Config A)")
    print(f"Gaps excluded: {PEPPERSTONE_XAUUSD_KNOWN_GAPS}")
    print("Loading H1 bars ...", end=" ")
    result = load_bars(str(path), expected_timeframe="H1")
    bars = result.df
    print(f"{result.rows:,} rows, {result.span_years:.1f} years")

    cost_model = PepperstoneXAUUSDCostModel()
    wf = run_walk_forward(
        bars, CrestNKeelMomentum,
        session_hours=None,            # 24/7, matches TradingView config
        params={},
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

    r = wf.to_scorecard_result(name="crest_n_keel_momentum_24h", num_trials=1)
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
