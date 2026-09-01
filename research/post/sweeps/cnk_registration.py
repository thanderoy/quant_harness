"""Registration: cnk_param_sweep — exhaustive two-mode sweep of crest_n_keel.

    python -m research.post.sweeps.cnk_registration
"""
from __future__ import annotations

from research.log import EdgeGateRole, register_hypothesis

FROZEN_GRID = {
    "shared": {"hma_period": [13, 21, 34, 55, 89, 144],
               "atr_period": [7, 14, 21],
               "min_atr": [0.0, 1.0, 2.0],
               "direction": ["both", "long", "short"]},
    "pullback_only": {"stoch_k": [9, 14, 21],
                      "zones_oversold_overbought": [[20, 80], [25, 75], [30, 70]],
                      "sl_atr_mult": [1.0, 1.5, 2.0, 3.0],
                      "tp_atr_mult": [1.5, 2.0, 3.0, 4.0, 5.0]},
    "momentum_only": {"trail_atr_mult": [1.5, 2.0, 2.5, 3.0, 4.0, 5.0]},
    "entry_timeframes": ["M5", "M15", "H1", "H4", "D1"],
    "fixed": {"stoch_d": 3, "stoch_smooth_k": 3, "risk_pct": 0.02,
              "max_drawdown_halt": "DISABLED (absorbing barrier)"},
    "n_configs": {"pullback_per_tf": 29160, "momentum_per_tf": 972,
                  "total": 150660},
}

FROZEN_GATES = {"n_trades_min": 100, "profit_factor_min": 1.20,
                "max_dd_max": 0.30, "sharpe_min": 0.0}

PREDICTIONS = [
    "P1_mode (the question seq=35/36 raised but never answered at grid scale): if "
    "the momentum entry is genuinely better than the pullback entry, the MOMENTUM "
    "surface must dominate the PULLBACK surface on median Sharpe and percent-"
    "positive at every timeframe. If it dominates only at the single config found "
    "by TradingView search, seq=36's advantage was a selection artifact.",
    "P2_long_bias: within MOMENTUM, long-only beats short-only at every timeframe "
    "(gold's secular uptrend), which is the assumption seq=35 froze in without "
    "testing.",
    "P3_beats_drift (DECISIVE): the leading config's Sharpe exceeds a random-entry "
    "null drawn from its own eligible pool, with the REALIZED trade count matched "
    "and the null annualised on the strategy's own periods-per-year, holding "
    "direction, exit rules, sizing and costs fixed.",
    "P4_beats_passive (DECISIVE): the leading config's Calmar exceeds passive long "
    "XAUUSD over the identical window.",
    "P5_dsr: Deflated Sharpe at N = full grid size exceeds 0.95.",
    "P6_plateau: the leader's one-step grid neighbours remain positive.",
    "P7_pullback_generalises: the deployed pullback region (hma 55, sl 1.5, tp 3.0, "
    "zones 20/80) sits near zero across its neighbourhood, confirming seq=29's "
    "walk-forward result is a property of the entry rather than of one config.",
]

KILL_CRITERIA = [
    "K1: leader fails the matched random-entry control (p >= 0.05) -> the HMA/"
    "stochastic entry adds nothing over random timing in the same regime. KILL.",
    "K2: leader's Calmar <= passive buy-and-hold Calmar -> no economic reason to "
    "run it. KILL regardless of Sharpe.",
    "K3: DSR at N = grid size <= 0.95 -> cannot promote.",
    "K4: leader is an isolated spike -> overfit to the grid.",
]

STOPPING_RULE = (
    "Single exhaustive pass; grid frozen above. If the leader survives K1-K4 the "
    "only next step is OOS walk-forward under qhf_harness on the surviving region. "
    "A finer grid around the leader is overfitting and requires a NEW registration."
)

