"""research.post.sweeps.cnk_nested_wf — nested walk-forward for crest_n_keel.

WHY THIS EXISTS
---------------
seq=46 walk-forwarded the seq=44 sweep leaders under qhf_harness and found good
temporal stability (H1 IS-OOS gap -0.02). That test could not be clean: the
harness applies FIXED parameters to every fold, and those parameters were
selected from a sweep over the full history, which contains every fold. The
selection saw the test data.

This module removes that leak. For each fold it re-runs the FULL grid on the
TRAINING window only, applies the gates, selects a leader from training data
alone, and then evaluates that leader once on the following, untouched test
window. What is being validated is therefore the SELECTION PROCEDURE, not a
configuration -- which is the question the Deflated Sharpe haircut tries to
answer analytically.

Nothing about mode or direction is fixed in advance. Restricting the grid to
"momentum long-only" would re-import a conclusion drawn from the full history
and reintroduce the leak in a subtler form, so every fold chooses freely across
both entry modes and all three direction settings.

THREE THINGS ARE MEASURED PER FOLD
1. `selected`  -- the config training picked, and its test-window result. This
   is the honest out-of-sample number.
2. `pool`      -- a random sample of OTHER configs that also cleared the gates
   in training, evaluated on the same test window. If picking the best in
   training does not beat picking any qualifying config, the ranking is noise.
   This is the control that matters.
3. `fixed`     -- the seq=44 full-history leader for this timeframe on the same
   test window, for direct comparison with seq=46 and as a leakage estimate.

Usage:
    python -m research.post.sweeps.cnk_nested_wf --tf H1
    python -m research.post.sweeps.cnk_nested_wf --tf H4 --time-one-fold
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
from research.post.sweeps.run_cnk_sweep import (
    HMA_PERIODS, ATR_PERIODS, MIN_ATRS, DIRECTIONS, STOCH_KS, ZONES,
    SL_MULTS, TP_MULTS, TRAIL_MULTS, STOCH_D, STOCH_SMOOTH, RISK_PCT, OUT_DIR)

RANDOM_SEED = 20260820
POOL_SAMPLE = 50          # gate-passers sampled per fold for the NK2 control

# Fold geometry mirrors the seq=46 harness run so the two are comparable.
WINDOWS = {"H1": ("1460D", "365D", "365D"), "H4": ("1825D", "365D", "365D")}

# Gates. PF / DD / Sharpe are identical to seq=44. The trade floor is scaled to
# the training window -- 100 trades over 21.6 years is ~4.6/year, and applying
# the absolute number to a 4-year window would be a far harsher gate than the
# sweep used. A hard minimum keeps a Sharpe from being computed on noise.
GATES_PF, GATES_DD, GATES_SR = 1.20, 0.30, 0.0
TRADE_FLOOR_PER_YEAR = 100.0 / 21.6
TRADE_FLOOR_MIN = 30

# seq=44 full-history leaders, for the `fixed` comparison arm.
FIXED_LEADER = {
    "H1": dict(mode="momentum", hma=55, atr=14, stoch_k=0, zone=None,
               sl=0.0, tp=0.0, trail=3.0, direction="long", min_atr=0.0),
    "H4": dict(mode="momentum", hma=13, atr=7, stoch_k=0, zone=None,
               sl=0.0, tp=0.0, trail=1.5, direction="long", min_atr=0.0),
}

_G: dict = {}


def _units() -> list[tuple]:
    pull = [("pullback", h, a, k)
            for h, a, k in itertools.product(HMA_PERIODS, ATR_PERIODS, STOCH_KS)]
    mom = [("momentum", h, a, None)
           for h, a in itertools.product(HMA_PERIODS, ATR_PERIODS)]
    return pull + mom


def _init_worker(bars):
    _G["bars"] = bars


def _sim_one(bars, cfg: dict) -> dict:
    """Simulate one fully-specified config on `bars`."""
    hma_v = E.hma(bars.close, cfg["hma"])
    atr_v = E.atr(bars.high, bars.low, bars.close, cfg["atr"])
    if cfg["mode"] == "pullback":
        k, d = E.stochastic(bars.high, bars.low, bars.close,
                            cfg["stoch_k"], STOCH_D, STOCH_SMOOTH)
        lo_s, sh_s = E.pullback_signals(bars, hma_v, k, d,
                                        cfg["zone"][0], cfg["zone"][1])
    else:
        lo_s, sh_s = E.momentum_signals(bars, hma_v)
    direc = cfg["direction"]
    sim = E.simulate(bars, cfg["mode"], hma_v, atr_v, lo_s, sh_s,
                     enable_long=direc in ("both", "long"),
                     enable_short=direc in ("both", "short"),
                     sl_mult=cfg["sl"], tp_mult=cfg["tp"], trail_mult=cfg["trail"],
                     risk_pct=RISK_PCT, min_atr=cfg["min_atr"], max_dd_halt=1.0)
    m = E.metrics(sim, basis="price")
    ma = E.metrics(sim, basis="account")
    return {"n_trades": m["n_trades"], "sharpe": m["sharpe"],
            "max_dd": m["max_dd"], "profit_factor": m["profit_factor"],
            "win_rate": m["win_rate"], "cagr_acct": ma["cagr"],
            "max_dd_acct": ma["max_dd"]}


def _eval_unit(unit) -> list[dict]:
    """Evaluate every config in one grid unit on the worker's training bars."""
    mode, hp, ap, sk = unit
    bars = _G["bars"]
    hma_v = E.hma(bars.close, hp)
    atr_v = E.atr(bars.high, bars.low, bars.close, ap)
    out: list[dict] = []
    if mode == "pullback":
        k, d = E.stochastic(bars.high, bars.low, bars.close, sk, STOCH_D, STOCH_SMOOTH)
        for zone in ZONES:
            lo_s, sh_s = E.pullback_signals(bars, hma_v, k, d, zone[0], zone[1])
            for direc in DIRECTIONS:
                for sl, tp, ma_ in itertools.product(SL_MULTS, TP_MULTS, MIN_ATRS):
                    sim = E.simulate(bars, "pullback", hma_v, atr_v, lo_s, sh_s,
                                     enable_long=direc in ("both", "long"),
                                     enable_short=direc in ("both", "short"),
                                     sl_mult=sl, tp_mult=tp, trail_mult=0.0,
                                     risk_pct=RISK_PCT, min_atr=ma_, max_dd_halt=1.0)
                    m = E.metrics(sim, basis="price")
                    out.append({"mode": "pullback", "hma": hp, "atr": ap,
                                "stoch_k": sk, "zone": zone, "sl": sl, "tp": tp,
                                "trail": 0.0, "direction": direc, "min_atr": ma_,
                                "n_trades": m["n_trades"], "sharpe": m["sharpe"],
                                "max_dd": m["max_dd"],
                                "profit_factor": m["profit_factor"]})
    else:
        lo_s, sh_s = E.momentum_signals(bars, hma_v)
        for direc in DIRECTIONS:
            for trail, ma_ in itertools.product(TRAIL_MULTS, MIN_ATRS):
                sim = E.simulate(bars, "momentum", hma_v, atr_v, lo_s, sh_s,
                                 enable_long=direc in ("both", "long"),
                                 enable_short=direc in ("both", "short"),
                                 sl_mult=0.0, tp_mult=0.0, trail_mult=trail,
                                 risk_pct=RISK_PCT, min_atr=ma_, max_dd_halt=1.0)
                m = E.metrics(sim, basis="price")
                out.append({"mode": "momentum", "hma": hp, "atr": ap,
                            "stoch_k": 0, "zone": None, "sl": 0.0, "tp": 0.0,
                            "trail": trail, "direction": direc, "min_atr": ma_,
                            "n_trades": m["n_trades"], "sharpe": m["sharpe"],
                            "max_dd": m["max_dd"],
                            "profit_factor": m["profit_factor"]})
    return out


