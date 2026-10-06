"""Register the zerolag_chandelier NESTED walk-forward BEFORE it is run.

Design, fold geometry, gates and kill criteria below are frozen. Changing any
of them after seeing a result requires a NEW registration, not an edit here.

Run once:  python -m research.post.sweeps.zlch_nested_registration
"""
from __future__ import annotations

import argparse

from research.log import EdgeGateRole, register_hypothesis, trial_count, verify

HYPOTHESIS_ID = "zlch_nested_walk_forward"

FROZEN_DESIGN = (
    "For each fold: re-run the FULL seq=39 grid on the TRAINING window ONLY "
    "(3,696 configs per timeframe: 8 atr_periods x 7 atr_mults x 11 bias keys "
    "[none + 2 higher TFs x 5 ZLSMA lengths] x 3 directions x 2 min_atr); "
    "apply the gates; select the highest training Sharpe; evaluate that ONE "
    "config once on the following untouched test window. Fold geometry mirrors "
    "seq=47/49 so zlch and cnk are directly comparable -- H1 train 1460D / "
    "test 365D / step 365D (17 folds), H4 train 1825D / test 365D / step 365D "
    "(16 folds). Gates are seq=39's (PF >= 1.20, max DD <= 0.30, Sharpe > 0) "
    "with the trade floor SCALED to the training window at 100/21.6 per year, "
    "hard minimum 30, because applying the absolute 100 to a 4-5 year window "
    "would be a far harsher gate than the sweep itself used. Direction, bias "
    "timeframe, ZLSMA length and min_atr are NOT fixed in advance: restricting "
    "to 'H4 long-only, bias=none' would re-import seq=40's full-history "
    "conclusion and reintroduce the leak in a subtler form -- the exact error "
    "corrected at seq=64 for seq=36/46. risk_pct 0.01; max_drawdown_halt "
    "DISABLED; Pepperstone cost model; POOL_SAMPLE 50; seed 20260827."
)

PREDICTIONS = [
    "Z1: the nested procedure's mean OOS Sharpe across folds is > 0.",
    "Z2 (DECISIVE): the training-selected config's OOS Sharpe exceeds the "
    "median OOS Sharpe of a random sample of OTHER configs that also cleared "
    "the training gates, in a majority of folds. This is the test of whether "
    "training rank carries any information about the test window. It is the "
    "test that killed crest_n_keel at seq=49 (17/32 folds, p=0.430).",
    "Z3: at least one config clears the training gates in every fold.",
    "Z4 (leakage estimate): nested OOS mean Sharpe is BELOW the seq=40 "
    "full-history leader's OOS mean on the SAME folds. The shortfall is the "
    "value of the lookahead in seq=40's in-sample ranking. seq=49 measured "
    "0.68 (H1) / 0.81 (H4) for crest_n_keel; a similar figure here would mean "
    "seq=40's in-sample Sharpe of 0.833 is mostly hindsight.",
    "Z5: long-only is selected in a majority of folds, and short in none. "
    "seq=40 found short negative at every timeframe and the seq=20 E-Ratio "
    "split agrees (long 1.033 / short 0.927). If honest per-fold selection "
    "instead scatters across directions, the seq=40 direction finding was "
    "itself a full-history artifact.",
    "Z6: selection is unstable -- the config chosen changes across folds and "
    "fewer than half the folds select the seq=40 full-history leader.",
]

KILL_CRITERIA = [
    "ZK1: mean OOS Sharpe across folds <= 0 -> the selection procedure has no "
    "out-of-sample edge. KILL zerolag_chandelier outright; its status moves "
    "from 'untested out-of-sample' to 'refuted'.",
    "ZK2 (DECISIVE): the selected config fails to beat the gate-passing pool "
    "median in a majority of folds (sign-test p >= 0.05) -> the seq=40 ranking "
    "is noise. KILL. Combined with seq=49 this would be the second independent "
    "demonstration that top-of-grid selection carries no out-of-sample "
    "information in this repo, and the finding generalises past zlch.",
    "ZK3: fewer than 60% of folds yield ANY config clearing the training "
    "gates -> not deployable regardless of its average.",
]

STOPPING_RULE = (
    "Single pass over H1 and H4; geometry, gates and grid frozen above. If it "
    "survives ZK1-ZK3 the next step is the seq=63 permutation null on the "
    "concatenated OOS stream -- NOT a finer grid, NOT a different timeframe, "
    "and NOT a re-run with different gates. If it fails ZK2 the correct "
    "response is to stop ranking sweeps by top-of-grid Sharpe across this "
    "repo, which is a methodology change rather than a strategy change."
)

