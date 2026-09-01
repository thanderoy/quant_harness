"""research.post.sweeps.momentum_null_calibration — empirical null for the
whole nested-WF pipeline, so the DSR gate can be calibrated instead of argued.

The DSR verdict on the seq=60/61 momentum rule swings from 0.996 to 0.000
depending on two unobservable knobs: the trial count N, and the Var(SR)
source. Rather than defend a choice of either, this runs the ENTIRE pipeline
(feature build -> nested selection -> OOS concatenation) many times on data
whose intraday predictability has been destroyed by construction, and reads
the null distribution of the final statistic straight off the result.

Null construction: within each trading day, the order of the H1 bars is
randomly permuted. Each bar carries its own log return, its own
open/high/low geometry relative to its close, and its own volume, so the
day's return distribution, volatility clustering, bar shapes and session
structure all survive. What does NOT survive is any relationship between the
session's first-bar return and what follows -- which is precisely the effect
under test. Price level is chained across days so the series stays realistic.

Reported: p = fraction of null runs whose concatenated OOS per-observation
Sharpe equals or exceeds the observed value. This needs no N and no Var(SR).

Usage:  python -m research.post.sweeps.momentum_null_calibration --reps 200
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
from pathlib import Path

import numpy as np
import pandas as pd

from research.pre.feature_screen import build_features
from research.post.sweeps import default_workers
from research.post.sweeps.data import load
from research.post.sweeps.momentum_nested_wf import (
    TF, TRAIN, TEST, STEP, HORIZONS, ENTRY_PCTILE, expanding_pct, simulate,
    MIN_SPREAD, ROUND_TRIP_COST, FIXED_CHOICE)
from research.post.sweeps.cnk_engine import (
    SPREAD_USD_PER_OZ, SPREAD_REF_PRICE, COMMISSION_PER_LOT_RT, CONTRACT_SIZE,
    _swap_usd)

OUT = Path("research/pre/artifacts/momentum_null_calibration.json")


def permute_within_day(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Shuffle bar order inside each trading day; chain the price level."""
    c = df.close.to_numpy(float)
    lr = np.diff(np.log(c), prepend=np.log(c[0]))
    ratio_o = df.open.to_numpy(float) / c
    ratio_h = df.high.to_numpy(float) / c
    ratio_l = df.low.to_numpy(float) / c
    vol = (df.volume.to_numpy(float) if "volume" in df.columns
           else np.ones(len(df)))
    day_id = df.index.normalize()
    new_idx = np.empty(len(df), dtype=int)
    starts = np.flatnonzero(np.r_[True, day_id[1:] != day_id[:-1]])
    ends = np.r_[starts[1:], len(df)]
    for s, e in zip(starts, ends):
        new_idx[s:e] = s + rng.permutation(e - s)
    lr_n, ro, rh, rl, vn = (lr[new_idx], ratio_o[new_idx],
                            ratio_h[new_idx], ratio_l[new_idx], vol[new_idx])
    c_new = c[0] * np.exp(np.cumsum(lr_n))
    out = pd.DataFrame(
        {"open": c_new * ro, "high": c_new * rh, "low": c_new * rl,
         "close": c_new, "volume": vn}, index=df.index)
    out["high"] = out[["open", "high", "low", "close"]].max(axis=1)
    out["low"] = out[["open", "high", "low", "close"]].min(axis=1)
    return out


def _oos_returns(te_df, te_f, name, horizon, use_regime, cache) -> np.ndarray:
    """Per-trade OOS returns. Mirrors momentum_dsr.fold_returns, swap included."""
    if name not in cache:
        cache[name] = expanding_pct(te_f[name].to_numpy(float))
    pct = cache[name]
    reg = None
    if use_regime:
        if "__atr" not in cache:
            cache["__atr"] = expanding_pct(te_f["atr_ratio"].to_numpy(float))
        reg = cache["__atr"] < (1.0 / 3.0)
    op = te_df.open.to_numpy(float)
    idx = te_df.index
    sf = SPREAD_USD_PER_OZ / SPREAD_REF_PRICE
    comm = COMMISSION_PER_LOT_RT / CONTRACT_SIZE
    ent = pct >= ENTRY_PCTILE
    if reg is not None:
        ent = ent & reg
    n, i, rets = len(te_df), 0, []
    while i < n - horizon - 1:
        if not ent[i]:
            i += 1
            continue
        f, x = i + 1, i + 1 + horizon
        if x >= n:
            break
        e_px = op[f] * (1 + sf)
        pnl = (op[x] - e_px) - comm
        pnl += _swap_usd(1.0 / CONTRACT_SIZE, True, idx[f], idx[x])
        rets.append(pnl / e_px)
        i = x
    return np.asarray(rets, float)


