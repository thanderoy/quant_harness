"""research.pre.state_screen — do three orthogonal market-state variables
separate forward outcomes?

Tests three state variables chosen to answer DIFFERENT questions, so that the
stack is not five re-derivations of one smoothed price (which is what the
seq=58 screen turned out to be: its five surviving features had pairwise
Spearman 0.59-0.84).

    ker20     = |C - C[20]| / sum|dC| over 20      -- trend QUALITY  (unsigned)
    vol_ratio = ATR(14) / ATR(100)                  -- vol REGIME     (unsigned)
    bias_atr  = (C - SMA(200)) / ATR(14)            -- trend LOCATION (signed)

Measured orthogonality on 124,688 H1 bars: max |Spearman| = 0.140.

WHY THIS IS NOT JUST THE seq=58 SCREEN AGAIN
---------------------------------------------
feature_screen.py buckets by a feature and measures SIGNED forward return.
ker20 and vol_ratio are direction-agnostic by construction -- ER's numerator is
an absolute value -- so that test is structurally incapable of validating them,
and seq=58's "efficiency_ratio does not pay costs" therefore does not refute
ER. It never tested ER's claim. seq=43 said the same thing from the other end:
salvage the KER GATE, not the strategy. A gate conditions someone else's
signal; it is not a signal.

Three arms, accordingly:
  A UNSIGNED   -- for ker20, vol_ratio, |bias|: forward MFE, MAE and |move| in
                  ATR units per tercile. Asks "does a move develop?"
  B SIGNED     -- bias_atr only: forward return net of cost per tercile. The
                  ordinary marginal test, which is appropriate here.
  C CONDITIONAL-- H1 only: does the intraday_ret/h=12 long signal -- the one
                  directional effect in this repo that beat its permutation
                  null (p=0.010, seq=65) -- improve inside each tercile?

Buckets are CAUSAL expanding terciles, not full-sample qcut: a live gate only
ever sees history, and seq=60 measured full-sample bucketing as lookahead worth
~0.15 Sharpe.

Usage:  python -m research.pre.state_screen --tf H1
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.post.sweeps.data import load
from research.post.sweeps.momentum_nested_wf import expanding_pct

OUT = Path("research/pre/artifacts")
COST_RT = 0.29                      # $/oz round trip: spread 0.22 + commission 0.07
HORIZONS = (6, 12, 24)
ENTRY_PCTILE = 0.90                 # frozen, from seq=60
N_ER, N_ATR_FAST, N_ATR_SLOW, N_SMA = 20, 14, 100, 200


def wilder_atr(df: pd.DataFrame, n: int) -> pd.Series:
    pc = df.close.shift(1)
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(),
                    (df.low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False).mean()


def build_state(df: pd.DataFrame) -> pd.DataFrame:
    """The three state variables. All use information available at bar close."""
    c = df.close
    num = (c - c.shift(N_ER)).abs()
    den = (c - c.shift(1)).abs().rolling(N_ER).sum().replace(0, np.nan)
    return pd.DataFrame({
        "ker20": num / den,
        "vol_ratio": wilder_atr(df, N_ATR_FAST) / wilder_atr(df, N_ATR_SLOW),
        "bias_atr": (c - c.rolling(N_SMA).mean()) / wilder_atr(df, N_ATR_FAST),
    }, index=df.index)


def forward_stats(df: pd.DataFrame, atr: pd.Series, h: int) -> pd.DataFrame:
    """Forward excursions over the next h bars, in ATR units, from bar close."""
    c = df.close.to_numpy(float)
    hi, lo = df.high.to_numpy(float), df.low.to_numpy(float)
    a = atr.to_numpy(float)
    n = len(c)
    mfe = np.full(n, np.nan)
    mae = np.full(n, np.nan)
    ret_usd = np.full(n, np.nan)
    for i in range(n - h - 1):
        w_hi = hi[i + 1:i + 1 + h].max()
        w_lo = lo[i + 1:i + 1 + h].min()
        mfe[i] = (w_hi - c[i]) / a[i]
        mae[i] = (c[i] - w_lo) / a[i]
        ret_usd[i] = c[i + h] - c[i]
    return pd.DataFrame({"mfe": mfe, "mae": mae, "ret_usd": ret_usd,
                         "abs_move_atr": np.abs(ret_usd) / a},
                        index=df.index)


def terciles(v: np.ndarray) -> np.ndarray:
    """Causal expanding tercile label (0/1/2), NaN until history exists."""
    p = expanding_pct(v)
    out = np.full(v.size, np.nan)
    out[p < 1 / 3] = 0
    out[(p >= 1 / 3) & (p < 2 / 3)] = 1
    out[p >= 2 / 3] = 2
    return out


def _boot_ci(x: np.ndarray, reps: int = 2000, seed: int = 20260827) -> tuple:
    """Bootstrap 95% CI of the mean — no normality assumption on fat tails."""
    rng = np.random.default_rng(seed)
    if x.size < 30:
        return (float("nan"), float("nan"))
    idx = rng.integers(0, x.size, size=(reps, x.size))
    m = x[idx].mean(axis=1)
    return (float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5)))


def arm_unsigned(state: pd.DataFrame, fwd: dict, var: str, absolute: bool) -> dict:
    """Does this state variable separate the SIZE of the forward move?"""
    v = state[var].to_numpy(float)
    if absolute:
        v = np.abs(v)
    t = terciles(v)
    out = {"variable": ("|" + var + "|") if absolute else var, "buckets": {}}
    for h, F in fwd.items():
        mfe, mae, am = (F.mfe.to_numpy(), F.mae.to_numpy(),
                        F.abs_move_atr.to_numpy())
        rows = {}
        for b in (0, 1, 2):
            m = (t == b) & np.isfinite(mfe) & np.isfinite(mae)
            if m.sum() < 100:
                continue
            rows[int(b)] = {
                "n": int(m.sum()),
                "mfe_atr": float(np.nanmean(mfe[m])),
                "mae_atr": float(np.nanmean(mae[m])),
                "e_ratio": float(np.nanmean(mfe[m]) / np.nanmean(mae[m])),
                "abs_move_atr": float(np.nanmean(am[m])),
            }
        if len(rows) == 3:
            lo, hi = rows[0]["abs_move_atr"], rows[2]["abs_move_atr"]
            a0 = am[(t == 0) & np.isfinite(am)]
            a2 = am[(t == 2) & np.isfinite(am)]
            ci0, ci2 = _boot_ci(a0), _boot_ci(a2)
            out["buckets"][h] = {
                "terciles": rows,
                "abs_move_top_minus_bottom": hi - lo,
                "separates": bool(ci0[1] < ci2[0] or ci2[1] < ci0[0]),
                "monotone": bool(rows[0]["abs_move_atr"] < rows[1]["abs_move_atr"]
                                 < rows[2]["abs_move_atr"]
                                 or rows[0]["abs_move_atr"] > rows[1]["abs_move_atr"]
                                 > rows[2]["abs_move_atr"]),
                "e_ratio_spread": rows[2]["e_ratio"] - rows[0]["e_ratio"],
            }
    return out


def arm_signed(state: pd.DataFrame, fwd: dict, var: str) -> dict:
    """Ordinary marginal test — appropriate only for the SIGNED variable."""
    v = state[var].to_numpy(float)
    t = terciles(v)
    out = {"variable": var, "buckets": {}}
    for h, F in fwd.items():
        r = F.ret_usd.to_numpy(float)
        rows = {}
        for b in (0, 1, 2):
            m = (t == b) & np.isfinite(r)
            if m.sum() < 100:
                continue
            x = r[m]
            ci = _boot_ci(x)
            rows[int(b)] = {"n": int(m.sum()), "mean_usd_per_oz": float(x.mean()),
                            "ci95": ci}
        if len(rows) == 3:
            spread = rows[2]["mean_usd_per_oz"] - rows[0]["mean_usd_per_oz"]
            out["buckets"][h] = {
                "terciles": rows, "spread_usd_per_oz": spread,
                "net_of_cost": spread - COST_RT,
                "pays_costs": bool(abs(spread) > COST_RT),
                "monotone": bool(rows[0]["mean_usd_per_oz"] < rows[1]["mean_usd_per_oz"]
                                 < rows[2]["mean_usd_per_oz"]
                                 or rows[0]["mean_usd_per_oz"] > rows[1]["mean_usd_per_oz"]
                                 > rows[2]["mean_usd_per_oz"]),
            }
    return out


def arm_conditional(df: pd.DataFrame, state: pd.DataFrame, horizon: int = 12) -> dict:
    """Does gating the ONE real directional effect on market state help?

    The signal is frozen from seq=60/65: long when the causal expanding
    percentile of intraday_ret >= 0.90, hold `horizon` bars, exit at market,
    non-overlapping. It is the only directional effect here that beat its own
    permutation null (p=0.010). Asking whether state improves it is a sharper
    question than asking whether state predicts returns.

    Reports every one of the 3 vars x 3 terciles = 9 cells so the BEST cell can
    be scored against the MEDIAN of the others. Per seq=68, picking the best of
    a grid carried negative value; a gate is a grid, so it needs the same
    control.
    """
    from research.pre.feature_screen import build_features
    feats, _ = build_features(df)
    sig = expanding_pct(feats["intraday_ret"].to_numpy(float))
    op = df.open.to_numpy(float)
    n = len(df)
    sf = 0.22 / 2000.0                       # spread as a fraction, ref price
    comm = 0.07

    ent = sig >= ENTRY_PCTILE
    tmaps = {v: terciles(state[v].to_numpy(float)) for v in state.columns}
    tmaps["|bias_atr|"] = terciles(np.abs(state["bias_atr"].to_numpy(float)))

    # walk once; record each trade with the state labels at its signal bar
    trades = []
    i = 0
    while i < n - horizon - 1:
        if not ent[i]:
            i += 1
            continue
        f, x = i + 1, i + 1 + horizon
        if x >= n:
            break
        e_px = op[f] * (1 + sf)
        pnl = (op[x] - e_px) - comm
        trades.append({"ret": pnl / e_px, "usd": pnl,
                       **{k: tmaps[k][i] for k in tmaps}})
        i = x
    T = pd.DataFrame(trades)
    if T.empty:
        return {"error": "no trades"}

    def stats(sub):
        r = sub["ret"].to_numpy(float)
        r = r[np.isfinite(r)]
        if r.size < 30 or r.std(ddof=1) == 0:
            return None
        return {"n": int(r.size), "mean_usd": float(sub["usd"].mean()),
                "per_obs_sharpe": float(r.mean() / r.std(ddof=1))}

    base = stats(T)
    cells = {}
    for var in tmaps:
        for b in (0, 1, 2):
            s = stats(T[T[var] == b])
            if s:
                cells[f"{var}=T{int(b)}"] = s
    if not cells:
        return {"unconditional": base, "cells": {}}
    srs = {k: v["per_obs_sharpe"] for k, v in cells.items()}
    best = max(srs, key=srs.get)
    others = [v for k, v in srs.items() if k != best]
    return {
        "unconditional": base, "cells": cells,
        "best_cell": best, "best_sharpe": srs[best],
        "pool_median_sharpe": float(np.median(others)),
        "best_minus_pool_median": float(srs[best] - np.median(others)),
        "best_minus_unconditional": float(srs[best] - base["per_obs_sharpe"]),
        "n_cells": len(cells),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tf", default="H1")
    a = ap.parse_args()

    df = load(a.tf, tz="server_eet", with_volume=True)
    state = build_state(df)
    atr = wilder_atr(df, N_ATR_FAST)
    fwd = {h: forward_stats(df, atr, h) for h in HORIZONS}

    res = {"timeframe": a.tf, "n_bars": int(len(df)),
           "lookbacks": {"er": N_ER, "atr_fast": N_ATR_FAST,
                         "atr_slow": N_ATR_SLOW, "sma": N_SMA},
           "cost_round_trip": COST_RT, "bucketing": "causal expanding terciles",
           "spearman": state.dropna().corr(method="spearman").round(4).to_dict(),
           "unsigned": {}, "signed": {}}
    for var, absolute in (("ker20", False), ("vol_ratio", False),
                          ("bias_atr", True)):
        k = ("|" + var + "|") if absolute else var
        res["unsigned"][k] = arm_unsigned(state, fwd, var, absolute)
    res["signed"]["bias_atr"] = arm_signed(state, fwd, "bias_atr")
    if a.tf == "H1":
        res["conditional"] = arm_conditional(df, state)

    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / f"state_screen_{a.tf}.json"
    p.write_text(json.dumps(res, indent=2, default=str))
    print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
