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
:func:`validate_resampling`; ``tests/test_panel_edge_resampling.py`` pins
those numbers, and :func:`check_panel` runs the check so the evidence travels
on the report rather than living in this paragraph.

Phase 2b adds XAUUSD, XAGUSD and GER40 (:data:`PANEL_2B`), so the panel spans
three market structures (R5, R14). GER40 closes every night and on European
holidays, and has **no native H4** to validate against. Resampling is checked
structurally instead (:func:`h4_structure`): no empty bin is emitted, no bin's
members span 4h or more, and on GER40 no bin straddles a session break at all,
because its nightly closes fall on 4h bin edges. Session-aware resampling was
therefore not needed. ``masked=True`` runs the panel under R3's mask
(:func:`build_panel_mask`); the mask-off path is the seq=109 path unchanged.

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

from resources.data.mask import MaskReason, TradabilityMask

from research import admission
from research.pre.signal_edge import (_excursions, _forward_extremes,
                                      wilder_atr)
from research.pre.signals.flood_tide import FloodTideParams, generate_signals

__all__ = [
    "MAJORS",
    "PANEL_2B",
    "STRUCTURE",
    "build_panel_mask",
    "h4_structure",
    "masked_atr",
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

#: Phase 2b's panel: the majors, the two metals, and GER40 as the third market
#: structure (R14). UK100 is R14's fallback and is not in the panel.
PANEL_2B = MAJORS + ("XAUUSD", "XAGUSD", "GER40")

#: Which market structure each instrument stands for. R5's gate is about
#: structures, not instrument counts, so the report groups by this.
STRUCTURE = {**{s: "fx" for s in MAJORS},
             "XAUUSD": "metals", "XAGUSD": "metals",
             "GER40": "equity_index"}

#: The mask the panel runs under when ``masked=True`` (R3). Two flags, both
#: derivable from the bar index alone, so they mean the same thing on an FX
#: pair, a metal and an exchange-traded index:
#:
#: * ``WEEKEND_GAP`` — the first bar after a gap over 40h, unchanged from T9a.
#: * ``HOLIDAY`` — the first bar after a gap over ``CLOSURE_GAP_BARS`` H1 bars,
#:   i.e. a whole day missing. This catches the mid-week closures the weekend
#:   flag cannot: GER40's Christmas closures run 26-35h.
#:
#: Session breaks (GER40's nightly close, gold's daily break, 2-11h) are
#: deliberately NOT flagged. They recur every session, so flagging them caps
#: every clean run at one session (median 22 bars on GER40, 23 on XAUUSD) and
#: R3's WINDOW rule then NaNs the 55-bar Donchian almost everywhere — 16% of
#: GER40 bars and 0% of XAUUSD bars would keep a clean 55-bar window. That is
#: the mask starvation law, not a property of the market. The bar after a
#: closure does carry stale state: its open moves a median 0.87 ATR from the
#: prior close on GER40 (weekends 0.65, ordinary bars 0.01), against 0.17 after
#: a nightly close.
TIMEFRAME = pd.Timedelta("1h")
WEEKEND_GAP_HOURS = 40.0
CLOSURE_GAP_BARS = 24

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


def h4_structure(h1: pd.DataFrame) -> dict:
    """Structural check of :func:`resample_h4` on a series with closures.

    There is no native H4 for most of the panel (GER40 included), so the
    exact-match check against native bars is only available on XAUUSD. What
    can be checked anywhere is that resampling neither invents bars nor merges
    across a closure:

    ``empty_bins_emitted``
        H4 bars with no H1 bar behind them. Must be 0.
    ``bins_spanning_more_than_width``
        Bins whose first and last H1 member are 4h or more apart. Must be 0:
        a bin that did this would have merged bars from either side of a gap
        at least as wide as the bin.
    ``bins_straddling_a_session_break``
        Bins with a gap of more than one bar *inside* them — a session break
        that falls mid-bin rather than on a bin edge. Reported, not refused:
        native MT5 H4 aggregates exactly these bars too (XAUUSD's daily break
        sits inside its 00:00 bin and still matches native 100%).
    """
    idx = h1.index
    bins = idx.floor("4h")
    s = pd.Series(idx, index=idx)
    grouped = s.groupby(bins)
    first, last, count = grouped.min(), grouped.max(), grouped.size()
    span_h = (last - first).dt.total_seconds() / 3600.0
    inner_gap_h = (s.diff().dt.total_seconds() / 3600.0).where(
        pd.Series(bins, index=idx).eq(pd.Series(bins, index=idx).shift()))
    straddling = int((inner_gap_h > 1.0).groupby(bins).any().sum())
    r = resample_h4(h1)
    per_day = r.groupby(r.index.normalize()).size()
    return {
        "h1_bars": int(len(idx)),
        "h4_bars": int(len(r)),
        "nonempty_bins": int(len(count)),
        "empty_bins_emitted": int(len(r) - len(count)),
        "members_per_bin": {int(k): int(v) for k, v in
                            count.value_counts().sort_index().items()},
        "max_member_span_hours": float(span_h.max()) if len(span_h) else 0.0,
        "bins_spanning_more_than_width": int((span_h >= 4.0).sum()),
        "bins_straddling_a_session_break": straddling,
        "h4_bars_per_day": {int(k): int(v) for k, v in
                            per_day.value_counts().sort_index().items()},
    }


def build_panel_mask(index: pd.DatetimeIndex) -> TradabilityMask:
    """The panel's declared mask — see :data:`CLOSURE_GAP_BARS`."""
    return (TradabilityMask(index)
            .flag_weekend_gap(max_gap_hours=WEEKEND_GAP_HOURS)
            .flag_gap(MaskReason.HOLIDAY, timeframe=TIMEFRAME,
                      n_bars=CLOSURE_GAP_BARS))


def masked_atr(h1: pd.DataFrame, mask: TradabilityMask) -> np.ndarray:
    """Wilder ATR with masked bars skipped (R3: ATR is an ACCUMULATOR).

    State advances across the gap rather than absorbing the gap bar's true
    range; masked bars read NaN and so drop out of both the signal set and
    the null's eligible pool through the existing finite-ATR filter.
    """
    kept = h1[mask.tradable.to_numpy()]
    atr = wilder_atr(kept["high"], kept["low"], kept["close"], ATR_PERIOD)
    return atr.reindex(h1.index).to_numpy(float)


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
    structure: str = ""
    p_value: dict[int, float] = field(default_factory=dict)
    mask: Optional[dict] = None
    h4: dict = field(default_factory=dict)

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
    symbols: tuple[str, ...] = MAJORS
    masked: bool = False

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

    def structures_decided(self) -> dict[str, list[str]]:
        """Decidable instruments per market structure. A structure with none
        has not been tested, whatever the pooled number says."""
        out: dict[str, list[str]] = {}
        for i in self.instruments:
            members = out.setdefault(i.structure or "unclassified", [])
            if i.decidable:
                members.append(i.symbol)
        return out

    def as_dict(self) -> dict:
        return {
            "mechanism": "flood_tide_h1",
            "panel": list(self.symbols),
            "masked": self.masked,
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
                 "decidable": i.decidable, "e_ratio": i.e_ratio,
                 "structure": i.structure, "p_value": i.p_value,
                 "mask": i.mask, "h4_structure": i.h4}
                for i in self.instruments
            ],
            "structures_decided": self.structures_decided(),
        }


