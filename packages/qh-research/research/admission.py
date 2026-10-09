"""Admission check — what a series must pass before it enters a universe.

US500_H1.csv opened with 897 daily bars and was read as hourly by two results
before anyone noticed (seq=128). GER40_H1.csv, pulled the same way, opens with
monthly bars. Both looked like ordinary files. So this is a standing gate, run
on every instrument before it joins any universe, not a one-off catch.

It checks **integrity only**: is the file the timeframe it claims, from where,
and where is it missing. It never reads a return, a correlation or anything a
mechanism could be judged on — that boundary is what makes it safe to run
before a universe is declared rather than after.

Checks, each a refusal reason when it fails:

``shape``
    Strictly increasing unique timestamps; high and low bracket open and close;
    every price positive.
``off_grid``
    Every bar opens on the timeframe's grid (minute 0 for H1).
``timeframe``
    The commonest spacing between consecutive bars equals the declared one.
``conforming``
    Where the series is the declared timeframe. A day *conforms* when the
    median spacing between its own bars equals the timeframe, so a holiday
    half-day still conforms and a day of H4 or daily bars does not. The series
    is admitted from the day after its last run of at least five
    non-conforming days. Bar counts alone miss this: GER40_H1.csv holds monthly
    bars, then daily, then six bars a day — H4 — from 2015-02 to mid-2018, and
    six a day clears a bars-per-day threshold.
``holes``
    No gap longer than :data:`HOLE_HOURS` unless declared in
    :data:`KNOWN_HOLES`. The longest holiday closure in the candidate files is
    131 hours (GER40, Christmas 2018); 144 sits above every one of them.

A coarse stretch is not a refusal: the verdict is ``ADMIT_FROM`` with the
first conforming date, and a caller must start there. Every other check runs
on the admitted range only.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from research import data_manifest as dm
from research.post.sweeps.data import KNOWN_GAPS

#: A gap longer than this is a hole in the data, not a market closure.
HOLE_HOURS = 144.0

#: Holes that are known, sourced and accepted. Anything else refuses.
KNOWN_HOLES: dict[str, list[tuple[str, str]]] = {
    # Broker-history holes documented in research.engines.btpy_runner.
    "XAUUSD": list(KNOWN_GAPS),
}

#: A run of non-conforming days this long moves the admitted start past it.
NONCONFORMING_MIN_DAYS = dm.SPARSE_PREFIX_MIN_DAYS

ADMIT = "ADMIT"
ADMIT_FROM = "ADMIT_FROM"
REFUSE = "REFUSE"


class AdmissionRefused(ValueError):
    """A series failed the admission check and may not enter a universe."""


@dataclass
class Admission:
    symbol: str
    timeframe: str
    verdict: str
    admit_from: str
    reasons: list[str] = field(default_factory=list)
    census: dict = field(default_factory=dict)


def _shape_problems(df: pd.DataFrame) -> list[str]:
    out = []
    if not df.index.is_monotonic_increasing or df.index.has_duplicates:
        out.append("timestamps not strictly increasing")
    body_hi = df[["open", "close"]].max(axis=1)
    body_lo = df[["open", "close"]].min(axis=1)
    n_bad = int(((df.high < body_hi) | (df.low > body_lo)).sum())
    if n_bad:
        out.append(f"{n_bad} bars where high/low do not bracket open/close")
    n_nonpos = int((df[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())
    if n_nonpos:
        out.append(f"{n_nonpos} bars with a non-positive price")
    return out


def conforming_start(index: pd.DatetimeIndex, tf_hours: float) -> tuple[pd.Timestamp, int]:
    """First bar after the last run of non-conforming days, and how many runs.

    A day conforms when the median spacing between its bars is the timeframe.
    A one-bar day has no spacing and does not conform.
    """
    if tf_hours >= 24:
        return index[0], 0
    s = index.to_series()
    days = index.normalize()
    spacing = s.diff().where(days == pd.Series(days, index=index).shift()).dt.total_seconds() / 3600
    med = spacing.groupby(days).median()
    ok = (med == tf_hours).to_numpy()
    last_bad_run_end, runs, current = None, 0, 0
    for i, flag in enumerate(ok):
        current = 0 if flag else current + 1
        if current == NONCONFORMING_MIN_DAYS:
            runs += 1
        if current >= NONCONFORMING_MIN_DAYS:
            last_bad_run_end = i
    if last_bad_run_end is None or last_bad_run_end + 1 >= len(med):
        return (index[0] if last_bad_run_end is None else index[-1]), runs
    first_day = med.index[last_bad_run_end + 1]
    return index[days >= first_day][0], runs


def _declared(symbol: str, before: pd.Timestamp, after: pd.Timestamp) -> bool:
    slack = pd.Timedelta(days=1)
    for start, end in KNOWN_HOLES.get(symbol, []):
        lo = pd.Timestamp(start, tz=before.tz) - slack
        hi = pd.Timestamp(end, tz=before.tz) + slack
        if before >= lo and after <= hi:
            return True
    return False


def admit_frame(symbol: str, timeframe: str, df: pd.DataFrame) -> Admission:
    """Run every check on an already-loaded frame."""
    tf_hours = dm.TIMEFRAME_HOURS[timeframe]
    reasons = _shape_problems(df)
    start, coarse_runs = conforming_start(df.index, tf_hours)
    dense = df[df.index >= start]

    step = pd.Timedelta(hours=tf_hours)
    off_grid = int(((dense.index - dense.index.normalize()) % step != pd.Timedelta(0)).sum())
    if off_grid:
        reasons.append(f"{off_grid} bars off the {timeframe} grid")

    gaps = dense.index.to_series().diff().dropna()
    modal_hours = gaps.mode().iloc[0].total_seconds() / 3600 if len(gaps) else None
    if modal_hours != tf_hours:
        reasons.append(f"commonest spacing is {modal_hours}h, not {tf_hours}h")

    holes, declared = [], []
    gap_hours = gaps.dt.total_seconds() / 3600
    for after, h in gap_hours[gap_hours > HOLE_HOURS].items():
        before = after - pd.Timedelta(hours=h)
        rec = {"from": str(before), "to": str(after), "hours": round(float(h), 1)}
        (declared if _declared(symbol, before, after) else holes).append(rec)
    if holes:
        reasons.append(f"{len(holes)} undeclared holes over {HOLE_HOURS:.0f}h")

    prefix = int((df.index < start).sum())
    if reasons:
        verdict = REFUSE
    elif prefix:
        verdict = ADMIT_FROM
    else:
        verdict = ADMIT
    census = {
        "n_bars": int(len(df)), "n_dense": int(len(dense)),
        "first_bar": str(df.index[0]), "last_bar": str(df.index[-1]),
        "bars_before_admitted": prefix,
        "nonconforming_runs": coarse_runs,
        "manifest_sparse_prefix_bars": int((df.index < dm.dense_start(df.index, tf_hours)).sum()),
        "modal_spacing_hours": modal_hours,
        "gaps_by_hours": {
            "1_step": int((gap_hours == tf_hours).sum()),
            "within_day": int(((gap_hours > tf_hours) & (gap_hours <= 24)).sum()),
            "over_day_to_weekend": int(((gap_hours > 24) & (gap_hours <= 72)).sum()),
            "long_weekend_or_holiday": int(((gap_hours > 72) & (gap_hours <= HOLE_HOURS)).sum()),
            "holes": int((gap_hours > HOLE_HOURS).sum()),
        },
        "undeclared_holes": holes, "declared_holes": declared,
    }
    return Admission(symbol, timeframe, verdict, str(start), reasons, census)


def admit(symbol: str, timeframe: str = "H1",
          data_dir: Path | None = None) -> Admission:
    path = Path(data_dir or dm.DATA_DIR) / f"{symbol}_{timeframe}.csv"
    return admit_frame(symbol, timeframe, dm.load_ohlcv(path))


def require(symbol: str, timeframe: str = "H1",
            data_dir: Path | None = None) -> pd.Timestamp:
    """Raise unless admitted; return the first bar a caller may use."""
    a = admit(symbol, timeframe, data_dir)
    if a.verdict == REFUSE:
        raise AdmissionRefused(f"{symbol}_{timeframe}: " + "; ".join(a.reasons))
    return pd.Timestamp(a.admit_from)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("symbols", nargs="+")
    ap.add_argument("--timeframe", default="H1")
    ap.add_argument("--out", type=Path, default=None,
                    help="write the admissions as one JSON artifact")
    a = ap.parse_args()
    results = [admit(s, a.timeframe) for s in a.symbols]
    for r in results:
        print(f"{r.symbol:8s} {r.verdict:10s} from {r.admit_from[:10]}  "
              f"{'; '.join(r.reasons) or 'ok'}")
    if a.out:
        a.out.write_text(json.dumps({
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "data_dir": str(dm.DATA_DIR), "hole_hours": HOLE_HOURS,
            "admissions": [asdict(r) for r in results]}, indent=2) + "\n")
    return 0 if all(r.verdict != REFUSE for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
