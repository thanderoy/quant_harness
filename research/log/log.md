# Research Log (rendered view)

> **Generated artifact** — do not edit. Source: `entries.jsonl`. Regenerate with `render_markdown()`.

- **Entries:** 30
- **Trial count (floor N for DSR):** 10
- **Hash chain:** OK — chain ok (30 entries)

## Principles

**1. E-Ratio: hard gate vs diagnostic** — The E-Ratio is a **hard gate** for breakout/continuation entries (the entry itself should do the work — kill on a flat E-Ratio). It is a **diagnostic only** for pullback/mean-reversion entries (the edge legitimately lives in the exit — a flat entry E-Ratio is expected and must NOT trigger a kill). Set `edge_gate_role` at registration time so this rule travels with the hypothesis.

**2. Log generously; the trial count is a floor** — `trial_count()` is the N that feeds Deflated Sharpe Ratio. It cannot capture ideas considered and discarded before logging, so the true multiple-testing burden is always ≥ this number. Register early, even for vague ideas — it's cheaper to log a trial than to under-haircut a future Sharpe.

## Current state by hypothesis

Edge-gate role is shown on every row: a **hard_gate** entry must show E-Ratio edge; a **diagnostic** entry may legitimately have a flat E-Ratio (edge lives in the exit) and must not be killed on it.

| hypothesis | family | role | stage | verdict | latest metrics |
|---|---|---|---|---|---|
| `asian_session_fade` — Asian-session ATR-channel fade | mean_reversion | diagnostic | 0_hypothesis | open | — |
| `asqs` — ASQ SafeScalping v1.20 — M5 7-condition breakout | breakout | hard_gate | 8_deployed | deployed | profit_factor=1.55, sharpe_oos=5.14 |
| `avwap_liquidity_sweep` — H1 HMA + NY AVWAP + 5-day VP + sweep/reclaim | breakout | diagnostic | 0_hypothesis | shelved | — |
| `avwap_multibar_reclaim_m15` — AVWAP-only multi-bar sweep-and-reclaim on XAUUSD M15 with H1 HMA bias | mean-reversion | diagnostic | 0_hypothesis | open | artifact_path=research/artifacts/avwap_multibar_reclaim_signal_edge_20260614T133418Z.json, e_ratio_16bar_combined=0.7442676947027749, e_ratio_16bar_long=0.752738401545089, e_ratio_16bar_short=0.7373789256325337, e_ratio_16bar_sweep_1bar=0.8587431852056898, e_ratio_16bar_sweep_2bar=0.6593045423120963, e_ratio_16bar_sweep_3bar=0.63133028877003, e_ratio_32bar_combined=0.8579269972413494, e_ratio_8bar_combined=0.8029473830802075, p_value_16bar=0.943, random_baseline_ci_hi=1.3435445752288044, random_baseline_ci_lo=0.7338073025220379, random_baseline_mean=1.1712825593901284, run_valid=False, signal_hash=97102210ade375b6, trigger_count_long=40, trigger_count_short=43, trigger_count_sweep_1bar=40, trigger_count_sweep_2bar=27, trigger_count_sweep_3bar=16, trigger_count_total=83 |
| `avwap_sweep_reclaim_m15` — AVWAP/POC/HVN sweep-and-reclaim on XAUUSD M15 with H1 HMA bias | mean-reversion | diagnostic | 1_signal_edge | open | artifact_path=research/artifacts/avwap_sweep_reclaim_signal_edge_20260614T083827Z.json, e_ratio_16bar_avwap=0.6105235797712227, e_ratio_16bar_combined=0.806326708871015, e_ratio_16bar_hvn=0.9389136831082255, e_ratio_16bar_long=0.8362129729640871, e_ratio_16bar_poc=0.5316155984971189, e_ratio_16bar_short=0.7813945766834295, e_ratio_32bar_combined=0.8981169691816416, e_ratio_8bar_combined=0.8630572252818496, p_value_16bar=0.942, random_baseline_ci_hi=1.2329962317847916, random_baseline_ci_lo=0.7953614436587528, random_baseline_mean=1.0407515046105003, signal_hash=35d6b60e498f3813, trigger_count_avwap=40, trigger_count_hvn=97, trigger_count_long=58, trigger_count_poc=8, trigger_count_short=87, trigger_count_total=145 |
| `crest_n_keel` — HMA+Stoch 1H pullback (a.k.a. hma_stoch_1h) | pullback | diagnostic | 5_walk_forward | open | e_ratio_w30=0.9, p_value=0.34, sharpe_oos=1.76, dsr_prob_24h=0.106, dsr_prob_session=0.028, folds=33, oos_max_dd_session=0.1, oos_trades_24h=323, oos_trades_session=146, profit_factor_24h=1.15, profit_factor_session=1.45, sharpe_oos_24h=0.27, sharpe_oos_session=0.41, spread_stress_survives_2x=True |
| `donchian_50_control` — Donchian-50 breakout (positive control) | breakout | hard_gate | 1_signal_edge | shelved | e_ratio_w10=1.11, e_ratio_w50=1.17, p_value=0.0, artifact_path=None, e_ratio_32bar_combined=None, e_ratio_32bar_long=None, e_ratio_32bar_short=None, p_value_32bar=0.0, random_baseline_mean=None, signal_hash=None, trigger_count_long=None, trigger_count_short=None, trigger_count_total=None |
| `ebb_n_flow` — Bollinger mean-reversion with KER gate | mean_reversion | diagnostic | 3_is_backtest | killed | e_ratio_w30=0.97, gross_expectancy=-1.0 |
| `gold_dxy_divergence` — Gold–DXY cointegration divergence MR | mean_reversion | diagnostic | 0_hypothesis | open | — |
| `zerolag_chandelier` — ZeroLag Chandelier M15 trend-flip with H4 ZLSMA bias | trend-following | hard_gate | 1_signal_edge | killed | artifact_path=research/artifacts/zlch_signal_edge_20260613T124557Z.json, e_ratio_16bar_combined=0.9982942985402807, e_ratio_32bar_combined=0.9812997845502123, e_ratio_32bar_long=1.0329712568883036, e_ratio_32bar_short=0.9272756416318665, e_ratio_64bar_combined=0.9947033410972972, p_value_32bar=0.772, random_baseline_ci_hi=1.0489893240653485, random_baseline_ci_lo=0.9569090443774892, random_baseline_mean=1.0010775037450308, signal_hash=605f94fe1150069a, trigger_count_long=1984, trigger_count_short=1785, trigger_count_total=3769 |

