"""Backfill the research log with every hypothesis tested to date.

This sets the honest starting N for multiple-testing corrections. Re-running
is safe: hypotheses already registered are skipped, so this script is
idempotent.

Usage
-----
Dry-run (default — prints the plan, writes nothing)::

    research/.venv/bin/python -m research.seed_log

Commit (actually append to the log)::

    research/.venv/bin/python -m research.seed_log --commit
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from research.log import (
    DEFAULT_LOG_DIR,
    EdgeGateRole,
    Stage,
    Verdict,
    register_hypothesis,
    render_markdown,
    trial_count,
    update_hypothesis,
)


@dataclass
class _Seed:
    hypothesis_id: str
    title: str
    mechanism: str
    family: str
    edge_gate_role: EdgeGateRole
    timeframe: str = ""
    market: str = "XAUUSD"
    # ordered list of UPDATE events to fold in after registration
    updates: list[dict] = field(default_factory=list)


SEEDS: list[_Seed] = [
    _Seed(
        hypothesis_id="crest_n_keel",
        title="HMA+Stoch 1H pullback (a.k.a. hma_stoch_1h)",
        mechanism=(
            "Trend established by HMA slope; entries taken on Stochastic "
            "pullback into trend direction. Profit captured by asymmetric "
            "ATR exit (SL 1.5·ATR / TP 3.0·ATR) — entry edge ≈ flat by design."
        ),
        family="pullback",
        edge_gate_role=EdgeGateRole.DIAGNOSTIC,
        timeframe="H1",
        updates=[
            dict(stage=Stage.SIGNAL_EDGE, verdict=Verdict.OPEN,
                 metrics={"e_ratio_w30": 0.90, "p_value": 0.34},
                 note=("Entry E-Ratio ~0.9 — no standalone edge. Expected for "
                       "a pullback entry; do NOT kill on this (diagnostic).")),
            dict(stage=Stage.OOS, verdict=Verdict.PROMOTED,
                 metrics={"sharpe_oos": 1.76},
                 note="Sharpe ~1.76 OOS; profit lives in the asymmetric ATR exit."),
            dict(stage=Stage.DEPLOYED, verdict=Verdict.DEPLOYED,
                 note="Live in production."),
        ],
    ),
    _Seed(
        hypothesis_id="asqs",
        title="ASQ SafeScalping v1.20 — M5 7-condition breakout",
        mechanism=(
            "Seven-condition M5 breakout filter (HLPeak channel + multi-MA "
            "stack + ATR regime + session window). Continuation entry where "
            "the breakout itself is expected to do the work."
        ),
        family="breakout",
        edge_gate_role=EdgeGateRole.HARD_GATE,
        timeframe="M5",
        updates=[
            dict(stage=Stage.SIGNAL_EDGE, verdict=Verdict.PROMOTED,
                 note="Entry edge confirmed (breakout — must pass hard gate)."),
            dict(stage=Stage.OOS, verdict=Verdict.PROMOTED,
                 metrics={"sharpe_oos": 5.14, "profit_factor": 1.55},
                 note="OOS Sharpe 5.14, PF 1.55 on harness backtest."),
            dict(stage=Stage.DEPLOYED, verdict=Verdict.DEPLOYED,
                 note=("Live; 3 live-adapter bugs fixed during deployment "
                       "(SL/TP, drawdown, daily-cap query).")),
        ],
    ),
    _Seed(
        hypothesis_id="ebb_n_flow",
        title="Bollinger mean-reversion with KER gate",
        mechanism=(
            "Symmetric fade of Bollinger band touches gated by Kaufman "
            "Efficiency Ratio (only when trend strength is low)."
        ),
        family="mean_reversion",
        edge_gate_role=EdgeGateRole.DIAGNOSTIC,
        updates=[
            dict(stage=Stage.SIGNAL_EDGE, verdict=Verdict.OPEN,
                 metrics={"e_ratio_w30": 0.97},
                 note=("Entry E-Ratio flat — diagnostic only for MR, so not "
                       "a kill signal on its own.")),
            dict(stage=Stage.IS_BACKTEST, verdict=Verdict.KILLED,
                 metrics={"gross_expectancy": -1.0},
                 note=("Negative gross expectancy. Gold's secular uptrend "
                       "punishes symmetric fades; MR sleeve needs asymmetric "
                       "treatment of long vs short. Killed on backtest, not "
                       "on the flat entry E-Ratio.")),
        ],
    ),
    _Seed(
        hypothesis_id="donchian_50_control",
        title="Donchian-50 breakout (positive control)",
        mechanism=(
            "Classic 50-bar Donchian channel breakout — used as a positive "
            "control for signal_edge.py to confirm the tool detects real "
            "entry edge when present. Not a deployment candidate."
        ),
        family="breakout",
        edge_gate_role=EdgeGateRole.HARD_GATE,
        timeframe="H1",
        updates=[
            dict(stage=Stage.SIGNAL_EDGE, verdict=Verdict.SHELVED,
                 metrics={"e_ratio_w10": 1.11, "e_ratio_w50": 1.17,
                          "p_value": 0.000},
                 note=("E-Ratio 1.11→1.17 across windows at p=0.000. Confirms "
                       "the tool detects real edge. Shelved — control, not a "
                       "deployment candidate.")),
        ],
    ),
    _Seed(
        hypothesis_id="avwap_liquidity_sweep",
        title="H1 HMA + NY AVWAP + 5-day VP + sweep/reclaim",
        mechanism=(
            "Continuation entry: H1 HMA filter establishes trend, NY-session "
            "anchored VWAP and 5-day volume profile locate liquidity, entry "
            "fires on a sweep-and-reclaim of identified levels."
        ),
        family="breakout",
        edge_gate_role=EdgeGateRole.HARD_GATE,
        timeframe="H1",
        updates=[
            dict(stage=Stage.HYPOTHESIS, verdict=Verdict.OPEN,
                 note="Fully specced; backtest harness not built yet."),
        ],
    ),
    _Seed(
        hypothesis_id="asian_session_fade",
        title="Asian-session ATR-channel fade",
        mechanism=(
            "Liquidity vacuum 22:00–05:00 GMT lets price overshoot an HLPeak "
            "ATR channel; mean-revert back to channel midline near London "
            "open. StochMA used as the trigger."
        ),
        family="mean_reversion",
        edge_gate_role=EdgeGateRole.DIAGNOSTIC,
        timeframe="M5",
        updates=[
            dict(stage=Stage.HYPOTHESIS, verdict=Verdict.OPEN,
                 note=("MR sleeve candidate; target 0.0–0.25 correlation with "
                       "the trend book. Edge expected in the exit (diagnostic).")),
        ],
    ),
    _Seed(
        hypothesis_id="gold_dxy_divergence",
        title="Gold–DXY cointegration divergence MR",
        mechanism=(
            "Stat-arb style mean-reversion of gold vs DXY when the "
            "cointegration spread stretches beyond a Z-score threshold."
        ),
        family="mean_reversion",
        edge_gate_role=EdgeGateRole.DIAGNOSTIC,
        updates=[
            dict(stage=Stage.HYPOTHESIS, verdict=Verdict.OPEN,
                 note=("Falsification prerequisites undone: rolling "
                       "correlation, CADF cointegration test, cross-corr lag "
                       "analysis. No spec yet.")),
        ],
    ),
]


def _plan(log_dir: Path) -> tuple[list[str], list[_Seed]]:
    """Return (printable-plan-lines, seeds-to-actually-write)."""
    from research.log import _read_all  # internal; fine for a seed script

    existing_ids = {e.hypothesis_id for e in _read_all(log_dir)
                    if e.event_type.value == "hypothesis"}

    lines = []
    todo: list[_Seed] = []
    for s in SEEDS:
        if s.hypothesis_id in existing_ids:
            lines.append(f"  SKIP  {s.hypothesis_id} (already registered)")
            continue
        todo.append(s)
        lines.append(
            f"  ADD   {s.hypothesis_id} [{s.family} / "
            f"{s.edge_gate_role.value}] + {len(s.updates)} update(s)"
        )
    return lines, todo


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--commit", action="store_true",
        help="Actually write to the log. Without this, prints the plan only.",
    )
    parser.add_argument(
        "--log-dir", type=Path, default=DEFAULT_LOG_DIR,
        help=f"Log directory (default: {DEFAULT_LOG_DIR}).",
    )
    args = parser.parse_args(argv)

    lines, todo = _plan(args.log_dir)
    print(f"Seed plan ({len(todo)} to add, {len(SEEDS) - len(todo)} to skip):")
    for line in lines:
        print(line)

    if not args.commit:
        print("\nDry run. Re-run with --commit to write.")
        return 0

    for s in todo:
        register_hypothesis(
            s.hypothesis_id, title=s.title, mechanism=s.mechanism,
            market=s.market, timeframe=s.timeframe, family=s.family,
            edge_gate_role=s.edge_gate_role, log_dir=args.log_dir,
        )
        for u in s.updates:
            update_hypothesis(s.hypothesis_id, log_dir=args.log_dir, **u)

    render_markdown(log_dir=args.log_dir)
    print(f"\nCommitted. trial_count() = {trial_count(args.log_dir)}")
    print(f"Rendered: {args.log_dir / 'log.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
