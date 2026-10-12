"""research.post.sr_star_reeval — the shelved XAUUSD DSRs, re-priced against SR*.

Phase 2b's second half (docs/STATUS.md, "What done looks like for Phase 2b";
REWRITE.md D5). Every DSR in the research log before T8 was computed against
an economic benchmark of zero (log seq=94). On gold that is not a neutral
choice: D5 puts XAUUSD buy-and-hold at 0.6343 annualised, so a zero benchmark
handed every long-biased gold mechanism that Sharpe for free.

This module recomputes those DSRs with ONLY the benchmark changed. Everything
else -- the return stream, N, the Var(SR) path -- is held at what the original
evaluation used, and the SR*=0 column must reproduce the logged figure before
the other columns mean anything. It writes no log entries; recording the
result is the owner's decision.

Which evaluations are re-run, and why not the rest
--------------------------------------------------
A positive SR* can only LOWER a DSR (it shifts the benchmark up and leaves
everything else alone). So an evaluation that already failed 0.95 against zero
cannot change verdict here; only the readings that cleared 0.95 against zero
can move. Those are re-run in full, and the failing DSRs whose streams were
cheap to recover are carried alongside so the table is complete. Mechanisms
whose verdict was decided by something other than a Sharpe-vs-zero
comparison -- a permutation null, a pool control, a drift-matched random-entry
control, a cost-floor translation -- are listed in :data:`MOOT` with the
reason, and are NOT recomputed: those nulls already carry gold's drift.

Three benchmarks, each for one job
----------------------------------
``d5``           D5's buy-and-hold SR* (phase0_universe_20260907.json), the
                 benchmark T8 wires into DSR. This is the re-evaluation.
``same_window``  Buy-and-hold over the stream's OWN calendar window, by D5's
                 exact method (H1 closes -> daily log returns -> sqrt(252)).
                 D5 covers 2004-06..2025-12; an OOS stream from 2008-06 on
                 faces a different gold, so this is the like-for-like check.
``exposure``     Always-long held for the stream's mean holding length, from
                 every bar in the same window: the per-trade Sharpe of drift
                 capture at the stream's own exposure. Screen-hygiene rule 3's
                 "excess over always-long", in Sharpe units. Weaker than D5
                 (it asks "beyond drift?", not "better than holding gold?").

Periodicity
-----------
Every stream here is per-TRADE. The annualised benchmarks are converted with
``sr_ann / sqrt(trades_per_year)`` at the trade frequency the mechanism's own
Sharpe was annualised with (recorded per stream as ``ppy_basis``); the
exposure benchmark is computed directly in per-trade units and needs no
conversion.

Usage::

    python -m research.post.sr_star_reeval                 # table from saved streams
    python -m research.post.sr_star_reeval --regenerate h1_momentum_unfiltered ...
    python -m research.post.sr_star_reeval --regenerate all  # incl. the slow WF
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from research import admission
from research.post.dsr import (
    DEFAULT_DSR_THRESHOLD,
    benchmark_from_d5,
    deflated_sharpe_ratio,
)
from research.post.sweeps import data as sweep_data

RESEARCH_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[4]
ARTIFACT_DIR = RESEARCH_ROOT / "post" / "artifacts"
STREAM_DIR = ARTIFACT_DIR / "sr_star_streams"
MANIFEST = STREAM_DIR / "manifest.json"
OUT = ARTIFACT_DIR / "sr_star_reeval.json"
D5_ARTIFACT = REPO_ROOT / "phase0" / "phase0_universe_20260907.json"
SYMBOL = "XAUUSD"

#: D5's annualisation: daily log returns, 252 trading days.
D5_DAYS_PER_YEAR = 252
#: Tolerance for "the SR*=0 column reproduces the logged DSR". Logged values
#: are rounded to 3-4 places in the log text; artifacts carry full precision.
REPRODUCE_TOL = 5e-4

#: Where the streams that were saved rather than regenerated come from:
#: ``QH_DATA_DIR`` (the out-of-repo research/data tree), via the same
#: resolution the sweep loaders use. Unset, it is the in-repo data directory,
#: which does not hold them, and the import refuses.
QH_DATA_DIR = sweep_data.DATA_DIR


@dataclass(frozen=True)
class Evaluation:
    """One logged DSR evaluation, pinned to what it originally used."""

    key: str
    seq: int
    hypothesis_id: str
    label: str
    source: str                     # "regenerated" | "read"
    n_trials: tuple[int, ...]
    logged_dsr: dict[int, float]
    decisive_n: Optional[int]
    var_sr_path: str                # "estimated" | "override (harness twin)"
    verdict_then: str
    decided_by_now: str
    caveats: tuple[str, ...] = field(default_factory=tuple)


EVALUATIONS: tuple[Evaluation, ...] = (
    Evaluation(
        key="h1_momentum_unfiltered", seq=62,
        hypothesis_id="h1_momentum_nested_wf",
        label="H1 intraday momentum, frozen intraday_ret/h=12, unfiltered",
        source="regenerated", n_trials=(1, 21, 126, 276),
        logged_dsr={1: 0.9959400806723786, 21: 0.7657554992912876,
                    126: 0.5144277457742589, 276: 0.4121051184338076},
        decisive_n=126, var_sr_path="estimated",
        verdict_then="FAIL DSR 0.95 at every N except N=1 (seq=62)",
        decided_by_now=("seq=63 replaced DSR with a within-day permutation "
                        "null; seq=65 killed on the nested stream, p=0.1045. "
                        "The null mean is +0.011 per trade: it already "
                        "carries gold's drift."),
    ),
    Evaluation(
        key="h1_momentum_lowvol", seq=62,
        hypothesis_id="h1_momentum_nested_wf",
        label="H1 intraday momentum, low-volatility filter variant",
        source="regenerated", n_trials=(1, 21, 126, 276),
        logged_dsr={1: 0.9936020791347699, 21: 0.714743261814088,
                    126: 0.4516588263883289, 276: 0.3520553135540311},
        decisive_n=126, var_sr_path="estimated",
        verdict_then="FAIL DSR 0.95 at every N except N=1 (seq=62)",
        decided_by_now=("Same as unfiltered; the gate itself was later "
                        "killed on its own null (seq=71, advantage p=0.0647) "
                        "and failed replication (seq=74)."),
    ),
    Evaluation(
        key="cnk_momentum_wf", seq=36,
        hypothesis_id="crest_n_keel_momentum",
        label="crest_n_keel MOMENTUM walk-forward (TradingView Config A)",
        source="regenerated", n_trials=(1, 20),
        logged_dsr={1: 1.0, 20: 0.061},
        decisive_n=20, var_sr_path="override (harness twin)",
        verdict_then="FAIL (DSR only); PASS at num_trials=1 (seq=36)",
        decided_by_now=("seq=64: the stream is contaminated -- parameters "
                        "were selected on full history. The family died on "
                        "seq=49's nested pool control (NK2 p=0.430), not "
                        "on DSR."),
        caveats=(
            "Fold geometry 1460D/365D/180D overlaps test windows, so the "
            "3829-trade stream holds 1970 distinct trades counted ~twice. "
            "The logged OOS Sharpe 1.20 annualises the duplicated stream over "
            "its calendar span (~229/yr); at the true rate it is ~0.86.",
            "Regenerated under CostScenario.CONSERVATIVE (7.0 USD/lot, 0.22 "
            "USD/oz), the cost model in force at seq=36. The current default "
            "(MEASURED) gives OOS Sharpe 1.317 and does not reproduce.",
        ),
    ),
    Evaluation(
        key="zlch_sweep_leader", seq=40,
        hypothesis_id="zlch_param_sweep",
        label="zerolag_chandelier sweep leader, H4 atr8 x2.0 long, IN-SAMPLE",
        source="regenerated", n_trials=(15, 18480),
        logged_dsr={15: 0.9980013712709273, 18480: 0.7391681696382162},
        decisive_n=18480, var_sr_path="estimated",
        verdict_then="K3 FAIL at N=18,480; 0.998 at N=15 noted as the wrong N",
        decided_by_now=("seq=68 nested walk-forward: ZK1 and ZK2 fail "
                        "(pool p=1.0000). Refuted on the selection control."),
        caveats=("In-sample full-history leader of an 18,480-config grid; "
                 "a sweep leader is not a candidate (seq=49, seq=68).",),
    ),
    Evaluation(
        key="cnk_sweep_leader", seq=45,
        hypothesis_id="cnk_param_sweep",
        label="crest_n_keel sweep leader, H4 momentum long, IN-SAMPLE",
        source="read", n_trials=(17, 119917),
        logged_dsr={17: 0.9998, 119917: 0.8391},
        decisive_n=119917, var_sr_path="estimated",
        verdict_then="K3 FAIL at N=119,917; 0.9998 at N=17 noted as the wrong N",
        decided_by_now=("seq=49 nested walk-forward: NK2 fails (p=0.430). "
                        "Selection carries no OOS information."),
        caveats=("In-sample full-history leader; not a candidate.",),
    ),
    Evaluation(
        key="flood_tide_median_config", seq=56,
        hypothesis_id="flood_tide_h1",
        label="flood_tide median-ranked config, bracket atr21 sl1 tp2 long, IN-SAMPLE",
        source="regenerated", n_trials=(1, 19, 3744),
        logged_dsr={1: 0.9618420957333165, 19: 0.4579731462762655,
                    3744: 0.03282083511263301},
        decisive_n=3744, var_sr_path="estimated",
        verdict_then="FAIL at grid N (seq=56); verdict left OPEN",
        decided_by_now=("Shelving at seq=32/34 rests on the regime-filtered "
                        "E-Ratio null; the median config already beat its "
                        "drift-matched random-entry null (p=0.000, null "
                        "mean -0.356)."),
        caveats=("The N=1 reading (0.9618) is in the seq=56 artifact but not "
                 "its log metrics, so seq=94's list of zero-benchmark passes "
                 "omits it.",),
    ),
    Evaluation(
        key="crest_n_keel_wf_24h", seq=29,
        hypothesis_id="crest_n_keel",
        label="crest_n_keel pullback walk-forward, 24/7",
        source="read", n_trials=(5,),
        logged_dsr={5: 0.106},
        decisive_n=5, var_sr_path="override (harness twin)",
        verdict_then="FAIL DSR (0.106) and PF (1.15) (seq=29)",
        decided_by_now=("seq=45 P7: deployed region median Sharpe -0.074; "
                        "seq=49 NK2 kills the family."),
        caveats=("Same overlapping fold geometry as seq=36 (duplicated "
                 "trades). N=5 and the twin's Var(SR) are what reproduce the "
                 "logged figure (data/crest_n_keel/recompute_dsr.py).",),
    ),
    Evaluation(
        key="crest_n_keel_wf_session", seq=29,
        hypothesis_id="crest_n_keel",
        label="crest_n_keel pullback walk-forward, 08-17 session (mislabelled tz)",
        source="read", n_trials=(5,),
        logged_dsr={5: 0.028},
        decisive_n=5, var_sr_path="override (harness twin)",
        verdict_then="FAIL DSR (0.028) (seq=29)",
        decided_by_now=("seq=52: the session filter read broker time as UTC; "
                        "on true UTC the arm is net-losing (-0.239)."),
        caveats=("The stream itself is invalid (seq=52); carried only so "
                 "every seq=29 DSR has a row.",),
    ),
)

#: XAUUSD verdicts that did NOT rest on a Sharpe/DSR comparison against zero.
#: Recomputing a DSR for these would manufacture a re-evaluation.
MOOT: tuple[dict, ...] = (
    {"seq": "30, 51", "hypothesis_id": "asqs / asqs_param_sweep",
     "decided_by": "OOS Sharpe -1.06 (net-losing); AK4 grid median negative "
                   "at every timeframe",
     "why_moot": "Negative raw Sharpe; DSR was ~0 against zero already and a "
                 "positive SR* only lowers it."},
    {"seq": "43", "hypothesis_id": "ebb_n_flow_sweep",
     "decided_by": "K1: leader loses to matched random entry, p=1.000",
     "why_moot": "Killed on the drift-matched control; DSR failed at every N "
                 "including the log floor (0.8008 at N=16)."},
    {"seq": "46", "hypothesis_id": "cnk_param_sweep (walk-forward)",
     "decided_by": "Contaminated stream (seq=64); family killed by seq=49 NK2",
     "why_moot": "DSR 0.0 at grid N, 0.042/0.359 at N=17 -- failed against "
                 "zero, so cannot change."},
    {"seq": "49", "hypothesis_id": "cnk_nested_walk_forward",
     "decided_by": "NK2 pool control, p=0.430",
     "why_moot": "Selection control compares configs with each other; drift "
                 "is common to both arms."},
    {"seq": "65", "hypothesis_id": "h1_momentum_nested_wf (final verdict)",
     "decided_by": "Within-day permutation null, nested stream p=0.1045",
     "why_moot": "The null re-runs the long-only pipeline on permuted bars, so "
                 "its mean (+0.011 fixed, +0.005 nested) is the drift "
                 "benchmark. The seq=62 DSR is re-priced above for "
                 "completeness only."},
    {"seq": "68", "hypothesis_id": "zlch_nested_walk_forward",
     "decided_by": "ZK1 mean OOS +0.012; ZK2 pool control p=1.0000",
     "why_moot": "ZK1 is a Sharpe-vs-zero test, but it FAILED against zero; "
                 "a higher bar cannot rescue it. ZK2 is relative."},
    {"seq": "70-72", "hypothesis_id": "state_gate_nested_wf (low-vol gate)",
     "decided_by": "V2 pool control (p=0.0384 worse than chance); advantage "
                   "stream null p=0.0647",
     "why_moot": "The advantage stream is gated minus ungated on the same "
                 "long-only signal, so drift cancels; the null mean "
                 "(+0.0158) prices the residual."},
    {"seq": "74, 131", "hypothesis_id": "vol_gate_cross_instrument",
     "decided_by": "Advantage stream vs own permutation null on XAG/US500",
     "why_moot": "Not XAUUSD-decided; per-instrument nulls carry each drift."},
    {"seq": "32, 34", "hypothesis_id": "flood_tide_h1 / _iter2 (shelving)",
     "decided_by": "Regime-filtered E-Ratio null",
     "why_moot": "Entry-only MFE/MAE null, not a Sharpe. The seq=56 DSR is "
                 "re-priced above."},
    {"seq": "38", "hypothesis_id": "regime_align_h1",
     "decided_by": "K2: edge explained by the bias-eligible drift null",
     "why_moot": "Already benchmarked against drift."},
    {"seq": "54, 55", "hypothesis_id": "avwap_sweep_reclaim / multibar",
     "decided_by": "Drift-matched random-entry control; surface median",
     "why_moot": "No DSR in the verdict."},
    {"seq": "20", "hypothesis_id": "zerolag_chandelier (entry)",
     "decided_by": "E-Ratio 0.98, p=0.772 (hard gate)",
     "why_moot": "Entry-only statistic."},
    {"seq": "48, 75, 80", "hypothesis_id": "asian_session_fade, "
                                           "gold_dxy_divergence, gold_real_yields",
     "decided_by": "Gross USD/oz vs round-trip cost; lead-lag; rule-3 excess "
                   "over always-long (seq=80)",
     "why_moot": "Economic and prerequisite tests, not Sharpe; seq=80 already "
                 "measured against always-long."},
    {"seq": "58", "hypothesis_id": "feature_edge_screen",
     "decided_by": "Top-minus-bottom decile spread vs cost",
     "why_moot": "A long-short spread nets drift out."},
    {"seq": "78", "hypothesis_id": "ensemble_vs_selection",
     "decided_by": "E1 total return, sign test",
     "why_moot": "Methodology test, decided in dollars, relative."},
)


# --------------------------------------------------------------------------- #
# Stream storage                                                              #
# --------------------------------------------------------------------------- #

def _stream_path(key: str) -> Path:
    return STREAM_DIR / f"{key}.csv"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_stream(key: str, returns: np.ndarray,
                 bars_held: Optional[np.ndarray], meta: dict) -> None:
    """Persist one per-trade stream and its metadata.

    Floats are written with 17 significant digits, which round-trips a
    double; read back with ``float_precision='round_trip'``.
    """
    STREAM_DIR.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame({"ret": np.asarray(returns, float)})
    if bars_held is not None:
        frame["bars_held"] = np.asarray(bars_held, int)
    path = _stream_path(key)
    frame.to_csv(path, index=False, float_format="%.17g")
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    manifest[key] = {**meta, "n": int(frame.shape[0]), "sha256": _sha256(path)}
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def read_stream(key: str) -> tuple[np.ndarray, Optional[np.ndarray], dict]:
    """Saved stream, its holding lengths (if known) and its manifest entry."""
    frame = pd.read_csv(_stream_path(key), float_precision="round_trip")
    meta = json.loads(MANIFEST.read_text())[key]
    held = frame["bars_held"].to_numpy(int) if "bars_held" in frame else None
    return frame["ret"].to_numpy(float), held, meta


# --------------------------------------------------------------------------- #
# Regeneration -- frozen runners, logged parameters, nothing re-tuned         #
# --------------------------------------------------------------------------- #

def _require_admitted(tf: str) -> None:
    admission.require(SYMBOL, tf, data_dir=sweep_data.DATA_DIR)


def _bar_positions(index: pd.DatetimeIndex, stamps) -> np.ndarray:
    pos = index.get_indexer(pd.DatetimeIndex(stamps))
    if (pos < 0).any():
        raise ValueError("trade timestamp not on the bar grid")
    return pos


def regenerate_h1_momentum(lowvol: bool) -> tuple[np.ndarray, np.ndarray, dict]:
    """seq=62's streams, via momentum_dsr.fold_returns unchanged."""
    from research.pre.feature_screen import build_features
    from research.post.sweeps.momentum_dsr import HORIZON, fold_returns
    from research.post.sweeps.momentum_nested_wf import STEP, TEST, TF, TRAIN

    _require_admitted(TF)
    df = sweep_data.load(TF, tz="server_eet", with_volume=True)
    feats, _ = build_features(df)
    folds, start = [], df.index[0]
    while start + TRAIN + TEST <= df.index[-1]:
        folds.append((start, start + TRAIN, start + TRAIN + TEST))
        start = start + STEP
    r = fold_returns(df, feats, folds, lowvol)
    r = r[np.isfinite(r)]
    window_days = (folds[-1][2] - folds[0][1]).days
    meta = {
        "source": "regenerated",
        "runner": "research.post.sweeps.momentum_dsr.fold_returns",
        "timeframe": TF,
        "window": [str(folds[0][1].date()), str(folds[-1][2].date())],
        "ppy": r.size / (window_days / 365.25),
        "ppy_basis": "realised trades per year over the contiguous OOS "
                     "window (17 x 365D), as momentum_nested_wf annualises",
    }
    return r, np.full(r.size, HORIZON, int), meta


