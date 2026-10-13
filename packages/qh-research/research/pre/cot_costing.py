"""Phase 4 — does the COT positioning effect survive what it costs to trade?

``cot_positioning_residual`` passed at seq=144: the part of speculators'
positioning that past returns do not explain is contrarian in FX. This puts a
price on trading it, before any strategy or out-of-sample hold.

**The trade.** At each report's release (the same entry and exit as
seq=143): long the instrument when its residual signal is in the LOW tercile,
short when in the HIGH, flat in between; exit at the next release. One round
trip per active interval.

**The labels are seq=143's**, cut on each instrument's full sample. That is
how the registered test was defined, and it is not a causal rule: a trader
could not have known the tercile cut-points in advance. So the gross figure
here is an upper bound on what a causal rule would earn; the causal version
is the out-of-sample hold's job.

**Costs** are fixed before the gross P&L is read, from measured inputs:

* Commission: zero, on all 358 live deals (seq=105, Standard account).
* Slippage beyond the quote, per side, from live fills (#68,
  ``phase0/execution_cost_20261011.json``): mean (base) and p90 (stress).
  Exits there include take-profit and stop fills, so stress is conservative.
* Quoted spread in the hour after the Friday release, from the live tick
  feed over 92 Fridays (2026-10-13): median (base) and p90 (stress).
* USDJPY, USDCHF and USDCAD have no live fills; they take the worst
  measured FX pair's round trip in pips.

Costs are compared in units of return: a round trip's price cost over the
instrument's price at entry.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from research.pre import cot_positioning as cp
from research.pre import cot_residual as cr
from research.pre.activity_reversal import _admitted_frame, label_terciles
from research.pre.panel_edge import PANEL_2B, STRUCTURE, _default_data_dir

#: Round-trip cost in price units, per scenario. Sources in the module doc.
#: FX: (entry slip + exit slip) ticks x 1e-5 (1e-3 for JPY) + quoted spread.
ROUND_TRIP: dict[str, dict[str, float]] = {
    "base": {
        "EURUSD": (2.76 + 3.81) * 1e-5 + 0.0,
        "GBPUSD": (0.81 + 4.12) * 1e-5 + 1e-5,
        "AUDUSD": (2.20 + 6.13) * 1e-5 + 1e-5,
        "NZDUSD": (1.86 + 4.57) * 1e-5 + 2e-5,
        "XAUUSD": 0.15,           # slip measured favourable; spread only
        "XAGUSD": 0.0315,
    },
    "stress": {
        "EURUSD": (5.0 + 9.0) * 1e-5 + 0.0,
        "GBPUSD": (4.5 + 13.0) * 1e-5 + 2e-5,
        "AUDUSD": (7.4 + 12.2) * 1e-5 + 1e-5,
        "NZDUSD": (4.0 + 7.8) * 1e-5 + 2e-5,
        "XAUUSD": (10.8 + 61.0) * 0.01 + 0.19,
        "XAGUSD": 0.057 * 3,      # no silver fills: three p90 spreads
    },
}
#: Pips per price unit, to carry the worst measured FX round trip to pairs
#: with no fills.
PIP = {"USDJPY": 0.01, "USDCHF": 1e-4, "USDCAD": 1e-4}
MEASURED_FX = ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD")


def round_trip(sym: str, scenario: str) -> Optional[float]:
    """Price-unit cost of one round trip; None where nothing applies (GER40)."""
    table = ROUND_TRIP[scenario]
    if sym in table:
        return table[sym]
    if sym in PIP:
        worst_pips = max(table[s] / 1e-4 for s in MEASURED_FX)
        return worst_pips * PIP[sym]
    return None


def trades(df: pd.DataFrame, fr: pd.DataFrame) -> pd.DataFrame:
    """One row per active interval: side, entry price and gross log return."""
    logc = np.log(df["close"].to_numpy(float))
    lab = label_terciles(fr["signal"])
    side = np.where(lab == 0, 1, np.where(lab == 2, -1, 0))
    p = fr["pos"].to_numpy()
    nxt = np.r_[p[1:], -1]
    ok = (side != 0) & (nxt > 0)
    gross = side[ok] * (logc[nxt[ok]] - logc[p[ok]])
    return pd.DataFrame({"report_date": fr["report_date"].to_numpy()[ok],
                         "side": side[ok], "entry": np.exp(logc[p[ok]]),
                         "gross": gross})


def summarise(t: pd.DataFrame, cost_price: Optional[float]) -> dict:
    g = t["gross"].to_numpy()
    out = {"n_trades": int(g.size), "gross_mean_bp": float(g.mean() * 1e4),
           "gross_t": float(g.mean() / (g.std(ddof=1) / np.sqrt(g.size)))}
    if cost_price is not None:
        c = cost_price / t["entry"].to_numpy()
        net = g - c
        out.update({"cost_mean_bp": float(c.mean() * 1e4),
                    "net_mean_bp": float(net.mean() * 1e4),
                    "net_t": float(net.mean() / (net.std(ddof=1) / np.sqrt(net.size))),
                    "cost_share_of_gross": float(c.mean() / g.mean())
                    if g.mean() > 0 else None})
    return out


def run(data_dir: Optional[Path] = None,
        symbols: tuple[str, ...] = PANEL_2B) -> dict:
    data_dir = Path(data_dir) if data_dir else _default_data_dir()
    cot = cp.load_cot()
    out: dict = {"instruments": {}, "fx_pooled": {}}
    fx_trades = []
    for sym in symbols:
        market, orient = cp.MARKETS[sym]
        df, _ = _admitted_frame(sym, data_dir)
        fr = cr.instrument_frame(df, cp.positioning_z(cot, market, orient),
                                 with_outcomes=True)
        if len(fr) < 3 * cp.MIN_CELL:
            continue
        t = trades(df, fr)
        out["instruments"][sym] = {
            "structure": STRUCTURE[sym],
            **{s: summarise(t, round_trip(sym, s)) for s in ROUND_TRIP}}
        if STRUCTURE[sym] == "fx":
            for s in ROUND_TRIP:
                c = round_trip(sym, s) / t["entry"].to_numpy()
                t[f"net_{s}"] = t["gross"].to_numpy() - c
            fx_trades.append(t)
    fx = pd.concat(fx_trades)
    for s in ROUND_TRIP:
        n = fx[f"net_{s}"].to_numpy()
        out["fx_pooled"][s] = {
            "n_trades": int(n.size),
            "gross_mean_bp": float(fx["gross"].mean() * 1e4),
            "net_mean_bp": float(n.mean() * 1e4),
            "net_t": float(n.mean() / (n.std(ddof=1) / np.sqrt(n.size)))}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    res = run(args.data_dir)
    text = json.dumps(res, indent=1, default=float)
    if args.out:
        args.out.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
