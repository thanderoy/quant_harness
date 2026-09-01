"""Pre-registration: flood_tide_h1_iter2 — Iteration 2 of flood_tide_h1 (seq=31).

SINGLE parameter change from the parent: entry_len 55 -> 20. Everything else
(exit, stop, H4-EMA + Efficiency-Ratio regime filter, cost model, kill criteria)
is carried forward verbatim from seq=31.

Registered as a FRESH trial (new HYPOTHESIS event, incrementing trial_count())
so the multiple-testing tax is paid honestly. Run:

    research/.venv/bin/python -m research.pre.flood_tide_h1_iter2            # register
    research/.venv/bin/python -m research.pre.scripts.run_flood_tide_edge \
        --entry-len 20 --hypothesis-id flood_tide_h1_iter2 --seq <seq>      # P1 gate

Honesty note (also embedded in the log): the parent's frozen stopping rule
contemplated an Iteration 2 for a *DSR* failure (entry edge clears, full system
fails OOS), not a *P1* failure. seq=31 failed at P1 (K2 SHELVE). This iteration
is therefore a deliberate, logged departure from the pre-registered plan — which
is exactly why it is booked as a separate trial rather than a silent re-run.
"""
from __future__ import annotations

from research.log import EdgeGateRole, register_hypothesis, render_markdown, trial_count, verify
from research.pre.flood_tide_h1 import (
    EdgeGate,
    FalsifiablePrediction,
    FloodTideH1Payload,
    _log_predictions,
    _preregistration_note,
    build_payload,
)


CODENAME = "flood_tide_h1_iter2"
NEW_ENTRY_LEN = 20

ITER2_MECHANISM = (
    "ITERATION 2 of flood_tide_h1 (parent seq=31, SHELVED at P1). In Iteration 1 "
    "the Donchian-55 breakout's forward MFE/MAE asymmetry cleared the raw 1.10 "
    "threshold but was statistically insignificant against a regime-filtered null "
    "at every horizon (p = 0.10 / 0.46 / 0.71 at H = 20 / 50 / 100), and the "
    "observed E-Ratio fell BELOW the regime null mean at H=100. The entry's excess "
    "over the null was concentrated at the SHORT horizon and decayed to sub-null "
    "with holding time. Ex-ante reading: the institutional flow shift a breakout "
    "marks is fast and short-lived on XAUUSD H1; a 55-bar channel confirms it late "
    "and buys exhaustion. SINGLE change: entry_len 55 -> 20, entering the same flow "
    "shift earlier, before it is spent. The falsifiable claim is that a faster "
    "breakout produces a regime-null-significant forward asymmetry where the slow "
    "one did not. All other params, gates, kill criteria and cost model are "
    "unchanged from seq=31."
)

ITER2_STOPPING = (
    "Terminal iteration. This is the one and only re-parameterisation of the "
    "flood_tide breakout mechanism. A PASS proceeds to btpy_runner walk-forward "
    "(P2 / DSR). A fail (K1 or K2) shelves the flood_tide breakout family — no "
    "Iteration 3, no further entry_len search. NB: this Iteration 2 is a deliberate "
    "departure from the parent's frozen stopping rule, which reserved Iteration 2 "
    "for a DSR failure; seq=31 failed earlier, at P1. Booked as a separate trial "
    "so trial_count() reflects the extra look at the data."
)

ITER2_CORRELATION = (
    "Near-identical to parent flood_tide_h1 (seq=31): same regime filter, exit, "
    "stop, instrument and timeframe — only entry_len differs (20 vs 55). "
    "Signal-timing correlation with the parent is very high; this is NOT a "
    "diversifying idea, it is a faster re-test of the same mechanism. It counts as "
    "a full separate trial precisely because it is a fresh pass over the same data."
)


def build_iter2_payload() -> FloodTideH1Payload:
    base = build_payload()

    frozen = {**base.frozen_params, "entry_len": NEW_ENTRY_LEN}

    # Only P1 (the entry-edge prediction) changes — it now points at the faster
    # channel and the iter2 driver invocation. P2/P3 carry forward unchanged.
    p1 = base.predictions[0].model_copy(update={
        "statement": (
            "Faster (20-bar) breakout entry has positive edge above a "
            "regime-filtered random baseline across short/medium/long horizons."
        ),
        "test": (
            "research.pre.scripts.run_flood_tide_edge "
            "--entry-len 20 --hypothesis-id flood_tide_h1_iter2"
        ),
    })
    predictions = [p1, *base.predictions[1:]]

    # Entry gate component renamed to the new channel length; role unchanged.
    entry_gate = base.edge_gates[0].model_copy(update={
        "component": "entry_donchian_20_breakout",
        "rationale": (
            "Faster breakout / continuation entry (Iteration 2). E-Ratio <= 1.0 "
            "is terminal per house rules; a flat-vs-null E-Ratio here shelves the "
            "breakout family — no exit design rescues a non-edge entry."
        ),
    })
    edge_gates = [entry_gate, *base.edge_gates[1:]]

    return base.model_copy(update={
        "codename": CODENAME,
        "frozen_params": frozen,
        "mechanism": ITER2_MECHANISM,
        "predictions": predictions,
        "edge_gates": edge_gates,
        "stopping_rule": ITER2_STOPPING,
        "correlation_notes": ITER2_CORRELATION,
        "reproducibility_artifact_path": None,
    })


def main() -> None:
    payload = build_iter2_payload()

    entry = register_hypothesis(
        payload.codename,
        title=(
            "flood_tide_h1_iter2 — Donchian-20 (faster) H1 breakout, H4-EMA + "
            "Efficiency-Ratio regime gate (XAUUSD, long-only). Iteration 2 of seq=31."
        ),
        mechanism=payload.mechanism,
        market=payload.instrument,
        timeframe=payload.execution_timeframe,
        family=payload.strategy_family,
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
    print(f"  research/.venv/bin/python -m research.pre.scripts.run_flood_tide_edge "
          f"--entry-len 20 --hypothesis-id {CODENAME} --seq {entry.seq}")


if __name__ == "__main__":
    main()