def regenerate_zlch_leader() -> tuple[np.ndarray, np.ndarray, dict]:
    """seq=40's leader, via the sweep's own deepdive._build."""
    from research.post.sweeps.analyze import load_all
    from research.post.sweeps.deepdive import _build

    sweep = load_all()
    best = sweep.sort_values("sharpe_px", ascending=False).iloc[0]
    _require_admitted(best["timeframe"])
    df, _, _, _, sim = _build(best)
    held = (_bar_positions(df.index, sim["exit_ts"])
            - _bar_positions(df.index, sim["entry_ts"]))
    meta = {
        "source": "regenerated",
        "runner": "research.post.sweeps.deepdive._build (seq=40 leader row)",
        "timeframe": str(best["timeframe"]),
        "config": {k: (v.item() if hasattr(v, "item") else v)
                   for k, v in best[["atr_period", "atr_mult", "bias_tf",
                                     "zlsma_len", "direction",
                                     "min_atr"]].items()},
        "window": [str(df.index[0].date()), str(df.index[-1].date())],
        "ppy": float(best["trades_per_year"]),
        "ppy_basis": "the sweep's trades_per_year (n / first-entry..last-exit "
                     "span); the seq=40 DSR displayed at a rounded 41",
    }
    return np.asarray(sim["px_returns"], float), held, meta


