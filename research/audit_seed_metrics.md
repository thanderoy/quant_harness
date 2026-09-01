# Seed-Metric Provenance Audit

**Objective:** categorised inventory of every performance-metric claim in the
project's docs, with each claim's provenance resolved.
**Method:** documentation audit — **no harness runs performed today**. This is the
scoping pass; the `SEEDED_UNVERIFIED` / `AMBIGUOUS` pile is the queue to schedule
through the harness in subsequent sessions.
**Date:** 2026-07-02.

> **Update 2026-07-03 — harness queue item 1 executed.** Ran the asqs qhf
> walk-forward (`examples/export_asqs_returns.py` → OOS returns saved under
> `data/asqs/`, canonical DSR via `data/asqs/recompute_dsr.py`) and logged it as
> **seq=30** (`5_walk_forward`, verdict `open`). Result: the seeded
> `sharpe_oos=5.14 / PF=1.55` (rows 18–19) is **refuted, not merely unverified** —
> measured OOS Sharpe **−1.06** (24/7) / **−1.04** (session), PF **0.91 / 0.90**,
> OOS max DD **67% / 72%**, DSR **0.000** both. New harness-verified rows 44–48
> below; headline 1 and the tally are updated accordingly. asqs remains **live on
> demo** — the deploy/kill decision is deferred to the owner.

## Categories

- **HARNESS_VERIFIED** — reproducible from a saved scorecard/artifact, a log
  entry produced by a tool/harness (event ≠ hypothesis), or a documented
  reproducible invocation. Carries an artifact hash or seq-N pointer.
- **SEEDED_UNVERIFIED** — hand-entered, no backing artifact. Queue for harness.
- **ASSUMPTION** — a modelling choice / parameter freeze, not a measured claim.
- **CROSS_REFERENCED** — echoes another claim elsewhere; inherits its status.
- **AMBIGUOUS** — provenance unclear or run self-invalidated; needs a decision.

## Provenance boundary (dating tells the story)

- **seq 0–18 — all timestamped `2026-06-11T09:16:34Z`.** This is the one-shot
  `seed_log.py` backfill: identical timestamps, no artifacts, no `signal_hash`.
  Every performance number in this block is hand-entered. This is the
  pre-discipline pile and where the falsified `1.76` lives.
- **seq 19–30 — `2026-06-13` onward, discipline-active.** Real tool runs:
  `artifact_path` + `signal_hash` on signal-edge entries, saved OOS-returns +
  `recompute_dsr.py` paths on the walk-forward entries (crest_n_keel seq=29,
  asqs seq=30). These are the verified anchors.

## ⚠️ Headline findings

1. **ASQS `sharpe_oos=5.14` / `PF=1.55` — REFUTED by harness seq=30 (2026-07-03).**
   Originally flagged as SEEDED_UNVERIFIED (seq=6) and live on demo, this was the
   top harness-queue exposure. The walk-forward has now been run (33 folds, ~21y
   M5, Razor costs) and it **contradicts the seed by sign**: OOS Sharpe −1.06/−1.04,
   PF 0.91/0.90, DSR 0.000 — a net-losing system, not a 5.14-Sharpe one. This was
   a **larger exposure than the 1.76**, and it resolved the same way the 1.76 did:
   the seeded number had no basis in the harness. Rows 18–19 kept as
   SEEDED_UNVERIFIED with a REFUTED note (lineage preserved, mirroring the 1.76);
   measured values in new rows 44–48. The seq=5 "entry edge confirmed (hard gate)"
   claim (row 20) remains assertion-only — asqs is still the one strategy promoted
   through a HARD_GATE with **no measured E-Ratio** — and the strategy-level
   refutation makes it moot regardless: there is no strategy edge to attribute to
   the entry. **ASQS is still live on demo; the deploy/kill decision is the owner's.**
2. **The `1.76` is confirmed falsified, not merely unverified** — harness seq=29
   contradicts it directly (OOS Sharpe 0.27 / 0.41). Left as SEEDED_UNVERIFIED
   below with a FALSIFIED note so its lineage stays visible.
