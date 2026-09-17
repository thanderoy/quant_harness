"""T9b — ``post/`` path parity against the crest_n_keel nested walk-forward (seq=49).

The ``post/`` leg exercises the widest slice of the stack: HMA, Stochastic and
ATR (all three D8-pinned indicators), the asymmetric ATR exit that carries the
``effective_atr`` contract, multi-fold walk-forward, and the sizer. Phase 1
moves all of it, so the seq=49 run is pinned — the rewrite may not shift a
number without saying so.

**What is pinned, and what it was derived from.** The stored artifacts record
per-fold statistics only; no artifact in either repository ever held
trade-for-trade records, so X15b's trade-level assertions had nothing to assert
against. ``phase0/build_t9b_cnk_fixture.py`` derived them, and was allowed to
only because re-running each fold's recorded config reproduced every fold
boundary and every recorded statistic exactly. The fixture carries that
provenance, including the two things a match does *not* establish — the
generating module was untracked when the artifact was written, and selection
was not reproduced. Read ``provenance_note`` in the fixture before trusting a
green run here to mean more than it does.

**Layered, and ordered.** Six checks run in dependency order and stop at the
first failure, so a break localises to a layer instead of needing a bisect:

1. ``bars_hash`` — the data loader. Nothing downstream is meaningful if the
   bars moved, so nothing downstream is reported when this fails.
2. ``fold_geometry`` — fold boundaries, given identical bars.
3. ``trade_counts`` — per-fold trade count per arm, called out separately
   because "one trade vanished" and "every trade shifted a bar" both break the
   trade-for-trade check below and want different investigations.
4. ``trade_records`` — entry and exit timestamp, direction, and volume,
   element-wise and exact. These are discrete: a timestamp is an index, a
   direction is a label, and a volume is rounded to the lot step. Nothing here
   is a float that arithmetic can nudge, so an inexact comparison would only
   hide a real break.
5. ``trade_prices`` — entry and exit price, element-wise, ULP-bounded rather
   than exact. Prices descend from ``hma``, which reduces each window with
   ``np.dot``; the summation order comes from the OpenBLAS kernel chosen for
   the CPU, not from the source. T11 learned this the hard way when ``wma_9``
   reproduced its fixture on the development machine and missed on 1,090 of
   6,000 cells on the runner. A price that differs by more than
   ``PRICE_ULP_TOLERANCE`` units in the last place is a logic change; a price
   that differs by less is the kernel, and is reported as ``max_ulp`` so drift
   is visible even while the check passes.
6. ``sharpe`` — per-fold and aggregate Sharpe. Also ULP-bounded, for the same
   reason and with the same reporting.

**Why the trade set is compared exactly while prices are not.** These are not
in tension. A ULP-level difference in ``hma`` can in principle flip a
comparison and move an entry to a neighbouring bar — but if it does, the trade
set has changed, and that is a finding, not noise to absorb. Layer 4 is where
such a flip must surface; widening it to tolerate one would defeat the point of
running the check at all.

**Mask-on** is not implemented here. It needs a mask-aware path through the
walk-forward that does not exist yet, and reporting one leg of a two-leg
comparison produces a number nobody can interpret. See T9's mask-on entry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

HYPOTHESIS_ID = "crest_n_keel"
SEQ = 49

_HERE = Path(__file__).resolve().parent

#: Trade-level pin, derived and provenance-stamped by
#: ``phase0/build_t9b_cnk_fixture.py``. Not an original artifact.
FIXTURE = _HERE / "fixtures" / "t9b_crest_n_keel_maskoff.json"

TIMEFRAMES = ("H1", "H4")

#: Units in the last place tolerated on any price or Sharpe. Chosen to absorb a
#: BLAS kernel difference in `hma`'s reduction and nothing larger: at a gold
#: price near 2000, one ULP is about 4.5e-13, so 64 of them is under a
#: nanodollar — far below a tick, and so incapable of moving a decision.
PRICE_ULP_TOLERANCE = 64


class FixtureMissing(FileNotFoundError):
    """The trade-level pin is not on disk."""


@dataclass
class LayerResult:
    order: int
    layer: str
    passed: bool
    detail: str = ""
    n_compared: int = 0
    max_ulp: Optional[int] = None
    failures: list[str] = field(default_factory=list)


@dataclass
class ParityReport:
    mode: str
    passed: bool
    layers: list[LayerResult] = field(default_factory=list)
    stopped_at: Optional[str] = None
    fixture: str = ""
    provenance: str = ""
    checked_at_utc: str = ""

    def as_dict(self) -> dict:
        d = asdict(self)
        d["layers"] = [asdict(x) if not isinstance(x, dict) else x
                       for x in self.layers]
        return d


def load_fixture(path: Path = FIXTURE) -> dict:
    if not path.exists():
        raise FixtureMissing(
            f"T9b trade-level fixture not found at {path}. Rebuild it with "
            f"`python -m phase0.build_t9b_cnk_fixture`, which refuses to write "
            f"unless the regeneration reproduces the stored artifact exactly.")
    return json.loads(path.read_text())


# --------------------------------------------------------------------------- #
# Comparison primitives                                                        #
# --------------------------------------------------------------------------- #
def ulp_distance(a: float, b: float) -> int:
    """Units in the last place between two floats.

    NaN reproducing NaN is zero distance. A fold whose config takes fewer than
    two trades reports NaN for every ratio metric, and under IEEE-754
    ``nan != nan`` — comparing those naively would report a break where the
    runs agree. Infinities are equal to themselves and infinitely far from
    anything else; a profit factor with no losing trade is legitimately
    infinite, and silently treating that as a match to a finite number would
    hide exactly the kind of change this fixture exists to catch.
    """
    if math.isnan(a) and math.isnan(b):
        return 0
    if math.isnan(a) or math.isnan(b):
        return 2 ** 62
    if a == b:
        return 0
    if math.isinf(a) or math.isinf(b):
        return 2 ** 62

    def ordinal(x: float) -> int:
        bits = int(np.float64(x).view(np.int64))
        return bits if bits >= 0 else (1 << 63) - bits

    return abs(ordinal(a) - ordinal(b))


def _arms(fold: dict) -> list[tuple[str, dict]]:
    """The arms of one fold that carry trades, in a stable order."""
    return [(name, fold[name]) for name in ("selected", "fixed")
            if fold.get(name)]


# --------------------------------------------------------------------------- #
# Recomputation                                                                #
# --------------------------------------------------------------------------- #
def recompute() -> dict:
    """Re-run every pinned fold through the rewritten ``post/`` path.

    Imports are local: the walk-forward module pulls in the sweep grid and the
    OHLC loader, and a parity module that cannot even be imported without them
    would make an unrelated collection error look like a parity failure.
    """
    from research.post.sweeps import cnk_engine as engine
    from research.post.sweeps import cnk_nested_wf as wf
    from research.post.sweeps import run_cnk_sweep as sweep
    from research.post.sweeps.data import load

    out: dict = {}
    for tf in TIMEFRAMES:
        df = load(tf)
        digest = hashlib.sha256(
            df[["open", "high", "low", "close"]].to_numpy().tobytes()
        ).hexdigest()
        folds = []
        for tr_start, tr_end, te_end in wf._folds(df, tf):
            test_df = df.loc[(df.index >= tr_end) & (df.index < te_end)]
            folds.append({
                "train_start": str(tr_start.date()),
                "train_end": str(tr_end.date()),
                "test_end": str(te_end.date()),
                "bars": engine.Bars(test_df),
            })
        out[tf] = {"bars_hash": digest, "folds": folds,
                   "engine": engine, "sweep": sweep, "wf": wf}
    return out


def _simulate(state: dict, bars, cfg: dict) -> tuple[dict, dict]:
    engine, sweep = state["engine"], state["sweep"]
    hma_v = engine.hma(bars.close, cfg["hma"])
    atr_v = engine.atr(bars.high, bars.low, bars.close, cfg["atr"])
    if cfg["mode"] == "pullback":
        k, d = engine.stochastic(bars.high, bars.low, bars.close, cfg["stoch_k"],
                                 sweep.STOCH_D, sweep.STOCH_SMOOTH)
        long_sig, short_sig = engine.pullback_signals(
            bars, hma_v, k, d, cfg["zone"][0], cfg["zone"][1])
    else:
        long_sig, short_sig = engine.momentum_signals(bars, hma_v)
    direction = cfg["direction"]
    sim = engine.simulate(bars, cfg["mode"], hma_v, atr_v, long_sig, short_sig,
                          enable_long=direction in ("both", "long"),
                          enable_short=direction in ("both", "short"),
                          sl_mult=cfg["sl"], tp_mult=cfg["tp"],
                          trail_mult=cfg["trail"], risk_pct=sweep.RISK_PCT,
                          min_atr=cfg["min_atr"], max_dd_halt=1.0,
                          record_trades=True)
    return sim, engine.metrics(sim, basis="price")


def _config_of(arm: dict) -> dict:
    """The fixture stores each arm's config inline, beside its label."""
    zone = arm["zone"]
    return {"mode": arm["mode"], "hma": arm["hma"], "atr": arm["atr"],
            "stoch_k": arm["stoch_k"],
            "zone": tuple(zone) if zone is not None else None,
            "sl": arm["sl"], "tp": arm["tp"], "trail": arm["trail"],
            "direction": arm["direction"], "min_atr": arm["min_atr"]}