def _forward_arrays(ohlc: pd.DataFrame):
    return (ohlc["open"].to_numpy(float), ohlc["high"].to_numpy(float),
            ohlc["low"].to_numpy(float), ohlc["close"].to_numpy(float))


def _instrument_excursions(ohlc: pd.DataFrame, signal_idx: np.ndarray,
                           window: int, atr: np.ndarray, fwd=None):
    """Normalised MFE/MAE for a set of entry bars at one horizon.

    The forward arrays come from :func:`signal_edge._forward_extremes` rather
    than being rebuilt here. ``_excursions`` indexes them by *bar position*
    (``fwd_high[idx]``), so they must be full length and aligned to ``t``; an
    earlier version of this function passed one element per signal and indexed
    it with original bar numbers, which raised IndexError on the first real
    run. Reusing the canonical builder removes the second definition rather
    than repairing it — the arithmetic here was never the part that was wrong.
    """
    open_, high, low, close = _forward_arrays(ohlc)
    n = len(close)
    keep = signal_idx[signal_idx <= n - window - 1]
    if keep.size == 0:
        return np.array([]), np.array([])
    dirs = np.ones(keep.size, dtype=np.int64)
    # ``fwd`` is the same _forward_extremes output, built once per instrument
    # and horizon by the caller; rebuilding it inside every permutation was
    # the whole cost of the null. The arrays are identical either way.
    fwd_high, fwd_low, fwd_close = (
        fwd if fwd is not None else _forward_extremes(high, low, close, window))
    mfe, mae, _ = _excursions(keep, dirs, open_, fwd_high, fwd_low,
                              fwd_close, atr)
    finite = np.isfinite(mfe) & np.isfinite(mae)
    return mfe[finite], mae[finite]