3. **Seed E-Ratio window labels are mislabelled** vs `calibration_results.md`:
   the log's `e_ratio_w30` values (crest 0.90, ebb 0.97) are actually the **w10**
   figures in the calibration table. Low-stakes, but it means the seeded numbers
   were transcribed loosely — reinforcing "repetition ≠ evidence".
4. **`VALIDATION.md` "OOS MDD ~15.6%" is unbacked** and sits beside harness
   seq=29 `oos_max_dd_session=0.10`. It anchors the locked 15% drawdown guard, so
   it deserves a real artifact.

---

## Inventory

### crest_n_keel (hma_stoch_1h)

| # | claim source | metric | value | provenance | validation seq | notes |
|---|---|---|---|---|---|---|
| 1 | seed_log.py / seq=1 | e_ratio_w30 | 0.90 | SEEDED_UNVERIFIED | — | Window mislabel: 0.90 is w10 in calibration_results.md; w30 there = 0.79. No artifact. |
| 2 | seed_log.py / seq=1 | p_value | 0.34 | SEEDED_UNVERIFIED | — | Not reproduced anywhere; calibration_results.md reports p 0.82/0.98/0.95. Origin of 0.34 unknown. |
| 3 | seed_log.py / seq=2 | sharpe_oos | 1.76 | SEEDED_UNVERIFIED | — | **FALSIFIED by seq=29** (0.27/0.41). The original "1.76 pattern"; no backing artifact, absent from qhf_harness. |
| 4 | entries seq=29 | sharpe_oos_24h | 0.27 | HARNESS_VERIFIED | seq=29 | qhf walk-forward, 33 folds, 21.6y H1, Razor costs. OOS returns saved `data/crest_n_keel/*_24h.csv`. Reproduce not executed this audit. |
| 5 | entries seq=29 | sharpe_oos_session | 0.41 | HARNESS_VERIFIED | seq=29 | Session CSV; same run. |
| 6 | entries seq=29 | dsr_prob_24h | 0.106 | HARNESS_VERIFIED | seq=29 | Recomputable from saved OOS returns via `data/crest_n_keel/recompute_dsr.py` → canonical `post/dsr`. |
| 7 | entries seq=29 | dsr_prob_session | 0.028 | HARNESS_VERIFIED | seq=29 | As above. Both fail DSR>0.95. |
| 8 | entries seq=29 | profit_factor_24h | 1.15 | HARNESS_VERIFIED | seq=29 | Fails PF≥1.20 gate. |
| 9 | entries seq=29 | profit_factor_session | 1.45 | HARNESS_VERIFIED | seq=29 | |
| 10 | entries seq=29 | oos_trades_24h / session | 323 / 146 | HARNESS_VERIFIED | seq=29 | Trade counts from harness run. |
| 11 | entries seq=29 | oos_max_dd_session | 0.10 | HARNESS_VERIFIED | seq=29 | Contrast VALIDATION.md's 15.6% (row 34). |
| 12 | entries seq=29 | spread_stress_survives_2x | true | HARNESS_VERIFIED | seq=29 | "Survives 2× spread but no edge to protect." |
| 13 | entries seq=29 | folds / span | 33 / 21.6y | ASSUMPTION | N/A | Walk-forward configuration, not a measured outcome. |
| 14 | calibration_results.md | E-Ratio 10/30/70 | 0.90 / 0.79 / 0.82 | HARNESS_VERIFIED | test_signal_edge Test 3 | Documented reproduce (`pytest -k "calibration or weak or control"`, seed=42, windows[10,30,70], 1000 perms). Test pins **bounds** (best<1.15, min-p>0.05), not exact decimals. Not run today. |
| 15 | calibration_results.md | p-value 10/30/70 | 0.82 / 0.98 / 0.95 | HARNESS_VERIFIED | test_signal_edge Test 3 | As row 14. |
| 16 | calibration_results.md | N (L/S), baseline ER | 166 (65/101); 0.88/0.91/0.87 | HARNESS_VERIFIED | test_signal_edge Test 3 | As row 14. |
| 17 | calibration_results.md Test 3 | "validated Sharpe ≈1.76" (premise) | 1.76 | CROSS_REFERENCED | seq=2 → falsified seq=29 | Doc itself already marks the premise falsified. |

