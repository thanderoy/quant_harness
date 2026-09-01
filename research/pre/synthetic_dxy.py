"""research.pre.synthetic_dxy — reconstruct the dollar index from its legs.

The broker's own `USDX` instrument was evaluated and rejected (seq=73): only
3,548 H1 bars (2.5 years) and a price range of 25.00-26.43 against a real index
trading ~100-107, i.e. roughly a 4x scale offset. Too shallow to run folds on,
and not verifiably the index.

All six ICE legs ARE available at 80,000 H1 bars each back to 2013-10, so the
index is reconstructed directly rather than substituted. The ICE definition is
a geometric weighted basket:

    DXY = 50.14348112
          * EURUSD ^ -0.576
          * USDJPY ^ +0.136
          * GBPUSD ^ -0.119
          * USDCAD ^ +0.091
          * USDSEK ^ +0.042
          * USDCHF ^ +0.036

Negative exponents are the legs quoted as FOREIGN/USD (a rising EURUSD is a
falling dollar); positive are USD/FOREIGN. Weights sum to 1.000.

VALIDATION. USDX is too short to study but IS long enough to verify the
reconstruction. Because the basket is geometric, any constant scale factor
cancels in log returns, so a scale offset does not impair the check: if
synthetic and USDX log returns agree over the 2.5-year overlap, the
construction is right regardless of USDX's absolute level. `validate()`
reports that correlation and the implied scale ratio.

Usage:  python -m research.pre.synthetic_dxy
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.post.sweeps.data import load

OUT = Path("research/pre/artifacts")
CSV = Path("research/data/SYNDXY_H1.csv")

ICE_CONSTANT = 50.14348112
# (symbol, exponent). Negative => quoted FOREIGN/USD.
LEGS = [("EURUSD", -0.576), ("USDJPY", 0.136), ("GBPUSD", -0.119),
        ("USDCAD", 0.091), ("USDSEK", 0.042), ("USDCHF", 0.036)]


def build(tz: str = "server_eet") -> pd.DataFrame:
    """Synthetic DXY OHLC on the timestamps common to all six legs."""
    frames = {}
    for sym, _ in LEGS:
        d = load("H1", tz=tz, symbol=sym)
        frames[sym] = d[~d.index.duplicated(keep="first")]
    idx = None
    for d in frames.values():
        idx = d.index if idx is None else idx.intersection(d.index)
    idx = idx.sort_values()

    # Geometric basket, applied per OHLC field. For a negatively-weighted leg a
    # rising quote LOWERS the index, so its high feeds the index low. Tracking
    # that keeps the synthetic bar's range honest rather than merely indicative.
    out = {}
    for field in ("open", "high", "low", "close"):
        acc = np.full(len(idx), ICE_CONSTANT, dtype=float)
        for sym, w in LEGS:
            src = field
            if w < 0 and field in ("high", "low"):
                src = "low" if field == "high" else "high"
            acc *= frames[sym].loc[idx, src].to_numpy(float) ** w
        out[field] = acc
    df = pd.DataFrame(out, index=idx)
    df["volume"] = frames["EURUSD"].loc[idx].get(
        "volume", pd.Series(0.0, index=idx)).to_numpy(float) \
        if "volume" in frames["EURUSD"] else 0.0
    return df


def validate(syn: pd.DataFrame) -> dict:
    """Check the reconstruction against the broker's USDX over the overlap."""
    try:
        ux = load("H1", tz="server_eet", symbol="USDX")
    except FileNotFoundError:
        return {"validated": False, "reason": "USDX csv absent"}
    idx = syn.index.intersection(ux.index)
    if len(idx) < 500:
        return {"validated": False, "reason": f"overlap only {len(idx)} bars"}
    a = syn.loc[idx, "close"].to_numpy(float)
    b = ux.loc[idx, "close"].to_numpy(float)
    ra = np.diff(np.log(a))
    rb = np.diff(np.log(b))
    m = np.isfinite(ra) & np.isfinite(rb)
    return {
        "validated": True, "overlap_bars": int(len(idx)),
        "overlap_start": str(idx[0]), "overlap_end": str(idx[-1]),
        "logret_pearson": float(np.corrcoef(ra[m], rb[m])[0, 1]),
        "logret_spearman": float(pd.Series(ra[m]).corr(pd.Series(rb[m]), method="spearman")),
        "level_pearson": float(np.corrcoef(a, b)[0, 1]),
        "scale_ratio_mean": float(np.mean(a / b)),
        "scale_ratio_sd": float(np.std(a / b)),
    }


def main() -> int:
    syn = build()
    OUT.mkdir(parents=True, exist_ok=True)
    # Same on-disk format as every other series here, so load() can read it.
    exp = syn.copy()
    exp.index.name = "Date"
    exp = exp.reset_index()
    exp["Date"] = exp["Date"].dt.strftime("%Y.%m.%d %H:%M")
    exp.columns = ["Date", "Open", "High", "Low", "Close", "Volume"]
    CSV.write_text(exp.to_csv(sep=";", index=False, lineterminator="\n"))

    v = validate(syn)
    meta = {"n_bars": int(len(syn)), "start": str(syn.index[0]),
            "end": str(syn.index[-1]),
            "level_min": float(syn.close.min()), "level_max": float(syn.close.max()),
            "legs": {s: w for s, w in LEGS}, "validation": v}
    (OUT / "synthetic_dxy.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