def check_panel(data_dir: Optional[Path] = None,
                params: FloodTideParams = FloodTideParams(),
                n_permutations: int = N_PERMUTATIONS,
                symbols: tuple[str, ...] = MAJORS,
                masked: bool = False) -> PanelEdgeReport:
    """Run the mechanism across the panel and test the pooled statistic.

    ``masked=False`` is the seq=109 path, unchanged: no mask reaches the
    signal generator and ATR is the plain Wilder ATR. ``masked=True`` applies
    :func:`build_panel_mask` per instrument (R3): the Donchian channels become
    WINDOW indicators and ATR skips masked bars as an ACCUMULATOR.

    Horizons are positional, so they count bars that are present (R4): an
    instrument's closed hours are not in its series and are never counted as
    exposure. ``tests/test_panel_edge_r4.py`` demonstrates this.
    """
    from research.pre.scripts.run_flood_tide_edge import load_ohlcv

    data_dir = Path(data_dir) if data_dir else _default_data_dir()
    rng = np.random.default_rng(RANDOM_SEED)
    report = PanelEdgeReport(n_permutations=n_permutations,
                             symbols=tuple(symbols), masked=masked)

    observed: dict[int, list] = {h: [[], []] for h in HORIZONS}
    pools: list[tuple] = []

    for sym in symbols:
        # The admission gate: no instrument enters the panel unchecked, and
        # one admitted from a later date is read from there (seq=128).
        admitted_from = admission.require(sym, "H1", data_dir)
        h1 = load_ohlcv(data_dir / f"{sym}_H1.csv")
        h1 = h1[h1.index >= admitted_from]
        h4 = resample_h4(h1)
        if masked:
            mask = build_panel_mask(h1.index)
            sig = generate_signals(h1, h4, params, mask=mask)
            atr = masked_atr(h1, mask)
        else:
            mask = None
            sig = generate_signals(h1, h4, params)
            atr = wilder_atr(h1["high"], h1["low"], h1["close"],
                             ATR_PERIOD).to_numpy(float)

        entries = np.flatnonzero(sig["entry_signal"].to_numpy())
        eligible = np.flatnonzero(
            (sig["regime_ok"] & sig["upper_entry"].notna()).to_numpy()
            & np.isfinite(atr))

        _, hi, lo, cl = _forward_arrays(h1)
        fwd = {h: _forward_extremes(hi, lo, cl, h) for h in HORIZONS}
        e_ratio, s_mfe, s_mae = {}, {}, {}
        for h in HORIZONS:
            mfe, mae = _instrument_excursions(h1, entries, h, atr, fwd[h])
            s_mfe[h] = float(mfe.sum())
            s_mae[h] = float(mae.sum())
            e_ratio[h] = float(mfe.sum() / mae.sum()) if mae.sum() else float("nan")
            observed[h][0].append(mfe.sum())
            observed[h][1].append(mae.sum())

        report.instruments.append(InstrumentEdge(
            symbol=sym, n_bars=len(h1), start=str(h1.index[0].date()),
            end=str(h1.index[-1].date()), n_signals=int(entries.size),
            e_ratio=e_ratio, sum_mfe=s_mfe, sum_mae=s_mae,
            eligible_bars=int(eligible.size),
            structure=STRUCTURE.get(sym, ""),
            mask=mask.summary() if mask is not None else None,
            h4=h4_structure(h1)))
        pools.append((entries, eligible, h1, atr, int(entries.size), fwd))

    for h in HORIZONS:
        num, den = sum(observed[h][0]), sum(observed[h][1])
        report.pooled_e_ratio[h] = float(num / den) if den else float("nan")

    # The majors have no native H4, so every trend filter in this run reads a
    # resampled series. XAUUSD has both, and is the only place that assumption
    # can be checked — so it is checked here and travels with the result,
    # rather than being asserted in a docstring. A missing file degrades to an
    # empty check rather than failing the run: the panel does not depend on
    # XAUUSD, only the validation does.
    try:
        report.resampling_check = validate_resampling(
            load_ohlcv(data_dir / "XAUUSD_H1.csv"),
            load_ohlcv(data_dir / "XAUUSD_H4.csv"))
    except (FileNotFoundError, OSError):
        report.resampling_check = {"common_bars": 0, "exact_match_rate": {},
                                   "note": "XAUUSD H1/H4 not available here"}

    # -- the pooled null ---------------------------------------------------
    # Per-instrument nulls come from the same draws as the pooled one, so they
    # cost nothing and do not move the random stream: the pooled p-value is
    # what it would be without them.
    null = {h: [] for h in HORIZONS}
    inst_null = [{h: [] for h in HORIZONS} for _ in pools]
    for _ in range(n_permutations):
        acc = {h: [0.0, 0.0] for h in HORIZONS}
        for k, (entries, eligible, h1, atr, n_sig, fwd) in enumerate(pools):
            if n_sig == 0 or eligible.size == 0:
                continue
            draw = rng.choice(eligible, size=min(n_sig, eligible.size),
                              replace=False)
            for h in HORIZONS:
                mfe, mae = _instrument_excursions(h1, draw, h, atr, fwd[h])
                acc[h][0] += mfe.sum()
                acc[h][1] += mae.sum()
                inst_null[k][h].append(
                    mfe.sum() / mae.sum() if mae.sum() else np.nan)
        for h in HORIZONS:
            null[h].append(acc[h][0] / acc[h][1] if acc[h][1] else np.nan)

    for inst, nulls in zip(report.instruments, inst_null):
        for h in HORIZONS:
            arr = np.asarray(nulls[h], dtype=float)
            arr = arr[np.isfinite(arr)]
            obs = inst.e_ratio[h]
            inst.p_value[h] = (float((arr >= obs).mean())
                               if arr.size and np.isfinite(obs) else float("nan"))

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
            "max_e_ratio_anywhere": max(
                (v for i in report.instruments for v in i.e_ratio.values()),
                default=float("nan")),
            "gate": 1.15,
            "min_signals_to_decide": MIN_SIGNALS_TO_DECIDE,
            "resampling_check": report.resampling_check,
        },
        **kwargs,
    )


