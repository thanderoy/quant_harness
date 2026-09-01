"""research.pre.feature_screen — does ANY candidate feature carry tradeable edge?

Motivation
----------
Eleven strategies have been tested in this repo and none is viable. Every one
was an indicator recombination on XAUUSD bars. Rather than build a twelfth,
this screens the INPUTS: it asks, for each candidate predictor, whether it
carries information about forward returns, and whether that information is
large enough to pay the spread.

The cost floor is the whole point. A Pepperstone XAUUSD round trip is
$0.22/oz spread + $0.07/oz commission = $0.29/oz. `asian_session_fade` died at
seq=48 with a gross edge of $0.082/oz -- a real effect, 3.5x too small. So
every feature here is scored in DOLLARS PER OUNCE as well as in correlation,
and a feature whose top-minus-bottom decile spread is under $0.29 cannot be
traded on its own no matter how significant its t-statistic.

Method
------
For each (timeframe, feature, horizon):
  * compute the feature causally on closed bars only (no lookahead)
  * compute the forward return over `horizon` bars from the NEXT bar's open
    (entry realism: you cannot trade the close you just observed)
  * Spearman IC, decile monotonicity, and the top-minus-bottom decile spread
    expressed both in ATR units and in $/oz
  * Newey-West t-statistic on the decile spread to handle the overlapping
    windows that horizons > 1 create

Multiple testing is corrected with Benjamini-Hochberg FDR across the whole
screen, because running ~20 features x 4 horizons x 3 timeframes and reporting
the best raw p-value is exactly the error seq=49 documented.

TIMEZONE: bars load tz="server_eet" (true UTC). Session features are
meaningless otherwise -- the raw CSVs are broker server time.

Usage:
    python -m research.pre.feature_screen --tf M5
    python -m research.pre.feature_screen --all
"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from research.post.sweeps.data import load

REPO_ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = REPO_ROOT / "research" / "pre" / "artifacts"

SPREAD_USD_PER_OZ = 0.22
COMMISSION_USD_PER_OZ = 0.07
ROUND_TRIP_COST = SPREAD_USD_PER_OZ + COMMISSION_USD_PER_OZ

TIMEFRAMES = ["M5", "M15", "H1"]
HORIZONS = [1, 3, 6, 12]
N_DECILES = 10
ATR_LEN = 14


# --------------------------------------------------------------------------- #
# helpers                                                                       #
# --------------------------------------------------------------------------- #
def _atr(df: pd.DataFrame, n: int = ATR_LEN) -> pd.Series:
    pc = df.close.shift(1)
    tr = pd.concat([df.high - df.low, (df.high - pc).abs(),
                    (df.low - pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def _zscore(s: pd.Series, n: int) -> pd.Series:
    m = s.rolling(n).mean()
    sd = s.rolling(n).std(ddof=0)
    return (s - m) / sd.replace(0, np.nan)


def _session_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP anchored to each UTC day, using tick volume."""
    tp = (df.high + df.low + df.close) / 3.0
    day = df.index.normalize()
    pv = (tp * df.volume).groupby(day).cumsum()
    vv = df.volume.groupby(day).cumsum().replace(0, np.nan)
    return pv / vv


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Every feature is a function of information available at the bar CLOSE."""
    c, h, l, o, v = df.close, df.high, df.low, df.open, df.volume
    atr = _atr(df)
    rng = (h - l).replace(0, np.nan)
    day = df.index.normalize()
    f = pd.DataFrame(index=df.index)

    # --- momentum / reversal at several lookbacks --------------------------
    for k in (1, 3, 6, 12, 24):
        f[f"ret_{k}"] = (c / c.shift(k) - 1.0) / (atr / c)

    # --- intraday momentum (Gao/Han/Li/Zhou): return so far today ----------
    day_open = o.groupby(day).transform("first")
    f["intraday_ret"] = (c / day_open - 1.0) / (atr / c)
    # first-hour return, held constant through the day
    first_n = {"M5": 12, "M15": 4, "H1": 1}
    f["_first_n"] = np.nan  # filled by caller-specific code below

    # --- candle shape / order-flow proxies ---------------------------------
    f["body_ratio"] = (c - o) / rng
    f["upper_wick"] = (h - np.maximum(c, o)) / rng
    f["lower_wick"] = (np.minimum(c, o) - l) / rng
    f["close_pos"] = (c - l) / rng                       # where in the bar we closed
    f["signed_vol"] = np.sign(c - o) * _zscore(v, 96)    # direction x volume surprise
    f["vol_z"] = _zscore(v, 96)

    # --- volatility state ---------------------------------------------------
    f["atr_pct"] = atr / c
    f["atr_ratio"] = atr / atr.rolling(96).mean()
    f["range_expansion"] = rng / rng.rolling(24).mean()
    rv = (np.log(c / c.shift(1))).rolling(12).std(ddof=0)
    f["rv_ratio"] = rv / rv.rolling(96).mean()

    # --- structure ----------------------------------------------------------
    f["dist_vwap"] = (c - _session_vwap(df)) / atr
    # PRIOR-day high/low. `high.groupby(day).transform("max")` would broadcast
    # the CURRENT day's max back onto bars that precede it -- a lookahead that
    # manufactures an IC of -0.45 and a monotonicity of exactly -1.00. Aggregate
    # to daily, shift one DAY, then map back onto bars.
    daily = pd.DataFrame({"dh": h.groupby(day).max(), "dl": l.groupby(day).min()})
    prev_day = daily.shift(1)
    pdh = pd.Series(day.map(prev_day["dh"]), index=df.index)
    pdl = pd.Series(day.map(prev_day["dl"]), index=df.index)
    f["dist_pdh"] = (c - pdh) / atr
    f["dist_pdl"] = (c - pdl) / atr
    er_num = (c - c.shift(12)).abs()
    er_den = (c - c.shift(1)).abs().rolling(12).sum().replace(0, np.nan)
    f["efficiency_ratio"] = er_num / er_den
    same = np.sign(c - o)
    f["streak"] = same.groupby((same != same.shift()).cumsum()).cumcount() + 1
    f["streak"] = f["streak"] * same

    # --- calendar (true UTC) ------------------------------------------------
    f["hour"] = df.index.hour.astype(float)
    f["dow"] = df.index.dayofweek.astype(float)

    f = f.drop(columns=["_first_n"])
    return f, atr


def forward_return(df: pd.DataFrame, atr: pd.Series, horizon: int):
    """Return from NEXT bar's open to the open `horizon` bars later.

    Entry at the next open rather than this close is the same convention the
    sweep engines use; scoring a feature against the close it was computed on
    would manufacture edge that cannot be captured.
    """
    entry = df.open.shift(-1)
    exit_ = df.open.shift(-1 - horizon)
    usd = exit_ - entry                              # $ per ounce, unsigned
    in_atr = usd / atr
    return usd, in_atr


def _nw_tstat(x: np.ndarray, lags: int) -> float:
    """Newey-West t-stat of the mean, for overlapping windows."""
    x = x[np.isfinite(x)]
    n = x.size
    if n < 30:
        return float("nan")
    mu = x.mean()
    e = x - mu
    gamma0 = float(e @ e / n)
    var = gamma0
    for L in range(1, min(lags, n - 1) + 1):
        w = 1.0 - L / (lags + 1.0)
        cov = float(e[L:] @ e[:-L] / n)
        var += 2.0 * w * cov
    if var <= 0:
        return float("nan")
    return float(mu / np.sqrt(var / n))


def screen_one(feat: pd.Series, usd: pd.Series, in_atr: pd.Series,
               horizon: int) -> dict:
    m = np.isfinite(feat) & np.isfinite(usd) & np.isfinite(in_atr)
    x, yu, ya = feat[m], usd[m], in_atr[m]
    if x.size < 500 or x.nunique() < N_DECILES:
        return {"n": int(x.size), "skipped": "insufficient data"}
    ic, ic_p = stats.spearmanr(x, ya)
    try:
        q = pd.qcut(x, N_DECILES, labels=False, duplicates="drop")
    except ValueError:
        return {"n": int(x.size), "skipped": "cannot decile"}
    nq = int(np.nanmax(q)) + 1
    top, bot = q == nq - 1, q == 0
    # Signed long/short spread: long the top decile, short the bottom.
    spread_usd = float(yu[top].mean() - yu[bot].mean())
    spread_atr = float(ya[top].mean() - ya[bot].mean())
    combined = np.concatenate([yu[top].to_numpy(), -yu[bot].to_numpy()])
    t = _nw_tstat(combined, lags=max(horizon * 2, 2))
    means = [float(yu[q == i].mean()) for i in range(nq)]
    rho_mono = float(stats.spearmanr(np.arange(nq), means).statistic)
    return {
        "n": int(x.size), "ic": float(ic), "ic_p": float(ic_p),
        "spread_usd_per_oz": spread_usd, "spread_atr": spread_atr,
        "nw_t": t, "monotonicity": rho_mono,
        "net_usd_per_oz": spread_usd - ROUND_TRIP_COST,
        "pays_costs": bool(abs(spread_usd) > ROUND_TRIP_COST),
        "decile_means_usd": means,
    }


def bh_fdr(pvals: list[float], alpha: float = 0.05) -> list[bool]:
    """Benjamini-Hochberg. Returns which hypotheses are rejected."""
    p = np.asarray(pvals, float)
    ok = np.isfinite(p)
    out = np.zeros(p.size, bool)
    idx = np.flatnonzero(ok)
    if idx.size == 0:
        return out.tolist()
    order = idx[np.argsort(p[idx])]
    m = order.size
    thresh = alpha * (np.arange(1, m + 1) / m)
    passed = p[order] <= thresh
    if passed.any():
        kmax = np.flatnonzero(passed).max()
        out[order[:kmax + 1]] = True
    return out.tolist()


def run_tf(tf: str) -> list[dict]:
    df = load(tf, tz="server_eet", with_volume=True)
    feats, atr = build_features(df)
    rows = []
    for h in HORIZONS:
        usd, in_atr = forward_return(df, atr, h)
        for name in feats.columns:
            r = screen_one(feats[name], usd, in_atr, h)
            r.update({"timeframe": tf, "feature": name, "horizon": h})
            rows.append(r)
        print(f"  [{tf}] horizon {h} done ({len(feats.columns)} features)", flush=True)
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tf", choices=TIMEFRAMES)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    tfs = TIMEFRAMES if args.all else [args.tf]

    rows: list[dict] = []
    for tf in tfs:
        rows.extend(run_tf(tf))

    live = [r for r in rows if "skipped" not in r]
    rej = bh_fdr([r["ic_p"] for r in live])
    for r, k in zip(live, rej):
        r["fdr_significant"] = bool(k)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df_out = pd.DataFrame(rows)
    df_out.to_csv(OUT_DIR / "feature_screen.csv", index=False)
    (OUT_DIR / "feature_screen.json").write_text(json.dumps({
        "cost_round_trip_usd_per_oz": ROUND_TRIP_COST,
        "n_tests": len(live), "n_fdr_significant": int(sum(rej)),
        "n_paying_costs": int(sum(1 for r in live if r["pays_costs"])),
        "horizons": HORIZONS, "timeframes": tfs,
        "rows": rows}, indent=2, default=float))

    print(f"\n{len(live)} tests, {sum(rej)} significant after BH-FDR, "
          f"{sum(1 for r in live if r['pays_costs'])} with a decile spread "
          f"above the ${ROUND_TRIP_COST:.2f} round trip")
    top = sorted((r for r in live if r["pays_costs"]),
                 key=lambda r: -abs(r["spread_usd_per_oz"]))[:20]
    if top:
        print(f"\n{'tf':<4}{'feature':<18}{'h':>3}{'IC':>8}{'spread$':>10}"
              f"{'net$':>9}{'NW t':>8}{'mono':>7}  FDR")
        for r in top:
            print(f"{r['timeframe']:<4}{r['feature']:<18}{r['horizon']:>3}"
                  f"{r['ic']:>8.4f}{r['spread_usd_per_oz']:>10.3f}"
                  f"{r['net_usd_per_oz']:>9.3f}{r['nw_t']:>8.2f}"
                  f"{r['monotonicity']:>7.2f}  {r['fdr_significant']}")
    else:
        print("\nNO feature has a decile spread exceeding the round-trip cost.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
