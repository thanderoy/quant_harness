"""Phase 4 — does the equity market lead the risk-sensitive currencies?

The fourth Phase 4 mechanism and the first cross-asset one on the panel.
Cross-asset inputs were tried on gold alone before Phase 4: the dollar
(seq=17, dead at seq=75) and real yields (seq=79). Both co-moved with gold
in the same period and led it by nothing.

**The claim.** Equity is where risk appetite is priced first. If risk
currencies absorb that information with a lag, an hour's equity return
predicts the next hour's return in AUDUSD, NZDUSD, USDJPY and USDCHF,
oriented so that risk-on is positive: the AUD and NZD rise, the JPY and CHF
fall. Continuation (slow absorption) and reversal (overshoot in the thinner
market) predict opposite signs. Two-sided.

**Leader.** GER40, the only equity index ``research.admission`` admits;
US500 is refused for an undeclared 55-day hole. Its feed shares the
broker's clock with the FX pairs, so bar t means the same hour on both.

**Point in time.** The leader's return over bar t ends at bar t's close,
which is when the follower's position would open. The outcome runs from the
follower's close at t to its close at t + h. A return is taken only across
two consecutive tradable bars (R3's mask on each instrument), and an outcome
only across h + 1 of them, so nothing straddles a closure.

**Scaling.** Each return is divided by its own instrument's std over the
previous 500 bars (min 400), excluding the current one. Not centred.

**Statistic.** Per instrument, the mean product of the scaled leader return
and the scaled, oriented follower return — a correlation. The pooled
statistic is their mean. The same-hour product is reported as a check that
the orientation is right; it is lookahead and never decides anything.

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
                                            _two_sided_p, pooled_statistic)
from research.pre.decisive_stream import DecisiveStream, declare
from research.pre.normalizer_check import assert_disjoint
from research.pre.panel_edge import _default_data_dir, build_panel_mask

HYPOTHESIS_ID = "equity_fx_lead_h1"
FAMILY = "cross_asset_lead"

LEADER = "GER40"
#: Follower -> orientation: +1 where risk-on raises the quoted price.
FOLLOWERS: dict[str, int] = {"AUDUSD": 1, "NZDUSD": 1, "USDJPY": 1, "USDCHF": 1}
SIGMA_BARS = 500
SIGMA_MIN_BARS = 400
HORIZONS = (1, 4)
DECISIVE_HORIZON = 1
MIN_ROWS = 2_000
N_PERMUTATIONS = 1000
RANDOM_SEED = 42
ALPHA = 0.05
STREAMS = frozenset({f"pooled_p_h{h}" for h in HORIZONS})
REGISTRY_SNAPSHOT = "pepperstone_live_20261009b.json"
ONE_HOUR = np.timedelta64(1, "h")


def decisive_stream() -> DecisiveStream:
    return declare(
        f"pooled_p_h{DECISIVE_HORIZON}", ALPHA, set(STREAMS),
        rationale=(
            "The claim is a lag of about an hour, so h=1 is the horizon that "
            "addresses it and does not overlap. h=4 is reported, never "
            "decisive. Two-sided, because slow absorption and overshoot "
            "predict opposite signs. All followers are one structure, FX, "
            "so the pooled statistic is the mean over the four pairs."))


def feature_spec() -> dict:
    """Feature inputs and target normalizer, asserted disjoint (rule 1)."""
    spec = {"feature_inputs": {f"{LEADER}_close"},
            "target_normalizer": {"follower_close_logret_std"}}
    assert_disjoint(spec["feature_inputs"], spec["target_normalizer"],
                    name="equity_fx_lead")
    return {k: sorted(v) for k, v in spec.items()}


def bar_returns(df: pd.DataFrame) -> pd.Series:
    """Log return per bar, NaN unless this bar and the one an hour before
    are both present and tradable."""
    tradable = build_panel_mask(df.index).tradable.to_numpy()
    logc = np.log(df["close"].to_numpy(float))
    t = df.index.to_numpy("datetime64[ns]")
    ok = np.r_[False, tradable[1:] & tradable[:-1] & (np.diff(t) == ONE_HOUR)]
    r = np.r_[np.nan, np.diff(logc)]
    return pd.Series(np.where(ok, r, np.nan), index=df.index)


def scaled(r: pd.Series) -> pd.Series:
    """r over the std of the previous SIGMA_BARS returns, excluding t."""
    sd = r.shift(1).rolling(SIGMA_BARS, min_periods=SIGMA_MIN_BARS).std()
    return r / sd


def pair_frame(leader: pd.DataFrame, follower: pd.DataFrame, orient: int,
               with_outcomes: bool = False) -> pd.DataFrame:
    """One row per hour where the leader's scaled return exists and every
    follower outcome window is clean. Outcomes only when asked.

    Row eligibility depends on bar presence and tradability alone, so a
    count matches a run without computing an outcome.
    """
    x = scaled(bar_returns(leader))
    rf = bar_returns(follower)
    sd_f = rf.shift(1).rolling(SIGMA_BARS, min_periods=SIGMA_MIN_BARS).std()
    idx = follower.index.intersection(x.index)
    pos = follower.index.get_indexer(idx)
    clean = np.isfinite(rf.to_numpy(float))
    n = len(follower)
    h_max = max(HORIZONS)
    ok = np.isfinite(x.loc[idx].to_numpy(float)) & np.isfinite(
        sd_f.to_numpy(float)[pos]) & (pos + h_max < n)
    ok &= clean[pos]  # the same-hour check needs this bar's return too
    for k in range(1, h_max + 1):
        ok &= clean[np.minimum(pos + k, n - 1)]
    keep = pos[ok]
    out = pd.DataFrame({"time": follower.index[keep],
                        "x": x.loc[idx].to_numpy(float)[ok]})
    if with_outcomes:
        logc = np.log(follower["close"].to_numpy(float))
        s = sd_f.to_numpy(float)[keep]
        out["same_hour"] = orient * rf.to_numpy(float)[keep] / s
        for h in HORIZONS:
            out[f"y_h{h}"] = orient * (logc[keep + h] - logc[keep]) / (s * np.sqrt(h))
    return out


def _product(x: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean(x * y))


def rotation_test(frames: dict[str, pd.DataFrame], h: int,
                  n_permutations: int = N_PERMUTATIONS,
                  seed: int = RANDOM_SEED) -> dict:
    """Pooled mean of x*y over followers; rotation null on x per follower."""
    rng = np.random.default_rng(seed)
    col = f"y_h{h}"
    structure_of = {s: "fx" for s in frames}
    xs = {s: f["x"].to_numpy(float) for s, f in frames.items()}
    ys = {s: f[col].to_numpy(float) for s, f in frames.items()}
    obs = {s: _product(xs[s], ys[s]) for s in frames}
    pooled, _ = pooled_statistic(obs, structure_of)
    null = np.empty(n_permutations)
    for i in range(n_permutations):
        null[i] = pooled_statistic(
            {s: _product(_rotate(xs[s], rng), ys[s]) for s in frames},
            structure_of)[0]
    per_p = {}
    for s in frames:
        r2 = np.random.default_rng(seed + 1)
        nul = np.array([_product(_rotate(xs[s], r2), ys[s])
                        for _ in range(n_permutations)])
        per_p[s] = _two_sided_p(nul, obs[s])
    return {"observed": pooled, "p": _two_sided_p(null, pooled),
            "per_instrument": {s: {"observed": obs[s], "p": per_p[s]}
                               for s in frames}}


def verdict(result: dict, stream: DecisiveStream) -> tuple[str, str]:
    d = result[f"h{DECISIVE_HORIZON}"]
    passed, why = stream.verdict({stream.name: d["p"]})
    if passed == "FAIL":
        return "DEAD", why
    signs = {k: np.sign(v["observed"]) for k, v in d["per_instrument"].items()}
    if all(s == np.sign(d["observed"]) for s in signs.values()):
        return "ALIVE", why
    return "ALIVE_POOLED_ONLY", f"{why}; follower signs {signs}"


@dataclass
class InstrumentResult:
    symbol: str
    orientation: int
    admitted_from: str
    n_rows: int
    decidable: bool
    same_hour: Optional[float] = None
    statistic: dict = field(default_factory=dict)


def _load(data_dir: Path) -> tuple[pd.DataFrame, dict]:
    leader, _ = _admitted_frame(LEADER, data_dir)
    followers = {s: _admitted_frame(s, data_dir) for s in FOLLOWERS}
    return leader, followers


def count_rows(data_dir: Optional[Path] = None) -> dict:
    """Usable hours per follower. Reads no outcome."""
    data_dir = Path(data_dir) if data_dir else _default_data_dir()
    leader, followers = _load(data_dir)
    out = {}
    for sym, (df, start) in followers.items():
        fr = pair_frame(leader, df, FOLLOWERS[sym])
        out[sym] = {"admitted_from": str(start.date()), "n_rows": len(fr),
                    "first": str(fr["time"].min()) if len(fr) else None,
                    "last": str(fr["time"].max()) if len(fr) else None}
    return out


def _registered(log_dir: Optional[Path]) -> bool:
    from research import log as research_log
    kwargs = {"log_dir": log_dir} if log_dir is not None else {}
    return bool(research_log.history(HYPOTHESIS_ID, **kwargs))


def run(data_dir: Optional[Path] = None, log_dir: Optional[Path] = None,
        n_permutations: int = N_PERMUTATIONS) -> dict:
    """The registered test. Refuses to compute an outcome before registration."""
    if not _registered(log_dir):
        raise RuntimeError(
            f"{HYPOTHESIS_ID!r} is not registered in the research log; "
            "register it before any outcome is computed.")
    data_dir = Path(data_dir) if data_dir else _default_data_dir()
    leader, followers = _load(data_dir)
    frames, insts = {}, []
    for sym, (df, start) in followers.items():
        fr = pair_frame(leader, df, FOLLOWERS[sym], with_outcomes=True)
        decidable = len(fr) >= MIN_ROWS
        insts.append(InstrumentResult(
            sym, FOLLOWERS[sym], str(start.date()), len(fr), decidable,
            same_hour=_product(fr["x"].to_numpy(), fr["same_hour"].to_numpy())))
        if decidable:
            frames[sym] = fr
    result = {f"h{h}": rotation_test(frames, h, n_permutations) for h in HORIZONS}
    for inst in insts:
        inst.statistic = {h: result[f"h{h}"]["per_instrument"].get(inst.symbol)
                          for h in HORIZONS}
    stream = decisive_stream()
    label, why = verdict(result, stream)
    return {"hypothesis_id": HYPOTHESIS_ID, "verdict": label, "reason": why,
            "decisive_stream": stream.name,
            "streams": {f"pooled_p_h{h}": result[f"h{h}"]["p"] for h in HORIZONS},
            "results": result, "instruments": [asdict(i) for i in insts],
            "n_permutations": n_permutations, "random_seed": RANDOM_SEED}


def registration_parameters() -> dict:
    stream = decisive_stream()
    return {
        "leader": LEADER, "followers": FOLLOWERS,
        "orientation": "+1 where risk-on raises the quoted price",
        "feature": "leader's bar-t log return over its prior 500-bar std (min 400)",
        "outcome": "follower's oriented log return from close t to close t+h, over its prior 500-bar std (min 400) x sqrt(h); not centred",
        "statistic": "per follower mean(feature x outcome); pooled = mean over followers",
        "clean_bars": "a return needs two consecutive tradable bars (R3 mask, both instruments); an outcome needs h+1",
        "horizons": list(HORIZONS), "decisive_horizon": DECISIVE_HORIZON,
        "min_rows": MIN_ROWS, "n_permutations": N_PERMUTATIONS,
        "random_seed": RANDOM_SEED,
        "decisive_stream": stream.name, "decisive_threshold": stream.threshold,
        "decisive_rationale": stream.rationale, "two_sided": True,
        "streams_emitted": sorted(STREAMS), **feature_spec(),
        "diagnostic_only": "same-hour product (lookahead): orientation check",
        "admission": "research.admission.require per instrument",
        "verdict_labels": ["ALIVE", "ALIVE_POOLED_ONLY", "DEAD"],
    }


#: Rows on the four followers from :func:`count_rows` on 2026-10-19.
INTENDED_N_OBS = 129_651
#: ``min_decidable_sharpe(INTENDED_N_OBS, sr_star=0.0)``, normal moments.
MIN_DECIDABLE_SHARPE = 0.004568

NULL_BASELINE = (
    "Per-follower circular rotation of the leader-return sequence by a "
    "random offset in [n/10, 9n/10], 1000 draws, seed 42; pooled statistic "
    "recomputed identically. Keeps each series' autocorrelation and "
    "volatility clustering; breaks only their alignment.")

DECLARED = (
    "Prior exposure: seq=17/75 and seq=79 found gold's cross-asset links "
    "purely contemporaneous, which is the prior here, and no work in this "
    "repo has paired equity with FX. Before this registration only row "
    "counts were read. NZDUSD is admitted only from 2025-01-22, so its "
    "sample is about a fifth of the others' and it is weighted equally. "
    "USDCAD, EURUSD and GBPUSD are left out: their risk orientation is not "
    "fixed a priori. Costs are not in this test; FX fills land about 0.5 "
    "pip beyond the quote (seq=133), so an ALIVE verdict is a mechanism, "
    "not a strategy, and an hourly one faces about a pip per round trip.")


def preregister(log_dir: Optional[Path] = None):
    """Append the HYPOTHESIS event. Must precede :func:`run`."""
    from research import log as research_log
    stream = decisive_stream()
    kwargs = {"log_dir": log_dir} if log_dir is not None else {}
    return research_log.register_hypothesis(
        HYPOTHESIS_ID,
        title="Does an hour's GER40 return lead the risk-sensitive currencies?",
        mechanism=(
            "An hour's GER40 return, scaled by its own recent volatility, is "
            "correlated with the next hour's risk-oriented return in AUDUSD, "
            "NZDUSD, USDJPY and USDCHF. Continuation and reversal predict "
            "opposite signs. Two-sided."),
        market="AUDUSD, NZDUSD, USDJPY, USDCHF led by GER40", timeframe="H1",
        family=FAMILY, edge_gate_role=research_log.EdgeGateRole.UNSET,
        predictions=[
            f"{stream.name} < {stream.threshold}, two-sided, decides; h=4 "
            "(overlapping) and per-follower p are reported, never decisive",
            "ALIVE requires every follower's statistic to share the pooled "
            "sign; ALIVE_POOLED_ONLY does not proceed",
            f"a follower with fewer than {MIN_ROWS} rows is reported, not pooled",
            "the same-hour product should be positive; if not, the "
            "orientation is wrong and the run is void, not a verdict"],
        note=("Phase 4's fourth mechanism (input class cross-asset, chosen by "
              "the owner 2026-10-19). Pre-registered before any outcome was "
              "computed; run() refuses until this entry exists. " + DECLARED),
        universe=[LEADER, *FOLLOWERS],
        selection_rule=research_log.SelectionRule.POOLED_ALL,
        null_baseline_structure=NULL_BASELINE,
        benchmark_sharpe=0.0,
        min_decidable_sharpe=MIN_DECIDABLE_SHARPE,
        registry_snapshot=REGISTRY_SNAPSHOT,
        parameters=registration_parameters(),
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
        metrics={
            "verdict": res["verdict"], "reason": res["reason"],
            "artifact": artifact, "streams": res["streams"],
            "pooled": {k: v["observed"] for k, v in h.items()},
            "per_follower_h1": h[f"h{DECISIVE_HORIZON}"]["per_instrument"],
            "same_hour": {i["symbol"]: i["same_hour"] for i in res["instruments"]},
            "n_rows": {i["symbol"]: i["n_rows"] for i in res["instruments"]},
        },
        note=(f"Registered run: {res['verdict']} ({res['reason']}). Decided "
              "by the pre-declared stream alone. Statistic is the mean "
              "product of scaled GER40 return and the scaled, risk-oriented "
              "follower return; positive is continuation, negative reversal."),
        **kwargs,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--count", action="store_true",
                    help="row counts only; reads no outcome")
    ap.add_argument("--preregister", action="store_true",
                    help="append the HYPOTHESIS event to the research log")
    ap.add_argument("--run", action="store_true",
                    help="the registered test; refuses before registration")
    ap.add_argument("--data-dir", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    if args.count:
        print(json.dumps(count_rows(args.data_dir), indent=1))
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