def _folds(df: pd.DataFrame, tf: str) -> list[tuple]:
    train, test, step = (pd.Timedelta(x) for x in WINDOWS[tf])
    out, start = [], df.index[0]
    while True:
        tr_end = start + train
        te_end = tr_end + test
        if te_end > df.index[-1]:
            break
        out.append((start, tr_end, te_end))
        start = start + step
    return out


def _cfg_of(row: dict) -> dict:
    return {k: row[k] for k in ("mode", "hma", "atr", "stoch_k", "zone",
                                "sl", "tp", "trail", "direction", "min_atr")}


def _label(c: dict) -> str:
    if c["mode"] == "momentum":
        return (f"momentum/{c['direction']} hma{c['hma']} atr{c['atr']} "
                f"trail{c['trail']:g} minATR{c['min_atr']:g}")
    return (f"pullback/{c['direction']} hma{c['hma']} atr{c['atr']} "
            f"k{c['stoch_k']} z{int(c['zone'][0])}/{int(c['zone'][1])} "
            f"sl{c['sl']:g} tp{c['tp']:g} minATR{c['min_atr']:g}")


def run_fold(df: pd.DataFrame, tf: str, fold, workers: int, rng) -> dict:
    tr_start, tr_end, te_end = fold
    train_df = df.loc[(df.index >= tr_start) & (df.index < tr_end)]
    test_df = df.loc[(df.index >= tr_end) & (df.index < te_end)]
    train_bars, test_bars = E.Bars(train_df), E.Bars(test_df)
    train_years = (tr_end - tr_start).days / 365.25
    floor = max(TRADE_FLOOR_MIN, int(round(TRADE_FLOOR_PER_YEAR * train_years)))

    t0 = time.time()
    rows: list[dict] = []
    with Pool(workers, initializer=_init_worker, initargs=(train_bars,)) as pool:
        for res in pool.imap_unordered(_eval_unit, _units()):
            rows.extend(res)
    tr = pd.DataFrame(rows)
    passers = tr[(tr.n_trades >= floor) & (tr.profit_factor >= GATES_PF)
                 & (tr.max_dd <= GATES_DD) & (tr.sharpe > GATES_SR)]

    out = {
        "train_start": str(tr_start.date()), "train_end": str(tr_end.date()),
        "test_end": str(te_end.date()), "train_years": round(train_years, 2),
        "trade_floor": floor, "n_grid": int(len(tr)),
        "n_passers": int(len(passers)), "seconds": round(time.time() - t0, 1),
    }
    if passers.empty:
        out["selected"] = None
        return out

    best = passers.sort_values("sharpe", ascending=False).iloc[0]
    cfg = _cfg_of(best)
    te = _sim_one(test_bars, cfg)
    out["selected"] = {
        "config": _label(cfg), "mode": cfg["mode"], "direction": cfg["direction"],
        "train_sharpe": float(best["sharpe"]), "train_trades": int(best["n_trades"]),
        "oos_sharpe": te["sharpe"], "oos_trades": te["n_trades"],
        "oos_max_dd": te["max_dd"], "oos_profit_factor": te["profit_factor"],
        "oos_cagr_acct": te["cagr_acct"],
    }
    # NK2 control: other configs that also cleared the training gates.
    idx = rng.choice(len(passers), size=min(POOL_SAMPLE, len(passers)),
                     replace=False)
    pool_sh = []
    for i in idx:
        r = passers.iloc[int(i)]
        pool_sh.append(_sim_one(test_bars, _cfg_of(r))["sharpe"])
    pool_sh = np.asarray([s for s in pool_sh if np.isfinite(s)], float)
    out["pool"] = {
        "n": int(pool_sh.size),
        "mean": float(pool_sh.mean()) if pool_sh.size else None,
        "median": float(np.median(pool_sh)) if pool_sh.size else None,
        "pct_selected_beats": (float((pool_sh < te["sharpe"]).mean() * 100)
                               if pool_sh.size else None),
    }
    fx = _sim_one(test_bars, FIXED_LEADER[tf])
    out["fixed"] = {"oos_sharpe": fx["sharpe"], "oos_trades": fx["n_trades"]}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tf", choices=["H1", "H4"], required=True)
    ap.add_argument("--workers", type=int, default=default_workers())
    ap.add_argument("--time-one-fold", action="store_true",
                    help="Run only the first fold and report timing. Prints no "
                         "selection result, so it cannot inform the design.")
    args = ap.parse_args()

    df = load(args.tf)
    folds = _folds(df, args.tf)
    rng = np.random.default_rng(RANDOM_SEED)
    print(f"[{args.tf}] {len(df):,} bars {df.index[0].date()}..{df.index[-1].date()} "
          f"| {len(folds)} folds | grid {len(_units())} units", flush=True)

    if args.time_one_fold:
        t0 = time.time()
        r = run_fold(df, args.tf, folds[0], args.workers, rng)
        el = time.time() - t0
        print(f"fold 1: {r['n_grid']:,} configs in {el:.0f}s "
              f"({r['n_passers']:,} passers, floor {r['trade_floor']}) "
              f"-> projected {el * len(folds) / 60:.0f} min for {len(folds)} folds")
        return 0

    results = []
    for i, fold in enumerate(folds, 1):
        r = run_fold(df, args.tf, fold, args.workers, rng)
        results.append(r)
        s = r.get("selected")
        if s:
            print(f"  fold {i:>2}/{len(folds)} test->{r['test_end']}  "
                  f"train SR {s['train_sharpe']:+.3f} -> OOS SR {s['oos_sharpe']:+.3f}  "
                  f"({s['oos_trades']:>4} tr)  pool med "
                  f"{r['pool']['median']:+.3f}  fixed {r['fixed']['oos_sharpe']:+.3f}  "
                  f"| {s['config']}  [{r['seconds']:.0f}s]", flush=True)
        else:
            print(f"  fold {i:>2}/{len(folds)} test->{r['test_end']}  "
                  f"NO CONFIG CLEARED TRAINING GATES  [{r['seconds']:.0f}s]", flush=True)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUT_DIR / f"cnk_nested_wf_{args.tf}.json").write_text(
            json.dumps({"timeframe": args.tf, "windows": WINDOWS[args.tf],
                        "gates": {"pf": GATES_PF, "dd": GATES_DD, "sharpe": GATES_SR,
                                  "trade_floor_per_year": TRADE_FLOOR_PER_YEAR,
                                  "trade_floor_min": TRADE_FLOOR_MIN},
                        "pool_sample": POOL_SAMPLE, "seed": RANDOM_SEED,
                        "folds": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
