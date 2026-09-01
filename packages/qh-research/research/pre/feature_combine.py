"""research.pre.feature_combine — do the surviving features combine into an edge?

Follows research/pre/feature_screen.py. That screen found that at M5 NOTHING
clears the $0.29/oz round trip, and that what does clear it at H1 is a
momentum family at a ~12-bar horizon. This asks two follow-up questions:

1. COMBINATION. Do the surviving features carry independent information, or
   are they one effect wearing several hats? Tested by (a) their correlation
   matrix and (b) whether an equal-weight composite of their cross-sectional
   ranks beats the best single feature.

2. CONDITIONING. Gao/Han/Li/Zhou report that intraday momentum is stronger on
   high-volatility and high-volume days. That is a mechanism-derived
   prediction, not a parameter to tune, so it gets tested directly rather than
   swept: does the momentum spread widen in the top volatility/volume tercile?

Everything is scored in $/oz against the round-trip cost, as in the screen.
No parameter search: the feature set is inherited from the screen's FDR
survivors and the conditioning variable is specified by the source paper.

Usage:  python -m research.pre.feature_combine
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy import stats

from research.pre.feature_screen import (build_features, forward_return,
                                         _nw_tstat, ROUND_TRIP_COST, OUT_DIR,
                                         N_DECILES)
from research.post.sweeps.data import load

TF = "H1"
HORIZON = 12
# Inherited from the screen: FDR-significant, clears costs, monotonicity > 0.7.
SURVIVORS = ["intraday_ret", "ret_12", "dist_pdl", "dist_pdh", "dist_vwap"]


def _spread(sig: pd.Series, usd: pd.Series, horizon: int) -> dict:
    m = np.isfinite(sig) & np.isfinite(usd)
    x, y = sig[m], usd[m]
    if x.size < 500:
        return {"n": int(x.size), "skipped": True}
    try:
        q = pd.qcut(x, N_DECILES, labels=False, duplicates="drop")
    except ValueError:
        return {"n": int(x.size), "skipped": True}
    nq = int(np.nanmax(q)) + 1
    top, bot = q == nq - 1, q == 0
    spread = float(y[top].mean() - y[bot].mean())
    combined = np.concatenate([y[top].to_numpy(), -y[bot].to_numpy()])
    t = _nw_tstat(combined, lags=max(horizon * 2, 2))
    means = [float(y[q == i].mean()) for i in range(nq)]
    mono = float(stats.spearmanr(np.arange(nq), means).statistic)
    return {"n": int(x.size), "spread_usd_per_oz": spread,
            "net_usd_per_oz": spread - ROUND_TRIP_COST, "nw_t": t,
            "monotonicity": mono, "pays_costs": bool(abs(spread) > ROUND_TRIP_COST)}


def main() -> int:
    df = load(TF, tz="server_eet", with_volume=True)
    feats, atr = build_features(df)
    usd, _ = forward_return(df, atr, HORIZON)

    sub = feats[SURVIVORS]
    out = {"timeframe": TF, "horizon": HORIZON, "features": SURVIVORS,
           "cost_round_trip": ROUND_TRIP_COST}

    # --- 1. are they independent? -----------------------------------------
    corr = sub.corr(method="spearman")
    out["spearman_corr"] = corr.round(4).to_dict()
    print("Spearman correlation between survivors:")
    print(corr.round(3).to_string())

    # --- 2. individual baselines ------------------------------------------
    print("\nIndividual (baseline, from the screen):")
    out["individual"] = {}
    for f in SURVIVORS:
        r = _spread(sub[f], usd, HORIZON)
        out["individual"][f] = r
        print(f"  {f:<14} spread ${r['spread_usd_per_oz']:>6.3f}  "
              f"net ${r['net_usd_per_oz']:>6.3f}  t {r['nw_t']:>5.2f}  "
              f"mono {r['monotonicity']:>5.2f}")

    # --- 3. equal-weight rank composite -----------------------------------
    ranks = sub.rank(pct=True)
    composite = ranks.mean(axis=1)
    r = _spread(composite, usd, HORIZON)
    out["composite_all"] = r
    print(f"\nComposite (equal-weight rank of all {len(SURVIVORS)}):"
          f"  spread ${r['spread_usd_per_oz']:.3f}  net ${r['net_usd_per_oz']:.3f}"
          f"  t {r['nw_t']:.2f}  mono {r['monotonicity']:.2f}")

    # momentum-only composite (the two strongest, same family)
    mom = ranks[["intraday_ret", "ret_12"]].mean(axis=1)
    r2 = _spread(mom, usd, HORIZON)
    out["composite_momentum"] = r2
    print(f"Composite (momentum pair only):"
          f"          spread ${r2['spread_usd_per_oz']:.3f}  "
          f"net ${r2['net_usd_per_oz']:.3f}  t {r2['nw_t']:.2f}  "
          f"mono {r2['monotonicity']:.2f}")

    # --- 4. conditioning, as specified by Gao/Han/Li/Zhou ------------------
    # Their claim: intraday momentum is STRONGER on high-volatility and
    # high-volume days. Tested as stated, not tuned.
    print("\nConditioning (Gao/Han/Li/Zhou: stronger on volatile / high-volume):")
    out["conditioned"] = {}
    for cond_name, cond in (("atr_ratio", feats["atr_ratio"]),
                            ("vol_z", feats["vol_z"])):
        terc = pd.qcut(cond.rank(method="first"), 3, labels=["low", "mid", "high"])
        out["conditioned"][cond_name] = {}
        for level in ("low", "mid", "high"):
            m = terc == level
            r3 = _spread(feats["intraday_ret"][m], usd[m], HORIZON)
            out["conditioned"][cond_name][level] = r3
            if "skipped" in r3:
                continue
            print(f"  intraday_ret | {cond_name}={level:<5} "
                  f"spread ${r3['spread_usd_per_oz']:>6.3f}  "
                  f"net ${r3['net_usd_per_oz']:>6.3f}  t {r3['nw_t']:>5.2f}  "
                  f"mono {r3['monotonicity']:>5.2f}  n={r3['n']:,}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "feature_combine.json").write_text(json.dumps(out, indent=2, default=float))
    print(f"\nwrote {OUT_DIR / 'feature_combine.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
