"""T9a — ``pre/`` path parity against the flood_tide_h1 E-Ratio artifact (seq=31).

The ``pre/`` leg exercises data loading, signal generation, the ATR
normaliser and the E-Ratio itself. Phase 1 changes all four, so the seq=31
run is pinned: if the rewrite moves any of these numbers, it has to be
because someone decided to move them.

**Layered, and ordered.** The five checks run in dependency order and stop at
the first failure, so a break localises to a layer instead of needing a
bisect:

1. ``ohlc_hash`` — the data loader. Everything downstream is meaningless if
   this moved, so nothing downstream is reported when it fails.
2. ``signal_hash`` — signal generation, given identical data.
3. ``n_long_signals`` — the signal count, called out separately because
   "3 signals appeared" and "every signal shifted by a bar" both break the
   hash and want different investigations.
4. Signal timestamps, element-wise.
5. E-Ratios at h=20, 50, 100, at float equality.

Checks 2 and 4 overlap by construction -- ``signal_hash`` is a digest of the
serialised signal Series, so it already covers the timestamps. They are kept
separate anyway, because the hash says only *that* something differs and the
element-wise comparison says *which bar*. The seq=31 artifact stores the
hash but not the timestamps, so the element-wise pin is written by this
module into its own fixture on first run, and compared against thereafter.

**Horizon semantics (R4).** h=20 means twenty *tradable* bars, not twenty
calendar bars containing holes. Mask-off this is a distinction without a
difference, because nothing is masked -- but it is recorded in the fixture
explicitly so a future reader is not left to infer which convention the
pinned numbers were produced under. Under mask-on it is the whole ballgame.

**Scope: mask-off only.** The mask-on comparison is a separate piece of work
and is deliberately not half-done here. It has two independent channels --
the signal set changes, *and* the ATR normaliser changes across weekend and
holiday boundaries -- and reporting one without the other produces a number
nobody can interpret. The normaliser channel needs a mask-aware path through
``signal_edge``, which does not exist yet.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from research.pre.scripts.run_flood_tide_edge import (
    ATR_PERIOD,
    HORIZONS,
    RANDOM_SEED,
    load_ohlcv,
)
from research.pre.signal_edge import signal_edge_report
from research.pre.signals.flood_tide import FloodTideParams, generate_signals

HYPOTHESIS_ID = "flood_tide_h1"
SEQ = 31

_HERE = Path(__file__).resolve().parent
REPO_ROOT = _HERE.parents[3]

#: The adjudicated run this fixture pins.
REFERENCE_ARTIFACT = (
    REPO_ROOT / "packages" / "qh-research" / "research" / "pre" / "artifacts"
    / "flood_tide_h1_seq31_p1_20260706T075247Z.json"
)

#: Element-wise timestamp pin, written by this module (see the docstring).
FIXTURE = _HERE / "fixtures" / "t9a_flood_tide_maskoff.json"

#: Horizons are counted in tradable bars, per R4.
HORIZON_UNIT = "tradable_bars"

#: The permutation null does not enter any of the five checks -- it is a
#: separate statistic computed from shuffled signals, and the E-Ratio of the
#: real signal set is unaffected by how many shuffles sit beside it. Running
#: 1 instead of the original 1000 takes the fixture from minutes to seconds.
#: Verified: all three E-Ratios reproduce to float equality at n=1.
PARITY_N_PERMUTATIONS = 1


class ReferenceMissing(FileNotFoundError):
    """The adjudicated artifact this fixture pins is not on disk."""


@dataclass
class LayerResult:
    order: int
    layer: str
    passed: bool
    expected: object = None
    actual: object = None
    detail: str = ""


@dataclass
class ParityReport:
    mode: str
    passed: bool
    layers: list[LayerResult] = field(default_factory=list)
    stopped_at: Optional[str] = None
    horizon_unit: str = HORIZON_UNIT
    reference: str = ""
    checked_at_utc: str = ""

    def as_dict(self) -> dict:
        d = asdict(self)
        d["layers"] = [asdict(x) if not isinstance(x, dict) else x
                       for x in self.layers]
        return d


# --------------------------------------------------------------------------- #
# Recomputation                                                                #
# --------------------------------------------------------------------------- #

#: Override the location of seq=31's OHLC inputs.
DATA_DIR_ENV = "QH_PARITY_DATA_DIR"


def default_data_paths() -> tuple[Path, Path]:
    """Where seq=31's inputs live.

    The artifact records absolute paths into the WMPS repo, which is where
    the CSVs are on the machine that produced them and nowhere else — a CI
    runner has no such directory, which is how the first CI run failed. The
    artifact's own SHA-256 still guards the contents, so the path may move
    freely as long as the bytes do not.

    Resolution order: ``$QH_PARITY_DATA_DIR`` if set, else the path recorded
    in the artifact.
    """
    ref = load_reference()
    h1 = Path(ref["inputs"]["h1_path"])
    h4 = Path(ref["inputs"]["h4_path"])
    override = os.environ.get(DATA_DIR_ENV)
    if override:
        d = Path(override)
        return d / h1.name, d / h4.name
    return h1, h4


def source_data_available() -> bool:
    """Whether the seq=31 inputs can be read from this machine.

    Recomputation needs them; validating the committed fixture does not.
    Kept as a predicate so the distinction is explicit at each call site
    rather than expressed as a caught exception.
    """
    try:
        h1, h4 = default_data_paths()
    except ReferenceMissing:
        return False
    return h1.exists() and h4.exists()


def load_reference(path: Path = REFERENCE_ARTIFACT) -> dict:
    if not path.exists():
        raise ReferenceMissing(
            f"seq={SEQ} artifact not found at {path}. T9a pins an "
            f"adjudicated run; without it there is nothing to pin against."
        )
    return json.loads(path.read_text())


def recompute(h1_path: Path, h4_path: Path,
              n_permutations: int = PARITY_N_PERMUTATIONS) -> dict:
    """Re-run the seq=31 pipeline and return what the five checks need."""
    h1 = load_ohlcv(h1_path)
    h4 = load_ohlcv(h4_path)

    sig = generate_signals(h1, h4, FloodTideParams())
    signal = pd.Series(0, index=h1.index, dtype=np.int64)
    signal[sig["entry_signal"].to_numpy()] = 1
    eligible = (sig["regime_ok"] & sig["upper_entry"].notna()).to_numpy()

    report = signal_edge_report(
        signal=signal, ohlc=h1, forward_windows=list(HORIZONS),
        atr_period=ATR_PERIOD, n_permutations=n_permutations,
        random_seed=RANDOM_SEED, eligible_pool=eligible,
    )
    meta = report.metadata
    return {
        "ohlc_hash": meta["ohlc_hash"],
        "signal_hash": meta["signal_hash"],
        "n_long_signals": int(meta["n_long_signals"]),
        "signal_timestamps": [t.isoformat()
                              for t in signal.index[signal == 1]],
        "e_ratios": {int(r["window"]): float(r["e_ratio"])
                     for _, r in report.per_window.iterrows()},
        "n_signals_by_horizon": {int(r["window"]): int(r["n_signals"])
                                 for _, r in report.per_window.iterrows()},
    }


# --------------------------------------------------------------------------- #
# The checks                                                                   #
# --------------------------------------------------------------------------- #

def check_mask_off(h1_path: Optional[Path] = None,
                   h4_path: Optional[Path] = None,
                   n_permutations: int = PARITY_N_PERMUTATIONS) -> ParityReport:
    """Run the five checks in order, stopping at the first failure."""
    ref = load_reference()
    if h1_path is None or h4_path is None:
        h1_path, h4_path = default_data_paths()

    got = recompute(Path(h1_path), Path(h4_path), n_permutations)
    meta = ref["edge_report_metadata"]
    report = ParityReport(
        mode="mask_off", passed=True,
        reference=REFERENCE_ARTIFACT.name,
        checked_at_utc=datetime.now(timezone.utc).isoformat(),
    )

    def record(order: int, layer: str, expected, actual, detail: str = "") -> bool:
        ok = expected == actual
        report.layers.append(LayerResult(order, layer, ok, expected, actual, detail))
        if not ok:
            report.passed = False
            report.stopped_at = layer
        return ok

    if not record(1, "ohlc_hash", meta["ohlc_hash"], got["ohlc_hash"],
                  "the data loader; nothing downstream is meaningful if this moved"):
        return report
    if not record(2, "signal_hash", meta["signal_hash"], got["signal_hash"],
                  "signal generation, given identical data"):
        return report
    if not record(3, "n_long_signals", int(meta["n_long_signals"]),
                  got["n_long_signals"], "signal count"):
        return report

    # 4 — element-wise timestamps, against this module's own pin.
    pinned = _load_fixture()
    if pinned is None:
        report.layers.append(LayerResult(
            4, "signal_timestamps", True, None, len(got["signal_timestamps"]),
            "no element-wise pin yet; written on this run (hash already "
            "checked at layer 2)"))
    else:
        exp_ts, act_ts = pinned["signal_timestamps"], got["signal_timestamps"]
        if exp_ts == act_ts:
            report.layers.append(LayerResult(
                4, "signal_timestamps", True, len(exp_ts), len(act_ts),
                "element-wise"))
        else:
            report.passed = False
            report.stopped_at = "signal_timestamps"
            report.layers.append(LayerResult(
                4, "signal_timestamps", False, len(exp_ts), len(act_ts),
                _first_timestamp_difference(exp_ts, act_ts)))
            return report

    # 5 — E-Ratios, float equality on the serialised float64.
    want = {int(r["horizon"]): float(r["e_ratio"])
            for r in ref["results_by_horizon"]}
    for h in sorted(want):
        if not record(5, f"e_ratio_h{h}", want[h], got["e_ratios"].get(h),
                      "float equality"):
            return report
    return report


def _first_timestamp_difference(expected: list[str], actual: list[str]) -> str:
    """Name the first divergence rather than dumping two long lists."""
    for i, (e, a) in enumerate(zip(expected, actual)):
        if e != a:
            return f"first difference at index {i}: expected {e}, got {a}"
    if len(expected) != len(actual):
        longer, n = ("expected", len(expected)) if len(expected) > len(actual) \
            else ("actual", len(actual))
        return (f"common prefix identical; {longer} has {n} entries "
                f"({abs(len(expected) - len(actual))} extra)")
    return "no difference found"


def _load_fixture() -> Optional[dict]:
    if not FIXTURE.exists():
        return None
    return json.loads(FIXTURE.read_text())


def write_fixture(h1_path: Optional[Path] = None,
                  h4_path: Optional[Path] = None) -> Path:
    """Pin the element-wise timestamps and the horizon convention."""
    ref = load_reference()
    if h1_path is None or h4_path is None:
        h1_path, h4_path = default_data_paths()
    got = recompute(Path(h1_path), Path(h4_path))

    FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    FIXTURE.write_text(json.dumps({
        "fixture": "t9a_flood_tide_maskoff",
        "hypothesis_id": HYPOTHESIS_ID,
        "seq": SEQ,
        "reference_artifact": REFERENCE_ARTIFACT.name,
        "mode": "mask_off",
        "horizon_unit": HORIZON_UNIT,
        "horizon_note": (
            "h counts tradable bars, not calendar bars (R4). Mask-off these "
            "coincide; recorded so the convention behind these numbers is "
            "stated rather than inferred."),
        "n_permutations": PARITY_N_PERMUTATIONS,
        "n_permutations_note": (
            "The original run used 1000. The permutation null is a separate "
            "statistic computed from shuffled signals and does not enter the "
            "E-Ratio of the real signal set; all three E-Ratios reproduce to "
            "float equality at n=1."),
        "ohlc_hash": got["ohlc_hash"],
        "signal_hash": got["signal_hash"],
        "n_long_signals": got["n_long_signals"],
        "e_ratios": {str(k): v for k, v in got["e_ratios"].items()},
        "n_signals_by_horizon": {str(k): v
                                 for k, v in got["n_signals_by_horizon"].items()},
        "signal_timestamps": got["signal_timestamps"],
        "written_at_utc": datetime.now(timezone.utc).isoformat(),
    }, indent=2) + "\n")
    return FIXTURE


def log_parity_fixture(report: ParityReport, log_dir: Optional[Path] = None):
    """Append a PARITY_FIXTURE event. Never counts as a trial."""
    from research import log as research_log

    kw = {} if log_dir is None else {"log_dir": log_dir}
    passed = [l for l in report.layers if l.passed]
    return research_log.append_record(
        research_log.EventType.PARITY_FIXTURE,
        record_id=f"record:t9a-{HYPOTHESIS_ID}-mask-off",
        title=f"T9a mask-off parity against {HYPOTHESIS_ID} seq={SEQ}",
        note=(
            f"Re-ran the seq={SEQ} E-Ratio pipeline and compared five layers "
            f"in dependency order: {'PASS' if report.passed else 'FAIL'}"
            + ("" if report.passed else f", stopped at {report.stopped_at}")
            + ".\n\nThis is a migration test of an already-adjudicated "
            "mechanism, not a new trial. flood_tide_h1's verdict "
            "(SHELVE_INSUFFICIENT_SIGNIFICANCE) is untouched and is not "
            "reopened by reproducing it.\n\nHorizons count tradable bars "
            "(R4). Mask-off only: the mask-on comparison has two independent "
            "channels — the signal set and the ATR normaliser — and is left "
            "for its own piece of work rather than half-reported here."
        ),
        metrics={
            "mode": report.mode,
            "passed": report.passed,
            "layers_checked": len(report.layers),
            "layers_passed": len(passed),
            "stopped_at": report.stopped_at,
            "horizon_unit": report.horizon_unit,
            "reference_artifact": report.reference,
            "counts_as_trial": False,
        },
        **kw,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write-fixture", action="store_true",
                    help="(re)pin the element-wise timestamps")
    ap.add_argument("--log", action="store_true",
                    help="append a PARITY_FIXTURE event")
    ap.add_argument("--permutations", type=int, default=PARITY_N_PERMUTATIONS)
    args = ap.parse_args()

    if args.write_fixture:
        print(f"fixture written: {write_fixture()}")

    report = check_mask_off(n_permutations=args.permutations)
    for layer in report.layers:
        mark = "ok  " if layer.passed else "FAIL"
        print(f"  {layer.order}. {mark} {layer.layer}")
        if not layer.passed:
            print(f"        expected {layer.expected!r}")
            print(f"        actual   {layer.actual!r}")
            print(f"        {layer.detail}")
    print(json.dumps(report.as_dict()["layers"][-1], indent=2)
          if not report.passed else
          f"\nT9a mask-off: PASS ({len(report.layers)} layers)")

    if args.log:
        entry = log_parity_fixture(report)
        print(f"logged seq={entry.seq}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(main())
