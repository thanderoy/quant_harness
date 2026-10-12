"""Phase 4 — does relative quote activity change how an H1 move follows through?

The mechanism is the first one drawn from an input other than price (R5,
CLAUDE.md's ceiling): MT5 ``tick_volume``, the number of quote updates in a
bar. On a CFD feed it carries no traded volume and no aggressor side — the
2026-10-12 probe of the live terminal found ``volume`` and ``last`` zero on
every tick and the BUY/SELL flags absent — so this is quote *activity*, not
order flow.

**The claim.** On an H1 bar whose move is large against its own recent
volatility, the bar's activity relative to its usual level for that hour of
the week changes what the next few bars do. Two published theories predict
opposite signs:

* Campbell, Grossman & Wang (1993): moves on high volume are liquidity-driven
  and *reverse more*.
* Llorente, Michaely, Saar & Wang (2002): where informed trading dominates,
  moves on high volume *continue*.

Either sign would be tradable, and choosing one before the data would be
choosing between two theories by preference, so the decisive test is
two-sided and the sign is reported with the result.

**Activity is relative, never absolute.** Median ticks per hour moves by
orders of magnitude across a feed's history (XAUUSD 33 in 2004, 5,263 in 2013;
GER40 157 to 19,173 to 1,388) for reasons that are the feed, not the market.
So a bar's activity is its log ratio to the median of the same hour-of-week
over the previous ``BASELINE_WEEKS`` weeks, and a baseline window that crosses
a declared feed break (:data:`KNOWN_FEED_BREAKS`) is not computed.

**The outcome cannot see the feature's inputs.** The forward move is in units
of a trailing close-to-close standard deviation; the feature is built from
``volume`` alone (screen hygiene rule 1, asserted in :func:`feature_spec`).
The forward move is net of the trailing mean return, so an instrument's drift
cannot pose as continuation (rule 3).

**Events do not overlap.** An event is kept only if no event was kept in the
previous ``max(HORIZONS)`` bars, so no two forward windows share a bar. The
cnk_momentum walk-forward counted 3,829 trades that were 1,970 distinct ones
(seq=136); this is the same failure in a different place.

**The null keeps activity's autocorrelation.** Activity clusters, so a free
shuffle of labels would understate the null's spread and make p too small.
The null instead rotates each instrument's label sequence by a random offset
(at least a tenth of the sequence away from zero), which breaks the alignment
between labels and outcomes and keeps everything else.

Nothing here computes an outcome on real data until the registration exists in
the log: :func:`run` refuses otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from research import admission
from research.pre.decisive_stream import DecisiveStream, declare
from research.pre.normalizer_check import assert_disjoint
from research.pre.panel_edge import (PANEL_2B, STRUCTURE, _default_data_dir,
                                     build_panel_mask)

HYPOTHESIS_ID = "activity_reversal_h1"
FAMILY = "activity_reversal"

#: An H1 bar is an event when |log return| is at least this many trailing
#: standard deviations.
EVENT_Z = 1.0
#: Trailing window, in present bars, for the volatility and drift estimates.
SIGMA_BARS = 500
SIGMA_MIN_BARS = 400
#: Same-hour-of-week baseline: the median of the previous 8 weeks, with at
#: least 6 of them present.
BASELINE_WEEKS = 8
BASELINE_MIN_OBS = 6
#: Forward horizons in present bars (R4). The decisive one is 4.
HORIZONS = (1, 4, 12)
DECISIVE_HORIZON = 4
#: A cell (one instrument's HIGH or LOW tercile) below this many events is
#: reported but not read as evidence (screen hygiene rule 2).
MIN_CELL_EVENTS = 100
N_PERMUTATIONS = 1000
RANDOM_SEED = 42
#: The null's rotation is drawn from [n/10, 9n/10] so it never sits near the
#: identity.
MIN_ROTATION_SHARE = 0.10
ALPHA = 0.05

#: Feed breaks, as the first date the new feed is in force. A baseline window
#: that spans one is not computed. EURUSD's tick flags change encoding
#: (134 -> 1158) between the 2025-12-24 and 2025-12-31 samples of the
#: 2026-10-12 depth scan; the other majors were not probed and are assumed to
#: share the FX feed. XAUUSD reads 1158 throughout the retained span and
#: GER40 134 throughout. Breaks before 2025-01 cannot be seen in tick flags —
#: the broker retains no ticks from then — and are a declared limitation.
KNOWN_FEED_BREAKS: dict[str, tuple[str, ...]] = {
    s: ("2025-12-31",) for s in
    ("EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD")
}

STRUCTURES = ("fx", "metals", "equity_index")
STREAMS = frozenset(
    {f"pooled_p_h{h}" for h in HORIZONS}
    | {f"{s}_p_h{DECISIVE_HORIZON}" for s in STRUCTURES})
REGISTRY_SNAPSHOT = "pepperstone_live_20261009b.json"


def decisive_stream() -> DecisiveStream:
    return declare(
        f"pooled_p_h{DECISIVE_HORIZON}", ALPHA, set(STREAMS),
        rationale=(
            "The claim is that relative activity separates follow-through on "
            "three market structures, not on one. The pooled statistic weights "
            "the structures equally, so seven FX pairs cannot carry it alone. "
            "h=4 is fixed now as the horizon both theories address — a "
            "liquidity reversal or an information continuation that has "
            "played out within a session; h=1 and h=12 are reported, never "
            "decisive. Two-sided, because the two theories predict opposite "
            "signs."))


def feature_spec() -> dict:
    """Feature inputs and target normalizer, asserted disjoint (rule 1)."""
    spec = {"feature_inputs": {"volume"},
            "target_normalizer": {"close_logret_std"}}
    assert_disjoint(spec["feature_inputs"], spec["target_normalizer"],
                    name="relative_activity")
    return {k: sorted(v) for k, v in spec.items()}


def load_h1(path: Path) -> pd.DataFrame:
    """A house H1 CSV with its tick-volume column kept."""
    df = pd.read_csv(path, sep=";", header=0,
                     names=["datetime", "open", "high", "low", "close", "volume"],
                     parse_dates=["datetime"], date_format="%Y.%m.%d %H:%M")
    df = df.set_index("datetime").sort_index()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df.astype(float)


def relative_activity(volume: pd.Series,
                      breaks: tuple[str, ...] = ()) -> pd.Series:
    """log(volume / median of the same hour-of-week over prior weeks).

    Strictly causal: the window is closed on the left, so a bar never sees
    itself or anything after it. NaN where fewer than ``BASELINE_MIN_OBS``
    prior weeks are present, or where the window spans a feed break.
    """
    v = volume.where(volume > 0)
    key = v.index.dayofweek * 24 + v.index.hour
    window = pd.Timedelta(weeks=BASELINE_WEEKS)
    base = pd.Series(np.nan, index=v.index)
    count = pd.Series(0.0, index=v.index)
    for _, grp in v.groupby(key):
        roll = grp.rolling(window, closed="left")
        base.loc[grp.index] = roll.median().to_numpy()
        count.loc[grp.index] = roll.count().to_numpy()
    out = np.log(v / base).where(count >= BASELINE_MIN_OBS)
    for b in breaks:
        start = pd.Timestamp(b, tz=out.index.tz)
        out[(out.index >= start) & (out.index < start + window)] = np.nan
    return out


def trailing_moments(r: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Mean and std of the previous ``SIGMA_BARS`` returns, excluding t."""
    prior = r.shift(1).rolling(SIGMA_BARS, min_periods=SIGMA_MIN_BARS)
    return prior.mean(), prior.std()


