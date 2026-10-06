"""
Pre-registration: flood_tide_h1

Donchian-55 breakout with HTF-EMA and Efficiency Ratio regime gate.
XAUUSD H1, long-only.

This module CONSTRUCTS the pre-registration payload and calls
register_hypothesis(). It does not execute any research.

Execution flow:
    1. python -m research.pre.flood_tide_h1  -> writes JSONL entry, returns seq/hash
    2. research.pre.signal_edge on frozen params  -> E-Ratio gate
    3. If passed: btpy_runner walk-forward     -> OOS Sharpe series
    4. research.post.dsr on Sharpe series       -> DSR verdict
"""
from __future__ import annotations

import json
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from research.log import (  # append-only, hash-chained
    EdgeGateRole,
    register_hypothesis,
    render_markdown,
    trial_count,
    verify,
)


# ---------------------------------------------------------------------------
# Frozen parameters — DO NOT MODIFY POST-REGISTRATION
# Any change requires a new register_hypothesis call and trial_count increment.
# ---------------------------------------------------------------------------
FROZEN_PARAMS: dict[str, float | int | str] = {
    "entry_len": 55,           # Turtle System 2 robust region
    "exit_len": 20,            # Asymmetric Turtle exit
    "stop_len": 10,            # Initial stop channel
    "htf_timeframe": "H4",
    "htf_ema_len": 200,
    "er_len": 14,
    "er_threshold": 0.30,
    "risk_pct": 1.0,           # Research risk — NOT the live 5% in trading_profile
    "direction": "long_only",
    "reentry_cooldown_bars": 5,
}


# ---------------------------------------------------------------------------
# Payload schema — mirrors the fields expected by research/log.py
# Rename fields here to match actual log.py signature before commit.
# ---------------------------------------------------------------------------
class EdgeGate(BaseModel):
    component: str
    role: Literal["HARD_GATE", "DIAGNOSTIC"]
    rationale: str


class FalsifiablePrediction(BaseModel):
    id: str
    statement: str
    metric: str
    threshold: str
    test: str


class KillCriterion(BaseModel):
    id: str
    condition: str
    action: Literal["TERMINAL_KILL", "SHELVE", "KILL"]


class CostModel(BaseModel):
    spread_model: str
    commission_per_001_lot_round_trip_usd: Decimal
    entry_slippage_formula: str
    exit_slippage_formula: str
    order_filling: Literal["IOC"] = "IOC"


class FloodTideH1Payload(BaseModel):
    codename: str = "flood_tide_h1"
    strategy_family: str = "trend_following_breakout"
    instrument: str = "XAUUSD"
    broker: str = "pepperstone_razor"
    execution_timeframe: str = "H1"
    regime_timeframe: str = "H4"
    direction: Literal["long_only"] = "long_only"

    mechanism: str
    mechanism_prior_work: list[str]

    frozen_params: dict[str, float | int | str]

    predictions: list[FalsifiablePrediction]
    kill_criteria: list[KillCriterion]
    edge_gates: list[EdgeGate]

    cost_model: CostModel

    stopping_rule: str
    correlation_notes: str
    seed_metric_status: Literal["NONE"] = "NONE"

    reproducibility_artifact_path: str | None = None  # populated on signal_edge run

    author: str = "roy"
    partner: str = "claude"