### asqs (ASQ SafeScalping v1.20) — highest-risk block

| # | claim source | metric | value | provenance | validation seq | notes |
|---|---|---|---|---|---|---|
| 18 | seed_log.py / seq=6 | sharpe_oos | 5.14 | SEEDED_UNVERIFIED | — | ⚠️ **REFUTED by seq=30** (measured OOS Sharpe −1.06/−1.04; rows 44–45). Hand-seeded, implausibly high; was live on demo with no backing artifact. Resolved like the 1.76 — no basis in the harness. Kept here for lineage. |
| 19 | seed_log.py / seq=6 | profit_factor | 1.55 | SEEDED_UNVERIFIED | — | **REFUTED by seq=30** (measured PF 0.91/0.90 < 1 — net-losing; row 46). Same unbacked run as 5.14. |
| 20 | seed_log.py / seq=5 | "entry edge confirmed (hard gate)" | qualitative | SEEDED_UNVERIFIED | — | Asserts asqs passed a HARD_GATE, but no E-Ratio value or artifact logged — the only strategy promoted through the gate with **no measured signal-edge**. Moot after seq=30: no strategy edge exists to attribute to the entry. |
| 21 | log.md line 22 / memory | echo of 5.14 & 1.55 | — | CROSS_REFERENCED | seq=6 → seq=30 | Rendered view + memory summary repeat the seed. Repetition ≠ evidence. Now inherits the seq=30 REFUTED status. |

#### asqs walk-forward (seq=30, 2026-07-03) — harness-verified refutation

| # | claim source | metric | value | provenance | validation seq | notes |
|---|---|---|---|---|---|---|
| 44 | entries seq=30 | sharpe_oos_24h | −1.06 | HARNESS_VERIFIED | seq=30 | qhf walk-forward, 33 folds, ~21y M5, Razor costs. OOS returns saved `data/asqs/asqs_oos_returns_24h.csv`. Directly refutes seed 5.14 (row 18). |
| 45 | entries seq=30 | sharpe_oos_session | −1.04 | HARNESS_VERIFIED | seq=30 | Session (08–17 UTC) CSV; same run. |
| 46 | entries seq=30 | profit_factor_24h / session | 0.91 / 0.90 | HARNESS_VERIFIED | seq=30 | Both < 1 → gross losses exceed gross wins over 11k+ OOS trades. Refutes seed PF 1.55 (row 19). |
| 47 | entries seq=30 | dsr_prob_24h / session | 0.000 / 0.000 | HARNESS_VERIFIED | seq=30 | Canonical `post/dsr` on saved returns via `data/asqs/recompute_dsr.py`. Raw OOS Sharpe negative → PSR-vs-zero 0 before any haircut. |
| 48 | entries seq=30 | oos_max_dd_24h / session; oos_trades | 67% / 72%; 11763 / 11048 | HARNESS_VERIFIED | seq=30 | Catastrophic drawdown vs the 8% dd-guard anchor (row 33). Trade counts from harness run. |

### ebb_n_flow

| # | claim source | metric | value | provenance | validation seq | notes |
|---|---|---|---|---|---|---|
| 22 | seed_log.py / seq=9 | e_ratio_w30 | 0.97 | SEEDED_UNVERIFIED | — | Window mislabel: 0.97 is w10 in calibration; w30 there = 0.99. No artifact. |
| 23 | seed_log.py / seq=10 | gross_expectancy | -1.0 | SEEDED_UNVERIFIED | — | Suspiciously round sentinel; IS-backtest kill. No artifact. |
| 24 | calibration_results.md Test 4 | E-Ratio / p / baseline / N | 0.97/0.99/1.04; 0.74/0.76/0.72; 0.99/1.00/1.06; 4243 | HARNESS_VERIFIED | test_ebb_n_flow_weak_edge | Documented pytest reproduce; bounds-pinned, not run today. |
| 25 | calibration_results.md Test 4 | "PF 0.76, SQN −2.36" | 0.76 / −2.36 | SEEDED_UNVERIFIED | — | Full-backtest narrative figures; no artifact/seq. Distinct from the E-Ratio run. |