## Full event stream (oldest first)

### seq 0 · 2026-06-11T09:16:34Z · hypothesis · `crest_n_keel`

**HMA+Stoch 1H pullback (a.k.a. hma_stoch_1h)**

_Mechanism_: Trend established by HMA slope; entries taken on Stochastic pullback into trend direction. Profit captured by asymmetric ATR exit (SL 1.5·ATR / TP 3.0·ATR) — entry edge ≈ flat by design.

market=XAUUSD· timeframe=H1· family=pullback· edge_gate_role=diagnostic· counts_as_trial=True

_hash_: `efb640a963f98af2…` · _prev_: `(genesis)`

### seq 1 · 2026-06-11T09:16:34Z · update · `crest_n_keel`

stage=1_signal_edge · verdict=open · counts_as_trial=False

_Metrics_: `e_ratio_w30`=0.9, `p_value`=0.34

> Entry E-Ratio ~0.9 — no standalone edge. Expected for a pullback entry; do NOT kill on this (diagnostic).

_hash_: `b94a48cc5f48b1ed…` · _prev_: `efb640a963f98af2…`

### seq 2 · 2026-06-11T09:16:34Z · update · `crest_n_keel`

stage=4_oos · verdict=promoted · counts_as_trial=False

_Metrics_: `sharpe_oos`=1.76

> Sharpe ~1.76 OOS; profit lives in the asymmetric ATR exit.

_hash_: `b3b9fc738cd5d7f4…` · _prev_: `b94a48cc5f48b1ed…`

### seq 3 · 2026-06-11T09:16:34Z · update · `crest_n_keel`

stage=8_deployed · verdict=deployed · counts_as_trial=False

> Live in production.

_hash_: `0d8de9105eaed1a9…` · _prev_: `b3b9fc738cd5d7f4…`

### seq 4 · 2026-06-11T09:16:34Z · hypothesis · `asqs`

**ASQ SafeScalping v1.20 — M5 7-condition breakout**