def thin(candidates: np.ndarray, gap: int) -> np.ndarray:
    """Keep a candidate only if none was kept in the previous ``gap`` bars."""
    kept: list[int] = []
    last = -gap - 1
    for i in candidates:
        if i - last > gap:
            kept.append(int(i))
            last = i
    return np.asarray(kept, dtype=int)


def instrument_events(df: pd.DataFrame, tradable: np.ndarray,
                      breaks: tuple[str, ...] = (),
                      with_outcomes: bool = False) -> pd.DataFrame:
    """One row per kept event: its time, activity and (optionally) outcomes.

    ``tradable`` is the panel mask's per-bar flag (R3). A bar's return is
    taken only when the bar and its predecessor are both tradable, and an
    event is dropped if a non-tradable bar falls inside its longest forward
    window, so no outcome straddles a closure.
    """
    close = df["close"].to_numpy(float)
    logc = np.log(close)
    r = pd.Series(np.r_[np.nan, np.diff(logc)], index=df.index)
    ok = tradable & np.r_[False, tradable[:-1]]
    r[~ok] = np.nan
    mu, sigma = trailing_moments(r)
    act = relative_activity(df["volume"], breaks)

    h_max = max(HORIZONS)
    n = len(df)
    blocked = np.convolve((~tradable).astype(int), np.ones(h_max, int))[h_max:]
    # blocked[i] counts non-tradable bars in i+1 .. i+h_max.
    blocked = np.r_[blocked, np.ones(n - blocked.size, int)][:n]
    z = (r / sigma).to_numpy(float)
    cand = np.flatnonzero(np.isfinite(z) & (np.abs(z) >= EVENT_Z)
                          & np.isfinite(act.to_numpy(float))
                          & (np.arange(n) + h_max < n) & (blocked == 0))
    idx = thin(cand, h_max)

    out = pd.DataFrame({"time": df.index[idx],
                        "activity": act.to_numpy(float)[idx],
                        "sign": np.sign(r.to_numpy(float)[idx])})
    if with_outcomes:
        s = sigma.to_numpy(float)[idx]
        m = mu.to_numpy(float)[idx]
        for h in HORIZONS:
            fwd = logc[idx + h] - logc[idx] - h * m
            out[f"y_h{h}"] = out["sign"].to_numpy() * fwd / s
    return out


