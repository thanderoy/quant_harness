# qhf — Project Status

A living record of phases, decisions made, and open items. Updated at the end
of each work session.

**Last updated:** end of session — Phase 2a complete.

---

## Snapshot

| Metric | Value |
|---|---|
| Tests passing | **53 / 53** |
| Source files | 14 modules (4 packages) |
| Lines of code | ~2,400 (incl. tests, excl. blank/comments) |
| Calibration | Verified: noise FAILs gates, real alpha PASSes |
| Real-data verified against | 5 timeframes × 21.6 years XAUUSD (1.4M+ M5 bars) |

---

## Phase progress

| Phase | Module | Status | Tests |
|---|---|---|---:|
| 1 | metrics.core (Sharpe, Sortino, Calmar, MDD, PF, expectancy, CAGR) | ✅ done | included |
| 1 | metrics.deflated (PSR, DSR, expected_max_sharpe) | ✅ done | included |
| 1 | metrics.pbo (CSCV) | ✅ done | included |
| 1 | validation.walk_forward (rolling/expanding splits) | ✅ done | included |
| 1 | reports.scorecard (gates, Result, Thresholds) | ✅ done | 16 |
| 2a | data.csv_loader (auto-sniff, MT5 format, gap detection) | ✅ done | 12 |
| 2a | data.cost_model (Pepperstone Razor MT5) | ✅ done | 13 |
| 2a | walk_forward.exclude_ranges + SplitReport + align_data_files | ✅ done | 12 |
| 2a | examples/gap_report.py diagnostic | ✅ done | — |
| 2b | engines.btpy_runner (backtesting.py wrapper) | ⏭ next session | — |
| 2c | validation.stress (spread shock + parameter sensitivity) | ⏭ after 2b | — |
| 3 | engines.vbt_runner (VectorBT parameter-sweep wrapper) | ⏭ later | — |
| 3 | reports.tearsheet (HTML/PDF strategy report) | ⏭ later | — |

---

## Decisions made (chronological)

| # | Decision | Rationale |
|---|---|---|
| 1 | Build the harness FIRST, then re-validate existing strategies, then generate new ones | The "disciplined path." Without DSR/PBO/walk-forward, any backtest is just an equity curve. |
| 2 | Use both VectorBT (parameter sweeps) and backtesting.py (path-dependent fills) | Different jobs: breadth vs depth. |
| 3 | Linux dev box, Windows VPS for live MT5 only | MT5 Python lib is Windows-only. CSV-based pipeline avoids the OS lock-in. |
| 4 | Validate all three strategies (1H HMA+Stoch, M15 HMA+Stoch, ASQ SafeScalping) | Same data, same gates — only valid comparison. |
| 5 | Income target reframed: KES 1M/yr from $100 = 14yr horizon at 15% CAGR + $100/mo DCA | Original 6M/yr target was 462× starting capital — mathematically impossible. |
| 6 | Strategy targets: 20% CAGR, Sharpe > 1.5, max DD 30% portfolio / 20% acceptable | Defensible vs hedge-fund history; consistent with risk profile. |
| 7 | "20% gain per trade" rejected; per-trade gains scale 0.3–3% by horizon | Per-trade % of account at 20% requires 40:1 leverage and assumed 50%+ hit rate on coin-flip moves. |
| 8 | H1 strategy v1.1 patches: sane `safety_floor_atr=0.10` (numerical only), explicit `min_atr_for_signal` (regime filter), persistent peak-equity drawdown guard | Three real bugs in v1.0; signal filter and sizer floor were conflated in one constant. |
| 9 | M15 v1.1: keep `min_atr_for_signal=5.0` (preserves v1.0 behaviour) | M15 had the right structure already — only the implementation location moves to strategy.py. |
| 10 | H1 v1.1: new default `min_atr_for_signal=1.0` — small behaviour change vs v1.0 | Documented; v1.0 backtest baseline preservable via git tag for comparison. |
| 11 | ASQ SafeScalping parked until original .mq5 source is in hand | Python class is entries-only; full strategy lives in MT5 OnTick handler we don't have. |
| 12 | Stay on pip+venv (not uv) for now | Minimum moving parts; revisit if dependency surface expands. |
| 13 | Build the exclusion mechanism in walk_forward; defer truncation decision | Keep validation infrastructure flexible; data quality choices come later. |
| 14 | Default research thresholds: gap < 0.5, PBO < 0.5, DSR > 0.95, OOS DD < 30%, trades ≥ 30, PF ≥ 1.20 | Production: 0.3 / 0.3 / 0.99 / 0.15 / 100 / 1.40 (tighter for live capital). |

---

## Bugs found and fixed