### donchian_50_control (positive control)

| # | claim source | metric | value | provenance | validation seq | notes |
|---|---|---|---|---|---|---|
| 26 | seed_log.py / seq=12 | e_ratio_w10 / e_ratio_w50 / p | 1.11 / 1.17 / 0.0 | HARNESS_VERIFIED | test_signal_edge Test 3 (control) | Reproduced by test (control best>1.15, significant). Note "w50" is a spurious label — settings use windows[10,30,70]; 1.17 is w70. |
| 27 | calibration_results.md | E-Ratio / p / baseline / N | 1.11/1.12/1.17; 0.00×3; 0.98/1.03/1.07; 3806 | HARNESS_VERIFIED | test_signal_edge Test 3 | As row 26. Authoritative tool-calibration anchor. |
| 28 | entries seq=21 | backfill metrics | null | AMBIGUOUS | seq=21/22 | Backfill UPDATE carries only `p_value_32bar=0.0`; all other fields null, then reverted PROMOTED→SHELVED at seq=22. Provenance note only, no reusable metric. |

### Artifact-backed signal-edge runs (discipline-active)

| # | claim source | metric | value | provenance | validation seq | notes |
|---|---|---|---|---|---|---|
| 29 | entries seq=20 | zerolag_chandelier E-Ratios (32bar comb 0.9813, p 0.772, baseline 1.001, triggers 3769) | — | HARNESS_VERIFIED | seq=20 | Saved artifact `pre/artifacts/zlch_...json`, `signal_hash=605f94fe1150069a`. Pre-conditions passed; KILLED (anti-edge). Cleanest verified provenance. |
| 30 | entries seq=26 | avwap_sweep_reclaim_m15 E-Ratios (16bar comb 0.8063, p 0.942, baseline 1.041, triggers 145) | — | HARNESS_VERIFIED | seq=26 | Artifact `avwap_sweep_..json`, `signal_hash=35d6b60e498f3813`. Valid diagnostic checkpoint. |
| 31 | entries seq=28 | avwap_multibar_reclaim_m15 E-Ratios (16bar comb 0.7443, p 0.943, baseline 1.171, triggers 83) | — | AMBIGUOUS | seq=28 | Artifact + `signal_hash=97102210ade375b6` exist, **but `run_valid=false`**: triggers 83<100 floor; metrics statistically unreliable. Not a clean result. |

### VALIDATION.md (crest_n_keel demo doc)

| # | claim source | metric | value | provenance | validation seq | notes |
|---|---|---|---|---|---|---|
| 32 | VALIDATION.md | "OOS MDD ~15.6%" | 15.6% | SEEDED_UNVERIFIED | — | Anchors the locked 15% dd-guard. Not in any log entry; seq=29 session MDD=0.10. May be the 24/7 config but no saved artifact. |
| 33 | VALIDATION.md | "ASQS backtested MDD is 5.5%" | 5.5% | SEEDED_UNVERIFIED | — | Anchors ASQS's 8% dd-guard. **Contradicted by seq=30** (OOS max DD 67%/72%, row 48) — the 8% guard is set ~10× below realised walk-forward drawdown. No artifact behind the 5.5%. |
| 34 | VALIDATION.md | risk 0.5%, dd-guard 15%, session 08–17 UTC, spread 50pt, magic 1100001, Fri cutoff | config | ASSUMPTION | N/A | Locked deployment choices, not measured claims. |
| 35 | VALIDATION.md Tier 2 | PF≥1.2, win-floor 35%, MDD≤23%, dur ±50% | targets | ASSUMPTION | N/A | Acceptance thresholds. The "≤23% = 1.5×OOS MDD" derivation inherits the unverified 15.6% (row 32). |

### CLAUDE.md (project context)

