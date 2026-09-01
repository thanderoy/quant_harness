"""research.pre.gold_yields_prereq — the same three prerequisites, on real yields.

gold_dxy_divergence died at seq=75 because the gold/dollar relationship, while
real and stable (rolling correlation -0.41, negative 100% of the time at a
252-day window), is essentially PURELY CONTEMPORANEOUS: the strongest non-zero
lag was 3.9% of the contemporaneous correlation and translated to 0.113x of the
round-trip cost. No lead-lag, no cointegration, nothing to trade.

Real yields are the better fundamental prior for gold than the dollar is -- gold
is a zero-coupon perpetual with no carry, so its opportunity cost IS the real
rate -- and the horizon is daily, which is the one regime where a $0.29/oz round
trip does not dominate. This runs the identical three tests so the two are
directly comparable, and adds nothing else.

THE LOOKAHEAD THAT WOULD MAKE THIS FAKE. DFII10 for date D is the Treasury's
constant-maturity real yield OBSERVED on D and published after the US close.
Gold trades around the clock. Pairing yield[D] with gold's return ON day D
therefore uses information that did not exist when that return was being
earned. That single alignment error would manufacture most of an apparent
relationship, because gold and yields move together intraday in response to the
same news. Both alignments are reported so the size of the illusion is visible:

    CONTEMPORANEOUS  yield change on D  vs  gold return on D    <- LOOKAHEAD
    CAUSAL           yield change on D  vs  gold return on D+1  <- tradeable

Only the causal figure decides anything.

Usage:  python -m research.pre.gold_yields_prereq
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.post.sweeps.data import load

OUT = Path("research/pre/artifacts/gold_yields_prereq.json")
YIELDS = Path("research/data/DFII10.csv")
ROLL_WINDOWS = (21, 63, 252)          # trading days
MAX_LAG = 10
COST_USD_PER_OZ = 0.29


def adf(y: np.ndarray, maxlag: int = 10) -> float:
    """ADF t-stat with a constant, AIC-selected lag. Calibrated at seq=76."""
    y = np.asarray(y, float)
    dy = np.diff(y)
    best = None
    for L in range(maxlag + 1):
        n = len(dy) - L
        if n < 100:
            break
        Y = dy[L:]
        cols = [np.ones(n), y[L:-1]]
        for i in range(1, L + 1):
            cols.append(dy[L - i:-i])
        X = np.column_stack(cols)
        beta, *_ = np.linalg.lstsq(X, Y, rcond=None)
        r = Y - X @ beta
        s2 = r @ r / (n - X.shape[1])
        aic = n * np.log(r @ r / n) + 2 * X.shape[1]
        if best is None or aic < best[0]:
            se = np.sqrt(s2 * np.linalg.inv(X.T @ X)[1, 1])
            best = (aic, beta[1] / se)
    return best[1]


def aligned() -> pd.DataFrame:
    g = load("D1", tz="server_eet", symbol="XAUUSD")
    g = g[~g.index.duplicated(keep="first")]
    gd = pd.DataFrame({"gold": g.close.astype(float)})
    gd.index = gd.index.tz_convert("UTC").normalize().tz_localize(None)
    gd = gd[~gd.index.duplicated(keep="last")]

    y = pd.read_csv(YIELDS)
    y.columns = ["date", "y"]
    y["date"] = pd.to_datetime(y["date"])
    y["y"] = pd.to_numeric(y["y"], errors="coerce")
    y = y.dropna().set_index("date").sort_index()

    df = gd.join(y, how="inner").dropna()
    return df.sort_index()


def main() -> int:
    df = aligned()
    lg = np.log(df.gold)
    rg = lg.diff()                       # gold log return on day D
    dy = df.y.diff()                     # yield CHANGE on day D, in pct points
    res = {"n_days": int(len(df)), "start": str(df.index[0].date()),
           "end": str(df.index[-1].date()), "cost_usd_per_oz": COST_USD_PER_OZ}
    print(f"aligned {len(df):,} trading days {df.index[0].date()} .. {df.index[-1].date()}\n")

    # 1 ------------------------------------------------------------- rolling
    print("1. ROLLING CORRELATION  (gold return vs yield change, same day)")
    res["rolling"] = {}
    for w in ROLL_WINDOWS:
        rc = rg.rolling(w).corr(dy).dropna()
        res["rolling"][w] = {"mean": float(rc.mean()), "sd": float(rc.std()),
                             "min": float(rc.min()), "max": float(rc.max()),
                             "frac_negative": float((rc < 0).mean())}
        print(f"   w={w:>4}d  mean {rc.mean():+.3f}  sd {rc.std():.3f}  "
              f"[{rc.min():+.3f}, {rc.max():+.3f}]  negative "
              f"{100*(rc < 0).mean():.0f}% of the time")
    res["full_sample_corr"] = float(rg.corr(dy))
    print(f"   full-sample: {res['full_sample_corr']:+.4f}")

    # 2 -------------------------------------------------------- cointegration
    print("\n2. COINTEGRATION  log(gold) vs yield LEVEL (Engle-Granger)")
    X = np.column_stack([np.ones(len(df)), df.y.to_numpy(float)])
    b, *_ = np.linalg.lstsq(X, lg.to_numpy(float), rcond=None)
    resid = lg.to_numpy(float) - X @ b
    t = adf(resid)
    CV = {"1%": -3.90, "5%": -3.34, "10%": -3.04}
    res["coint"] = {"beta": float(b[1]), "adf_t": float(t), "crit": CV,
                    "cointegrated_5pct": bool(t < CV["5%"])}
    print(f"   beta {b[1]:+.4f} log-gold per 1pp of real yield")
    print(f"   ADF t={t:.4f}  vs 5% crit {CV['5%']}  -> "
          f"{'COINTEGRATED' if t < CV['5%'] else 'NOT cointegrated'}")

    # 3 ------------------------------------------------- lead/lag + lookahead
    print("\n3. LEAD-LAG  (the test that killed the DXY version)")
    contemp = float(rg.corr(dy))
    causal = float(rg.corr(dy.shift(1)))
    res["contemporaneous_LOOKAHEAD"] = contemp
    res["causal_lag1"] = causal
    print(f"   contemporaneous (yield[D] vs gold[D])   {contemp:+.4f}   <- LOOKAHEAD")
    print(f"   causal          (yield[D] vs gold[D+1]) {causal:+.4f}   <- tradeable")
    print(f"   ratio causal/contemporaneous: {abs(causal)/abs(contemp):.4f}")
    lags = {k: float(rg.corr(dy.shift(k))) for k in range(-MAX_LAG, MAX_LAG + 1)}
    res["cross_corr"] = lags
    print("   lags k=1..5 (yield leads gold): " +
          "  ".join(f"{k}:{lags[k]:+.4f}" for k in range(1, 6)))
    n = int(rg.notna().sum())
    print(f"   (n={n:,}; 2/sqrt(n) = {2/np.sqrt(n):.4f})")

    # economic translation of the CAUSAL signal only
    x = dy.shift(1)
    m = np.isfinite(x) & np.isfinite(rg) 
    xv, yv = x[m].to_numpy(), rg[m].to_numpy()
    px = df.gold[m].to_numpy()
    sig = -np.sign(xv)                       # yields up -> gold down
    gross = sig * yv * px
    res["econ"] = {"gross_usd_per_oz": float(gross.mean()),
                   "net_usd_per_oz": float(gross.mean() - COST_USD_PER_OZ),
                   "gross_cost_ratio": float(abs(gross.mean()) / COST_USD_PER_OZ),
                   "n_trades": int(len(gross))}
    print(f"\n   ECONOMIC (causal signal, 1-day hold, both directions, "
          f"n={len(gross):,}):")
    print(f"     gross {gross.mean():+.4f} $/oz   net {gross.mean()-COST_USD_PER_OZ:+.4f}"
          f"   ratio to cost {abs(gross.mean())/COST_USD_PER_OZ:.3f}x")
    q = np.quantile(np.abs(xv), 0.9)
    big = np.abs(xv) >= q
    res["econ_decile"] = {"gross_usd_per_oz": float(gross[big].mean()),
                          "n": int(big.sum()),
                          "gross_cost_ratio": float(abs(gross[big].mean()) / COST_USD_PER_OZ)}
    print(f"     top-decile |yield move| (n={big.sum():,}): gross "
          f"{gross[big].mean():+.4f} $/oz  net {gross[big].mean()-COST_USD_PER_OZ:+.4f}"
          f"  ratio {abs(gross[big].mean())/COST_USD_PER_OZ:.3f}x")

    OUT.write_text(json.dumps(res, indent=2))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
