"""research.post.sweeps.run_signal_sweep — sweep PRE-STAGE ENTRY SIGNALS.

Three registered ideas have a working signal generator but no strategy class,
so they were never swept: flood_tide (Donchian breakout, shelved at seq=32/34),
avwap_sweep_reclaim_m15 (seq=25/26, OPEN) and avwap_multibar_reclaim_m15
(seq=27-ish, OPEN). They stalled at the signal-edge stage because there is no
exit logic to backtest.

That is exactly what this sweeps. Per CLAUDE.md, a reclaim / mean-reversion
entry is EXPECTED to look flat on entry-only diagnostics because it is designed
to be carried by an asymmetric exit -- "the edge must live in the exit, point
robustness testing there". So the honest sweep for these is entry signal x EXIT
FAMILY, which asks whether ANY exit in a wide grid makes the entry viable.

The exit machinery is cnk_engine.simulate, unchanged and already parity-
validated: mode="pullback" is a fixed ATR bracket (sl_mult x tp_mult) and
mode="momentum" is an ATR chandelier trail. Feeding it foreign entry masks is
supported by design -- the signals are arguments, only the exit is selected by
`mode`. Costs, sizing and the two return bases are therefore identical to the
zlch/ebb/cnk/asqs sweeps and the numbers are directly comparable.

Read with seq=49: this is a surface characterisation. No configuration produced
here is promotable on the strength of topping a ranking.

Usage:
    python -m research.post.sweeps.run_signal_sweep --signal flood_tide
    python -m research.post.sweeps.run_signal_sweep --all --workers 7
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
OUT_DIR = REPO_ROOT / "research" / "data" / "signals"

# ---- FROZEN EXIT GRID (shared by every signal) ---------------------------- #
ATR_PERIODS = [7, 14, 21]
SL_MULTS = [1.0, 1.5, 2.0, 3.0]
TP_MULTS = [1.5, 2.0, 3.0, 4.0, 5.0]
TRAIL_MULTS = [1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
MIN_ATRS = [0.0, 1.0]
DIRECTIONS = ["both", "long", "short"]
RISK_PCT = 0.02

# ---- FROZEN ENTRY GRIDS (per signal) ------------------------------------- #
FLOOD_ENTRY_LENS = [20, 34, 55]
FLOOD_ER_THRESHOLDS = [0.0, 0.30]
FLOOD_HTF_EMA = [100, 200]

AVWAP_HMA = [30, 50]
AVWAP_SWEEP_ATR = [0.1, 0.2, 0.4]

_G: dict = {}


def _flood_units():
    return [("flood_tide", el, er, he) for el, er, he in
            itertools.product(FLOOD_ENTRY_LENS, FLOOD_ER_THRESHOLDS, FLOOD_HTF_EMA)]


def _avwap_units(name):
    return [(name, h, s, None) for h, s in
            itertools.product(AVWAP_HMA, AVWAP_SWEEP_ATR)]


SIGNALS = {
    "flood_tide": dict(tf="H1", units=_flood_units, volume=False),
    "avwap_sweep_reclaim": dict(tf="M15", units=lambda: _avwap_units("avwap_sweep_reclaim"),
                                volume=True),
    "avwap_multibar_reclaim": dict(tf="M15",
                                   units=lambda: _avwap_units("avwap_multibar_reclaim"),
                                   volume=True),
}


def _masks(unit) -> tuple[np.ndarray, np.ndarray]:
    """Entry masks for one signal-parameter unit, on the worker's bars."""
    name = unit[0]
    df = _G["df"]
    n = len(df)
    if name == "flood_tide":
        from research.pre.signals.flood_tide import (generate_signals,
                                                     FloodTideParams)
        _, el, er, he = unit
        p = FloodTideParams(entry_len=el, er_threshold=er, htf_ema_len=he)
        sig = generate_signals(df, _G["aux"], p)
        long_m = sig["entry_signal"].to_numpy(bool)
        return long_m, np.zeros(n, bool)          # breakout is long-only upstream
    if name == "avwap_sweep_reclaim":
        from research.pre.signals.avwap_sweep_reclaim_m15 import emit_signals
        _, hma, sw, _x = unit
        s = emit_signals(df, h1_hma_period=hma, sweep_threshold_atr_mult=sw)
    else:
        from research.pre.signals.avwap_multibar_reclaim_m15 import emit_signals
        _, hma, sw, _x = unit
        s = emit_signals(df, h1_hma_period=hma, sweep_threshold_atr_mult=sw)
    sg = s["signal"].to_numpy()
    dr = s["direction"].to_numpy()
    sg = sg.astype(bool) if sg.dtype != bool else sg
    if dr.dtype.kind in "OU":                       # strings
        long_m = sg & (dr == "long")
        short_m = sg & (dr == "short")
    else:
        long_m = sg & (np.nan_to_num(dr.astype(float)) > 0)
        short_m = sg & (np.nan_to_num(dr.astype(float)) < 0)
    return long_m, short_m


def _init_worker(name, df, aux):
    _G["name"], _G["df"], _G["aux"] = name, df, aux
    _G["bars"] = E.Bars(df)