def regenerate_flood_tide_median() -> tuple[np.ndarray, np.ndarray, dict]:
    """seq=56's median-ranked config, via the signal sweep's own machinery."""
    from research.post.sweeps import cnk_engine as E
    from research.post.sweeps.run_signal_sweep import (
        RISK_PCT, SIGNALS, _G, _init_worker, _masks)

    spec = SIGNALS["flood_tide"]
    _require_admitted(spec["tf"])
    _require_admitted("H4")
    df = sweep_data.load(spec["tf"], tz="server_eet", with_volume=spec["volume"])
    aux = sweep_data.load("H4", tz="server_eet")
    _init_worker("flood_tide", df, aux)
    _G["tf"] = spec["tf"]
    bars = E.Bars(df)
    long_m, short_m = _masks(("flood_tide", 20, 0.3, 200))
    atr_v = E.atr(bars.high, bars.low, bars.close, 21)
    sim = E.simulate(bars, "pullback", np.zeros(bars.n, float), atr_v,
                     long_m, short_m, enable_long=True, enable_short=False,
                     sl_mult=1.0, tp_mult=2.0, trail_mult=0.0,
                     risk_pct=RISK_PCT, min_atr=0.0, max_dd_halt=1.0)
    m = E.metrics(sim, basis="price")
    held = (_bar_positions(df.index, sim["exit_ts"])
            - _bar_positions(df.index, sim["entry_ts"]))
    meta = {
        "source": "regenerated",
        "runner": "research.post.sweeps.run_signal_sweep (cnk_engine.simulate)",
        "timeframe": spec["tf"],
        "config": {"entry": [20, 0.3, 200], "exit": "bracket", "atr_period": 21,
                   "sl_mult": 1.0, "tp_mult": 2.0, "direction": "long",
                   "min_atr": 0.0},
        "window": [str(df.index[0].date()), str(df.index[-1].date())],
        "ppy": float(m["trades_per_year"]),
        "ppy_basis": "the engine's trades_per_year (n / first-entry..last-exit "
                     "span), as the sweep annualised",
    }
    return np.asarray(sim["px_returns"], float), held, meta