# -- Phase 2b: the validation run across three market structures -----------

PHASE2B_PREREG_ID = "record:phase2b-panel-preregistration"
PHASE2B_RESULT_ID = "record:phase2b-panel-flood-tide"

#: The streams a Phase 2b run emits. ``pooled_p_min`` is the smallest of the
#: mask-on pooled p-values across the three horizons; the per-horizon values
#: and the mask-off minimum are reported beside it.
PHASE2B_STREAMS = {"pooled_p_min", "pooled_p_h20", "pooled_p_h50",
                   "pooled_p_h100", "pooled_p_min_mask_off"}
PHASE2B_THRESHOLD = 0.05
PHASE2B_RATIONALE = (
    "The claim under test is that the harness reports an already-falsified "
    "mechanism as dead on three market structures. The mask-on run decides "
    "because R3 is the standing mask policy; the mask-off run exists only to "
    "reproduce seq=109. The minimum p over the three horizons, uncorrected, "
    "is the stream that makes 'dead' hardest to claim: any single horizon "
    "under 0.05 counts as alive."
)


def phase2b_decisive_stream():
    from research.pre.decisive_stream import declare
    return declare("pooled_p_min", PHASE2B_THRESHOLD, PHASE2B_STREAMS,
                   rationale=PHASE2B_RATIONALE)


def phase2b_streams(masked: PanelEdgeReport,
                    unmasked: PanelEdgeReport) -> dict[str, float]:
    out = {f"pooled_p_h{h}": masked.pooled_p_value[h] for h in HORIZONS}
    out["pooled_p_min"] = min(masked.pooled_p_value.values())
    out["pooled_p_min_mask_off"] = min(unmasked.pooled_p_value.values())
    return out


