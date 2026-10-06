"""Register the ASQS parameter sweep BEFORE it is run. Grid frozen."""
from __future__ import annotations

from research.log import register_hypothesis, EdgeGateRole, trial_count, verify
from research.post.sweeps.run_asqs_sweep import (
    EMA_PAIRS, BREAKOUT_LOOKBACKS, TREND_STRENGTHS, BREAKOUT_BUFFERS, RSI_BANDS,
    SL_POINTS, TP_POINTS, SESSIONS, DIRECTIONS, RSI_PERIOD, ATR_PERIOD,
    PARTIAL_MODE, FIXED, TIMEFRAMES, _units)

PER_TF = (len(_units()) * len(TREND_STRENGTHS) * len(BREAKOUT_BUFFERS)
          * len(RSI_BANDS) * len(SESSIONS) * len(DIRECTIONS)
          * len(SL_POINTS) * len(TP_POINTS))

FROZEN_GRID = (
    f"{PER_TF:,} configs x {len(TIMEFRAMES)} timeframes (M5, M15, H1) = "
    f"{PER_TF * len(TIMEFRAMES):,}. ema_pairs={EMA_PAIRS}; "
    f"breakout_lookback={BREAKOUT_LOOKBACKS}; trend_strength={TREND_STRENGTHS}; "
    f"breakout_buffer={BREAKOUT_BUFFERS}; rsi_bands={RSI_BANDS}; "
    f"sl_points={SL_POINTS}; tp_points={TP_POINTS}; sessions={SESSIONS}; "
    f"directions={DIRECTIONS}. FIXED: rsi_period={RSI_PERIOD}, "
    f"atr_period={ATR_PERIOD}, partial_mode={PARTIAL_MODE}, {FIXED}. "
    "H4/D1 excluded: ASQS sizes stops in POINTS (300 points = $3.00), which is "
    "meaningless against a daily bar. Bars load tz='server_eet' (true UTC)."
)

FROZEN_GATES = {"n_trades_min": 100, "profit_factor_min": 1.20,
                "max_dd_max": 0.30, "sharpe_min": 0.0}

PREDICTIONS = [
    "A1 (the reason this sweep exists): ASQS is session-filtered and every "
    "recorded result for it, seq=30 included, filtered the WRONG HOURS because "
    "the loader labels broker server time as UTC. Re-run on true UTC, the "
    "original 08:00-17:00 window will NOT be the best session in the grid, and "
    "the difference between the correct and incorrect window is the size of the "
    "error in the logged record.",
    "A2: the short side underperforms the long side at every timeframe, as it "
    "has in all three previous sweeps on this instrument.",
    "A3: median Sharpe is negative across the grid at M5 and improves "
    "monotonically with timeframe, because a roughly fixed cost per round trip "
    "is charged against a gross edge that shrinks with horizon.",
    "A4: no configuration clears DSR > 0.95 at N = grid size.",
    "A5 (methodology, carried from seq=49): the top-of-grid configuration will "
    "NOT be shown to be promotable, and this sweep is registered as a SURFACE "
    "CHARACTERISATION, not a search for a deployable config.",
]

KILL_CRITERIA = [
    "AK1: the leading config fails the matched random-entry control (p >= 0.05) "
    "-> the 7-condition entry adds nothing over random timing. KILL.",
    "AK2: leading config's Calmar <= passive buy-and-hold Calmar -> no economic "
    "reason to run it. KILL.",
    "AK3: DSR at N = grid size <= 0.95 -> cannot promote.",
    "AK4: median Sharpe across the whole grid is negative at every timeframe "
    "-> the strategy family has no viable region and the live demo deployment "
    "has no support at any parameterisation.",
]

STOPPING_RULE = (
    "Single exhaustive pass; grid frozen above. Per seq=49 the top-of-grid "
    "config is NOT promotable on this evidence and no walk-forward of a "
    "grid-selected leader will be treated as validation. The only outcomes "
    "this sweep can produce are: a surface characterisation, a corrected "
    "estimate of the seq=30 timezone error, and a decision about the live "
    "demo deployment. A finer grid requires a NEW registration."
)

