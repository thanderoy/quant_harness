"""research.post.sweeps.analyze — rank sweep survivors and test the parameter surface.

Produces the executive-report data set:
  * survival gates applied to every swept config
  * rankings by Sharpe, drawdown, win rate and profit factor
  * neighbourhood robustness (is the leader a plateau or an isolated spike?)
  * Deflated Sharpe at N = full grid size, using the sweep's own trial Sharpes
    as the empirical Var(SR) source

Usage:  python -m research.post.sweeps.analyze
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.post.dsr import deflated_sharpe_ratio
from research.post.sweeps import zlch_engine as E
from research.post.sweeps.data import RESAMPLE_RULE, load

REPO_ROOT = Path(__file__).resolve().parents[3]
ART = REPO_ROOT / "research" / "post" / "artifacts"

# Survival gates, stated BEFORE looking at results. Aligned with
# qhf.reports.scorecard.Thresholds where they apply, with a stricter trade
# floor because this is a 21.6-year in-sample sweep and low-n configs are noise.
GATES = {
    "n_trades_min": 100,
    "profit_factor_min": 1.20,
    "max_dd_max": 0.30,
    "sharpe_min": 0.0,
}

KEY = ["timeframe", "atr_period", "atr_mult", "bias_tf", "zlsma_len",
       "direction", "min_atr"]
SHOW = KEY + ["n_trades", "sharpe_px", "max_dd_px", "profit_factor_px",
              "win_rate", "sharpe_acct", "total_return_acct", "cagr_acct"]


def load_all() -> pd.DataFrame:
    frames = [pd.read_csv(p) for p in sorted(ART.glob("zlch_sweep_*.csv"))]
    if not frames:
        raise SystemExit("no sweep CSVs found -- run run_sweep first")
    return pd.concat(frames, ignore_index=True)


def apply_gates(df: pd.DataFrame) -> pd.DataFrame:
    return df[
        (df.n_trades >= GATES["n_trades_min"])
        & (df.profit_factor_px >= GATES["profit_factor_min"])
        & (df.max_dd_px <= GATES["max_dd_max"])
        & (df.sharpe_px > GATES["sharpe_min"])
    ].copy()


def rerun_returns(row: pd.Series) -> dict:
    """Re-simulate one config to recover its per-trade return streams."""
    df = load(row.timeframe)
    bars = E.Bars(df)
    d = E.chandelier_direction(bars.high_s, bars.low_s, bars.close_s,
                               int(row.atr_period), float(row.atr_mult))
    a = E.wilder_atr(bars.high_s, bars.low_s, bars.close_s, int(row.atr_period))
    if row.bias_tf == "none":
        rise = fall = np.ones(len(df), dtype=bool)
    else:
        rise, fall = E.htf_bias(bars.close_s, df.index,
                                RESAMPLE_RULE[row.bias_tf], int(row.zlsma_len))
    return E.simulate(bars, d, a, rise, fall,
                      row.direction in ("both", "long"),
                      row.direction in ("both", "short"),
                      float(row.atr_mult), 0.01, float(row.min_atr),
                      max_dd_halt=1.0)


def neighbourhood(df: pd.DataFrame, row: pd.Series) -> pd.DataFrame:
    """Configs identical to `row` except adjacent atr_period / atr_mult."""
    periods = sorted(df.atr_period.unique())
    mults = sorted(df.atr_mult.unique())
    pi, mi = periods.index(row.atr_period), mults.index(row.atr_mult)
    p_nb = periods[max(0, pi - 1): pi + 2]
    m_nb = mults[max(0, mi - 1): mi + 2]
    return df[
        (df.timeframe == row.timeframe) & (df.bias_tf == row.bias_tf)
        & (df.zlsma_len == row.zlsma_len) & (df.direction == row.direction)
        & (df.min_atr == row.min_atr)
        & df.atr_period.isin(p_nb) & df.atr_mult.isin(m_nb)
    ].copy()


def main() -> int:
    df = load_all()
    n_total = len(df)
    surv = apply_gates(df)

    print(f"SWEEP: {n_total:,} configs across {df.timeframe.nunique()} timeframes")
    print(f"GATES: n_trades>={GATES['n_trades_min']}, "
          f"PF>={GATES['profit_factor_min']}, DD<={GATES['max_dd_max']:.0%}, "
          f"Sharpe>{GATES['sharpe_min']}")
    print(f"SURVIVORS: {len(surv):,} ({100*len(surv)/n_total:.2f}%)\n")

    print("-- configs per timeframe / survivors --")
    tab = df.groupby("timeframe").agg(
        configs=("sharpe_px", "size"),
        median_sharpe=("sharpe_px", "median"),
        best_sharpe=("sharpe_px", "max"),
        pct_positive=("sharpe_px", lambda s: 100.0 * (s > 0).mean()),
    )
    tab["survivors"] = surv.groupby("timeframe").size().reindex(tab.index).fillna(0).astype(int)
    print(tab.round(3).to_string(), "\n")

    if surv.empty:
        print("Nothing survived the gates.")
        return 0

    for metric, asc, label in [
        ("sharpe_px", False, "SHARPE (harness basis)"),
        ("max_dd_px", True, "DRAWDOWN (lowest)"),
        ("win_rate", False, "WIN RATE"),
        ("profit_factor_px", False, "PROFIT FACTOR"),
    ]:
        print(f"-- top 10 survivors by {label} --")
        print(surv.sort_values(metric, ascending=asc).head(10)[SHOW]
              .round(4).to_string(index=False), "\n")

    # ---- leader robustness + DSR -------------------------------------------
    best = surv.sort_values("sharpe_px", ascending=False).iloc[0]
    print("=" * 78)
    print("LEADER BY SHARPE:", {k: best[k] for k in KEY})
    nb = neighbourhood(df, best)
    print(f"\nneighbourhood (adjacent atr_period x atr_mult): {len(nb)} configs")
    print(nb.sort_values(["atr_period", "atr_mult"])[
        ["atr_period", "atr_mult", "n_trades", "sharpe_px",
         "profit_factor_px", "max_dd_px"]].round(4).to_string(index=False))
    print(f"\nneighbourhood sharpe: median={nb.sharpe_px.median():.3f} "
          f"min={nb.sharpe_px.min():.3f} max={nb.sharpe_px.max():.3f} "
          f"| fraction>0: {(nb.sharpe_px > 0).mean():.0%}")

    sim = rerun_returns(best)
    r = sim["px_returns"]
    ppy = int(round(best.trades_per_year))
    trial_sh = df.sharpe_px.dropna()
    trial_sh_perobs = (trial_sh / np.sqrt(ppy)).to_numpy()
    res = deflated_sharpe_ratio(r, n_trials=n_total,
                                trial_sharpes=trial_sh_perobs,
                                periods_per_year=ppy)
    print(f"\nDSR at N={n_total:,} (empirical Var(SR) from the sweep's own "
          f"{len(trial_sh):,} trial Sharpes)")
    print(f"  sr_per_obs={res.sr_hat_per_obs:.5f}  sr_annualised={res.sr_hat_annualised:.3f}")
    print(f"  sr_star   ={res.sr_star:.5f}  var_sr={res.var_sr:.3e} ({res.var_sr_source})")
    print(f"  DSR       ={res.dsr:.4f}   PSR_vs_zero={res.psr_vs_zero:.4f}")
    print(f"  passes(>{res.threshold})  = {res.passes}")

    payload = {
        "n_configs": int(n_total),
        "gates": GATES,
        "n_survivors": int(len(surv)),
        "per_timeframe": json.loads(tab.to_json(orient="index")),
        "leader": {k: (best[k].item() if hasattr(best[k], "item") else best[k])
                   for k in SHOW},
        "leader_neighbourhood_sharpe": {
            "median": float(nb.sharpe_px.median()),
            "min": float(nb.sharpe_px.min()),
            "max": float(nb.sharpe_px.max()),
            "frac_positive": float((nb.sharpe_px > 0).mean()),
        },
        "dsr": {"dsr": res.dsr, "sr_star": res.sr_star,
                "sr_hat_per_obs": res.sr_hat_per_obs,
                "sr_hat_annualised": res.sr_hat_annualised,
                "n_trials": res.n_trials, "var_sr": res.var_sr,
                "var_sr_source": res.var_sr_source, "passes": res.passes},
    }
    (ART / "zlch_sweep_summary.json").write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {ART / 'zlch_sweep_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
