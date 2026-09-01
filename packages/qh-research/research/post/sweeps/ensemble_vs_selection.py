"""research.post.sweeps.ensemble_vs_selection — stop picking, start averaging?

Across every nested walk-forward this repo has run, the POOL beat the SELECTION:

    seq=68 zlch H4   selected +0.103   pool +0.164
    seq=68 zlch H1   selected -0.073   pool +0.168
    seq=70 gates     selected -0.157   pool +0.046
    seq=49 cnk       selected -0.124   pool -0.149   (the one exception, +0.025)

Mean across the four: selected -0.063, pool +0.057. Those pool figures were
CONTROLS -- the "what if you picked any qualifying config" null -- not results
anyone went looking for, which is why this is a finding rather than mining.

So the question is not which config to pick. It is whether to pick at all.
This tests EQUAL-WEIGHTING every gate-passer against taking the top-1 by
training Sharpe, out-of-sample, on the seq=66 zlch geometry.

TWO THINGS THAT WOULD MAKE THIS A MIRAGE, AND HOW THEY ARE HANDLED
1. Ensembling shrinks variance without creating edge. If every config has zero
   expected return, an average of them has zero expected return and a SMALLER
   denominator, so Sharpe rises while nothing is earned. That is the bias_atr
   trap from seq=71. The DECISIVE metric here is therefore total return in
   price-return units -- dollars, not Sharpe. Sharpe is reported as secondary.
2. K configs could mean K times the cost. Handled by construction: each config
   is held at 1/K size, and each config's returns already carry its own costs
   from the engine, so an equal-weight average charges the correct total. This
   IGNORES netting -- offsetting positions still each pay -- which makes the
   ensemble estimate CONSERVATIVE rather than flattering.

The sampled pool uses the same seed and size as seq=68's control, so the
ensemble is built from the identical configs that produced the pool numbers
above.

Usage:  python -m research.post.sweeps.ensemble_vs_selection --tf H4
"""
from __future__ import annotations

import argparse
import itertools
import json
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

from research.post.sweeps import default_workers
from research.post.sweeps import zlch_engine as E
from research.post.sweeps.data import load
from research.post.sweeps.run_sweep import (
    ATR_PERIODS, ATR_MULTS, RISK_PCT, OUT_DIR)
from research.post.sweeps.zlch_nested_wf import (
    BIAS_ORIGIN, CFG_KEYS, GATES_DD, GATES_PF, GATES_SR, POOL_SAMPLE,
    RANDOM_SEED, TRADE_FLOOR_MIN, TRADE_FLOOR_PER_YEAR, WINDOWS,
    _bias_full, _eval_unit, _folds, _init_worker, _label, _unit_full)


def _score(bars, bias_full, lo, hi, cfg, cache) -> dict:
    """One config on bars[lo:hi]. Returns total price-return and its trades."""
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
    r = np.asarray(sim["px_returns"], float)
    r = r[np.isfinite(r)]
    return {"total": float(r.sum()), "n": int(r.size), "rets": r}