def _row(name, unit, exit_family, ap, sl, tp, tr, direc, ma, sim) -> dict:
    mpx = E.metrics(sim, basis="price")
    mac = E.metrics(sim, basis="account")
    return {
        "signal": name, "timeframe": _G["tf"], "entry_p1": unit[1],
        "entry_p2": unit[2], "entry_p3": unit[3], "exit_family": exit_family,
        "atr_period": ap, "sl_mult": sl, "tp_mult": tp, "trail_mult": tr,
        "direction": direc, "min_atr": ma,
        "n_trades": mpx["n_trades"], "trades_per_year": mpx["trades_per_year"],
        "sharpe_px": mpx["sharpe"], "max_dd_px": mpx["max_dd"],
        "profit_factor_px": mpx["profit_factor"], "win_rate": mpx["win_rate"],
        "expectancy_px": mpx["expectancy"], "sharpe_acct": mac["sharpe"],
        "max_dd_acct": mac["max_dd"], "total_return_acct": mac["total_return"],
        "cagr_acct": mac["cagr"], "equity_final": sim["equity_final"],
    }


def _eval_unit(unit) -> list[dict]:
    name = unit[0]
    bars = _G["bars"]
    long_m, short_m = _masks(unit)
    rows: list[dict] = []
    for ap in ATR_PERIODS:
        atr_v = E.atr(bars.high, bars.low, bars.close, ap)
        # a foreign signal has no HMA; pass a finite dummy so the engine's
        # finite-indicator guard does not veto every bar.
        dummy = np.zeros(bars.n, float)
        for direc in DIRECTIONS:
            en_l, en_s = direc in ("both", "long"), direc in ("both", "short")
            if not (long_m.any() and en_l) and not (short_m.any() and en_s):
                continue
            for ma in MIN_ATRS:
                for sl, tp in itertools.product(SL_MULTS, TP_MULTS):
                    sim = E.simulate(bars, "pullback", dummy, atr_v, long_m, short_m,
                                     enable_long=en_l, enable_short=en_s,
                                     sl_mult=sl, tp_mult=tp, trail_mult=0.0,
                                     risk_pct=RISK_PCT, min_atr=ma, max_dd_halt=1.0)
                    rows.append(_row(name, unit, "bracket", ap, sl, tp, 0.0,
                                     direc, ma, sim))
                for tr in TRAIL_MULTS:
                    sim = E.simulate(bars, "momentum", dummy, atr_v, long_m, short_m,
                                     enable_long=en_l, enable_short=en_s,
                                     sl_mult=0.0, tp_mult=0.0, trail_mult=tr,
                                     risk_pct=RISK_PCT, min_atr=ma, max_dd_halt=1.0)
                    rows.append(_row(name, unit, "trail", ap, 0.0, 0.0, tr,
                                     direc, ma, sim))
    return rows


def sweep(name: str, workers: int) -> pd.DataFrame:
    spec = SIGNALS[name]
    tf = spec["tf"]
    t0 = time.time()
    df = load(tf, tz="server_eet", with_volume=spec["volume"])
    aux = load("H4", tz="server_eet") if name == "flood_tide" else None
    units = spec["units"]()
    _G["tf"] = tf
    rows: list[dict] = []
    with Pool(workers, initializer=_init_worker, initargs=(name, df, aux)) as pool:
        for i, res in enumerate(pool.imap_unordered(_eval_unit, units), 1):
            rows.extend(res)
            print(f"  [{name}] unit {i}/{len(units)}  rows={len(rows):,}  "
                  f"{time.time() - t0:.0f}s", flush=True)
    out = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"signal_sweep_{name}.csv"
    out.to_csv(path, index=False)
    print(f"[{name}] {len(out):,} configs, {time.time() - t0:.0f}s -> {path}", flush=True)
    return out


def main() -> int:
    ap_ = argparse.ArgumentParser(description=__doc__)
    ap_.add_argument("--signal", choices=list(SIGNALS))
    ap_.add_argument("--all", action="store_true")
    ap_.add_argument("--workers", type=int, default=default_workers())
    args = ap_.parse_args()
    names = list(SIGNALS) if args.all else [args.signal]
    total = 0
    done = []
    for nm in names:
        try:
            total += len(sweep(nm, args.workers))
            done.append(nm)
        except Exception as exc:                    # noqa: BLE001
            # One signal failing must not lose the others -- report and continue.
            print(f"[{nm}] FAILED: {type(exc).__name__}: {exc}", flush=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "signal_sweep_summary.json").write_text(json.dumps({
        "n_configs_total": total, "signals_completed": done,
        "exit_grid": {"atr_periods": ATR_PERIODS, "sl_mults": SL_MULTS,
                      "tp_mults": TP_MULTS, "trail_mults": TRAIL_MULTS,
                      "min_atrs": MIN_ATRS, "directions": DIRECTIONS},
        "risk_pct": RISK_PCT, "tz": "server_eet"}, indent=2))
    print(f"\nTOTAL {total:,} configs across {len(done)} signals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
