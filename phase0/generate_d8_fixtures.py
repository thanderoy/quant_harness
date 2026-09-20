"""D8 — generate golden fixtures from the current WMPS code.

Phase 0 task D8. These fixtures are the contract the rebuilt numerical code must
satisfy (T11 / X22). They pin *numerical* behaviour only; symbol-agnostic
behaviour is a Phase 1 concern and is not covered here.

Generated once, committed, and never regenerated except under the WMPS-freeze
mirror rule (spec 1.3).

Run:
    python3 phase0/generate_d8_fixtures.py

Reads WMPS at the path below; writes CSVs plus a manifest recording the WMPS
commit SHA and a sha256 of every source file the fixtures depend on.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

WMPS = Path.home() / "Local" / "wine-mt5-python-setup"
STRATEGIES = WMPS / "backend" / "trading" / "app" / "quant" / "strategies"
# Phase 0.5 acceptance places the golden fixtures inside the package whose
# tests consume them, not beside the generator. Keeping a second copy under
# phase0/ would mean two sources of truth for a file whose whole purpose is to
# be the single pinned reference.
OUT = (Path(__file__).resolve().parents[1] / "packages" / "qh-resources"
       / "tests" / "fixtures")

sys.path.insert(0, str(STRATEGIES))

from drawdown_guard import DrawdownGuard, PeakStore  # noqa: E402
from indicators import atr, hma, stochastic, wma  # noqa: E402
from sizer import calculate_lot_size  # noqa: E402

# Sample window: fixed and deterministic. 6,000 H1 bars from 2024-01-01
# spans ~35 weekends and the New Year / Easter / Christmas holiday gaps,
# comfortably clearing the spec's ">=5,000 bars, >=4 weekend boundaries,
# >=1 holiday" requirement.
SAMPLE_START = "2024-01-01T00:00:00+00:00"
SAMPLE_BARS = 6_000

WMA_PERIODS = (9, 20, 55)
HMA_PERIODS = (21, 55)
STOCH_PARAMS = (14, 3, 3)
ATR_PERIOD = 14


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_sha(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def git_is_dirty(repo: Path, rel: str) -> bool:
    out = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain", rel],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return bool(out)


def load_ohlcv(path: Path) -> pd.DataFrame:
    """House ``;``-separated OHLCV loader — identical to the one used by the
    seq=31 flood_tide driver, so ohlc_hash values are comparable."""
    df = pd.read_csv(
        path, sep=";", header=0,
        names=["datetime", "open", "high", "low", "close", "volume"],
        parse_dates=["datetime"], date_format="%Y.%m.%d %H:%M",
    )
    df = df.set_index("datetime").sort_index()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df[["open", "high", "low", "close"]].astype(float)


def f64(v: float) -> str:
    """Shortest round-trip float64 representation, or empty for NaN.

    ``repr`` on a Python float is guaranteed round-trip since 3.1, so string
    equality on this output is exact float64 equality — what X22 requires
    instead of ``approx``.
    """
    return "" if (v is None or (isinstance(v, float) and np.isnan(v))) else repr(float(v))


def describe_gaps(idx: pd.DatetimeIndex) -> dict:
    """Count structural breaks so the fixture's coverage is self-evidencing."""
    deltas = idx.to_series().diff().dropna()
    hours = deltas.dt.total_seconds() / 3600.0
    weekend = int(((hours >= 40) & (hours <= 60)).sum())
    holiday = int(((hours > 2) & (hours < 40)).sum())
    return {
        "weekend_boundaries_40_60h": weekend,
        "intraweek_gaps_2_40h": holiday,
        "long_gaps_over_60h": int((hours > 60).sum()),
        "max_gap_hours": float(hours.max()),
    }


def _wma_exact(series: pd.Series, period: int) -> pd.Series:
    """WMA reduced with ``math.fsum`` instead of WMPS's ``np.dot``.

    The one place this generator deliberately departs from WMPS, added
    2026-09-20 (research log seq=102). WMPS reduces the window with
    ``np.dot``, which dispatches to BLAS, so the summation order — and the
    last bit — belongs to the kernel chosen for the running CPU and to the
    numpy build, not to the source.

    That was treated as a machine-portability problem until this generator was
    re-run on the machine that produced the original fixture, against
    byte-identical WMPS sources (all three sha256 matching the manifest) and
    byte-identical input: ``wma_20``, ``wma_55``, ``hma_21`` and ``hma_55``
    came back up to 5 ULP different, and ``wma_9`` — the column seq=98
    recorded as the CI-breaking one — came back exact. A reference that does
    not reproduce on its own machine is pinning a toolchain, not arithmetic.

    ``math.fsum`` is correctly rounded, so these columns are now fixed by
    IEEE-754 and reproduce on any conforming platform. The values sit 2-4 ULP
    from WMPS's ``np.dot`` and are the more accurate of the two; the manifest
    records the measured distance, so the deviation is auditable rather than
    silent. WMPS itself is unchanged — it is frozen under spec 1.3.
    """
    weights = np.arange(1, period + 1, dtype=float)
    weight_sum = float(weights.sum())
    return series.rolling(period).apply(
        lambda x: math.fsum(x * weights) / weight_sum, raw=True)


