"""research.post.sweeps.momentum_dsr — Deflated Sharpe on the seq=60/61 rule.

seq=60 passed its nested walk-forward and seq=61 passed cost stress, but
neither computed a Deflated Sharpe. DSR is the gate that every other candidate
in this repo has failed, so leaving it out would be conspicuous.

IMPORTANT DIFFERENCE from the earlier DSR calculations here. For the sweeps,
DSR was computed on an IN-SAMPLE leader selected from a huge grid, which is
what made the honest N so large and the haircut so brutal. This is computed on
the CONCATENATED OUT-OF-SAMPLE fold returns of a rule whose parameters were
selected inside each training window. The selection surface is therefore the
126 candidates re-scored per fold, not a 150,000-config grid.

N is reported across a range rather than argued for, as in every other DSR
table in this repo:
    1       no selection at all -- the optimistic bound
    21      the research log's global trial_count
    126     candidates the nested walk-forward chose among, per fold
    276     the seq=58 feature screen's full test count, which is the widest
            defensible reading since that screen is what pointed here

Usage:  python -m research.post.sweeps.momentum_dsr
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.pre.feature_screen import build_features
from research.post.dsr import deflated_sharpe_ratio
from research.post.sweeps.data import load
from research.post.sweeps.momentum_cost_stress import simulate_costed
from research.post.sweeps.momentum_nested_wf import (
    TF, TRAIN, TEST, STEP, expanding_pct)

FEATURE, HORIZON = "intraday_ret", 12
OUT = Path("research/pre/artifacts/momentum_dsr.json")


def fold_returns(df, feats, folds, lowvol: bool, swap: bool = True):
    """Concatenated per-trade OOS returns across every fold."""
    allr = []
    for (_tr0, tr1, te1) in folds:
        te = (df.index >= tr1) & (df.index < te1)
        te_df, te_f = df[te], feats[te]
        pct = expanding_pct(te_f[FEATURE].to_numpy(float))
        reg = None
        if lowvol:
            reg = expanding_pct(te_f["atr_ratio"].to_numpy(float)) < (1 / 3)
        # simulate_costed returns summary stats; re-derive the series here
        op = te_df.open.to_numpy(float)
        idx = te_df.index
        from research.post.sweeps.cnk_engine import (
            SPREAD_USD_PER_OZ, SPREAD_REF_PRICE, COMMISSION_PER_LOT_RT,
            CONTRACT_SIZE, _swap_usd)
        sf = SPREAD_USD_PER_OZ / SPREAD_REF_PRICE
        comm = COMMISSION_PER_LOT_RT / CONTRACT_SIZE
        ent = pct >= 0.90
        if reg is not None:
            ent = ent & reg
        i = 0
        n = len(te_df)
        while i < n - HORIZON - 1:
            if not ent[i]:
                i += 1
                continue
            f, x = i + 1, i + 1 + HORIZON
            if x >= n:
                break
            e_px = op[f] * (1 + sf)
            pnl = (op[x] - e_px) - comm
            if swap:
                pnl += _swap_usd(1.0 / CONTRACT_SIZE, True, idx[f], idx[x])
            allr.append(pnl / e_px)
            i = x
    return np.asarray(allr, float)


def main() -> int:
    df = load(TF, tz="server_eet", with_volume=True)
    feats, _ = build_features(df)
    folds, start = [], df.index[0]
    while True:
        tr1 = start + TRAIN
        te1 = tr1 + TEST
        if te1 > df.index[-1]:
            break
        folds.append((start, tr1, te1))
        start = start + STEP

    out = {"horizon": HORIZON, "feature": FEATURE, "n_folds": len(folds),
           "variants": {}}
    for label, lowvol in (("unfiltered", False), ("lowvol_filter", True)):
        r = fold_returns(df, feats, folds, lowvol)
        r = r[np.isfinite(r)]
        sr = float(r.mean() / r.std(ddof=1)) if r.size > 2 else float("nan")
        # Var(SR) is reported BOTH ways. dsr.py's docstring asks for per-fold
        # Sharpes on walk-forward results and warns that the estimated path is
        # "a leniency that should be flagged". The original run of this module
        # silently took the lenient path. Neither is unambiguously right here --
        # DSR's var_sr means dispersion ACROSS TRIALS under the null, while
        # per-fold Sharpes measure dispersion ACROSS TIME -- so both are shown
        # and the spread between them is the honest measure of the ambiguity.
        per_fold = []
        for f in folds:
            fr = fold_returns(df, feats, [f], lowvol)
            fr = fr[np.isfinite(fr)]
            if fr.size > 2 and fr.std(ddof=1) > 0:
                per_fold.append(float(fr.mean() / fr.std(ddof=1)))

        d = {"n_trades": int(r.size), "per_obs_sharpe": sr,
             "mean_ret": float(r.mean()),
             "per_fold_per_obs_sharpes": per_fold,
             "dsr": {}, "dsr_empirical_var_sr": {}}
        print(f"\n{label}: {r.size} OOS trades, per-observation Sharpe {sr:.4f}")
        print(f"  per-fold per-obs Sharpes: n={len(per_fold)} "
              f"sd={np.std(per_fold, ddof=1):.4f}")
        for n in (1, 21, 126, 276):
            try:
                res = deflated_sharpe_ratio(r, n_trials=int(n))
                emp = deflated_sharpe_ratio(r, n_trials=int(n),
                                            trial_sharpes=per_fold)
                d["dsr"][str(n)] = float(res.dsr)
                d["dsr_empirical_var_sr"][str(n)] = float(emp.dsr)
                flag = "" if n == 1 else "   <-- lenient branch" if res.dsr > emp.dsr else ""
                print(f"  DSR @ N={n:<4}: {res.dsr:.4f} ({res.var_sr_source})"
                      f"   empirical: {emp.dsr:.4f}{flag}")
            except Exception as exc:                     # noqa: BLE001
                d["dsr"][str(n)] = f"error: {exc}"
                print(f"  DSR @ N={n:<4}: {exc}")
        out["variants"][label] = d

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=float))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
