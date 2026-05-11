"""examples/run_walk_forward.py — validate H1 and M15 strategies.

Usage:
    # Full validation: session-filtered + spread stress
    python -m examples.run_walk_forward

    # Specific strategies
    python -m examples.run_walk_forward --strategies h1

    # Skip stress test (faster)
    python -m examples.run_walk_forward --no-stress

    # Change window sizes
    python -m examples.run_walk_forward --train 1460D --test 365D --step 180D

    # Honest num_trials (every distinct backtest on this data counts)
    python -m examples.run_walk_forward --num-trials 5

Session filter
--------------
The HMA+Stoch live strategies have NO session filter — they evaluate every
bar. However, gold's Asia session (00:00-08:00 UTC) has different vol and
trend characteristics, and running the backtest on session-only bars gives
a clearer picture of edge in the hours the strategy is most likely to trade.

The backtest is run TWICE per strategy:
    1. 24/7 (matches current live behaviour)
    2. 08:00-17:00 UTC London+NY session only

If edge is real it should survive both. If session-only looks dramatically
different from 24/7, that's a signal about where the edge lives.

Spread stress test
------------------
Pepperstone Razor typical spread: ~$0.22/oz.
Tests at 1.0×, 1.5×, 2.0× to check whether edge survives realistic
spread widening (news events, low-liquidity sessions, overnight holds).
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import pandas as pd

from qhf.data import load_bars, PepperstoneXAUUSDCostModel
from qhf.engines import (
    run_walk_forward,
    run_spread_stress,
    HMAStoch1H, HMAStochM15, ASQSafeScalping,
    PEPPERSTONE_XAUUSD_KNOWN_GAPS,
)
from qhf.metrics import dsr
from qhf.reports import evaluate, Thresholds

DATA_ROOT = Path("qhf/data/raw")

STRATEGIES = {
    "h1": {
        "cls": HMAStoch1H,
        "csv": "XAUUSD_H1.csv",
        "periods_per_year": None,          # auto from trade frequency
        "timeframe_label": "H1",
        "params": {},
    },
    "m15": {
        "cls": HMAStochM15,
        "csv": "XAUUSD_M15.csv",
        "periods_per_year": None,
        "timeframe_label": "M15",
        "params": {},
    },
    "asq": {
        "cls": ASQSafeScalping,
        "csv": "XAUUSD_M5.csv",
        "periods_per_year": None,          # auto from trade frequency
        "timeframe_label": "M5",
        "params": {},
        # Session filter lives INSIDE next() (handles Friday cutoff separately).
        # Do NOT pre-filter bars — indicators should see all-hours data.
    },
}


def _dsr_for(wf, num_trials: int) -> dict | None:
    oos_returns = wf.oos_return_pct
    if oos_returns.empty or len(oos_returns) < 30:
        return None
    sr_var = (pd.Series(wf.is_sharpes).var(ddof=1)
              if len(wf.is_sharpes) > 1 else 0.5)
    return dsr(
        oos_returns,
        num_trials=num_trials,
        sr_variance_annualised=max(sr_var, 1e-6),
        periods_per_year=int(len(oos_returns) /
                             max(len(wf.folds), 1)),  # trades/fold approx
    )


def _gate(wf, dsr_result, name: str) -> None:
    r = wf.to_scorecard_result(name=name, num_trials=1)
    if dsr_result is not None:
        r.dsr_probability = dsr_result["dsr_probability"]
    gate = evaluate(r, Thresholds())
    print()
    print("--- GATE ---")
    print(gate)
    if gate.passed:
        print("\n  ✅ Passes research-tier gates.")
    else:
        print(f"\n  ❌ Fails {len(gate.failures)} gate(s). Do not promote.")


def run_strategy(name: str, cfg: dict, args: argparse.Namespace) -> None:
    path = DATA_ROOT / cfg["csv"]
    if not path.exists():
        print(f"[SKIP] {cfg['timeframe_label']}: {path} not found.")
        return

    print(f"\n{'='*72}")
    print(f"  {cfg['timeframe_label']}  HMA+Stoch  v1.1")
    print(f"{'='*72}")

    print("Loading bars ...", end=" ")
    result = load_bars(str(path), expected_timeframe=cfg["timeframe_label"])
    bars = result.df
    print(f"{result.rows:,} rows, {result.span_years:.1f} years")
    cost_model = PepperstoneXAUUSDCostModel()

    common = dict(
        params=cfg.get("params"),
        train_size=args.train,
        test_size=args.test,
        step_size=args.step,
        exclude_ranges=PEPPERSTONE_XAUUSD_KNOWN_GAPS,
        cash=args.cash,
        cost_model=cost_model,
        periods_per_year=cfg["periods_per_year"],
        verbose=True,
    )

    # ── Run 1: 24/7 (matches live behaviour) ─────────────────────────────
    print(f"\n--- 24/7 (all hours, matches live strategy behaviour) ---")
    wf_24h = run_walk_forward(bars, cfg["cls"], session_hours=None, **common)
    print()
    print(wf_24h.summary_str())
    dsr_24h = _dsr_for(wf_24h, args.num_trials)
    if dsr_24h:
        print(f"DSR: Sharpe {dsr_24h['sharpe_obs_annualised']:.3f}  "
              f"vs expected max {dsr_24h['sr_benchmark_annualised']:.3f}  "
              f"(prob={dsr_24h['dsr_probability']:.3f})")
    _gate(wf_24h, dsr_24h, f"{cfg['timeframe_label']}_24h")

    # ── Run 2: Session-only (08:00–17:00 UTC, London+NY) ─────────────────
    print(f"\n--- Session-only (08:00–17:00 UTC, London+NY) ---")
    wf_sess = run_walk_forward(bars, cfg["cls"],
                               session_hours=(8, 17), **common)
    print()
    print(wf_sess.summary_str())
    dsr_sess = _dsr_for(wf_sess, args.num_trials)
    if dsr_sess:
        print(f"DSR: Sharpe {dsr_sess['sharpe_obs_annualised']:.3f}  "
              f"vs expected max {dsr_sess['sr_benchmark_annualised']:.3f}  "
              f"(prob={dsr_sess['dsr_probability']:.3f})")
    _gate(wf_sess, dsr_sess, f"{cfg['timeframe_label']}_session")

    # ── Spread stress test ────────────────────────────────────────────────
    if not args.no_stress:
        print(f"\n--- Spread stress test (using session-filtered bars) ---")
        stress = run_spread_stress(
            bars, cfg["cls"],
            multipliers=[1.0, 1.5, 2.0],
            session_hours=(8, 17),
            **common,
        )
        print()
        print(stress.summary_str())
        if stress.survives_stress():
            print("\n  ✅ Edge survives 2× spread. Robust to cost variation.")
        else:
            print("\n  ⚠  Edge does not survive spread doubling. "
                  "Sensitive to execution costs.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strategies", nargs="+", choices=["h1", "m15", "asq"],
                        default=["h1", "m15", "asq"])
    parser.add_argument("--train", default="1460D")
    parser.add_argument("--test", default="365D")
    parser.add_argument("--step", default="180D")
    parser.add_argument("--num-trials", type=int, default=5,
                        help="Total strategy variants tested on this data.")
    parser.add_argument("--cash", type=float, default=10_000)
    parser.add_argument("--no-stress", action="store_true",
                        help="Skip spread stress test (faster).")
    args = parser.parse_args()

    print("qhf walk-forward validation")
    print(f"Gaps excluded: {PEPPERSTONE_XAUUSD_KNOWN_GAPS}")

    for name in args.strategies:
        run_strategy(name, STRATEGIES[name], args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