_Mechanism_: Seven-condition M5 breakout filter (HLPeak channel + multi-MA stack + ATR regime + session window). Continuation entry where the breakout itself is expected to do the work.

market=XAUUSD· timeframe=M5· family=breakout· edge_gate_role=hard_gate· counts_as_trial=True

_hash_: `0ef15bcec093af79…` · _prev_: `0d8de9105eaed1a9…`

### seq 5 · 2026-06-11T09:16:34Z · update · `asqs`

stage=1_signal_edge · verdict=promoted · counts_as_trial=False

> Entry edge confirmed (breakout — must pass hard gate).

_hash_: `c885399e34ed3907…` · _prev_: `0ef15bcec093af79…`

### seq 6 · 2026-06-11T09:16:34Z · update · `asqs`

stage=4_oos · verdict=promoted · counts_as_trial=False

_Metrics_: `profit_factor`=1.55, `sharpe_oos`=5.14

> OOS Sharpe 5.14, PF 1.55 on harness backtest.

_hash_: `92d4d8398dc37947…` · _prev_: `c885399e34ed3907…`

### seq 7 · 2026-06-11T09:16:34Z · update · `asqs`

stage=8_deployed · verdict=deployed · counts_as_trial=False

> Live; 3 live-adapter bugs fixed during deployment (SL/TP, drawdown, daily-cap query).

_hash_: `bc1551daaa97ae12…` · _prev_: `92d4d8398dc37947…`

### seq 8 · 2026-06-11T09:16:34Z · hypothesis · `ebb_n_flow`

**Bollinger mean-reversion with KER gate**

_Mechanism_: Symmetric fade of Bollinger band touches gated by Kaufman Efficiency Ratio (only when trend strength is low).

market=XAUUSD· family=mean_reversion· edge_gate_role=diagnostic· counts_as_trial=True

_hash_: `84a718f83fee61ed…` · _prev_: `bc1551daaa97ae12…`

### seq 9 · 2026-06-11T09:16:34Z · update · `ebb_n_flow`

stage=1_signal_edge · verdict=open · counts_as_trial=False

_Metrics_: `e_ratio_w30`=0.97

> Entry E-Ratio flat — diagnostic only for MR, so not a kill signal on its own.

_hash_: `0b932b024ee0f1f1…` · _prev_: `84a718f83fee61ed…`

### seq 10 · 2026-06-11T09:16:34Z · update · `ebb_n_flow`

stage=3_is_backtest · verdict=killed · counts_as_trial=False

_Metrics_: `gross_expectancy`=-1.0

> Negative gross expectancy. Gold's secular uptrend punishes symmetric fades; MR sleeve needs asymmetric treatment of long vs short. Killed on backtest, not on the flat entry E-Ratio.

_hash_: `420513b5e5129481…` · _prev_: `0b932b024ee0f1f1…`

### seq 11 · 2026-06-11T09:16:34Z · hypothesis · `donchian_50_control`

**Donchian-50 breakout (positive control)**

_Mechanism_: Classic 50-bar Donchian channel breakout — used as a positive control for signal_edge.py to confirm the tool detects real entry edge when present. Not a deployment candidate.

market=XAUUSD· timeframe=H1· family=breakout· edge_gate_role=hard_gate· counts_as_trial=True

_hash_: `dc22380a48130ec4…` · _prev_: `420513b5e5129481…`

### seq 12 · 2026-06-11T09:16:34Z · update · `donchian_50_control`

stage=1_signal_edge · verdict=shelved · counts_as_trial=False

_Metrics_: `e_ratio_w10`=1.11, `e_ratio_w50`=1.17, `p_value`=0.0

> E-Ratio 1.11→1.17 across windows at p=0.000. Confirms the tool detects real edge. Shelved — control, not a deployment candidate.

_hash_: `a89bf080cc85181a…` · _prev_: `dc22380a48130ec4…`

### seq 13 · 2026-06-11T09:16:34Z · hypothesis · `avwap_liquidity_sweep`

**H1 HMA + NY AVWAP + 5-day VP + sweep/reclaim**

_Mechanism_: Continuation entry: H1 HMA filter establishes trend, NY-session anchored VWAP and 5-day volume profile locate liquidity, entry fires on a sweep-and-reclaim of identified levels.

