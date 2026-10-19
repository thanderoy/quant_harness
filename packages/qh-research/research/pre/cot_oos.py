"""Phase 4 — COT positioning, out of sample, on raw returns.

seq=142 and seq=144 found speculator positioning predictive and seq=146
withdrew both: the outcome subtracted a trailing 52-interval mean, and the
trend-following signal correlates with that mean, so most of the contrarian
spread was the drift term. On raw returns only GBPUSD and USDCAD leaned
contrarian. Nothing about positioning is established.

This is the test that can still settle it: the same signal, scored on reports
that did not exist when the design was fixed, against the raw release-to-
release return.

**What changes from seq=141.**

* **Outcome.** Raw log return from one release's entry bar to the next, over
  the trailing 52-interval std. Scaled, never centred: the scale is positive,
  so it cannot manufacture a sign the way the subtracted mean did.
* **Sample.** Only reports dated after :data:`IN_SAMPLE_LAST_REPORT`, the last
  report in the dataset committed with seq=146. The z-score's history window
  still reaches back into the in-sample reports; that is causal, and the
  signal definition is unchanged.
* **Statistic.** About 52 reports a year cannot fill tercile cells of 50, so
  the per-instrument statistic is the mean product of signal and outcome — a
  correlation, since both are unit-scaled. Pooled by structure as before.
* **Universe.** All ten instruments, NZDUSD included: a continuous statistic
  has no cell-occupancy floor.

**One look, fixed now.** :func:`run` refuses until every instrument holds
:data:`OOS_MIN_INTERVALS` scored intervals and the date is past
:data:`EARLIEST_RUN`. :func:`count_oos` reads no outcome and may be run at any
time.

**Before the run** the dataset and price files have to be extended, and
neither can be done now because the data does not exist yet:

* rebuild ``cot_positions.csv`` with ``build_cot.py`` from the CFTC's 2026 and
  2027 files, after saving the 2027 release-schedule page and any delay
  announcements to ``raw/schedule/`` (the CFTC does not host past years'
  schedules, so the 2027 page must be saved while it is live);
* re-dump the ten H1 files from the live terminal (GET-only) past the last
  scored release.

Rows that :func:`check_dataset_extension` finds changed in the in-sample part
of the dataset stop the run: the extension must append, never revise.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from research.pre import cot_positioning as cp
from research.pre.activity_reversal import _admitted_frame, _rotate, _two_sided_p, pooled_statistic
from research.pre.decisive_stream import DecisiveStream, declare
from research.pre.panel_edge import PANEL_2B, STRUCTURE, _default_data_dir

HYPOTHESIS_ID = "cot_positioning_oos"
FAMILY = cp.FAMILY

#: The last report in the dataset committed with seq=146 (released 2026-10-09).
IN_SAMPLE_LAST_REPORT = "2026-10-06"
#: sha256 of that dataset's rows dated on or before IN_SAMPLE_LAST_REPORT, in
#: file order, as written by :func:`in_sample_digest`.
IN_SAMPLE_DIGEST = "1fd14379b2d43a489609b6db0065663383ecd3789072534da9ceae7c03932c3c"
OOS_MIN_INTERVALS = 52
EARLIEST_RUN = "2027-10-18"
RET_WINDOW = cp.RET_WINDOW
RET_MIN = cp.RET_MIN
N_PERMUTATIONS = 1000
RANDOM_SEED = 42
ALPHA = 0.05

STRUCTURES = cp.STRUCTURES
STREAMS = frozenset({"pooled_p"} | {f"{s}_p" for s in STRUCTURES})
REGISTRY_SNAPSHOT = cp.REGISTRY_SNAPSHOT


def decisive_stream() -> DecisiveStream:
    return declare(
        "pooled_p", ALPHA, set(STREAMS),
        rationale=(
            "The claim is the same as seq=141: positioning extremes predict "
            "the next interval on three market structures, weighted equally "
            "so seven FX pairs cannot carry it alone. Two-sided, because the "
            "in-sample sign came from the withdrawn drift term and is not a "
            "prior. Per-structure p is reported, never decisive."))


def feature_spec() -> dict:
    return cp.feature_spec()


def in_sample_digest(cot: pd.DataFrame) -> str:
    """sha256 over the in-sample rows' identity and positions, file order."""
    cols = ["market", "report_date", "open_interest", "lev_money_long",
            "lev_money_short", "m_money_long", "m_money_short",
            "release_conservative_utc"]
    rows = cot[pd.to_datetime(cot["report_date"])
               <= pd.Timestamp(IN_SAMPLE_LAST_REPORT)][cols]
    text = rows.astype(str).to_csv(index=False)
    return hashlib.sha256(text.encode()).hexdigest()