def regenerate_cnk_momentum() -> tuple[np.ndarray, np.ndarray, dict]:
    """seq=36's walk-forward, as examples/run_cnk_momentum.py runs it.

    Same strategy, defaults, geometry, gaps and cash. The one explicit input
    is the cost scenario: seq=36 ran under the then-default Razor model,
    which is now ``CostScenario.CONSERVATIVE``. Slow (minutes).
    """
    from research.datasets import PepperstoneXAUUSDCostModel, load_bars
    from research.engines import PEPPERSTONE_XAUUSD_KNOWN_GAPS, run_walk_forward
    from research.engines.strategies.cnk_momentum import CrestNKeelMomentum

    _require_admitted("H1")
    bars = load_bars(str(sweep_data.DATA_DIR / "XAUUSD_H1.csv"),
                     expected_timeframe="H1").df
    wf = run_walk_forward(
        bars, CrestNKeelMomentum, session_hours=None, params={},
        train_size="1460D", test_size="365D", step_size="180D",
        exclude_ranges=PEPPERSTONE_XAUUSD_KNOWN_GAPS, cash=10_000,
        cost_model=PepperstoneXAUUSDCostModel.for_scenario("conservative"),
        periods_per_year=None, verbose=False)
    trades = pd.concat([f.oos_result.trades for f in wf.folds
                        if not f.oos_result.trades.empty], ignore_index=True)
    r = wf.oos_return_pct.to_numpy(float)
    if r.size != len(trades):
        raise ValueError("OOS return series and trade table disagree")
    ppy_twin = int(r.size / max(len(wf.folds), 1))
    var_ann = float(pd.Series(wf.is_sharpes).var(ddof=1))
    meta = {
        "source": "regenerated",
        "runner": "examples/run_cnk_momentum.py path (run_walk_forward, "
                  "CostScenario.CONSERVATIVE)",
        "timeframe": "H1",
        "window": [str(wf.folds[0].test_start.date()),
                   str(wf.folds[-1].test_end.date())],
        "n_folds": len(wf.folds),
        "harness_oos_sharpe": float(wf.oos_sharpe),
        "harness_oos_profit_factor": float(wf.oos_profit_factor),
        "distinct_entries": int(trades["EntryTime"].nunique()),
        "ppy": r.size / (len(wf.folds) * 365 / 365.25),
        "ppy_basis": "trades per 365D test window (n / n_folds), the rate the "
                     "seq=36 DSR used (int 116)",
        "var_sr_per_obs": var_ann / ppy_twin,
        "var_sr_basis": f"harness twin: Var(IS Sharpes, annualised) / {ppy_twin}",
    }
    held = (trades["ExitBar"] - trades["EntryBar"]).to_numpy(int)
    return r, held, meta


