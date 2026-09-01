"""research.post.sweeps.cnk_analyze — rank crest_n_keel sweep survivors.

Produces the executive-report data set:
  * survival gates applied to every swept config (thresholds frozen BEFORE
    the sweep ran, and identical to the zlch and ebb sweeps so the three are
    directly comparable)
  * rankings by Sharpe, drawdown, win rate and profit factor
  * K1 random-entry control with the REALIZED trade count matched
  * K2 buy-and-hold Calmar comparison
  * K3 Deflated Sharpe across a range of honest N
  * K4 neighbourhood robustness (plateau or isolated spike?)
  * PULLBACK vs MOMENTUM surface comparison -- the question seq=35/36 raised
    but never answered at grid scale

Usage:  python -m research.post.sweeps.cnk_analyze
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.post.dsr import deflated_sharpe_ratio
from research.post.sweeps import cnk_engine as E
from research.post.sweeps.analyze import GATES
from research.post.sweeps.control import (buy_and_hold, matched_random_control,
                                          N_PERMUTATIONS)
from research.post.sweeps.data import load
from research.post.sweeps.run_cnk_sweep import (HMA_PERIODS, ATR_PERIODS, MIN_ATRS,
                                                SL_MULTS, TP_MULTS, TRAIL_MULTS,
                                                STOCH_KS, STOCH_D, STOCH_SMOOTH,
                                                RISK_PCT, OUT_DIR)

KEY = ["timeframe", "mode", "hma_period", "atr_period", "stoch_k", "oversold",
       "overbought", "sl_mult", "tp_mult", "trail_mult", "direction", "min_atr"]
SHOW = KEY + ["n_trades", "sharpe_px", "max_dd_px", "profit_factor_px",
              "win_rate", "sharpe_acct", "total_return_acct", "cagr_acct"]

# Ordered dimensions for the neighbourhood test (one step in one dimension).
NEIGHBOUR_DIMS = {
    "hma_period": HMA_PERIODS, "atr_period": ATR_PERIODS, "min_atr": MIN_ATRS,
    "sl_mult": SL_MULTS, "tp_mult": TP_MULTS, "trail_mult": TRAIL_MULTS,
    "stoch_k": STOCH_KS,
}
_bars_cache: dict = {}


def _clean(o):
    """JSON-safe: inf/nan -> None."""
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        f = float(o)
        return None if (np.isnan(f) or np.isinf(f)) else f
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def load_all(dedup: bool = True) -> pd.DataFrame:
    """Load every per-timeframe sweep CSV.

    `min_atr` is a DEGENERATE dimension wherever the timeframe's ATR sits above
    every tested floor -- on D1 it never binds at all, so each configuration is
    stored three times with identical metrics. Left in, those duplicates pad the
    ranking tables with the same config repeated and inflate the grid size N that
    feeds the Deflated Sharpe haircut. The N inflation is conservative (a larger
    N only makes the haircut harsher), but a padded number is still a wrong
    number, so the default is to collapse them and report both counts.

    Collapsing keeps the SMALLEST min_atr of each identical group, i.e. the
    config that does not rely on a filter which never fired.
    """
    frames = [pd.read_csv(p) for p in sorted(OUT_DIR.glob("cnk_sweep_*.csv"))]
    if not frames:
        raise SystemExit("no sweep CSVs found -- run run_cnk_sweep first")
    df = pd.concat(frames, ignore_index=True)
    if not dedup:
        return df
    key = [c for c in df.columns if c != "min_atr"]
    return (df.sort_values("min_atr")
              .drop_duplicates(subset=key, keep="first")
              .reset_index(drop=True))


def apply_gates(df: pd.DataFrame) -> pd.DataFrame:
    return df[
        (df.n_trades >= GATES["n_trades_min"])
        & (df.profit_factor_px >= GATES["profit_factor_min"])
        & (df.max_dd_px <= GATES["max_dd_max"])
        & (df.sharpe_px > GATES["sharpe_min"])
    ].copy()


def _bars(tf: str):
    if tf not in _bars_cache:
        df = load(tf)
        _bars_cache[tf] = (df, E.Bars(df))
    return _bars_cache[tf]


def _signals(row: pd.Series):
    df, bars = _bars(row["timeframe"])
    hma_v = E.hma(bars.close, int(row["hma_period"]))
    atr_v = E.atr(bars.high, bars.low, bars.close, int(row["atr_period"]))
    if row["mode"] == "pullback":
        k, d = E.stochastic(bars.high, bars.low, bars.close,
                            int(row["stoch_k"]), STOCH_D, STOCH_SMOOTH)
        lo_s, sh_s = E.pullback_signals(bars, hma_v, k, d,
                                        float(row["oversold"]), float(row["overbought"]))
    else:
        lo_s, sh_s = E.momentum_signals(bars, hma_v)
    return df, bars, hma_v, atr_v, lo_s, sh_s


def rerun(row: pd.Series, override=None) -> dict:
    """Re-simulate one config, optionally with overridden entry masks."""
    df, bars, hma_v, atr_v, lo_s, sh_s = _signals(row)
    if override is not None:
        lo_s, sh_s = override
    direc = row["direction"]
    return E.simulate(
        bars, row["mode"], hma_v, atr_v, lo_s, sh_s,
        enable_long=direc in ("both", "long"), enable_short=direc in ("both", "short"),
        sl_mult=float(row["sl_mult"]), tp_mult=float(row["tp_mult"]),
        trail_mult=float(row["trail_mult"]), risk_pct=RISK_PCT,
        min_atr=float(row["min_atr"]), max_dd_halt=1.0)


def control_for(row: pd.Series, n_perm: int = N_PERMUTATIONS) -> dict:
    """K1: does this config beat a random entry drawn from its own eligible pool?"""
    df, bars, hma_v, atr_v, lo_s, sh_s = _signals(row)
    sim = rerun(row)
    if sim["n_trades"] < 2:
        return {"skipped": "fewer than 2 trades"}
    m = E.metrics(sim, basis="price")

    # Eligible pool = every bar the strategy could legally have entered on:
    # indicators warm and the ATR floor satisfied. Nothing about the HMA or
    # stochastic gate, so the comparison isolates ENTRY TIMING alone.
    ok = (np.isfinite(hma_v) & np.isfinite(atr_v)
          & (np.nan_to_num(atr_v, nan=-1.0) >= float(row["min_atr"])))
    pool = np.flatnonzero(ok)
    direc = row["direction"]
    is_long = None if direc == "both" else (direc == "long")

    def run_masked(lm, sm):
        return rerun(row, override=(lm, sm))

    ctrl = matched_random_control(run_masked, pool, sim["n_trades"], bars.n,
                                  is_long=is_long, ppy=m["trades_per_year"],
                                  n_perm=n_perm)
    s = ctrl["sharpes"]
    s = s[~np.isnan(s)]
    p = float((s >= m["sharpe"]).sum() / s.size) if s.size else float("nan")
    return {"actual_sharpe": m["sharpe"], "null_mean": ctrl["null_mean"],
            "null_p95": ctrl["null_p95"], "p_value": p,
            "n_valid": ctrl["n_valid"], "pool_size": ctrl["pool_size"],
            "target_trades": ctrl["target"],
            "median_realized": ctrl["median_realized"]}


def neighbours(row: pd.Series, df: pd.DataFrame) -> pd.DataFrame:
    """Configs one grid step away in exactly one dimension."""
    out = []
    for dim, grid in NEIGHBOUR_DIMS.items():
        if dim not in df.columns or row[dim] not in grid:
            continue
        i = grid.index(row[dim])
        for j in (i - 1, i + 1):
            if not (0 <= j < len(grid)):
                continue
            q = df
            for k in KEY:
                q = q[q[k] == (grid[j] if k == dim else row[k])]
            out.append(q)
    return pd.concat(out, ignore_index=True) if out else df.iloc[0:0]


def dsr_at(returns: np.ndarray, n_list, trial_sharpes=None) -> dict:
    res = {}
    for n in n_list:
        try:
            r = deflated_sharpe_ratio(returns, n_trials=int(n),
                                      trial_sharpes=trial_sharpes)
            res[str(n)] = {"dsr": float(r.dsr), "var_sr_source": r.var_sr_source}
        except Exception as exc:                       # noqa: BLE001
            res[str(n)] = {"error": str(exc)}
    return res


# --------------------------------------------------------------------------- #
# Report assembly                                                              #
# --------------------------------------------------------------------------- #
def _records(d: pd.DataFrame, n: int = 15) -> list[dict]:
    return _clean(d[SHOW].head(n).to_dict("records"))


def _surface(df: pd.DataFrame, by: list[str]) -> list[dict]:
    """Median / positive-rate of the parameter surface, sliced by `by`."""
    g = df.groupby(by, dropna=False)
    out = g.agg(n_configs=("sharpe_px", "size"),
                median_sharpe=("sharpe_px", "median"),
                pct_positive=("sharpe_px", lambda s: float((s > 0).mean() * 100)),
                median_trades=("n_trades", "median")).reset_index()
    return _clean(out.to_dict("records"))


def main() -> int:
    df_raw = load_all(dedup=False)
    df = load_all()
    # Every "best" statistic is computed over configs that clear the trade
    # floor. Without this the top of a grid this size is 2-trade noise with an
    # infinite profit factor -- the failure mode caught during the ebb sweep.
    countable = df[df.n_trades >= GATES["n_trades_min"]].copy()
    surv = apply_gates(df)

    report: dict = {
        "n_configs_total": int(len(df)),
        "n_configs_raw": int(len(df_raw)),
        "min_atr_degeneracy": _clean([
            {"timeframe": tf,
             "rows": int(len(g)),
             "distinct": int(len(g.drop_duplicates(
                 subset=[c for c in g.columns if c != "min_atr"])))}
            for tf, g in df_raw.groupby("timeframe")]),
        "n_countable": int(len(countable)),
        "n_survivors": int(len(surv)),
        "survival_rate_pct": float(100.0 * len(surv) / max(len(df), 1)),
        "gates": GATES,
        "risk_pct": RISK_PCT,
        "n_permutations": N_PERMUTATIONS,
        "by_timeframe": _surface(df, ["timeframe"]),
        "by_mode": _surface(df, ["mode"]),
        "by_tf_mode": _surface(df, ["timeframe", "mode"]),
        "by_mode_direction": _surface(df, ["mode", "direction"]),
        "by_tf_mode_direction": _surface(df, ["timeframe", "mode", "direction"]),
        "survivors_by_tf_mode": _clean(
            surv.groupby(["timeframe", "mode"]).size().reset_index(name="n")
            .to_dict("records")) if len(surv) else [],
    }

    # -- rankings (over countable configs only) ----------------------------- #
    report["rank_sharpe"] = _records(countable.sort_values("sharpe_px", ascending=False))
    report["rank_drawdown"] = _records(
        countable[countable.sharpe_px > 0].sort_values("max_dd_px"))
    report["rank_win_rate"] = _records(countable.sort_values("win_rate", ascending=False))
    report["rank_profit_factor"] = _records(
        countable[np.isfinite(countable.profit_factor_px)]
        .sort_values("profit_factor_px", ascending=False))

    if countable.empty:
        (OUT_DIR / "cnk_report_data.json").write_text(json.dumps(_clean(report), indent=2))
        print("no config clears the trade floor -- nothing further to test")
        return 0

    # -- leader + per-(tf,mode) leaders ------------------------------------- #
    leader = countable.sort_values("sharpe_px", ascending=False).iloc[0]
    report["leader"] = _clean(leader[SHOW].to_dict())

    tf_mode_leaders = (countable.sort_values("sharpe_px", ascending=False)
                       .groupby(["timeframe", "mode"]).head(1))
    report["tf_mode_leaders"] = _records(
        tf_mode_leaders.sort_values("sharpe_px", ascending=False), n=20)

    # -- K1 random-entry control ------------------------------------------- #
    controls = []
    for _, row in tf_mode_leaders.sort_values("sharpe_px", ascending=False).iterrows():
        c = control_for(row)
        c.update({k: _clean(row[k]) for k in
                  ["timeframe", "mode", "direction", "n_trades"]})
        controls.append(_clean(c))
        print(f"  K1 {row['timeframe']:>3} {row['mode']:<8} "
              f"actual={c.get('actual_sharpe', float('nan')):.3f} "
              f"null={c.get('null_mean', float('nan')):.3f} "
              f"p={c.get('p_value', float('nan')):.3f} "
              f"realized={c.get('median_realized', 0)}/{c.get('target_trades', 0)}",
              flush=True)
    report["k1_controls"] = controls

    # -- K2 buy and hold ---------------------------------------------------- #
    bh = {}
    for tf in sorted(df.timeframe.unique()):
        bh[tf] = _clean(buy_and_hold(load(tf)))
    report["buy_and_hold"] = bh
    beat = []
    for _, row in tf_mode_leaders.iterrows():
        b = bh[row["timeframe"]]
        cal = (row["cagr_acct"] / row["max_dd_acct"]
               if row["max_dd_acct"] and np.isfinite(row["max_dd_acct"]) and row["max_dd_acct"] > 0
               else float("nan"))
        # buy_and_hold() reports cagr and max_dd, not calmar -- derive it here.
        # Reading a "calmar" key straight off that dict silently yields None and
        # turns every K2 comparison into False, i.e. a fabricated kill.
        bh_cal = (b["cagr"] / b["max_dd"]
                  if b.get("max_dd") and b["max_dd"] > 0 else float("nan"))
        beat.append(_clean({"timeframe": row["timeframe"], "mode": row["mode"],
                            "direction": row["direction"], "calmar": cal,
                            "bh_calmar": bh_cal,
                            "beats_bh": bool(np.isfinite(cal) and np.isfinite(bh_cal)
                                             and cal > bh_cal)}))
    report["k2_calmar"] = beat
    report["k2_n_beating_bh"] = int(sum(1 for b in beat if b["beats_bh"]))

    # -- K3 deflated Sharpe -------------------------------------------------- #
    sim = rerun(leader)
    lead_r = sim["px_returns"]
    lead_r = lead_r[~np.isnan(lead_r)]
    # Empirical Var(SR) restricted to configs that clear the trade floor;
    # pooling across structurally heterogeneous timeframes would be a
    # misapplication of the estimator, so this is reported with its source.
    ts = countable["sharpe_px"].dropna()
    ts = ts[np.isfinite(ts)].to_numpy(float)
    try:
        from research.log import trial_count
        honest_n = int(trial_count())
    except Exception:                                   # noqa: BLE001
        honest_n = None
    n_list = [x for x in [1, honest_n, 20, len(countable), len(df)] if x]
    report["honest_trial_count"] = honest_n
    report["k3_dsr"] = dsr_at(lead_r, sorted(set(n_list)), trial_sharpes=ts)
    report["k3_dsr_single_sharpe_se"] = dsr_at(lead_r, sorted(set(n_list)))

    # -- K4 neighbourhood ---------------------------------------------------- #
    nb = neighbours(leader, df)
    nb_c = nb[nb.n_trades >= GATES["n_trades_min"]]
    report["k4_neighbourhood"] = _clean({
        "n_neighbours": int(len(nb)), "n_countable": int(len(nb_c)),
        "median_sharpe": float(nb_c.sharpe_px.median()) if len(nb_c) else None,
        "min_sharpe": float(nb_c.sharpe_px.min()) if len(nb_c) else None,
        "all_positive": bool((nb_c.sharpe_px > 0).all()) if len(nb_c) else False,
        "rows": _records(nb_c.sort_values("sharpe_px", ascending=False), n=20),
    })

    # -- artefacts ----------------------------------------------------------- #
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "cnk_report_data.json").write_text(json.dumps(_clean(report), indent=2))
    countable.sort_values("sharpe_px", ascending=False).head(500)[SHOW].to_csv(
        OUT_DIR / "cnk_deepdive.csv", index=False)
    pd.DataFrame({"entry_time": sim["entry_ts"], "exit_time": sim["exit_ts"],
                  "px_return": sim["px_returns"], "acct_return": sim["returns"],
                  "pnl_usd": sim["pnls"]}).to_csv(
        OUT_DIR / "cnk_leader_returns.csv", index=False)
    print(f"\nconfigs={len(df):,} countable={len(countable):,} survivors={len(surv):,} "
          f"({report['survival_rate_pct']:.2f}%)")
    print(f"leader: {report['leader']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
