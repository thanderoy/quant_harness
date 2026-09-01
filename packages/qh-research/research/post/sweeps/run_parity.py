"""research.post.sweeps.run_parity — validate the fast engine against the harness.

The sweep is only trustworthy if research.post.sweeps.zlch_engine reproduces
qhf.engines.strategies.zlch.ZeroLagChandelier under qhf.engines.btpy_runner.
This compares trade sets and metrics across a spread of configs/timeframes.

Usage:  python -m research.post.sweeps.run_parity
"""
from __future__ import annotations

import sys
from pathlib import Path
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path.home() / "Local" / "quant_harness"))

from qhf.engines.btpy_runner import run_backtest              # noqa: E402
from qhf.engines.strategies.zlch import ZeroLagChandelier      # noqa: E402

from research.post.sweeps import zlch_engine as E              # noqa: E402
from research.post.sweeps.data import load                     # noqa: E402

CASES = [
    ("M15", "2018-01-01", "2020-12-31", dict(chand_atr_period=14, chand_atr_mult=2.5, zlsma_len=50, enable_long=True,  enable_short=True,  use_h4_bias=True)),
    ("M15", "2018-01-01", "2020-12-31", dict(chand_atr_period=14, chand_atr_mult=2.5, zlsma_len=50, enable_long=True,  enable_short=False, use_h4_bias=True)),
    ("M15", "2018-01-01", "2020-12-31", dict(chand_atr_period=20, chand_atr_mult=3.0, zlsma_len=50, enable_long=True,  enable_short=True,  use_h4_bias=False)),
    ("M15", "2018-01-01", "2020-12-31", dict(chand_atr_period=8,  chand_atr_mult=1.5, zlsma_len=20, enable_long=False, enable_short=True,  use_h4_bias=True)),
    ("H1",  "2010-01-01", "2019-12-31", dict(chand_atr_period=14, chand_atr_mult=2.5, zlsma_len=50, enable_long=True,  enable_short=True,  use_h4_bias=True)),
    ("H1",  "2010-01-01", "2019-12-31", dict(chand_atr_period=50, chand_atr_mult=4.0, zlsma_len=120, enable_long=True, enable_short=True,  use_h4_bias=True)),
    ("H4",  "2004-01-01", "2025-12-31", dict(chand_atr_period=10, chand_atr_mult=2.0, zlsma_len=50, enable_long=True,  enable_short=True,  use_h4_bias=True)),
]


def engine_run(tf, start, end, c):
    df = load(tf, start, end)
    bars = E.Bars(df)
    d = E.chandelier_direction(bars.high_s, bars.low_s, bars.close_s,
                               c["chand_atr_period"], c["chand_atr_mult"])
    a = E.wilder_atr(bars.high_s, bars.low_s, bars.close_s, c["chand_atr_period"])
    if c["use_h4_bias"]:
        r, f = E.htf_bias(bars.close_s, df.index, "4h", c["zlsma_len"])
    else:
        r = np.ones(len(df), bool)
        f = np.ones(len(df), bool)
    sim = E.simulate(bars, d, a, r, f, c["enable_long"], c["enable_short"],
                     c["chand_atr_mult"], 0.01, 1.0,
                     max_dd_halt=c.get("max_drawdown_halt", 1.0))
    return df, sim, E.metrics(sim, basis="price")


def main() -> int:
    print(f"{'tf':<4}{'config':<34}{'n_eng':>6}{'n_hrn':>6}{'match%':>8}"
          f"{'shrpPX_e':>9}{'shrp_h':>8}{'pf_e':>7}{'pf_h':>7}{'dd_e':>7}{'dd_h':>7}")
    worst = 0.0
    for tf, start, end, c in CASES:
        df, sim, m = engine_run(tf, start, end, c)
        res = run_backtest(df, ZeroLagChandelier,
                           params={**c, "max_drawdown_halt": 1.0})
        hs = set(pd.to_datetime(res.trades["EntryTime"])) if not res.trades.empty else set()
        ms = set(pd.to_datetime(sim["entry_ts"]))
        match = 100.0 * len(hs & ms) / max(len(hs | ms), 1)
        lbl = (f"p{c['chand_atr_period']} m{c['chand_atr_mult']} z{c['zlsma_len']} "
               f"L{int(c['enable_long'])}S{int(c['enable_short'])}B{int(c['use_h4_bias'])}")
        print(f"{tf:<4}{lbl:<34}{m['n_trades']:>6}{res.n_trades:>6}{match:>7.1f}%"
              f"{m['sharpe']:>8.3f}{res.sharpe:>8.3f}{m['profit_factor']:>7.3f}"
              f"{res.pf:>7.3f}{m['max_dd']:>7.3f}{res.max_dd:>7.3f}")
        worst = max(worst, abs(m["sharpe"] - res.sharpe))
    print(f"\nworst |sharpe_engine - sharpe_harness| = {worst:.4f}")
    print("NOTE: max_drawdown_halt disabled on BOTH sides. It is an absorbing\n"
          "      barrier that permanently truncates a config's record, making\n"
          "      swept configs non-comparable. Drawdown is reported as a metric.")
    return 0 if worst < 0.05 else 1


if __name__ == "__main__":
    sys.exit(main())