NOTE_CONTEXT = (
    "PARENTS: crest_n_keel seq=0 (PULLBACK, deployed, live magic 1100001) whose "
    "walk-forward at seq=29 returned OOS Sharpe 0.27-0.41 / DSR 0.03-0.11 and "
    "REFUTED a seeded 1.76 that never had a backing artifact - verdict left OPEN "
    "and deployment contested; and crest_n_keel_momentum seq=35 (MOMENTUM, "
    "TradingView Config A) which at seq=36 passed 4/5 gates on walk-forward "
    "(OOS Sharpe 1.20, gap -0.34, PF 1.26, 3829 trades) but FAILED DSR (0.061 at "
    "N=20) and was marked do-not-promote. Both parents are still OPEN, so this "
    "sweep is a scoping exercise over a contested live strategy, not a post-kill "
    "reopening. "
    "EDGE_GATE_ROLE is recorded DIAGNOSTIC for the entry as a whole because the "
    "pullback arm is a pullback entry (house rule: E-Ratio is diagnostic-only "
    "there, never a veto). The MOMENTUM arm is properly HARD_GATE - it is a "
    "continuation entry. No E-Ratio gate is applied in this sweep either way; it "
    "runs at stage 3 and the operative test is the K1 control. The split is "
    "recorded here so the correct rule carries forward per arm. "
    "SEQUENCING DISCLOSURE: the grid, gates and kill criteria were frozen before "
    "the sweep ran. The D1 timeframe was executed first as a smoke test and its "
    "results WERE inspected before this entry was written - D1 leader (momentum, "
    "long, hma 13, trail 2.0, 271 trades, Sharpe 0.795, K1 p=0.000 against a null "
    "of 0.580) and the D1 mode/direction medians are therefore OBSERVED, and P1/P2 "
    "are partially observed on D1 only. M5, M15, H1 and H4 were entirely unseen. "
    "Gates are reused verbatim from the zlch_param_sweep registration (seq=39) so "
    "they cannot be tuned to this data. This is a post-hoc exploration, not a "
    "pre-registration, and is logged as such."
)

CORRELATION_NOTES = (
    "HIGH correlation with the trend/breakout book by construction: the momentum "
    "arm is an HMA-slope trend follower and shares gold's long drift with "
    "flood_tide, regime_align and the long side of zerolag_chandelier. That shared "
    "drift is exactly what the matched random-entry control is designed to price "
    "out - a leader that merely rides the drift will not clear K1. The pullback "
    "arm is structurally short-biased and historically faded the gold bull, which "
    "is the recorded explanation for its weak standalone entry (E-Ratio ~0.9)."
)


def main() -> None:
    e = register_hypothesis(
        hypothesis_id="cnk_param_sweep",
        title="Exhaustive parameter + timeframe sweep of crest_n_keel, both entry modes",
        mechanism=(
            "crest_n_keel exists in two structurally different forms that have "
            "never been compared on equal footing. PULLBACK (deployed): HMA slope "
            "plus price side plus a stochastic cross out of the oversold or "
            "overbought zone, exited by a fixed ATR bracket. MOMENTUM (candidate): "
            "HMA slope FLIP, long-only, exited by an ATR chandelier trail. seq=36 "
            "showed the momentum config beating the pullback config, but that was "
            "ONE configuration selected by TradingView search against ONE baseline. "
            "This sweep runs both modes over the same shared parameter dimensions "
            "and five entry timeframes, so the mode comparison is made across the "
            "whole surface instead of at two hand-picked points. Hypothesised "
            "mechanism if positive: on a secular-bull instrument a long trend-"
            "continuation entry with a ratcheting exit captures drift, while a "
            "symmetric pullback entry with a fixed bracket repeatedly fades it."
        ),
        market="XAUUSD",
        timeframe="M5/M15/H1/H4/D1",
        family="crest_n_keel",
        edge_gate_role=EdgeGateRole.DIAGNOSTIC,
        predictions=PREDICTIONS,
        note=(
            "CONTEXT=" + NOTE_CONTEXT
            + " | FROZEN_GRID=" + repr(FROZEN_GRID)
            + " | FROZEN_GATES=" + repr(FROZEN_GATES)
            + " | KILL=" + " ; ".join(KILL_CRITERIA)
            + " | STOPPING_RULE=" + STOPPING_RULE
            + " | CORRELATION=" + CORRELATION_NOTES
            + " | ENGINE=research.post.sweeps.cnk_engine, validated against "
              "qhf.engines.strategies.hma_stoch.HMAStoch1H and "
              "qhf.engines.strategies.cnk_momentum.CrestNKeelMomentum under "
              "btpy_runner: 100% entry-set match on 11 configs across both modes "
              "and 4 timeframes, worst |dSharpe|=0.0031. Parity covers the default "
              "slice only - the swept stochastic zones and direction toggle are a "
              "constant substitution and an entry mask that the harness classes "
              "cannot arbitrate."
        ),
    )
    print(f"registered seq={e.seq} hash={e.entry_hash[:16]} role={e.edge_gate_role.value}")


if __name__ == "__main__":
    main()