def _hma_exact(series: pd.Series, period: int) -> pd.Series:
    """HMA over :func:`_wma_exact`, mirroring WMPS's composition exactly."""
    half, sqrt_p = period // 2, round(math.sqrt(period))
    diff = 2.0 * _wma_exact(series, half) - _wma_exact(series, period)
    return _wma_exact(diff, sqrt_p)


def dot_product_deviation(df: pd.DataFrame) -> dict:
    """ULP distance from WMPS's own ``np.dot`` output, measured at generation.

    Recorded in the manifest so the deviation introduced by ``_wma_exact`` is
    a stated, measured number rather than a claim in a docstring.
    """
    out: dict[str, float] = {}
    for p in WMA_PERIODS:
        a = _wma_exact(df["close"], p).to_numpy()
        b = wma(df["close"], p).to_numpy()
        m = ~np.isnan(a)
        out[f"wma_{p}"] = float(
            (np.abs(a[m] - b[m]) / np.spacing(np.abs(b[m]))).max())
    for p in HMA_PERIODS:
        a = _hma_exact(df["close"], p).to_numpy()
        b = hma(df["close"], p).to_numpy()
        m = ~np.isnan(a)
        out[f"hma_{p}"] = float(
            (np.abs(a[m] - b[m]) / np.spacing(np.abs(b[m]))).max())
    return out


def gen_indicators(df: pd.DataFrame) -> dict:
    cols: dict[str, pd.Series] = {}
    for p in WMA_PERIODS:
        cols[f"wma_{p}"] = _wma_exact(df["close"], p)
    for p in HMA_PERIODS:
        cols[f"hma_{p}"] = _hma_exact(df["close"], p)
    k_p, d_p, s_k = STOCH_PARAMS
    k, d = stochastic(df["high"], df["low"], df["close"], k_p, d_p, s_k)
    cols[f"stoch_k_{k_p}_{d_p}_{s_k}"] = k
    cols[f"stoch_d_{k_p}_{d_p}_{s_k}"] = d
    cols[f"atr_{ATR_PERIOD}"] = atr(df["high"], df["low"], df["close"], ATR_PERIOD)

    out = pd.DataFrame(index=df.index)
    for name, series in cols.items():
        out[name] = series.map(f64)
    out.index.name = "datetime"

    nan_counts = {n: int(s.isna().sum()) for n, s in cols.items()}
    return {"frame": out, "nan_counts": nan_counts,
            "columns": list(cols.keys())}


def gen_sizer_grid() -> pd.DataFrame:
    """Grid over balance x ATR x risk_pct x sl_multiplier.

    Deliberately includes:
      - the LOT_SAFETY_FLOOR_ATR path (atr below 0.10)
      - the min_lot clamp (tiny balance)   -> the live risk bug T5 fixes
      - the max_lot clamp (large balance)
      - the $100 account at 2% on a realistic H1 gold ATR, which is the
        case spec 8 says must become untradeable under T5.
    """
    balances = [100.0, 500.0, 3_643.0, 10_000.0, 100_000.0]
    atrs = [0.001, 0.05, 0.10, 0.5, 5.0, 14.0, 22.0, 60.0]
    risks = [0.005, 0.02, 0.05]
    slmults = [1.0, 1.5, 3.0, 10.0]

    rows = []
    for b in balances:
        for a in atrs:
            for r in risks:
                for m in slmults:
                    lots, eff = calculate_lot_size(
                        account_balance=b, atr_value=a,
                        risk_pct=r, sl_atr_multiplier=m,
                    )
                    sl_dist = eff * m
                    realised = lots * 100.0 * sl_dist
                    rows.append({
                        "account_balance": f64(b), "atr_value": f64(a),
                        "risk_pct": f64(r), "sl_atr_multiplier": f64(m),
                        "lots": f64(lots), "effective_atr": f64(eff),
                        "sl_distance": f64(sl_dist),
                        "realised_risk_usd": f64(realised),
                        "realised_risk_pct": f64(realised / b),
                        "budget_usd": f64(b * r),
                        "over_budget": str(realised > b * r + 1e-12),
                    })
    return pd.DataFrame(rows)


class MemPeakStore(PeakStore):
    """In-memory PeakStore. The JSON store's atomic-write behaviour is a
    persistence concern, not a numerical one, and is out of D8 scope."""

    def __init__(self) -> None:
        self._peak: float | None = None

    def read(self) -> float | None:
        return self._peak

    def write(self, peak_equity: float) -> None:
        self._peak = peak_equity