def check_dataset_extension(cot: pd.DataFrame) -> None:
    """Raise if the in-sample part of ``cot`` differs from the committed one."""
    got = in_sample_digest(cot)
    if got != IN_SAMPLE_DIGEST:
        raise RuntimeError(
            f"in-sample COT rows changed (digest {got[:12]} != "
            f"{IN_SAMPLE_DIGEST[:12]}); an extension must append only")


def add_raw_outcome(df: pd.DataFrame, fr: pd.DataFrame) -> pd.DataFrame:
    """Attach y: the next interval's log return over the trailing std.

    Never centred. The std uses intervals before the scored one only.
    """
    fr = fr.copy()
    logc = np.log(df["close"].to_numpy(float))
    p = fr["pos"].to_numpy()
    r1 = np.r_[logc[p[1:]] - logc[p[:-1]], np.nan]
    sd = pd.Series(r1).shift(1).rolling(RET_WINDOW, min_periods=RET_MIN).std()
    fr["y"] = r1 / sd.to_numpy()
    return fr


def oos_rows(fr: pd.DataFrame) -> np.ndarray:
    """Rows dated after the in-sample cut whose next interval will exist.

    Decided from dates and position alone, so a count can match a run.
    """
    after = (pd.to_datetime(fr["report_date"])
             > pd.Timestamp(IN_SAMPLE_LAST_REPORT)).to_numpy()
    has_next = np.arange(len(fr)) < len(fr) - 1
    return after & has_next & np.isfinite(fr["signal"].to_numpy(float))


def instrument_frame(df: pd.DataFrame, sig: pd.DataFrame,
                     with_outcomes: bool = False) -> pd.DataFrame:
    """Out-of-sample interval rows, with the raw outcome when asked.

    The trailing std is computed over every interval, in-sample included,
    before the out-of-sample rows are kept.
    """
    fr = cp.interval_frame(df, sig)
    keep = oos_rows(fr)
    if with_outcomes:
        fr = add_raw_outcome(df, fr)
        keep &= np.isfinite(fr["y"].to_numpy(float))
    return fr[keep].reset_index(drop=True)


def _product(x: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean(x * y))


def rotation_test(frames: dict[str, pd.DataFrame], structure_of: dict[str, str],
                  n_permutations: int = N_PERMUTATIONS,
                  seed: int = RANDOM_SEED) -> dict:
    """Mean signal x outcome, pooled by structure; rotation null on signal."""
    rng = np.random.default_rng(seed)
    xs = {s: f["signal"].to_numpy(float) for s, f in frames.items()}
    ys = {s: f["y"].to_numpy(float) for s, f in frames.items()}
    obs = {s: _product(xs[s], ys[s]) for s in frames}
    pooled, per = pooled_statistic(obs, structure_of)
    null_pooled = np.empty(n_permutations)
    null_per = {k: np.empty(n_permutations) for k in per}
    for i in range(n_permutations):
        sp = {s: _product(_rotate(xs[s], rng), ys[s]) for s in frames}
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
    """seq=141's conjoint rule, on the out-of-sample statistic."""
    missing = [s for s in STRUCTURES if s not in tested]
    if missing:
        return "UNTESTED_STRUCTURE", f"no instrument in {missing}"
    passed, why = stream.verdict({stream.name: result["p"]})
    if passed == "FAIL":
        return "DEAD", why
    signs = {k: np.sign(v["observed"]) for k, v in result["per_structure"].items()}
    if all(s == np.sign(result["observed"]) for s in signs.values()):
        return "ALIVE", why
    return "ALIVE_POOLED_ONLY", f"{why}; structure signs {signs}"


@dataclass
class InstrumentResult:
    symbol: str
    structure: str
    cot_market: str
    n_intervals: int
    statistic: Optional[float] = None
    extra: dict = field(default_factory=dict)


def count_oos(data_dir: Optional[Path] = None,
              symbols: tuple[str, ...] = PANEL_2B,
              cot: Optional[pd.DataFrame] = None) -> dict:
    """Out-of-sample intervals per instrument so far. Reads no outcome."""
    data_dir = Path(data_dir) if data_dir else _default_data_dir()
    cot = cp.load_cot() if cot is None else cot
    out = {}
    for sym in symbols:
        market, orient = cp.MARKETS[sym]
        df, _ = _admitted_frame(sym, data_dir)
        fr = instrument_frame(df, cp.positioning_z(cot, market, orient))
        out[sym] = {"cot_market": market, "n_intervals": len(fr),
                    "last_report": (str(pd.Timestamp(fr["report_date"].max()).date())
                                    if len(fr) else None)}
    return out


