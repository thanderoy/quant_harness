"""research.post.sweeps.run_cnk_parity — validate cnk_engine against the harness.

The sweep is only trustworthy if research.post.sweeps.cnk_engine reproduces
research.engines.strategies.hma_stoch.HMAStoch1H (PULLBACK) and
research.engines.strategies.cnk_momentum.CrestNKeelMomentum (MOMENTUM) running
under research.engines.btpy_runner.

Scope note: the canonical classes hardcode the 20/80 stochastic zones and are
long+short (pullback) / long-only (momentum). Parity therefore covers the
DEFAULT slice of the sweep grid. The swept extensions — oversold/overbought
thresholds and the direction toggle — are a literal constant substitution and
an entry mask respectively, neither of which the harness can arbitrate.

Usage:  python -m research.post.sweeps.run_cnk_parity
"""
from __future__ import annotations

import sys
from pathlib import Path
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path.home() / "Local" / "quant_harness"))

from research.engines.btpy_runner import run_backtest                      # noqa: E402
from research.engines.strategies.hma_stoch import HMAStoch1H               # noqa: E402
from research.engines.strategies.cnk_momentum import CrestNKeelMomentum    # noqa: E402

from research.post.sweeps import cnk_engine as E                      # noqa: E402
from research.post.sweeps.data import load                            # noqa: E402

PB = dict(stoch_k_period=14, stoch_d_period=3, stoch_smooth_k=3, risk_pct=0.02)

CASES = [
    # (mode, tf, start, end, params)
    ("pullback", "H1",  "2010-01-01", "2019-12-31", dict(PB, hma_period=55, atr_period=14, sl_atr_mult=1.5, tp_atr_mult=3.0, min_atr_for_signal=1.0)),
    ("pullback", "H1",  "2004-01-01", "2025-12-31", dict(PB, hma_period=55, atr_period=14, sl_atr_mult=1.5, tp_atr_mult=3.0, min_atr_for_signal=1.0)),
    ("pullback", "H1",  "2010-01-01", "2019-12-31", dict(PB, hma_period=21, atr_period=7,  sl_atr_mult=2.0, tp_atr_mult=2.0, min_atr_for_signal=0.0)),
    ("pullback", "M15", "2018-01-01", "2020-12-31", dict(PB, hma_period=21, atr_period=14, sl_atr_mult=1.5, tp_atr_mult=2.5, min_atr_for_signal=2.0)),
    ("pullback", "H4",  "2004-01-01", "2025-12-31", dict(PB, hma_period=89, atr_period=21, sl_atr_mult=3.0, tp_atr_mult=5.0, min_atr_for_signal=1.0)),
    ("pullback", "D1",  "2004-01-01", "2025-12-31", dict(PB, hma_period=55, atr_period=14, sl_atr_mult=1.5, tp_atr_mult=3.0, min_atr_for_signal=0.0)),
    ("momentum", "H1",  "2004-01-01", "2025-12-31", dict(hma_period=55, atr_period=14, trail_atr_mult=3.0, risk_pct=0.02, min_atr_for_signal=1.0)),
    ("momentum", "H1",  "2010-01-01", "2019-12-31", dict(hma_period=55, atr_period=14, trail_atr_mult=3.0, risk_pct=0.02, min_atr_for_signal=1.0)),
    ("momentum", "H1",  "2010-01-01", "2019-12-31", dict(hma_period=21, atr_period=14, trail_atr_mult=2.0, risk_pct=0.02, min_atr_for_signal=0.0)),
    ("momentum", "H4",  "2004-01-01", "2025-12-31", dict(hma_period=55, atr_period=14, trail_atr_mult=4.0, risk_pct=0.02, min_atr_for_signal=1.0)),
    ("momentum", "M15", "2018-01-01", "2020-12-31", dict(hma_period=55, atr_period=14, trail_atr_mult=3.0, risk_pct=0.02, min_atr_for_signal=1.0)),
]


