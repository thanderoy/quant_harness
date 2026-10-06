"""
Pre-registration: regime_align_h1

Three-parameter regime alignment as a standalone entry.
XAUUSD H1, long-only.

Entry fires on the *transition* into a bar where all three regime parameters
from ``research.pre.regime`` are simultaneously satisfied:

    trend_quality  ER(20)                >= 0.30   (directional path, not chop)
    vol_regime     ATR(14) / ATR(100)    >= 1.10   (vol expanding)
    trend_location (close - SMA200)/ATR14 >= 0.0   (above the anchor)

This module CONSTRUCTS the pre-registration payload and calls
register_hypothesis(). It does not execute any research.

Execution flow:
    1. python -m research.pre.regime_align_h1  -> writes JSONL entry, returns seq/hash
    2. python -m research.pre.scripts.run_regime_align_edge  -> E-Ratio gate
    3. If passed: btpy_runner walk-forward     -> OOS Sharpe series
    4. research.post.dsr on Sharpe series      -> DSR verdict

WHY HARD_GATE: the alignment is a momentum/continuation condition — it asserts
price is moving directionally, with expanding vol, on the bull side of its
anchor. That is precisely the entry category for which house rules make the
E-Ratio terminal. It is NOT a pullback entry, so a ~1.0 E-Ratio cannot be
excused as "the edge lives in the exit".

THE NULL IS THE WHOLE TEST (flood_tide lesson, seq=31/33): gold has a strong
secular uptrend, so ANY long-only signal measured against an unconditional null
inherits that drift and scores > 1.0 for free. The decisive test therefore
draws the permutation null from **bias-eligible bars only** (trend_location >=
0), so the directional filter's drift is baked into the null instead of
inflating the entry. The unconditional null is reported alongside as a
diagnostic to make the size of that inflation visible.
"""
from __future__ import annotations

from research.log import EdgeGateRole, register_hypothesis


# ---------------------------------------------------------------------------
# Frozen parameters — DO NOT MODIFY POST-REGISTRATION
# Any change requires a new register_hypothesis call and trial_count increment.
# ---------------------------------------------------------------------------
FROZEN_PARAMS: dict[str, float | int | str] = {
    "er_len": 20,
    "er_threshold": 0.30,          # p65 of XAUUSD H1 2004-2025
    "atr_fast": 14,
    "atr_slow": 100,
    "vol_threshold": 1.10,         # p76
    "sma_len": 200,
    "bias_threshold": 0.0,         # long-only: at or above the anchor
    "entry_event": "transition_into_alignment",
    "direction": "long_only",
}

# Frozen test specification — P1 / kill K1.
FROZEN_TEST: dict[str, float | int | str] = {
    "horizons": "20, 50, 100",
    "e_ratio_threshold": 1.15,     # CLAUDE.md HARD_GATE bar for momentum entries
    "p_value_threshold": 0.05,
    "n_permutations": 1000,
    "atr_period": 14,
    "random_seed": 20260726,
    "decisive_null": "bias_eligible (trend_location >= 0)",
}

PREDICTIONS = [
    "P1_entry_edge: E-Ratio > 1.15 AND p < 0.05 at ALL of H in {20, 50, 100}, "
    "measured against the bias-eligible permutation null (N=1000). This is the "
    "hard gate.",
    "P2_null_inflation: the unconditional-null E-Ratio will exceed the "
    "bias-eligible-null E-Ratio, quantifying how much of any apparent edge is "
    "gold's secular drift rather than the regime alignment.",
    "P3_episode_persistence: alignment episodes have median length >= 2 bars "
    "(measured: 2, mean 4.3, n=1628 over 124,688 bars) — recorded so a later "
    "persistence/hysteresis re-parameterisation is visibly a NEW trial.",
]

KILL_CRITERIA = [
    "K1: E-Ratio <= 1.15 or p >= 0.05 at ANY horizon under the bias-eligible "
    "null -> SHELVE. Momentum/continuation entry; house rules make this "
    "terminal. No exit design rescues it.",
    "K2: E-Ratio > 1.15 under unconditional null but <= 1.15 under the "
    "bias-eligible null -> SHELVE, and record explicitly that the apparent "
    "edge was gold drift, not regime alignment.",
    "K3: Walk-forward OOS DSR <= 0.95 -> KILL.",
]

STOPPING_RULE = (
    "Iteration 1: this pre-registration exactly. No parameter changes. "
    "A persistence/hysteresis variant (addressing the 2-bar median episode) is "
    "a materially different re-parameterisation and requires a NEW "
    "register_hypothesis call incrementing trial_count — it is not an UPDATE. "
    "After Iteration 2: SHELVED. No third iteration."
)

CORRELATION_NOTES = (
    "vs flood_tide_h1 / _iter2 (both SHELVED, seq=32/34): shares the ER regime "
    "filter and H1 long-only XAU framing. flood_tide's decisive failure was the "
    "regime-filtered null — the same null design is applied here from the "
    "start, so this is a genuinely harder test than flood_tide iteration 1 was. "
    "High prior of correlated failure; registered anyway because the entry "
    "trigger differs (regime alignment itself vs Donchian breakout). "
    "vs crest_n_keel / _momentum (seq=29/36): both H1 long-biased XAU; timing "
    "correlation expected. Occupies the same 'H1 trend continuation' portfolio "
    "slot — not a diversification add."
)


def main() -> None:
    entry = register_hypothesis(
        hypothesis_id="regime_align_h1",
        title="Three-parameter regime alignment (ER + vol expansion + anchor bias) as a standalone H1 entry",
        mechanism=(
            "Kaufman ER(20) >= 0.30 asserts price is travelling a directional "
            "path rather than churning; ATR(14)/ATR(100) >= 1.10 asserts vol is "
            "expanding, i.e. a move has room to develop; (close - SMA200)/ATR14 "
            ">= 0 restricts to the bull side of the H1 anchor. Entry on the "
            "transition into simultaneous satisfaction of all three. "
            "ADX is deliberately excluded — documented unreliable on XAU; ER is "
            "its bounded replacement. Hypothesised mechanism: the conjunction "
            "identifies the onset of directional expansion, which should show "
            "forward MFE/MAE asymmetry before any exit logic exists."
        ),
        market="XAUUSD",
        timeframe="H1",
        family="momentum_continuation",
        edge_gate_role=EdgeGateRole.HARD_GATE,
        predictions=PREDICTIONS,
        note=(
            "FROZEN_PARAMS=" + repr(FROZEN_PARAMS) + " | "
            "FROZEN_TEST=" + repr(FROZEN_TEST) + " | "
            "KILL=" + " ; ".join(KILL_CRITERIA) + " | "
            "STOPPING_RULE=" + STOPPING_RULE + " | "
            "CORRELATION=" + CORRELATION_NOTES
        ),
    )
    print(f"registered seq={entry.seq} hash={entry.entry_hash[:16]}...")
    print(f"hypothesis_id={entry.hypothesis_id} role={entry.edge_gate_role.value}")


if __name__ == "__main__":
    main()
