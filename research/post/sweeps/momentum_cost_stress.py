"""research.post.sweeps.momentum_cost_stress — how much cost kills the seq=60 edge?

seq=60 passed its nested walk-forward at mean OOS Sharpe +0.548. That was
computed with the modelled $0.22/oz spread and $0.07/oz round-turn commission,
and with TWO COST OMISSIONS this module corrects:

  1. SWAP. The winning rule holds 12 H1 bars, which crosses the daily rollover
     roughly half the time and sometimes the Wednesday triple. seq=60 charged
     no swap at all. At -$10/lot/night for gold longs that is -$0.10/oz per
     night crossed -- material against a $0.29 round trip.
  2. SLIPPAGE. Only the quoted spread was charged. Real fills on a market
     order are worse, especially at a session open.

The question is not "does it still work at the modelled cost" -- seq=60 already
answered that. It is "how much worse can costs get before the edge is gone",
because that margin is what separates a deployable rule from one that only
works in a spreadsheet. A strategy whose breakeven is 1.1x modelled cost is not
tradeable; one whose breakeven is 3x has real room.

Grid, applied to the SAME frozen rule and the SAME 17 folds as seq=60:
  cost multiplier x {1.0, 1.5, 2.0, 3.0, 4.0} on spread + commission
  additional slippage per side x {0.00, 0.05, 0.10, 0.20} $/oz
  swap {off, on}          -- "off" reproduces seq=60 exactly as a control

Nothing about the RULE is re-tuned. This only changes what trading costs.

Usage:  python -m research.post.sweeps.momentum_cost_stress
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.pre.feature_screen import build_features
from research.post.sweeps.data import load
from research.post.sweeps.cnk_engine import (SPREAD_USD_PER_OZ, SPREAD_REF_PRICE,
                                             COMMISSION_PER_LOT_RT, CONTRACT_SIZE,
                                             _swap_usd)
from research.post.sweeps.momentum_nested_wf import (
    TF, TRAIN, TEST, STEP, HORIZONS, ENTRY_PCTILE, expanding_pct, RANDOM_SEED)

COST_MULTS = [1.0, 1.5, 2.0, 3.0, 4.0]
SLIPPAGES = [0.00, 0.05, 0.10, 0.20]
OUT = Path("research/pre/artifacts/momentum_cost_stress_nolowvol.json")
# The rule seq=60's folds converged on. Held FIXED here: this module stresses
# costs, it does not re-select.
FEATURE, HORIZON, LOWVOL = "intraday_ret", 12, False


def simulate_costed(df, sig_pct, horizon, regime_ok, *,
                    cost_mult=1.0, slippage=0.0, swap=True):
    op = df.open.to_numpy(float)
    idx = df.index
    n = len(df)
    spread_frac = (SPREAD_USD_PER_OZ * cost_mult) / SPREAD_REF_PRICE
    comm = (COMMISSION_PER_LOT_RT / CONTRACT_SIZE) * cost_mult
    entries = sig_pct >= ENTRY_PCTILE
    if regime_ok is not None:
        entries = entries & regime_ok
    rets = []
    i = 0
    while i < n - horizon - 1:
        if not entries[i]:
            i += 1
            continue
        f, x = i + 1, i + 1 + horizon
        if x >= n:
            break
        entry_px = op[f] * (1 + spread_frac) + slippage
        exit_px = op[x] - slippage
        pnl = (exit_px - entry_px) - comm
        if swap:
            # one ounce = 0.01 lots
            pnl += _swap_usd(1.0 / CONTRACT_SIZE, True, idx[f], idx[x])
        rets.append(pnl / entry_px)
        i = x
    r = np.asarray(rets, float)
    if r.size < 2:
        return {"n": int(r.size), "sharpe": float("nan"), "mean_ret": float("nan")}
    years = max((idx[-1] - idx[0]).days / 365.25, 1e-9)
    sd = r.std(ddof=1)
    return {"n": int(r.size),
            "sharpe": float(r.mean() / sd * np.sqrt(r.size / years)) if sd > 0 else float("nan"),
            "mean_ret": float(r.mean())}


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
    print(f"[{TF}] {len(folds)} folds, rule = {FEATURE}/h{HORIZON}"
          f"{'/lowvol' if LOWVOL else ''}\n", flush=True)

    results = {}
    for swap in (False, True):
        for cm in COST_MULTS:
            for sl in SLIPPAGES:
                sharpes, trades = [], 0
                for (tr0, tr1, te1) in folds:
                    te = (df.index >= tr1) & (df.index < te1)
                    te_df, te_f = df[te], feats[te]
                    pct = expanding_pct(te_f[FEATURE].to_numpy(float))
                    reg = None
                    if LOWVOL:
                        reg = expanding_pct(te_f["atr_ratio"].to_numpy(float)) < (1/3)
                    r = simulate_costed(te_df, pct, HORIZON, reg,
                                        cost_mult=cm, slippage=sl, swap=swap)
                    if np.isfinite(r["sharpe"]):
                        sharpes.append(r["sharpe"])
                    trades += r["n"]
                s = np.asarray(sharpes, float)
                key = f"swap={'on' if swap else 'off'}|mult={cm}|slip={sl}"
                results[key] = {"mean_sharpe": float(s.mean()) if s.size else None,
                                "median_sharpe": float(np.median(s)) if s.size else None,
                                "folds_positive": int((s > 0).sum()),
                                "n_folds": int(s.size), "trades": trades}
                print(f"  swap {'on ' if swap else 'off'} x{cm:<4} slip ${sl:.2f}  "
                      f"mean Sharpe {results[key]['mean_sharpe']:+.3f}  "
                      f"folds+ {results[key]['folds_positive']}/{results[key]['n_folds']}  "
                      f"trades {trades}", flush=True)
        print(flush=True)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"rule": {"feature": FEATURE, "horizon": HORIZON,
                                        "lowvol": LOWVOL},
                               "cost_mults": COST_MULTS, "slippages": SLIPPAGES,
                               "results": results}, indent=2, default=float))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
