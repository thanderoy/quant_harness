"""research.post.sweeps.zlch_nested_wf — nested walk-forward for zerolag_chandelier.

WHY THIS EXISTS
---------------
seq=40 swept 18,480 configs in-sample and found the H4 long-only region clears
K1 (random-entry control, p=0.000), K2 (Calmar 0.41 vs buy-and-hold 0.28) and
K4 (plateau, 9/9 neighbours positive), failing only K3, the Deflated Sharpe
haircut at grid N. seq=39's frozen stopping rule says the ONLY legitimate next
step is an out-of-sample walk-forward -- not a finer grid. That step was never
taken, so zlch's honest status is UNTESTED OUT-OF-SAMPLE, not refuted, and it
is the only candidate in the corpus in that position (see log seq=64).

seq=63/65 then showed the K3 haircut was measuring the wrong thing: on a
long-biased rule DSR benchmarks against zero while the true null mean is
positive (drift capture), the estimated-Var(SR) branch was the lenient one, and
the gate had power 0.061 at the effect sizes in play. So K3 alone is not a
verdict. What zlch has never had is the test that actually killed
crest_n_keel at seq=49.

WHAT THIS MEASURES, AND WHY IT IS THE DECISIVE ONE
--------------------------------------------------
For each fold the FULL grid is re-run on the TRAINING window only, the seq=39
gates are applied, the highest training Sharpe is selected, and that single
config is evaluated once on the following untouched test window. Three arms per
fold, exactly as seq=47/49:

1. `selected` -- what training picked, scored out-of-sample. The honest number.
2. `pool`     -- other configs that ALSO cleared the training gates, scored on
   the same test window. If picking the best in training does not beat picking
   any qualifying config, training rank is noise. THIS IS THE DECISIVE ARM: it
   is what failed at seq=49 (p=0.430) and killed crest_n_keel.
3. `fixed`    -- the seq=40 full-history leader on the same test window. Its
   excess over `selected` is a direct estimate of the lookahead in seq=40's
   in-sample ranking, the quantity seq=49 measured at 0.68-0.81 Sharpe for cnk.

Direction, bias timeframe, ZLSMA length and min_atr are NOT fixed in advance.
Restricting to "H4 long-only, bias=none" would re-import seq=40's full-history
conclusion and reintroduce the leak in a subtler form -- the exact error
seq=64 corrected for seq=36/46.

Usage:
    python -m research.post.sweeps.zlch_nested_wf --tf H4 --time-one-fold
    python -m research.post.sweeps.zlch_nested_wf --tf H4
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
from research.post.sweeps.run_sweep import (
    ATR_PERIODS, ATR_MULTS, ZLSMA_LENS, DIRECTIONS, MIN_ATRS, RISK_PCT, OUT_DIR)

RANDOM_SEED = 20260827

# Fixed absolute origin for HTF resample bins. Every fold slices the history at
# a different date, so without a pinned origin the weekly/daily bins would move
# between folds and the "same" config would not mean the same thing in fold 1
# and fold 9. Monday before the first bar. Verified against the seq=40 sweep:
# reproduces H1 exactly on all three bias families and H4 exactly on none/D1;
# see the registration note for the H4 W1 caveat.
BIAS_ORIGIN = pd.Timestamp("2004-06-07 00:00:00", tz="UTC")
POOL_SAMPLE = 50          # gate-passers sampled per fold for the ZK2 control

# Fold geometry mirrors seq=47/49 so zlch and cnk are directly comparable.
WINDOWS = {"H1": ("1460D", "365D", "365D"), "H4": ("1825D", "365D", "365D")}

# Gates are seq=39's, with the trade floor SCALED to the training window.
# 100 trades over 21.6 years is ~4.6/year; applying the absolute 100 to a 4-5
# year window would be a far harsher gate than the sweep itself used.
GATES_PF, GATES_DD, GATES_SR = 1.20, 0.30, 0.0
TRADE_FLOOR_PER_YEAR = 100.0 / 21.6
TRADE_FLOOR_MIN = 30

CFG_KEYS = ("atr_period", "atr_mult", "bias_tf", "zlsma_len",
            "direction", "min_atr")

_G: dict = {}


def _bias_keys(tf: str) -> list[tuple]:
    keys: list[tuple] = [(None, None)]
    for btf in TIMEFRAMES[tf]["bias"]:
        for z in ZLSMA_LENS:
            keys.append((btf, z))
    return keys


def _bias_full(bars: E.Bars, index: pd.DatetimeIndex, tf: str) -> dict:
    """HTF bias flags computed ONCE on the FULL series, then sliced per fold.

    Computing these on a fold slice starves the ZLSMA warm-up: a 365-day test
    window holds ~52 weekly bars, so any W1 bias with zlsma_len >= 50 returns
    all-NaN and the config cannot trade at all, while the same config scores
    normally on a 5-year training window. That asymmetry silently selects
    long-lookback bias configs and then gives them zero OOS trades. htf_bias
    is strictly backward-looking (shift(1) + ffill), so evaluating it on the
    full series and slicing introduces no lookahead and is what a live system
    would see.
    """
    return {(btf, z): E.htf_bias(bars.close_s, index, RESAMPLE_RULE[btf], z,
                                 origin=BIAS_ORIGIN)
            for btf in TIMEFRAMES[tf]["bias"] for z in ZLSMA_LENS}


def _unit_full(bars: E.Bars, period: int, mult: float):
    """Chandelier direction + Wilder ATR on the FULL series. Causal recursions."""
    return (E.chandelier_direction(bars.high_s, bars.low_s, bars.close_s,
                                   period, mult),
            E.wilder_atr(bars.high_s, bars.low_s, bars.close_s, period))


def _init_worker(df, bias_full, tf):
    _G["bars"] = E.Bars(df)
    _G["bias"] = bias_full
    _G["tf"] = tf
    _G["cache"] = {}


def _eval_unit(args) -> list[dict]:
    """One (atr_period, atr_mult) unit, scored on one fold's TRAINING slice."""
    (period, mult), lo, hi = args
    bars, tf = _G["bars"], _G["tf"]
    key = (period, mult)
    if key not in _G["cache"]:
        _G["cache"][key] = _unit_full(bars, period, mult)
    direction_f, atr_f = _G["cache"][key]

    win = bars.index[lo:hi]
    wb = E.Bars(pd.DataFrame(
        {"open": bars.open[lo:hi], "high": bars.high[lo:hi],
         "low": bars.low[lo:hi], "close": bars.close[lo:hi]}, index=win))
    direction, atr_vals = direction_f[lo:hi], atr_f[lo:hi]
    ones = np.ones(hi - lo, dtype=bool)
    rows: list[dict] = []
    for (btf, zlen) in _bias_keys(tf):
        if btf is None:
            rise, fall = ones, ones
        else:
            rf, ff = _G["bias"][(btf, zlen)]
            rise, fall = rf[lo:hi], ff[lo:hi]
        for direc in DIRECTIONS:
            for min_atr in MIN_ATRS:
                sim = E.simulate(wb, direction, atr_vals, rise, fall,
                                 direc in ("both", "long"),
                                 direc in ("both", "short"),
                                 mult, RISK_PCT, min_atr, max_dd_halt=1.0)
                m = E.metrics(sim, basis="price")
                rows.append({"atr_period": period, "atr_mult": mult,
                             "bias_tf": btf or "none", "zlsma_len": zlen or 0,
                             "direction": direc, "min_atr": min_atr,
                             "n_trades": m["n_trades"], "sharpe": m["sharpe"],
                             "max_dd": m["max_dd"],
                             "profit_factor": m["profit_factor"]})
    return rows