NOTE_CONTEXT = (
    "PARENT: asqs seq=? (ASQ SafeScalping v1.20, M5 7-condition breakout, LIVE "
    "ON DEMO) whose seeded 5.14 Sharpe / 1.55 profit factor was REFUTED by the "
    "harness at seq=30 (OOS Sharpe ~-1, net-losing). This is the first "
    "exhaustive sweep of it. "
    "TWO DEFECTS FOUND DURING THE ENGINE PORT, both of which change what every "
    "previously recorded ASQS number means: "
    "(1) TIMEZONE -- research/post/sweeps/data.py labels broker server time "
    "(MetaQuotes EET/EEST) as UTC. Calibrated empirically: exactly +3h for "
    "74,184 bars and +2h for 50,703 bars. ASQS filters 08:00-17:00 'UTC', so "
    "it has really been trading ~05:00-14:00 / 06:00-15:00 UTC. "
    "(2) PARTIAL CLOSE IS INERT -- qhf btpy_runner sets exclusive_orders=True, "
    "so the second of ASQS's two partial-close orders CANCELS the first. The "
    "TP1 leg never exists and the only surviving effect is that size is halved. "
    "Verified directly against harness trades: 349 trades, all unique entry "
    "timestamps, all at the remainder size, normal durations. The strategy's "
    "own docstring calls this a 'two-leg approximation -- see BUG-2 fix'; the "
    "fix does not work under this runner. The main grid reproduces the harness "
    "behaviour so it stays comparable with the logged record. "
    "ENGINE PARITY: research/post/sweeps/asqs_engine.py vs btpy_runner on 10 "
    "configs across M5/M15/H1 -- 100.0% entry-set match on all ten, worst "
    "|dSharpe| 0.0721. That residual is not a disagreement: per-trade return "
    "std matches to 7 significant figures (0.00223227 vs 0.00223239) and the "
    "annualisation factor to 4 (18.739 vs 18.735); the engines differ by "
    "5e-06 per trade in the mean. Sharpe is simply unstable when the mean "
    "return is 0.04 of a standard deviation. Reaching parity required fixing "
    "three semantic errors in my port: initial SL/TP anchor to the SIGNAL BAR "
    "CLOSE while breakeven/trailing anchor to the FILL price (two different "
    "anchors in one strategy); use_session=False disables the weekend and "
    "Friday-cutoff checks too, because they live inside _pass_session(); and "
    "the partial-close behaviour above. "
    "SEQUENCING: no sweep output has been observed. The grid was sized from "
    "per-config TIMING only (2.68s on full M5 history)."
)


def main() -> int:
    e = register_hypothesis(
        hypothesis_id="asqs_param_sweep",
        title="Exhaustive parameter + timeframe sweep of ASQ SafeScalping v1.20",
        mechanism=(
            "7-condition breakout scalper: EMA trend direction, minimum EMA "
            "separation in ATR units, price above/below both EMAs, N-bar "
            "breakout with an ATR buffer, RSI band, bar-over-bar momentum, and "
            "an optional MTF agreement. Fixed point-based SL/TP with breakeven, "
            "trailing and a nominal partial close. The sweep asks whether ANY "
            "parameterisation of this family has a viable region on XAUUSD, "
            "and how much of the recorded seq=30 refutation is attributable to "
            "a mis-specified session window."),
        market="XAUUSD", timeframe="M5,M15,H1", family="asqs",
        edge_gate_role=EdgeGateRole.HARD_GATE,
        predictions=PREDICTIONS,
        note=(NOTE_CONTEXT + " | FROZEN_GRID=" + FROZEN_GRID
              + " | FROZEN_GATES=" + str(FROZEN_GATES)
              + " | KILL_CRITERIA=" + " ".join(KILL_CRITERIA)
              + " | STOPPING_RULE=" + STOPPING_RULE),
    )
    print(f"registered seq={e.seq} hash={e.entry_hash[:16]} role={e.edge_gate_role.value}")
    print("chain:", verify(), "| trial_count:", trial_count())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