def engine_run(mode, tf, start, end, c, from_fill=True):
    df = load(tf, start, end)
    bars = E.Bars(df)
    hma_v = E.hma(bars.close, c["hma_period"])
    atr_v = E.atr(bars.high, bars.low, bars.close, c["atr_period"])
    if mode == "pullback":
        lo_s, sh_s = E.pullback_signals(
            bars, hma_v,
            *E.stochastic(bars.high, bars.low, bars.close,
                          c["stoch_k_period"], c["stoch_d_period"], c["stoch_smooth_k"]),
            oversold=20.0, overbought=80.0)
        enable_long = enable_short = True
        sl_m, tp_m, tr_m = c["sl_atr_mult"], c["tp_atr_mult"], 0.0
    else:
        lo_s, sh_s = E.momentum_signals(bars, hma_v)
        enable_long, enable_short = True, False
        sl_m, tp_m, tr_m = 0.0, 0.0, c["trail_atr_mult"]
    sim = E.simulate(bars, mode, hma_v, atr_v, lo_s, sh_s,
                     enable_long=enable_long, enable_short=enable_short,
                     sl_mult=sl_m, tp_mult=tp_m, trail_mult=tr_m,
                     risk_pct=c["risk_pct"], min_atr=c["min_atr_for_signal"],
                     max_dd_halt=1.0, sl_checked_from_fill_bar=from_fill)
    return df, sim, E.metrics(sim, basis="price")


def main() -> int:
    # Verified: backtesting.py checks contingent SL/TP on the FILL bar itself.
    # --bar-after-fill re-tests the rejected alternative.
    from_fill = "--bar-after-fill" not in sys.argv
    print(f"SL/TP first checked on: {'FILL bar' if from_fill else 'bar AFTER fill'}\n")
    print(f"{'mode':<9}{'tf':<4}{'config':<30}{'n_eng':>6}{'n_hrn':>6}{'match%':>8}"
          f"{'shrp_e':>8}{'shrp_h':>8}{'pf_e':>7}{'pf_h':>7}{'dd_e':>7}{'dd_h':>7}")
    worst = 0.0
    worst_match = 100.0
    for mode, tf, start, end, c in CASES:
        df, sim, m = engine_run(mode, tf, start, end, c, from_fill)
        cls = HMAStoch1H if mode == "pullback" else CrestNKeelMomentum
        res = run_backtest(df, cls, params={**c, "max_drawdown_halt": 1.0})
        hs = set(pd.to_datetime(res.trades["EntryTime"])) if not res.trades.empty else set()
        ms = set(pd.to_datetime(sim["entry_ts"]))
        match = 100.0 * len(hs & ms) / max(len(hs | ms), 1)
        if mode == "pullback":
            lbl = f"h{c['hma_period']} a{c['atr_period']} sl{c['sl_atr_mult']} tp{c['tp_atr_mult']} m{c['min_atr_for_signal']}"
        else:
            lbl = f"h{c['hma_period']} a{c['atr_period']} tr{c['trail_atr_mult']} m{c['min_atr_for_signal']}"
        print(f"{mode:<9}{tf:<4}{lbl:<30}{m['n_trades']:>6}{res.n_trades:>6}{match:>7.1f}%"
              f"{m['sharpe']:>8.3f}{res.sharpe:>8.3f}{m['profit_factor']:>7.3f}"
              f"{res.pf:>7.3f}{m['max_dd']:>7.3f}{res.max_dd:>7.3f}")
        if np.isfinite(m["sharpe"]) and np.isfinite(res.sharpe):
            worst = max(worst, abs(m["sharpe"] - res.sharpe))
        worst_match = min(worst_match, match)
    print(f"\nworst |sharpe_engine - sharpe_harness| = {worst:.4f}")
    print(f"worst entry-set match = {worst_match:.1f}%")
    print("NOTE: max_drawdown_halt disabled on BOTH sides — it is an absorbing\n"
          "      barrier that truncates a config's record at a path-dependent\n"
          "      point, making swept configs non-comparable. DD is a metric.")
    return 0 if worst < 0.05 else 1


if __name__ == "__main__":
    sys.exit(main())
