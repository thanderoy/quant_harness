"""research.post.sweeps.rerun_seq29_session — quantify the seq=29 timezone error.

seq=29 walk-forwarded crest_n_keel in two configurations, "24/7" and
"session-only", and recorded OOS Sharpe 0.27-0.41 across them. The session-only
arm filtered hour-of-day on an index that is broker server time labelled UTC,
so it traded roughly 05:00-14:00 / 06:00-15:00 UTC instead of the intended
08:00-17:00, DST-dependent.

This re-runs the SAME strategy and the SAME window twice -- once on the
mislabelled index (reproducing what seq=29 actually measured) and once on
corrected true-UTC bars -- so the difference is the size of the error in the
logged record. The 24/7 arm is included as a control: it has no session filter,
so a relabel cannot change it, and any difference there would indicate a bug in
this script rather than a real effect.

Usage:  python -m research.post.sweeps.rerun_seq29_session
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, "/home/roy-thande/Local/qhf_harness")

import numpy as np

from qhf.data import PepperstoneXAUUSDCostModel                       # noqa: E402
from qhf.engines import run_walk_forward, PEPPERSTONE_XAUUSD_KNOWN_GAPS  # noqa: E402
from qhf.engines.strategies.hma_stoch import HMAStoch1H               # noqa: E402

from research.post.sweeps.data import load                            # noqa: E402

OUT = Path(__file__).resolve().parents[3] / "research" / "data" / "crest_n_keel"
ARMS = [("24_7", None), ("session_8_17", (8, 17))]
TRAIN, TEST, STEP = "1460D", "365D", "365D"


def run(tz: str, session):
    df = load("H1", tz=tz)
    # The harness compares against tz-NAIVE exclude_ranges and treats a naive
    # index as UTC. Drop the tz AFTER the conversion so both arms are naive and
    # the only difference between them is the 2-3h EET/EEST correction itself.
    df = df.copy()
    df.index = df.index.tz_convert("UTC").tz_localize(None)
    wf = run_walk_forward(
        df, HMAStoch1H, params={}, session_hours=session,
        train_size=TRAIN, test_size=TEST, step_size=STEP,
        exclude_ranges=PEPPERSTONE_XAUUSD_KNOWN_GAPS,
        cash=10_000, cost_model=PepperstoneXAUUSDCostModel(),
        periods_per_year=None, verbose=False)
    oos = np.asarray(wf.oos_sharpes, float)
    oos = oos[np.isfinite(oos)]
    return {"n_folds": len(wf.folds), "oos_sharpe_pooled": float(wf.oos_sharpe),
            "oos_sharpe_mean_folds": float(oos.mean()) if oos.size else None,
            "oos_folds_positive": int((oos > 0).sum()),
            "oos_max_dd": float(wf.oos_max_dd), "oos_trades": int(wf.n_trades_oos),
            "oos_profit_factor": float(wf.oos_profit_factor)}


def main() -> int:
    res = {}
    for arm, session in ARMS:
        for tz in ("legacy_utc", "server_eet"):
            key = f"{arm}__{tz}"
            print(f"running {key} ...", flush=True)
            res[key] = run(tz, session)
            r = res[key]
            print(f"  folds {r['n_folds']}  pooled OOS Sharpe "
                  f"{r['oos_sharpe_pooled']:+.4f}  trades {r['oos_trades']:,}  "
                  f"PF {r['oos_profit_factor']:.3f}  DD {r['oos_max_dd']:.3f}",
                  flush=True)

    print("\n=== SIZE OF THE seq=29 ERROR ===")
    for arm, _ in ARMS:
        a = res[f"{arm}__legacy_utc"]["oos_sharpe_pooled"]
        b = res[f"{arm}__server_eet"]["oos_sharpe_pooled"]
        tag = ("CONTROL - must be ~0" if arm == "24_7"
               else "the correction to the logged figure")
        print(f"  {arm:<14} logged-basis {a:+.4f}  corrected {b:+.4f}  "
              f"delta {b - a:+.4f}   [{tag}]")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "seq29_session_rerun.json").write_text(json.dumps(res, indent=2))
    print(f"\nwrote {OUT / 'seq29_session_rerun.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
