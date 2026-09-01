"""research.pre.asian_session_fade — event study for the seq=15 hypothesis.

MECHANISM UNDER TEST (from the registration)
    The 22:00-05:00 UTC book is thin. Price overshoots in that vacuum. When
    real liquidity arrives at the London open it gets pushed back toward fair
    value. The payer is whoever had to transact into the thin session.

This is deliberately NOT a strategy. No entry rule, no exit, no sizing, no
parameter search. It is the cheapest thing that can falsify the mechanism: a
SORT. Bucket days by how far the Asian session overshot, then look at what
happens next. If the effect is not visible in a sort it will not be rescued by
a backtest with parameters bolted on.

Per CLAUDE.md this is a mean-reversion entry, so the E-Ratio is DIAGNOSTIC
ONLY and never a veto -- the edge is expected to live in the exit. The bucket
sort below is the primary evidence; nothing here is a hard gate.

TIMEZONE. Bars load with tz="server_eet" because the CSVs are broker server
time (EET/EEST), not UTC. Using the default would shift the session window by
2-3 hours and test a different session entirely. See research/post/sweeps/data.py.

CONTROLS
    1. London session overshoot -> same forward window. If the reversion is a
       property of thin books it should be WEAKER here, where the book is deep.
       If it is the same, we are measuring generic mean reversion, not the
       stated mechanism.
    2. Sign-flipped / shuffled overshoot. Breaks the link between the
       conditioning variable and the forward return while keeping both
       marginal distributions, pricing in drift and autocorrelation.

Usage:
    python -m research.pre.asian_session_fade
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd
from scipy import stats

from research.post.sweeps.data import load

RANDOM_SEED = 20260820
N_SHUFFLE = 2000

# All hours UTC. Asian = the thin book. London = the deep-book control.
SESSIONS = {"asian": (22, 5), "london": (7, 12)}
# The forward window is SESSION-RELATIVE: it starts when the session being
# measured ends, and runs FORWARD_HOURS beyond it. It must never overlap the
# session itself -- a fixed window that overlaps returns beta ~ +1.0 because
# the "forward" return then contains the session's own displacement.
FORWARD_HOURS = 6
N_BUCKETS = 10
ATR_DAYS = 14


def _atr_daily(d1: pd.DataFrame, n: int = ATR_DAYS) -> pd.Series:
    pc = d1.close.shift(1)
    tr = pd.concat([d1.high - d1.low, (d1.high - pc).abs(),
                    (d1.low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def _window(h1: pd.DataFrame, start_h: int, end_h: int) -> pd.DataFrame:
    """Aggregate each session window to one row per session date.

    A window that wraps midnight (22->5) is stamped with the date it ENDS on,
    so 'the Asian session preceding this London open' is one row.
    """
    h = h1.index.hour
    if start_h > end_h:                      # wraps midnight
        mask = (h >= start_h) | (h < end_h)
        # bars at/after start_h belong to the NEXT calendar date's session
        date = np.where(h >= start_h,
                        (h1.index + pd.Timedelta(days=1)).normalize(),
                        h1.index.normalize())
    else:
        mask = (h >= start_h) & (h < end_h)
        date = h1.index.normalize()
    sub = h1[mask].copy()
    sub["sdate"] = pd.DatetimeIndex(np.asarray(date)[mask])
    g = sub.groupby("sdate")
    out = pd.DataFrame({
        "open": g.open.first(), "high": g.high.max(),
        "low": g.low.min(), "close": g.close.last(), "bars": g.close.size(),
    })
    return out[out.bars >= 3]


def _forward(h1: pd.DataFrame, end_h: int) -> pd.DataFrame:
    """Return prices at the session end and FORWARD_HOURS later, by date."""
    h = h1.index.hour
    to_h = (end_h + FORWARD_HOURS) % 24
    a = h1[h == end_h].copy()
    b = h1[h == to_h].copy()
    a["d"] = a.index.normalize()
    # If the forward window wraps past midnight the endpoint belongs to the
    # session date that STARTED the window, so pull that date back a day.
    b["d"] = (b.index - pd.Timedelta(days=1)).normalize() if to_h < end_h \
        else b.index.normalize()
    a = a.groupby("d").close.first().rename("px_from")
    b = b.groupby("d").close.first().rename("px_to")
    return pd.concat([a, b], axis=1).dropna()


def build(tf_h1: pd.DataFrame, d1: pd.DataFrame, session: str) -> pd.DataFrame:
    s0, s1 = SESSIONS[session]
    sess = _window(tf_h1, s0, s1)
    fwd = _forward(tf_h1, s1)
    atr = _atr_daily(d1).rename("atr")
    atr.index = atr.index.normalize()
    df = sess.join(fwd, how="inner").join(atr.shift(1), how="inner").dropna()
    df = df[df.atr > 0]
    # Overshoot: the session's net displacement, normalised by yesterday's ATR.
    # Signed, so a positive value means the thin session pushed price UP.
    df["overshoot"] = (df.close - df.open) / df.atr
    # Forward return over the London morning, same normalisation.
    df["fwd"] = (df.px_to - df.px_from) / df.atr
    return df[np.isfinite(df.overshoot) & np.isfinite(df.fwd)]


def bucket_table(df: pd.DataFrame, n: int = N_BUCKETS) -> pd.DataFrame:
    q = pd.qcut(df.overshoot, n, labels=False, duplicates="drop")
    g = df.groupby(q)
    t = pd.DataFrame({
        "n": g.size(),
        "overshoot_mean": g.overshoot.mean(),
        "fwd_mean": g.fwd.mean(),
        "fwd_median": g.fwd.median(),
        "fwd_t": g.fwd.apply(lambda s: stats.ttest_1samp(s, 0.0).statistic
                             if len(s) > 2 else np.nan),
        "pct_reverting": g.apply(
            lambda x: float((np.sign(x.fwd) != np.sign(x.overshoot)).mean() * 100),
            include_groups=False),
    })
    return t


def headline(df: pd.DataFrame) -> dict:
    """The single number the mechanism predicts: beta of fwd on overshoot < 0."""
    x = df.overshoot.to_numpy(float)
    y = df.fwd.to_numpy(float)
    lr = stats.linregress(x, y)
    rng = np.random.default_rng(RANDOM_SEED)
    null = np.empty(N_SHUFFLE)
    for i in range(N_SHUFFLE):
        null[i] = stats.linregress(rng.permutation(x), y).slope
    p_shuf = float((null <= lr.slope).mean())
    return {"n": int(len(df)), "beta": float(lr.slope),
            "beta_t": float(lr.slope / lr.stderr) if lr.stderr else float("nan"),
            "beta_p_analytic": float(lr.pvalue),
            "beta_p_shuffle_lte": p_shuf,
            "r_squared": float(lr.rvalue ** 2),
            "corr": float(lr.rvalue),
            "fwd_mean_top_decile": float(
                df[df.overshoot >= df.overshoot.quantile(0.9)].fwd.mean()),
            "fwd_mean_bottom_decile": float(
                df[df.overshoot <= df.overshoot.quantile(0.1)].fwd.mean())}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", default="research/pre/artifacts/asian_session_fade.json")
    args = ap.parse_args()

    h1 = load("H1", tz="server_eet")
    d1 = load("D1", tz="server_eet")
    print(f"H1 {len(h1):,} bars {h1.index[0]} .. {h1.index[-1]}  (true UTC)")

    report = {"sessions": SESSIONS, "forward_hours": FORWARD_HOURS,
              "atr_days": ATR_DAYS, "n_shuffle": N_SHUFFLE, "seed": RANDOM_SEED,
              "results": {}}

    for session in ("asian", "london"):
        df = build(h1, d1, session)
        h = headline(df)
        report["results"][session] = {"headline": h,
                                      "buckets": bucket_table(df).reset_index()
                                      .to_dict("records")}
        tag = "MECHANISM" if session == "asian" else "CONTROL (deep book)"
        print(f"\n{'=' * 70}\n{session.upper()}  {tag}\n{'=' * 70}")
        print(f"  n days           : {h['n']:,}")
        print(f"  beta(fwd~overshoot): {h['beta']:+.4f}   t={h['beta_t']:+.2f}   "
              f"r={h['corr']:+.3f}  R2={h['r_squared']:.4f}")
        print(f"  p analytic       : {h['beta_p_analytic']:.4f}")
        print(f"  p shuffle (beta<=): {h['beta_p_shuffle_lte']:.4f}   "
              f"[{N_SHUFFLE} permutations]")
        print(f"  fwd | top decile : {h['fwd_mean_top_decile']:+.4f} ATR")
        print(f"  fwd | bot decile : {h['fwd_mean_bottom_decile']:+.4f} ATR")
        print("\n  bucket  n     overshoot   fwd_mean   fwd_t   %reverting")
        for r in bucket_table(df).reset_index().to_dict("records"):
            print(f"   {int(r['overshoot']):>4}  {int(r['n']):>5}  "
                  f"{r['overshoot_mean']:>+8.3f}  {r['fwd_mean']:>+8.4f}  "
                  f"{r['fwd_t']:>+6.2f}   {r['pct_reverting']:>5.1f}%")

    a = report["results"]["asian"]["headline"]
    l = report["results"]["london"]["headline"]
    print(f"\n{'=' * 70}\nVERDICT INPUTS\n{'=' * 70}")
    print(f"  asian beta  {a['beta']:+.4f} (t {a['beta_t']:+.2f})")
    print(f"  london beta {l['beta']:+.4f} (t {l['beta_t']:+.2f})  <- deep-book control")
    print("  mechanism predicts: asian beta < 0 AND clearly more negative than london")

    from pathlib import Path
    Path(args.json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.json).write_text(json.dumps(report, indent=2, default=float))
    print(f"\nwrote {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
