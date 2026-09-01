"""research.post.sweeps.run_asqs_sweep — exhaustive sweep of ASQ SafeScalping.

ASQS is the last strategy in this repo with a real engine that had never been
swept, and the only one still running live on demo (magic-tagged, seq=30
recorded its seeded 5.14 Sharpe as REFUTED).

Two defects found during the engine port change what a sweep of this strategy
even means, and both are swept or reported rather than assumed away:

1. TIMEZONE. ASQS is session-filtered by default (08:00-17:00, documented "UTC
   hour"). The CSVs are broker server time, so every recorded ASQS result -- 
   seq=30 included -- filtered the wrong hours by 2-3 DST-dependent hours.
   Bars here load with tz="server_eet" (true UTC) and the session window is a
   SWEPT dimension.

2. PARTIAL CLOSE IS INERT UNDER THE HARNESS. btpy_runner sets
   exclusive_orders=True, so the second of ASQS's two partial-close orders
   cancels the first. The TP1 leg never exists; the only surviving effect is
   that position size is halved. Verified against harness trades (349 trades,
   all unique entry times, all at the remainder size). The main grid runs
   partial_mode="harness" so it is comparable with everything already logged;
   run_asqs_partial_compare covers the intended two-leg behaviour separately,
   because folding it into the factorial would double a grid that is already
   M5-bound.

max_drawdown_halt is ASQS's own max_dd_pct and is NOT disabled here, unlike the
cnk/zlch/ebb sweeps: it is not an absorbing barrier in this strategy (it blocks
new entries while the drawdown holds and releases on recovery), so it does not
truncate a config's record. It is swept.

Usage:
    python -m research.post.sweeps.run_asqs_sweep --tf M5
    python -m research.post.sweeps.run_asqs_sweep --all
"""
from __future__ import annotations

import argparse
import itertools
import json
import time
from multiprocessing import Pool
from pathlib import Path

import pandas as pd

from research.post.sweeps import default_workers
from research.post.sweeps import asqs_engine as A
from research.post.sweeps.data import load

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = REPO_ROOT / "research" / "data" / "asqs"

# ---- FROZEN GRID ---------------------------------------------------------- #
EMA_PAIRS = [(20, 100), (20, 200), (50, 100), (50, 200), (50, 400), (100, 400)]
BREAKOUT_LOOKBACKS = [10, 15, 25]
TREND_STRENGTHS = [0, 1, 2]
BREAKOUT_BUFFERS = [0.1, 0.3]
# (buy_min, buy_max, sell_min, sell_max)
RSI_BANDS = [(45.0, 65.0, 35.0, 55.0), (40.0, 70.0, 30.0, 60.0)]
SL_POINTS = [150, 300, 500]
TP_POINTS = [225, 450, 750]
# (use_session, start, end). Includes the ORIGINAL 8-17 window, an earlier
# London-weighted window, and no session filter at all.
SESSIONS = [(True, 8, 17), (True, 7, 16), (False, 0, 24)]
DIRECTIONS = ["both", "long", "short"]

# Held fixed -- swept dimensions were chosen to keep M5 tractable.
RSI_PERIOD = 14
ATR_PERIOD = 50
PARTIAL_MODE = "harness"
# Split deliberately: SIM_FIXED goes to simulate(), SESSION_FIXED to
# session_mask(). Passing the session keys into simulate() is a TypeError.
SIM_FIXED = dict(use_breakeven=True, breakeven_start=150, breakeven_offset=20,
                 use_trailing=True, trail_start=200, trail_step=100,
                 use_partial_close=True, tp1_points=200, tp1_close_pct=50.0,
                 risk_pct=0.5, max_day_trades=4, max_dd_pct=8.0)
SESSION_FIXED = dict(avoid_friday=True, friday_cutoff=14)
FIXED = {**SIM_FIXED, **SESSION_FIXED}          # for the frozen-grid record

TIMEFRAMES = ["M5", "M15", "H1"]     # a point-based scalper; H4/D1 are meaningless
_G: dict = {}


def _units() -> list[tuple]:
    return [(ef, es, bl) for (ef, es), bl
            in itertools.product(EMA_PAIRS, BREAKOUT_LOOKBACKS)]


def _init_worker(tf, bars):
    _G["tf"], _G["bars"] = tf, bars