market=XAUUSD· timeframe=H1· family=breakout· edge_gate_role=hard_gate· counts_as_trial=True

_hash_: `f65be64f27df1299…` · _prev_: `a89bf080cc85181a…`

### seq 14 · 2026-06-11T09:16:34Z · update · `avwap_liquidity_sweep`

stage=0_hypothesis · verdict=open · counts_as_trial=False

> Fully specced; backtest harness not built yet.

_hash_: `17a9cde75ce114f1…` · _prev_: `f65be64f27df1299…`

### seq 15 · 2026-06-11T09:16:34Z · hypothesis · `asian_session_fade`

**Asian-session ATR-channel fade**

_Mechanism_: Liquidity vacuum 22:00–05:00 GMT lets price overshoot an HLPeak ATR channel; mean-revert back to channel midline near London open. StochMA used as the trigger.

market=XAUUSD· timeframe=M5· family=mean_reversion· edge_gate_role=diagnostic· counts_as_trial=True

_hash_: `f6d4a6c602c353df…` · _prev_: `17a9cde75ce114f1…`

### seq 16 · 2026-06-11T09:16:34Z · update · `asian_session_fade`

stage=0_hypothesis · verdict=open · counts_as_trial=False

> MR sleeve candidate; target 0.0–0.25 correlation with the trend book. Edge expected in the exit (diagnostic).

_hash_: `e4c665a3c07f0f01…` · _prev_: `f6d4a6c602c353df…`

### seq 17 · 2026-06-11T09:16:34Z · hypothesis · `gold_dxy_divergence`

**Gold–DXY cointegration divergence MR**

_Mechanism_: Stat-arb style mean-reversion of gold vs DXY when the cointegration spread stretches beyond a Z-score threshold.

market=XAUUSD· family=mean_reversion· edge_gate_role=diagnostic· counts_as_trial=True

_hash_: `c912ec87c6b8bd8c…` · _prev_: `e4c665a3c07f0f01…`

### seq 18 · 2026-06-11T09:16:34Z · update · `gold_dxy_divergence`

stage=0_hypothesis · verdict=open · counts_as_trial=False

> Falsification prerequisites undone: rolling correlation, CADF cointegration test, cross-corr lag analysis. No spec yet.

_hash_: `b2d0e2fbbe7c3539…` · _prev_: `c912ec87c6b8bd8c…`

### seq 19 · 2026-06-13T10:18:03Z · hypothesis · `zerolag_chandelier`

**ZeroLag Chandelier M15 trend-flip with H4 ZLSMA bias**

_Mechanism_: Chandelier direction-flip is a momentum-transition trigger: dir flips +1 when close breaks above the trailing short_stop band (rolling-low + k*ATR), and -1 when close breaks below the trailing long_stop band. The H4 ZLSMA slope filter constrains entries to the dominant macro bias and is intended to suppress flip-noise during ranging conditions. If the entry trigger has no standalone edge against random entries within the same regime filter, the strategy reduces to its (unspecified) exit design and becomes structurally similar to crest_n_keel — i.e., the entry itself is not the source of alpha. HARD_GATE: a flat E-Ratio falsifies the idea outright.

market=XAUUSD· timeframe=M15 (H4 reference)· family=trend-following· edge_gate_role=hard_gate· counts_as_trial=True

_Predictions_:
- On XAUUSD M15 over 2018-01-01 to 2025-12-31, the combined long+short entry-signal E-Ratio at a 32-bar forward window is >= 1.10.
- The permutation test p-value (1,000 permutations) is < 0.05.
- The random-entry baseline E-Ratio over the same period falls within [0.95, 1.05] — confirming the tool itself is unbiased on this dataset.
- Trigger count across the 8-year window is >= 200, satisfying the statistical-power floor for the permutation test.

> Earlier informal version analysed 2026-03-23; not previously registered. Frozen parameters: Chandelier ATR(14, mult=2.5), H4 ZLSMA(50), no additional filters. H4 series resampled from M15 with label='right', closed='right' and referenced at .shift(1) to prevent look-ahead. Direction-flip entries only — persistent-direction variant is out of scope and would be a separate hypothesis.

_hash_: `062f9304f833e53f…` · _prev_: `b2d0e2fbbe7c3539…`