def import_cnk_sweep_leader() -> tuple[np.ndarray, np.ndarray, dict]:
    """seq=45's leader returns, saved by the sweep in QH_DATA_DIR."""
    src = QH_DATA_DIR / "crest_n_keel" / "cnk_leader_returns.csv"
    t = pd.read_csv(src, float_precision="round_trip",
                    parse_dates=["entry_time", "exit_time"])
    _require_admitted("H4")
    h4 = sweep_data.load("H4")
    held = (_bar_positions(h4.index, t["exit_time"])
            - _bar_positions(h4.index, t["entry_time"]))
    span_days = (t["exit_time"].iloc[-1] - t["entry_time"].iloc[0]).days
    meta = {
        "source": "read",
        "from": "QH_DATA_DIR/crest_n_keel/cnk_leader_returns.csv (px_return)",
        "source_sha256": _sha256(src),
        "timeframe": "H4",
        "window": [str(h4.index[0].date()), str(h4.index[-1].date())],
        "ppy": len(t) / (span_days / 365.25),
        "ppy_basis": "n / first-entry..last-exit span, as cnk_engine.metrics",
    }
    return t["px_return"].to_numpy(float), held, meta


#: The harness exporter's twin Var(SR) and trades-per-fold for seq=29, as
#: recorded in QH_DATA_DIR/crest_n_keel/recompute_dsr.py.
SEQ29_TWIN = {"24h": (0.103499, 9), "session": (0.219370, 4)}
SEQ29_FOLDS = 33