def gen_drawdown_guard() -> pd.DataFrame:
    """Scripted equity sequence covering first-evaluation no-trip, peak
    advance, trip, and post-trip behaviour, at both the 8% production guard
    and a 20% research setting."""
    equities = [
        1000.0,   # first evaluation: no peak yet -> cannot trip
        1010.0,   # peak advance
        1050.0,   # peak advance
        1000.0,   # drawdown, not tripped at 8%
        966.0,    # -8.0% exactly: not < threshold, so not tripped
        965.9,    # just below threshold -> TRIP
        900.0,    # deeper, still tripped
        1050.0,   # recovery to peak: no longer tripped, peak unchanged
        1200.0,   # new peak after recovery
        1100.0,   # drawdown from the new, higher peak
    ]
    rows = []
    for max_dd in (0.08, 0.20):
        guard = DrawdownGuard(store=MemPeakStore(), max_drawdown_pct=max_dd)
        for step, eq in enumerate(equities):
            tripped = guard.is_tripped(eq)
            dd = guard.current_drawdown(eq)
            thr = guard.trigger_threshold()
            peak_before = guard.peak_equity
            guard.update(eq)
            rows.append({
                "max_drawdown_pct": f64(max_dd), "step": str(step),
                "equity": f64(eq),
                "peak_before_update": f64(peak_before) if peak_before is not None else "",
                "trigger_threshold": f64(thr) if thr is not None else "",
                "is_tripped": str(tripped),
                "current_drawdown": f64(dd),
                "peak_after_update": f64(guard.peak_equity),
            })
    return pd.DataFrame(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    src_csv = WMPS / "research" / "data" / "XAUUSD_H1.csv"
    full = load_ohlcv(src_csv)
    start = pd.Timestamp(SAMPLE_START)
    sample = full.loc[full.index >= start].iloc[:SAMPLE_BARS]
    if len(sample) < 5_000:
        raise SystemExit(f"sample too short: {len(sample)} bars")

    # The OHLCV sample is committed with the fixtures so they are
    # self-contained and do not depend on the gitignored research/data tree.
    sample_out = sample.copy()
    for c in sample_out.columns:
        sample_out[c] = sample_out[c].map(f64)
    sample_out.index.name = "datetime"
    sample_out.to_csv(OUT / "sample_xauusd_h1.csv")

    ind = gen_indicators(sample)
    deviation = dot_product_deviation(sample)
    ind["frame"].to_csv(OUT / "indicators.csv")

    sizer_df = gen_sizer_grid()
    sizer_df.to_csv(OUT / "sizer_grid.csv", index=False)

    ddg_df = gen_drawdown_guard()
    ddg_df.to_csv(OUT / "drawdown_guard.csv", index=False)

    sources = {
        "indicators.py": STRATEGIES / "indicators.py",
        "sizer.py": STRATEGIES / "sizer.py",
        "drawdown_guard.py": STRATEGIES / "drawdown_guard.py",
    }
    manifest = {
        "task": "D8",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "generator": "phase0/generate_d8_fixtures.py",
        "wmps_repo": str(WMPS),
        "wmps_commit_sha": git_sha(WMPS),
        "wmps_repo_dirty": git_is_dirty(WMPS, "."),
        "source_files_clean_at_head": {
            name: not git_is_dirty(WMPS, str(p.relative_to(WMPS)))
            for name, p in sources.items()
        },
        "source_sha256": {name: sha256_file(p) for name, p in sources.items()},
        "sample": {
            "source_csv": str(src_csv.relative_to(WMPS)),
            "source_csv_sha256": sha256_file(src_csv),
            "source_csv_gitignored": True,
            "start": str(sample.index[0]),
            "end": str(sample.index[-1]),
            "n_bars": int(len(sample)),
            "ohlc_hash_sha16": hashlib.sha256(
                sample.to_csv().encode("utf-8")
            ).hexdigest()[:16],
            "gaps": describe_gaps(sample.index),
        },
        "indicators": {
            "columns": ind["columns"],
            "nan_counts": ind["nan_counts"],
            "wma_periods": list(WMA_PERIODS),
            "hma_periods": list(HMA_PERIODS),
            "stoch_params": {"k_period": STOCH_PARAMS[0],
                             "d_period": STOCH_PARAMS[1],
                             "smooth_k": STOCH_PARAMS[2]},
            "atr_period": ATR_PERIOD,
            "reduction": "math.fsum (correctly rounded)",
            "reduction_note": (
                "wma/hma are reduced with math.fsum, not WMPS's np.dot. "
                "np.dot dispatches to BLAS, so its summation order comes "
                "from the CPU kernel and numpy build; re-running this "
                "generator on the SAME machine against byte-identical "
                "sources reproduced four of the five columns only to 5 ULP. "
                "fsum is correctly rounded, so these columns are fixed by "
                "IEEE-754 and reproduce anywhere. See seq=102."),
            "deviates_from_wmps": True,
            "deviation_ulp_vs_wmps_np_dot": deviation,
            "exactly_reproducible_columns": "all",
        },
        "sizer_grid": {
            "n_rows": int(len(sizer_df)),
            "n_over_budget": int((sizer_df["over_budget"] == "True").sum()),
        },
        "drawdown_guard": {"n_rows": int(len(ddg_df))},
        "float_encoding": "repr(float) — shortest round-trip float64; "
                          "string equality is exact float64 equality",
        "scope_note": "Pins numerical behaviour only. Symbol-agnostic "
                      "behaviour is a Phase 1 concern (spec D8 note).",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