def _sim_one(bars: E.Bars, bias_full: dict, lo: int, hi: int,
             cfg: dict, cache: dict) -> dict:
    """Score one fully-specified config on bars[lo:hi], full-series warm-up."""
    key = (int(cfg["atr_period"]), float(cfg["atr_mult"]))
    if key not in cache:
        cache[key] = _unit_full(bars, key[0], key[1])
    direction_f, atr_f = cache[key]
    win = bars.index[lo:hi]
    wb = E.Bars(pd.DataFrame(
        {"open": bars.open[lo:hi], "high": bars.high[lo:hi],
         "low": bars.low[lo:hi], "close": bars.close[lo:hi]}, index=win))
    if cfg["bias_tf"] in (None, "none"):
        rise = fall = np.ones(hi - lo, dtype=bool)
    else:
        rf, ff = bias_full[(cfg["bias_tf"], int(cfg["zlsma_len"]))]
        rise, fall = rf[lo:hi], ff[lo:hi]
    sim = E.simulate(wb, direction_f[lo:hi], atr_f[lo:hi], rise, fall,
                     cfg["direction"] in ("both", "long"),
                     cfg["direction"] in ("both", "short"),
                     float(cfg["atr_mult"]), RISK_PCT, float(cfg["min_atr"]),
                     max_dd_halt=1.0)
    m = E.metrics(sim, basis="price")
    ma = E.metrics(sim, basis="account")
    return {"n_trades": m["n_trades"], "sharpe": m["sharpe"],
            "max_dd": m["max_dd"], "profit_factor": m["profit_factor"],
            "cagr_acct": ma["cagr"]}