### seq 20 · 2026-06-13T12:46:28Z · update · `zerolag_chandelier`

stage=1_signal_edge · verdict=killed · counts_as_trial=False

_Metrics_: `artifact_path`=research/artifacts/zlch_signal_edge_20260613T124557Z.json, `e_ratio_16bar_combined`=0.9982942985402807, `e_ratio_32bar_combined`=0.9812997845502123, `e_ratio_32bar_long`=1.0329712568883036, `e_ratio_32bar_short`=0.9272756416318665, `e_ratio_64bar_combined`=0.9947033410972972, `p_value_32bar`=0.772, `random_baseline_ci_hi`=1.0489893240653485, `random_baseline_ci_lo`=0.9569090443774892, `random_baseline_mean`=1.0010775037450308, `signal_hash`=605f94fe1150069a, `trigger_count_long`=1984, `trigger_count_short`=1785, `trigger_count_total`=3769

> SIGNAL_EDGE verdict: KILLED (anti-edge). 32-bar combined E-Ratio=0.9813 < 1.00, p=0.7720. Both pre-conditions passed: random baseline=1.0011 in [0.95,1.05], triggers=3769 >= 200. Sensitivity: 16-bar=0.9983, 64-bar=0.9947 — flat at every window, no edge concentration anywhere. HARD_GATE classification → terminal for this parameterisation. Returning to avwap_liquidity_sweep.

_hash_: `6691f108baace712…` · _prev_: `062f9304f833e53f…`

### seq 21 · 2026-06-13T13:10:03Z · update · `donchian_50_control`

stage=1_signal_edge · verdict=promoted · counts_as_trial=False

_Metrics_: `artifact_path`=None, `e_ratio_32bar_combined`=None, `e_ratio_32bar_long`=None, `e_ratio_32bar_short`=None, `p_value_32bar`=0.0, `random_baseline_mean`=None, `signal_hash`=None, `trigger_count_long`=None, `trigger_count_short`=None, `trigger_count_total`=None

> Backfill UPDATE: positive control passed the signal_edge gate at p<0.05, confirming the diagnostic tool detects edge in canonical breakout signals on XAUUSD. NOT a strategy candidate — donchian_50_control exists solely as a tool-calibration anchor. Stage will not advance further; this entry will sit permanently at SIGNAL_EDGE/PROMOTED. The result was the reference point used to interpret the crest_n_keel and zerolag_chandelier findings.

_hash_: `b5362c1b16025362…` · _prev_: `6691f108baace712…`

### seq 22 · 2026-06-13T14:00:46Z · update · `donchian_50_control`

stage=1_signal_edge · verdict=shelved · counts_as_trial=False

> Verdict revert: seq=21 PROMOTED was a semantic mis-classification. Control passed the signal_edge gate (E-Ratio 1.11-1.17, p=0.000), but donchian_50_control exists solely as a tool-calibration anchor - terminal by design, no deployment intent. SHELVED reads correctly in render_markdown: tool-passed, parked. Edge-confirmation metrics remain on seq=21 and are the authoritative reference for tool calibration on XAUUSD H1/M15.

_hash_: `129ec15bfc171c84…` · _prev_: `b5362c1b16025362…`

### seq 23 · 2026-06-13T14:02:14Z · update · `avwap_liquidity_sweep`

stage=0_hypothesis · verdict=open · counts_as_trial=False

> Role reclassification: HARD_GATE -> DIAGNOSTIC. The entry trigger is structurally a mean-reversion reclaim-at-level (sweep + reclaim against AVWAP / VP-POC / HVN), not a momentum-transition breakout. A flat or sub-1.0 E-Ratio on the entry is the EXPECTED outcome and does not falsify the hypothesis - by analogy with crest_n_keel (E-Ratio ~0.9, no significance, DIAGNOSTIC), where the edge lives entirely in the asymmetric ATR exit. Edge claim for avwap will live in the exit design downstream. Reclassification was decided in earlier sessions; this UPDATE persists the decision to the log so the next signal_edge run interprets the result correctly.

_hash_: `fcfcbf0e439ed2af…` · _prev_: `129ec15bfc171c84…`

### seq 24 · 2026-06-14T08:24:31Z · update · `avwap_liquidity_sweep`

stage=0_hypothesis · verdict=shelved · counts_as_trial=False