def import_crest_n_keel(arm: str) -> tuple[np.ndarray, None, dict]:
    """seq=29's OOS returns, saved by examples/export_crest_n_keel_returns.py.

    The CSV carries no timestamps, so there is no holding length (no exposure
    benchmark) and the window is taken from the same harness geometry seq=36
    used on the same file, which is the cnk_momentum stream's window.
    """
    src = QH_DATA_DIR / "crest_n_keel" / f"crest_n_keel_oos_returns_{arm}.csv"
    r = pd.read_csv(src, float_precision="round_trip")["oos_return_pct"]
    var_ann, ppy_twin = SEQ29_TWIN[arm]
    meta = {
        "source": "read",
        "from": f"QH_DATA_DIR/crest_n_keel/{src.name}",
        "source_sha256": _sha256(src),
        "timeframe": "H1",
        "window_from": "cnk_momentum_wf (identical 1460D/365D/180D geometry)",
        "ppy": r.size / (SEQ29_FOLDS * 365 / 365.25),
        "ppy_basis": "trades per 365D test window (n / 33 folds)",
        "var_sr_per_obs": var_ann / ppy_twin,
        "var_sr_basis": f"harness twin: {var_ann} / {ppy_twin} "
                        "(recompute_dsr.py)",
    }
    return r.to_numpy(float), None, meta