def _registered(log_dir: Optional[Path]) -> bool:
    from research import log as research_log
    kwargs = {"log_dir": log_dir} if log_dir is not None else {}
    return bool(research_log.history(HYPOTHESIS_ID, **kwargs))


def ready(counts: dict, today: pd.Timestamp) -> tuple[bool, str]:
    """Whether the single look may be taken."""
    if today < pd.Timestamp(EARLIEST_RUN):
        return False, f"before {EARLIEST_RUN}"
    short = {s: c["n_intervals"] for s, c in counts.items()
             if c["n_intervals"] < OOS_MIN_INTERVALS}
    if short:
        return False, f"fewer than {OOS_MIN_INTERVALS} intervals: {short}"
    return True, "ready"


def run(data_dir: Optional[Path] = None, log_dir: Optional[Path] = None,
        symbols: tuple[str, ...] = PANEL_2B,
        n_permutations: int = N_PERMUTATIONS,
        today: Optional[pd.Timestamp] = None) -> dict:
    """The registered test, taken once. Refuses early or unregistered."""
    if not _registered(log_dir):
        raise RuntimeError(
            f"{HYPOTHESIS_ID!r} is not registered in the research log; "
            "register it before any outcome is computed.")
    data_dir = Path(data_dir) if data_dir else _default_data_dir()
    cot = cp.load_cot()
    check_dataset_extension(pd.read_csv(cp.COT))
    ok, why = ready(count_oos(data_dir, symbols, cot),
                    today if today is not None else pd.Timestamp.now())
    if not ok:
        raise RuntimeError(f"{HYPOTHESIS_ID}: not ready ({why})")
    frames, insts = {}, []
    for sym in symbols:
        market, orient = cp.MARKETS[sym]
        df, _ = _admitted_frame(sym, data_dir)
        fr = instrument_frame(df, cp.positioning_z(cot, market, orient),
                              with_outcomes=True)
        frames[sym] = fr
        insts.append(InstrumentResult(sym, STRUCTURE[sym], market, len(fr)))
    structure_of = {s: STRUCTURE[s] for s in frames}
    result = rotation_test(frames, structure_of, n_permutations)
    for inst in insts:
        inst.statistic = result["per_instrument"][inst.symbol]
    stream = decisive_stream()
    label, why = verdict(result, stream, set(structure_of.values()))
    streams = {"pooled_p": result["p"]}
    streams.update({f"{k}_p": v["p"] for k, v in result["per_structure"].items()})
    return {"hypothesis_id": HYPOTHESIS_ID, "verdict": label, "reason": why,
            "decisive_stream": stream.name, "streams": streams,
            "result": result, "instruments": [asdict(i) for i in insts],
            "n_permutations": n_permutations, "random_seed": RANDOM_SEED}


def registration_parameters() -> dict:
    stream = decisive_stream()
    return {
        "cot": "research/datasets/cot/cot_positions.csv, extended by build_cot.py",
        "in_sample_last_report": IN_SAMPLE_LAST_REPORT,
        "in_sample_digest": IN_SAMPLE_DIGEST,
        "markets": {k: list(v) for k, v in cp.MARKETS.items()},
        "speculators": {"tff": "leveraged funds",
                        "disaggregated": "managed money"},
        "launch_exclusion": cp.LAUNCH,
        "release_column": "release_conservative_utc",
        "signal": "seq=141's: oriented net share of open interest, z over prior 156 reports (min 104)",
        "outcome": "next release-to-release log return over trailing 52-interval std (min 40); not centred",
        "statistic": "per instrument mean(signal x outcome); mean over structures of the mean within each",
        "server_tz": cp.SERVER_TZ,
        "oos_min_intervals": OOS_MIN_INTERVALS, "earliest_run": EARLIEST_RUN,
        "looks": 1,
        "n_permutations": N_PERMUTATIONS, "random_seed": RANDOM_SEED,
        "decisive_stream": stream.name, "decisive_threshold": stream.threshold,
        "decisive_rationale": stream.rationale, "two_sided": True,
        "streams_emitted": sorted(STREAMS), **feature_spec(),
        "admission": "research.admission.require per instrument",
        "ger40_proxy": "E-mini S&P 500 positioning (owner ruling 2026-10-13)",
        "verdict_labels": ["ALIVE", "ALIVE_POOLED_ONLY", "DEAD",
                           "UNTESTED_STRUCTURE"],
    }


#: Ten instruments x OOS_MIN_INTERVALS: the sample the single look will have.
INTENDED_N_OBS = 10 * OOS_MIN_INTERVALS
#: ``min_decidable_sharpe(INTENDED_N_OBS, sr_star=0.0)``, normal moments.
MIN_DECIDABLE_SHARPE = 0.072295

