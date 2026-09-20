# D6 — Hardcoded-assumption audit

**Phase 0 task D6.** Catalogue of every XAUUSD-specific constant, assumption and code path
across the two repositories in scope, with its generalised replacement.

- **Scope:** `wine-mt5-python-setup` (WMPS) at `3db869a` (working tree, dirty) and
  `quant_harness` at `cb48e00`.
- **Produced:** 2026-08-31. No production code was changed.
- **Package naming:** target packages are `resources`, `strategies`, `research`, `platform`
  (distributions `qh-resources` / `qh-strategies` / `qh-research` / `qh-platform`), per the
  ruling of 2026-08-31 superseding §2.1's `qh_core` / `qh_research` / `qh_execution`.

Status values: **RESOLVED** (replacement specified and assigned to a Phase 1 task),
**DEFERRED** (out of Phase 0–1 scope, reason given), **FINDING** (not an assumption to
replace — a defect or fact discovered by the audit).

---

## D6 required output — does `btpy_runner` route sizing through `calculate_lot_size`?

**Answer: partly — and the split matters more than the question anticipated.**

`btpy_runner` itself is sizing-agnostic. It constructs `Backtest(..., cash=10_000,
margin=1/400)` and never supplies a default size; every order size is decided inside the
strategy class and passed as an absolute unit count (`size=size_oz`) to
`self.buy()` / `self.sell()`. `backtesting.py`'s native fractional-equity sizing (the
`0 < size < 1` branch) is never exercised.

But the strategies do not agree on how that number is produced. There are **three** sizing
implementations:

| Strategy | Sizing route | Sensitive to T5? |
|---|---|---|
| `hma_stoch` (crest_n_keel) | `research.engines.sizer.calculate_lot_size` | **Yes** |
| `cnk_momentum` | `research.engines.sizer.calculate_lot_size` | **Yes** |
| `zlch` | `research.engines.sizer.calculate_lot_size` | **Yes** |
| `ebb_n_flow` | `_size_oz()` — private reimplementation, `ebb_n_flow.py:131-137` | No |
| `asq_safe_scalping` | inline `size = risk_amount / sl_dist`, `asq_safe_scalping.py:458` | No |

**Consequence for T9c: not mandatory.** T9b's fixture is `crest_n_keel` = `hma_stoch`, which
routes through `calculate_lot_size`. The historical walk-forward artifact is therefore
sensitive to T5, and T9b covers sizer integration with SL/TP placement at the artifact level.
T9c's premise — "no historical artifact is sensitive to T5" — does not hold.

This is recorded as a resolved decision, not a judgement call to be revisited: the condition
in the spec is a fact about code, and the fact is that the T9b fixture exercises the sizer.

---

## FINDING 1 — the two `sizer.py` copies are numerically identical

`WMPS backend/trading/app/quant/strategies/sizer.py` and `quant_harness research/engines/sizer.py`
were compared with docstrings stripped via AST normalisation. The arithmetic is identical:
same `effective_atr = max(atr_value, safety_floor_atr)`, same `risk_amount`, same
`sl_distance`, same `math.floor` step-down, same clamp.

The only difference is that the harness copy **omits two input-validation guards** present in
WMPS:

```python
if min_lot <= 0 or max_lot < min_lot:
    raise ValueError(...)
if safety_floor_atr <= 0:
    raise ValueError(...)
```

**Why this matters:** it means no historical harness artifact is numerically affected by the
duplication, so D8 can pin the WMPS implementation and T11 parity will hold against artifacts
produced by the harness copy. Had the arithmetic diverged, every stored backtest result would
have needed re-derivation before parity was meaningful.

The missing guards are unreachable in every current call site (all pass defaults), so this is
recorded rather than fixed — fixing it during the freeze would require a mirrored change under
§1.3 for no behavioural gain.

## FINDING 2 — `ORDER_FILLING_IOC` is already partly generalised

The spec's D1 guard assumes IOC is hardcoded. It is not. `mt5-api/app/main.py:776-780` and
`:980-984` already branch across `ORDER_FILLING_IOC` / `_FOK` / `_RETURN`. The residual
assumption is in documentation and in the *choice rule*, not in a literal. D1 must still
record supported filling modes per symbol, but the code change implied by the guard is
smaller than the spec anticipates.