| # | claim source | metric | value | provenance | validation seq | notes |
|---|---|---|---|---|---|---|
| 36 | CLAUDE.md | crest "E-Ratio ~0.9" | 0.9 | CROSS_REFERENCED | seq=1 / calibration (row 14) | Echo. |
| 37 | CLAUDE.md | crest "OOS Sharpe 0.27–0.41" | 0.27–0.41 | CROSS_REFERENCED | seq=29 (rows 4–5) | Echo of verified source. |
| 38 | CLAUDE.md | crest "DSR 0.03–0.11" | 0.03–0.11 | CROSS_REFERENCED | seq=29 (rows 6–7) | Echo; log exact = 0.028 / 0.106 (rounded). |
| 39 | CLAUDE.md | "Sharpe ~1.76 … unsourced seed, never produced by harness" | 1.76 | CROSS_REFERENCED | seq=2 → seq=29 | Already correctly documented as falsified. Good. |
| 40 | CLAUDE.md | E-Ratio gate ">1.15, p<0.05" | threshold | ASSUMPTION | N/A | Gate parameter. |
| 41 | CLAUDE.md | "DSR > 0.95" | threshold | ASSUMPTION | N/A | Acceptance parameter. |

### research/README.md & calibration settings

| # | claim source | metric | value | provenance | validation seq | notes |
|---|---|---|---|---|---|---|
| 42 | README parity table | psr()/expected_max_sharpe() golden vectors | 6 values | ASSUMPTION | N/A | Deterministic test fixtures (not strategy performance); pinned by `test_dsr_parity.py`. Reference-only. |
| 43 | calibration_results.md | data/settings: 95,832 bars 2004–2020, atr_period=14, windows[10,30,70], 1000 perms, seed=42 | config | ASSUMPTION | N/A | Frozen calibration configuration. |

---

## Tally

| Provenance | Count | Rows |
|---|---|---|
| HARNESS_VERIFIED | 20 | 4–12, 14–16, 26–27, 29–30, 44–48 |
| SEEDED_UNVERIFIED | 11 | 1–3, 18–20, 22–23, 25, 32–33 |
| ASSUMPTION | 7 | 13, 34–35, 40–43 |
| CROSS_REFERENCED | 5 | 17, 21, 36–39 |
| AMBIGUOUS | 2 | 28, 31 |

(Rows counting a merged multi-metric claim as one line.)

Rows 18–19 stay in SEEDED_UNVERIFIED (the seed's original provenance) but are now
**REFUTED by seq=30** — same treatment as the falsified 1.76 (row 3): the seed
line is kept for lineage while the measured truth lives in the harness-verified
rows (44–48). "Refuted" is a verdict on the seed, not a new provenance class.

## Harness queue (next sessions)

Priority order for scheduling reproduction/validation runs:

1. ~~**asqs walk-forward (rows 18–20)** — live on demo, 5.14 unbacked, no log entry.
   Build/run the qhf walk-forward exactly as crest_n_keel got at seq=29; log the
   result as a `5_walk_forward` UPDATE. **Highest priority.**~~ ✅ **DONE 2026-07-03
   (seq=30).** REFUTED — OOS Sharpe −1.06/−1.04, PF 0.91/0.90, DSR 0.000 (rows
   44–48). Export driver `examples/export_asqs_returns.py` + `data/asqs/`
   returns + `recompute_dsr.py` now exist, mirroring crest_n_keel. **Remaining
   owner decision:** asqs is still live on demo — pause/kill vs keep, like the
   open crest_n_keel reconciliation.
2. **VALIDATION.md MDD figures (rows 32–33)** — produce the backtest artifacts
   behind the 15.6% (crest) and 5.5% (asqs) drawdown-guard anchors, or restate
   the guards against seq=29's measured MDD.
3. **Calibration E-Ratios (rows 14–16, 24, 26–27)** — cheap: run
   `pytest -k "calibration or weak or control"` to re-derive exact decimals and
   confirm the doc still matches; promote from "bounds-pinned" to fully current.
4. **seq=28 avwap_multibar (row 31)** — decide: re-parameterise to clear the
   ≥100-trigger floor, or close the family per its own seq=28 note.
5. **Housekeeping** — correct the seed E-Ratio window mislabels (rows 1, 22, 26)
   if/when those hypotheses are re-touched; do not hand-edit the append-only log.
