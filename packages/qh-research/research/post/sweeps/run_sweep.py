"""research.post.sweeps.run_sweep — exhaustive parameter + timeframe sweep for zerolag_chandelier.

zerolag_chandelier was KILLED at the signal-edge stage (log seq=19/20): combined
E-Ratio 0.9813, p=0.772, flat at every forward window. That verdict is about the
ENTRY. This sweep asks a different question: does any (parameter, timeframe)
configuration produce a profitable *strategy* once the chandelier trailing exit
is included? Entry edge and strategy edge are distinct claims.

Design notes that matter for reading the output
-----------------------------------------------
1. This is an IN-SAMPLE sweep over the full history. The top of a grid this
   size is selection-inflated by construction. The ranking is a description of
   the parameter surface, not a recommendation. `n_configs` from this sweep is
   the honest N for any subsequent Deflated Sharpe calculation.
2. `max_drawdown_halt` is DISABLED. In the live strategy it is an absorbing
   barrier: once tripped the config never trades again, truncating its record
   at a path-dependent point and making configs non-comparable. Drawdown is
   reported as a metric instead.
3. Two return bases are reported and they are NOT interchangeable:
     *_px   per-unit price return -- reproduces research.engines.btpy_runner
            exactly (validated to 0.0015 Sharpe by run_parity). Size-agnostic:
            position sizing has no effect on it.
     *_acct per-trade PnL / equity at entry -- the true account return,
            reflecting the ATR sizer and the 0.01-0.10 lot clamp.
   Because the *_px basis is size-agnostic, the sweep fixes risk_pct=0.01;
   varying it cannot change any *_px metric.

Usage:
    python -m research.post.sweeps.run_sweep --tf H1
    python -m research.post.sweeps.run_sweep --all
"""
from __future__ import annotations

import argparse
import itertools
import json
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd

from research.post.sweeps import default_workers
from research.post.sweeps import zlch_engine as E
from research.post.sweeps.data import RESAMPLE_RULE, TIMEFRAMES, load

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = REPO_ROOT / "research" / "post" / "artifacts"

# --------------------------------------------------------------------------- #
# The grid                                                                     #
# --------------------------------------------------------------------------- #
ATR_PERIODS = [5, 8, 10, 14, 20, 27, 34, 50]
ATR_MULTS = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
ZLSMA_LENS = [20, 32, 50, 80, 120]
DIRECTIONS = ["both", "long", "short"]
MIN_ATRS = [0.0, 1.0]
RISK_PCT = 0.01

_G: dict = {}


def _init_worker(tf: str, bars: E.Bars, bias_cache: dict, n: int):
    _G["tf"] = tf
    _G["bars"] = bars
    _G["bias"] = bias_cache
    _G["n"] = n


def _bias_keys(tf: str) -> list[tuple[str | None, int | None]]:
    keys: list[tuple[str | None, int | None]] = [(None, None)]
    for btf in TIMEFRAMES[tf]["bias"]:
        for z in ZLSMA_LENS:
            keys.append((btf, z))
    return keys


def _eval_unit(args) -> list[dict]:
    """One (atr_period, atr_mult) unit: compute direction once, sweep the rest."""
    period, mult = args
    bars: E.Bars = _G["bars"]
    n = _G["n"]
    tf = _G["tf"]

    direction = E.chandelier_direction(bars.high_s, bars.low_s, bars.close_s,
                                       period, mult)
    atr_vals = E.wilder_atr(bars.high_s, bars.low_s, bars.close_s, period)
    ones = np.ones(n, dtype=bool)
    rows: list[dict] = []

    for (btf, zlen) in _bias_keys(tf):
        if btf is None:
            rise, fall = ones, ones
        else:
            rise, fall = _G["bias"][(btf, zlen)]
        for direc in DIRECTIONS:
            en_long = direc in ("both", "long")
            en_short = direc in ("both", "short")
            for min_atr in MIN_ATRS:
                sim = E.simulate(bars, direction, atr_vals, rise, fall,
                                 en_long, en_short, mult, RISK_PCT, min_atr,
                                 max_dd_halt=1.0)
                mpx = E.metrics(sim, basis="price")
                mac = E.metrics(sim, basis="account")
                rows.append({
                    "timeframe": tf, "atr_period": period, "atr_mult": mult,
                    "bias_tf": btf or "none", "zlsma_len": zlen or 0,
                    "direction": direc, "min_atr": min_atr,
                    "n_trades": mpx["n_trades"],
                    "trades_per_year": mpx["trades_per_year"],
                    "sharpe_px": mpx["sharpe"], "max_dd_px": mpx["max_dd"],
                    "profit_factor_px": mpx["profit_factor"],
                    "win_rate": mpx["win_rate"],
                    "expectancy_px": mpx["expectancy"],
                    "sharpe_acct": mac["sharpe"], "max_dd_acct": mac["max_dd"],
                    "profit_factor_acct": mac["profit_factor"],
                    "total_return_acct": mac["total_return"],
                    "cagr_acct": mac["cagr"],
                    "equity_final": sim["equity_final"],
                })
    return rows


def sweep_tf(tf: str, workers: int) -> pd.DataFrame:
    t0 = time.time()
    df = load(tf)
    bars = E.Bars(df)
    n = len(df)

    bias_cache: dict = {}
    for btf in TIMEFRAMES[tf]["bias"]:
        for z in ZLSMA_LENS:
            bias_cache[(btf, z)] = E.htf_bias(bars.close_s, df.index,
                                              RESAMPLE_RULE[btf], z)

    units = list(itertools.product(ATR_PERIODS, ATR_MULTS))
    n_cfg = len(units) * len(_bias_keys(tf)) * len(DIRECTIONS) * len(MIN_ATRS)
    print(f"[{tf}] {n:,} bars {df.index[0].date()}->{df.index[-1].date()} | "
          f"{len(units)} direction units x {n_cfg // len(units)} = {n_cfg:,} configs "
          f"| {workers} workers", flush=True)

    rows: list[dict] = []
    with Pool(workers, initializer=_init_worker,
              initargs=(tf, bars, bias_cache, n)) as pool:
        for i, res in enumerate(pool.imap_unordered(_eval_unit, units), 1):
            rows.extend(res)
            print(f"  [{tf}] unit {i}/{len(units)}  ({time.time()-t0:.0f}s)", flush=True)

    out = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"zlch_sweep_{tf}.csv"
    out.to_csv(path, index=False)
    print(f"[{tf}] done {len(out):,} configs in {time.time()-t0:.0f}s -> {path.name}",
          flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", action="append", help="timeframe(s); repeatable")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--workers", type=int, default=default_workers())
    args = ap.parse_args()

    tfs = list(TIMEFRAMES) if args.all else (args.tf or ["H1"])
    for tf in tfs:
        sweep_tf(tf, args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
