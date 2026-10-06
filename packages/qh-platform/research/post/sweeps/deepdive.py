"""research.post.sweeps.deepdive — controls + exposure for the sweep's leading configs.

For the top-K survivors on each timeframe, runs the drift control from
research.post.sweeps.control and adds the context an in-sample ranking cannot
provide on its own:

  exposure     fraction of calendar time actually in the market. A strategy
               matching buy-and-hold's Calmar on 40% exposure is a different
               proposition from one that needs 100%.
  calmar       CAGR / max drawdown, computed on the account basis.
  vs_bh        the same ratio for passive long gold over the identical window.
  p_value      P(random-entry Sharpe >= actual) with the exit rule, cost model,
               direction and trade count all held fixed.

Usage:  python -m research.post.sweeps.deepdive --top 5 --perm 1000
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.post.sweeps import zlch_engine as E
from research.post.sweeps.analyze import GATES, apply_gates, load_all
from research.post.sweeps.control import buy_and_hold, matched_random_control
from research.post.sweeps.data import RESAMPLE_RULE, load

REPO_ROOT = Path(__file__).resolve().parents[3]
ART = REPO_ROOT / "research" / "post" / "artifacts"


def _build(row: pd.Series):
    df = load(row["timeframe"])
    bars = E.Bars(df)
    d = E.chandelier_direction(bars.high_s, bars.low_s, bars.close_s,
                               int(row["atr_period"]), float(row["atr_mult"]))
    a = E.wilder_atr(bars.high_s, bars.low_s, bars.close_s, int(row["atr_period"]))
    if row["bias_tf"] == "none":
        rise = fall = np.ones(len(df), dtype=bool)
    else:
        rise, fall = E.htf_bias(bars.close_s, df.index,
                                RESAMPLE_RULE[row["bias_tf"]], int(row["zlsma_len"]))
    sim = E.simulate(bars, d, a, rise, fall,
                     row["direction"] in ("both", "long"),
                     row["direction"] in ("both", "short"),
                     float(row["atr_mult"]), 0.01, float(row["min_atr"]),
                     max_dd_halt=1.0)
    return df, bars, d, a, sim


def exposure(df: pd.DataFrame, sim: dict) -> float:
    if not sim["entry_ts"]:
        return 0.0
    held = sum((x - e).total_seconds()
               for e, x in zip(sim["entry_ts"], sim["exit_ts"]))
    span = (df.index[-1] - df.index[0]).total_seconds()
    return float(held / span) if span > 0 else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--perm", type=int, default=1000)
    args = ap.parse_args()

    allc = load_all()
    surv = apply_gates(allc)
    # min_atr is degenerate on timeframes whose ATR never drops below the
    # filter, producing exact duplicate rows. Count distinct strategies.
    dedup_cols = ["timeframe", "atr_period", "atr_mult", "bias_tf",
                  "zlsma_len", "direction", "n_trades", "sharpe_px"]
    n_distinct = len(allc.drop_duplicates(subset=dedup_cols))
    print(f"configs {len(allc):,} | distinct {n_distinct:,} | "
          f"survivors {len(surv):,}\n")

    rows = []
    for tf, grp in surv.groupby("timeframe"):
        picks = (grp.drop_duplicates(subset=dedup_cols)
                    .sort_values("sharpe_px", ascending=False).head(args.top))
        for _, row in picks.iterrows():
            df, bars, d, a, sim = _build(row)
            m = E.metrics(sim, basis="price")
            mac = E.metrics(sim, basis="account")
            direc = row["direction"]
            is_long = None if direc == "both" else direc == "long"
            pool = np.flatnonzero(
                np.isfinite(a) & (np.nan_to_num(a, nan=-1.0) >= float(row["min_atr"])))
            pool = pool[(pool > 0) & (pool < bars.n - 2)]

            def run_masked(lm, sm, _b=bars, _d=d, _a=a, _r=row):
                return E.simulate(_b, _d, _a, np.ones(_b.n, bool), np.ones(_b.n, bool),
                                  True, True, float(_r["atr_mult"]), 0.01,
                                  float(_r["min_atr"]), max_dd_halt=1.0,
                                  entry_override=(lm, sm))

            ctrl = matched_random_control(run_masked, pool, m["n_trades"], bars.n,
                                          is_long=is_long, ppy=m["trades_per_year"],
                                          n_perm=args.perm)
            sh = ctrl["sharpes"]
            p = float(np.nanmean(sh >= m["sharpe"]))
            bh = buy_and_hold(df)
            exp = exposure(df, sim)
            calmar = mac["cagr"] / mac["max_dd"] if mac["max_dd"] > 0 else np.nan
            rows.append({
                "timeframe": tf, "atr_period": int(row["atr_period"]),
                "atr_mult": float(row["atr_mult"]), "bias_tf": row["bias_tf"],
                "zlsma_len": int(row["zlsma_len"]), "direction": row["direction"],
                "n_trades": m["n_trades"], "sharpe_px": m["sharpe"],
                "profit_factor": m["profit_factor"], "win_rate": m["win_rate"],
                "max_dd_px": m["max_dd"], "cagr_acct": mac["cagr"],
                "max_dd_acct": mac["max_dd"], "calmar": calmar,
                "exposure": exp,
                "null_mean": ctrl["null_mean"], "null_p95": ctrl["null_p95"],
                "p_value": p, "null_median_realized": ctrl["median_realized"],
                "null_target": ctrl["target"],
                "bh_sharpe": bh["sharpe"], "bh_cagr": bh["cagr"],
                "bh_max_dd": bh["max_dd"],
                "bh_calmar": bh["cagr"] / bh["max_dd"],
            })
            print(f"  {tf} p{row['atr_period']} m{row['atr_mult']} "
                  f"{row['bias_tf']}/{row['zlsma_len']} {row['direction']}: "
                  f"SR={m['sharpe']:.3f} null={ctrl['null_mean']:.3f} "
                  f"p={p:.4f} exp={exp:.1%} calmar={calmar:.2f} "
                  f"(B&H {bh['cagr']/bh['max_dd']:.2f})", flush=True)

    out = pd.DataFrame(rows)
    out.to_csv(ART / "zlch_deepdive.csv", index=False)
    (ART / "zlch_deepdive_meta.json").write_text(json.dumps({
        "n_configs": int(len(allc)), "n_distinct": int(n_distinct),
        "n_survivors": int(len(surv)), "gates": GATES,
        "n_permutations": args.perm, "top_per_tf": args.top,
    }, indent=2))
    print(f"\nwrote {ART/'zlch_deepdive.csv'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
