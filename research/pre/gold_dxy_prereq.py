"""research.pre.gold_dxy_prereq — the falsification prerequisites seq=18 named.

seq=17 registered gold_dxy_divergence as an idea and seq=18 recorded that its
prerequisites were undone with NO SPEC written: "rolling correlation, CADF
cointegration test, cross-corr lag analysis". This runs exactly those three and
nothing else. It is deliberately NOT a strategy: no entry rule, no exit, no
sizing, no parameter search. Writing a spec and testing it in the same motion
is the entry-trigger archaeology this programme has repeatedly shown to be
worthless.

What each question decides:

  1 ROLLING CORRELATION -- is the gold/dollar relationship stable enough to
    trade, or does it wander? A divergence idea needs a reliable baseline to
    diverge FROM. If rho swings sign across regimes there is no baseline.

  2 COINTEGRATION -- do the log levels share a stochastic trend, so that gaps
    between them mean-revert? Without it, "divergence" has no restoring force
    and any apparent signal is two random walks drifting apart.

  3 CROSS-CORRELATION LAG -- does either series LEAD? A contemporaneous-only
    relationship is not tradeable: knowing gold and the dollar move together
    right now tells you nothing about the next bar. This is the question that
    decides whether anything is buildable at all.

DXY is the validated synthetic (research/pre/synthetic_dxy.py); the broker's
USDX was rejected as a reference -- 29.5% zero returns and 143 unique prices in
3,540 bars.

Usage:  python -m research.pre.gold_dxy_prereq
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.post.sweeps.data import load
from research.pre.synthetic_dxy import build as build_dxy

OUT = Path("research/pre/artifacts/gold_dxy_prereq.json")
ROLL_WINDOWS = (24 * 5, 24 * 21, 24 * 63, 24 * 252)      # ~1w, 1m, 1q, 1y of H1
MAX_LAG = 24


def aligned() -> pd.DataFrame:
    xau = load("H1", tz="server_eet", symbol="XAUUSD")
    dxy = build_dxy()
    idx = xau.index.intersection(dxy.index)
    df = pd.DataFrame({"xau": xau.loc[idx, "close"].astype(float),
                       "dxy": dxy.loc[idx, "close"].astype(float)}).dropna()
    return df.sort_index()


def main() -> int:
    df = aligned()
    lx, ld = np.log(df.xau), np.log(df.dxy)
    rx, rd = lx.diff(), ld.diff()
    res = {"n_bars": int(len(df)), "start": str(df.index[0]), "end": str(df.index[-1])}
    print(f"aligned {len(df):,} H1 bars {df.index[0].date()} .. {df.index[-1].date()}\n")

    # 1 ---------------------------------------------------------------- rolling
    print("1. ROLLING CORRELATION of log returns")
    res["rolling"] = {}
    for w in ROLL_WINDOWS:
        rc = rx.rolling(w).corr(rd).dropna()
        frac_neg = float((rc < 0).mean())
        res["rolling"][w] = {"mean": float(rc.mean()), "sd": float(rc.std()),
                             "min": float(rc.min()), "max": float(rc.max()),
                             "q05": float(rc.quantile(.05)), "q95": float(rc.quantile(.95)),
                             "frac_negative": frac_neg}
        print(f"   w={w:>5} ({w//24:>3}d)  mean {rc.mean():+.3f}  sd {rc.std():.3f}  "
              f"[{rc.min():+.3f}, {rc.max():+.3f}]  negative {100*frac_neg:.0f}% of the time")
    res["full_sample_corr"] = float(rx.corr(rd))
    print(f"   full-sample return correlation: {res['full_sample_corr']:+.4f}")

    # 2 ----------------------------------------------------------- cointegration
    print("\n2. COINTEGRATION of log levels (Engle-Granger)")
    try:
        from statsmodels.tsa.stattools import coint, adfuller
        t, p, cv = coint(lx, ld)
        res["coint"] = {"tstat": float(t), "pvalue": float(p),
                        "crit_1pct": float(cv[0]), "crit_5pct": float(cv[1]),
                        "crit_10pct": float(cv[2]), "cointegrated_5pct": bool(p < 0.05)}
        print(f"   EG t={t:.4f}  p={p:.4f}  crit 5% {cv[1]:.4f}  "
              f"-> {'COINTEGRATED' if p < 0.05 else 'NOT cointegrated'} at 5%")
        beta = np.polyfit(ld, lx, 1)[0]
        spread = lx - beta * ld
        a = adfuller(spread.dropna(), maxlag=24, autolag="AIC")
        res["spread_adf"] = {"beta": float(beta), "tstat": float(a[0]),
                             "pvalue": float(a[1]), "stationary_5pct": bool(a[1] < 0.05)}
        print(f"   hedge beta {beta:+.4f}; ADF on spread t={a[0]:.4f} p={a[1]:.4f} "
              f"-> {'stationary' if a[1] < 0.05 else 'NON-stationary'}")
    except ImportError:
        res["coint"] = {"error": "statsmodels unavailable"}
        print("   statsmodels unavailable")

    # 3 ------------------------------------------------------------ lead / lag
    print("\n3. CROSS-CORRELATION -- does either series LEAD?")
    lags = {}
    for k in range(-MAX_LAG, MAX_LAG + 1):
        lags[k] = float(rx.corr(rd.shift(k)))
    res["cross_corr"] = lags
    contemp = lags[0]
    off = {k: v for k, v in lags.items() if k != 0}
    best_k = max(off, key=lambda k: abs(off[k]))
    res["contemporaneous"] = contemp
    res["best_lagged_k"] = int(best_k)
    res["best_lagged_corr"] = float(off[best_k])
    res["lead_lag_ratio"] = float(abs(off[best_k]) / abs(contemp)) if contemp else float("nan")
    print(f"   contemporaneous (k=0): {contemp:+.4f}")
    print(f"   strongest non-zero lag: k={best_k:+d} -> {off[best_k]:+.4f}")
    print(f"   |lagged| / |contemporaneous| = {res['lead_lag_ratio']:.4f}")
    print("   nearby lags: " + "  ".join(
        f"{k:+d}:{lags[k]:+.4f}" for k in (-3, -2, -1, 0, 1, 2, 3)))
    n = len(rx.dropna())
    res["corr_se"] = float(1 / np.sqrt(n))
    print(f"   (n={n:,}; 1/sqrt(n) = {1/np.sqrt(n):.4f} -- correlations below "
          f"~{2/np.sqrt(n):.4f} are within 2 SE of zero)")

    OUT.write_text(json.dumps(res, indent=2))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