REGENERATORS = {
    "h1_momentum_unfiltered": partial(regenerate_h1_momentum, False),
    "h1_momentum_lowvol": partial(regenerate_h1_momentum, True),
    "zlch_sweep_leader": regenerate_zlch_leader,
    "flood_tide_median_config": regenerate_flood_tide_median,
    "cnk_momentum_wf": regenerate_cnk_momentum,
    "cnk_sweep_leader": import_cnk_sweep_leader,
    "crest_n_keel_wf_24h": partial(import_crest_n_keel, "24h"),
    "crest_n_keel_wf_session": partial(import_crest_n_keel, "session"),
}


# --------------------------------------------------------------------------- #
# Benchmarks                                                                  #
# --------------------------------------------------------------------------- #

def same_window_buy_and_hold(start: str, end: str) -> dict:
    """Annualised buy-and-hold Sharpe over [start, end], by D5's method.

    D5 (phase0/run_d2_d4_d5.py): H1 closes, last per day, log returns,
    sqrt(252), on the legacy (server-time-as-UTC) index. Over the full file
    this reproduces D5's 0.634324777595297 exactly; see the tests.
    """
    _require_admitted("H1")
    close = sweep_data.load("H1")["close"]
    daily = close.resample("1D").last().dropna()
    r = np.log(daily).diff().dropna()
    r = r[(r.index >= pd.Timestamp(start, tz="UTC"))
          & (r.index <= pd.Timestamp(end, tz="UTC"))]
    sd = float(r.std(ddof=1))
    return {"start": str(r.index[0].date()), "end": str(r.index[-1].date()),
            "n_days": int(r.size),
            "sharpe_annualised": float(r.mean() / sd * math.sqrt(D5_DAYS_PER_YEAR))}


def exposure_matched_always_long(timeframe: str, start: str, end: str,
                                 hold_bars: int) -> dict:
    """Per-trade Sharpe of always-long held ``hold_bars`` from every bar.

    Simple close-to-close returns over the stream's own bar file and window,
    no costs. Already per-observation in the stream's (per-trade) units.
    """
    _require_admitted(timeframe)
    close = sweep_data.load(timeframe)["close"]
    close = close[(close.index >= pd.Timestamp(start, tz="UTC"))
                  & (close.index <= pd.Timestamp(end, tz="UTC"))].to_numpy(float)
    r = close[hold_bars:] / close[:-hold_bars] - 1.0
    return {"hold_bars": int(hold_bars), "n_holds": int(r.size),
            "sharpe_per_trade": float(r.mean() / r.std(ddof=1))}


# --------------------------------------------------------------------------- #
# Evaluation                                                                  #
# --------------------------------------------------------------------------- #

def _dsr(r: np.ndarray, ppy: float, benchmark: float, n: int,
         var_sr: Optional[float]):
    return deflated_sharpe_ratio(r, benchmark_sharpe=benchmark, n_trials=n,
                                 var_sr=var_sr, periods_per_year=ppy)


def _window(meta: dict, manifest: dict) -> list[str]:
    if "window" in meta:
        return meta["window"]
    return manifest["cnk_momentum_wf"]["window"]