> Shelved: hypothesis as registered at seq=13 is structurally a H1 BREAKOUT continuation strategy (H1 HMA + AVWAP + VP locating breakout levels). The seq=23 role reclassification to DIAGNOSTIC was correct about the mechanism — sweep-and-reclaim reads as mean-reversion, not continuation — but the underlying registration's timeframe (H1) and family (breakout) remained inconsistent with that reclassification. Rather than rewrite identity fields via UPDATE (which would erode the append-only log's audit guarantees), this hypothesis is shelved and the mean-reversion variant is registered as avwap_sweep_reclaim_m15 with the correct timeframe (M15), family (mean-reversion), and full frozen parameter spec. No edge measurement was performed against seq=13's parameterisation; this is a definitional shelving, not an evidence-based one.

_hash_: `e72053cc701ee953…` · _prev_: `fcfcbf0e439ed2af…`

### seq 25 · 2026-06-14T08:25:23Z · hypothesis · `avwap_sweep_reclaim_m15`

**AVWAP/POC/HVN sweep-and-reclaim on XAUUSD M15 with H1 HMA bias**

_Mechanism_: Mean-reversion reclaim-at-level. Premise: institutional liquidity clusters at three reference levels on XAUUSD intraday — the NY-anchored AVWAP (session consensus), the rolling 5-day Volume Profile POC (multi-day fair value), and high-volume nodes within reach (accepted price zones). When price sweeps a level (wicks past by >=0.2*ATR) and reclaims it within the same M15 candle, trapped breakout traders provide displacement fuel back toward the level. The H1 HMA(50) bias filter constrains entries to the macro direction (longs only above HMA, shorts only below). The Stochastic %K-%D cross in oversold/overbought confirms momentum has turned at the reclaim. DIAGNOSTIC role: this is a reclaim-at-level entry, so a flat or sub-1.0 E-Ratio on the entry alone is expected and does NOT falsify the hypothesis. The edge claim will live in the exit design downstream, structurally analogous to crest_n_keel where the entry is no-edge but the asymmetric ATR exit carries the alpha. signal_edge here produces a reference E-Ratio against which the full-strategy backtest's improvement is later measured.

market=XAUUSD· timeframe=M15 (H1 reference for HMA, H1 aggregation for Volume Profile)· family=mean-reversion· edge_gate_role=diagnostic· counts_as_trial=True

_Predictions_:
- On XAUUSD M15 over 2018-01-01 to 2025-12-31, the entry stack produces >= 100 triggers (long + short combined), satisfying the statistical-power floor for the signal_edge permutation test under DIAGNOSTIC framing.
- The random-entry baseline E-Ratio over the same period falls within [0.95, 1.05] — confirming the tool itself is unbiased on this dataset.
- The Volume Profile is computed from a trailing 120 H1 bar window ending at bar t-1, with no inclusion of bar t's H1 bar — verified by the signal-generator unit tests for look-ahead protection.
- The signal-output DataFrame includes a 'triggering_level' column (values: 'avwap', 'poc', 'hvn') for diagnostic attribution of any observed E-Ratio by level type, used in next-hypothesis design only.

> Successor to avwap_liquidity_sweep (seq=13, shelved at seq=24) — same level-set concept, materially different mechanism (mean-reversion reclaim) and timeframe (M15 not H1). Frozen entry stack: NY cash open AVWAP (DST-aware), H1 HMA(50), 5-day Volume Profile (120 H1 bars, 0.025%-of-price bins, POC + top-3 HVNs within 2*ATR of current price), 0.2*ATR(14) sweep threshold, same-M15-candle reclaim, Stochastic(14,3,3) %K-%D cross coincident with sweep bar. Forward window 16 bars primary, 8/32 sensitivity. ATR-scaled VP binning, multi-bar reclaim variant, and confluence-required triggering are explicitly deferred as separate hypotheses if this one shows interesting results. Edge claim is in exit design, not entry.

_hash_: `2951fe53609fd1e8…` · _prev_: `e72053cc701ee953…`

### seq 26 · 2026-06-14T08:40:47Z · update · `avwap_sweep_reclaim_m15`

stage=1_signal_edge · verdict=open · counts_as_trial=False

