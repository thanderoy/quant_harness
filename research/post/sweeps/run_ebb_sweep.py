"""research.post.sweeps.run_ebb_sweep — exhaustive parameter + timeframe sweep for ebb_n_flow.

ebb_n_flow was KILLED at the in-sample backtest stage (log seq=8/9/10) on negative
gross expectancy. Its edge_gate_role is DIAGNOSTIC, so the flat entry E-Ratio (0.97)
was never the kill -- house rules say a mean-reversion entry is carried by its exit.
The recorded kill note reads: "Gold's secular uptrend punishes symmetric fades; MR
sleeve needs asymmetric treatment of long vs short."

This sweep tests that stated diagnosis directly by making direction a first-class
grid dimension, alongside every other parameter and five entry timeframes.

Same conventions as the zerolag_chandelier sweep so the two are comparable:
  - in-sample over the full history; the ranking describes a surface, not a pick
  - two return bases, *_px (harness-identical, size-agnostic) and *_acct
  - risk_pct fixed at 0.01 (cannot affect any *_px metric)

Usage:
    python -m research.post.sweeps.run_ebb_sweep --tf H4
    python -m research.post.sweeps.run_ebb_sweep --all
"""
from __future__ import annotations

import argparse
import itertools
import time
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

from research.post.sweeps import default_workers
from research.post.sweeps import ebb_engine as E
from research.post.sweeps.data import TIMEFRAMES, load
from research.post.sweeps.zlch_engine import metrics

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = REPO_ROOT / "research" / "data" / "ebb_n_flow"

BB_NS = [10, 14, 20, 30, 50]
BB_KS = [1.5, 2.0, 2.5, 3.0]
ER_MAXES = [0.20, 0.30, 0.40, 1.00]        # 1.00 disables the regime gate
SL_MULTS = [0.5, 1.0, 1.5, 2.0, 3.0]
TIME_STOPS = [4, 8, 16, 32]
DIRECTIONS = ["both", "long", "short"]
# Fixed at the registered values.
ER_N, ATR_N, ATR_FLOOR, ATR_SPIKE, MIN_R, RISK_PCT = 10, 14, 1.0, 2.5, 0.5, 0.01

_G: dict = {}


def _sessions_for(tf: str) -> list[bool]:
    # D1 bars are all stamped hour 0, so the 08-17 UTC filter would block every
    # entry. Session is not a meaningful dimension there.
    return [False] if tf == "D1" else [True, False]


def _init_worker(tf: str, bars: E.EbbBars):
    _G["tf"] = tf
    _G["bars"] = bars


def _eval_unit(args) -> list[dict]:
    bb_n, bb_k = args
    bars: E.EbbBars = _G["bars"]
    tf = _G["tf"]
    mid, up, lo, er, atr = E.build_indicators(bars, bb_n, bb_k, ER_N, ATR_N)
    rows: list[dict] = []
    for er_max, sl_mult, ts_bars, direc, use_sess in itertools.product(
            ER_MAXES, SL_MULTS, TIME_STOPS, DIRECTIONS, _sessions_for(tf)):
        sim = E.simulate(bars, mid, up, lo, er, atr,
                         er_max=er_max, sl_atr_mult=sl_mult, atr_floor=ATR_FLOOR,
                         time_stop_bars=ts_bars, atr_spike_mult=ATR_SPIKE,
                         min_r=MIN_R,
                         enable_long=direc in ("both", "long"),
                         enable_short=direc in ("both", "short"),
                         use_session=use_sess, risk_pct=RISK_PCT)
        mpx = metrics(sim, basis="price")
        mac = metrics(sim, basis="account")
        n_long = int((sim["dirs"] == 1).sum()) if sim["n_trades"] else 0
        rows.append({
            "timeframe": tf, "bb_n": bb_n, "bb_k": bb_k, "er_max": er_max,
            "sl_atr_mult": sl_mult, "time_stop_bars": ts_bars,
            "direction": direc, "session": "rth" if use_sess else "all",
            "n_trades": mpx["n_trades"], "n_long": n_long,
            "trades_per_year": mpx["trades_per_year"],
            "sharpe_px": mpx["sharpe"], "max_dd_px": mpx["max_dd"],
            "profit_factor_px": mpx["profit_factor"], "win_rate": mpx["win_rate"],
            "expectancy_px": mpx["expectancy"],
            "sharpe_acct": mac["sharpe"], "max_dd_acct": mac["max_dd"],
            "profit_factor_acct": mac["profit_factor"],
            "total_return_acct": mac["total_return"], "cagr_acct": mac["cagr"],
            "equity_final": sim["equity_final"],
        })
    return rows


def sweep_tf(tf: str, workers: int) -> pd.DataFrame:
    t0 = time.time()
    df = load(tf)
    bars = E.EbbBars(df)
    units = list(itertools.product(BB_NS, BB_KS))
    per_unit = (len(ER_MAXES) * len(SL_MULTS) * len(TIME_STOPS)
                * len(DIRECTIONS) * len(_sessions_for(tf)))
    print(f"[{tf}] {len(df):,} bars {df.index[0].date()}->{df.index[-1].date()} | "
          f"{len(units)} units x {per_unit} = {len(units)*per_unit:,} configs | "
          f"{workers} workers", flush=True)

    rows: list[dict] = []
    with Pool(workers, initializer=_init_worker, initargs=(tf, bars)) as pool:
        for i, res in enumerate(pool.imap_unordered(_eval_unit, units), 1):
            rows.extend(res)
            print(f"  [{tf}] unit {i}/{len(units)} ({time.time()-t0:.0f}s)", flush=True)

    out = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"ebb_sweep_{tf}.csv"
    out.to_csv(path, index=False)
    print(f"[{tf}] done {len(out):,} configs in {time.time()-t0:.0f}s -> {path.name}",
          flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tf", action="append")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--workers", type=int, default=default_workers())
    args = ap.parse_args()
    tfs = list(TIMEFRAMES) if args.all else (args.tf or ["H4"])
    for tf in tfs:
        sweep_tf(tf, args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