def _fixed_leader(tf: str) -> dict | None:
    """seq=40's full-history leader for `tf`, read from the sweep CSV.

    Used ONLY for the leakage-estimate arm. Reading it is not a leak into the
    selection: it is already-known in-sample information whose whole purpose
    here is to be compared against honest selection.
    """
    path = OUT_DIR / f"zlch_sweep_{tf}.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df = df[(df.n_trades >= 100) & (df.profit_factor_px >= GATES_PF)
            & (df.max_dd_px <= GATES_DD)]
    if df.empty:
        return None
    r = df.sort_values("sharpe_px", ascending=False).iloc[0]
    return {"atr_period": int(r.atr_period), "atr_mult": float(r.atr_mult),
            "bias_tf": str(r.bias_tf), "zlsma_len": int(r.zlsma_len),
            "direction": str(r.direction), "min_atr": float(r.min_atr)}


def _label(c: dict) -> str:
    b = "none" if c["bias_tf"] in (None, "none") else f"{c['bias_tf']}/z{c['zlsma_len']}"
    return (f"{c['direction']} atr{int(c['atr_period'])}x{float(c['atr_mult']):g} "
            f"bias{b} minATR{float(c['min_atr']):g}")


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


def run_fold(pool, bars, bias_full, tf, fold, rng, fixed_cfg, cache) -> dict:
    tr_start, tr_end, te_end = fold
    idx = bars.index
    tr_lo = int(np.searchsorted(idx, tr_start, "left"))
    tr_hi = int(np.searchsorted(idx, tr_end, "left"))
    te_hi = int(np.searchsorted(idx, te_end, "left"))
    train_years = (tr_end - tr_start).days / 365.25
    floor = max(TRADE_FLOOR_MIN, int(round(TRADE_FLOOR_PER_YEAR * train_years)))

    t0 = time.time()
    units = list(itertools.product(ATR_PERIODS, ATR_MULTS))
    rows: list[dict] = []
    for res in pool.imap_unordered(_eval_unit, [(u, tr_lo, tr_hi) for u in units]):
        rows.extend(res)
    tr = pd.DataFrame(rows)
    passers = tr[(tr.n_trades >= floor) & (tr.profit_factor >= GATES_PF)
                 & (tr.max_dd <= GATES_DD) & (tr.sharpe > GATES_SR)]

    out = {"train_start": str(tr_start.date()), "train_end": str(tr_end.date()),
           "test_end": str(te_end.date()), "train_years": round(train_years, 2),
           "trade_floor": floor, "n_grid": int(len(tr)),
           "n_passers": int(len(passers)), "seconds": round(time.time() - t0, 1)}
    if passers.empty:
        out["selected"] = None
        return out

    best = passers.sort_values("sharpe", ascending=False).iloc[0]
    cfg = {k: best[k] for k in CFG_KEYS}
    te = _sim_one(bars, bias_full, tr_hi, te_hi, cfg, cache)
    out["selected"] = {
        "config": _label(cfg),
        "atr_period": int(cfg["atr_period"]), "atr_mult": float(cfg["atr_mult"]),
        "bias_tf": str(cfg["bias_tf"]), "zlsma_len": int(cfg["zlsma_len"]),
        "direction": str(cfg["direction"]), "min_atr": float(cfg["min_atr"]),
        "train_sharpe": float(best["sharpe"]), "train_trades": int(best["n_trades"]),
        "oos_sharpe": te["sharpe"], "oos_trades": te["n_trades"],
        "oos_max_dd": te["max_dd"], "oos_profit_factor": te["profit_factor"],
        "oos_cagr_acct": te["cagr_acct"]}

    sel = rng.choice(len(passers), size=min(POOL_SAMPLE, len(passers)),
                     replace=False)
    pool_sh = []
    for i in sel:
        r = passers.iloc[int(i)]
        pool_sh.append(_sim_one(bars, bias_full, tr_hi, te_hi,
                                {k: r[k] for k in CFG_KEYS}, cache)["sharpe"])
    pool_sh = np.asarray([x for x in pool_sh if np.isfinite(x)], float)
    out["pool"] = {"n": int(pool_sh.size),
                   "mean": float(pool_sh.mean()) if pool_sh.size else None,
                   "median": float(np.median(pool_sh)) if pool_sh.size else None,
                   "selected_beats_median": (bool(te["sharpe"] > np.median(pool_sh))
                                             if pool_sh.size and np.isfinite(te["sharpe"])
                                             else None)}
    if fixed_cfg is not None:
        fx = _sim_one(bars, bias_full, tr_hi, te_hi, fixed_cfg, cache)
        out["fixed"] = {"oos_sharpe": fx["sharpe"], "oos_trades": fx["n_trades"]}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tf", choices=["H1", "H4"], required=True)
    ap.add_argument("--workers", type=int, default=default_workers())
    ap.add_argument("--time-one-fold", action="store_true",
                    help="Run only fold 1 and report timing. Prints NO selection "
                         "result, so it cannot inform the design.")
    a = ap.parse_args()

    df = load(a.tf)                      # legacy_utc, matching the seq=40 sweep
    bars = E.Bars(df)
    bias_full = _bias_full(bars, df.index, a.tf)
    folds = _folds(df, a.tf)
    rng = np.random.default_rng(RANDOM_SEED)
    fixed_cfg = _fixed_leader(a.tf)
    cache: dict = {}
    n_cfg = (len(ATR_PERIODS) * len(ATR_MULTS) * len(_bias_keys(a.tf))
             * len(DIRECTIONS) * len(MIN_ATRS))
    print(f"[{a.tf}] {len(df):,} bars {df.index[0].date()}..{df.index[-1].date()} "
          f"| {len(folds)} folds | {n_cfg:,} configs/fold "
          f"| fixed arm: {_label(fixed_cfg) if fixed_cfg else 'unavailable'}",
          flush=True)

    results = []
    with Pool(a.workers, initializer=_init_worker,
              initargs=(df, bias_full, a.tf)) as pool:
        todo = folds[:1] if a.time_one_fold else folds
        for i, fold in enumerate(todo, 1):
            t0 = time.time()
            r = run_fold(pool, bars, bias_full, a.tf, fold, rng, fixed_cfg, cache)
            results.append(r)
            if a.time_one_fold:
                el = time.time() - t0
                print(f"fold 1: {r['n_grid']:,} configs in {el:.0f}s "
                      f"({r['n_passers']:,} passers, floor {r['trade_floor']}) "
                      f"-> projected {el * len(folds) / 60:.1f} min for "
                      f"{len(folds)} folds")
                return 0
            s = r.get("selected")
            if s:
                fx = r.get("fixed", {}).get("oos_sharpe")
                fx_s = f"  fixed {fx:+.3f}" if fx is not None else ""
                pm = r["pool"]["median"]
                pm_s = f"{pm:+.3f}" if pm is not None else "  n/a"
                print(f"  fold {i:>2}/{len(folds)} test->{r['test_end']}  "
                      f"train {s['train_sharpe']:+.3f} -> OOS {s['oos_sharpe']:+.3f} "
                      f"({s['oos_trades']:>4} tr)  pool med {pm_s}{fx_s}"
                      f"  | {s['config']} [{r['seconds']:.0f}s]", flush=True)
            else:
                print(f"  fold {i:>2}/{len(folds)} test->{r['test_end']}  "
                      f"NO CONFIG CLEARED TRAINING GATES [{r['seconds']:.0f}s]",
                      flush=True)
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            (OUT_DIR / f"zlch_nested_wf_{a.tf}.json").write_text(json.dumps(
                {"timeframe": a.tf, "windows": WINDOWS[a.tf],
                 "gates": {"pf": GATES_PF, "dd": GATES_DD, "sharpe": GATES_SR,
                           "trade_floor_per_year": TRADE_FLOOR_PER_YEAR,
                           "trade_floor_min": TRADE_FLOOR_MIN},
                 "pool_sample": POOL_SAMPLE, "seed": RANDOM_SEED,
                 "bias_origin": str(BIAS_ORIGIN),
                 "fixed_config": fixed_cfg, "folds": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