NOTE_CONTEXT = (
    "PARENT: zerolag_chandelier seq=19/20 (KILLED at signal-edge: combined "
    "E-Ratio 0.9813, p=0.772, role=HARD_GATE) -> zlch_param_sweep seq=39 "
    "(registration) / seq=40 (result: 18,480 configs; leader H4 atr_period=8 "
    "atr_mult=2.0 bias=none direction=long, Sharpe_px 0.833, PF 1.495, DD "
    "0.238; K1 PASS random-entry p=0.000; K2 PASS Calmar 0.41 vs B&H 0.28; K4 "
    "PASS 9/9 neighbours positive; K3 FAIL DSR 0.739 at N=18,480 -> cannot "
    "promote). "
    "WHY THIS RUNS NOW: seq=39's frozen stopping rule states that if the "
    "leader survives K1-K4 the ONLY legitimate next step is an out-of-sample "
    "walk-forward, NOT a finer grid. K3 was the sole failure and that step was "
    "never taken, so zlch is the one candidate in the corpus whose honest "
    "status is UNTESTED OUT-OF-SAMPLE rather than refuted (log seq=64). "
    "seq=63/65 then showed the K3 haircut was measuring the wrong thing on a "
    "long-biased rule: DSR benchmarks against zero while the true permutation "
    "null mean is positive (drift capture), the Var(SR) branch used was the "
    "lenient one, and the gate had power 0.061 at these effect sizes. K3 alone "
    "is therefore not a verdict. This registration supplies the test zlch has "
    "never had and that actually killed crest_n_keel. "
    "SEQUENCING DISCLOSURE: nothing from this nested run has been observed. "
    "One H4 fold was timed for feasibility with the selection result "
    "deliberately not printed; that timing informed only the decision to "
    "proceed, not the design. Runner research/post/sweeps/zlch_nested_wf.py "
    "was written before this registration and is frozen with it. "
    "REPRODUCIBILITY DEFECT FOUND AND DISCLOSED BEFORE RUNNING: under pandas "
    "2.1.4 the engine's HTF-bias resample raises 'Values falls before first "
    "bin' for the 7D (W1) rule, so the seq=40 sweep cannot have been produced "
    "by this environment and its weekly bin alignment is not recoverable -- an "
    "origin sweep at 4h resolution across the full week got no closer than "
    "|dSharpe| 0.0048. htf_bias therefore gained an optional `origin` "
    "argument (default None, so every existing caller is unchanged) and this "
    "run pins bins to a fixed absolute Monday, 2004-06-07 UTC, which is also "
    "required for correctness in a walk-forward: without a pinned origin every "
    "fold would slice at a different date and the same config would not mean "
    "the same thing across folds. VERIFIED against the recorded seq=40 CSVs: "
    "H1 reproduces EXACTLY (max |dSharpe| 0.0000000000) on all three bias "
    "families (none, D1, H4), and H4 reproduces exactly on none and D1. Only "
    "H4's W1-bias configs differ (max |dSharpe| 0.084 on spot checks), which "
    "is ~45% of the H4 grid. Those configs remain valid grid members under a "
    "well-defined causal weekly alignment; they are simply not bit-identical "
    "to seq=40. The seq=40 leader is bias=none, so the `fixed` comparison arm "
    "is unaffected, and H1 is unaffected entirely. "
    "EXCLUDED TIMEFRAMES, disclosed: M5, M15 and D1 are not run. M5/M15 are "
    "structurally cost-destroyed (seq=40 median Sharpe -1.402 / -0.602 against "
    "a 0.29 USD/oz round trip) and D1 yields too few trades per fold for a "
    "Sharpe to mean anything. That exclusion rests on cost arithmetic, not on "
    "which config won."
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--commit", action="store_true",
                    help="Actually append. Without it, prints and exits.")
    a = ap.parse_args()
    note = (NOTE_CONTEXT + " | FROZEN_DESIGN=" + FROZEN_DESIGN
            + " | KILL_CRITERIA=" + " ; ".join(KILL_CRITERIA)
            + " | STOPPING_RULE=" + STOPPING_RULE)
    if not a.commit:
        print(note)
        print("\nPREDICTIONS:")
        for p in PREDICTIONS:
            print("  -", p)
        print(f"\n(dry run; trial_count currently {trial_count()})")
        return 0
    e = register_hypothesis(
        HYPOTHESIS_ID,
        title="zerolag_chandelier nested walk-forward (the OOS test seq=39 mandated)",
        mechanism=("Chandelier-exit trend following on a ZLSMA-biased entry. "
                   "Tests whether the SELECTION PROCEDURE generalises, not "
                   "whether one config does."),
        market="XAUUSD", timeframe="H1+H4", family="trend_following",
        edge_gate_role=EdgeGateRole.HARD_GATE,
        predictions=PREDICTIONS,
        note=note,
    )
    print(f"registered seq={e.seq}")
    ok, msg = verify()
    print("chain verify:", ok, msg)
    print("trial_count:", trial_count())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