# ---------------------------------------------------------------------------
# Payload construction
# ---------------------------------------------------------------------------
def build_payload() -> FloodTideH1Payload:
    return FloodTideH1Payload(
        mechanism=(
            "On XAUUSD, a close exceeding the prior 55-bar H1 high represents a "
            "shift in institutional flow that persists beyond a single bar. Gold's "
            "macro drivers (real rates, DXY, geopolitical premium, CB flows) "
            "reprice on multi-day-to-week horizons, not intraday. A confirmed H1 "
            "breakout in a structurally trending H4 regime is therefore expected "
            "to produce positive-expectancy continuation over the following "
            "20-100 H1 bars. Long-only: XAU secular uptrend + ebb_n_flow "
            "falsification of symmetric counter-trend logic on gold."
        ),
        mechanism_prior_work=[
            "dennis_eckhardt_turtle_system_1_and_2",
            "clenow_following_the_trend",
            "crest_n_keel_falsification_edge_in_exit_finding",
            "ebb_n_flow_falsification_symmetric_logic_fails_on_xau",
            "research.signal_edge.e_ratio_methodology",
        ],
        frozen_params=FROZEN_PARAMS,
        predictions=[
            FalsifiablePrediction(
                id="P1_entry_edge",
                statement=(
                    "Breakout entry has positive edge above random baseline "
                    "across short/medium/long holding horizons."
                ),
                metric="E-Ratio at H in {20, 50, 100} bars",
                threshold="E-Ratio > 1.10 AND p < 0.05, N >= 500 permutations",
                test="research.signal_edge.run(hypothesis='flood_tide_h1')",
            ),
            FalsifiablePrediction(
                id="P2_oos_survival",
                statement=(
                    "Full system (entry + trail exit + regime filter) produces "
                    "statistically significant OOS Sharpe after multiple-testing "
                    "correction."
                ),
                metric="Deflated Sharpe Ratio, 20-year walk-forward (2004-2024)",
                threshold="DSR > 0.95 with honest trial_count denominator",
                test="btpy_runner + research.dsr.compute(sharpe_series)",
            ),
            FalsifiablePrediction(
                id="P3_trade_shape",
                statement=(
                    "Trade distribution matches trend-following payoff profile. "
                    "If shape violated, P&L is not from the stated mechanism."
                ),
                metric="win_rate, avg_winner / avg_loser, max_consecutive_losers",
                threshold=(
                    "win_rate in [0.30, 0.45] AND "
                    "avg_winner / avg_loser >= 2.5 AND "
                    "max_consecutive_losers <= 12"
                ),
                test="post-walk-forward trade log analysis",
            ),
        ],
        kill_criteria=[
            KillCriterion(
                id="K1",
                condition="E-Ratio <= 1.0 at any H in {20, 50, 100}",
                action="TERMINAL_KILL",
            ),
            KillCriterion(
                id="K2",
                condition="E-Ratio > 1.0 but p >= 0.05 at all H",
                action="SHELVE",
            ),
            KillCriterion(
                id="K3",
                condition="Walk-forward OOS DSR <= 0.95",
                action="KILL",
            ),
            KillCriterion(
                id="K4",
                condition="Walk-forward max drawdown > 40% at 1% risk sizing",
                action="KILL",
            ),
            KillCriterion(
                id="K5",
                condition="Trade shape violates P3 thresholds",
                action="KILL",
            ),
        ],
        edge_gates=[
            EdgeGate(
                component="entry_donchian_55_breakout",
                role="HARD_GATE",
                rationale=(
                    "Breakout / continuation entry. E-Ratio <= 1.0 is terminal "
                    "per house rules — no exit design can rescue a non-edge "
                    "entry in this category."
                ),
            ),
            EdgeGate(
                component="exit_donchian_20_trail",
                role="DIAGNOSTIC",
                rationale=(
                    "Trend-following edge lives in exit design "
                    "(crest_n_keel finding). E-Ratio not applicable — measured "
                    "via full-system walk-forward contribution."
                ),
            ),
            EdgeGate(
                component="regime_htf_ema_and_er",
                role="DIAGNOSTIC",
                rationale=(
                    "Filter contribution measured via ablation. Not gated in "
                    "isolation. ADX explicitly excluded — documented "
                    "ineffective on XAU."
                ),
            ),
        ],
        cost_model=CostModel(
            spread_model=(
                "Time-varying per hour-of-day bucket from Pepperstone Razor "
                "historical spread series. Fallback: conservative flat 25 pips "
                "($2.50 per 0.01 lot round-trip)."
            ),
            commission_per_001_lot_round_trip_usd=Decimal("7.00"),
            entry_slippage_formula=(
                "fill = breakout_level + 0.5 * spread + 0.2 * ATR(14)_breakout_bar"
            ),
            exit_slippage_formula=(
                "fill = trail_level - 0.3 * ATR(14)_current_bar"
            ),
        ),
        stopping_rule=(
            "Iteration 1: this pre-registration exactly. No parameter changes. "
            "Iteration 2: only if Iteration 1 produces E-Ratio > 1.0 but fails "
            "DSR. Exactly one parameter changed, ex-ante justified via ablation "
            "diagnostics, logged as a new register_hypothesis call incrementing "
            "trial_count. After Iteration 2: SHELVED. No third iteration."
        ),
        correlation_notes=(
            "vs crest_n_keel (H1 HMA/Stoch, falsified): both H1 long-biased XAU; "
            "signal-timing correlation expected 0.3-0.5; not a genuine "
            "diversification add if both were live. "
            "vs asqs (M5 scalping, halted): different timeframe and mechanism; "
            "moot. "
            "vs avwap_multibar_reclaim_m15 (pending): different TF and mechanism "
            "(reclaim vs breakout); formal correlation study deferred until "
            "one clears DSR gate. "
            "Portfolio role: occupies 'H1 trend continuation' slot. Does not by "
            "itself constitute a diversified book."
        ),
    )


