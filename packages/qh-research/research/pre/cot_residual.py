"""Phase 4 — is seq=142's COT effect positioning, or past returns seen through it?

``cot_positioning_extremes`` came back ALIVE (seq=142): when speculators are
crowded the instrument moves against them over the next report interval.
Speculators chase trends, so their positioning is extreme after large moves,
and a weekly price reversal would produce the same sign with positioning
carrying no information of its own.

**The test.** The signal is positioning's z-score with its relation to past
returns removed: at each report, an OLS of z on the prior interval's return
(R1) and the prior 13 intervals' return (R13), fitted on the previous
``FIT_WINDOW`` reports only, is subtracted. What is left is the part of
positioning that past returns do not explain. Same outcome, terciles,
pooling, rotation null and verdict rule as seq=141.

**Reading it, fixed before the run.** The regression's warm-up shortens the
sample, so the test also emits the raw signal on exactly the residual's
sample:

* residual ALIVE — positioning carries information beyond past returns;
* residual DEAD, raw-on-same-sample ALIVE — seq=142 was price reversal;
* both DEAD — undecided: the shorter sample lost the power to see either.

This is a decomposition of seq=142 on the same data, not an out-of-sample
test, and it is a new trial.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from research.pre import cot_positioning as cp
from research.pre.activity_reversal import _admitted_frame, label_terciles
from research.pre.decisive_stream import DecisiveStream, declare
from research.pre.panel_edge import PANEL_2B, STRUCTURE, _default_data_dir

HYPOTHESIS_ID = "cot_positioning_residual"
FAMILY = cp.FAMILY
R_LONG = 13
FIT_WINDOW = 156
FIT_MIN = 104
DECISIVE_HORIZON = cp.DECISIVE_HORIZON
STRUCTURES = cp.STRUCTURES
STREAMS = frozenset({"pooled_p_h1", "pooled_p_h4", "raw_same_sample_p_h1"}
                    | {f"{s}_p_h1" for s in STRUCTURES})


def decisive_stream() -> DecisiveStream:
    return declare(
        "pooled_p_h1", cp.ALPHA, set(STREAMS),
        rationale=(
            "The question is whether positioning carries information beyond "
            "past returns, so the residual signal at the non-overlapping "
            "horizon decides. raw_same_sample_p_h1 is not a second chance: it "
            "only separates 'the effect was price reversal' (raw alive, "
            "residual dead) from 'the shorter sample lost power' (both "
            "dead). Two-sided, as seq=141."))


def lagged_returns(df: pd.DataFrame, pos: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """R1 and R13 ending at each entry: known when the report is used."""
    logc = np.log(df["close"].to_numpy(float))[pos]
    r1 = np.r_[np.nan, np.diff(logc)]
    r13 = pd.Series(logc).diff(R_LONG).to_numpy()
    return r1, r13


def residualise(z: np.ndarray, x: np.ndarray) -> np.ndarray:
    """z minus its fit on x, each fit on the previous FIT_WINDOW rows only."""
    n = z.size
    out = np.full(n, np.nan)
    X = np.column_stack([np.ones(n), x])
    ok = np.isfinite(z) & np.isfinite(X).all(axis=1)
    for t in range(n):
        if not ok[t]:
            continue
        lo = max(0, t - FIT_WINDOW)
        m = ok[lo:t]
        if m.sum() < FIT_MIN:
            continue
        beta, *_ = np.linalg.lstsq(X[lo:t][m], z[lo:t][m], rcond=None)
        out[t] = z[t] - X[t] @ beta
    return out


def residual_frame(df: pd.DataFrame, sig: pd.DataFrame) -> pd.DataFrame:
    """Every interval row with the raw and residual signal. No outcome.

    The regression runs over all interval rows, so the fit is identical
    whether or not outcomes are attached afterwards.
    """
    fr = cp.interval_frame(df, sig)
    r1, r13 = lagged_returns(df, fr["pos"].to_numpy())
    fr["raw"] = fr["signal"]
    fr["signal"] = residualise(fr["raw"].to_numpy(), np.column_stack([r1, r13]))
    return fr


def instrument_frame(df: pd.DataFrame, sig: pd.DataFrame,
                     with_outcomes: bool = False) -> pd.DataFrame:
    """Rows with a finite residual and an outcome (or, without outcomes,
    rows whose outcome will exist — decided by position alone)."""
    fr = residual_frame(df, sig)
    if with_outcomes:
        fr = cp.add_outcomes(df, fr)
        ok = np.isfinite(fr["signal"]) & np.isfinite(fr["y_h1"])
    else:
        ok = np.isfinite(fr["signal"]) & cp.outcome_available(len(fr))
    return fr[ok].reset_index(drop=True)


def count_intervals(data_dir: Optional[Path] = None,
                    symbols: tuple[str, ...] = PANEL_2B) -> dict:
    """Usable intervals and cells per instrument. Computes no outcome."""
    data_dir = Path(data_dir) if data_dir else _default_data_dir()
    cot = cp.load_cot()
    out = {}
    for sym in symbols:
        market, orient = cp.MARKETS[sym]
        df, _ = _admitted_frame(sym, data_dir)
        fr = instrument_frame(df, cp.positioning_z(cot, market, orient))
        lab = label_terciles(fr["signal"]) if len(fr) >= 3 else np.array([])
        out[sym] = {"n_intervals": len(fr),
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
        n_permutations: int = cp.N_PERMUTATIONS) -> dict:
    """The registered test. Refuses to compute an outcome before registration."""
    if not _registered(log_dir):
        raise RuntimeError(
            f"{HYPOTHESIS_ID!r} is not registered in the research log; "
            "register it before any outcome is computed.")
    data_dir = Path(data_dir) if data_dir else _default_data_dir()
    cot = cp.load_cot()
    frames, labels, raw_labels, insts = {}, {}, {}, []
    for sym in symbols:
        market, orient = cp.MARKETS[sym]
        df, start = _admitted_frame(sym, data_dir)
        fr = instrument_frame(df, cp.positioning_z(cot, market, orient),
                              with_outcomes=True)
        # An instrument the warm-up leaves empty (NZDUSD) has no cells.
        lab = label_terciles(fr["signal"]) if len(fr) >= 3 else np.array([])
        cell = int(min((lab == 0).sum(), (lab == 2).sum())) if lab.size else 0
        decidable = cell >= cp.MIN_CELL
        insts.append(cp.InstrumentResult(sym, STRUCTURE[sym], market,
                                         str(start.date()), len(fr), cell,
                                         decidable))
        if decidable:
            frames[sym], labels[sym] = fr, lab
            raw_labels[sym] = label_terciles(fr["raw"])
    structure_of = {s: STRUCTURE[s] for s in frames}
    result = {f"h{h}": cp.rotation_test(frames, labels, structure_of, h,
                                        n_permutations)
              for h in cp.HORIZONS}
    raw = cp.rotation_test(frames, raw_labels, structure_of, DECISIVE_HORIZON,
                           n_permutations)
    for inst in insts:
        inst.spread = {h: result[f"h{h}"]["per_instrument"].get(inst.symbol)
                       for h in cp.HORIZONS}
    stream = decisive_stream()
    label, why = cp.verdict(result, stream, set(structure_of.values()))
    streams = {f"pooled_p_h{h}": result[f"h{h}"]["p"] for h in cp.HORIZONS}
    streams.update({f"{k}_p_h1": v["p"] for k, v in
                    result["h1"]["per_structure"].items()})
    streams["raw_same_sample_p_h1"] = raw["p"]
    raw_alive = raw["p"] < cp.ALPHA
    reading = ("positioning carries information beyond past returns"
               if label == "ALIVE" else
               "seq=142 was price reversal seen through COT"
               if raw_alive else
               "undecided: the shorter sample lost the power to see either")
    return {"hypothesis_id": HYPOTHESIS_ID, "verdict": label, "reason": why,
            "reading": reading, "decisive_stream": stream.name,
            "streams": streams, "results": result, "raw_same_sample_h1": raw,
            "instruments": [asdict(i) for i in insts],
            "n_permutations": n_permutations, "random_seed": cp.RANDOM_SEED}


def registration_parameters() -> dict:
    base = cp.registration_parameters()
    stream = decisive_stream()
    base.update({
        "signal": ("seq=141's oriented positioning z, less its OLS fit on R1 "
                   "and R13 (log returns over the prior 1 and 13 report "
                   "intervals, ending at entry), fitted on the previous 156 "
                   "reports (min 104)"),
        "r_long": R_LONG, "fit_window": FIT_WINDOW, "fit_min": FIT_MIN,
        "decisive_stream": stream.name, "decisive_threshold": stream.threshold,
        "decisive_rationale": stream.rationale,
        "streams_emitted": sorted(STREAMS),
        "feature_inputs": ["cftc_open_interest", "cftc_positions",
                           "lagged_interval_returns"],
        "reading_rule": {
            "residual ALIVE": "information beyond past returns",
            "residual DEAD, raw_same_sample ALIVE": "price reversal",
            "both DEAD": "undecided (power)"},
        "parent": "cot_positioning_extremes (seq=141/142)",
    })
    return base


def preregister(intended_n_obs: int, min_decidable: float,
                log_dir: Optional[Path] = None):
    """Append the HYPOTHESIS event. Must precede :func:`run`."""
    from research import log as research_log
    stream = decisive_stream()
    kwargs = {"log_dir": log_dir} if log_dir is not None else {}
    params = registration_parameters()
    params["intended_n_obs"] = intended_n_obs
    return research_log.register_hypothesis(
        HYPOTHESIS_ID,
        title=("COT positioning extremes net of past returns — is seq=142 "
               "positioning, or price reversal?"),
        mechanism=(
            "The part of speculators' positioning z that a rolling, past-only "
            "regression on prior 1- and 13-interval returns does not explain "
            "predicts the next report interval's move. Two-sided."),
        market="FX majors, XAUUSD, XAGUSD, GER40 (via ES)", timeframe="H1",
        family=FAMILY, edge_gate_role=research_log.EdgeGateRole.UNSET,
        predictions=[
            f"{stream.name} < {stream.threshold}, two-sided, decides",
            "residual DEAD with raw_same_sample_p_h1 < 0.05 is read as "
            "price reversal; both DEAD as undecided for power",
            "same ALIVE/ALIVE_POOLED_ONLY rule and cell minimum as seq=141"],
        note=("A decomposition of seq=142 on the same data, not out of "
              "sample; registered after seeing seq=142's result, which is "
              "why it is a new trial. The test's design was fixed before any "
              "residual outcome was computed: only interval counts were read. "
              "The R1/R13 lags were chosen to cover the short-term reversal "
              "and the quarter-scale trend that speculators are known to "
              "follow, not tuned. " + cp.DECLARED.split(" Prior exposure")[0]),
        universe=list(PANEL_2B),
        selection_rule=research_log.SelectionRule.POOLED_ALL,
        null_baseline_structure=cp.NULL_BASELINE,
        benchmark_sharpe=0.0,
        min_decidable_sharpe=min_decidable,
        registry_snapshot=cp.REGISTRY_SNAPSHOT,
        parameters=params,
        **kwargs,
    )


def log_result(res: dict, artifact: str, log_dir: Optional[Path] = None):
    """Record a :func:`run` result against the registration. Not a trial."""
    from research import log as research_log
    kwargs = {"log_dir": log_dir} if log_dir is not None else {}
    h = res["results"]
    return research_log.update_hypothesis(
        HYPOTHESIS_ID,
        stage=research_log.Stage.SIGNAL_EDGE,
        verdict=(research_log.Verdict.OPEN if res["verdict"] == "ALIVE"
                 else research_log.Verdict.KILLED),
        metrics={"verdict": res["verdict"], "reason": res["reason"],
                 "reading": res["reading"], "artifact": artifact,
                 "streams": res["streams"],
                 "pooled_spread": {k: v["observed"] for k, v in h.items()},
                 "per_structure_h1": h["h1"]["per_structure"],
                 "raw_same_sample_h1": {
                     "observed": res["raw_same_sample_h1"]["observed"],
                     "p": res["raw_same_sample_h1"]["p"]},
                 "n_intervals": {i["symbol"]: i["n_intervals"]
                                 for i in res["instruments"]}},
        note=(f"Registered run: {res['verdict']} ({res['reason']}). Reading, "
              f"by the rule fixed at registration: {res['reading']}."),
        **kwargs,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--count", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    if args.count:
        print(json.dumps(count_intervals(args.data_dir), indent=1))
        return 0
    if args.run:
        res = run(args.data_dir)
        if args.out:
            args.out.write_text(json.dumps(res, indent=1, default=float) + "\n")
        print(res["verdict"], "—", res["reason"], "—", res["reading"])
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
