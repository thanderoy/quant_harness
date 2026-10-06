"""research.post.sweeps.run_ebb_parity — validate ebb_engine against the harness.

Usage:  python -m research.post.sweeps.run_ebb_parity
"""
from __future__ import annotations

import sys
from pathlib import Path
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path.home() / "Local" / "quant_harness"))

from qhf.engines.btpy_runner import run_backtest                 # noqa: E402
from qhf.engines.strategies.ebb_n_flow import EbbNFlow           # noqa: E402

from research.post.sweeps import ebb_engine as E                 # noqa: E402
from research.post.sweeps.data import load                       # noqa: E402
from research.post.sweeps.zlch_engine import metrics             # noqa: E402

CASES = [
    ("M15", "2018-01-01", "2021-12-31", dict()),
    ("M15", "2018-01-01", "2021-12-31", dict(bb_n=30, bb_k=2.5, er_max=0.40)),
    ("M15", "2018-01-01", "2021-12-31", dict(sl_atr_mult=2.0, time_stop_bars=16)),
    ("H1",  "2010-01-01", "2019-12-31", dict()),
    ("H1",  "2010-01-01", "2019-12-31", dict(bb_n=50, bb_k=3.0, er_max=1.0, time_stop_bars=4)),
    ("H4",  "2004-06-11", "2025-12-31", dict(bb_n=14, bb_k=1.5, sl_atr_mult=3.0)),
]

DEFAULTS = dict(bb_n=20, bb_k=2.0, er_n=10, er_max=0.30, atr_n=14, atr_floor=1.0,
                sl_atr_mult=1.0, atr_spike_mult=2.5, min_r=0.5,
                time_stop_bars=8, risk_pct=0.01)


def engine_run(tf, start, end, p):
    df = load(tf, start, end)
    bars = E.EbbBars(df)
    mid, up, lo, er, atr = E.build_indicators(bars, p["bb_n"], p["bb_k"],
                                              p["er_n"], p["atr_n"])
    return df, E.simulate(bars, mid, up, lo, er, atr,
                          er_max=p["er_max"], sl_atr_mult=p["sl_atr_mult"],
                          atr_floor=p["atr_floor"],
                          time_stop_bars=p["time_stop_bars"],
                          atr_spike_mult=p["atr_spike_mult"], min_r=p["min_r"],
                          enable_long=True, enable_short=True, use_session=True,
                          risk_pct=p["risk_pct"])


def main() -> int:
    print(f"{'tf':<4}{'params':<40}{'n_e':>6}{'n_h':>6}{'match%':>8}"
          f"{'shrp_e':>9}{'shrp_h':>9}{'pf_e':>8}{'pf_h':>8}{'dd_e':>7}{'dd_h':>7}")
    worst = 0.0
    for tf, start, end, over in CASES:
        p = {**DEFAULTS, **over}
        df, sim = engine_run(tf, start, end, p)
        m = metrics(sim, basis="price")
        res = run_backtest(df, EbbNFlow, params=over or None)
        hs = set(pd.to_datetime(res.trades["EntryTime"])) if not res.trades.empty else set()
        ms = set(pd.to_datetime(sim["entry_ts"]))
        match = 100.0 * len(hs & ms) / max(len(hs | ms), 1)
        lbl = ",".join(f"{k}={v}" for k, v in over.items()) or "registered defaults"
        print(f"{tf:<4}{lbl:<40}{m['n_trades']:>6}{res.n_trades:>6}{match:>7.1f}%"
              f"{m['sharpe']:>9.3f}{res.sharpe:>9.3f}{m['profit_factor']:>8.3f}"
              f"{res.pf:>8.3f}{m['max_dd']:>7.3f}{res.max_dd:>7.3f}")
        worst = max(worst, abs(m["sharpe"] - res.sharpe))
    print(f"\nworst |sharpe_engine - sharpe_harness| = {worst:.4f}")
    return 0 if worst < 0.05 else 1


if __name__ == "__main__":
    sys.exit(main())
