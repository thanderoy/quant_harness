"""research.post.sweeps.ebb_supplement — K4 neighbourhood + corrected DSR pool.

Re-runs only the cheap parts of the analysis (leader neighbourhood, DSR
variants) and merges them into ebb_report_data.json, so the expensive
permutation controls do not have to be recomputed.

Two corrections applied here:
  * empirical Var(SR) is taken over configs meeting the 100-trade floor. The
    raw grid contains configs with a handful of trades and arithmetically huge
    Sharpes, which inflate the sample variance to ~1e2 and push SR* to absurd
    values (43.1 per observation). That is a broken estimator, not evidence.
  * the leader's neighbourhood in (bb_n, bb_k) is evaluated for K4.

    python -m research.post.sweeps.ebb_supplement
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from research.post.dsr import deflated_sharpe_ratio
from research.post.sweeps import ebb_engine as E
from research.post.sweeps.analyze import GATES
from research.post.sweeps.data import load
from research.post.sweeps.ebb_analyze import DATA_DIR, _sim, load_all
from research.post.sweeps.zlch_engine import metrics

BB_NS = [10, 14, 20, 30, 50]
BB_KS = [1.5, 2.0, 2.5, 3.0]


def main() -> int:
    d = load_all()
    countable = d[d.n_trades >= GATES["n_trades_min"]]
    out = json.loads((DATA_DIR / "ebb_report_data.json").read_text())
    lead = out["leader"]
    tf = lead["timeframe"]

    # ---- K4: neighbourhood in (bb_n, bb_k) ---------------------------------
    pi, ki = BB_NS.index(int(lead["bb_n"])), BB_KS.index(float(lead["bb_k"]))
    nb = d[(d.timeframe == tf) & (d.er_max == lead["er_max"])
           & (d.sl_atr_mult == lead["sl_atr_mult"])
           & (d.time_stop_bars == lead["time_stop_bars"])
           & (d.direction == lead["direction"]) & (d.session == lead["session"])
           & d.bb_n.isin(BB_NS[max(0, pi-1):pi+2])
           & d.bb_k.isin(BB_KS[max(0, ki-1):ki+2])]
    out["neighbourhood"] = {
        "n": int(len(nb)),
        "median_sharpe": float(nb.sharpe_px.median()),
        "min_sharpe": float(nb.sharpe_px.min()),
        "max_sharpe": float(nb.sharpe_px.max()),
        "frac_positive": float((nb.sharpe_px > 0).mean()),
        "rows": json.loads(nb[["bb_n", "bb_k", "n_trades", "sharpe_px",
                               "profit_factor_px", "max_dd_px"]]
                           .sort_values(["bb_n", "bb_k"]).round(4)
                           .to_json(orient="records")),
    }

    # ---- corrected DSR -------------------------------------------------------
    bars = E.EbbBars(load(tf))
    r = _sim(lead, bars)["px_returns"]
    ppy = max(int(round(metrics(_sim(lead, bars), basis="price")["trades_per_year"])), 1)
    n_tf = int((d.timeframe == tf).sum())
    sh_tf = (countable[countable.timeframe == tf].sharpe_px.dropna()
             / np.sqrt(ppy)).to_numpy()
    variants = [
        (f"estimated SE / N={len(d):,} (full grid)", dict(n_trials=len(d))),
        (f"estimated SE / N={n_tf:,} ({tf} grid)", dict(n_trials=n_tf)),
        (f"empirical Var(SR), {tf} pool >=100 trades / N={n_tf:,}",
         dict(n_trials=n_tf, trial_sharpes=sh_tf)),
        ("estimated SE / N=16 (research log floor)", dict(n_trials=16)),
    ]
    out["dsr_variants"] = []
    for label, kw in variants:
        res = deflated_sharpe_ratio(r, periods_per_year=ppy, **kw)
        out["dsr_variants"].append({
            "label": label, "n_trials": res.n_trials, "var_sr": res.var_sr,
            "var_sr_source": res.var_sr_source, "sr_star": res.sr_star,
            "dsr": res.dsr, "passes": bool(res.passes),
            "sr_hat_per_obs": res.sr_hat_per_obs,
            "sr_hat_annualised": res.sr_hat_annualised})

    out["n_countable"] = int(len(countable))
    (DATA_DIR / "ebb_report_data.json").write_text(json.dumps(out, indent=2, default=str))
    print("neighbourhood:", {k: v for k, v in out["neighbourhood"].items() if k != "rows"})
    for v in out["dsr_variants"]:
        print(f'  {v["label"]:<52} SR*={v["sr_star"]:.4f} DSR={v["dsr"]:.4f} '
              f'{"PASS" if v["passes"] else "fail"}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
