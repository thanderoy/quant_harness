"""research.post.sweeps.report_data — consolidate every table the executive report needs."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.post.dsr import deflated_sharpe_ratio
from research.post.sweeps.analyze import GATES, apply_gates, load_all
from research.post.sweeps.deepdive import _build

REPO_ROOT = Path(__file__).resolve().parents[3]
ART = REPO_ROOT / "research" / "post" / "artifacts"
TF_ORDER = ["M5", "M15", "H1", "H4", "D1"]


def main() -> int:
    d = load_all()
    d["timeframe"] = pd.Categorical(d.timeframe, TF_ORDER, ordered=True)
    surv = apply_gates(d)
    dl = d[d.direction == "long"].copy()
    dl["bias"] = np.where(dl.bias_tf == "none", "none", "htf")

    dedup = ["timeframe", "atr_period", "atr_mult", "bias_tf", "zlsma_len",
             "direction", "n_trades", "sharpe_px"]

    tf_tab = d.groupby("timeframe", observed=True).agg(
        configs=("sharpe_px", "size"),
        median_sharpe=("sharpe_px", "median"),
        best_sharpe=("sharpe_px", "max"),
        pct_positive=("sharpe_px", lambda s: 100.0 * (s > 0).mean()),
        median_trades_yr=("trades_per_year", "median"),
        median_pf=("profit_factor_px", "median"),
        median_wr=("win_rate", "median"),
    )
    tf_tab["survivors"] = (surv.groupby("timeframe", observed=True).size()
                           .reindex(tf_tab.index).fillna(0).astype(int))

    out = {
        "n_configs": int(len(d)),
        "n_distinct": int(len(d.drop_duplicates(subset=dedup))),
        "n_survivors": int(len(surv)),
        "gates": GATES,
        "per_timeframe": json.loads(tf_tab.round(4).to_json(orient="index")),
        "direction_median": json.loads(
            d.pivot_table(index="timeframe", columns="direction",
                          values="sharpe_px", aggfunc="median", observed=True)
            .round(3).to_json(orient="index")),
        "bias_median_long": json.loads(
            dl.pivot_table(index="timeframe", columns="bias", values="sharpe_px",
                           aggfunc="median", observed=True)
            .round(3).to_json(orient="index")),
        "mult_median_long": json.loads(
            dl.pivot_table(index="timeframe", columns="atr_mult",
                           values="sharpe_px", aggfunc="median", observed=True)
            .round(3).to_json(orient="index")),
    }

    cols = ["timeframe", "atr_period", "atr_mult", "bias_tf", "zlsma_len",
            "direction", "n_trades", "sharpe_px", "max_dd_px",
            "profit_factor_px", "win_rate", "cagr_acct", "max_dd_acct"]
    for name, metric, asc in [("by_sharpe", "sharpe_px", False),
                              ("by_drawdown", "max_dd_px", True),
                              ("by_win_rate", "win_rate", False),
                              ("by_profit_factor", "profit_factor_px", False)]:
        t = (surv.drop_duplicates(subset=dedup)
                 .sort_values(metric, ascending=asc).head(10)[cols])
        out[name] = json.loads(t.round(4).to_json(orient="records"))

    out["best_per_tf"] = json.loads(
        d.loc[d.groupby("timeframe", observed=True).sharpe_px.idxmax()][cols]
        .round(4).to_json(orient="records"))

    orig = d[(d.timeframe == "M15") & (d.atr_period == 14) & (d.atr_mult == 2.5)
             & (d.bias_tf == "H4") & (d.zlsma_len == 50) & (d.min_atr == 0.0)]
    out["original_config"] = json.loads(orig[cols].round(4).to_json(orient="records"))
    m15 = d[(d.timeframe == "M15") & (d.direction == "both")].sharpe_px
    o = orig[orig.direction == "both"].sharpe_px.iloc[0]
    out["original_percentile_in_m15_both"] = float(100 * (m15 < o).mean())

    if (ART / "zlch_deepdive.csv").exists():
        dd = pd.read_csv(ART / "zlch_deepdive.csv")
        out["deepdive"] = json.loads(dd.round(4).to_json(orient="records"))

        best = d.sort_values("sharpe_px", ascending=False).iloc[0]
        _, _, _, _, sim = _build(best)
        r = sim["px_returns"]
        ppy = 41
        n_h4 = int((d.timeframe == "H4").sum())
        sh_h4 = (d[d.timeframe == "H4"].sharpe_px.dropna() / np.sqrt(ppy)).to_numpy()
        sh_all = (d.sharpe_px.dropna() / np.sqrt(ppy)).to_numpy()
        variants = [
            ("estimated SE / N=18,480 (full grid)", dict(n_trials=len(d))),
            ("estimated SE / N=15,630 (distinct)", dict(n_trials=out["n_distinct"])),
            ("estimated SE / N=3,696 (H4 grid)", dict(n_trials=n_h4)),
            ("empirical Var(SR), H4 pool / N=3,696",
             dict(n_trials=n_h4, trial_sharpes=sh_h4)),
            ("empirical Var(SR), full grid / N=18,480",
             dict(n_trials=len(d), trial_sharpes=sh_all)),
            ("estimated SE / N=15 (research log floor)", dict(n_trials=15)),
        ]
        out["dsr_variants"] = []
        for label, kw in variants:
            res = deflated_sharpe_ratio(r, periods_per_year=ppy, **kw)
            out["dsr_variants"].append({
                "label": label, "n_trials": res.n_trials, "var_sr": res.var_sr,
                "var_sr_source": res.var_sr_source, "sr_star": res.sr_star,
                "dsr": res.dsr, "passes": bool(res.passes),
                "sr_hat_per_obs": res.sr_hat_per_obs,
                "sr_hat_annualised": res.sr_hat_annualised,
            })

    (ART / "zlch_report_data.json").write_text(json.dumps(out, indent=2))
    print(f"wrote {ART/'zlch_report_data.json'}  keys={list(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
