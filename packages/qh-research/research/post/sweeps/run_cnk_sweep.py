"""research.post.sweeps.run_cnk_sweep — exhaustive parameter + timeframe sweep
for crest_n_keel, covering BOTH entry modes.

Why both modes
--------------
crest_n_keel exists in the log twice. seq=0 is the deployed PULLBACK entry
(HMA slope + price side + stochastic cross out of the oversold/overbought
zone, fixed ATR bracket) whose walk-forward at seq=29 returned OOS Sharpe
0.27-0.41 / DSR 0.03-0.11 and contradicted a seeded 1.76 that never had a
backing artifact. seq=35 is the MOMENTUM variant (HMA slope flip, long-only,
ATR chandelier trail) found by TradingView search, which at seq=36 passed 4/5
gates on walk-forward but failed DSR (0.061 at N=20).

Sweeping only one of them would answer half the question. The interesting
comparison is whether the momentum entry's advantage is a property of the
whole parameter surface or an artifact of the single config that was searched
for on TradingView.

Design notes that matter for reading the output
-----------------------------------------------
1. IN-SAMPLE sweep over full history. The top of a grid this size is
   selection-inflated by construction. The ranking describes the parameter
   surface; it is not a recommendation. `n_configs` is the honest N for any
   subsequent Deflated Sharpe calculation.
2. `max_drawdown_halt` is DISABLED (harness default 0.30). It is an absorbing
   barrier: once tripped the config never trades again, truncating its record
   at a path-dependent point and making configs non-comparable. Drawdown is
   reported as a metric instead.
3. Two return bases are reported and they are NOT interchangeable:
     *_px   per-unit price return -- reproduces qhf.engines.btpy_runner
            (validated to 0.0031 Sharpe / 100% entry match by
            run_cnk_parity). Size-agnostic: position sizing cannot move it.
     *_acct per-trade PnL / equity at entry -- true account return, reflecting
            the ATR sizer and the 0.01-0.10 lot clamp.
   risk_pct is fixed at the strategy's own 0.02; it cannot change any *_px
   metric.
4. `min_atr` is progressively DEGENERATE as the timeframe slows: D1 ATR is
   far above every tested floor, so the dimension collapses there. Reported,
   not silently dropped.
5. MOMENTUM is long-only upstream. The sweep includes short and both so the
   long-only choice is tested rather than assumed.

Usage:
    python -m research.post.sweeps.run_cnk_sweep --tf H1
    python -m research.post.sweeps.run_cnk_sweep --all
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
from research.post.sweeps import cnk_engine as E
from research.post.sweeps.data import load

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = REPO_ROOT / "research" / "data" / "crest_n_keel"

# ---- grid ---------------------------------------------------------------- #
HMA_PERIODS = [13, 21, 34, 55, 89, 144]
ATR_PERIODS = [7, 14, 21]
MIN_ATRS = [0.0, 1.0, 2.0]
DIRECTIONS = ["both", "long", "short"]

# pullback-only
STOCH_KS = [9, 14, 21]
ZONES = [(20.0, 80.0), (25.0, 75.0), (30.0, 70.0)]
SL_MULTS = [1.0, 1.5, 2.0, 3.0]
TP_MULTS = [1.5, 2.0, 3.0, 4.0, 5.0]
STOCH_D, STOCH_SMOOTH = 3, 3

# momentum-only
TRAIL_MULTS = [1.5, 2.0, 2.5, 3.0, 4.0, 5.0]

RISK_PCT = 0.02

_G: dict = {}


def _init_worker(tf: str, bars: E.Bars):
    _G["tf"] = tf
    _G["bars"] = bars


def _units(tf: str) -> list[tuple]:
    u = [("pullback", h, a, k)
         for h in HMA_PERIODS for a in ATR_PERIODS for k in STOCH_KS]
    u += [("momentum", h, a, None) for h in HMA_PERIODS for a in ATR_PERIODS]
    return u


def _row(tf, mode, hp, ap, sk, zone, sl, tp, trail, direc, min_atr, sim):
    mpx = E.metrics(sim, basis="price")
    mac = E.metrics(sim, basis="account")
    return {
        "timeframe": tf, "mode": mode, "hma_period": hp, "atr_period": ap,
        "stoch_k": sk or 0, "oversold": zone[0] if zone else 0.0,
        "overbought": zone[1] if zone else 0.0,
        "sl_mult": sl, "tp_mult": tp, "trail_mult": trail,
        "direction": direc, "min_atr": min_atr,
        "n_trades": mpx["n_trades"], "trades_per_year": mpx["trades_per_year"],
        "sharpe_px": mpx["sharpe"], "max_dd_px": mpx["max_dd"],
        "profit_factor_px": mpx["profit_factor"], "win_rate": mpx["win_rate"],
        "expectancy_px": mpx["expectancy"],
        "sharpe_acct": mac["sharpe"], "max_dd_acct": mac["max_dd"],
        "profit_factor_acct": mac["profit_factor"],
        "total_return_acct": mac["total_return"], "cagr_acct": mac["cagr"],
        "equity_final": sim["equity_final"],
    }


def _eval_unit(unit) -> list[dict]:
    mode, hp, ap, sk = unit
    tf, bars = _G["tf"], _G["bars"]
    hma_v = E.hma(bars.close, hp)
    atr_v = E.atr(bars.high, bars.low, bars.close, ap)
    rows: list[dict] = []

    if mode == "pullback":
        k, d = E.stochastic(bars.high, bars.low, bars.close, sk, STOCH_D, STOCH_SMOOTH)
        for zone in ZONES:
            lo_s, sh_s = E.pullback_signals(bars, hma_v, k, d, zone[0], zone[1])
            for direc in DIRECTIONS:
                en_l, en_s = direc in ("both", "long"), direc in ("both", "short")
                for sl, tp, min_atr in itertools.product(SL_MULTS, TP_MULTS, MIN_ATRS):
                    sim = E.simulate(bars, "pullback", hma_v, atr_v, lo_s, sh_s,
                                     enable_long=en_l, enable_short=en_s,
                                     sl_mult=sl, tp_mult=tp, trail_mult=0.0,
                                     risk_pct=RISK_PCT, min_atr=min_atr,
                                     max_dd_halt=1.0)
                    rows.append(_row(tf, mode, hp, ap, sk, zone, sl, tp, 0.0,
                                     direc, min_atr, sim))
    else:
        lo_s, sh_s = E.momentum_signals(bars, hma_v)
        for direc in DIRECTIONS:
            en_l, en_s = direc in ("both", "long"), direc in ("both", "short")
            for trail, min_atr in itertools.product(TRAIL_MULTS, MIN_ATRS):
                sim = E.simulate(bars, "momentum", hma_v, atr_v, lo_s, sh_s,
                                 enable_long=en_l, enable_short=en_s,
                                 sl_mult=0.0, tp_mult=0.0, trail_mult=trail,
                                 risk_pct=RISK_PCT, min_atr=min_atr,
                                 max_dd_halt=1.0)
                rows.append(_row(tf, mode, hp, ap, None, None, 0.0, 0.0, trail,
                                 direc, min_atr, sim))
    return rows


def sweep_tf(tf: str, workers: int) -> pd.DataFrame:
    t0 = time.time()
    df = load(tf)
    bars = E.Bars(df)
    units = _units(tf)
    rows: list[dict] = []
    with Pool(workers, initializer=_init_worker, initargs=(tf, bars)) as pool:
        for i, res in enumerate(pool.imap_unordered(_eval_unit, units), 1):
            rows.extend(res)
            print(f"  [{tf}] unit {i}/{len(units)}  rows={len(rows):,}  "
                  f"{time.time() - t0:.0f}s", flush=True)
    out = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"cnk_sweep_{tf}.csv"
    out.to_csv(path, index=False)
    print(f"[{tf}] {len(out):,} configs, {df.index[0].date()}..{df.index[-1].date()}, "
          f"{time.time() - t0:.0f}s -> {path}", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tf", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--workers", type=int, default=default_workers())
    args = ap.parse_args()

    tfs = ["D1", "H4", "H1", "M15", "M5"] if args.all else [args.tf or "H1"]
    summary = {}
    for tf in tfs:
        d = sweep_tf(tf, args.workers)
        summary[tf] = {"n_configs": int(len(d)),
                       "n_pullback": int((d["mode"] == "pullback").sum()),
                       "n_momentum": int((d["mode"] == "momentum").sum())}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    total = sum(v["n_configs"] for v in summary.values())
    (OUT_DIR / "cnk_sweep_summary.json").write_text(
        json.dumps({"per_timeframe": summary, "n_configs_total": total,
                    "risk_pct": RISK_PCT,
                    "grid": {"hma_period": HMA_PERIODS, "atr_period": ATR_PERIODS,
                             "min_atr": MIN_ATRS, "direction": DIRECTIONS,
                             "stoch_k": STOCH_KS, "zones": ZONES,
                             "sl_mult": SL_MULTS, "tp_mult": TP_MULTS,
                             "trail_mult": TRAIL_MULTS,
                             "stoch_d": STOCH_D, "stoch_smooth_k": STOCH_SMOOTH}},
                   indent=2))
    print(f"\nTOTAL {total:,} configs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