def label_terciles(activity: pd.Series) -> np.ndarray:
    """0 = LOW, 1 = MID, 2 = HIGH, by the instrument's own event terciles.

    Cut-points use activity values only — never an outcome — so they carry
    no information about what follows.
    """
    return pd.qcut(activity, 3, labels=False).to_numpy(int)


@dataclass
class InstrumentResult:
    symbol: str
    structure: str
    admitted_from: str
    n_events: int
    n_high: int
    n_low: int
    decidable: bool
    spread: dict = field(default_factory=dict)


def _cell_spread(y: np.ndarray, labels: np.ndarray) -> float:
    return float(y[labels == 2].mean() - y[labels == 0].mean())


def _rotate(labels: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    n = labels.size
    lo = max(1, int(np.ceil(MIN_ROTATION_SHARE * n)))
    hi = max(lo + 1, int(np.floor((1 - MIN_ROTATION_SHARE) * n)))
    return np.roll(labels, int(rng.integers(lo, hi)))


def _two_sided_p(null: np.ndarray, x: float) -> float:
    return float((1 + np.sum(np.abs(null) >= abs(x))) / (null.size + 1))


def pooled_statistic(spreads: dict[str, float],
                     structure_of: dict[str, str]) -> tuple[float, dict]:
    """Mean over structures of the mean spread within each structure."""
    by: dict[str, list[float]] = {}
    for sym, d in spreads.items():
        by.setdefault(structure_of[sym], []).append(d)
    per = {k: float(np.mean(v)) for k, v in by.items()}
    return (float(np.mean(list(per.values()))) if per else float("nan")), per


def permutation_test(frames: dict[str, pd.DataFrame],
                     labels: dict[str, np.ndarray],
                     structure_of: dict[str, str], h: int,
                     n_permutations: int = N_PERMUTATIONS,
                     seed: int = RANDOM_SEED) -> dict:
    """Two-sided rotation null for the pooled and per-structure spreads."""
    rng = np.random.default_rng(seed)
    col = f"y_h{h}"
    obs = {s: _cell_spread(frames[s][col].to_numpy(), labels[s]) for s in frames}
    pooled, per = pooled_statistic(obs, structure_of)
    null_pooled = np.empty(n_permutations)
    null_per = {k: np.empty(n_permutations) for k in per}
    for i in range(n_permutations):
        sp = {s: _cell_spread(frames[s][col].to_numpy(), _rotate(labels[s], rng))
              for s in frames}
        p_i, per_i = pooled_statistic(sp, structure_of)
        null_pooled[i] = p_i
        for k in per:
            null_per[k][i] = per_i[k]
    return {"observed": pooled, "p": _two_sided_p(null_pooled, pooled),
            "per_structure": {k: {"observed": v,
                                  "p": _two_sided_p(null_per[k], v)}
                              for k, v in per.items()},
            "per_instrument": obs}


def verdict(result: dict, stream: DecisiveStream,
            tested: set[str]) -> tuple[str, str]:
    """The conjoint rule fixed at registration.

    * ``UNTESTED_STRUCTURE`` — a structure has no decidable instrument; no
      claim about three structures is possible.
    * ``ALIVE`` — decisive p under threshold and every structure's spread has
      the pooled sign.
    * ``ALIVE_POOLED_ONLY`` — decisive p under threshold but a structure
      disagrees in sign. Does not proceed.
    * ``DEAD`` — decisive p at or over threshold.
    """
    missing = [s for s in STRUCTURES if s not in tested]
    if missing:
        return "UNTESTED_STRUCTURE", f"no decidable instrument in {missing}"
    p = {stream.name: result[f"h{DECISIVE_HORIZON}"]["p"]}
    passed, why = stream.verdict(p)
    if passed == "FAIL":
        return "DEAD", why
    d = result[f"h{DECISIVE_HORIZON}"]
    signs = {k: np.sign(v["observed"]) for k, v in d["per_structure"].items()}
    if all(s == np.sign(d["observed"]) for s in signs.values()):
        return "ALIVE", why
    return "ALIVE_POOLED_ONLY", f"{why}; structure signs {signs}"


def _admitted_frame(sym: str, data_dir: Path) -> tuple[pd.DataFrame, pd.Timestamp]:
    start = admission.require(sym, "H1", data_dir)
    df = load_h1(data_dir / f"{sym}_H1.csv")
    return df[df.index >= start], start


def count_events(data_dir: Optional[Path] = None,
                 symbols: tuple[str, ...] = PANEL_2B) -> dict:
    """Event and cell counts per instrument. Reads no outcome.

    Run before registration to fix the intended sample, which is what
    ``min_decidable_sharpe`` is computed from.
    """
    data_dir = Path(data_dir) if data_dir else _default_data_dir()
    out = {}
    for sym in symbols:
        df, start = _admitted_frame(sym, data_dir)
        tradable = build_panel_mask(df.index).tradable.to_numpy()
        ev = instrument_events(df, tradable, KNOWN_FEED_BREAKS.get(sym, ()))
        lab = label_terciles(ev["activity"])
        out[sym] = {"admitted_from": str(start.date()),
                    "n_events": int(len(ev)),
                    "n_high": int((lab == 2).sum()),
                    "n_low": int((lab == 0).sum())}
    return out


def _registered(log_dir: Optional[Path]) -> bool:
    from research import log as research_log
    kwargs = {"log_dir": log_dir} if log_dir is not None else {}
    return bool(research_log.history(HYPOTHESIS_ID, **kwargs))


def run(data_dir: Optional[Path] = None, log_dir: Optional[Path] = None,
        symbols: tuple[str, ...] = PANEL_2B,
        n_permutations: int = N_PERMUTATIONS) -> dict:
    """The registered test. Refuses to compute an outcome before registration."""
    if not _registered(log_dir):
        raise RuntimeError(
            f"{HYPOTHESIS_ID!r} is not registered in the research log; "
            "register it before any outcome is computed.")
    data_dir = Path(data_dir) if data_dir else _default_data_dir()
    frames, labels, insts = {}, {}, []
    for sym in symbols:
        df, start = _admitted_frame(sym, data_dir)
        tradable = build_panel_mask(df.index).tradable.to_numpy()
        ev = instrument_events(df, tradable, KNOWN_FEED_BREAKS.get(sym, ()),
                               with_outcomes=True)
        lab = label_terciles(ev["activity"])
        n_hi, n_lo = int((lab == 2).sum()), int((lab == 0).sum())
        decidable = min(n_hi, n_lo) >= MIN_CELL_EVENTS
        insts.append(InstrumentResult(sym, STRUCTURE[sym], str(start.date()),
                                      len(ev), n_hi, n_lo, decidable))
        if decidable:
            frames[sym], labels[sym] = ev, lab
    structure_of = {s: STRUCTURE[s] for s in frames}
    result: dict = {f"h{h}": permutation_test(frames, labels, structure_of, h,
                                              n_permutations)
                    for h in HORIZONS}
    for inst in insts:
        inst.spread = {h: result[f"h{h}"]["per_instrument"].get(inst.symbol)
                       for h in HORIZONS}
    stream = decisive_stream()
    label, why = verdict(result, stream, set(structure_of.values()))
    streams = {f"pooled_p_h{h}": result[f"h{h}"]["p"] for h in HORIZONS}
    streams.update({f"{k}_p_h{DECISIVE_HORIZON}": v["p"] for k, v in
                    result[f"h{DECISIVE_HORIZON}"]["per_structure"].items()})
    return {"hypothesis_id": HYPOTHESIS_ID, "verdict": label, "reason": why,
            "decisive_stream": stream.name, "streams": streams,
            "results": result, "instruments": [asdict(i) for i in insts],
            "n_permutations": n_permutations, "random_seed": RANDOM_SEED}


def registration_parameters() -> dict:
    """The single parameter set, applied to every instrument."""
    stream = decisive_stream()
    return {
        "event_z": EVENT_Z, "sigma_bars": SIGMA_BARS,
        "sigma_min_bars": SIGMA_MIN_BARS, "baseline_weeks": BASELINE_WEEKS,
        "baseline_min_obs": BASELINE_MIN_OBS, "horizons": list(HORIZONS),
        "decisive_horizon": DECISIVE_HORIZON,
        "min_cell_events": MIN_CELL_EVENTS,
        "n_permutations": N_PERMUTATIONS, "random_seed": RANDOM_SEED,
        "min_rotation_share": MIN_ROTATION_SHARE,
        "known_feed_breaks": {k: list(v) for k, v in KNOWN_FEED_BREAKS.items()},
        "decisive_stream": stream.name, "decisive_threshold": stream.threshold,
        "decisive_rationale": stream.rationale, "two_sided": True,
        "streams_emitted": sorted(STREAMS), **feature_spec(),
        "mask": "panel_edge.build_panel_mask (WEEKEND_GAP 40h, HOLIDAY 24 bars)",
        "admission": "research.admission.require per instrument",
        "verdict_labels": ["ALIVE", "ALIVE_POOLED_ONLY", "DEAD",
                           "UNTESTED_STRUCTURE"],
    }


#: The intended sample: HIGH plus LOW events across the panel, from
#: :func:`count_events` on 2026-10-12. One derived trade per event.
INTENDED_N_OBS = 23_617
#: ``min_decidable_sharpe(INTENDED_N_OBS, sr_star=0.0)``, normal moments.
MIN_DECIDABLE_SHARPE = 0.010704

NULL_BASELINE = (
    "Per-instrument circular rotation of the activity-label sequence by a "
    "random offset in [n/10, 9n/10], 1000 draws, seed 42; pooled statistic "
    "recomputed identically. Keeps activity's autocorrelation and every "
    "instrument's outcome series; breaks only the label-outcome alignment.")

PRIOR_EXPOSURE = (
    "Tick volume has been seen before, on XAUUSD only: as the weight in "
    "VWAP and volume-profile levels (seq 13, 25, 27) and as a conditioner of "
    "an intraday-momentum rule (seq 57/58, F4, 'weakly consistent'). Neither "
    "measured bar-level follow-through by relative activity, and FX and "
    "GER40 volume behaviour has not been inspected. Integrity only was read "
    "before this registration: zero-volume share, yearly median level, tick "
    "retention and flag encodings.")


def preregister(log_dir: Optional[Path] = None):
    """Append the HYPOTHESIS event. Must precede :func:`run`."""
    from research import log as research_log
    stream = decisive_stream()
    kwargs = {"log_dir": log_dir} if log_dir is not None else {}
    return research_log.register_hypothesis(
        HYPOTHESIS_ID,
        title=("Relative quote activity and H1 follow-through, across FX, "
               "metals and GER40"),
        mechanism=(
            "An H1 bar moving at least 1 trailing sigma is followed over the "
            "next 4 bars differently when its quote activity, relative to "
            "the same hour of the week over the prior 8 weeks, is high than "
            "when it is low. CGW (1993) predict high-activity moves reverse "
            "more; Llorente et al. (2002) predict they continue. Two-sided."),
        market="FX majors, XAUUSD, XAGUSD, GER40", timeframe="H1",
        family=FAMILY, edge_gate_role=research_log.EdgeGateRole.UNSET,
        predictions=[
            f"{stream.name} < {stream.threshold}, two-sided, decides; "
            "h=1, h=12 and per-structure p are reported, never decisive",
            "ALIVE requires every structure's spread to share the pooled "
            "sign; ALIVE_POOLED_ONLY does not proceed",
            f"an instrument whose HIGH or LOW cell holds < {MIN_CELL_EVENTS} "
            "events is reported, not pooled; a structure with none is "
            "UNTESTED_STRUCTURE"],
        note=(
            "Phase 4's first mechanism, chosen by input class (tick activity) "
            "on 2026-10-12. Pre-registered before any outcome was computed: "
            "run() refuses until this entry exists. E-Ratio does not apply — "
            "the decisive stream is the gate. " + PRIOR_EXPOSURE + " Declared "
            "limitations: feed breaks before 2025-01 cannot be detected from "
            "tick flags and are not masked; XAUUSD's 2004-08 bars carry "
            "median 33-349 ticks, so its early activity ratios are coarse; "
            "activity terciles are cut on each instrument's full event set "
            "(activity only, no outcome), so the labels are descriptive, not "
            "a causal trading rule. Costs are not in this test; a live "
            "mechanism goes to costing (FX from fills, #68) before anything "
            "else."),
        universe=list(PANEL_2B),
        selection_rule=research_log.SelectionRule.POOLED_ALL,
        null_baseline_structure=NULL_BASELINE,
        benchmark_sharpe=0.0,
        min_decidable_sharpe=MIN_DECIDABLE_SHARPE,
        registry_snapshot=REGISTRY_SNAPSHOT,
        parameters=registration_parameters(),
        **kwargs,
    )

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--count", action="store_true",
                    help="event and cell counts only; reads no outcome")
    ap.add_argument("--preregister", action="store_true",
                    help="append the HYPOTHESIS event to the research log")
    ap.add_argument("--run", action="store_true",
                    help="the registered test; refuses before registration")
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    if args.count:
        print(json.dumps(count_events(args.data_dir), indent=1))
        return 0
    if args.preregister:
        entry = preregister()
        print(f"registered seq={entry.seq} {entry.hypothesis_id}")
        return 0
    if args.run:
        res = run(args.data_dir)
        text = json.dumps(res, indent=1, default=float)
        if args.out:
            args.out.write_text(text + "\n")
        print(res["verdict"], "—", res["reason"])
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