| # | Where | What | Severity | Fix |
|---|---|---|---|---|
| B1 | sizer.py | `XAUUSD_MIN_ATR=5.0` distorted normal H1 sizing — over 60% of bars affected | 🔴 high | New `LOT_SAFETY_FLOOR_ATR=0.10` (numerical safety only); regime filter moved to strategy |
| B2 | sizer ↔ strategy | Sizer used floored ATR; broker SL placement used raw ATR — risk-target mismatch | 🔴 high | Sizer returns `(lots, effective_atr)`; caller uses `effective_atr` for SL too |
| B3 | strategy.py | "10% drawdown guard" was actually `equity < balance * 0.90` (open-P&L only check) | 🔴 high | New `DrawdownGuard` with persistent peak-equity tracking via JSON file |
| B4 | gap_report.py | f-string `{ts:<19}` parsed as datetime format spec, not width | 🟡 med | Pre-stringify timestamps with `strftime` |
| B5 | strategy.py (ASQ) | `_daily_trades` lives in instance attrs — lost on process restart | 🔴 high (deferred) | Same fix pattern as B3; not applied (ASQ parked) |
| B6 | strategy.py (ASQ) | `_check_drawdown` has same bug class as B3 | 🔴 high (deferred) | Same fix pattern; not applied (ASQ parked) |
| B7 | strategy.py (ASQ) | H1 confirmation fetch on order-placement path adds 50–500ms latency | 🟡 med (deferred) | Move H1 fetch upstream of M5 evaluation; cache per bar |
| B8 | strategy.py (ASQ) | Session timezone hardcoded to UTC; original EA uses MT5 server time | 🟡 med (deferred) | Document; choose convention before backtest |

---

## Data quality findings

| Finding | Affects | Disposition |
|---|---|---|
| 32-day gap **2025-09-12 → 2025-10-15** in all 5 timeframes (broker history hole) | All TFs, recent OOS | Mechanism in place: `exclude_ranges=[("2025-09-12", "2025-10-15")]` |
| 9-day gap **2026-01-13 → 2026-01-22** in H4/M5/D1 only | TFs ending Jan 2026 | Same mechanism: `exclude_ranges=[..., ("2026-01-13", "2026-01-22")]` |
| File end-dates differ: H1, M15 → 2025-12-31; H4, M5, D1 → 2026-01-30 | Multi-TF parallel analysis | `align_data_files()` helper available |
| Bar coverage 92–101% of theoretical (M5 92% / H4 101%) | All | Acceptable; normal forex closure pattern |
| Top 10 gaps in H1 (excl. the 32-day) are all US holiday closures (Thanksgiving / Labor Day / Christmas / Presidents Day) | All TFs | Harmless for bar-close strategies |
| Total missing rows 4–14% by timeframe (D1: 4.3%, M5: 13.6%) | All | Mostly small holiday holes |

---

## Open / pending items

### Required before next session

| Item | Owner | Notes |
|---|---|---|
| Apply v1.1 patches to live H1 + M15 strategies | You | git tag `HMA1H-v1.0` and `HMAM15-v1.0` first, then apply patches as separate commits. M15 keeps `min_atr_for_signal=5.0`; H1 takes new default `1.0`. |
| Decide on data: re-export, truncate, or keep with exclusions | You | Mechanism handles all three. Re-export is the cleanest. |

### Useful but not blocking

| Item | Owner | Notes |
|---|---|---|
| Get current Pepperstone XAUUSD swap rates from MT5 | You | Override placeholders in `cost_model.py` for production accuracy. ~30 seconds in MT5 Symbol Specifications. |
| Get Pepperstone XAUUSD Stops level value | You | Currently assumed at $0.10/oz floor; verify against MT5 Symbol Specifications. |
| Locate original ASQ .mq5 source | You | Required before ASQ revalidation. Possibly download from mql5.com/en/code/71189 if still available. |

### My queue for next session

| Item | When |
|---|---|
| Write `qhf.engines.btpy_runner` (backtesting.py wrapper) | Next session start |
| Write strategy adapter that wraps live H1 / M15 strategy classes for backtesting.py | Next session |
| Run H1 v1.0 baseline + H1 v1.1 + M15 v1.0 + M15 v1.1 through harness | Next session |
| Generate scorecard reports for all four | Next session |

---

## Architecture invariants

These hold throughout the project. If a future change would break them, that's
the moment to stop and reconsider.

1. **The harness scores returns; it does not run strategies.** Engine-agnostic.
2. **Pre-registered gates only.** Threshold changes go through `Thresholds.production()` or a documented override — not silent in-code edits.
3. **`num_trials` is honest.** Every parameter sweep cell counts. Not "number of variants in the final run."
4. **Bar-close evaluation only.** No look-ahead through intra-bar prices, no decisions on the currently-forming bar.
5. **The MT5 live path is deterministic.** No LLM in the order-placing path, ever. The harness validates the deterministic strategy; LLM agents only ever advise upstream of orders.
6. **All strategies share the same scaffolding.** Same indicators module, same sizer module, same drawdown guard. Bug fixes propagate to all consumers.

---

## Cumulative session count

| # | Focus | Outcome |
|---|---|---|
| 1 | Agentic AI research, scope, harness Phase 1 | Research report, harness math primitives |
| 2 | Phase 1 setup, data loading, strategy spec extraction | All three strategies audited; H1+M15 patched; ASQ parked |
| 3 | Phase 2a build (loader, costs, exclusions, gap report) | 53/53 tests; data quality mapped |

---

## What "done" looks like

Validated H1 and M15 strategies with all gates passing on real Pepperstone XAUUSD
data, with full DSR / PBO / walk-forward reports generated, baseline (v1.0) vs
patched (v1.1) comparisons quantified. Engine wrapper drives both VectorBT
(breadth) and backtesting.py (depth). ASQ comes back later with .mq5 source.
After validation, MQL5 translation of the surviving strategies for live demo
deployment, with the deterministic-strategy-core / read-only-monitoring-agent
architecture from the original report.
