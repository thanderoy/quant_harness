"""research.pre.state_gate_wf — nested walk-forward on the market-state GATE.

The state screen (exploratory, H1) found that gating the frozen
intraday_ret/h=12 signal on low volatility lifted per-observation Sharpe from
0.0898 to 0.2012, and that the best of 12 gate cells beat the pool median by
+0.123. That statistic was computed IN-SAMPLE: all 12 cells were scored on the
same data and the maximum taken, and the max of 12 noisy cells exceeds their
median by construction. At seq=68 the out-of-sample version of exactly that
statistic came out at -0.154. So the screen produced a lead, not evidence.

This is the confirmatory test. Per fold the gate is selected on TRAINING bars
only and applied once to the untouched test window, against four arms:

  selected -- the gate training picked.               (honest)
  pool     -- the OTHER gate cells on the same test window. DECISIVE: if
              picking the best gate in training does not beat picking any
              gate, the gating is noise (seq=49, seq=68).
  ungated  -- the raw signal, no gate. Does gating help AT ALL?
  fixed    -- vol_ratio=T0 on every fold. That cell was chosen after seeing
              the full sample, so its excess over `selected` is the lookahead
              in the screen, the quantity seq=49/68 measured at 0.5-0.8.

Deviation from seq=60, disclosed: expanding percentiles and tercile labels are
computed ONCE on the FULL series and then sliced, rather than restarted inside
each window. Both are causal, but restarting starves indicator warm-up and at
seq=67 that silently produced configs with zero trades. The ungated arm is
reported so any drift from seq=60's baseline is visible.

Usage:  python -m research.pre.state_gate_wf
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.pre.feature_screen import build_features
from research.pre.state_screen import build_state, terciles
from research.post.sweeps.data import load
from research.post.sweeps.momentum_nested_wf import (
    TF, TRAIN, TEST, STEP, expanding_pct)
from research.post.sweeps.cnk_engine import (
    SPREAD_USD_PER_OZ, SPREAD_REF_PRICE, COMMISSION_PER_LOT_RT,
    CONTRACT_SIZE, _swap_usd)

OUT = Path("research/pre/artifacts/state_gate_wf.json")
HORIZON = 12
ENTRY_PCTILE = 0.90
MIN_TRAIN_TRADES = 30        # a Sharpe on fewer than this is noise
MIN_TEST_TRADES = 5
FIXED_GATE = "vol_ratio=T0"
STATE_VARS = ("ker20", "vol_ratio", "bias_atr", "|bias_atr|")


def build_gates(df: pd.DataFrame) -> dict:
    """Causal tercile membership masks for every gate cell, full series."""
    st = build_state(df)
    lab = {v: terciles(st[v].to_numpy(float)) for v in st.columns}
    lab["|bias_atr|"] = terciles(np.abs(st["bias_atr"].to_numpy(float)))
    gates = {"none": np.ones(len(df), dtype=bool)}
    for v in STATE_VARS:
        for b in (0, 1, 2):
            gates[f"{v}=T{b}"] = (lab[v] == b)
    return gates


def simulate(op, idx, ent, lo, hi) -> np.ndarray:
    """Per-trade returns inside [lo, hi). Non-overlapping, long only, costed."""
    sf = SPREAD_USD_PER_OZ / SPREAD_REF_PRICE
    comm = COMMISSION_PER_LOT_RT / CONTRACT_SIZE
    rets = []
    i = lo
    while i < hi - HORIZON - 1:
        if not ent[i]:
            i += 1
            continue
        f, x = i + 1, i + 1 + HORIZON
        if x >= hi:
            break
        e_px = op[f] * (1 + sf)
        pnl = (op[x] - e_px) - comm + _swap_usd(1.0 / CONTRACT_SIZE, True,
                                                idx[f], idx[x])
        rets.append(pnl / e_px)
        i = x
    return np.asarray(rets, float)


def sr(r: np.ndarray) -> float:
    r = r[np.isfinite(r)]
    if r.size < MIN_TEST_TRADES or r.std(ddof=1) == 0:
        return float("nan")
    return float(r.mean() / r.std(ddof=1))


def main() -> int:
    df = load(TF, tz="server_eet", with_volume=True)
    feats, _ = build_features(df)
    sig = expanding_pct(feats["intraday_ret"].to_numpy(float)) >= ENTRY_PCTILE
    gates = build_gates(df)
    op, idx = df.open.to_numpy(float), df.index
    n = len(df)

    folds, start = [], idx[0]
    while True:
        tr1 = start + TRAIN
        te1 = tr1 + TEST
        if te1 > idx[-1]:
            break
        folds.append((start, tr1, te1))
        start = start + STEP

    results, sel_all, pool_all, ung_all, fix_all = [], [], [], [], []
    for k, (tr0, tr1, te1) in enumerate(folds, 1):
        a = int(np.searchsorted(idx, tr0, "left"))
        b = int(np.searchsorted(idx, tr1, "left"))
        c = int(np.searchsorted(idx, te1, "left"))

        # ---- select on TRAINING only
        best, best_sr = None, -np.inf
        for name, m in gates.items():
            if name == "none":
                continue
            r = simulate(op, idx, sig & m, a, b)
            if r.size >= MIN_TRAIN_TRADES:
                s = sr(r)
                if np.isfinite(s) and s > best_sr:
                    best, best_sr = name, s

        # ---- score on the untouched TEST window
        ung = sr(simulate(op, idx, sig, b, c))
        fix = sr(simulate(op, idx, sig & gates[FIXED_GATE], b, c))
        sel = sr(simulate(op, idx, sig & gates[best], b, c)) if best else float("nan")
        pool = []
        for name, m in gates.items():
            if name in ("none", best):
                continue
            s = sr(simulate(op, idx, sig & m, b, c))
            if np.isfinite(s):
                pool.append(s)
        pool_med = float(np.median(pool)) if pool else float("nan")

        n_sel = simulate(op, idx, sig & gates[best], b, c).size if best else 0
        row = {"fold": k, "train_end": str(tr1.date()), "test_end": str(te1.date()),
               "selected": best, "train_sharpe": best_sr if best else None,
               "sel_oos": sel, "sel_trades": int(n_sel), "pool_median": pool_med,
               "pool_n": len(pool), "ungated_oos": ung, "fixed_oos": fix}
        results.append(row)
        for lst, val in ((sel_all, sel), (pool_all, pool_med),
                         (ung_all, ung), (fix_all, fix)):
            lst.append(val)
        print(f"  fold {k:>2}/{len(folds)} ->{row['test_end']}  "
              f"sel {sel:+.3f} ({n_sel:>3}tr)  pool {pool_med:+.3f}  "
              f"ungated {ung:+.3f}  fixed {fix:+.3f}  | {best}", flush=True)

    A = {k: np.array(v, float) for k, v in
         (("sel", sel_all), ("pool", pool_all), ("ung", ung_all), ("fix", fix_all))}
    ok = np.isfinite(A["sel"]) & np.isfinite(A["pool"])
    wins = int((A["sel"][ok] > A["pool"][ok]).sum())
    from math import comb
    nn = int(ok.sum())
    p = min(1.0, 2 * sum(comb(nn, i) for i in range(wins, nn + 1)) / 2 ** nn) if nn else float("nan")
    summary = {
        "n_folds": len(folds), "horizon": HORIZON, "fixed_gate": FIXED_GATE,
        "V1_sel_mean": float(np.nanmean(A["sel"])),
        "V1_ungated_mean": float(np.nanmean(A["ung"])),
        "V1_gate_value": float(np.nanmean(A["sel"]) - np.nanmean(A["ung"])),
        "V2_wins": wins, "V2_n": nn, "V2_sign_p": p,
        "V2_pool_mean": float(np.nanmean(A["pool"])),
        "V2_selection_value": float(np.nanmean(A["sel"]) - np.nanmean(A["pool"])),
        "V3_fixed_mean": float(np.nanmean(A["fix"])),
        "V3_fixed_minus_ungated": float(np.nanmean(A["fix"]) - np.nanmean(A["ung"])),
        "lookahead_fixed_minus_selected": float(np.nanmean(A["fix"]) - np.nanmean(A["sel"])),
        "V4_median_sel_trades": float(np.median([r["sel_trades"] for r in results])),
        "folds": results,
    }
    OUT.write_text(json.dumps(summary, indent=2))
    print("\n" + json.dumps({k: v for k, v in summary.items() if k != "folds"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