def run_fold(pool, bars, bias_full, tf, fold, rng, cache) -> dict:
    tr0, tr1, te1 = fold
    idx = bars.index
    a = int(np.searchsorted(idx, tr0, "left"))
    b = int(np.searchsorted(idx, tr1, "left"))
    c = int(np.searchsorted(idx, te1, "left"))
    years = (tr1 - tr0).days / 365.25
    floor = max(TRADE_FLOOR_MIN, int(round(TRADE_FLOOR_PER_YEAR * years)))

    t0 = time.time()
    units = list(itertools.product(ATR_PERIODS, ATR_MULTS))
    rows = []
    for res in pool.imap_unordered(_eval_unit, [(u, a, b) for u in units]):
        rows.extend(res)
    tr = pd.DataFrame(rows)
    passers = tr[(tr.n_trades >= floor) & (tr.profit_factor >= GATES_PF)
                 & (tr.max_dd <= GATES_DD) & (tr.sharpe > GATES_SR)]
    out = {"train_end": str(tr1.date()), "test_end": str(te1.date()),
           "n_passers": int(len(passers)), "seconds": round(time.time() - t0, 1)}
    if passers.empty:
        return {**out, "top1": None, "ensemble": None}

    best = passers.sort_values("sharpe", ascending=False).iloc[0]
    s1 = _score(bars, bias_full, b, c, {k: best[k] for k in CFG_KEYS}, cache)
    out["top1"] = {"config": _label({k: best[k] for k in CFG_KEYS}),
                   "total": s1["total"], "n_trades": s1["n"],
                   "sharpe": float(s1["rets"].mean() / s1["rets"].std(ddof=1))
                   if s1["n"] > 2 and s1["rets"].std(ddof=1) > 0 else float("nan")}

    # Same seed and sample size as the seq=68 pool control -> identical configs.
    sel = rng.choice(len(passers), size=min(POOL_SAMPLE, len(passers)),
                     replace=False)
    totals, all_rets, ns = [], [], []
    for i in sel:
        r = passers.iloc[int(i)]
        s = _score(bars, bias_full, b, c, {k: r[k] for k in CFG_KEYS}, cache)
        totals.append(s["total"])
        ns.append(s["n"])
        if s["n"]:
            all_rets.append(s["rets"] / len(sel))     # 1/K sizing
    tot = np.asarray(totals, float)
    pooled = np.concatenate(all_rets) if all_rets else np.array([])
    out["ensemble"] = {
        "k": int(len(sel)),
        "total": float(tot.mean()),                   # equal-weight allocation
        "median_member_total": float(np.median(tot)),
        "frac_members_positive": float((tot > 0).mean()),
        "mean_member_trades": float(np.mean(ns)),
        "sharpe": float(pooled.mean() / pooled.std(ddof=1))
        if pooled.size > 2 and pooled.std(ddof=1) > 0 else float("nan"),
    }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tf", choices=["H1", "H4"], required=True)
    ap.add_argument("--workers", type=int, default=default_workers())
    a = ap.parse_args()

    df = load(a.tf)
    bars = E.Bars(df)
    bias_full = _bias_full(bars, df.index, a.tf)
    folds = _folds(df, a.tf)
    rng = np.random.default_rng(RANDOM_SEED)
    cache: dict = {}
    print(f"[{a.tf}] {len(df):,} bars | {len(folds)} folds | K={POOL_SAMPLE}", flush=True)

    results = []
    with Pool(a.workers, initializer=_init_worker,
              initargs=(df, bias_full, a.tf)) as pool:
        for i, fold in enumerate(folds, 1):
            r = run_fold(pool, bars, bias_full, a.tf, fold, rng, cache)
            results.append(r)
            if r["top1"]:
                print(f"  fold {i:>2}/{len(folds)} ->{r['test_end']}  "
                      f"top1 {r['top1']['total']:+.4f} ({r['top1']['n_trades']:>3}tr)  "
                      f"ens {r['ensemble']['total']:+.4f} "
                      f"({r['ensemble']['frac_members_positive']*100:.0f}% members +)  "
                      f"[{r['seconds']:.0f}s]", flush=True)
            else:
                print(f"  fold {i:>2}/{len(folds)} ->{r['test_end']}  NO PASSERS", flush=True)

    ok = [r for r in results if r["top1"]]
    t1 = np.array([r["top1"]["total"] for r in ok])
    en = np.array([r["ensemble"]["total"] for r in ok])
    from math import comb
    w = int((en > t1).sum()); n = len(ok)
    p = min(1.0, 2 * sum(comb(n, k) for k in range(w, n + 1)) / 2 ** n)
    summary = {"timeframe": a.tf, "n_folds": n, "k": POOL_SAMPLE,
               "top1_mean_total": float(t1.mean()), "ens_mean_total": float(en.mean()),
               "ens_minus_top1": float(en.mean() - t1.mean()),
               "ens_beats_top1_folds": w, "sign_p": p,
               "top1_mean_sharpe": float(np.nanmean([r["top1"]["sharpe"] for r in ok])),
               "ens_mean_sharpe": float(np.nanmean([r["ensemble"]["sharpe"] for r in ok])),
               "folds": results}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / f"ensemble_vs_selection_{a.tf}.json").write_text(json.dumps(summary, indent=2))
    print("\n" + json.dumps({k: v for k, v in summary.items() if k != "folds"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
