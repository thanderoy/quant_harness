"""examples/export_asqs_returns.py — regenerate + persist ASQS OOS returns.

Runs the ASQSafeScalping (M5, 7-condition breakout) walk-forward and writes the
per-trade OOS ReturnPct series to CSV for BOTH configs:

    1. 24/7   (session_hours=None)     -> asqs_oos_returns_24h.csv
    2. 08-17  (session_hours=(8, 17))  -> asqs_oos_returns_session.csv

The stock run_walk_forward.py computes DSR inline but discards the underlying
return stream. This driver persists it so the canonical
`research/post/dsr.py` (in the wine-mt5-python-setup repo) can recompute the
Deflated Sharpe at the log's honest trial_count(). It is the ASQS twin of
export_crest_n_keel_returns.py, produced to clear the seed-metric audit's
top-priority queue item (asqs walk-forward; the seeded 5.14/1.55 is unbacked).

Params mirror the crest_n_keel export: train=1460D, test=365D, step=180D,
Pepperstone Razor costs, PEPPERSTONE_XAUUSD_KNOWN_GAPS excluded. Session filter
lives INSIDE the strategy's next() (Friday cutoff handled separately) — bars are
NOT pre-filtered so indicators see all-hours data.

Usage:
    python -m examples.export_asqs_returns --out-dir /abs/path
"""

from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import pandas as pd

from research.datasets import load_bars, PepperstoneXAUUSDCostModel
from research.engines import (
    run_walk_forward,
    ASQSafeScalping,
    PEPPERSTONE_XAUUSD_KNOWN_GAPS,
)

DATA_ROOT = Path("packages/qh-research/research/data")


def _export(wf, label: str, out_dir: Path) -> Path:
    returns = wf.oos_return_pct.reset_index(drop=True)
    out_path = out_dir / f"asqs_oos_returns_{label}.csv"
    returns.to_frame(name="oos_return_pct").to_csv(out_path, index_label="trade_idx")
    print(f"  wrote {len(returns)} OOS trade returns -> {out_path}")
    print(f"    oos_sharpe(ann, harness-side)={wf.oos_sharpe:.4f}  "
          f"trades={wf.n_trades_oos}  folds={len(wf.folds)}  "
          f"PF={wf.oos_profit_factor:.3f}")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--train", default="1460D")
    parser.add_argument("--test", default="365D")
    parser.add_argument("--step", default="180D")
    parser.add_argument("--cash", type=float, default=10_000)
    parser.add_argument("--out-dir", default=".", help="Directory for CSV output.")
    args = parser.parse_args()

    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    path = DATA_ROOT / "XAUUSD_M5.csv"
    if not path.exists():
        print(f"[FATAL] {path} not found.", file=sys.stderr)
        return 1

    print("Loading M5 bars ...", end=" ")
    result = load_bars(str(path), expected_timeframe="M5")
    bars = result.df
    print(f"{result.rows:,} rows, {result.span_years:.1f} years")

    cost_model = PepperstoneXAUUSDCostModel()
    common = dict(
        params={},
        train_size=args.train,
        test_size=args.test,
        step_size=args.step,
        exclude_ranges=PEPPERSTONE_XAUUSD_KNOWN_GAPS,
        cash=args.cash,
        cost_model=cost_model,
        periods_per_year=None,
        verbose=False,
    )

    print("\n[1/2] 24/7 walk-forward ...")
    wf_24h = run_walk_forward(bars, ASQSafeScalping, session_hours=None, **common)
    _export(wf_24h, "24h", out_dir)

    print("\n[2/2] 08:00-17:00 UTC session walk-forward ...")
    wf_sess = run_walk_forward(bars, ASQSafeScalping, session_hours=(8, 17), **common)
    _export(wf_sess, "session", out_dir)

    # Also emit the empirical IS-Sharpe variance the harness twin uses, so the
    # downstream canonical recompute can run a byte-parity-matched variant.
    for label, wf in (("24h", wf_24h), ("session", wf_sess)):
        sr_var_ann = (pd.Series(wf.is_sharpes).var(ddof=1)
                      if len(wf.is_sharpes) > 1 else float("nan"))
        ppy_approx = int(len(wf.oos_return_pct) / max(len(wf.folds), 1))
        print(f"  [{label}] harness Var(SR_ann)={sr_var_ann:.6f}  "
              f"ppy_approx(trades/fold)={ppy_approx}  n_is_folds={len(wf.is_sharpes)}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
