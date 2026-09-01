"""Registration: zlch_param_sweep — post-kill exhaustive sweep of zerolag_chandelier.

Registers the sweep in the research log. Run once:
    python -m research.post.sweeps.registration
"""
from __future__ import annotations

from research.log import EdgeGateRole, register_hypothesis

FROZEN_GRID = {
    "atr_periods": [5, 8, 10, 14, 20, 27, 34, 50],
    "atr_mults": [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0],
    "zlsma_lens": [20, 32, 50, 80, 120],
    "bias_tfs": "none + the two next-higher TFs per entry TF",
    "directions": ["both", "long", "short"],
    "min_atr": [0.0, 1.0],
    "entry_timeframes": ["M5", "M15", "H1", "H4", "D1"],
    "risk_pct": 0.01,
    "max_drawdown_halt": "DISABLED (absorbing barrier; truncates records)",
}

FROZEN_GATES = {
    "n_trades_min": 100, "profit_factor_min": 1.20,
    "max_dd_max": 0.30, "sharpe_min": 0.0,
}

PREDICTIONS = [
    "P1_some_positive: many configs will show positive in-sample Sharpe. This "
    "is EXPECTED and is NOT evidence — XAUUSD rose ~12x over the window and "
    "any long-biased trend follower inherits that drift.",
    "P2_beats_drift (DECISIVE): the leading config's Sharpe exceeds a "
    "random-entry null at p < 0.05, where the null randomises ONLY the entry "
    "bars and holds direction, exit rule, trade count, sizing and cost model "
    "fixed. This isolates entry timing from drift and from the exit design.",
    "P3_beats_passive (DECISIVE): the leading config's Calmar (CAGR / max "
    "drawdown) exceeds passive long XAUUSD over the identical window. A "
    "trend follower that merely reproduces buy-and-hold risk-adjusted return "
    "has no reason to exist.",
    "P4_dsr: Deflated Sharpe at N = full grid size exceeds 0.95, using the "
    "sweep's own trial Sharpes as the empirical Var(SR) source.",
    "P5_plateau: the leader sits on a plateau — adjacent atr_period/atr_mult "
    "configs remain positive — rather than being an isolated spike.",
]

KILL_CRITERIA = [
    "K1: leader fails the random-entry control (p >= 0.05) -> the apparent "
    "edge is drift plus exit mechanics, not signal. KILL, consistent with the "
    "seq=20 E-Ratio verdict.",
    "K2: leader's Calmar <= passive buy-and-hold Calmar -> no economic reason "
    "to run it. KILL regardless of Sharpe.",
    "K3: DSR at N = grid size <= 0.95 -> the leader is within reach of a "
    "search of this size over noise. Cannot promote.",
    "K4: leader is an isolated spike (neighbours negative) -> overfit to the "
    "grid, not a robust region.",
]

STOPPING_RULE = (
    "This is a single exhaustive pass. The grid is frozen above. If the "
    "leader survives K1-K4 the ONLY next step is out-of-sample walk-forward "
    "under qhf_harness — NOT a finer grid around the leader, which would be "
    "pure overfitting and would require a new registration."
)

NOTE_CONTEXT = (
    "Parent hypothesis zerolag_chandelier (seq=19/20) was KILLED at the "
    "signal-edge stage: 32-bar combined E-Ratio 0.9813, p=0.7720, flat at "
    "16/32/64 bars, with role=HARD_GATE. CLAUDE.md holds that for "
    "momentum/continuation entries a failed E-Ratio is terminal and no exit "
    "design rescues it. This sweep deliberately probes that rule at the "
    "user's request: the chandelier IS a trailing exit, so strategy-level "
    "edge could in principle exist without entry-level edge. A positive "
    "result must therefore clear a HIGHER bar than usual (K1-K4 together), "
    "not a lower one. "
    "SEQUENCING DISCLOSURE: the grid and the survival gates were frozen "
    "before any results were read, but the D1 and H4 slices had been "
    "inspected before this entry was written. M15/M5/H1 were not. This is a "
    "post-hoc exploration of a killed hypothesis, not a pre-registration, "
    "and is logged as such."
)

CORRELATION_NOTES = (
    "Shares the XAUUSD long-bias drift exposure of crest_n_keel (seq=29), "
    "crest_n_keel_momentum (seq=36), flood_tide_h1 (seq=32), "
    "flood_tide_h1_iter2 (seq=34) and regime_align_h1 (seq=38). In the last "
    "three the drift-matched null was decisive. The random-entry control "
    "here plays the same role and is applied from the start."
)


def main() -> None:
    entry = register_hypothesis(
        hypothesis_id="zlch_param_sweep",
        title="Exhaustive parameter + timeframe sweep of zerolag_chandelier (post-kill exit-edge probe)",
        mechanism=(
            "zerolag_chandelier's ENTRY was killed on a flat E-Ratio. The "
            "chandelier direction flip is, however, simultaneously a trailing "
            "EXIT rule, and entry edge and strategy edge are distinct claims. "
            "This sweep evaluates every (atr_period x atr_mult x zlsma_len x "
            "bias_tf x direction x min_atr) combination on five entry "
            "timeframes over 21.6 years, scoring Sharpe, max drawdown, win "
            "rate and profit factor, then subjects the leader to a "
            "drift-matched random-entry null, a passive buy-and-hold "
            "benchmark, and a Deflated Sharpe haircut at N = grid size. "
            "Hypothesised mechanism if positive: the asymmetric trailing exit "
            "(cut on flip, ride otherwise) converts a directionally neutral "
            "entry into positive expectancy by shaping the trade-return "
            "distribution rather than by timing."
        ),
        market="XAUUSD",
        timeframe="M5/M15/H1/H4/D1",
        family="trend-following",
        edge_gate_role=EdgeGateRole.DIAGNOSTIC,
        predictions=PREDICTIONS,
        note=(
            "PARENT=zerolag_chandelier seq=19/20 (KILLED) | "
            "CONTEXT=" + NOTE_CONTEXT + " | "
            "FROZEN_GRID=" + repr(FROZEN_GRID) + " | "
            "FROZEN_GATES=" + repr(FROZEN_GATES) + " | "
            "KILL=" + " ; ".join(KILL_CRITERIA) + " | "
            "STOPPING_RULE=" + STOPPING_RULE + " | "
            "CORRELATION=" + CORRELATION_NOTES + " | "
            "ENGINE=research.post.sweeps.zlch_engine, validated against "
            "qhf.engines.strategies.zlch under btpy_runner to worst "
            "|dSharpe|=0.0015 with 100% trade-set match on 7 configs "
            "(research.post.sweeps.run_parity)."
        ),
    )
    print(f"registered seq={entry.seq} hash={entry.entry_hash[:16]}")
    print(f"id={entry.hypothesis_id} role={entry.edge_gate_role.value}")


if __name__ == "__main__":
    main()
