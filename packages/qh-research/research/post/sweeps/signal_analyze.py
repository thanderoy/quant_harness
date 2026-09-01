"""research.post.sweeps.signal_analyze — analyse the pre-stage signal sweeps.

Covers flood_tide, avwap_sweep_reclaim and avwap_multibar_reclaim in one pass,
because they share an exit grid and the interesting comparison is between them.

The question these sweeps answer is narrow and worth stating precisely: given
this entry, does ANY exit in a wide grid produce a viable strategy? A negative
answer is strong -- it means the entry cannot be rescued by exit engineering,
which is the usual defence of a mean-reversion signal with a flat E-Ratio.
A positive answer is weak, because per seq=49 topping a grid carries no
out-of-sample information.

Usage:  python -m research.post.sweeps.signal_analyze
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from research.post.dsr import deflated_sharpe_ratio
from research.post.sweeps.analyze import GATES
from research.post.sweeps.control import (buy_and_hold, matched_random_control,
                                          N_PERMUTATIONS)
from research.post.sweeps.data import load
from research.post.sweeps.run_signal_sweep import (OUT_DIR, RISK_PCT, SIGNALS,
                                                   _masks, _init_worker, _G)
from research.post.sweeps import cnk_engine as E

SHOW = ["signal", "timeframe", "entry_p1", "entry_p2", "entry_p3", "exit_family",
        "atr_period", "sl_mult", "tp_mult", "trail_mult", "direction", "min_atr",
        "n_trades", "sharpe_px", "max_dd_px", "profit_factor_px", "win_rate",
        "cagr_acct"]


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
    frames = [pd.read_csv(p) for p in sorted(OUT_DIR.glob("signal_sweep_*.csv"))]
    if not frames:
        raise SystemExit("no signal sweep CSVs found -- run run_signal_sweep first")
    return pd.concat(frames, ignore_index=True)


def _surface(df, by):
    g = df.groupby(by, dropna=False)
    out = g.agg(n_configs=("sharpe_px", "size"),
                median_sharpe=("sharpe_px", "median"),
                pct_positive=("sharpe_px", lambda s: float((s > 0).mean() * 100)),
                median_trades=("n_trades", "median"),
                best_sharpe=("sharpe_px", "max")).reset_index()
    return _clean(out.to_dict("records"))


def drift_control(row, n_perm: int = N_PERMUTATIONS) -> dict:
    """Matched random-entry null for one swept config.

    THIS IS THE LOAD-BEARING TEST for these signals, not the ranking. A
    long-only breakout with a trailing stop on a secular bull instrument will
    show a positive Sharpe from DRIFT ALONE. The null randomises only the entry
    bars, holding direction, exit rule, realised trade count, sizing and the
    full cost model identical, so the comparison isolates entry timing. A
    positive surface that does not clear this null is measuring gold, not the
    signal.
    """
    sig = row["signal"]
    spec = SIGNALS[sig]
    tf = spec["tf"]
    df = load(tf, tz="server_eet", with_volume=spec["volume"])
    aux = load("H4", tz="server_eet") if sig == "flood_tide" else None
    _init_worker(sig, df, aux)
    _G["tf"] = tf
    bars = E.Bars(df)
    p3 = row["entry_p3"] if not pd.isna(row["entry_p3"]) else None
    unit = (sig, row["entry_p1"], row["entry_p2"], p3)
    long_m, short_m = _masks(unit)

    ap = int(row["atr_period"])
    atr_v = E.atr(bars.high, bars.low, bars.close, ap)
    dummy = np.zeros(bars.n, float)
    mode = "momentum" if row["exit_family"] == "trail" else "pullback"
    direc = row["direction"]
    en_l, en_s = direc in ("both", "long"), direc in ("both", "short")

    def run(lm, sm):
        return E.simulate(bars, mode, dummy, atr_v, lm, sm,
                          enable_long=en_l, enable_short=en_s,
                          sl_mult=float(row["sl_mult"]), tp_mult=float(row["tp_mult"]),
                          trail_mult=float(row["trail_mult"]), risk_pct=RISK_PCT,
                          min_atr=float(row["min_atr"]), max_dd_halt=1.0)

    sim = run(long_m, short_m)
    if sim["n_trades"] < 2:
        return {"skipped": "fewer than 2 trades"}
    m = E.metrics(sim, basis="price")
    ok = np.isfinite(atr_v) & (np.nan_to_num(atr_v, nan=-1.0) >= float(row["min_atr"]))
    pool = np.flatnonzero(ok)
    is_long = None if direc == "both" else (direc == "long")
    ctrl = matched_random_control(run, pool, sim["n_trades"], bars.n,
                                  is_long=is_long, ppy=m["trades_per_year"],
                                  n_perm=n_perm)
    sh = ctrl["sharpes"]; sh = sh[~np.isnan(sh)]
    pv = float((sh >= m["sharpe"]).sum() / sh.size) if sh.size else float("nan")
    return {"actual_sharpe": m["sharpe"], "null_mean": ctrl["null_mean"],
            "null_p95": ctrl["null_p95"], "p_value": pv,
            "target_trades": ctrl["target"], "median_realized": ctrl["median_realized"],
            "beats_drift": bool(np.isfinite(pv) and pv < 0.05)}


def main() -> int:
    df = load_all()
    countable = df[df.n_trades >= GATES["n_trades_min"]].copy()
    surv = df[(df.n_trades >= GATES["n_trades_min"])
              & (df.profit_factor_px >= GATES["profit_factor_min"])
              & (df.max_dd_px <= GATES["max_dd_max"])
              & (df.sharpe_px > GATES["sharpe_min"])]

    report = {
        "n_configs_total": int(len(df)), "n_countable": int(len(countable)),
        "n_survivors": int(len(surv)), "gates": GATES,
        "by_signal": _surface(df, ["signal"]),
        "by_signal_exit": _surface(df, ["signal", "exit_family"]),
        "by_signal_direction": _surface(df, ["signal", "direction"]),
        "by_signal_countable": _surface(countable, ["signal"]) if len(countable) else [],
    }

    # Per-signal detail, including the trade-floor question which is decisive
    # for the AVWAP signals -- they fire rarely enough that many configs cannot
    # produce a meaningful Sharpe at all.
    per = {}
    for sig, g in df.groupby("signal"):
        gc = g[g.n_trades >= GATES["n_trades_min"]]
        tf = g.timeframe.iloc[0]
        bh = buy_and_hold(load(tf, tz="server_eet"))
        bh["calmar"] = bh["cagr"] / bh["max_dd"] if bh["max_dd"] > 0 else float("nan")
        d = {"timeframe": tf, "n_configs": int(len(g)),
             "n_countable": int(len(gc)),
             "pct_countable": float(100.0 * len(gc) / max(len(g), 1)),
             "median_trades": float(g.n_trades.median()),
             "max_trades": int(g.n_trades.max()),
             "median_sharpe": float(g.sharpe_px.median()),
             "pct_positive": float((g.sharpe_px > 0).mean() * 100),
             "buy_and_hold": _clean(bh)}
        if len(gc):
            best = gc.sort_values("sharpe_px", ascending=False).iloc[0]
            d["best"] = _clean(best[SHOW].to_dict())
            r = gc.sharpe_px.dropna()
            r = r[np.isfinite(r)].to_numpy(float)
            d["best_countable_sharpe"] = float(gc.sharpe_px.max())
            d["top10"] = _clean(gc.sort_values("sharpe_px", ascending=False)
                                .head(10)[SHOW].to_dict("records"))
        else:
            d["best"] = None
            d["note"] = ("no configuration reaches the trade floor -- this entry "
                         "fires too rarely for any exit to be evaluated")
        # Drift control on the best countable config for this signal. Without
        # it a positive surface cannot be distinguished from gold's uptrend.
        if d.get("best"):
            try:
                d["drift_control"] = _clean(drift_control(gc.sort_values(
                    "sharpe_px", ascending=False).iloc[0]))
                c = d["drift_control"]
                print(f"  drift control {sig}: actual "
                      f"{c.get('actual_sharpe', float('nan')):.3f} vs null "
                      f"{c.get('null_mean', float('nan')):.3f}  "
                      f"p={c.get('p_value', float('nan')):.3f}", flush=True)
            except Exception as exc:                      # noqa: BLE001
                d["drift_control"] = {"error": f"{type(exc).__name__}: {exc}"}
                print(f"  drift control {sig} FAILED: {exc}", flush=True)
        per[sig] = d
    report["per_signal"] = per

    # DSR on the single best countable config across all three signals.
    if len(countable):
        lead = countable.sort_values("sharpe_px", ascending=False).iloc[0]
        report["leader"] = _clean(lead[SHOW].to_dict())
        ts = countable.sharpe_px.dropna()
        ts = ts[np.isfinite(ts)].to_numpy(float)
        try:
            from research.log import trial_count
            hn = int(trial_count())
        except Exception:                                # noqa: BLE001
            hn = None
        report["honest_trial_count"] = hn
        # Per-trade returns are not stored in the CSV, so DSR here is computed
        # from the config's Sharpe under the same estimator the other sweeps
        # use; recorded as approximate and clearly labelled.
        report["dsr_note"] = (
            "DSR is not computed here: the sweep CSVs store summary metrics, "
            "not per-trade return series, and deflated_sharpe_ratio requires "
            "raw per-observation returns. Re-simulate the leader to compute it. "
            "Given seq=49 this is deliberately not treated as a promotion path.")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "signal_report_data.json").write_text(json.dumps(_clean(report), indent=2))

    print(f"configs={len(df):,}  countable={len(countable):,}  survivors={len(surv):,}")
    for sig, d in per.items():
        print(f"\n{sig} [{d['timeframe']}]")
        print(f"  configs {d['n_configs']:,}  countable {d['n_countable']:,} "
              f"({d['pct_countable']:.1f}%)  median trades {d['median_trades']:.0f} "
              f"(max {d['max_trades']:,})")
        print(f"  median Sharpe {d['median_sharpe']:+.3f}  "
              f"%positive {d['pct_positive']:.1f}%")
        if d["best"]:
            b = d["best"]
            print(f"  best countable: {b['exit_family']} atr{int(b['atr_period'])} "
                  f"sl{b['sl_mult']:g} tp{b['tp_mult']:g} tr{b['trail_mult']:g} "
                  f"{b['direction']} -> Sharpe {b['sharpe_px']:+.3f} "
                  f"({int(b['n_trades'])} trades, PF {b['profit_factor_px']:.3f})")
        else:
            print(f"  {d['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