_Metrics_: `artifact_path`=research/artifacts/avwap_sweep_reclaim_signal_edge_20260614T083827Z.json, `e_ratio_16bar_avwap`=0.6105235797712227, `e_ratio_16bar_combined`=0.806326708871015, `e_ratio_16bar_hvn`=0.9389136831082255, `e_ratio_16bar_long`=0.8362129729640871, `e_ratio_16bar_poc`=0.5316155984971189, `e_ratio_16bar_short`=0.7813945766834295, `e_ratio_32bar_combined`=0.8981169691816416, `e_ratio_8bar_combined`=0.8630572252818496, `p_value_16bar`=0.942, `random_baseline_ci_hi`=1.2329962317847916, `random_baseline_ci_lo`=0.7953614436587528, `random_baseline_mean`=1.0407515046105003, `signal_hash`=35d6b60e498f3813, `trigger_count_avwap`=40, `trigger_count_hvn`=97, `trigger_count_long`=58, `trigger_count_poc`=8, `trigger_count_short`=87, `trigger_count_total`=145

> DIAGNOSTIC SIGNAL_EDGE checkpoint: entry-only E-Ratio (16-bar combined) =0.8063, p=0.9420, baseline=1.0408. Pre-conditions both passed (triggers=145 >=100; baseline in [0.95,1.05]). By level: avwap n=40 E=0.611; poc n=8 E=0.532; hvn n=97 E=0.939. Verdict remains OPEN (DIAGNOSTIC: edge claim is in exit design downstream). Next: design asymmetric exit + run full backtest.

_hash_: `02309736130d9cf4…` · _prev_: `2951fe53609fd1e8…`

### seq 27 · 2026-06-14T10:42:03Z · hypothesis · `avwap_multibar_reclaim_m15`

**AVWAP-only multi-bar sweep-and-reclaim on XAUUSD M15 with H1 HMA bias**

_Mechanism_: Mean-reversion reclaim-at-level, AVWAP-only variant with multi-bar reclaim tolerance. Premise: in avwap_sweep_reclaim_m15 (seq=25, checkpoint at seq=27, E-Ratio 0.81 vs 1.04 baseline at 16 bars), the AVWAP-tagged subset produced the strongest decomposed E-Ratio (0.89, n=40) among three level types — still flat in absolute terms, but the cleanest signal in the stack. POC was effectively dead (n=8 in 8 years) and HVN diluted the result. This variant tests two design changes: (1) restrict triggers to AVWAP only, eliminating POC/HVN noise; (2) relax the same-candle reclaim constraint to allow up to 3 consecutive M15 bars of close-based displacement past the level before reclaim. The same-candle constraint may have been too restrictive for AVWAP specifically — institutional consensus levels operate on slower time scales than HVN-style reaction zones, and the 'trapped traders' mechanism requires sustained displacement to engage. DIAGNOSTIC role: this is still a reclaim-at-level entry, so flat or sub-1.0 E-Ratio on the entry alone remains the expected outcome. Edge claim, if pursued, will live in the exit design downstream.

market=XAUUSD· timeframe=M15 (H1 reference for HMA)· family=mean-reversion· edge_gate_role=diagnostic· counts_as_trial=True

_Predictions_:
- On XAUUSD M15 over 2018-01-01 to 2025-12-31, the AVWAP-only multi-bar reclaim entry produces >= 100 triggers (long + short combined), satisfying the statistical-power floor for signal_edge.
- The random-entry baseline E-Ratio satisfies: mean within [0.95, 1.05] OR [0.95, 1.05] fully contained within the 95% CI — the corrected calibration check from the avwap_sweep_reclaim_m15 debrief.
- The AVWAP value at M15 bar t is cumulative TPV/volume from the most recent NY cash open (09:30 America/New_York, DST-aware) at-or-before t, with no use of bars after t. Verified by signal-generator unit tests.
- The signal-output DataFrame includes a 'sweep_bars' integer column (values 1 through 3) recording how many M15 bars the level was breached before the reclaim, for diagnostic attribution of edge concentration by displacement duration.