NULL_BASELINE = (
    "Per-instrument circular rotation of the out-of-sample signal sequence "
    "by a random offset in [n/10, 9n/10], 1000 draws, seed 42; pooled "
    "statistic recomputed identically. Keeps positioning's autocorrelation "
    "and each instrument's outcome series; breaks only their alignment.")

DECLARED = (
    "Registered 2026-10-19, before any out-of-sample outcome exists: the "
    "first out-of-sample report (dated 2026-10-13) was released 2026-10-16 "
    "and no price file reaches past 2026-10-09. The signal and its sign "
    "were seen in sample (seq=142, seq=144, seq=146), which is why only "
    "later reports count. Power is low: about 520 observations against "
    "seq=141's 5,771, so a DEAD verdict is weak evidence of absence. One "
    "look; no interim run. The dataset extension must reproduce the "
    "in-sample rows exactly (digest checked in run()). Costs are not in "
    "this test; seq=146 measured pooled FX at 2.3 bp a week gross in "
    "sample, so an ALIVE verdict is a mechanism, not a strategy.")


def preregister(log_dir: Optional[Path] = None):
    """Append the HYPOTHESIS event. Must precede :func:`run`."""
    from research import log as research_log
    stream = decisive_stream()
    kwargs = {"log_dir": log_dir} if log_dir is not None else {}
    return research_log.register_hypothesis(
        HYPOTHESIS_ID,
        title=("COT positioning extremes out of sample, on raw returns — "
               "the test seq=146 left open"),
        mechanism=(
            "Speculators' oriented net position as a share of open interest, "
            "z-scored against its prior three years, is correlated with the "
            "raw return from that report's release to the next, on reports "
            "dated after 2026-10-06. Two-sided."),
        market="FX majors, XAUUSD, XAGUSD, GER40 (via ES)", timeframe="H1",
        family=FAMILY, edge_gate_role=research_log.EdgeGateRole.UNSET,
        predictions=[
            f"{stream.name} < {stream.threshold}, two-sided, decides; "
            "per-structure p is reported, never decisive",
            "ALIVE requires every structure's statistic to share the pooled "
            "sign; ALIVE_POOLED_ONLY does not proceed",
            f"one look, no earlier than {EARLIEST_RUN} and only once every "
            f"instrument holds {OOS_MIN_INTERVALS} scored intervals"],
        note=("Phase 4, resumed by the owner 2026-10-19. " + DECLARED),
        universe=list(PANEL_2B),
        selection_rule=research_log.SelectionRule.POOLED_ALL,
        null_baseline_structure=NULL_BASELINE,
        benchmark_sharpe=0.0,
        min_decidable_sharpe=MIN_DECIDABLE_SHARPE,
        registry_snapshot=REGISTRY_SNAPSHOT,
        parameters=registration_parameters(),
        **kwargs,
    )


def log_result(res: dict, artifact: str, log_dir: Optional[Path] = None):
    """Record the single look against the registration. Not a trial."""
    from research import log as research_log
    kwargs = {"log_dir": log_dir} if log_dir is not None else {}
    r = res["result"]
    return research_log.update_hypothesis(
        HYPOTHESIS_ID,
        stage=research_log.Stage.SIGNAL_EDGE,
        verdict=(research_log.Verdict.OPEN if res["verdict"] == "ALIVE"
                 else research_log.Verdict.KILLED),
        metrics={"verdict": res["verdict"], "reason": res["reason"],
                 "artifact": artifact, "streams": res["streams"],
                 "pooled": r["observed"], "per_structure": r["per_structure"],
                 "per_instrument": r["per_instrument"],
                 "n_intervals": {i["symbol"]: i["n_intervals"]
                                 for i in res["instruments"]}},
        note=(f"The single registered look: {res['verdict']} "
              f"({res['reason']}). Statistic is mean(signal x raw outcome), "
              "signal oriented to the instrument; positive is persistence, "
              "negative contrarian."),
        **kwargs,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--count", action="store_true",
                    help="out-of-sample intervals so far; reads no outcome")
    ap.add_argument("--digest", action="store_true",
                    help="print the in-sample digest of the current dataset")
    ap.add_argument("--preregister", action="store_true",
                    help="append the HYPOTHESIS event to the research log")
    ap.add_argument("--run", action="store_true",
                    help="the single registered look; refuses until ready")
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    if args.count:
        print(json.dumps(count_oos(args.data_dir), indent=1))
        return 0
    if args.digest:
        print(in_sample_digest(pd.read_csv(cp.COT)))
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
