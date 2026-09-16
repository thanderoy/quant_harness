"""research.post.sweeps.ebb_analyze — gates, rankings, drift controls and DSR for ebb_n_flow.

Writes research/data/ebb_n_flow/ebb_report_data.json, which build_ebb_report.py renders.

Gates are deliberately IDENTICAL to those used for the zerolag_chandelier sweep
(research.post.sweeps.analyze.GATES) so the two hypotheses are comparable and the
threshold cannot be accused of being tuned to this data set.

Usage:  python -m research.post.sweeps.ebb_analyze --top 3 --perm 500
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.post.dsr import deflated_sharpe_ratio

#: Economic benchmark for these historical XAUUSD runs, per observation.
#: These analyses were produced before T8, against an implicit SR* of 0. The
#: zero is kept here so the numbers still reproduce, but it is now written
#: down instead of implied: D5 puts XAUUSD buy-and-hold at 0.6343 annualised
#: (0.039959 per observation) over 2013-2026, so every DSR below is lenient
#: by roughly that much. See research log seq=94.
LEGACY_BENCHMARK_SHARPE = 0.0

from research.post.sweeps import ebb_engine as E
from research.post.sweeps.analyze import GATES
from research.post.sweeps.control import buy_and_hold, matched_random_control
from research.post.sweeps.data import load
from research.post.sweeps.zlch_engine import metrics

REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_DIR = REPO_ROOT / "research" / "data" / "ebb_n_flow"
TF_ORDER = ["M5", "M15", "H1", "H4", "D1"]
N_PERM = 500
SEED = 20260820

ER_N, ATR_N, ATR_FLOOR, ATR_SPIKE, MIN_R = 10, 14, 1.0, 2.5, 0.5
KEY = ["timeframe", "bb_n", "bb_k", "er_max", "sl_atr_mult",
       "time_stop_bars", "direction", "session"]


def load_all() -> pd.DataFrame:
    frames = [pd.read_csv(p) for p in sorted(DATA_DIR.glob("ebb_sweep_*.csv"))]
    if not frames:
        raise SystemExit("no ebb sweep CSVs found -- run run_ebb_sweep first")
    d = pd.concat(frames, ignore_index=True)
    d["timeframe"] = pd.Categorical(d.timeframe, TF_ORDER, ordered=True)
    return d


def apply_gates(d: pd.DataFrame) -> pd.DataFrame:
    return d[(d.n_trades >= GATES["n_trades_min"])
             & (d.profit_factor_px >= GATES["profit_factor_min"])
             & (d.max_dd_px <= GATES["max_dd_max"])
             & (d.sharpe_px > GATES["sharpe_min"])].copy()


def _sim(row, bars, override=None):
    mid, up, lo, er, atr = E.build_indicators(bars, int(row["bb_n"]),
                                              float(row["bb_k"]), ER_N, ATR_N)
    return E.simulate(bars, mid, up, lo, er, atr,
                      er_max=float(row["er_max"]),
                      sl_atr_mult=float(row["sl_atr_mult"]),
                      atr_floor=ATR_FLOOR,
                      time_stop_bars=int(row["time_stop_bars"]),
                      atr_spike_mult=ATR_SPIKE, min_r=MIN_R,
                      enable_long=row["direction"] in ("both", "long"),
                      enable_short=row["direction"] in ("both", "short"),
                      use_session=row["session"] == "rth",
                      entry_override=override)


def _gate_pool(row, bars) -> np.ndarray:
    mid, up, lo, er, atr = E.build_indicators(bars, int(row["bb_n"]),
                                              float(row["bb_k"]), ER_N, ATR_N)
    return E.simulate(bars, mid, up, lo, er, atr,
                      er_max=float(row["er_max"]),
                      sl_atr_mult=float(row["sl_atr_mult"]),
                      atr_floor=ATR_FLOOR,
                      time_stop_bars=int(row["time_stop_bars"]),
                      atr_spike_mult=ATR_SPIKE, min_r=MIN_R,
                      enable_long=True, enable_short=True,
                      use_session=row["session"] == "rth", return_gate=True)


def _feasible(row, bars, is_long: bool) -> np.ndarray:
    """Gated bars where the R-floor is satisfiable for this direction.

    A random bar is only a fair counterfactual if the strategy could actually
    have traded it. The R-floor (reward-to-midline / ATR-stop >= min_r) rejects
    the overwhelming majority of random bars, so drawing from the raw gated pool
    yields a handful of trades and a meaningless Sharpe. The null must be drawn
    from the feasible set, leaving the Bollinger band-touch test as the ONLY
    thing removed.
    """
    mid, up, lo, er, atr = E.build_indicators(bars, int(row["bb_n"]),
                                              float(row["bb_k"]), ER_N, ATR_N)
    gate = E.simulate(bars, mid, up, lo, er, atr, er_max=float(row["er_max"]),
                      sl_atr_mult=float(row["sl_atr_mult"]), atr_floor=ATR_FLOOR,
                      time_stop_bars=int(row["time_stop_bars"]),
                      atr_spike_mult=ATR_SPIKE, min_r=MIN_R,
                      enable_long=True, enable_short=True,
                      use_session=row["session"] == "rth", return_gate=True)
    sl_dist = float(row["sl_atr_mult"]) * np.maximum(atr, ATR_FLOOR)
    tp_dist = (mid - bars.close) if is_long else (bars.close - mid)
    with np.errstate(invalid="ignore"):
        rfloor = (tp_dist > 0) & (sl_dist > 0) & (tp_dist / sl_dist >= MIN_R)
    return gate & np.nan_to_num(rfloor, nan=False).astype(bool)


def control(row, bars, n_entries: int, ppy: float, n_perm: int = N_PERM) -> dict:
    """Count-matched random-entry null over the feasible, regime-gated pool."""
    is_long = None if row["direction"] == "both" else row["direction"] == "long"
    if is_long is None:
        pool_mask = _feasible(row, bars, True) | _feasible(row, bars, False)
    else:
        pool_mask = _feasible(row, bars, is_long)
    pool = np.flatnonzero(pool_mask)
    pool = pool[(pool > 0) & (pool < bars.n - 2)]
    if pool.size < 10:
        return {"null_mean": float("nan"), "null_p95": float("nan"),
                "sharpes": np.full(n_perm, np.nan), "pool_size": int(pool.size),
                "median_realized": 0, "n_valid": 0, "target": int(n_entries)}

    def run_masked(long_mask, short_mask):
        return _sim(row, bars, (long_mask, short_mask))

    return matched_random_control(run_masked, pool, n_entries, bars.n,
                                  is_long=is_long, ppy=ppy, n_perm=n_perm, seed=SEED)


def exposure(df, sim) -> float:
    if not sim["entry_ts"]:
        return 0.0
    held = sum((x - e).total_seconds() for e, x in zip(sim["entry_ts"], sim["exit_ts"]))
    span = (df.index[-1] - df.index[0]).total_seconds()
    return float(held / span) if span > 0 else 0.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=3)
    ap.add_argument("--perm", type=int, default=N_PERM)
    args = ap.parse_args()

    d = load_all()
    # A wide band on a slow timeframe can yield a handful of trades whose Sharpe
    # is arithmetically huge and financially meaningless (e.g. 2 trades, PF=inf).
    # Every "best" statistic is therefore computed over configs meeting the trade
    # floor; the full frame is kept for medians, which are unaffected.
    d_countable = d[d.n_trades >= GATES["n_trades_min"]]
    surv = apply_gates(d)
    dedup = KEY + ["n_trades", "sharpe_px"]

    tf_tab = d.groupby("timeframe", observed=True).agg(
        configs=("sharpe_px", "size"), median_sharpe=("sharpe_px", "median"),
        pct_positive=("sharpe_px", lambda s: 100.0 * (s > 0).mean()),
        median_trades_yr=("trades_per_year", "median"),
        median_pf=("profit_factor_px", "median"),
        median_wr=("win_rate", "median"))
    tf_tab["best_sharpe"] = (d_countable.groupby("timeframe", observed=True)
                             .sharpe_px.max().reindex(tf_tab.index))
    tf_tab["n_countable"] = (d_countable.groupby("timeframe", observed=True)
                             .size().reindex(tf_tab.index).fillna(0).astype(int))
    tf_tab["survivors"] = (surv.groupby("timeframe", observed=True).size()
                           .reindex(tf_tab.index).fillna(0).astype(int))

    out = {
        "n_configs": int(len(d)), "n_survivors": int(len(surv)), "gates": GATES,
        "per_timeframe": json.loads(tf_tab.round(4).to_json(orient="index")),
        "direction_median": json.loads(
            d.pivot_table(index="timeframe", columns="direction",
                          values="sharpe_px", aggfunc="median", observed=True)
            .round(3).to_json(orient="index")),
        "direction_pctpos": json.loads(
            d.pivot_table(index="timeframe", columns="direction", values="sharpe_px",
                          aggfunc=lambda s: 100.0 * (s > 0).mean(), observed=True)
            .round(1).to_json(orient="index")),
        "ermax_median_long": json.loads(
            d[d.direction == "long"].pivot_table(
                index="timeframe", columns="er_max", values="sharpe_px",
                aggfunc="median", observed=True).round(3).to_json(orient="index")),
        "session_median_long": json.loads(
            d[d.direction == "long"].pivot_table(
                index="timeframe", columns="session", values="sharpe_px",
                aggfunc="median", observed=True).round(3).to_json(orient="index")),
        "slmult_median_long": json.loads(
            d[d.direction == "long"].pivot_table(
                index="timeframe", columns="sl_atr_mult", values="sharpe_px",
                aggfunc="median", observed=True).round(3).to_json(orient="index")),
        "timestop_median_long": json.loads(
            d[d.direction == "long"].pivot_table(
                index="timeframe", columns="time_stop_bars", values="sharpe_px",
                aggfunc="median", observed=True).round(3).to_json(orient="index")),
        "bbk_median_long": json.loads(
            d[d.direction == "long"].pivot_table(
                index="timeframe", columns="bb_k", values="sharpe_px",
                aggfunc="median", observed=True).round(3).to_json(orient="index")),
    }

    cols = KEY + ["n_trades", "sharpe_px", "max_dd_px", "profit_factor_px",
                  "win_rate", "cagr_acct"]
    for name, metric, asc in [("by_sharpe", "sharpe_px", False),
                              ("by_drawdown", "max_dd_px", True),
                              ("by_win_rate", "win_rate", False),
                              ("by_profit_factor", "profit_factor_px", False)]:
        out[name] = json.loads(surv.drop_duplicates(subset=dedup)
                               .sort_values(metric, ascending=asc)
                               .head(10)[cols].round(4).to_json(orient="records"))
    out["best_per_tf"] = json.loads(
        d_countable.loc[d_countable.groupby("timeframe", observed=True)
                        .sharpe_px.idxmax()][cols].round(4).to_json(orient="records"))
    out["n_countable"] = int(len(d_countable))

    # registered defaults, as killed at seq=10
    orig = d[(d.bb_n == 20) & (d.bb_k == 2.0) & (d.er_max == 0.30)
             & (d.sl_atr_mult == 1.0) & (d.time_stop_bars == 8)
             & (d.session == "rth")]
    out["registered_config"] = json.loads(
        orig.sort_values(["timeframe", "direction"])[cols]
        .round(4).to_json(orient="records"))

    # ---- controls on the leaders --------------------------------------------
    print(f"configs {len(d):,} | survivors {len(surv):,}\n", flush=True)
    dd_rows = []
    for tf, grp in surv.groupby("timeframe", observed=True):
        picks = (grp.drop_duplicates(subset=dedup)
                    .sort_values("sharpe_px", ascending=False).head(args.top))
        if picks.empty:
            continue
        df_tf = load(tf)
        bars = E.EbbBars(df_tf)
        bh = buy_and_hold(df_tf)
        for _, row in picks.iterrows():
            sim = _sim(row, bars)
            mpx = metrics(sim, basis="price")
            mac = metrics(sim, basis="account")
            c = control(row, bars, mpx["n_trades"], mpx["trades_per_year"], n_perm=args.perm)
            p = float(np.nanmean(c["sharpes"] >= mpx["sharpe"]))
            exp = exposure(df_tf, sim)
            calmar = mac["cagr"] / mac["max_dd"] if mac["max_dd"] > 0 else np.nan
            dd_rows.append({
                **{k: row[k] for k in KEY},
                "n_trades": mpx["n_trades"], "sharpe_px": mpx["sharpe"],
                "profit_factor": mpx["profit_factor"], "win_rate": mpx["win_rate"],
                "max_dd_px": mpx["max_dd"], "cagr_acct": mac["cagr"],
                "calmar": calmar, "exposure": exp,
                "null_mean": c["null_mean"], "null_p95": c["null_p95"],
                "p_value": p, "pool_size": c["pool_size"],
                "null_median_realized": c["median_realized"],
                "null_n_valid": c["n_valid"],
                "bh_calmar": bh["cagr"] / bh["max_dd"], "bh_sharpe": bh["sharpe"],
            })
            print(f"  {tf} bb{row["bb_n"]}/{row['bb_k']} er{row['er_max']} "
                  f"sl{row['sl_atr_mult']} ts{row['time_stop_bars']} "
                  f"{row['direction']}/{row['session']}: SR={mpx['sharpe']:.3f} "
                  f"null={c['null_mean']:.3f} p={p:.4f} exp={exp:.1%} "
                  f"calmar={calmar:.2f} (B&H {bh['cagr']/bh['max_dd']:.2f})",
                  flush=True)
    out["deepdive"] = dd_rows
    if dd_rows:
        pd.DataFrame(dd_rows).to_csv(DATA_DIR / "ebb_deepdive.csv", index=False)

        best = surv.sort_values("sharpe_px", ascending=False).iloc[0]
        bars = E.EbbBars(load(best["timeframe"]))
        best_sim = _sim(best, bars)
        r = best_sim["px_returns"]
        # Per-trade returns for the leader, mirroring the convention in
        # research/data/asqs/ and research/data/crest_n_keel/ so the DSR can be
        # recomputed independently of this module.
        pd.DataFrame({
            "entry_time": best_sim["entry_ts"], "exit_time": best_sim["exit_ts"],
            "direction": np.where(best_sim["dirs"] == 1, "long", "short"),
            "pnl_usd": best_sim["pnls"],
            "return_px": best_sim["px_returns"],
            "return_acct": best_sim["returns"],
        }).to_csv(DATA_DIR / "ebb_leader_returns.csv", index=False)
        ppy = max(int(round(best["trades_per_year"])), 1)
        n_tf = int((d.timeframe == best["timeframe"]).sum())
        sh_tf = (d[d.timeframe == best["timeframe"]].sharpe_px.dropna()
                 / np.sqrt(ppy)).to_numpy()
        variants = [
            ("estimated SE / N=%d (full grid)" % len(d), dict(n_trials=len(d))),
            ("estimated SE / N=%d (%s grid)" % (n_tf, best["timeframe"]),
             dict(n_trials=n_tf)),
            ("empirical Var(SR), %s pool / N=%d" % (best["timeframe"], n_tf),
             dict(n_trials=n_tf, trial_sharpes=sh_tf)),
            ("estimated SE / N=16 (research log floor)", dict(n_trials=16)),
        ]
        out["dsr_variants"] = []
        for label, kw in variants:
            res = deflated_sharpe_ratio(
                r, periods_per_year=ppy,
                benchmark_sharpe=LEGACY_BENCHMARK_SHARPE, **kw)
            out["dsr_variants"].append({
                "label": label, "n_trials": res.n_trials, "var_sr": res.var_sr,
                "var_sr_source": res.var_sr_source, "sr_star": res.sr_star,
                "dsr": res.dsr, "passes": bool(res.passes),
                "sr_hat_per_obs": res.sr_hat_per_obs,
                "sr_hat_annualised": res.sr_hat_annualised})
        out["leader"] = {k: (best[k].item() if hasattr(best[k], "item") else best[k])
                         for k in cols}

    def _clean(o):
        if isinstance(o, float):
            return None if (np.isinf(o) or np.isnan(o)) else o
        if isinstance(o, dict):
            return {k: _clean(v) for k, v in o.items()}
        if isinstance(o, list):
            return [_clean(v) for v in o]
        return o

    (DATA_DIR / "ebb_report_data.json").write_text(
        json.dumps(_clean(out), indent=2, default=str))
    print(f"\nwrote {DATA_DIR/'ebb_report_data.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