def phase2b_verdict(masked: PanelEdgeReport,
                    unmasked: PanelEdgeReport) -> dict:
    """Apply the pre-registered rule. The rule is fixed in the registration
    (seq recorded in the result); this function only executes it.

    * ``ALIVE_POOLED`` — the decisive stream passes.
    * ``UNTESTED_STRUCTURE`` — it fails, but some structure has no decidable
      instrument, so "three structures" was not achieved.
    * ``DEAD_ON_AVERAGE`` — it fails, every structure is decided, but some
      decidable instrument clears the 1.15 gate at some horizon.
    * ``DEAD_EVERYWHERE`` — it fails, every structure is decided, and no
      decidable instrument clears 1.15 anywhere. The expected outcome.
    """
    stream = phase2b_decisive_stream()
    streams = phase2b_streams(masked, unmasked)
    decisive, why = stream.verdict(streams)
    alive = masked.alive_anywhere()
    untested = [k for k, v in masked.structures_decided().items() if not v]
    if decisive == "PASS":
        label = "ALIVE_POOLED"
    elif untested:
        label = "UNTESTED_STRUCTURE"
    elif alive:
        label = "DEAD_ON_AVERAGE"
    else:
        label = "DEAD_EVERYWHERE"
    return {"verdict": label, "decisive": decisive, "decisive_reason": why,
            "streams": streams, "alive_anywhere": alive,
            "untested_structures": untested}


def preregister_phase2b(log_dir: Optional[Path] = None):
    """Append the Phase 2b pre-registration. Must precede the run."""
    from research import log as research_log
    stream = phase2b_decisive_stream()
    kwargs = {"log_dir": log_dir} if log_dir is not None else {}
    return research_log.append_record(
        research_log.EventType.AUDIT,
        record_id=PHASE2B_PREREG_ID,
        title=("Phase 2b panel pre-registration — flood_tide_h1 across FX, "
               "metals and GER40, mask on"),
        note=(
            "Pre-registered before the run. Harness validation, not a trial: "
            "flood_tide_h1 was shelved at seq=34 and found dead on the seven "
            "majors at seq=109; this re-runs it on three market structures "
            "(R5, R14) with R3's mask applied and R4's present-bar horizons. "
            f"Decisive stream: {stream.name} < {stream.threshold} means alive. "
            f"{stream.rationale} Conjoint rule, also fixed now: a structure "
            "counts as tested only if it has at least one instrument with "
            f">= {MIN_SIGNALS_TO_DECIDE} signals; 'dead everywhere' further "
            "requires no decidable instrument to reach E-Ratio 1.15 at any "
            "horizon, otherwise the verdict is 'dead on average'. Mask: first "
            f"bar after a gap over {WEEKEND_GAP_HOURS:.0f}h (WEEKEND_GAP) or "
            f"over {CLOSURE_GAP_BARS} H1 bars (HOLIDAY); session breaks are "
            "not flagged. Same seed, horizons and permutation count as "
            "seq=109. Mask-off is run and reported, never decisive."
        ),
        metrics={
            "mechanism": "flood_tide_h1",
            "panel": list(PANEL_2B),
            "structures": {k: [s for s in PANEL_2B if STRUCTURE[s] == k]
                           for k in ("fx", "metals", "equity_index")},
            "horizons": list(HORIZONS),
            "n_permutations": N_PERMUTATIONS,
            "random_seed": RANDOM_SEED,
            "decisive_stream": stream.name,
            "decisive_threshold": stream.threshold,
            "decisive_rationale": stream.rationale,
            "streams_emitted": sorted(PHASE2B_STREAMS),
            "per_instrument_gate": 1.15,
            "min_signals_to_decide": MIN_SIGNALS_TO_DECIDE,
            "verdict_labels": ["ALIVE_POOLED", "UNTESTED_STRUCTURE",
                               "DEAD_ON_AVERAGE", "DEAD_EVERYWHERE"],
            "expected": "DEAD_EVERYWHERE",
            "mask": {"weekend_gap_hours": WEEKEND_GAP_HOURS,
                     "holiday_gap_bars": CLOSURE_GAP_BARS,
                     "timeframe": "H1",
                     "session_breaks_flagged": False},
            "h4": "resampled from H1 on every instrument; no native GER40 H4",
        },
        **kwargs,
    )


def _per_instrument(rep: PanelEdgeReport) -> dict:
    return {i.symbol: {"structure": i.structure, "n_signals": i.n_signals,
                       "decidable": i.decidable, "e_ratio": i.e_ratio,
                       "p_value": i.p_value}
            for i in rep.instruments}