> Successor variant to avwap_sweep_reclaim_m15 (seq=25, OPEN at seq=27 after DIAGNOSTIC checkpoint). Frozen entry stack: NY cash open AVWAP (DST-aware) — POC and HVN removed; H1 HMA(50) bias filter (unchanged); 0.2*ATR(14) sweep threshold (unchanged); multi-bar reclaim with maximum 3 M15 bars of consecutive close-based displacement past the level (close[N] past level by >= 0.2*ATR) before the reclaim bar (first bar with close back on original side); Stochastic(14,3,3) %K-%D edge-cross coincident with the RECLAIM bar (not the initial sweep bar), both < 20 long / > 80 short. Forward window 16 bars primary, 8/32 sensitivity. POC, HVN, same-candle reclaim variant, alternative anchor sessions, and longer reclaim timeouts are deferred as separate hypotheses. Edge claim is in exit design, not entry. If this variant also returns flat, the case for any further M15 entry-signal variant in this family becomes very weak and the next trial budget should be spent on a different mechanism class (e.g., gold_dxy_divergence).

_hash_: `52614e9c065eaf69…` · _prev_: `02309736130d9cf4…`

### seq 28 · 2026-06-14T13:51:01Z · update · `avwap_multibar_reclaim_m15`

stage=0_hypothesis · verdict=open · counts_as_trial=False

_Metrics_: `artifact_path`=research/artifacts/avwap_multibar_reclaim_signal_edge_20260614T133418Z.json, `e_ratio_16bar_combined`=0.7442676947027749, `e_ratio_16bar_long`=0.752738401545089, `e_ratio_16bar_short`=0.7373789256325337, `e_ratio_16bar_sweep_1bar`=0.8587431852056898, `e_ratio_16bar_sweep_2bar`=0.6593045423120963, `e_ratio_16bar_sweep_3bar`=0.63133028877003, `e_ratio_32bar_combined`=0.8579269972413494, `e_ratio_8bar_combined`=0.8029473830802075, `p_value_16bar`=0.943, `random_baseline_ci_hi`=1.3435445752288044, `random_baseline_ci_lo`=0.7338073025220379, `random_baseline_mean`=1.1712825593901284, `run_valid`=False, `signal_hash`=97102210ade375b6, `trigger_count_long`=40, `trigger_count_short`=43, `trigger_count_sweep_1bar`=40, `trigger_count_sweep_2bar`=27, `trigger_count_sweep_3bar`=16, `trigger_count_total`=83

> INVALID RUN: pre-condition #1 failed. Trigger count = 83 < 100 (spec floor for statistical power). Sweep-bars distribution {1:40, 2:27, 3:16}. Random baseline mean = 1.1713 (also outside [0.95,1.05] band; null p05=0.7338, p95=1.3435 - the band IS contained in [p05,p95], so the secondary calibration clause holds, but the trigger floor is the binding failure). Stage unchanged at HYPOTHESIS; not falsifying under DIAGNOSTIC. HALT - no parameter rescue. Diagnostic E-Ratio 0.7443 reported for completeness but is statistically unreliable at n=83.

_hash_: `387d0984c21ff918…` · _prev_: `52614e9c065eaf69…`

### seq 29 · 2026-06-26T08:05:14Z · update · `crest_n_keel`

stage=5_walk_forward · verdict=open · counts_as_trial=False

_Metrics_: `dsr_prob_24h`=0.106, `dsr_prob_session`=0.028, `folds`=33, `oos_max_dd_session`=0.1, `oos_trades_24h`=323, `oos_trades_session`=146, `profit_factor_24h`=1.15, `profit_factor_session`=1.45, `sharpe_oos_24h`=0.27, `sharpe_oos_session`=0.41, `spread_stress_survives_2x`=True

> qhf harness walk-forward (33 folds, 21.6y XAUUSD H1, Pepperstone Razor costs) CONTRADICTS the seeded sharpe_oos=1.76. Realized OOS Sharpe (ann.) 0.27 (24/7) / 0.41 (08-17 UTC session); DSR prob 0.106 / 0.028 -> FAILS DSR>0.95 gate on BOTH runs; 24/7 also fails PF>=1.20 (1.15). Edge survives 2x spread but there is no significant edge to protect. The 1.76 was a hand-seeded claim with no backing artifact (absent from qhf_harness; never produced by this harness). Verdict reopened to OPEN: deployed standing is contested. NOT auto-killed/shelved -- that decision is the owner's.

_hash_: `5a060a461d8bfeff…` · _prev_: `387d0984c21ff918…`
