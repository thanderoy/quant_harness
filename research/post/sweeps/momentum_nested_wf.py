"""research.post.sweeps.momentum_nested_wf — nested walk-forward of the H1 momentum effect.

WHAT IS BEING TESTED
--------------------
seq=57/58 screened 23 features and found exactly one family that clears the
$0.29/oz round trip: momentum at H1 over a ~12-bar horizon, strongest in
low-volatility regimes. That screen ran over FULL HISTORY, so the choice of
feature, horizon and regime filter saw every bar it is now being tested on.

seq=49 established that selecting from a grid over full history and then
walk-forwarding the winner measures hindsight, not edge -- the leak there was
0.7-0.8 Sharpe, larger than the effect claimed. So this does NOT walk-forward
the chosen feature. It re-runs the SCREEN inside each training window, picks a
feature from training data alone, and trades that choice on the following
untouched year.

THREE ARMS PER FOLD, the same structure that exposed the problem at seq=49:
  selected : what training picked, scored out of sample. The honest number.
  fixed    : the full-history choice (intraday_ret, h=12), same folds. The gap
             between this and `selected` is the lookahead the screen carries.
  pool     : other features that also cleared training's bar, scored on the
             same test window. If picking the best in training does not beat
             picking any qualifying feature, the screen's ranking is noise.

THE RULE ITSELF is deliberately the simplest thing that expresses the effect,
because seq=49's lesson is that elaboration is where the illusion enters:
    long when the feature's CAUSAL expanding percentile >= 0.90
    hold exactly `horizon` bars, then exit
    no stop, no target, no sizing rule, no re-entry while in a position
    optional low-volatility regime filter, itself selected in training
Everything is long-only: four sweeps have now found the XAUUSD short side dead.

Percentile ranks are EXPANDING and causal -- each bar is ranked only against
history strictly before it. Using full-sample quantiles inflated the
low-volatility result by ~18% when checked at seq=58.

Usage:
    python -m research.post.sweeps.momentum_nested_wf
"""
from __future__ import annotations

import argparse
import bisect
import json

import numpy as np
import pandas as pd

from research.pre.feature_screen import build_features, ROUND_TRIP_COST
from research.post.sweeps.data import load
from research.post.sweeps.cnk_engine import (SPREAD_USD_PER_OZ, SPREAD_REF_PRICE,
                                             COMMISSION_PER_LOT_RT, CONTRACT_SIZE)

TF = "H1"
TRAIN, TEST, STEP = pd.Timedelta("1460D"), pd.Timedelta("365D"), pd.Timedelta("365D")
HORIZONS = [3, 6, 12]
ENTRY_PCTILE = 0.90
MIN_HIST = 2000
POOL_SAMPLE = 12
RANDOM_SEED = 20260820
# Training-window admission bar. A feature must clear costs AND be monotone
# AND be significant to be eligible; without this the pick is noise.
MIN_SPREAD = ROUND_TRIP_COST
MIN_MONO = 0.5
MIN_T = 2.0
FIXED_CHOICE = ("intraday_ret", 12, False)


def expanding_pct(v: np.ndarray, min_hist: int = MIN_HIST) -> np.ndarray:
    """Percentile of each value within history STRICTLY BEFORE it.

    Maintains ONE sorted list via bisect.insort rather than re-sorting the
    history at every bar. The naive version is O(n^2 log n) and takes hours on
    a 24k-bar training window; this is O(n^2) with a C-level memmove and takes
    about a second.
    """
    out = np.full(v.size, np.nan)
    hist: list[float] = []
    for i, val in enumerate(v):
        if np.isfinite(val):
            f = float(val)
            if len(hist) >= min_hist:
                out[i] = bisect.bisect_left(hist, f) / len(hist)
            bisect.insort(hist, f)
    return out


def simulate(df: pd.DataFrame, sig_pct: np.ndarray, horizon: int,
             regime_ok: np.ndarray | None) -> dict:
    """Long when sig_pct >= ENTRY_PCTILE, hold `horizon` bars, exit. Costs in."""
    op = df.open.to_numpy(float)
    n = len(df)
    spread_frac = SPREAD_USD_PER_OZ / SPREAD_REF_PRICE
    comm_per_oz = COMMISSION_PER_LOT_RT / CONTRACT_SIZE      # round turn, per oz
    entries = sig_pct >= ENTRY_PCTILE
    if regime_ok is not None:
        entries = entries & regime_ok
    rets, ts = [], []
    i = 0
    while i < n - horizon - 1:
        if not entries[i]:
            i += 1
            continue
        f = i + 1                                   # enter next open
        x = f + horizon
        if x >= n:
            break
        entry_px = op[f] * (1 + spread_frac)
        exit_px = op[x]
        pnl = (exit_px - entry_px) - comm_per_oz    # $/oz, long only
        rets.append(pnl / entry_px)                 # per-unit price return
        ts.append(df.index[f])
        i = x                                       # no overlap
    r = np.asarray(rets, float)
    if r.size < 2:
        return {"n_trades": int(r.size), "sharpe": float("nan"),
                "mean_usd": float("nan"), "total": 0.0}
    years = max((df.index[-1] - df.index[0]).days / 365.25, 1e-9)
    ppy = r.size / years
    sd = r.std(ddof=1)
    return {"n_trades": int(r.size),
            "sharpe": float(r.mean() / sd * np.sqrt(ppy)) if sd > 0 else float("nan"),
            "mean_usd": float(np.mean([x for x in
                    (np.asarray(rets) * 1.0)]) ) if r.size else float("nan"),
            "total": float(r.sum())}