# --------------------------------------------------------------------------- #
# The checks                                                                   #
# --------------------------------------------------------------------------- #
def check_mask_off(fixture: Optional[dict] = None,
                   ulp_tolerance: int = PRICE_ULP_TOLERANCE) -> ParityReport:
    """Run the six checks in order, stopping at the first failure."""
    fx = fixture if fixture is not None else load_fixture()
    report = ParityReport(
        mode="mask_off", passed=True, fixture=FIXTURE.name,
        provenance=fx.get("provenance", ""),
        checked_at_utc=datetime.now(timezone.utc).isoformat(),
    )

    def record(order: int, layer: str, failures: list[str], detail: str,
               n_compared: int = 0, max_ulp: Optional[int] = None) -> bool:
        ok = not failures
        report.layers.append(LayerResult(order, layer, ok, detail, n_compared,
                                         max_ulp, failures[:40]))
        if not ok:
            report.passed = False
            report.stopped_at = layer
        return ok

    state = recompute()

    # -- 1. the data loader ------------------------------------------------- #
    # The fixture predates this layer, so there is nothing stored to compare
    # against; what is verified is that both timeframes load and that the two
    # digests differ, which is the cheapest guard against the loader silently
    # returning the same frame for every timeframe.
    hashes = {tf: state[tf]["bars_hash"] for tf in TIMEFRAMES}
    fails = ([] if len(set(hashes.values())) == len(hashes)
             else [f"timeframes share a bars hash: {hashes}"])
    if not record(1, "bars_hash", fails,
                  "the data loader; nothing downstream is meaningful if the "
                  "bars moved", n_compared=len(hashes)):
        return report

    # -- 2. fold geometry --------------------------------------------------- #
    fails, n = [], 0
    for tf in TIMEFRAMES:
        got, want = state[tf]["folds"], fx["folds"][tf]
        if len(got) != len(want):
            fails.append(f"{tf}: recomputed {len(got)} folds, fixture has {len(want)}")
            continue
        for i, (g, w) in enumerate(zip(got, want)):
            for key in ("train_start", "train_end", "test_end"):
                n += 1
                if g[key] != w[key]:
                    fails.append(f"{tf} fold {i}: {key} {g[key]} != {w[key]}")
    if not record(2, "fold_geometry", fails,
                  "fold boundaries, given identical bars", n_compared=n):
        return report

    # Simulate once; layers 3-6 all read from this.
    runs: list[tuple[str, int, str, dict, dict, dict]] = []
    for tf in TIMEFRAMES:
        for i, (g, w) in enumerate(zip(state[tf]["folds"], fx["folds"][tf])):
            for arm_name, arm in _arms(w):
                sim, met = _simulate(state[tf], g["bars"], _config_of(arm))
                runs.append((tf, i, arm_name, arm, sim, met))

    # -- 3. trade counts ---------------------------------------------------- #
    fails = []
    for tf, i, arm_name, arm, sim, _ in runs:
        if len(sim["records"]) != len(arm["trades"]):
            fails.append(f"{tf} fold {i} {arm_name}: {len(sim['records'])} trades, "
                         f"fixture has {len(arm['trades'])}")
    if not record(3, "trade_counts", fails,
                  "per-fold trade count per arm, before comparing trades "
                  "element-wise", n_compared=len(runs)):
        return report

    # -- 4. trade records, exact -------------------------------------------- #
    fails, n = [], 0
    for tf, i, arm_name, arm, sim, _ in runs:
        for j, (g, w) in enumerate(zip(sim["records"], arm["trades"])):
            for key in ("entry_ts", "exit_ts", "direction", "lots", "size_oz"):
                n += 1
                if g[key] != w[key]:
                    fails.append(f"{tf} fold {i} {arm_name} trade {j}: "
                                 f"{key} {g[key]!r} != {w[key]!r}")
    if not record(4, "trade_records", fails,
                  "timestamps, direction and volume; discrete, so compared "
                  "exactly", n_compared=n):
        return report

    # -- 5. trade prices, ULP-bounded --------------------------------------- #
    fails, n, worst = [], 0, 0
    for tf, i, arm_name, arm, sim, _ in runs:
        for j, (g, w) in enumerate(zip(sim["records"], arm["trades"])):
            for key in ("entry_px", "exit_px", "effective_atr"):
                n += 1
                d = ulp_distance(float(g[key]), float(w[key]))
                worst = max(worst, d)
                if d > ulp_tolerance:
                    fails.append(f"{tf} fold {i} {arm_name} trade {j}: "
                                 f"{key} {g[key]!r} != {w[key]!r} ({d} ulp)")
    if not record(5, "trade_prices", fails,
                  f"prices, bounded at {ulp_tolerance} ulp because `hma` "
                  f"reduces with np.dot and the summation order is the "
                  f"CPU's kernel, not the source", n_compared=n, max_ulp=worst):
        return report

    # -- 6. per-fold and aggregate Sharpe ----------------------------------- #
    fails, n, worst = [], 0, 0
    per_fold_got: list[float] = []
    per_fold_want: list[float] = []
    for tf, i, arm_name, arm, _, met in runs:
        n += 1
        got, want = float(met["sharpe"]), float(arm["stats"]["sharpe"])
        per_fold_got.append(got)
        per_fold_want.append(want)
        d = ulp_distance(got, want)
        worst = max(worst, d)
        if d > ulp_tolerance:
            fails.append(f"{tf} fold {i} {arm_name}: sharpe {got!r} != {want!r} "
                         f"({d} ulp)")
    finite_got = [x for x in per_fold_got if math.isfinite(x)]
    finite_want = [x for x in per_fold_want if math.isfinite(x)]
    if len(finite_got) != len(finite_want):
        fails.append(f"aggregate: {len(finite_got)} finite Sharpes, fixture has "
                     f"{len(finite_want)}")
    else:
        n += 1
        agg_got, agg_want = float(np.mean(finite_got)), float(np.mean(finite_want))
        d = ulp_distance(agg_got, agg_want)
        worst = max(worst, d)
        if d > ulp_tolerance:
            fails.append(f"aggregate sharpe {agg_got!r} != {agg_want!r} ({d} ulp)")
    record(6, "sharpe", fails,
           "per-fold and aggregate Sharpe, same ulp bound and same reason",
           n_compared=n, max_ulp=worst)
    return report


