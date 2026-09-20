"""Phase 2 — `signal_edge` across the FX majors, with a pooled null.

A single-instrument E-Ratio answers "did this entry show forward asymmetry on
this series". The panel answers the question that actually matters before
building anything: **does the entry show asymmetry as a mechanism, or did one
instrument happen to cooperate.** Seven one-instrument tests do not answer it —
run seven, take the best, and the selection has already eaten the significance
(the lesson of seq=49 and seq=68, stated there about sweep cells and true here
about instruments).

So the statistic is pooled, and the null is pooled the same way.

**Pooling the excursions, not the ratios.** E-Ratio is a ratio of means, and a
mean of ratios is not the ratio of means — averaging seven E-Ratios would
weight a 40-signal instrument like a 4,000-signal one. The pooled E-Ratio here
is ``sum(norm_mfe) / sum(norm_mae)`` over every signal on every instrument.
That is legitimate *because the excursions are ATR-normalised*: a 0.7-ATR
favourable excursion means the same thing on NZDUSD as on EURUSD, which is the
entire reason the normaliser is in the metric.

**The null matches realised counts per instrument.** For each instrument the
null draws exactly as many random entries as that instrument produced signals,
from its own regime-filtered eligible pool, and pools them identically. Both
halves are load-bearing. Drawing a flat count across instruments would let the
long-history instruments dominate the null but not the observed statistic;
drawing from the unfiltered universe would compare a regime-filtered entry
against an unfiltered null and credit the regime filter's drift to the entry
(seq=34's finding, and the reason ``eligible_pool`` exists).

**Attribution is per instrument and is not decoration.** "Dead everywhere" and
"dead on average" are different verdicts, and only the first confirms a
mechanism is dead. Each instrument reports its own E-Ratio, signal count and
decidability, so a pooled result can be read against its parts.

Data
----
The majors have no native H4, and `flood_tide_h1` needs one for its EMA(200)
trend filter. H4 is therefore resampled from H1. That is not assumed to be
faithful: XAUUSD has both natively, and resampling its H1 reproduces
**32,876 of 32,960 native H4 bars with a 100% exact match on open, high, low
and close** (the remainder are partial bars at the ends). The check is
:func:`validate_resampling` and a test runs it.

Histories are very unequal — EURUSD has 80,000 H1 bars from 2013, NZDUSD has
10,000 from 2025. That is reported rather than equalised: truncating everything
to the shortest would discard twelve years to make a table look tidy, and
MinTRL is the honest way to say when a sample cannot decide.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from research.pre.signal_edge import _excursions, wilder_atr
from research.pre.signals.flood_tide import FloodTideParams, generate_signals

__all__ = [
    "MAJORS",
    "InstrumentEdge",
    "PanelEdgeReport",
    "check_panel",
    "log_panel_edge",
    "resample_h4",
    "validate_resampling",
]

#: The seven FX majors, as D5 defines the panel. XAUUSD is deliberately absent:
#: Phase 2's acceptance is harness validation on FX, and gold's non-zero SR*
#: is a Phase 2b question (spec R5).
MAJORS = ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD")

#: Forward windows, in bars, matching the seq=31 run this is re-testing.
HORIZONS = (20, 50, 100)
ATR_PERIOD = 14
RANDOM_SEED = 42
N_PERMUTATIONS = 1000

#: Below this a per-instrument E-Ratio is reported but not read as evidence.
#: `signal_edge` warns at the same threshold.
MIN_SIGNALS_TO_DECIDE = 30


def resample_h4(h1: pd.DataFrame) -> pd.DataFrame:
    """Aggregate H1 bars into H4. Exact, not approximate — see module docstring."""
    out = h1.resample("4h").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last"})
    return out.dropna()


def validate_resampling(h1: pd.DataFrame, native_h4: pd.DataFrame) -> dict:
    """Compare resampled H4 against a native H4 series, where one exists."""
    r = resample_h4(h1)
    common = r.index.intersection(native_h4.index)
    if len(common) == 0:
        return {"common_bars": 0, "exact_match_rate": {}}
    a, b = r.loc[common], native_h4.loc[common]
    return {
        "common_bars": int(len(common)),
        "native_bars": int(len(native_h4)),
        "exact_match_rate": {c: float((a[c] == b[c]).mean())
                             for c in ("open", "high", "low", "close")},
    }


@dataclass
class InstrumentEdge:
    """One instrument's contribution, kept whole so the pool can be read
    against its parts rather than trusted."""

    symbol: str
    n_bars: int
    start: str
    end: str
    n_signals: int
    e_ratio: dict[int, float]
    sum_mfe: dict[int, float]
    sum_mae: dict[int, float]
    eligible_bars: int

    @property
    def decidable(self) -> bool:
        return self.n_signals >= MIN_SIGNALS_TO_DECIDE


@dataclass
class PanelEdgeReport:
    instruments: list[InstrumentEdge] = field(default_factory=list)
    pooled_e_ratio: dict[int, float] = field(default_factory=dict)
    pooled_p_value: dict[int, float] = field(default_factory=dict)
    null_mean: dict[int, float] = field(default_factory=dict)
    n_permutations: int = N_PERMUTATIONS
    resampling_check: dict = field(default_factory=dict)

    @property
    def decidable(self) -> list[InstrumentEdge]:
        return [i for i in self.instruments if i.decidable]

    def alive_anywhere(self, threshold: float = 1.15) -> list[str]:
        """Instruments whose own E-Ratio clears the gate at any horizon.

        The gate is the repo's usual breakout threshold. "Dead everywhere"
        means this list is empty across the decidable instruments — which is a
        stronger and more useful claim than a pooled number alone.
        """
        return [i.symbol for i in self.decidable
                if any(v >= threshold for v in i.e_ratio.values())]

    def as_dict(self) -> dict:
        return {
            "mechanism": "flood_tide_h1",
            "panel": list(MAJORS),
            "horizons": list(HORIZONS),
            "n_permutations": self.n_permutations,
            "pooled_e_ratio": self.pooled_e_ratio,
            "pooled_p_value": self.pooled_p_value,
            "null_mean": self.null_mean,
            "alive_anywhere": self.alive_anywhere(),
            "resampling_check": self.resampling_check,
            "per_instrument": [
                {"symbol": i.symbol, "n_bars": i.n_bars, "start": i.start,
                 "end": i.end, "n_signals": i.n_signals,
                 "eligible_bars": i.eligible_bars,
                 "decidable": i.decidable, "e_ratio": i.e_ratio}
                for i in self.instruments
            ],
        }


def _forward_arrays(ohlc: pd.DataFrame):
    return (ohlc["open"].to_numpy(float), ohlc["high"].to_numpy(float),
            ohlc["low"].to_numpy(float), ohlc["close"].to_numpy(float))


def _instrument_excursions(ohlc: pd.DataFrame, signal_idx: np.ndarray,
                           window: int, atr: np.ndarray):
    """Normalised MFE/MAE for a set of entry bars at one horizon."""
    open_, high, low, close = _forward_arrays(ohlc)
    n = len(close)
    keep = signal_idx[signal_idx <= n - window - 1]
    if keep.size == 0:
        return np.array([]), np.array([])
    dirs = np.ones(keep.size, dtype=np.int64)
    fwd_high = np.array([high[i + 1: i + 1 + window].max() for i in keep])
    fwd_low = np.array([low[i + 1: i + 1 + window].min() for i in keep])
    fwd_close = np.array([close[i + window] for i in keep])
    mfe, mae, _ = _excursions(keep, dirs, open_, fwd_high, fwd_low,
                              fwd_close, atr)
    finite = np.isfinite(mfe) & np.isfinite(mae)
    return mfe[finite], mae[finite]


def check_panel(data_dir: Optional[Path] = None,
                params: FloodTideParams = FloodTideParams(),
                n_permutations: int = N_PERMUTATIONS,
                symbols: tuple[str, ...] = MAJORS) -> PanelEdgeReport:
    """Run the mechanism across the panel and test the pooled statistic."""
    from research.pre.scripts.run_flood_tide_edge import load_ohlcv

    data_dir = Path(data_dir) if data_dir else _default_data_dir()
    rng = np.random.default_rng(RANDOM_SEED)
    report = PanelEdgeReport(n_permutations=n_permutations)

    observed: dict[int, list] = {h: [[], []] for h in HORIZONS}
    pools: list[tuple[np.ndarray, np.ndarray, pd.DataFrame, np.ndarray, int]] = []

    for sym in symbols:
        h1 = load_ohlcv(data_dir / f"{sym}_H1.csv")
        h4 = resample_h4(h1)
        sig = generate_signals(h1, h4, params)

        entries = np.flatnonzero(sig["entry_signal"].to_numpy())
        atr = wilder_atr(h1["high"], h1["low"], h1["close"],
                         ATR_PERIOD).to_numpy(float)
        eligible = np.flatnonzero(
            (sig["regime_ok"] & sig["upper_entry"].notna()).to_numpy()
            & np.isfinite(atr))

        e_ratio, s_mfe, s_mae = {}, {}, {}
        for h in HORIZONS:
            mfe, mae = _instrument_excursions(h1, entries, h, atr)
            s_mfe[h] = float(mfe.sum())
            s_mae[h] = float(mae.sum())
            e_ratio[h] = float(mfe.sum() / mae.sum()) if mae.sum() else float("nan")
            observed[h][0].append(mfe.sum())
            observed[h][1].append(mae.sum())

        report.instruments.append(InstrumentEdge(
            symbol=sym, n_bars=len(h1), start=str(h1.index[0].date()),
            end=str(h1.index[-1].date()), n_signals=int(entries.size),
            e_ratio=e_ratio, sum_mfe=s_mfe, sum_mae=s_mae,
            eligible_bars=int(eligible.size)))
        pools.append((entries, eligible, h1, atr, int(entries.size)))

    for h in HORIZONS:
        num, den = sum(observed[h][0]), sum(observed[h][1])
        report.pooled_e_ratio[h] = float(num / den) if den else float("nan")

    # -- the pooled null ---------------------------------------------------
    null = {h: [] for h in HORIZONS}
    for _ in range(n_permutations):
        acc = {h: [0.0, 0.0] for h in HORIZONS}
        for entries, eligible, h1, atr, n_sig in pools:
            if n_sig == 0 or eligible.size == 0:
                continue
            draw = rng.choice(eligible, size=min(n_sig, eligible.size),
                              replace=False)
            for h in HORIZONS:
                mfe, mae = _instrument_excursions(h1, draw, h, atr)
                acc[h][0] += mfe.sum()
                acc[h][1] += mae.sum()
        for h in HORIZONS:
            null[h].append(acc[h][0] / acc[h][1] if acc[h][1] else np.nan)

    for h in HORIZONS:
        arr = np.asarray(null[h], dtype=float)
        arr = arr[np.isfinite(arr)]
        obs = report.pooled_e_ratio[h]
        report.null_mean[h] = float(arr.mean()) if arr.size else float("nan")
        report.pooled_p_value[h] = (
            float((arr >= obs).mean()) if arr.size and np.isfinite(obs)
            else float("nan"))

    return report


def _default_data_dir() -> Path:
    import os
    from research import data_manifest
    return Path(os.environ.get("QH_DATA_DIR", data_manifest.DATA_DIR))


def log_panel_edge(report: PanelEdgeReport, log_dir: Optional[Path] = None):
    """Record the panel run. Not a trial: it re-tests a falsified mechanism."""
    from research import log as research_log

    alive = report.alive_anywhere()
    kwargs = {"log_dir": log_dir} if log_dir is not None else {}
    return research_log.append_record(
        research_log.EventType.AUDIT,
        record_id="record:phase2-panel-flood-tide",
        title=("Phase 2 panel harness — flood_tide_h1 across the FX majors, "
               "pooled null"),
        note=(
            "Phase 2 acceptance: re-run an already-falsified mechanism across "
            "the panel. The pooled E-Ratio pools excursions rather than "
            "averaging per-instrument ratios, and the null draws each "
            "instrument's realised signal count from its own regime-filtered "
            "eligible pool. "
            f"Instruments alive at their own gate: {alive or 'none'}. "
            "Not a trial: flood_tide_h1 was shelved at seq=34 and this "
            "re-tests it rather than proposing it."
        ),
        metrics={
            "panel": list(MAJORS),
            "pooled_e_ratio": report.pooled_e_ratio,
            "pooled_p_value": report.pooled_p_value,
            "null_mean": report.null_mean,
            "n_permutations": report.n_permutations,
            "alive_anywhere": alive,
            "decidable_instruments": [i.symbol for i in report.decidable],
            "per_instrument_e_ratio": {i.symbol: i.e_ratio
                                       for i in report.instruments},
            "per_instrument_n_signals": {i.symbol: i.n_signals
                                         for i in report.instruments},
        },
        **kwargs,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--permutations", type=int, default=N_PERMUTATIONS)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--log", action="store_true")
    args = ap.parse_args()

    report = check_panel(args.data_dir, n_permutations=args.permutations)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2, default=float))
    else:
        print(f"Phase 2 panel — flood_tide_h1 over {len(MAJORS)} FX majors")
        print(f"{'symbol':8s} {'bars':>7s} {'signals':>8s} {'dec':>4s}  "
              + "  ".join(f"E(h={h})" for h in HORIZONS))
        for i in report.instruments:
            es = "  ".join(f"{i.e_ratio[h]:7.3f}" for h in HORIZONS)
            print(f"{i.symbol:8s} {i.n_bars:7,d} {i.n_signals:8d} "
                  f"{'yes' if i.decidable else 'NO':>4s}  {es}")
        print()
        for h in HORIZONS:
            print(f"  pooled h={h:<4d} E={report.pooled_e_ratio[h]:.4f}  "
                  f"null={report.null_mean[h]:.4f}  "
                  f"p={report.pooled_p_value[h]:.4f}")
        print(f"\n  alive at their own gate: {report.alive_anywhere() or 'none'}")
    if args.log:
        entry = log_panel_edge(report)
        print(f"logged seq={entry.seq}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
