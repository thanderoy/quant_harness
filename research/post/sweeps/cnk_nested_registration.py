"""Register the crest_n_keel NESTED walk-forward BEFORE it is run.

Design, fold geometry, gates and kill criteria below are frozen. Changing any
of them after seeing a result requires a NEW registration, not an edit here.
"""
from __future__ import annotations

from research.log import register_hypothesis, EdgeGateRole, trial_count, verify

FROZEN_DESIGN = (
    "For each fold: re-run the FULL seq=44 grid (30,132 configs: both entry "
    "modes, all three directions, every parameter) on the TRAINING window "
    "ONLY; apply the gates; select the highest training Sharpe; evaluate that "
    "one config once on the following untouched test window. Fold geometry "
    "mirrors seq=46 so the two are comparable -- H1 train 1460D / test 365D / "
    "step 365D (17 folds), H4 train 1825D / test 365D / step 365D (16 folds). "
    "Gates: PF >= 1.20, max DD <= 0.30, Sharpe > 0 (identical to seq=44); "
    "trade floor SCALED to the training window at 100/21.6 per year with a "
    "hard minimum of 30, because applying the absolute 100 to a 4-year window "
    "would be a far harsher gate than the sweep itself used. "
    "Mode and direction are NOT fixed in advance: restricting to 'momentum "
    "long-only' would re-import a conclusion drawn from the full history and "
    "reintroduce the leak in a subtler form. max_drawdown_halt disabled "
    "throughout; risk_pct 0.02; Pepperstone cost model; seed 20260820."
)

PREDICTIONS = [
    "N1: the nested procedure's mean OOS Sharpe across folds is > 0.",
    "N2: momentum is the selected mode in a majority of folds at both H1 and H4.",
    "N3: a non-short direction (long or both) is selected in a majority of folds.",
    "N4 (leakage estimate): nested OOS mean Sharpe is BELOW the seq=46 "
    "fixed-leader OOS mean on the same geometry (H1 +0.761, H4 +0.454). The "
    "size of that shortfall is the value of the lookahead seq=46 could not "
    "remove.",
    "N5: selection is unstable -- the config chosen changes across folds, and "
    "fewer than half the folds select the seq=44 full-history leader.",
    "N6 (DECISIVE): the selected config's OOS Sharpe exceeds the median OOS "
    "Sharpe of a random sample of OTHER configs that also cleared the training "
    "gates, in a majority of folds. This is the test of whether training rank "
    "carries any information about the test window.",
]

KILL_CRITERIA = [
    "NK1: mean OOS Sharpe across folds <= 0 -> the selection procedure has no "
    "out-of-sample edge. KILL the line, not just the config.",
    "NK2 (DECISIVE): the selected config fails to beat the gate-passing pool "
    "median in a majority of folds -> the sweep ranking is noise and the whole "
    "exhaustive-sweep-then-pick-the-top methodology is not producing "
    "information. KILL, and the finding generalises well beyond crest_n_keel.",
    "NK3: fewer than 60% of folds yield ANY config clearing the training "
    "gates -> the procedure is not deployable regardless of its average.",
]

STOPPING_RULE = (
    "Single pass; geometry, gates and grid frozen above. If it survives "
    "NK1-NK3 the next step is a cost/slippage stress and a live-forward paper "
    "period on demo -- NOT another grid and NOT a finer search. If it fails "
    "NK2 the correct response is to stop ranking sweeps by top-of-grid Sharpe "
    "across this repo, which is a methodology change, not a strategy change."
)

NOTE_CONTEXT = (
    "PARENT: cnk_param_sweep seq=44 (registration) / seq=45 (result: leader H4 "
    "momentum long, Sharpe_px 0.985, K1 p=0.000, K2 Calmar 0.468 vs B&H 0.277, "
    "K3 DSR 0.839 at N=119,917 -> DO NOT PROMOTE) / seq=46 (harness "
    "walk-forward: H1 pooled OOS Sharpe 0.91 with IS-OOS gap -0.02, H4 0.71 "
    "with gap +0.07, both FAIL the research-tier gate on DSR at 0.0000). "
    "WHY THIS IS A SEPARATE TRIAL: seq=46 could not be clean. qhf_harness's "
    "run_walk_forward applies FIXED parameters to every fold and does not "
    "re-optimise inside the training window, and those parameters came from a "
    "sweep over the full history, which contains every fold it tested. The "
    "selection saw the test data. seq=46 therefore measures TEMPORAL "
    "STABILITY, which it found to be good, and cannot speak to whether the "
    "SELECTION PROCEDURE generalises. This registration tests the procedure. "
    "SEQUENCING DISCLOSURE: nothing from this nested run has been observed. "
    "One H4 fold was timed for feasibility (96s/fold, 4,058 gate-passers) with "
    "the selection result deliberately not printed; that timing informed only "
    "the decision to proceed, not the design. Runner: "
    "research/post/sweeps/cnk_nested_wf.py, written before this registration "
    "and frozen with it."
)


def main() -> int:
    e = register_hypothesis(
        hypothesis_id="cnk_nested_walk_forward",
        title="crest_n_keel nested walk-forward: does the selection procedure generalise?",
        mechanism=(
            "Tests the METHODOLOGY rather than a configuration. If an "
            "exhaustive parameter sweep followed by top-of-grid selection has "
            "real predictive content, then a leader chosen from a training "
            "window alone should outperform on the following unseen window, "
            "and should beat other configs that merely cleared the same gates. "
            "If it does not, the ranking is in-sample noise and every sweep in "
            "this repo has been measuring selection luck."),
        market="XAUUSD",
        timeframe="H1,H4",
        family="crest_n_keel",
        edge_gate_role=EdgeGateRole.DIAGNOSTIC,
        predictions=PREDICTIONS,
        note=(NOTE_CONTEXT + " | FROZEN_DESIGN=" + FROZEN_DESIGN
              + " | KILL_CRITERIA=" + " ".join(KILL_CRITERIA)
              + " | STOPPING_RULE=" + STOPPING_RULE),
    )
    print(f"registered seq={e.seq} hash={e.entry_hash[:16]} role={e.edge_gate_role.value}")
    print("chain:", verify(), "| trial_count:", trial_count())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
