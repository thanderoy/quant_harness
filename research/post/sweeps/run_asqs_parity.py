"""research.post.sweeps.run_asqs_parity — asqs_engine vs qhf btpy_runner.

Both sides are fed bars loaded with the DEFAULT tz ("legacy_utc"), i.e. broker
server time relabelled as UTC. That is deliberate: the harness assumes its
index is UTC and its session filter reads hour-of-day, so feeding it corrected
timestamps would change WHICH BARS it trades and confound an engine-parity test
with the timezone defect. This run isolates engine semantics. The sweep itself
uses tz="server_eet" and treats the session bounds as swept parameters.

Usage:
    python -m research.post.sweeps.run_asqs_parity
"""
from __future__ import annotations

import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/roy-thande/Local/qhf_harness")

from qhf.engines.btpy_runner import run_backtest                        # noqa: E402
from qhf.engines.strategies.asq_safe_scalping import ASQSafeScalping    # noqa: E402

from research.post.sweeps import asqs_engine as A                       # noqa: E402
from research.post.sweeps.data import load                              # noqa: E402

BASE = dict(ema_fast=50, ema_slow=200, trend_strength=1, rsi_period=14,
            rsi_buy_min=45.0, rsi_buy_max=65.0, rsi_sell_min=35.0,
            rsi_sell_max=55.0, breakout_lookback=15, breakout_buffer=0.3,
            atr_period=50, sl_points=300, tp_points=450,
            use_breakeven=True, breakeven_start=150, breakeven_offset=20,
            use_trailing=True, trail_start=200, trail_step=100,
            use_partial_close=True, tp1_points=200, tp1_close_pct=50.0,
            risk_pct=0.5, max_day_trades=4, max_dd_pct=8.0,
            use_session=True, session_start=8, session_end=17,
            avoid_friday=True, friday_cutoff=14, use_mtf=False)

# Windows kept short: backtesting.py is a per-bar Python loop and full M5
# history takes many minutes per config.
CASES = [
    ("M5",  "2018-01-01", "2019-01-01", {}),
    ("M5",  "2018-01-01", "2019-01-01", dict(use_partial_close=False)),
    ("M5",  "2018-01-01", "2019-01-01", dict(use_breakeven=False, use_trailing=False)),
    ("M5",  "2020-01-01", "2021-01-01", {}),
    ("M5",  "2020-01-01", "2021-01-01", dict(sl_points=200, tp_points=600)),
    ("M5",  "2022-01-01", "2023-01-01", dict(max_day_trades=0)),
    ("M5",  "2022-01-01", "2023-01-01", dict(use_session=False)),
    ("M15", "2019-01-01", "2021-01-01", {}),
    ("M15", "2019-01-01", "2021-01-01", dict(trend_strength=2, breakout_lookback=25)),
    ("H1",  "2015-01-01", "2020-01-01", {}),
]


def engine_run(tf, start, end, over):
    c = {**BASE, **over}
    df = load(tf, start, end)              # legacy_utc on purpose -- see docstring
    bars = A.Bars(df)
    ind = A.indicators(bars, c["ema_fast"], c["ema_slow"], c["rsi_period"],
                       c["atr_period"], c["breakout_lookback"])
    ls, ss = A.entry_signals(bars, ind, c["trend_strength"], c["breakout_buffer"],
                             c["rsi_buy_min"], c["rsi_buy_max"],
                             c["rsi_sell_min"], c["rsi_sell_max"])
    sm = A.session_mask(bars, c["use_session"], c["session_start"],
                        c["session_end"], c["avoid_friday"], c["friday_cutoff"])
    sim = A.simulate(bars, ind, ls, ss, sm,
                     sl_points=c["sl_points"], tp_points=c["tp_points"],
                     use_breakeven=c["use_breakeven"],
                     breakeven_start=c["breakeven_start"],
                     breakeven_offset=c["breakeven_offset"],
                     use_trailing=c["use_trailing"], trail_start=c["trail_start"],
                     trail_step=c["trail_step"],
                     use_partial_close=c["use_partial_close"],
                     tp1_points=c["tp1_points"], tp1_close_pct=c["tp1_close_pct"],
                     risk_pct=c["risk_pct"], max_day_trades=c["max_day_trades"],
                     max_dd_pct=c["max_dd_pct"])
    return df, c, sim, A.metrics(sim, basis="price")


def main() -> int:
    print(f"{'tf':<4}{'window':<12}{'variant':<28}{'n_eng':>6}{'n_hrn':>6}"
          f"{'match%':>8}{'shrp_e':>8}{'shrp_h':>8}{'pf_e':>7}{'pf_h':>7}")
    worst, worst_match = 0.0, 100.0
    for tf, start, end, over in CASES:
        df, c, sim, m = engine_run(tf, start, end, over)
        res = run_backtest(df, ASQSafeScalping, params=c)
        hs = set(pd.to_datetime(res.trades["EntryTime"])) if not res.trades.empty else set()
        ms = set(pd.to_datetime(sim["entry_ts"]))
        match = 100.0 * len(hs & ms) / max(len(hs | ms), 1)
        lbl = ",".join(f"{k}={v}" for k, v in over.items()) or "defaults"
        print(f"{tf:<4}{start[:7]:<12}{lbl[:27]:<28}{m['n_trades']:>6}{res.n_trades:>6}"
              f"{match:>7.1f}%{m['sharpe']:>8.3f}{res.sharpe:>8.3f}"
              f"{m['profit_factor']:>7.3f}{res.pf:>7.3f}")
        if np.isfinite(m["sharpe"]) and np.isfinite(res.sharpe):
            worst = max(worst, abs(m["sharpe"] - res.sharpe))
        worst_match = min(worst_match, match)
    print(f"\nworst |sharpe_engine - sharpe_harness| = {worst:.4f}")
    print(f"worst entry-set match = {worst_match:.1f}%")
    return 0 if worst < 0.05 else 1


if __name__ == "__main__":
    raise SystemExit(main())
