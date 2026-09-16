"""examples/load_and_cost.py — quick end-to-end demo of Phase 2.

Run with a real XAUUSD CSV path, or with no args to use a synthetic file.
The point: verify that load_bars + cost_model produce plausible numbers
on YOUR actual data before any engine is wired up.

Usage:
    python -m examples.load_and_cost                  # synthetic
    python -m examples.load_and_cost path/to/H1.csv   # real
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime
from io import StringIO

import numpy as np
import pandas as pd

from research.datasets import load_bars, PepperstoneXAUUSDCostModel


def _make_synthetic_h1() -> str:
    """Generate a 5y synthetic H1 file in MT5 native format."""
    idx = pd.date_range("2020-01-01", "2025-01-01", freq="h")
    idx = idx[idx.weekday < 5]
    rng = np.random.default_rng(0)
    drift = np.cumsum(rng.normal(0.001, 1.0, len(idx))) + 2000
    df = pd.DataFrame({
        "Date": [t.strftime("%Y.%m.%d %H:%M") for t in idx],
        "Open": drift - 0.1,
        "High": drift + 0.3,
        "Low": drift - 0.3,
        "Close": drift + rng.normal(0, 0.05, len(idx)),
        "Volume": rng.integers(20, 200, len(idx)),
    })
    fd, path = tempfile.mkstemp(suffix=".csv")
    os.close(fd)
    with open(path, "w") as f:
        df.to_csv(f, sep="\t", index=False)
    return path


def main():
    real = len(sys.argv) > 1
    path = sys.argv[1] if real else _make_synthetic_h1()

    print("=" * 72)
    print(f"DEMO: load + cost on {'YOUR FILE' if real else 'synthetic data'}")
    print("=" * 72)

    result = load_bars(path, expected_timeframe="H1")
    print(result.summary_str())
    print()

    # Show the cost of a sample trade.
    cost = PepperstoneXAUUSDCostModel()
    print("Sample trade cost (Pepperstone Razor MT5, current defaults):")
    print(f"  spread_per_oz_typical : ${cost.spread_usd_per_oz}")
    print(f"  commission_per_lot_RT : ${cost.commission_per_lot_round_turn}")
    print(f"  swap_long_per_lot_night : ${cost.swap_long_per_lot_night} (placeholder)")
    print()

    examples = [
        ("0.01 lot, intraday BUY (no swap)",     0.01, "BUY",
         datetime(2024, 5, 6, 9, 0), datetime(2024, 5, 6, 16, 0)),
        ("0.01 lot, BUY held 1 night",           0.01, "BUY",
         datetime(2024, 5, 6, 12, 0), datetime(2024, 5, 7, 12, 0)),
        ("0.10 lot, BUY held 5 nights (incl. Wed triple)", 0.10, "BUY",
         datetime(2024, 5, 6, 12, 0), datetime(2024, 5, 11, 12, 0)),
        ("1.00 lot, intraday BUY",               1.00, "BUY",
         datetime(2024, 5, 6, 9, 0), datetime(2024, 5, 6, 16, 0)),
    ]
    for label, lots, dirn, t0, t1 in examples:
        cb = cost.trade_cost(lots, dirn, t0, t1)
        print(f"  {label}")
        print(f"    spread:     ${cb.spread_usd:>7.2f}")
        print(f"    commission: ${cb.commission_usd:>7.2f}")
        print(f"    swap:       ${cb.swap_usd:>+7.2f}  ({cb.nights_held} nights, "
              f"{cb.triple_swap_nights} triples)")
        print(f"    TOTAL:      ${cb.total_usd:>+7.2f}")

    if not real:
        os.unlink(path)
        print()
        print("(Synthetic file cleaned up. Re-run with `python -m examples.load_and_cost "
              "path/to/your/H1.csv` to load YOUR data.)")


if __name__ == "__main__":
    main()