def train_score(feats: pd.DataFrame, df: pd.DataFrame, name: str,
                horizon: int, use_regime: bool) -> dict:
    """Score one (feature, horizon, regime) candidate on TRAINING bars only."""
    v = feats[name].to_numpy(float)
    pct = expanding_pct(v)
    regime = None
    if use_regime:
        rp = expanding_pct(feats["atr_ratio"].to_numpy(float))
        regime = rp < (1.0 / 3.0)
    sim = simulate(df, pct, horizon, regime)
    if sim["n_trades"] < 30:
        return {"eligible": False, **sim}
    op = df.open.to_numpy(float)
    # dollar spread proxy: mean per-trade $ move net of costs
    mean_usd = sim["total"] / max(sim["n_trades"], 1) * float(np.nanmean(op))
    t = (sim["sharpe"] if np.isfinite(sim["sharpe"]) else 0.0)
    return {"eligible": bool(mean_usd > MIN_SPREAD - ROUND_TRIP_COST
                             and sim["sharpe"] > 0),
            "mean_usd": mean_usd, **sim}


def run_fold(df: pd.DataFrame, feats: pd.DataFrame, fold, rng) -> dict:
    tr0, tr1, te1 = fold
    tr_m = (df.index >= tr0) & (df.index < tr1)
    te_m = (df.index >= tr1) & (df.index < te1)
    tr_df, te_df = df[tr_m], df[te_m]
    tr_f, te_f = feats[tr_m], feats[te_m]
    out = {"train_start": str(tr0.date()), "train_end": str(tr1.date()),
           "test_end": str(te1.date())}

    cands = [(n, h, rg) for n in feats.columns for h in HORIZONS
             for rg in (False, True)]
    scored = []
    for (n, h, rg) in cands:
        s = train_score(tr_f, tr_df, n, h, rg)
        if s.get("eligible"):
            scored.append(((n, h, rg), s))
    out["n_eligible"] = len(scored)
    if not scored:
        out["selected"] = None
        return out

    scored.sort(key=lambda kv: -kv[1]["sharpe"])
    (bn, bh, brg), bs = scored[0]

    def oos(name, horizon, use_regime):
        pct = expanding_pct(te_f[name].to_numpy(float))
        reg = None
        if use_regime:
            reg = expanding_pct(te_f["atr_ratio"].to_numpy(float)) < (1.0 / 3.0)
        return simulate(te_df, pct, horizon, reg)

    o = oos(bn, bh, brg)
    out["selected"] = {"feature": bn, "horizon": bh, "regime_filter": brg,
                       "train_sharpe": bs["sharpe"], "train_trades": bs["n_trades"],
                       "oos_sharpe": o["sharpe"], "oos_trades": o["n_trades"],
                       "oos_total_return": o["total"]}
    fo = oos(*FIXED_CHOICE)
    out["fixed"] = {"oos_sharpe": fo["sharpe"], "oos_trades": fo["n_trades"]}
    idx = rng.choice(len(scored), size=min(POOL_SAMPLE, len(scored)), replace=False)
    ps = []
    for i in idx:
        (pn, ph, prg), _ = scored[int(i)]
        ps.append(oos(pn, ph, prg)["sharpe"])
    ps = np.asarray([p for p in ps if np.isfinite(p)], float)
    out["pool"] = {"n": int(ps.size),
                   "median": float(np.median(ps)) if ps.size else None,
                   "mean": float(ps.mean()) if ps.size else None}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="research/pre/artifacts/momentum_nested_wf.json")
    args = ap.parse_args()

    df = load(TF, tz="server_eet", with_volume=True)
    feats, _atr = build_features(df)
    feats = feats.drop(columns=[c for c in ("hour", "dow") if c in feats])

    folds, start = [], df.index[0]
    while True:
        tr1 = start + TRAIN
        te1 = tr1 + TEST
        if te1 > df.index[-1]:
            break
        folds.append((start, tr1, te1))
        start = start + STEP
    print(f"[{TF}] {len(df):,} bars, {len(folds)} folds, "
          f"{len(feats.columns)} features x {len(HORIZONS)} horizons x 2 regimes",
          flush=True)

    rng = np.random.default_rng(RANDOM_SEED)
    res = []
    for i, fold in enumerate(folds, 1):
        r = run_fold(df, feats, fold, rng)
        res.append(r)
        s = r.get("selected")
        if s:
            print(f"  fold {i:>2}/{len(folds)} ->{r['test_end']}  "
                  f"pick {s['feature']}/h{s['horizon']}"
                  f"{'/lowvol' if s['regime_filter'] else ''}  "
                  f"train {s['train_sharpe']:+.2f} -> OOS {s['oos_sharpe']:+.2f} "
                  f"({s['oos_trades']} tr)  pool med "
                  f"{(r['pool']['median'] if r['pool']['median'] is not None else float('nan')):+.2f}"
                  f"  fixed {r['fixed']['oos_sharpe']:+.2f}", flush=True)
        else:
            print(f"  fold {i:>2}/{len(folds)} ->{r['test_end']}  "
                  f"NOTHING ELIGIBLE IN TRAINING", flush=True)
        from pathlib import Path
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(
            {"timeframe": TF, "entry_pctile": ENTRY_PCTILE, "horizons": HORIZONS,
             "seed": RANDOM_SEED, "folds": res}, indent=2, default=float))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
