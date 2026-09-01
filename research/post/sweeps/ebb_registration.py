"""Registration: ebb_n_flow_sweep — post-kill exhaustive sweep of ebb_n_flow.

    python -m research.post.sweeps.ebb_registration
"""
from __future__ import annotations

from research.log import EdgeGateRole, register_hypothesis

FROZEN_GRID = {
    "bb_n": [10, 14, 20, 30, 50],
    "bb_k": [1.5, 2.0, 2.5, 3.0],
    "er_max": [0.20, 0.30, 0.40, 1.00],      # 1.00 disables the KER regime gate
    "sl_atr_mult": [0.5, 1.0, 1.5, 2.0, 3.0],
    "time_stop_bars": [4, 8, 16, 32],
    "direction": ["both", "long", "short"],
    "session": ["rth (08-17 UTC, Fri cutoff 14)", "all"],
    "entry_timeframes": ["M5", "M15", "H1", "H4", "D1"],
    "fixed": {"er_n": 10, "atr_n": 14, "atr_floor": 1.0,
              "atr_spike_mult": 2.5, "min_r": 0.5, "risk_pct": 0.01},
    "note": "D1 sweeps session=all only: D1 bars are stamped hour 0, so the "
            "08-17 UTC filter would block every entry.",
}

FROZEN_GATES = {"n_trades_min": 100, "profit_factor_min": 1.20,
                "max_dd_max": 0.30, "sharpe_min": 0.0}

PREDICTIONS = [
    "P1_asymmetry (the recorded diagnosis, tested directly): the seq=10 kill note "
    "states 'Gold's secular uptrend punishes symmetric fades; MR sleeve needs "
    "asymmetric treatment of long vs short.' If true, median Sharpe must order "
    "long-only > both > short-only at every timeframe, since fading a dip (long) "
    "aligns with the secular uptrend and fading a rally (short) opposes it.",
    "P2_beats_drift (DECISIVE): the leading config's Sharpe exceeds a random-entry "
    "null drawn from the REGIME-GATED pool (bars passing the KER, session and "
    "ATR-spike filters but not the band-touch test), holding direction, exit rules, "
    "trade count, sizing and costs fixed. This isolates the Bollinger signal from "
    "the regime filter and from gold's drift.",
    "P3_beats_passive (DECISIVE): the leading config's Calmar exceeds passive long "
    "XAUUSD over the identical window.",
    "P4_dsr: Deflated Sharpe at N = full grid size exceeds 0.95.",
    "P5_plateau: the leader's adjacent bb_n / bb_k neighbours remain positive.",
]

KILL_CRITERIA = [
    "K1: leader fails the regime-gated random-entry control (p >= 0.05) -> the "
    "Bollinger touch adds nothing over the KER gate alone. KILL.",
    "K2: leader's Calmar <= passive buy-and-hold Calmar -> no economic reason to "
    "run it. KILL regardless of Sharpe.",
    "K3: DSR at N = grid size <= 0.95 -> cannot promote.",
    "K4: leader is an isolated spike -> overfit to the grid.",
]

STOPPING_RULE = (
    "Single exhaustive pass; grid frozen above. If the leader survives K1-K4 the "
    "only next step is OOS walk-forward under qhf_harness. A finer grid around the "
    "leader is overfitting and requires a NEW registration."
)

NOTE_CONTEXT = (
    "Parent ebb_n_flow (seq=8/9/10) was KILLED at stage 3_is_backtest on negative "
    "gross expectancy (-1.0). Its edge_gate_role is DIAGNOSTIC, so the flat entry "
    "E-Ratio (0.97 at w=30) was explicitly NOT the kill - house rules hold that a "
    "mean-reversion entry is carried by its exit, so a ~1.0 E-Ratio is expected. "
    "That makes this a materially better-founded reopening than the "
    "zerolag_chandelier sweep, where the parent failed a HARD_GATE. "
    "SEQUENCING DISCLOSURE: the grid and gates were frozen before any results were "
    "read. The D1 and H4 direction medians had been inspected before this entry was "
    "written, and both already order long > both > short, so P1 is partially "
    "observed; M5, M15 and H1 were unseen. Gates are reused verbatim from the "
    "zlch_param_sweep registration (seq=39) so they cannot be tuned to this data. "
    "This is a post-hoc exploration, not a pre-registration, and is logged as such."
)

CORRELATION_NOTES = (
    "Deliberately LOW correlation with the trend/breakout book (crest_n_keel, "
    "flood_tide, regime_align, zerolag_chandelier): this is the mean-reversion "
    "sleeve and fades what they follow. That diversification value is the reason "
    "to reopen it. Shares only the XAUUSD long-drift exposure on its long side, "
    "which the regime-gated random-entry control is designed to price out."
)


def main() -> None:
    e = register_hypothesis(
        hypothesis_id="ebb_n_flow_sweep",
        title="Exhaustive parameter + timeframe sweep of ebb_n_flow (post-kill asymmetry probe)",
        mechanism=(
            "Fade a Bollinger band excursion back to the midline, gated to "
            "balanced regimes by the Kaufman Efficiency Ratio; TP at the midline, "
            "SL at sl_atr_mult x max(ATR, floor), plus a hard time stop. The "
            "hypothesis was killed symmetric. Its own kill note names the "
            "suspected defect - symmetry on a secular-bull instrument - so this "
            "sweep promotes direction to a first-class grid dimension and tests "
            "that stated diagnosis across every other parameter and five entry "
            "timeframes. Hypothesised mechanism if positive: fading dips is a "
            "long-biased carry on an uptrending asset and survives, while fading "
            "rallies fights the drift and cannot."
        ),
        market="XAUUSD",
        timeframe="M5/M15/H1/H4/D1",
        family="mean_reversion",
        edge_gate_role=EdgeGateRole.DIAGNOSTIC,
        predictions=PREDICTIONS,
        note=(
            "PARENT=ebb_n_flow seq=8/9/10 (KILLED) | CONTEXT=" + NOTE_CONTEXT
            + " | FROZEN_GRID=" + repr(FROZEN_GRID)
            + " | FROZEN_GATES=" + repr(FROZEN_GATES)
            + " | KILL=" + " ; ".join(KILL_CRITERIA)
            + " | STOPPING_RULE=" + STOPPING_RULE
            + " | CORRELATION=" + CORRELATION_NOTES
            + " | ENGINE=research.post.sweeps.ebb_engine, validated against "
              "qhf.engines.strategies.ebb_n_flow under btpy_runner: 100% "
              "trade-set match on 6 configs / 3 timeframes, worst |dSharpe|=0.0172 "
              "(residual is the harness rounding trades-per-year to an integer)."
        ),
    )
    print(f"registered seq={e.seq} hash={e.entry_hash[:16]} role={e.edge_gate_role.value}")


if __name__ == "__main__":
    main()