# ---------------------------------------------------------------------------
# Registration
#
# The real research/log.py API is:
#   register_hypothesis(hypothesis_id, title, mechanism, *, market, timeframe,
#                       family, edge_gate_role, predictions, note) -> LogEntry
# A HYPOTHESIS event ALWAYS counts as a trial (no counts_as_trial arg), so the
# honest trial_count() denominator increments automatically — matching the
# original script's intent. There is no parent_seq / payload dict. The full
# frozen pydantic payload is embedded verbatim in `note` so the append-only
# hash chain protects the complete pre-registration (predictions, kill criteria,
# edge gates, cost model, stopping rule), not just the flat header fields.
# ---------------------------------------------------------------------------
def _log_predictions(payload: FloodTideH1Payload) -> list[str]:
    """Flatten the structured predictions to the log's list[str] schema."""
    return [
        f"{p.id}: {p.statement} "
        f"[metric={p.metric}; threshold={p.threshold}; test={p.test}]"
        for p in payload.predictions
    ]


def _preregistration_note(payload: FloodTideH1Payload) -> str:
    """Embed the full frozen payload as JSON so the hash chain protects it."""
    body = json.dumps(payload.model_dump(mode="json"), indent=2, sort_keys=True)
    return (
        "PRE-REGISTRATION (frozen; do not modify post-registration). Full "
        "falsifiable payload embedded verbatim below so the hash chain protects "
        "the complete commitment (predictions, kill criteria, edge gates, cost "
        "model, stopping rule):\n" + body
    )


def main() -> None:
    payload = build_payload()

    entry = register_hypothesis(
        payload.codename,
        title=(
            "flood_tide_h1 — Donchian-55 H1 breakout with H4-EMA + "
            "Efficiency-Ratio regime gate (XAUUSD, long-only)"
        ),
        mechanism=payload.mechanism,
        market=payload.instrument,
        timeframe=payload.execution_timeframe,
        family=payload.strategy_family,
        # Breakout/continuation entry -> HARD_GATE (house rule). The hypothesis
        # carries the role of its gating entry; see edge_gates[0] / kill K1.
        edge_gate_role=EdgeGateRole.HARD_GATE,
        predictions=_log_predictions(payload),
        note=_preregistration_note(payload),
    )

    render_markdown()
    ok, msg = verify()

    print(f"seq          : {entry.seq}")
    print(f"entry_hash   : {entry.entry_hash}")
    print(f"prev_hash    : {entry.prev_hash or '(genesis)'}")
    print(f"edge_gate    : {entry.edge_gate_role.value}")
    print(f"trial_count  : {trial_count()}")
    print(f"chain        : {msg} (ok={ok})")
    print()
    print("Next step:")
    print("  research/.venv/bin/python -m research.pre.signal_edge "
          "--hypothesis flood_tide_h1   # E-Ratio HARD_GATE (P1 / K1)")


if __name__ == "__main__":
    main()
