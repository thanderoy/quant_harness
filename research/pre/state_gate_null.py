"""research.pre.state_gate_null — permutation null for the FIXED low-vol gate.

seq=70's V3 showed the fixed vol_ratio=T0 gate beating ungated in 13/17 folds
(p=0.049, +0.058 mean Sharpe). That cell was chosen after a full-sample screen,
so the number is contaminated in the same way seq=46 was, and seq=49 showed
that arm's whole advantage can be lookahead. This prices the hindsight without
needing a trial count, which is what settled the momentum rule at seq=65.

WHY THIS NULL IS THE RIGHT ONE, and it is not obvious. Gating on LOW VOLATILITY
mechanically inflates Sharpe whenever drift is positive: Sharpe = mean/std, and
selecting low-vol bars shrinks the denominator. A naive test would reward the
gate for arithmetic. The within-day bar permutation preserves daily returns,
volatility clustering, bar geometry, volume and session structure -- so the
drift AND the vol regime structure both survive -- while destroying any
relationship between the session's first-bar return and what follows. Under
that null the gate can still shrink the denominator, so if its advantage is
merely the variance-reduction artifact, the null will reproduce it.

Two statistics, each against its own matched null:
    gated      -- concatenated OOS per-obs Sharpe with vol_ratio=T0 applied
    advantage  -- gated minus ungated, which is what V3 actually claimed

Usage:  python -m research.pre.state_gate_null --reps 200
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
from pathlib import Path

import numpy as np
import pandas as pd

from research.pre.feature_screen import build_features
from research.pre.state_screen import build_state, terciles
from research.post.sweeps.data import load
from research.post.sweeps.momentum_nested_wf import (
    TF, TRAIN, TEST, STEP, expanding_pct)
from research.post.sweeps.momentum_null_calibration import permute_within_day
from research.pre.state_gate_wf import simulate, ENTRY_PCTILE

OUT = Path("research/pre/artifacts/state_gate_null.json")


def _folds(idx) -> list[tuple[int, int]]:
    out, start = [], idx[0]
    while True:
        tr1 = start + TRAIN
        te1 = tr1 + TEST
        if te1 > idx[-1]:
            break
        out.append((int(np.searchsorted(idx, tr1, "left")),
                    int(np.searchsorted(idx, te1, "left"))))
        start = start + STEP
    return out


def statistics(df: pd.DataFrame) -> dict:
    """Concatenated OOS per-obs Sharpe, ungated and low-vol-gated."""
    feats, _ = build_features(df)
    sig = expanding_pct(feats["intraday_ret"].to_numpy(float)) >= ENTRY_PCTILE
    st = build_state(df)
    gate = terciles(st["vol_ratio"].to_numpy(float)) == 0        # T0 = low vol
    op, idx = df.open.to_numpy(float), df.index

    ung, gat = [], []
    for lo, hi in _folds(idx):
        ung.append(simulate(op, idx, sig, lo, hi))
        gat.append(simulate(op, idx, sig & gate, lo, hi))

    def sr(chunks):
        r = np.concatenate(chunks) if chunks else np.array([])
        r = r[np.isfinite(r)]
        if r.size < 30 or r.std(ddof=1) == 0:
            return float("nan"), 0
        return float(r.mean() / r.std(ddof=1)), int(r.size)

    s_u, n_u = sr(ung)
    s_g, n_g = sr(gat)
    return {"ungated": s_u, "gated": s_g, "advantage": s_g - s_u,
            "n_ungated": n_u, "n_gated": n_g}


def _one(seed: int) -> dict:
    df = load(TF, tz="server_eet", with_volume=True)
    return statistics(permute_within_day(df, np.random.default_rng(seed)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reps", type=int, default=200)
    ap.add_argument("--workers", type=int, default=max(mp.cpu_count() - 1, 1))
    a = ap.parse_args()

    obs = statistics(load(TF, tz="server_eet", with_volume=True))
    print("observed:", json.dumps(obs), flush=True)

    with mp.Pool(a.workers) as pool:
        sims = pool.map(_one, range(a.reps))

    res = {"observed": obs, "reps_requested": a.reps, "streams": {}}
    for k in ("gated", "advantage", "ungated"):
        s = np.asarray([d[k] for d in sims if np.isfinite(d[k])], float)
        o = obs[k]
        p = float((s >= o).sum() + 1) / (s.size + 1)
        res["streams"][k] = {
            "observed": o, "reps_valid": int(s.size), "p_value": p,
            "null_mean": float(s.mean()), "null_sd": float(s.std(ddof=1)),
            "null_q50": float(np.percentile(s, 50)),
            "null_q95": float(np.percentile(s, 95)),
            "null_max": float(s.max()), "passes_prereg": bool(p < 0.05),
            "null_values": s.tolist(),
        }
        print(f"[{k}] observed {o:+.5f}  p={p:.4f}  null mean {s.mean():+.5f} "
              f"sd {s.std(ddof=1):.5f}  q95 {np.percentile(s,95):+.5f} "
              f"({s.size} reps)", flush=True)
    OUT.write_text(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