## FINDING 3 — a strategy is currently live on demo

`h1_momentum` is scheduled and firing (`settings.py:281`, `crontab(minute=2,
day_of_week="mon-fri")`, magic per `strategy.py`). It is explicitly paper-forward data
collection, not a promoted strategy. It predates Phase 0 and so does not breach acceptance
criterion 10 ("the demo account has traded no new strategy during the phase"), but the phase
begins with it running and that should be a recorded fact rather than a surprise at Phase 3.
`crest_n_keel` and `asqs` are confirmed retired from the beat schedule.

---

## Audit table

### Contract size and lot geometry

| # | Location | Assumption | Generalised replacement | Task | Status |
|---|---|---|---|---|---|
| 1 | `WMPS sizer.py:43` | `XAUUSD_POINT_VALUE_PER_LOT = 100.0` | `spec.contract_size` from registry | T1/T5 | RESOLVED |
| 2 | `WMPS sizer.py:44-46` | `XAUUSD_MIN_LOT/MAX_LOT/LOT_STEP` = 0.01/0.10/0.01 | `spec.min_lot`, `spec.max_lot`, `spec.lot_step` | T1/T5 | RESOLVED |
| 3 | `WMPS sizer.py:50` | `LOT_SAFETY_FLOOR_ATR = 0.10` (USD/oz) | Per-instrument floor in **tick units** from registry | T5 | RESOLVED |
| 4 | `research/engines/sizer.py:16-20` | Duplicate of rows 1–3 | Module deleted at Phase 3; `resources.risk.sizer` is sole implementation | T11/Ph3 | RESOLVED |
| 5 | `research/datasets/cost_model.py:40` | `PEPPERSTONE_XAUUSD_CONTRACT_SIZE = 100.0` | `spec.contract_size` | T1 | RESOLVED |
| 6 | `research/engines/strategies/ebb_n_flow.py:32,35` | `XAUUSD_CONTRACT = 100.0`, `DOLLARS_PER_OZ_PER_LOT` | `spec.contract_size`; delete `_size_oz`, call `size_position()` | T5 | RESOLVED |
| 7 | `WMPS asqs/strategy.py:100,618` | `XAUUSD_CONTRACT = 100.0`, `raw_lots = risk / (sl_dollars * XAUUSD_CONTRACT)` | `size_position()` | Ph3 | DEFERRED — asqs is falsified and disabled; migrate at execution merge |
| 8 | `research/engines/btpy_runner.py:110,139` | `/ 100.0` twice — "1 lot = 100 oz" for commission and for `Size`→lots | `spec.contract_size` threaded through `BtRunResult` | T12 | RESOLVED |
| 9 | `WMPS h1_momentum/strategy.py:298` | `lot * 100.0` in realised-risk calc | `spec.contract_size` | Ph3 | DEFERRED — live strategy, frozen under §1.3 |

### Symbol identity

| # | Location | Assumption | Generalised replacement | Task | Status |
|---|---|---|---|---|---|
| 10 | `WMPS h1_momentum/strategy.py:60` | `SYMBOL = "XAUUSD"` module constant | Instrument passed in; strategy takes `spec` | Ph3 | DEFERRED — frozen |
| 11 | `WMPS asqs/tasks.py:116` | `get_market_rates("XAUUSD", "M5", ...)` literal | Symbol from strategy config | Ph3 | DEFERRED — disabled |
| 12 | `WMPS mt5-api/main.py` ×5 (`184,230,325,376,421`) | `"symbol": "XAUUSD"` in OpenAPI **examples** only | Change examples to a neutral symbol | Ph3 | DEFERRED — documentation, not behaviour |
| 13 | `WMPS mt5-api/main.py:1534,1577` | `symbol: str = "XAUUSD"` endpoint **defaults** | Make the parameter required — a default symbol is a live-order hazard | Ph3 | RESOLVED (deferred execution) |
| 14 | `WMPS common/constants.py:127` | `METALS = ["XAUUSD","XAGUSD"]` | Registry asset-class field | T1 | RESOLVED |
| 15 | X1 test target | Symbol literals anywhere outside the registry | AST-level check, all four packages | X1 | RESOLVED |