def run_phase2b(artifact: Path, data_dir: Optional[Path] = None,
                n_permutations: int = N_PERMUTATIONS) -> dict:
    """Run the panel mask-on and mask-off and write both to ``artifact``."""
    masked = check_panel(data_dir, n_permutations=n_permutations,
                         symbols=PANEL_2B, masked=True)
    unmasked = check_panel(data_dir, n_permutations=n_permutations,
                           symbols=PANEL_2B, masked=False)
    out = {"mask_on": masked.as_dict(), "mask_off": unmasked.as_dict(),
           "verdict": phase2b_verdict(masked, unmasked)}
    artifact = Path(artifact)
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(out, indent=2, default=float) + "\n")
    return {"masked": masked, "unmasked": unmasked, "summary": out}


def _print_report(report: PanelEdgeReport) -> None:
    print(f"panel — flood_tide_h1 over {len(report.symbols)} instruments, "
          f"mask {'on' if report.masked else 'off'}")
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


def log_phase2b_result(masked: PanelEdgeReport, unmasked: PanelEdgeReport,
                       artifact: str, prereg_seq: int,
                       log_dir: Optional[Path] = None):
    """Record the Phase 2b run against its pre-registration."""
    from research import log as research_log
    v = phase2b_verdict(masked, unmasked)
    kwargs = {"log_dir": log_dir} if log_dir is not None else {}

    return research_log.append_record(
        research_log.EventType.AUDIT,
        record_id=PHASE2B_RESULT_ID,
        title=("Phase 2b panel harness — flood_tide_h1 across FX, metals and "
               f"GER40: {v['verdict']}"),
        note=(
            f"Run against the pre-registration at seq={prereg_seq}. "
            f"Decisive: {v['decisive_reason']} -> {v['decisive']}. "
            f"Instruments alive at their own gate: {v['alive_anywhere'] or 'none'}. "
            f"Untested structures: {v['untested_structures'] or 'none'}. "
            "Not a trial: a falsified mechanism re-run to validate the harness."
        ),
        metrics={
            "preregistration_seq": prereg_seq,
            "artifact": artifact,
            "verdict": v,
            "panel": list(masked.symbols),
            "n_permutations": masked.n_permutations,
            "mask_on": {
                "pooled_e_ratio": masked.pooled_e_ratio,
                "pooled_p_value": masked.pooled_p_value,
                "null_mean": masked.null_mean,
                "structures_decided": masked.structures_decided(),
                "per_instrument": _per_instrument(masked),
                "mask_attribution": {i.symbol: i.mask for i in masked.instruments},
            },
            "mask_off": {
                "pooled_e_ratio": unmasked.pooled_e_ratio,
                "pooled_p_value": unmasked.pooled_p_value,
                "null_mean": unmasked.null_mean,
                "per_instrument": _per_instrument(unmasked),
            },
            "resampling_check": masked.resampling_check,
        },
        **kwargs,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--permutations", type=int, default=N_PERMUTATIONS)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--log", action="store_true")
    ap.add_argument("--preregister-phase2b", action="store_true",
                    help="append the Phase 2b pre-registration and exit")
    ap.add_argument("--phase2b", type=Path, metavar="ARTIFACT",
                    help="run the Phase 2b panel mask-on and mask-off, write "
                         "ARTIFACT; with --log, record it against --prereg-seq")
    ap.add_argument("--prereg-seq", type=int, default=None)
    args = ap.parse_args()

    if args.preregister_phase2b:
        from research.log import render_markdown
        entry = preregister_phase2b()
        render_markdown()
        print(f"pre-registered seq={entry.seq}")
        return 0
    if args.phase2b:
        if args.log and args.prereg_seq is None:
            ap.error("--phase2b --log needs --prereg-seq")
        res = run_phase2b(args.phase2b, args.data_dir, args.permutations)
        _print_report(res["masked"])
        print()
        _print_report(res["unmasked"])
        print("\n", json.dumps(res["summary"]["verdict"], indent=2))
        if args.log:
            from research.log import render_markdown
            entry = log_phase2b_result(res["masked"], res["unmasked"],
                                       str(args.phase2b), args.prereg_seq)
            render_markdown()
            print(f"logged seq={entry.seq}")
        return 0

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
