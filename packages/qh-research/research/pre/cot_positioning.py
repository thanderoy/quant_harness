"""Phase 4 — do speculators' positioning extremes predict the next week?

The third Phase 4 mechanism. Its input is the CFTC Commitments of Traders
report: what large speculators hold, published weekly. It is not derived from
the instruments' prices, and it is public only after a lag, which is the whole
difficulty of using it honestly.

**The claim.** When speculators' net position in an instrument is extreme
against its own recent history, the instrument's move until the next report
is different from when it is not. The common claim is contrarian — crowded
positioning unwinds — and the opposite, that positioning persists, is equally
on record. Two-sided.

**Speculators** are leveraged funds in the Traders in Financial Futures
report (FX, E-mini S&P) and managed money in the Disaggregated report
(gold, silver). Their net position is taken as a share of open interest, so
a contract's growth over twenty years is not read as conviction.

**Point in time is enforced three ways.**

* A report is used from ``release_conservative_utc`` — the actual release
  where the CFTC published one, including shutdown and cyber-incident
  catch-ups up to 1,634 days late, and otherwise the standard Friday 15:30 ET
  pushed past federal holidays.
* Reports dated before each report type existed are excluded, not merely
  delayed: the CFTC backcast those category splits using later information,
  so they were never knowable (:data:`LAUNCH`).
* The z-score uses only reports dated before the one being scored.

**Orientation.** CME currency futures are quoted as foreign currency in USD,
so speculators long the JPY, CHF or CAD contract are short USDJPY, USDCHF and
USDCAD; the signal's sign is flipped for those (:data:`MARKETS`).

**GER40 has no COT report** (Eurex is outside CFTC jurisdiction); E-mini S&P
positioning stands in for it, by the owner's ruling of 2026-10-13. The equity
leg is a cross-market proxy and is weaker by construction.

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

from research.pre.activity_reversal import (_admitted_frame, _rotate,
                                            _two_sided_p, label_terciles,
                                            pooled_statistic)
from research.pre.decisive_stream import DecisiveStream, declare
from research.pre.normalizer_check import assert_disjoint
from research.pre.panel_edge import PANEL_2B, STRUCTURE, _default_data_dir

HYPOTHESIS_ID = "cot_positioning_extremes"
FAMILY = "cot_positioning"

COT = (Path(__file__).resolve().parents[1] / "datasets" / "cot"
       / "cot_positions.csv")
SERVER_TZ = "Europe/Athens"

#: instrument -> (COT market key, orientation). Orientation turns
#: "speculators long the futures contract" into "long the instrument".
MARKETS: dict[str, tuple[str, int]] = {
    "EURUSD": ("EUR", 1), "GBPUSD": ("GBP", 1), "AUDUSD": ("AUD", 1),
    "NZDUSD": ("NZD", 1), "USDJPY": ("JPY", -1), "USDCHF": ("CHF", -1),
    "USDCAD": ("CAD", -1), "XAUUSD": ("XAU", 1), "XAGUSD": ("XAG", 1),
    "GER40": ("ES", 1),
}
#: First report date each report type was published live. Earlier rows were
#: backcast with later classification information and are excluded.
LAUNCH = {"TFF": "2010-07-20", "DISAGG": "2009-09-01"}
#: Speculator columns per report type.
SPEC = {"TFF": ("lev_money_long", "lev_money_short"),
        "DISAGG": ("m_money_long", "m_money_short")}

Z_WINDOW = 156          # reports, about three years
Z_MIN = 104             # at least two years before a z-score exists
RET_WINDOW = 52         # intervals for the outcome's trailing moments
RET_MIN = 40
HORIZONS = (1, 4)       # in report intervals; 1 does not overlap
DECISIVE_HORIZON = 1
MIN_CELL = 50
N_PERMUTATIONS = 1000
RANDOM_SEED = 42
ALPHA = 0.05

STRUCTURES = ("fx", "metals", "equity_index")
STREAMS = frozenset(
    {f"pooled_p_h{h}" for h in HORIZONS}
    | {f"{s}_p_h{DECISIVE_HORIZON}" for s in STRUCTURES})
REGISTRY_SNAPSHOT = "pepperstone_live_20261009b.json"


def decisive_stream() -> DecisiveStream:
    return declare(
        f"pooled_p_h{DECISIVE_HORIZON}", ALPHA, set(STREAMS),
        rationale=(
            "The claim is that positioning extremes change the next "
            "interval's move on three market structures. h=1 is the only "
            "horizon whose outcomes do not overlap — each runs from one "
            "release to the next — so it is the only one whose null is not "
            "flattered by overlap; h=4 and the per-structure p are reported, "
            "never decisive. Two-sided: contrarian and persistence are both "
            "on record."))


def feature_spec() -> dict:
    spec = {"feature_inputs": {"cftc_positions", "cftc_open_interest"},
            "target_normalizer": {"interval_logret_std"}}
    assert_disjoint(spec["feature_inputs"], spec["target_normalizer"],
                    name="positioning_z")
    return {k: sorted(v) for k, v in spec.items()}


def load_cot(path: Path = COT) -> pd.DataFrame:
    cot = pd.read_csv(path)
    cot["report_date"] = pd.to_datetime(cot["report_date"])
    cot["release"] = pd.to_datetime(cot["release_conservative_utc"], utc=True)
    return cot


def positioning_z(cot: pd.DataFrame, market: str, orientation: int) -> pd.DataFrame:
    """One market's oriented positioning z-score, by report, with release time.

    The z-score at report t uses reports t-Z_WINDOW .. t-1 only.
    """
    m = cot[cot["market"] == market].sort_values("report_date")
    report = m["report"].iloc[0]
    m = m[m["report_date"] >= pd.Timestamp(LAUNCH[report])]
    lo, sh = SPEC[report]
    share = (m[lo] - m[sh]) / m["open_interest"]
    prior = share.shift(1).rolling(Z_WINDOW, min_periods=Z_MIN)
    z = (share - prior.mean()) / prior.std()
    return pd.DataFrame({"report_date": m["report_date"].to_numpy(),
                         "release": m["release"].to_numpy(),
                         "signal": orientation * z.to_numpy()})


def entry_positions(index: pd.DatetimeIndex, release: pd.Series) -> np.ndarray:
    """Bar whose close is the first close at or after each release.

    ``index`` holds server-time labels (localised as UTC by the house
    loader); a bar labelled t closes at t + 1h. -1 where no bar qualifies.
    """
    labels = index.tz_localize(None).to_numpy("datetime64[ns]")
    rel = (pd.DatetimeIndex(release).tz_convert(SERVER_TZ).tz_localize(None)
           .to_numpy("datetime64[ns]"))
    close_t = labels + np.timedelta64(1, "h")
    j = np.searchsorted(close_t, rel, side="left")
    return np.where(j < labels.size, j, -1)


def interval_frame(df: pd.DataFrame, sig: pd.DataFrame) -> pd.DataFrame:
    """One row per report interval inside ``df``, signal possibly NaN.

    No outcome is computed here.
    """
    pos = entry_positions(df.index, sig["release"])
    keep = pos > 0
    out = sig[keep].copy()
    out["pos"] = pos[keep]
    return out.drop_duplicates("pos", keep="last").reset_index(drop=True)


def add_outcomes(df: pd.DataFrame, fr: pd.DataFrame) -> pd.DataFrame:
    """Attach y_h: the log return over h intervals from each row's entry,
    less h times the trailing mean interval return, over the trailing
    interval std scaled by sqrt(h). Computed over every row of ``fr``.
    """
    fr = fr.copy()
    logc = np.log(df["close"].to_numpy(float))
    p = fr["pos"].to_numpy()
    r1 = np.r_[logc[p[1:]] - logc[p[:-1]], np.nan]
    prior = pd.Series(r1).shift(1).rolling(RET_WINDOW, min_periods=RET_MIN)
    mu, sd = prior.mean().to_numpy(), prior.std().to_numpy()
    for h in HORIZONS:
        fwd = pd.Series(r1).rolling(h).sum().shift(-(h - 1)).to_numpy()
        fr[f"y_h{h}"] = (fwd - h * mu) / (sd * np.sqrt(h))
    return fr


def outcome_available(n: int) -> np.ndarray:
    """Rows whose decisive outcome will exist, from position alone.

    y_h1 needs a next interval and RET_MIN prior intervals; nothing about
    their values. Lets a count match a run without computing an outcome.
    """
    i = np.arange(n)
    return (i >= RET_MIN + 1) & (i < n - 1)


def instrument_frame(df: pd.DataFrame, sig: pd.DataFrame,
                     with_outcomes: bool = False) -> pd.DataFrame:
    """Interval rows with a finite signal, and outcomes when asked."""
    fr = interval_frame(df, sig)
    if not with_outcomes:
        return fr[np.isfinite(fr["signal"])].reset_index(drop=True)
    fr = add_outcomes(df, fr)
    ok = np.isfinite(fr["signal"]) & np.isfinite(fr[f"y_h{DECISIVE_HORIZON}"])
    return fr[ok].reset_index(drop=True)


def _spread(y: np.ndarray, labels: np.ndarray) -> float:
    ok = np.isfinite(y)
    return float(y[ok & (labels == 2)].mean() - y[ok & (labels == 0)].mean())


def rotation_test(frames: dict[str, pd.DataFrame], labels: dict[str, np.ndarray],
                  structure_of: dict[str, str], h: int,
                  n_permutations: int = N_PERMUTATIONS,
                  seed: int = RANDOM_SEED) -> dict:
    """HIGH-minus-LOW tercile spread, pooled by structure, rotation null."""
    rng = np.random.default_rng(seed)
    col = f"y_h{h}"
    obs = {s: _spread(frames[s][col].to_numpy(), labels[s]) for s in frames}
    pooled, per = pooled_statistic(obs, structure_of)
    null_pooled = np.empty(n_permutations)
    null_per = {k: np.empty(n_permutations) for k in per}
    for i in range(n_permutations):
        sp = {s: _spread(frames[s][col].to_numpy(), _rotate(labels[s], rng))
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
    """Same conjoint rule as seq=137 and seq=139."""
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


@dataclass
class InstrumentResult:
    symbol: str
    structure: str
    cot_market: str
    admitted_from: str
    n_intervals: int
    min_cell: int
    decidable: bool
    spread: dict = field(default_factory=dict)


def count_intervals(data_dir: Optional[Path] = None,
                    symbols: tuple[str, ...] = PANEL_2B) -> dict:
    """Usable intervals and tercile cells per instrument. Reads no outcome."""
    data_dir = Path(data_dir) if data_dir else _default_data_dir()
    cot = load_cot()
    out = {}
    for sym in symbols:
        market, orient = MARKETS[sym]
        df, start = _admitted_frame(sym, data_dir)
        fr = instrument_frame(df, positioning_z(cot, market, orient))
        lab = label_terciles(fr["signal"]) if len(fr) >= 3 else np.array([])
        out[sym] = {"cot_market": market, "admitted_from": str(start.date()),
                    "n_intervals": len(fr),
                    "min_cell": int(min((lab == 0).sum(), (lab == 2).sum()))
                    if lab.size else 0,
                    "first_report": str(fr["report_date"].min().date())
                    if len(fr) else None}
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
    cot = load_cot()
    frames, labels, insts = {}, {}, []
    for sym in symbols:
        market, orient = MARKETS[sym]
        df, start = _admitted_frame(sym, data_dir)
        fr = instrument_frame(df, positioning_z(cot, market, orient),
                              with_outcomes=True)
        lab = label_terciles(fr["signal"])
        cell = int(min((lab == 0).sum(), (lab == 2).sum()))
        decidable = cell >= MIN_CELL
        insts.append(InstrumentResult(sym, STRUCTURE[sym], market,
                                      str(start.date()), len(fr), cell,
                                      decidable))
        if decidable:
            frames[sym], labels[sym] = fr, lab
    structure_of = {s: STRUCTURE[s] for s in frames}
    result = {f"h{h}": rotation_test(frames, labels, structure_of, h,
                                     n_permutations) for h in HORIZONS}
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
    stream = decisive_stream()
    return {
        "cot": "research/datasets/cot/cot_positions.csv",
        "markets": {k: list(v) for k, v in MARKETS.items()},
        "speculators": {"tff": "leveraged funds",
                        "disaggregated": "managed money"},
        "launch_exclusion": LAUNCH,
        "release_column": "release_conservative_utc",
        "signal": "oriented net share of open interest, z over prior 156 reports (min 104)",
        "outcome": "release-to-release log return, drift-removed, over trailing 52-interval std (min 40)",
        "server_tz": SERVER_TZ, "horizons": list(HORIZONS),
        "decisive_horizon": DECISIVE_HORIZON, "min_cell": MIN_CELL,
        "n_permutations": N_PERMUTATIONS, "random_seed": RANDOM_SEED,
        "decisive_stream": stream.name, "decisive_threshold": stream.threshold,
        "decisive_rationale": stream.rationale, "two_sided": True,
        "streams_emitted": sorted(STREAMS), **feature_spec(),
        "admission": "research.admission.require per instrument",
        "ger40_proxy": "E-mini S&P 500 positioning (owner ruling 2026-10-13)",
        "verdict_labels": ["ALIVE", "ALIVE_POOLED_ONLY", "DEAD",
                           "UNTESTED_STRUCTURE"],
    }


#: Decisive intervals on decidable instruments, from :func:`count_intervals`
#: on 2026-10-13 (NZDUSD's 84 excluded: 28 per cell).
INTENDED_N_OBS = 5_771
#: ``min_decidable_sharpe(INTENDED_N_OBS, sr_star=0.0)``, normal moments.
MIN_DECIDABLE_SHARPE = 0.021657

NULL_BASELINE = (
    "Per-instrument circular rotation of the tercile-label sequence by a "
    "random offset in [n/10, 9n/10], 1000 draws, seed 42; pooled statistic "
    "recomputed identically. Keeps positioning's strong autocorrelation and "
    "each instrument's outcome series; breaks only their alignment.")

DECLARED = (
    "Positioning is weekly, so power is low: in synthetic checks a planted "
    "effect needs to be large to clear 0.05 on ~300 intervals per "
    "instrument, and the real panel has 430-780. A DEAD verdict here is "
    "weaker evidence of absence than seq=138's. Prior exposure: none of "
    "this repo's work has used positioning data; the dataset was built by a "
    "subagent barred from price data, which reported no incidental "
    "exposure. Before this registration only counts and point-in-time "
    "properties were read. GER40 uses E-mini S&P positioning by the owner's "
    "ruling (no CFTC report covers Eurex). Reports dated before each report "
    "type's launch are excluded because their categories were backcast. "
    "release_conservative_utc is the CFTC's actual release where known and "
    "otherwise Friday 15:30 ET pushed past federal holidays; 7,749 of "
    "10,607 rows rely on that rule because the CFTC does not host past "
    "schedules.")


def preregister(log_dir: Optional[Path] = None):
    """Append the HYPOTHESIS event. Must precede :func:`run`."""
    from research import log as research_log
    stream = decisive_stream()
    kwargs = {"log_dir": log_dir} if log_dir is not None else {}
    return research_log.register_hypothesis(
        HYPOTHESIS_ID,
        title=("Speculator positioning extremes and the next report "
               "interval, across FX, metals and GER40"),
        mechanism=(
            "When speculators' net position (leveraged funds, or managed "
            "money for metals) as a share of open interest is extreme "
            "against its prior three years, the instrument's move from that "
            "report's release to the next differs between the high and low "
            "terciles. Contrarian unwinding and persistence predict "
            "opposite signs. Two-sided."),
        market="FX majors, XAUUSD, XAGUSD, GER40 (via ES)", timeframe="H1",
        family=FAMILY, edge_gate_role=research_log.EdgeGateRole.UNSET,
        predictions=[
            f"{stream.name} < {stream.threshold}, two-sided, decides; h=4 "
            "(overlapping) and per-structure p are reported, never decisive",
            "ALIVE requires every structure's spread to share the pooled "
            "sign; ALIVE_POOLED_ONLY does not proceed",
            f"an instrument with < {MIN_CELL} intervals in its HIGH or LOW "
            "tercile is reported, not pooled (NZDUSD, 28)"],
        note=("Phase 4's third mechanism (input class COT positioning, "
              "chosen 2026-10-13; signal: extremes, chosen the same day). "
              "Pre-registered before any outcome was computed; run() "
              "refuses until this entry exists. " + DECLARED +
              " Costs are not in this test."),
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
            "pooled_spread": {k: v["observed"] for k, v in h.items()},
            "per_structure_h1": h[f"h{DECISIVE_HORIZON}"]["per_structure"],
            "per_instrument_spread": {i["symbol"]: i["spread"]
                                      for i in res["instruments"]},
            "n_intervals": {i["symbol"]: i["n_intervals"]
                            for i in res["instruments"]},
        },
        note=(f"Registered run: {res['verdict']} ({res['reason']}). Decided "
              "by the pre-declared stream alone. Spread is mean(HIGH) - "
              "mean(LOW) of the drift-removed interval return in trailing-"
              "std units, signal oriented to the instrument; positive is "
              "persistence, negative contrarian."
              + (" " + extra_note if extra_note else "")),
        **kwargs,
    )

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--count", action="store_true",
                    help="interval and cell counts only; reads no outcome")
    ap.add_argument("--preregister", action="store_true",
                    help="append the HYPOTHESIS event to the research log")
    ap.add_argument("--run", action="store_true",
                    help="the registered test; refuses before registration")
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    if args.count:
        print(json.dumps(count_intervals(args.data_dir), indent=1))
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
