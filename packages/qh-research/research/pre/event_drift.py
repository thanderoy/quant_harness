"""Phase 4 — does a scheduled release's first move carry on?

The second Phase 4 mechanism, and the first whose input is wholly outside the
price series: the timestamps of scheduled macro releases. Which bar is an
event is decided by a calendar compiled from central-bank and BLS pages
(``research/datasets/calendar/macro_events.csv``), never by anything the
market did.

**The claim.** On the H1 bar that contains a scheduled release, the direction
of that bar's move persists over the following bars more (or less) than the
same hour of the week does in weeks with no release. Information that arrives
at a known instant and is absorbed over hours — gradual diffusion — predicts
continuation; overshoot predicts reversal. Two-sided.

**The control is the same clock without the news.** Intraday momentum at
release hours exists with or without a release (seq 57-62 explored it on
gold), so an event's follow-through is compared with placebo bars at the same
hour of the week on the same instrument, drawn from other weeks within
``PLACEBO_WEEKS`` that hold no listed release within ``QUIET_HOURS``. The null
redraws every placebo set and recomputes the pooled statistic.

**Which releases reach which instrument** is fixed by currency, not by
result: US releases (FOMC, NFP, CPI) reach every panel instrument, because
each is USD-quoted or, for GER40, moves with US rates; ECB reaches EURUSD and
GER40; BoE reaches GBPUSD. BoJ is excluded because 156 of its 259 releases
have no published time and so no bar.

**Server time.** H1 bars are stamped in broker server time, which follows
Europe/Athens (EU DST). Checked on 2026-10-12 from bar spacing alone: gold's
New York-fixed daily break sits at server hour 0 in ordinary weeks and 23 in
the weeks when US and EU DST disagree, which only an EU-DST server clock
produces.

Nothing computes an outcome until the registration exists in the log.
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

from research.pre.activity_reversal import (load_h1, thin, trailing_moments,
                                            _admitted_frame, _two_sided_p,
                                            pooled_statistic)
from research.pre.decisive_stream import DecisiveStream, declare
from research.pre.normalizer_check import assert_disjoint
from research.pre.panel_edge import (MAJORS, PANEL_2B, STRUCTURE,
                                     _default_data_dir, build_panel_mask)

HYPOTHESIS_ID = "event_drift_h1"
FAMILY = "event_drift"

CALENDAR = (Path(__file__).resolve().parents[1] / "datasets" / "calendar"
            / "macro_events.csv")
SERVER_TZ = "Europe/Athens"

US_EVENTS = ("FOMC", "NFP", "CPI")
#: Which releases reach which instrument. Fixed by currency.
REACH: dict[str, tuple[str, ...]] = {
    **{s: US_EVENTS for s in PANEL_2B},
    "EURUSD": US_EVENTS + ("ECB",),
    "GER40": US_EVENTS + ("ECB",),
    "GBPUSD": US_EVENTS + ("BOE",),
}

SIGMA_BARS = 500
HORIZONS = (1, 4, 12)
DECISIVE_HORIZON = 4
#: Placebos come from the same hour of the week within this many weeks.
PLACEBO_WEEKS = 52
#: A placebo bar must be at least this far from any listed release.
QUIET_HOURS = 24
MIN_EVENTS = 100
N_PERMUTATIONS = 1000
RANDOM_SEED = 42
ALPHA = 0.05
#: Rejection rounds when redrawing a placebo whose week is ineligible.
MAX_REDRAWS = 50

STRUCTURES = ("fx", "metals", "equity_index")
STREAMS = frozenset(
    {f"pooled_p_h{h}" for h in HORIZONS}
    | {f"{s}_p_h{DECISIVE_HORIZON}" for s in STRUCTURES}
    | {f"pooled_p_h{DECISIVE_HORIZON}_verified_only"})
REGISTRY_SNAPSHOT = "pepperstone_live_20261009b.json"


def decisive_stream() -> DecisiveStream:
    return declare(
        f"pooled_p_h{DECISIVE_HORIZON}", ALPHA, set(STREAMS),
        rationale=(
            "The claim is that a scheduled release changes follow-through on "
            "three market structures, against the same clock without the "
            "news. Structures weigh equally, so seven FX pairs cannot carry "
            "it alone. h=4 is fixed now as the span in which diffusion or "
            "overshoot would play out within the session; h=1 and h=12, the "
            "per-structure p and the verified-times-only run are reported, "
            "never decisive. Two-sided: diffusion and overshoot predict "
            "opposite signs."))


def feature_spec() -> dict:
    spec = {"feature_inputs": {"calendar_timestamp"},
            "target_normalizer": {"close_logret_std"}}
    assert_disjoint(spec["feature_inputs"], spec["target_normalizer"],
                    name="event_bar")
    return {k: sorted(v) for k, v in spec.items()}


def load_calendar(path: Path = CALENDAR) -> pd.DataFrame:
    """Scheduled releases with a known time, as UTC timestamps."""
    cal = pd.read_csv(path)
    cal = cal[cal["scheduled"].astype(bool) & cal["time_known"].astype(bool)
              & cal["utc_datetime"].notna()].copy()
    cal["utc"] = pd.to_datetime(cal["utc_datetime"], utc=True)
    return cal[["event", "utc", "verified"]].reset_index(drop=True)


def server_bar(utc: pd.Series) -> pd.Series:
    """The server-time H1 bar label (naive, as in the CSVs) containing ``utc``."""
    local = utc.dt.tz_convert(SERVER_TZ).dt.tz_localize(None)
    return local.dt.floor("h")


def instrument_events(df: pd.DataFrame, tradable: np.ndarray,
                      cal: pd.DataFrame, reach: tuple[str, ...],
                      with_outcomes: bool = False) -> pd.DataFrame:
    """Event bars present in ``df``, thinned and clear of closures.

    ``df`` is indexed in server time localised as UTC (the house loader's
    convention); only the wall-clock labels are compared here.
    """
    labels = df.index.tz_localize(None)
    pos = pd.Series(np.arange(len(df)), index=labels)
    mine = cal[cal["event"].isin(reach)]
    bars = server_bar(mine["utc"])
    hit = bars.map(pos)
    keep = hit.notna()
    ev = pd.DataFrame({"pos": hit[keep].astype(int).to_numpy(),
                       "event": mine["event"][keep].to_numpy(),
                       "verified": mine["verified"][keep].astype(bool).to_numpy()})
    ev = ev.sort_values("pos").drop_duplicates("pos")
    return _with_outcomes(df, tradable, ev, with_outcomes)


def _forward_blocked(tradable: np.ndarray, h_max: int) -> np.ndarray:
    """Count of non-tradable bars in i+1 .. i+h_max, for each i."""
    n = tradable.size
    c = np.convolve((~tradable).astype(int), np.ones(h_max, int))[h_max:]
    return np.r_[c, np.ones(n - c.size, int)][:n]


def _bar_frame(df: pd.DataFrame, tradable: np.ndarray) -> pd.DataFrame:
    """Per-bar return, trailing moments and eligibility."""
    logc = np.log(df["close"].to_numpy(float))
    r = pd.Series(np.r_[np.nan, np.diff(logc)], index=df.index)
    ok = tradable & np.r_[False, tradable[:-1]]
    r[~ok] = np.nan
    mu, sigma = trailing_moments(r)
    n = len(df)
    base = (np.isfinite(r.to_numpy()) & np.isfinite(sigma.to_numpy())
            & (r.to_numpy() != 0))
    out = pd.DataFrame({"logc": logc, "r": r.to_numpy(), "mu": mu.to_numpy(),
                        "sigma": sigma.to_numpy(), "eligible": base})
    # A window must be clean only for the horizon it measures: a Friday
    # 15:00 NFP bar has 8 bars before the weekend, so requiring the longest
    # horizon's window everywhere would drop it from every horizon.
    for h in HORIZONS:
        out[f"clean_h{h}"] = (base & (np.arange(n) + h < n)
                              & (_forward_blocked(tradable, h) == 0))
    return out


def outcomes(bars: pd.DataFrame, pos: np.ndarray) -> dict[int, np.ndarray]:
    """Sign-aligned, drift-removed forward move in trailing-sigma units.

    NaN at a horizon whose window is not clean for that bar.
    """
    logc = bars["logc"].to_numpy()
    n = logc.size
    sign = np.sign(bars["r"].to_numpy()[pos])
    s, m = bars["sigma"].to_numpy()[pos], bars["mu"].to_numpy()[pos]
    out = {}
    for h in HORIZONS:
        clean = bars[f"clean_h{h}"].to_numpy()[pos]
        fwd = np.full(pos.size, np.nan)
        j = pos[clean]
        fwd[clean] = logc[np.minimum(j + h, n - 1)] - logc[j] - h * m[clean]
        out[h] = sign * fwd / s
    return out


def _with_outcomes(df: pd.DataFrame, tradable: np.ndarray, ev: pd.DataFrame,
                   with_outcomes: bool) -> pd.DataFrame:
    bars = _bar_frame(df, tradable)
    ev = ev[bars["clean_h1"].to_numpy()[ev["pos"].to_numpy()]]
    kept = thin(ev["pos"].to_numpy(), max(HORIZONS))
    ev = ev[ev["pos"].isin(kept)].reset_index(drop=True)
    if with_outcomes:
        for h, y in outcomes(bars, ev["pos"].to_numpy()).items():
            ev[f"y_h{h}"] = y
    return ev


def quiet_mask(index: pd.DatetimeIndex, cal: pd.DataFrame) -> np.ndarray:
    """True for bars at least ``QUIET_HOURS`` from every listed release."""
    labels = index.tz_localize(None).to_numpy("datetime64[ns]")
    ev = np.sort(server_bar(cal["utc"]).to_numpy("datetime64[ns]"))
    j = np.searchsorted(ev, labels)
    gap = np.full(labels.size, np.timedelta64(10**6, "h"))
    has_next = j < ev.size
    gap[has_next] = np.minimum(gap[has_next], ev[j[has_next]] - labels[has_next])
    has_prev = j > 0
    gap[has_prev] = np.minimum(gap[has_prev], labels[has_prev] - ev[j[has_prev] - 1])
    return gap >= np.timedelta64(QUIET_HOURS, "h")


def placebo_positions(index: pd.DatetimeIndex, event_pos: np.ndarray,
                      ok: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """One placebo per event: same hour of week, another week, eligible and quiet.

    Draws a week offset in [-PLACEBO_WEEKS, PLACEBO_WEEKS] \\ {0} and redraws
    those that land on an absent or ineligible bar. An event with no eligible
    placebo after ``MAX_REDRAWS`` rounds gets -1 and is dropped from that draw.
    """
    labels = index.tz_localize(None).to_numpy("datetime64[ns]")
    week = np.timedelta64(7 * 24, "h")
    out = np.full(event_pos.size, -1)
    todo = np.arange(event_pos.size)
    for _ in range(MAX_REDRAWS):
        if not todo.size:
            break
        k = rng.integers(1, PLACEBO_WEEKS + 1, todo.size)
        k = k * rng.choice((-1, 1), todo.size)
        target = labels[event_pos[todo]] + k * week
        j = np.searchsorted(labels, target)
        j = np.minimum(j, labels.size - 1)
        hit = (labels[j] == target) & ok[j]
        out[todo[hit]] = j[hit]
        todo = todo[~hit]
    return out


@dataclass
class InstrumentResult:
    symbol: str
    structure: str
    admitted_from: str
    n_events: int
    n_verified: int
    decidable: bool
    by_event: dict = field(default_factory=dict)
    mean_y: dict = field(default_factory=dict)


@dataclass
class _Prepared:
    index: pd.DatetimeIndex
    bars: pd.DataFrame
    events: pd.DataFrame
    #: Bars far from every release; combined per horizon with clean_h{h}.
    quiet: np.ndarray

    def placebo_ok(self, h: int) -> np.ndarray:
        return self.quiet & self.bars[f"clean_h{h}"].to_numpy()

    def events_for(self, h: int, verified_only: bool = False) -> pd.DataFrame:
        ev = self.events[np.isfinite(self.events[f"y_h{h}"])]
        return ev[ev["verified"]] if verified_only else ev


def _prepare(sym: str, data_dir: Path, cal: pd.DataFrame) -> tuple[_Prepared, str]:
    df, start = _admitted_frame(sym, data_dir)
    tradable = build_panel_mask(df.index).tradable.to_numpy()
    ev = instrument_events(df, tradable, cal, REACH[sym], with_outcomes=True)
    bars = _bar_frame(df, tradable)
    return _Prepared(df.index, bars, ev, quiet_mask(df.index, cal)), str(start.date())


def _event_stat(p: _Prepared, h: int, verified_only: bool = False) -> float:
    return float(p.events_for(h, verified_only)[f"y_h{h}"].mean())


def _placebo_stat(p: _Prepared, h: int, rng: np.random.Generator,
                  verified_only: bool = False) -> float:
    ev = p.events_for(h, verified_only)
    pos = placebo_positions(p.index, ev["pos"].to_numpy(), p.placebo_ok(h), rng)
    pos = pos[pos >= 0]
    return float(outcomes(p.bars, pos)[h].mean())


def placebo_test(prepared: dict[str, _Prepared], structure_of: dict[str, str],
                 h: int, n_permutations: int = N_PERMUTATIONS,
                 seed: int = RANDOM_SEED, verified_only: bool = False) -> dict:
    """Pooled event follow-through minus its placebo expectation, two-sided."""
    rng = np.random.default_rng(seed)
    obs = {s: _event_stat(p, h, verified_only) for s, p in prepared.items()}
    null = {s: np.array([_placebo_stat(p, h, rng, verified_only)
                         for _ in range(n_permutations)])
            for s, p in prepared.items()}
    centre = {s: float(v.mean()) for s, v in null.items()}
    excess = {s: obs[s] - centre[s] for s in obs}
    pooled, per = pooled_statistic(excess, structure_of)
    null_pooled = np.empty(n_permutations)
    null_per = {k: np.empty(n_permutations) for k in per}
    for i in range(n_permutations):
        d = {s: null[s][i] - centre[s] for s in null}
        p_i, per_i = pooled_statistic(d, structure_of)
        null_pooled[i] = p_i
        for k in per:
            null_per[k][i] = per_i[k]
    return {"observed": pooled, "p": _two_sided_p(null_pooled, pooled),
            "per_structure": {k: {"observed": v,
                                  "p": _two_sided_p(null_per[k], v)}
                              for k, v in per.items()},
            "per_instrument": excess, "per_instrument_raw": obs}


def verdict(result: dict, stream: DecisiveStream,
            tested: set[str]) -> tuple[str, str]:
    """Same conjoint rule as activity_reversal_h1 (seq=137)."""
    missing = [s for s in STRUCTURES if s not in tested]
    if missing:
        return "UNTESTED_STRUCTURE", f"no decidable instrument in {missing}"
    d = result[f"h{DECISIVE_HORIZON}"]
    passed, why = stream.verdict({stream.name: d["p"]})
    if passed == "FAIL":
        return "DEAD", why
    signs = {k: np.sign(v["observed"]) for k, v in d["per_structure"].items()}
    if all(s == np.sign(d["observed"]) for s in signs.values()):
        return "ALIVE", why
    return "ALIVE_POOLED_ONLY", f"{why}; structure signs {signs}"


def count_events(data_dir: Optional[Path] = None,
                 symbols: tuple[str, ...] = PANEL_2B) -> dict:
    """Event counts per instrument after admission, mask and thinning.

    Reads no forward outcome: ``instrument_events`` is called without them.
    """
    data_dir = Path(data_dir) if data_dir else _default_data_dir()
    cal = load_calendar()
    out = {}
    for sym in symbols:
        df, start = _admitted_frame(sym, data_dir)
        tradable = build_panel_mask(df.index).tradable.to_numpy()
        ev = instrument_events(df, tradable, cal, REACH[sym])
        bars = _bar_frame(df, tradable)
        pos = ev["pos"].to_numpy()
        d = ev[bars[f"clean_h{DECISIVE_HORIZON}"].to_numpy()[pos]]
        out[sym] = {"admitted_from": str(start.date()),
                    "n_events_by_h": {h: int(bars[f"clean_h{h}"].to_numpy()[pos].sum())
                                      for h in HORIZONS},
                    "n_verified_h4": int(d["verified"].sum()),
                    "by_event_h4": d["event"].value_counts().to_dict()}
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
    cal = load_calendar()
    prepared, insts = {}, []
    for sym in symbols:
        p, start = _prepare(sym, data_dir, cal)
        ev = p.events_for(DECISIVE_HORIZON)
        decidable = len(ev) >= MIN_EVENTS
        insts.append(InstrumentResult(
            sym, STRUCTURE[sym], start, len(ev), int(ev["verified"].sum()),
            decidable, by_event=ev["event"].value_counts().to_dict()))
        if decidable:
            prepared[sym] = p
    structure_of = {s: STRUCTURE[s] for s in prepared}
    result = {f"h{h}": placebo_test(prepared, structure_of, h, n_permutations)
              for h in HORIZONS}
    verified = placebo_test(prepared, structure_of, DECISIVE_HORIZON,
                            n_permutations, verified_only=True)
    for inst in insts:
        inst.mean_y = {h: result[f"h{h}"]["per_instrument"].get(inst.symbol)
                       for h in HORIZONS}
    stream = decisive_stream()
    label, why = verdict(result, stream, set(structure_of.values()))
    streams = {f"pooled_p_h{h}": result[f"h{h}"]["p"] for h in HORIZONS}
    streams.update({f"{k}_p_h{DECISIVE_HORIZON}": v["p"] for k, v in
                    result[f"h{DECISIVE_HORIZON}"]["per_structure"].items()})
    streams[f"pooled_p_h{DECISIVE_HORIZON}_verified_only"] = verified["p"]
    return {"hypothesis_id": HYPOTHESIS_ID, "verdict": label, "reason": why,
            "decisive_stream": stream.name, "streams": streams,
            "results": result, "verified_only_h4": verified,
            "instruments": [asdict(i) for i in insts],
            "n_permutations": n_permutations, "random_seed": RANDOM_SEED}


def registration_parameters() -> dict:
    stream = decisive_stream()
    return {
        "calendar": "research/datasets/calendar/macro_events.csv",
        "events_used": sorted({e for r in REACH.values() for e in r}),
        "reach_rule": {"US (FOMC, NFP, CPI)": "every panel instrument",
                       "ECB": "EURUSD, GER40", "BOE": "GBPUSD",
                       "BOJ": "excluded: 156/259 releases have no time"},
        "scheduled_only": True, "time_known_only": True,
        "server_tz": SERVER_TZ, "sigma_bars": SIGMA_BARS,
        "horizons": list(HORIZONS), "decisive_horizon": DECISIVE_HORIZON,
        "placebo_weeks": PLACEBO_WEEKS, "quiet_hours": QUIET_HOURS,
        "min_events": MIN_EVENTS, "n_permutations": N_PERMUTATIONS,
        "random_seed": RANDOM_SEED, "max_redraws": MAX_REDRAWS,
        "decisive_stream": stream.name, "decisive_threshold": stream.threshold,
        "decisive_rationale": stream.rationale, "two_sided": True,
        "streams_emitted": sorted(STREAMS), **feature_spec(),
        "mask": "panel_edge.build_panel_mask (WEEKEND_GAP 40h, HOLIDAY 24 bars)",
        "admission": "research.admission.require per instrument",
        "verdict_labels": ["ALIVE", "ALIVE_POOLED_ONLY", "DEAD",
                           "UNTESTED_STRUCTURE"],
    }


#: Decisive-horizon events on decidable instruments, from :func:`count_events`
#: on 2026-10-12 (3,979 at h=4, less NZDUSD's 46).
INTENDED_N_OBS = 3_933
#: ``min_decidable_sharpe(INTENDED_N_OBS, sr_star=0.0)``, normal moments.
MIN_DECIDABLE_SHARPE = 0.026236

NULL_BASELINE = (
    "Placebo bars: each event moved to the same hour of the week on the same "
    "instrument in a random other week within 52, at least 24h from any "
    "listed release and with a clean window for the horizon measured; 1000 "
    "draws, seed 42. The statistic is the event mean minus the placebo-draw "
    "mean; the null is the placebo draws centred the same way.")

PRIOR_EXPOSURE = (
    "Intraday momentum on XAUUSD H1 was explored at seq 57-62, including "
    "first-bar returns predicting the session; release hours were inside "
    "those samples but were never separated out. The calendar was compiled "
    "by a subagent barred from price data; it reported incidental exposure "
    "to text about market reactions: BoE minutes on gilts and sterling after "
    "the 2020-03-19 special meeting, a transcript line on Treasury yields "
    "around 2:15 p.m. FOMC statements, decision outcomes in page titles, and "
    "one CPI figure (Dec 2004). None bears on the instruments' H1 "
    "follow-through, and none changed which rows the calendar holds. Before "
    "this registration only integrity and counts were read: the server DST "
    "rule from bar spacing, and event counts per horizon.")


def preregister(log_dir: Optional[Path] = None):
    """Append the HYPOTHESIS event. Must precede :func:`run`."""
    from research import log as research_log
    stream = decisive_stream()
    kwargs = {"log_dir": log_dir} if log_dir is not None else {}
    return research_log.register_hypothesis(
        HYPOTHESIS_ID,
        title=("Scheduled-release follow-through on H1, against the same "
               "clock without the news, across FX, metals and GER40"),
        mechanism=(
            "On the H1 bar containing a scheduled FOMC, NFP, CPI, ECB or BoE "
            "release, the bar's direction persists over the next 4 bars "
            "differently from placebo bars at the same hour of the week in "
            "release-free weeks. Gradual diffusion predicts continuation; "
            "overshoot predicts reversal. Two-sided."),
        market="FX majors, XAUUSD, XAGUSD, GER40", timeframe="H1",
        family=FAMILY, edge_gate_role=research_log.EdgeGateRole.UNSET,
        predictions=[
            f"{stream.name} < {stream.threshold}, two-sided, decides; h=1, "
            "h=12, per-structure p and the verified-times-only run are "
            "reported, never decisive",
            "ALIVE requires every structure's excess to share the pooled "
            "sign; ALIVE_POOLED_ONLY does not proceed",
            f"an instrument with < {MIN_EVENTS} events at h=4 is reported, "
            "not pooled (NZDUSD, 46); a structure with none is "
            "UNTESTED_STRUCTURE"],
        note=(
            "Phase 4's second mechanism (input class event/calendar, chosen "
            "2026-10-12) after activity_reversal_h1 died at seq=138. "
            "Pre-registered before any outcome was computed; run() refuses "
            "until this entry exists. E-Ratio does not apply. Calendar: "
            "1,438 official-source releases 2004-06..2026-10; scheduled and "
            "time-known only; BoJ excluded (no times). 384 calendar rows are "
            "verified=false: the date is confirmed and the time is the "
            "central bank's documented standard practice (ECB before "
            "2022-06, BoE before 2015-08, FOMC 2004-10). " + PRIOR_EXPOSURE +
            " A forward window must be clean only for its own horizon, "
            "because a Friday 15:00-server NFP bar has 8 bars before the "
            "weekend; requiring the 12-bar window everywhere had dropped "
            "NFP from every horizon in the first count, and this was fixed "
            "from counts alone, before any outcome existed. Costs are not in "
            "this test; FX costs come from fills (#68)."),
        universe=list(PANEL_2B),
        selection_rule=research_log.SelectionRule.POOLED_ALL,
        null_baseline_structure=NULL_BASELINE,
        benchmark_sharpe=0.0,
        min_decidable_sharpe=MIN_DECIDABLE_SHARPE,
        registry_snapshot=REGISTRY_SNAPSHOT,
        parameters=registration_parameters(),
        **kwargs,
    )


def log_result(res: dict, artifact: str, log_dir: Optional[Path] = None,
               extra_note: str = ""):
    """Record a :func:`run` result against the registration. Not a trial."""
    from research import log as research_log
    kwargs = {"log_dir": log_dir} if log_dir is not None else {}
    h = res["results"]
    return research_log.update_hypothesis(
        HYPOTHESIS_ID,
        stage=research_log.Stage.SIGNAL_EDGE,
        verdict=(research_log.Verdict.OPEN if res["verdict"] == "ALIVE"
                 else research_log.Verdict.KILLED),
        metrics={
            "verdict": res["verdict"], "reason": res["reason"],
            "artifact": artifact, "streams": res["streams"],
            "pooled_excess_sigma": {k: v["observed"] for k, v in h.items()},
            "per_structure_h4": h[f"h{DECISIVE_HORIZON}"]["per_structure"],
            "per_instrument_excess_sigma": {
                i["symbol"]: i["mean_y"] for i in res["instruments"]},
            "n_events_h4": {i["symbol"]: i["n_events"]
                            for i in res["instruments"]},
        },
        note=(
            f"Registered run: {res['verdict']} ({res['reason']}). Decided by "
            "the pre-declared stream alone. Excess is the event bars' mean "
            "sign-aligned, drift-removed forward move minus the placebo "
            "mean, in trailing-sigma units; positive is continuation."
            + (" " + extra_note if extra_note else "")),
        **kwargs,
    )

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--count", action="store_true",
                    help="event counts only; reads no outcome")
    ap.add_argument("--preregister", action="store_true",
                    help="append the HYPOTHESIS event to the research log")
    ap.add_argument("--log-artifact", type=Path, default=None,
                    help="record a saved --run artifact against the registration")
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
    if args.log_artifact:
        res = json.loads(args.log_artifact.read_text())
        entry = log_result(res, args.log_artifact.name)
        print(f"logged seq={entry.seq} {res['verdict']}")
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