def _fold_best(tr_df, tr_f):
    """Training-window selection, with expanding_pct cached per feature.

    Mirrors momentum_nested_wf.train_score exactly, but computes the expanding
    percentile once per feature instead of once per (feature, horizon, regime).
    That is a 6x saving on the pipeline's dominant cost and changes no result.
    """
    cols = list(tr_f.columns)
    pct = {n: expanding_pct(tr_f[n].to_numpy(float)) for n in cols}
    reg = pct["atr_ratio"] < (1.0 / 3.0)
    mean_op = float(np.nanmean(tr_df.open.to_numpy(float)))
    best, best_sr = None, -np.inf
    for n in cols:
        for h in HORIZONS:
            for rg in (False, True):
                sim = simulate(tr_df, pct[n], h, reg if rg else None)
                if sim["n_trades"] < 30:
                    continue
                mean_usd = sim["total"] / max(sim["n_trades"], 1) * mean_op
                ok = (mean_usd > MIN_SPREAD - ROUND_TRIP_COST
                      and sim["sharpe"] > 0)
                if ok and sim["sharpe"] > best_sr:
                    best, best_sr = (n, h, rg), sim["sharpe"]
    return best


def _sr(chunks) -> float:
    r = np.concatenate(chunks) if chunks else np.array([])
    r = r[np.isfinite(r)]
    if r.size < 30 or r.std(ddof=1) <= 0:
        return float("nan")
    return float(r.mean() / r.std(ddof=1))


def pipeline_sharpe(df: pd.DataFrame) -> dict:
    """Full nested WF. Returns per-observation Sharpe for two streams.

    ``nested`` -- the selection procedure: each fold trades whatever its own
    training window ranked first. This is the stream that carries the
    selection cost DSR's ``n_trials`` is trying to price.

    ``fixed``  -- the frozen (intraday_ret, h=12) rule, which is what
    momentum_dsr.py actually evaluated. Kept so the observed 0.07627 has a
    null built on identical machinery.
    """
    feats, _ = build_features(df)
    folds, start = [], df.index[0]
    while True:
        tr1 = start + TRAIN
        te1 = tr1 + TEST
        if te1 > df.index[-1]:
            break
        folds.append((start, tr1, te1))
        start = start + STEP
    nested, fixed = [], []
    for (tr0, tr1, te1) in folds:
        tr_m = (df.index >= tr0) & (df.index < tr1)
        te_m = (df.index >= tr1) & (df.index < te1)
        te_df, te_f, cache = df[te_m], feats[te_m], {}
        fixed.append(_oos_returns(te_df, te_f, *FIXED_CHOICE, cache))
        best = _fold_best(df[tr_m], feats[tr_m])
        if best is not None:
            nested.append(_oos_returns(te_df, te_f, *best, cache))
    return {"nested": _sr(nested), "fixed": _sr(fixed)}


def _one(seed: int) -> dict:
    df = load(TF, tz="server_eet", with_volume=True)
    return pipeline_sharpe(permute_within_day(df, np.random.default_rng(seed)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reps", type=int, default=200)
    ap.add_argument("--workers", type=int, default=default_workers())
    a = ap.parse_args()

    # Observed values come from the pipeline itself on unpermuted data, so the
    # null and the observation are guaranteed to be the same statistic.
    observed = pipeline_sharpe(load(TF, tz="server_eet", with_volume=True))
    print(f"observed: {observed}")

    with mp.Pool(a.workers) as pool:
        sims = pool.map(_one, range(a.reps))

    res = {"observed": observed, "reps_requested": a.reps, "streams": {}}
    for stream in ("fixed", "nested"):
        s = np.asarray([d[stream] for d in sims if np.isfinite(d[stream])], float)
        obs = observed[stream]
        p_val = float((s >= obs).sum() + 1) / (s.size + 1)
        res["streams"][stream] = {
            "observed": obs, "reps_valid": int(s.size), "p_value": p_val,
            "null_mean": float(s.mean()), "null_sd": float(s.std(ddof=1)),
            "null_q50": float(np.percentile(s, 50)),
            "null_q95": float(np.percentile(s, 95)),
            "null_q99": float(np.percentile(s, 99)),
            "null_max": float(s.max()),
            "passes_prereg": bool(p_val < 0.05),
            "null_sharpes": s.tolist(),
        }
        print(f"\n[{stream}] observed {obs:.5f}  p={p_val:.4f}  "
              f"null mean {s.mean():+.5f} sd {s.std(ddof=1):.5f}  "
              f"q95 {np.percentile(s, 95):+.5f}  max {s.max():+.5f}  "
              f"({s.size} valid reps)")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
