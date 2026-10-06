# Test Triage Notes

Triage of the pre-existing 10F/5E baseline (see SPEC: "Triage and Resolve
10F/5E Pre-existing Test Failures"). Each failing test was categorized as one
of: **REAL_BUG** (production wrong, fix production), **OBSOLETE_TEST**
(production intentionally redesigned, rewrite/delete test), **WRONG_EXPECTATION**
(test never right, fix test), or **ENV_DEPENDENT** (mark + skip).

The investigation **falsified several of the SPEC's hypotheses** — in particular
the SPEC's P0 (a suspected ATR bug) does not exist. Findings below are grounded
in the current source, not the SPEC's assumptions.

## Group D — ATR Wilder smoothing — `WRONG_EXPECTATION` (highest-priority, resolved)

- **Test:** `test_indicators.py::test_atr_wilder_smoothing`
- **Finding:** The production ATR in `indicators.atr` is **correct** Wilder/RMA
  smoothing and matches Pine `ta.atr()`. The test fixture was wrong: it set
  `high = close + 10` for the stepped bars but left `low = close - 5`, giving a
  high-low span (and true range) of **15, not the 20 its comment claimed**.
  TR = max(high-low, |high-prev_close|, |low-prev_close|); with a +1/bar close
  the prev-close terms are small, so the span is the TR.
  - Production: `atr[15] = (10*13 + 15)/14 = 145/14 = 10.357142…` ✓ (correct)
  - Test expected: `(10*13 + 20)/14 = 150/14 = 10.714285…` ✗ (bad fixture)
- **Resolution:** Fixed the fixture to widen BOTH sides (`high=close+10`,
  `low=close-10`) so TR genuinely steps to 20, and added an in-test guard
  asserting `TR[14]==10`, `TR[15]==20`. The test is now a valid frozen-fixture
  Wilder regression anchor.
- **Downstream impact (SPEC §4.5):** NONE. ATR was never wrong, so position
  sizing, `_compute_sl_tp`, open ASQS positions, and any `crest_n_keel`
  backtest are unaffected. **No backtest re-run required; the ATR concern does
  not gate `crest_n_keel`.**

## Group C — Stochastic edge cases — `REAL_BUG` (resolved)

- **Tests:** `test_indicators.py::test_stochastic_nan_padding`,
  `test_indicators.py::test_stochastic_period_longer_than_series`
- **Finding:** `stochastic()` used `raw_k.where(hl_range > 0, 50.0)` to default
  constant-price bars to the midpoint. But during warmup `hl_range` is NaN, and
  `NaN > 0` is False, so `where` **overwrote the leading NaN padding with 50.0**
  (verified: `k[2], k[3] == 50.0`, should be NaN). Same failure when the period
  exceeds the series length (everything should be NaN, was 50.0).
- **Resolution:** Switched to `raw_k.mask(hl_range == 0, 50.0)`. `== 0` is False
  for NaN, so genuine zero-range bars still map to 50.0 while insufficient-data
  bars correctly stay NaN. Documented the NaN/insufficient-data contract in the
  `stochastic()` docstring (SPEC §5.4).
- **Strategic relevance:** Insufficient-bars-at-startup is a real surface for an
  H1 strategy on a fresh deploy; callers must guard against NaN %K/%D rather
  than assume a numeric reading — now stated in the docstring.

## Group A — `_check_daily_cap` — `OBSOLETE_TEST` (rewritten)

- **Tests:** `test_asqs_strategy.py::TestCheckDailyCap::*` (4)
- **Finding:** NOT signature drift. The method was redesigned from an in-memory
  `_daily_trades`/`_last_trade_date` counter to a **DB count** (`Trade.objects`
  filtered by strategy + today's date). That redesign is correct: strategies run
  as stateless Celery tasks (a fresh instance per cycle), so an in-memory counter
  would reset every run. The tests targeted the removed in-memory design and
  passed a `now` arg the method no longer takes.
- **Resolution:** Rewrote the class against the DB design (`@pytest.mark.django_db`
  + `baker.make(Trade, …)`): under-cap allows, at-cap blocks, and the per-day /
  per-strategy scoping (yesterday's and other strategies' trades don't count).

## Group B — `_compute_sl_tp` — `OBSOLETE_TEST` (rewritten)

- **Tests:** `test_asqs_strategy.py::TestComputeSlTp::*` (3)
- **Finding:** NOT signature drift. The method uses **fixed-point** SL/TP
  (`SL_POINTS=300` → $3.00, `TP_POINTS=450` → $4.50) — intentional for this
  scalper. The tests passed an `atr` arg and referenced `sl_atr_mult`/
  `tp_atr_mult`, which do not exist; they targeted a removed ATR-multiple design.
- **Resolution:** Rewrote the class to assert the fixed-point SL/TP and the
  resulting RR (`TP_POINTS / SL_POINTS`), importing the constants so the test
  tracks the production values.

## Group E — `TestCheckDrawdown` — `OBSOLETE_TEST` (deleted)

- **Tests:** `test_asqs_strategy.py::TestCheckDrawdown::*` (5 errors)
- **Finding:** The v1.0 `_check_drawdown(balance, equity)` method is gone;
  drawdown enforcement moved to the persistent `DrawdownGuard`, whose constructor
  validates `max_drawdown_pct ∈ (0, 1)`. The tests built the strategy with
  `max_drawdown_pct=10.0` → `ValueError` in `setup_method` → 5 errors.
- **Resolution:** Deleted the class. The surface is already covered by
  `test_drawdown_guard.py`, `test_asqs_drawdown_guard.py`, and the ASQS
  `evaluate()` halt integration tests (which assert the load-bearing invariant
  that downstream work does not run when tripped). Per SPEC §7.3, no migration
  of cases is needed — the existing tests are strictly better.

## Suspicions noted for follow-up (not fixed here — scope discipline, SPEC §10)

- None surfaced during this pass.
