"""research.post.sweeps.asqs_analyze — rank ASQS sweep survivors.

Same gates and controls as the zlch/ebb/cnk sweeps so the four are directly
comparable, plus one section unique to this strategy: a SESSION COMPARISON.
ASQS is the only swept strategy that filters by hour-of-day, so it is the only
one where the timezone defect changes results, and the size of that change is
the correction to the seq=30 record.

Read alongside seq=49: top-of-grid selection was shown to carry no information
out of sample, so the rankings here are a description of the parameter surface,
not a shortlist of promotable configurations.

Usage:  python -m research.post.sweeps.asqs_analyze
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from research.post.dsr import deflated_sharpe_ratio
from research.post.sweeps import asqs_engine as A
from research.post.sweeps.analyze import GATES
from research.post.sweeps.control import (buy_and_hold, matched_random_control,
                                          N_PERMUTATIONS)
from research.post.sweeps.data import load
from research.post.sweeps.run_asqs_sweep import (
    EMA_PAIRS, BREAKOUT_LOOKBACKS, TREND_STRENGTHS, BREAKOUT_BUFFERS,
    SL_POINTS, TP_POINTS, RSI_PERIOD, ATR_PERIOD, PARTIAL_MODE,
    SIM_FIXED, SESSION_FIXED, OUT_DIR)

KEY = ["timeframe", "ema_fast", "ema_slow", "breakout_lookback", "trend_strength",
       "breakout_buffer", "rsi_buy_min", "rsi_buy_max", "rsi_sell_min",
       "rsi_sell_max", "sl_points", "tp_points", "use_session", "session_start",
       "session_end", "direction"]
SHOW = KEY + ["n_trades", "sharpe_px", "max_dd_px", "profit_factor_px",
              "win_rate", "sharpe_acct", "total_return_acct", "cagr_acct"]
NEIGHBOUR_DIMS = {
    "breakout_lookback": BREAKOUT_LOOKBACKS, "trend_strength": TREND_STRENGTHS,
    "breakout_buffer": BREAKOUT_BUFFERS, "sl_points": SL_POINTS,
    "tp_points": TP_POINTS,
}
_bars_cache: dict = {}


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, (float, np.floating)):
        f = float(o)
        return None if (np.isnan(f) or np.isinf(f)) else f
    return o


def load_all() -> pd.DataFrame:
    frames = [pd.read_csv(p) for p in sorted(OUT_DIR.glob("asqs_sweep_*.csv"))]
    if not frames:
        raise SystemExit("no sweep CSVs found -- run run_asqs_sweep first")
    return pd.concat(frames, ignore_index=True)


def apply_gates(df: pd.DataFrame) -> pd.DataFrame:
    return df[(df.n_trades >= GATES["n_trades_min"])
              & (df.profit_factor_px >= GATES["profit_factor_min"])
              & (df.max_dd_px <= GATES["max_dd_max"])
              & (df.sharpe_px > GATES["sharpe_min"])].copy()


def _bars(tf: str):
    if tf not in _bars_cache:
        df = load(tf, tz="server_eet")
        _bars_cache[tf] = (df, A.Bars(df))
    return _bars_cache[tf]


def _signals(row: pd.Series):
    df, bars = _bars(row["timeframe"])
    ind = A.indicators(bars, int(row["ema_fast"]), int(row["ema_slow"]),
                       RSI_PERIOD, ATR_PERIOD, int(row["breakout_lookback"]))
    ls, ss = A.entry_signals(bars, ind, int(row["trend_strength"]),
                             float(row["breakout_buffer"]),
                             float(row["rsi_buy_min"]), float(row["rsi_buy_max"]),
                             float(row["rsi_sell_min"]), float(row["rsi_sell_max"]))
    sm = A.session_mask(bars, bool(row["use_session"]), int(row["session_start"]),
                        int(row["session_end"]), SESSION_FIXED["avoid_friday"],
                        SESSION_FIXED["friday_cutoff"])
    return df, bars, ind, ls, ss, sm


def rerun(row: pd.Series, override=None) -> dict:
    df, bars, ind, ls, ss, sm = _signals(row)
    if override is not None:
        ls, ss = override
    direc = row["direction"]
    return A.simulate(bars, ind, ls, ss, sm,
                      sl_points=int(row["sl_points"]), tp_points=int(row["tp_points"]),
                      partial_mode=PARTIAL_MODE,
                      enable_long=direc in ("both", "long"),
                      enable_short=direc in ("both", "short"), **SIM_FIXED)


def control_for(row: pd.Series, n_perm: int = N_PERMUTATIONS) -> dict:
    """AK1: does the 7-condition entry beat random timing in the same regime?"""
    df, bars, ind, ls, ss, sm = _signals(row)
    sim = rerun(row)
    if sim["n_trades"] < 2:
        return {"skipped": "fewer than 2 trades"}
    m = A.metrics(sim, basis="price")
    # Eligible pool = bars where indicators are warm AND the session filter
    # allows trading. Nothing about the 7 entry conditions, so the comparison
    # isolates entry TIMING while holding the session and costs fixed.
    warm = (np.isfinite(ind["ef"]) & np.isfinite(ind["es"]) & np.isfinite(ind["rsi"])
            & np.isfinite(ind["atr"]) & np.isfinite(ind["hi"]) & np.isfinite(ind["lo"]))
    pool = np.flatnonzero(warm & sm)
    direc = row["direction"]
    is_long = None if direc == "both" else (direc == "long")

    def run_masked(lm, smask):
        return rerun(row, override=(lm, smask))

    ctrl = matched_random_control(run_masked, pool, sim["n_trades"], bars.n,
                                  is_long=is_long, ppy=m["trades_per_year"],
                                  n_perm=n_perm)
    s = ctrl["sharpes"]; s = s[~np.isnan(s)]
    p = float((s >= m["sharpe"]).sum() / s.size) if s.size else float("nan")
    return {"actual_sharpe": m["sharpe"], "null_mean": ctrl["null_mean"],
            "null_p95": ctrl["null_p95"], "p_value": p,
            "target_trades": ctrl["target"], "median_realized": ctrl["median_realized"]}


def neighbours(row: pd.Series, df: pd.DataFrame) -> pd.DataFrame:
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


def dsr_at(returns, n_list, trial_sharpes=None) -> dict:
    res = {}
    for n in n_list:
        try:
            r = deflated_sharpe_ratio(returns, n_trials=int(n),
                                      trial_sharpes=trial_sharpes)
            res[str(n)] = {"dsr": float(r.dsr), "var_sr_source": r.var_sr_source}
        except Exception as exc:                        # noqa: BLE001
            res[str(n)] = {"error": str(exc)}
    return res


def _surface(df: pd.DataFrame, by: list[str]) -> list[dict]:
    g = df.groupby(by, dropna=False)
    out = g.agg(n_configs=("sharpe_px", "size"),
                median_sharpe=("sharpe_px", "median"),
                pct_positive=("sharpe_px", lambda s: float((s > 0).mean() * 100)),
                median_trades=("n_trades", "median")).reset_index()
    return _clean(out.to_dict("records"))


def _records(df: pd.DataFrame, n: int = 10) -> list[dict]:
    return _clean(df.head(n)[SHOW].to_dict("records"))


def _session_label(r) -> str:
    return "off" if not r["use_session"] else f"{int(r['session_start'])}-{int(r['session_end'])}"


def main() -> int:
    df = load_all()
    df["session"] = df.apply(_session_label, axis=1)
    countable = df[df.n_trades >= GATES["n_trades_min"]].copy()
    surv = apply_gates(df)

    report = {
        "n_configs_total": int(len(df)), "n_countable": int(len(countable)),
        "n_survivors": int(len(surv)),
        "survival_rate_pct": float(100.0 * len(surv) / max(len(df), 1)),
        "gates": GATES, "partial_mode": PARTIAL_MODE,
        "n_permutations": N_PERMUTATIONS,
        "by_timeframe": _surface(df, ["timeframe"]),
        "by_direction": _surface(df, ["direction"]),
        "by_tf_direction": _surface(df, ["timeframe", "direction"]),
        "by_session": _surface(df, ["session"]),
        "by_tf_session": _surface(df, ["timeframe", "session"]),
        "by_trend_strength": _surface(df, ["trend_strength"]),
        "by_sl_tp": _surface(df, ["sl_points", "tp_points"]),
    }
    report["rank_sharpe"] = _records(countable.sort_values("sharpe_px", ascending=False))
    report["rank_drawdown"] = _records(
        countable[countable.sharpe_px > 0].sort_values("max_dd_px"))
    report["rank_win_rate"] = _records(countable.sort_values("win_rate", ascending=False))
    report["rank_profit_factor"] = _records(
        countable[np.isfinite(countable.profit_factor_px)]
        .sort_values("profit_factor_px", ascending=False))

    if countable.empty:
        (OUT_DIR / "asqs_report_data.json").write_text(json.dumps(_clean(report), indent=2))
        print("no config clears the trade floor")
        return 0

    leader = countable.sort_values("sharpe_px", ascending=False).iloc[0]
    report["leader"] = _clean(leader[SHOW].to_dict())
    tf_leaders = (countable.sort_values("sharpe_px", ascending=False)
                  .groupby("timeframe").head(1))
    report["tf_leaders"] = _records(tf_leaders.sort_values("sharpe_px", ascending=False), n=10)

    controls = []
    for _, row in tf_leaders.sort_values("sharpe_px", ascending=False).iterrows():
        c = control_for(row)
        c.update({k: _clean(row[k]) for k in ["timeframe", "direction", "n_trades"]})
        c["session"] = _session_label(row)
        controls.append(_clean(c))
        print(f"  AK1 {row['timeframe']:>3} sess={c['session']:<5} "
              f"actual={c.get('actual_sharpe', float('nan')):.3f} "
              f"null={c.get('null_mean', float('nan')):.3f} "
              f"p={c.get('p_value', float('nan')):.3f}", flush=True)
    report["ak1_controls"] = controls

    bh = {}
    for tf in sorted(df.timeframe.unique()):
        b = buy_and_hold(load(tf, tz="server_eet"))
        b["calmar"] = b["cagr"] / b["max_dd"] if b["max_dd"] > 0 else float("nan")
        bh[tf] = _clean(b)
    report["buy_and_hold"] = bh
    beat = []
    for _, row in tf_leaders.iterrows():
        b = bh[row["timeframe"]]
        cal = (row["cagr_acct"] / row["max_dd_acct"]
               if row["max_dd_acct"] and np.isfinite(row["max_dd_acct"])
               and row["max_dd_acct"] > 0 else float("nan"))
        beat.append(_clean({"timeframe": row["timeframe"], "direction": row["direction"],
                            "session": _session_label(row), "calmar": cal,
                            "bh_calmar": b["calmar"],
                            "beats_bh": bool(np.isfinite(cal)
                                             and np.isfinite(b["calmar"])
                                             and cal > b["calmar"])}))
    report["ak2_calmar"] = beat
    report["ak2_n_beating_bh"] = int(sum(1 for x in beat if x["beats_bh"]))

    sim = rerun(leader)
    lead_r = sim["px_returns"]; lead_r = lead_r[~np.isnan(lead_r)]
    ts = countable["sharpe_px"].dropna()
    ts = ts[np.isfinite(ts)].to_numpy(float)
    try:
        from research.log import trial_count
        honest_n = int(trial_count())
    except Exception:                                    # noqa: BLE001
        honest_n = None
    n_list = sorted({x for x in [1, honest_n, len(countable), len(df)] if x})
    report["honest_trial_count"] = honest_n
    report["ak3_dsr"] = dsr_at(lead_r, n_list, trial_sharpes=ts)
    report["ak3_dsr_single_sharpe_se"] = dsr_at(lead_r, n_list)

    nb = neighbours(leader, df)
    nb_c = nb[nb.n_trades >= GATES["n_trades_min"]]
    report["ak4_neighbourhood"] = _clean({
        "n_neighbours": int(len(nb)), "n_countable": int(len(nb_c)),
        "median_sharpe": float(nb_c.sharpe_px.median()) if len(nb_c) else None,
        "min_sharpe": float(nb_c.sharpe_px.min()) if len(nb_c) else None,
        "all_positive": bool((nb_c.sharpe_px > 0).all()) if len(nb_c) else False,
        "rows": _records(nb_c.sort_values("sharpe_px", ascending=False), n=10)})

    # --- the section unique to ASQS: what the timezone defect cost ---------- #
    orig = df[(df.use_session) & (df.session_start == 8) & (df.session_end == 17)]
    sess_cmp = {}
    for s, g in df.groupby("session"):
        sess_cmp[s] = _clean({
            "n_configs": int(len(g)), "median_sharpe": float(g.sharpe_px.median()),
            "pct_positive": float((g.sharpe_px > 0).mean() * 100),
            "best_sharpe": float(g.sharpe_px.max()),
            "median_trades": float(g.n_trades.median())})
    report["session_comparison"] = sess_cmp
    report["original_window_is_best"] = bool(
        len(orig) and sess_cmp.get("8-17", {}).get("median_sharpe")
        == max(v["median_sharpe"] for v in sess_cmp.values()))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "asqs_report_data.json").write_text(json.dumps(_clean(report), indent=2))
    countable.sort_values("sharpe_px", ascending=False).head(500)[SHOW].to_csv(
        OUT_DIR / "asqs_deepdive.csv", index=False)
    print(f"\nconfigs={len(df):,} countable={len(countable):,} "
          f"survivors={len(surv):,} ({report['survival_rate_pct']:.2f}%)")
    print(f"leader: {report['leader']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
