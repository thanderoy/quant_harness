"""Can a daily-horizon trend test across the panel be decided at all?

Implements the rule pre-declared at seq=150, before any daily history was
pulled. It reads bar dates and raw daily returns only: no signal, no
strategy return, no outcome. Its job is to say whether registering a
low-turnover trend trial is worth a trial at all.

**The rule.**

* Prior: a per-instrument trend Sharpe of :data:`PRIOR_SR` (annualised),
  fixed at seq=150 before the floor was computed.
* Pooling: ``SR_pooled = PRIOR_SR * sqrt(N_eff)``,
  ``N_eff = N / (1 + (N - 1) * rho_bar)``, where ``rho_bar`` is the mean
  absolute correlation of raw daily log returns over the common window.
  Raw-return correlation stands in for strategy-return correlation, which
  is conservative.
* Floor: ``min_decidable_sharpe(n_obs, sr_star=0, alpha=0.05) * sqrt(252)``
  over the common window's days.
* Window: instruments ordered by admitted daily history, longest first; for
  each k the window is the common span of the top k. ``k*`` maximises
  ``prior_pooled(k) - floor(k)``.
* Clearable iff ``prior_pooled(k*) >= floor(k*)``.

The cross-check compares native D1 bars against H1 resampled by server date
over their overlap, as declared: native D1 is used only if they agree.

    python -m research.pre.daily_panel_power --d1-dir DIR --h1-dir DIR
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from research import admission
from research.post.mintrl import min_decidable_sharpe
from research.pre.activity_reversal import load_h1
from research.pre.panel_edge import PANEL_2B

PRIOR_SR = 0.25
DAYS_PER_YEAR = 252
DECLARED_AT_SEQ = 150
#: Daily returns differing by more than this count as disagreeing (1 bp).
AGREE_BP = 1.0
#: Native D1 is "in agreement" with resampled H1 when both hold.
AGREE_MIN_CORR = 0.99
AGREE_MAX_SHARE = 0.05


def admitted_d1(symbol: str, d1_dir: Path) -> pd.DataFrame:
    """The admitted part of a native daily series."""
    start = admission.require(symbol, "D1", d1_dir)
    df = load_h1(d1_dir / f"{symbol}_D1.csv")
    return df[df.index >= start]


def log_returns(df: pd.DataFrame) -> pd.Series:
    return np.log(df["close"]).diff().dropna()


def n_eff(n: int, rho_bar: float) -> float:
    return n / (1 + (n - 1) * rho_bar)


def prior_pooled(n: int, rho_bar: float, prior: float = PRIOR_SR) -> float:
    return prior * float(np.sqrt(n_eff(n, rho_bar)))


def floor(n_days: int) -> float:
    """Smallest annualised Sharpe ``n_days`` daily observations can decide."""
    return float(min_decidable_sharpe(n_obs=n_days, sr_star=0.0)) * float(np.sqrt(DAYS_PER_YEAR))


def mean_abs_corr(returns: pd.DataFrame) -> float:
    c = returns.corr().abs().to_numpy()
    k = c.shape[0]
    if k < 2:
        return 0.0
    return float((c.sum() - k) / (k * (k - 1)))


@dataclass
class Row:
    k: int
    instruments: list
    start: str
    end: str
    years: float
    n_days: int
    rho_bar: float
    n_eff: float
    prior_pooled: float
    floor: float
    margin: float


def plan(series: dict[str, pd.DataFrame]) -> dict:
    """The declared rule over every k. Reads dates and raw returns only."""
    order = sorted(series, key=lambda s: series[s].index[0])
    rets = {s: log_returns(series[s]) for s in order}
    rows = []
    for k in range(1, len(order) + 1):
        top = order[:k]
        frame = pd.concat({s: rets[s] for s in top}, axis=1, join="inner").dropna()
        if len(frame) < 2:
            continue
        rho = mean_abs_corr(frame)
        pp, fl = prior_pooled(k, rho), floor(len(frame))
        rows.append(Row(k, top, str(frame.index[0].date()), str(frame.index[-1].date()),
                        round((frame.index[-1] - frame.index[0]).days / 365.25, 2),
                        len(frame), round(rho, 4), round(n_eff(k, rho), 3),
                        round(pp, 4), round(fl, 4), round(pp - fl, 4)))
    best = max(rows, key=lambda r: r.margin)
    return {"declared_at_seq": DECLARED_AT_SEQ, "prior_sr_instrument": PRIOR_SR,
            "rows": [asdict(r) for r in rows], "k_star": best.k,
            "clearable": best.margin >= 0, "best": asdict(best)}


def resample_daily(h1: pd.DataFrame) -> pd.Series:
    """Last H1 close of each server date."""
    return h1["close"].groupby(h1.index.tz_localize(None).normalize()).last()


def cross_check(d1: pd.DataFrame, h1: pd.DataFrame) -> dict:
    """Native D1 against resampled H1 over their overlap."""
    native = d1["close"].copy()
    native.index = native.index.tz_localize(None).normalize()
    both = pd.concat({"native": native, "resampled": resample_daily(h1)}, axis=1, join="inner").dropna()
    r = np.log(both).diff().dropna()
    if len(r) < 20:
        return {"n_days": int(len(r)), "agree": False, "reason": "overlap too short"}
    diff_bp = (r["native"] - r["resampled"]).abs() * 1e4
    corr = float(r["native"].corr(r["resampled"]))
    share = float((diff_bp > AGREE_BP).mean())
    return {"n_days": int(len(r)), "from": str(r.index[0].date()), "to": str(r.index[-1].date()),
            "corr": round(corr, 6), "max_abs_diff_bp": round(float(diff_bp.max()), 3),
            "share_days_over_1bp": round(share, 4),
            "agree": corr >= AGREE_MIN_CORR and share <= AGREE_MAX_SHARE}


def run(d1_dir: Path, h1_dir: Optional[Path], symbols: tuple[str, ...] = PANEL_2B) -> dict:
    series, admissions, checks = {}, {}, {}
    for s in symbols:
        try:
            series[s] = admitted_d1(s, d1_dir)
            admissions[s] = {"admitted_from": str(series[s].index[0].date()),
                             "last": str(series[s].index[-1].date()), "n_bars": len(series[s])}
        except (admission.AdmissionRefused, FileNotFoundError) as exc:
            admissions[s] = {"refused": str(exc)}
            continue
        if h1_dir is not None and (h1_dir / f"{s}_H1.csv").exists():
            checks[s] = cross_check(series[s], load_h1(h1_dir / f"{s}_H1.csv"))
    out = {"admissions": admissions, "cross_check": checks}
    disagree = [s for s, c in checks.items() if not c["agree"]]
    out["cross_check_disagrees"] = disagree
    out["power"] = plan(series) if len(series) >= 2 else None
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--d1-dir", type=Path, required=True)
    ap.add_argument("--h1-dir", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    res = run(args.d1_dir, args.h1_dir)
    text = json.dumps(res, indent=1)
    if args.out:
        args.out.write_text(text + "\n")
    p = res["power"]
    print(text if p is None else
          f"k*={p['k_star']} clearable={p['clearable']} best={json.dumps(p['best'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