def log_parity_fixture(report: ParityReport, log_dir: Optional[Path] = None):
    """Append a PARITY_FIXTURE event. Never counts as a trial."""
    from research import log as research_log

    kw = {} if log_dir is None else {"log_dir": log_dir}
    passed = [l for l in report.layers if l.passed]
    return research_log.append_record(
        research_log.EventType.PARITY_FIXTURE,
        record_id=f"record:t9b-{HYPOTHESIS_ID}-mask-off",
        title=f"T9b mask-off parity against {HYPOTHESIS_ID} seq={SEQ}",
        note=(
            f"Re-ran the seq={SEQ} nested walk-forward through the rewritten "
            f"post/ path and compared six layers in order: "
            f"{'PASS' if report.passed else 'FAIL'}"
            + ("" if report.passed else f", stopped at {report.stopped_at}")
            + ".\n\nThis is a migration test of an already-adjudicated "
            "mechanism, not a new trial. crest_n_keel's verdict is untouched "
            "and is not reopened by reproducing it — seq=49 found that picking "
            "the sweep leader was worth +0.025 Sharpe against the gate-passing "
            "pool at p=0.430, and nothing here revisits that.\n\nThe trade "
            "records this pins are DERIVED, not original: no artifact ever "
            "held trade-for-trade records, and the regeneration was admitted "
            "only because every fold boundary and recorded statistic "
            "reproduced exactly. See the fixture's provenance_note for what "
            "that does and does not establish.\n\nMask-off only: the mask-on "
            "comparison needs a mask-aware walk-forward that does not exist "
            "yet, and half of it reported here would be uninterpretable."
        ),
        metrics={
            "mode": report.mode,
            "passed": report.passed,
            "layers_checked": len(report.layers),
            "layers_passed": len(passed),
            "stopped_at": report.stopped_at,
            "fixture": report.fixture,
            "fixture_provenance": report.provenance,
            "counts_as_trial": False,
        },
        **kw,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ulp", type=int, default=PRICE_ULP_TOLERANCE,
                    help="units in the last place tolerated on prices/Sharpe")
    ap.add_argument("--json", action="store_true", help="emit the report as JSON")
    ap.add_argument("--log", action="store_true",
                    help="append a PARITY_FIXTURE event to the research log")
    args = ap.parse_args()

    report = check_mask_off(ulp_tolerance=args.ulp)
    if args.log:
        log_parity_fixture(report)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
        return 0 if report.passed else 1

    print(f"T9b mask-off parity vs {report.fixture} [{report.provenance}]")
    for layer in report.layers:
        mark = "ok  " if layer.passed else "FAIL"
        ulp = f" max_ulp={layer.max_ulp}" if layer.max_ulp is not None else ""
        print(f"  {layer.order}. {mark} {layer.layer} "
              f"({layer.n_compared} compared){ulp}")
        for line in layer.failures:
            print(f"        {line}")
    print("PASSED" if report.passed else f"FAILED at {report.stopped_at}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
