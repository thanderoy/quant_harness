"""research.pre.vol_gate_replication — does the low-vol gate replicate off XAU?

seq=71/72 left the low-volatility gate SHELVED AS LIVE-UNPROVEN: real ordering
(raw $/oz 2.10 vs 0.82 unconditional), real persistence (19/22 years), but an
unproven increment (advantage p=0.0647 against a null mean of +0.0158). The
registration bars re-specification -- different terciles, ATR pair or horizon
would cross 0.05 by construction on the same 22 years and inflate the honest
trial count. The answer to a near miss is INDEPENDENT evidence.

This is that evidence. Identical specification, identical decisive stream,
identical threshold, run on instruments that share none of the data which
produced the near miss. Vol compression preceding directional expansion has a
literature prior, so the question is whether the mechanism is general or
whether it was 22 years of one series.

COST NORMALISATION, and why. XAU pays $0.29/oz round trip on a ~$2,000 price =
1.45bp. XAG and US500 have different real spreads. Comparing the MECHANISM
across instruments at their own differing cost structures would confound the
thing being replicated, so every instrument is charged the same 1.45bp
proportional round trip. That isolates "does compression precede expansion";
it does NOT establish tradeable viability, which needs each instrument's true
costs and is a separate question. Swap is excluded for the same reason -- it is
priced per-lot in XAU terms and does not transfer.

Usage:  python -m research.pre.vol_gate_replication --symbol XAGUSD --reps 200
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
from research.post.sweeps.momentum_nested_wf import TRAIN, TEST, STEP, expanding_pct
from research.post.sweeps.momentum_null_calibration import permute_within_day

OUT = Path("research/pre/artifacts")
HORIZON = 12
ENTRY_PCTILE = 0.90
COST_FRAC = 0.000145          # 1.45bp round trip, matched to XAU's $0.29/$2000
# Common window so no instrument is advantaged by simply having more history.
COMMON_START, COMMON_END = "2012-08-06", "2025-12-31"


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


def simulate(op, ent, lo, hi) -> np.ndarray:
    """Non-overlapping long-only holds, proportional cost."""
    rets, i = [], lo
    while i < hi - HORIZON - 1:
        if not ent[i]:
            i += 1
            continue
        f, x = i + 1, i + 1 + HORIZON
        if x >= hi:
            break
        rets.append((op[x] - op[f]) / op[f] - COST_FRAC)
        i = x
    return np.asarray(rets, float)


def statistics(df: pd.DataFrame) -> dict:
    feats, _ = build_features(df)
    sig = expanding_pct(feats["intraday_ret"].to_numpy(float)) >= ENTRY_PCTILE
    st = build_state(df)
    gate = terciles(st["vol_ratio"].to_numpy(float)) == 0
    op = df.open.to_numpy(float)
    ung, gat = [], []
    for lo, hi in _folds(df.index):
        ung.append(simulate(op, sig, lo, hi))
        gat.append(simulate(op, sig & gate, lo, hi))

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


_G = {}


def _init(sym, start, end):
    _G["df"] = load("H1", tz="server_eet", with_volume=True, symbol=sym,
                    start=start, end=end)


def _one(seed: int) -> dict:
    return statistics(permute_within_day(_G["df"], np.random.default_rng(seed)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--reps", type=int, default=200)
    ap.add_argument("--workers", type=int, default=max(mp.cpu_count() - 1, 1))
    ap.add_argument("--full-history", action="store_true",
                    help="Use the instrument's whole series instead of the "
                         "common window. Secondary context only.")
    a = ap.parse_args()

    start = None if a.full_history else COMMON_START
    end = None if a.full_history else COMMON_END
    df = load("H1", tz="server_eet", with_volume=True, symbol=a.symbol,
              start=start, end=end)
    obs = statistics(df)
    win = "full" if a.full_history else "common"
    print(f"[{a.symbol}/{win}] {len(df):,} bars {df.index[0].date()}..{df.index[-1].date()} "
          f"| {len(_folds(df.index))} folds", flush=True)
    print("observed:", json.dumps(obs), flush=True)

    with mp.Pool(a.workers, initializer=_init, initargs=(a.symbol, start, end)) as pool:
        sims = pool.map(_one, range(a.reps))

    res = {"symbol": a.symbol, "window": win, "n_bars": int(len(df)),
           "start": str(df.index[0]), "end": str(df.index[-1]),
           "cost_frac": COST_FRAC, "observed": obs, "streams": {}}
    for k in ("advantage", "gated", "ungated"):
        s = np.asarray([d[k] for d in sims if np.isfinite(d[k])], float)
        o = obs[k]
        p = float((s >= o).sum() + 1) / (s.size + 1)
        res["streams"][k] = {"observed": o, "reps_valid": int(s.size), "p_value": p,
                             "null_mean": float(s.mean()), "null_sd": float(s.std(ddof=1)),
                             "null_q95": float(np.percentile(s, 95)),
                             "null_values": s.tolist()}
        print(f"[{k}] observed {o:+.5f}  p={p:.4f}  null mean {s.mean():+.5f} "
              f"q95 {np.percentile(s,95):+.5f} ({s.size} reps)", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"vol_gate_repl_{a.symbol}_{win}.json").write_text(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