def evaluate_one(ev: Evaluation, d5_annualised: float, manifest: dict) -> dict:
    """One row per logged N: DSR at SR* = 0, D5, same-window, exposure."""
    r, held, meta = read_stream(ev.key)
    ppy = float(meta["ppy"])
    var_sr = meta.get("var_sr_per_obs")
    start, end = _window(meta, manifest)
    window_bh = same_window_buy_and_hold(start, end)

    benchmarks = {
        "zero": 0.0,
        "d5": benchmark_from_d5(SYMBOL, D5_ARTIFACT, ppy),
        "same_window": window_bh["sharpe_annualised"] / math.sqrt(ppy),
    }
    exposure = None
    if held is not None:
        exposure = exposure_matched_always_long(
            meta["timeframe"], start, end, max(int(round(held.mean())), 1))
        benchmarks["exposure"] = exposure["sharpe_per_trade"]

    rows = []
    for n in ev.n_trials:
        dsrs = {k: _dsr(r, ppy, b, n, var_sr) for k, b in benchmarks.items()}
        logged = ev.logged_dsr.get(n)
        zero = dsrs["zero"].dsr
        rows.append({
            "n_trials": n,
            "decisive_n": n == ev.decisive_n,
            "logged_dsr": logged,
            "reproduced": (logged is not None
                           and abs(zero - logged) <= max(REPRODUCE_TOL,
                                                         _rounding(logged))),
            "dsr": {k: v.dsr for k, v in dsrs.items()},
            "passes": {k: bool(v.dsr > DEFAULT_DSR_THRESHOLD)
                       for k, v in dsrs.items()},
            "sr_star_selection": dsrs["zero"].sr_star_selection,
            "var_sr": dsrs["zero"].var_sr,
            "var_sr_source": dsrs["zero"].var_sr_source,
        })

    first = _dsr(r, ppy, 0.0, ev.n_trials[0], var_sr)
    return {
        "key": ev.key, "seq": ev.seq, "hypothesis_id": ev.hypothesis_id,
        "label": ev.label, "source": ev.source,
        "stream": {k: v for k, v in meta.items() if k != "sha256"},
        "n_obs": int(r.size),
        "sr_hat_per_obs": first.sr_hat_per_obs,
        "sr_hat_annualised_at_ppy": first.sr_hat_per_obs * math.sqrt(ppy),
        "skew": first.skew, "kurtosis": first.kurtosis,
        "benchmarks_per_obs": benchmarks,
        "benchmarks_annualised": {
            "zero": 0.0, "d5": d5_annualised,
            "same_window": window_bh["sharpe_annualised"],
            **({"exposure": benchmarks["exposure"] * math.sqrt(ppy)}
               if exposure else {})},
        "same_window_buy_and_hold": window_bh,
        "exposure_matched_always_long": exposure,
        "var_sr_path": ev.var_sr_path,
        "rows": rows,
        "verdict_flips_at_any_n": {
            k: [row["n_trials"] for row in rows
                if row["passes"]["zero"] and not row["passes"][k]]
            for k in benchmarks if k != "zero"},
        "verdict_flips_at_decisive_n": any(
            row["passes"]["zero"] != row["passes"][k]
            for row in rows if row["decisive_n"]
            for k in benchmarks if k != "zero"),
        "verdict_then": ev.verdict_then,
        "decided_by_now": ev.decided_by_now,
        "caveats": list(ev.caveats),
    }


def _rounding(logged: float) -> float:
    """Half a unit in the last place the log recorded, for 3-4 dp figures."""
    text = repr(logged)
    places = len(text.split(".")[1]) if "." in text else 0
    return 0.5 * 10 ** -places if places <= 4 else 0.0


def d5_xauusd_annualised() -> float:
    payload = json.loads(D5_ARTIFACT.read_text())
    for row in payload["d5_benchmark_sharpe"]["per_instrument"]:
        if row["symbol"] == SYMBOL:
            return float(row["buy_and_hold_sharpe_annualised"])
    raise KeyError(SYMBOL)


def build_table() -> dict:
    manifest = json.loads(MANIFEST.read_text())
    d5 = d5_xauusd_annualised()
    rows = [evaluate_one(ev, d5, manifest) for ev in EVALUATIONS]
    payload = json.loads(D5_ARTIFACT.read_text())["d5_benchmark_sharpe"]
    d5_row = next(x for x in payload["per_instrument"] if x["symbol"] == SYMBOL)
    return {
        "generator": "research.post.sr_star_reeval",
        "d5_artifact": str(D5_ARTIFACT.relative_to(REPO_ROOT)),
        "d5_xauusd": d5_row,
        "threshold": DEFAULT_DSR_THRESHOLD,
        "rule": ("A positive SR* only lowers DSR, so only readings that "
                 "passed against zero can change verdict."),
        "evaluations": rows,
        "moot": list(MOOT),
        "log_writes": 0,
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--regenerate", nargs="*", default=[],
                    help="stream keys to rebuild before tabulating, or 'all'")
    args = ap.parse_args(argv)
    keys = list(REGENERATORS) if args.regenerate == ["all"] else args.regenerate
    for key in keys:
        r, held, meta = REGENERATORS[key]()
        write_stream(key, r, held, meta)
        print(f"wrote stream {key}: n={r.size}")
    table = build_table()
    OUT.write_text(json.dumps(table, indent=2) + "\n")
    for ev in table["evaluations"]:
        print(f"\nseq={ev['seq']} {ev['key']}  sr/obs={ev['sr_hat_per_obs']:.5f}"
              f"  ppy={ev['stream']['ppy']:.2f}  SR*/obs " + "  ".join(
                  f"{k}={v:.5f}" for k, v in ev["benchmarks_per_obs"].items()))
        for row in ev["rows"]:
            mark = "*" if row["decisive_n"] else " "
            print(f"  {mark}N={row['n_trials']:<7} logged={row['logged_dsr']}"
                  f" repro={row['reproduced']}  " + "  ".join(
                      f"{k}={v:.4f}" for k, v in row["dsr"].items()))
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