### Execution and broker

| # | Location | Assumption | Generalised replacement | Task | Status |
|---|---|---|---|---|---|
| 16 | `WMPS mt5-api/main.py:776-780, 980-984` | Filling-mode branch exists but selection rule is fixed | Registry `filling_modes`; select per symbol | T1/Ph3 | RESOLVED — see FINDING 2 |
| 17 | `research/engines/btpy_runner.py:413` | `margin = 1.0/400.0` — leverage assumed 1:400 for all instruments | Registry margin/leverage per symbol | T12 | RESOLVED |
| 18 | `research/engines/btpy_runner.py:362,458` | `cash = 10_000` default vs $100 live account | Explicit per-run; granularity flag makes the gap visible | T5/T12 | RESOLVED |
| 19 | All strategies | Fill assumption is implicit (single path) | Four-config `SimulatedBroker` frontier | T12/X23 | RESOLVED |
| 20 | Spread/commission | Cost model carries assumed spread | `PROVISIONAL_COSTS` stamp until D3 has real data | D3/T12 | DEFERRED — blocked on MT5 |

### Scheduling and identity

| # | Location | Assumption | Generalised replacement | Task | Status |
|---|---|---|---|---|---|
| 21 | `WMPS settings.py:263-308` | Beat schedule is per-strategy, single-symbol, `mon-fri` UTC | Per-instrument scheduling from registry session calendar | Ph4 | DEFERRED — multi-symbol live is Phase 4 |
| 22 | `WMPS settings.py` beat | `crontab(day_of_week="mon-fri")` assumes 24×5 | Holds for FX majors and metals; breaks on indices/crypto | Ph4 | DEFERRED |
| 23 | Magic numbers (`1100001`, `1500020`, `2460000`, h1_momentum) | One magic per strategy, implicitly one symbol | Magic must key on **(strategy, symbol)** once one strategy runs on seven instruments | Ph4 | RESOLVED (design fixed now, implemented Phase 4) |
| 24 | `WMPS adapters/mt5_api.py:136,330` | `magic: int = 0` default | Make required — a defaulted magic breaks position dedup | Ph3 | RESOLVED (deferred execution) |

### Risk parameters

| # | Location | Assumption | Generalised replacement | Task | Status |
|---|---|---|---|---|---|
| 25 | Trading profile | 5% risk / 10% max DD | 2% / 8%, matching code | §8 | RESOLVED — profile is stale, code is correct |
| 26 | `drawdown_guard.py` | Guard is account-level, single-strategy | Portfolio-level guard + correlation cap | Ph4 | DEFERRED |
| 27 | `sizer.py` clamp | Min-lot clamp silently trades oversized positions | `lots=0`, `MIN_POSITION_EXCEEDS_RISK_BUDGET` | T5/X7 | RESOLVED — live risk bug |

### Dead / non-production code

| # | Location | Assumption | Generalised replacement | Task | Status |
|---|---|---|---|---|---|
| 28 | `WMPS backend/trading/backtesting/london_breakout_backtestpy.py` | `pip_value` default 0.10 "for XAUUSD"; reads `XAUUSD_15m.csv` | None — standalone legacy script, not imported | — | DEFERRED — dead code, delete at Phase 3 |
| 29 | `WMPS backend/trading/backtesting/band_volume_reversal_backtestpy.py` | Same | Same | — | DEFERRED — dead code |
| 30 | `WMPS tests/test_sizer.py`, `tests/test_asqs_strategy.py` | Assert against `XAUUSD_*` constants | Rewrite against registry fixtures | T11 | RESOLVED |

---

## Summary

- **30 rows.** 19 RESOLVED, 11 DEFERRED — every deferral names its phase and reason.
  (Was stated as 17/13 until 2026-09-20; two rows had since been resolved and
  the summary was not re-counted.)
- No row is left unclassified, satisfying Phase 1 acceptance criterion 6 in advance of the work.
- Three findings recorded that were not assumptions: identical sizer copies (lowers T11 risk),
  filling mode already generalised (lowers Phase 3 scope), and a live strategy on demo at
  phase start (a fact for criterion 10).
- The largest single structural finding is **three independent sizing implementations**, which
  is the concrete instance of the drift risk §1.3 exists to control.