def _row(tf, ef, es, bl, ts, bb, rb, sl, tp, sess, direc, sim) -> dict:
    mpx = A.metrics(sim, basis="price")
    mac = A.metrics(sim, basis="account")
    return {
        "timeframe": tf, "ema_fast": ef, "ema_slow": es, "breakout_lookback": bl,
        "trend_strength": ts, "breakout_buffer": bb,
        "rsi_buy_min": rb[0], "rsi_buy_max": rb[1],
        "rsi_sell_min": rb[2], "rsi_sell_max": rb[3],
        "sl_points": sl, "tp_points": tp,
        "use_session": sess[0], "session_start": sess[1], "session_end": sess[2],
        "direction": direc, "partial_mode": PARTIAL_MODE,
        "n_trades": mpx["n_trades"], "trades_per_year": mpx["trades_per_year"],
        "sharpe_px": mpx["sharpe"], "max_dd_px": mpx["max_dd"],
        "profit_factor_px": mpx["profit_factor"], "win_rate": mpx["win_rate"],
        "expectancy_px": mpx["expectancy"],
        "sharpe_acct": mac["sharpe"], "max_dd_acct": mac["max_dd"],
        "profit_factor_acct": mac["profit_factor"],
        "total_return_acct": mac["total_return"], "cagr_acct": mac["cagr"],
        "equity_final": sim["equity_final"],
    }


def _eval_unit(unit) -> list[dict]:
    ef, es, bl = unit
    tf, bars = _G["tf"], _G["bars"]
    ind = A.indicators(bars, ef, es, RSI_PERIOD, ATR_PERIOD, bl)
    rows: list[dict] = []
    sess_cache = {s: A.session_mask(bars, s[0], s[1], s[2],
                                    SESSION_FIXED["avoid_friday"],
                                    SESSION_FIXED["friday_cutoff"])
                  for s in SESSIONS}
    for ts, bb, rb in itertools.product(TREND_STRENGTHS, BREAKOUT_BUFFERS, RSI_BANDS):
        ls, ss = A.entry_signals(bars, ind, ts, bb, rb[0], rb[1], rb[2], rb[3])
        for sess in SESSIONS:
            sm = sess_cache[sess]
            for direc in DIRECTIONS:
                for sl, tp in itertools.product(SL_POINTS, TP_POINTS):
                    sim = A.simulate(
                        bars, ind, ls, ss, sm, sl_points=sl, tp_points=tp,
                        partial_mode=PARTIAL_MODE,
                        enable_long=direc in ("both", "long"),
                        enable_short=direc in ("both", "short"), **SIM_FIXED)
                    rows.append(_row(tf, ef, es, bl, ts, bb, rb, sl, tp,
                                     sess, direc, sim))
    return rows


def sweep_tf(tf: str, workers: int) -> pd.DataFrame:
    t0 = time.time()
    df = load(tf, tz="server_eet")            # TRUE UTC -- session filter depends on it
    bars = A.Bars(df)
    units = _units()
    rows: list[dict] = []
    with Pool(workers, initializer=_init_worker, initargs=(tf, bars)) as pool:
        for i, res in enumerate(pool.imap_unordered(_eval_unit, units), 1):
            rows.extend(res)
            print(f"  [{tf}] unit {i}/{len(units)}  rows={len(rows):,}  "
                  f"{time.time() - t0:.0f}s", flush=True)
    out = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"asqs_sweep_{tf}.csv"
    out.to_csv(path, index=False)
    print(f"[{tf}] {len(out):,} configs, {df.index[0].date()}..{df.index[-1].date()}, "
          f"{time.time() - t0:.0f}s -> {path}", flush=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tf", choices=TIMEFRAMES)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--workers", type=int, default=default_workers())
    ap.add_argument("--count-only", action="store_true")
    args = ap.parse_args()

    per_tf = (len(_units()) * len(TREND_STRENGTHS) * len(BREAKOUT_BUFFERS)
              * len(RSI_BANDS) * len(SESSIONS) * len(DIRECTIONS)
              * len(SL_POINTS) * len(TP_POINTS))
    if args.count_only:
        print(f"{len(_units())} units x inner = {per_tf:,} configs per timeframe")
        return 0

    tfs = TIMEFRAMES if args.all else [args.tf]
    total = 0
    for tf in tfs:
        total += len(sweep_tf(tf, args.workers))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "asqs_sweep_summary.json").write_text(json.dumps({
        "n_configs_total": total, "per_timeframe": per_tf,
        "timeframes": tfs, "partial_mode": PARTIAL_MODE,
        "tz": "server_eet", "fixed": FIXED,
        "grid": {"ema_pairs": EMA_PAIRS, "breakout_lookbacks": BREAKOUT_LOOKBACKS,
                 "trend_strengths": TREND_STRENGTHS,
                 "breakout_buffers": BREAKOUT_BUFFERS, "rsi_bands": RSI_BANDS,
                 "sl_points": SL_POINTS, "tp_points": TP_POINTS,
                 "sessions": SESSIONS, "directions": DIRECTIONS,
                 "rsi_period": RSI_PERIOD, "atr_period": ATR_PERIOD}},
        indent=2))
    print(f"\nTOTAL {total:,} configs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
