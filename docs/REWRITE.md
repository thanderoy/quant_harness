# quant_harness — Symbol-Agnostic Core: Phase 0 + Phase 1 Specification

**Status:** Draft for review
**Scope:** Phase 0 (diagnostic, no code changes) and Phase 1 (instrument registry, tradability mask, panel data layer, normalisation, sizing, log schema)
**Universe (initial):** FX majors — EURUSD, GBPUSD, USDJPY, USDCHF, AUDUSD, USDCAD, NZDUSD
**School:** Systematic-macro / CTA pipeline with AFML instrumentation bolted on where cheap and correct
**Sequencing decision:** Rebuild `quant_harness` first; merge the WMPS execution stack at Phase 3 (§1.3, §11)

---

## 1. Context

The project is renamed from `qhf` to `quant_harness` as part of this work (see T10). All module
paths below use the new namespace.

`quant_harness` today is a single-instrument XAUUSD system. Five mechanisms have been falsified or shelved
(`crest_n_keel`, `asqs`, `ebb_n_flow`, `zerolag_chandelier`, `flood_tide_h1`). The rejection
machinery is working correctly. The binding constraint is not inference quality — it is
information. At the observed OOS Sharpe range (0.27–0.41), Minimum Track Record Length against a
zero benchmark is 24–46 years. Single-series XAUUSD research is undecidable at those effect sizes,
regardless of how much validation machinery is added.

Breadth is the only structural fix. A mechanism tested with identical parameters across a
diversified panel is both statistically more decidable and — more importantly — tests the
*mechanism* rather than correcting for search behaviour after the fact. This is the strongest
anti-overfitting device available and does not depend on any contested statistical methodology.

A second, independent finding forces the same conclusion. At ~$100 equity, the minimum expressible
XAUUSD position (0.01 lot = 1 oz) risks roughly 12% of the account on a normal 1.5×ATR(H1) stop.
`sizer.py`'s clamp floor, not its calculation, determines position size on every gold trade. The
8% `DrawdownGuard` can be tripped by a single stop-out. Position sizing on XAUUSD at this capital
base is not a function; it is a constant.

### 1.1 What must not break

**The `research/log.py` hash chain migrates intact.** Starting a fresh log resets `trial_count()`
to zero and silently launders accumulated multiplicity into the next DSR evaluation. The log is
the most valuable artifact in the repository; all other code is replaceable. Any sequencing option
that does not carry the chain forward byte-verifiable is rejected.

### 1.3 Sequencing decision — rebuild first, merge second

`quant_harness` is established as a new repository containing the core and research packages. The
existing execution repository (`wine-mt5-python-setup`, "WMPS") continues to run the demo account
untouched during the rebuild, and is merged in as a third package at Phase 3.

**Rebuild does not mean rewrite.** The numerical code in WMPS is already verified against external
references — `atr()` matches Pine Script `ta.atr()` exactly, `hma()` implements the standard
formula, `sizer.calculate_lot_size()` has a documented `effective_atr` contract, `DrawdownGuard`
has crash-safe atomic persistence. Reimplementing any of it from the description in this document
would discard that verification and introduce exactly the backtest/live drift the restructure
exists to prevent.

Rule: **structure is built fresh; numerical code is ported verbatim and pinned by golden fixtures
generated from WMPS before the rebuild starts** (task D8). Any deviation from a ported
implementation must be a deliberate, logged change with a stated reason, not an artifact of
retyping.

**WMPS freeze.** For the duration of Phases 0–2, WMPS is bug-fix-only. Any change to
`indicators.py`, `sizer.py` or `drawdown_guard.py` during the window must be mirrored into
`resources` and the D8 golden fixtures regenerated in the same commit. No new strategies are
deployed. Falsified and shelved mechanisms stay disabled.

### 1.4 Honest caveat on the chosen universe

FX majors is a defensible *engineering* starting universe: uniform contract specs, uniform
granularity, uniform 24×5 sessions, no rolls, no dividends, no corporate actions, deep and
consistently priced history. It is a poor *breadth* universe. All seven pairs share USD as one leg.

Per-instrument SR = 0.40, k = 7:

| Avg pairwise ρ | Effective independent bets | Portfolio SR | Portfolio MinTRL |
|---|---|---|---|
| 0.30 | 2.50 | 0.63 | 12.6 y |
| 0.45 | 1.89 | 0.55 | 15.1 y |
| 0.60 | 1.52 | 0.49 | 17.6 y |

Realistic sign-adjusted correlation across USD-legged majors is in the 0.4–0.55 band, so the
practical answer is roughly **two independent bets, not seven**. Compare against a mixed universe
of 12 instruments spanning FX crosses, metals and indices at blended ρ ≈ 0.20–0.25:

| Instruments | Blended ρ | Effective N | Portfolio SR | MinTRL |
|---|---|---|---|---|
| 12 | 0.25 | 3.20 | 0.72 | 10.9 y |
| 12 | 0.20 | 3.75 | 0.77 | 10.0 y |

**Conclusion to record in the log:** FX majors is adopted for Phase 1 to build and validate the
symbol-agnostic machinery against the cleanest possible instrument set. It is explicitly *not*
expected to deliver the breadth benefit. Phase 2b adds non-USD-legged crosses (EURGBP, EURJPY,
AUDJPY, EURAUD), metals (XAUUSD, XAGUSD) and indices to reach effective N ≳ 3.5. Phase 0 task D4
measures the actual correlation matrix so this is a measured decision rather than an assumed one.

---

## 2. Goal

Refactor `quant_harness` so that every component below the strategy layer is instrument-neutral, and every
instrument-specific fact lives in exactly one declarative place. Acceptance is defined by exact
reproduction of an existing XAUUSD result through the new stack, not by new results.

**Definition of "symbol-agnostic":** a strategy module can be executed against any instrument in
the registry without modification, and produces target positions in risk units, never in lots,
never in a quote currency, never with a hardcoded tick size.

### 2.1 Repository structure

**Four packages, imported unprefixed.** The repository is `quant_harness` and is not itself
importable; each package under `packages/` ships as its own distribution and is imported under a
short bare name.

```
quant_harness/
├── packages/
│   ├── qh-resources/   → import `resources`
│   │                     instrument registry, tradability mask, panel, indicators,
│   │                     normalisation, sizing, drawdown guard, broker port
│   │                     — no Django, no Celery, no MetaTrader5, pure functions
│   ├── qh-strategies/  → import `strategies`
│   │                     strategy definitions; instrument-neutral, emit risk units
│   ├── qh-research/    → import `research`
│   │                     signal_edge, dsr, mintrl, log, btpy_runner, artifacts
│   └── qh-platform/    → import `platform`
│                         (Phase 3) Django app: tasks, models, MT5 adapter
├── services/
│   ├── mt5-api/          (Phase 3) Wine container; only place MetaTrader5 is imported
│   └── trading/          (Phase 3) Django + Gunicorn + Celery
├── monitoring/           (Phase 3)
└── docker-compose.yml    (Phase 3)
```

`resources` is the instrument-neutral core — the role the earlier `qh_core` name referred to.
There is no `qh_core`; that name was superseded in the same pass that split execution into two
packages. It appears nowhere else in this document, and any code or doc still using it is stale.

**Import-direction contract, enforced in CI (X19):**

```
resources  ←  strategies  ←  { research, platform }
```

- `resources` imports nothing from the other three.
- `strategies` depends only on `resources`.
- `research` and `platform` each depend on `strategies` (and transitively `resources`), and never
  on each other.
- `resources` is importable with no Django settings configured and no network access.

**Stdlib shadowing (X32).** A top-level package named `platform` shadows the stdlib `platform`
module for anything that imports it after `qh-platform` is installed. This is accepted
deliberately, but it is not free: CI must assert that `import platform` from a clean interpreter
still resolves to the stdlib, and that `qh-platform`'s own modules reach the stdlib module when
they need it. A shadowing failure is silent and surfaces far from its cause, so it is tested
rather than trusted.

This contract is what makes backtest/live parity structural rather than aspirational. It is the
single rule that must not be relaxed for convenience.

### 2.2 Broker port

`resources` defines a broker interface; `MT5APIClient` (Phase 3) and `SimulatedBroker` (Phase 1)
both implement it. The backtester and the live trader then run identical strategy code against
different broker implementations, and the execution-assumption matrix becomes a set of
`SimulatedBroker` configurations rather than a parallel simulation code path:

| Config | Fill assumption |
|---|---|
| `IDEAL` | Signal bar close, exact price |
| `NEXT_OPEN` | Next bar open, exact price |
| `NEXT_OPEN_SPREAD` | Next bar open plus registry median spread |
| `REALISTIC` | Next bar open plus 95th-percentile spread plus latency-adverse slip |

Phase 1 delivers the interface and `SimulatedBroker`. `MT5APIClient` is adapted to the interface
at Phase 3, and the adaptation is verified by replaying recorded live orders through both.

---

## 3. Non-goals

Explicitly out of scope. Do not implement, do not scaffold, do not leave TODOs for:

- Combinatorial Purged Cross-Validation, purging, sample uniqueness weighting, sequential
  bootstrap. No per-fold model fitting exists, so there is no train→test leakage channel to purge.
  Deferred to Phase 4, gated on a mechanism actually surviving panel testing.
- Meta-labeling and probability-scaled bet sizing. Unexpressible at 0.01-lot granularity on a
  $100 account.
- Fractional differentiation. Exists for ML feature ingestion; the strategies use price levels.
- Information / volume / order-imbalance bars. MT5 "volume" is broker tick count, not traded
  volume, and would make bar close event-driven, breaking Celery beat scheduling.
- Hierarchical Risk Parity. Requires a covariance matrix of multiple live return streams. Inverse-
  volatility weighting is sufficient and will remain so until ≥5 uncorrelated surviving strategies
  exist.
- Superior Predictive Ability (SPA) testing. Redundant with DSR — both correct for multiplicity —
  and requires a stationary bootstrap and defined model universe.
- Any composite robustness score. Sequential hard gates only. A composite invites gate-shopping
  and creates a number that can be optimised.
- **New strategy research of any kind during Phases 0–1.** The only strategy logic touched is the
  existing `flood_tide_h1`, used solely as a migration parity fixture.
- Re-parameterising any falsified mechanism. The two-iteration stopping rule stands.
- **Reimplementing any numerical function that already exists in WMPS.** Port verbatim, pin with
  golden fixtures (D8). This includes `wma`, `hma`, `stochastic`, `atr`, `calculate_lot_size` and
  `DrawdownGuard`.
- Merging the WMPS execution stack. Deferred to Phase 3 (§11). Nothing in Phases 0–2 may assume
  Django, Celery, Postgres, Redis or a live MT5 terminal is available.
- Changing live behaviour on the demo account. WMPS is frozen to bug-fix-only (§1.3).

---

## 4. Project constraints

- Python; Django + Celery + Docker Compose; `uv` for dependencies; pytest with `pytest-django`.
- MT5 accessed only through the `mt5-api` FastAPI service. No module outside that service imports
  `MetaTrader5`.
- `research/log.py` remains stdlib-only, JSONL-backed, append-only, hash-chained.
- `iloc[-2]` confirmed-bar discipline preserved everywhere. No look-ahead.
- All metrics must be harness-produced. No hand-entered values in the log without explicit
  provenance marking.
- Two-commit structure for log-affecting changes: log UPDATE, then git commit.
- Single account, ~$100 equity, single broker (Pepperstone Razor), demo during development.

---

## 5. Phase 0 — Diagnostic (produces facts, not code)

No production code changes. Output is one artifact JSON plus a short memo. Every downstream design
decision in Phase 1 must cite a Phase 0 number.

### D1 — Contract spec dump
Pull `symbol_info` for all seven majors plus XAUUSD and XAGUSD. Capture: contract size, tick size,
tick value, lot step, min/max/step lot, quote currency, margin currency, digits, stops level,
freeze level, filling modes, swap long/short, swap rate mode. Pin with an `as_of` UTC timestamp
and the terminal build number.

**Every snapshot carries a `provenance` field: `MT5_SYMBOL_INFO` or `HAND_ENTERED`.** There is no
third state and no default. A hand-entered contract spec is a seeded, unverified value of exactly
the kind the log provenance audit was built to catch — the difference is that this one propagates
silently into every sizing calculation downstream.

**If MT5 is unavailable:** D1 is recorded as `BLOCKED` with the stated dependency. The collector is
written and committed so it runs unattended the moment a terminal is up. No provisional snapshot is
produced merely to unblock other work; if one is produced deliberately for scaffolding, it is
marked `HAND_ENTERED` and is subject to the T1 refusal rule.

**Guard:** if `ORDER_FILLING_IOC` is not in the supported filling modes for any symbol, record it —
the current XAUUSD assumption does not generalise.

### D2 — Granularity feasibility table
For each instrument, compute the account-currency risk of the minimum position (`min_lot`) against
a 1.5×ATR(H1) and 1.5×ATR(H4) stop, using median ATR over the last 24 months. Express as a
percentage of $100 equity.

Produce a binary `tradable_at_capital` flag per instrument per timeframe, defined as
`min_position_risk_pct <= target_risk_pct`. Target risk is 2%, matching the current `sizer.py`
default rather than the stale 5% in the trading profile (see §8).

### D3 — Spread and cost census

Split into two parts, because the historical half may not be obtainable.

**D3a — forward collection (start immediately once MT5 is up).** A lightweight collector sampling
`get_tick` on a schedule for every candidate symbol, writing bid/ask/spread to Postgres with a UTC
timestamp. This runs continuously from the day it is switched on, so that by the time Phase 2
needs session-bucketed spread distributions, real measured data exists. Starting this is the
single highest-value MT5-dependent action available and should not wait for the rest of D1.

**D3b — historical, best-effort.** Broker tick history depth via `copy_ticks_range` varies by
symbol and by broker retention policy; twelve months of Pepperstone tick data may simply not be
available for every candidate. Pull what exists, record the actual depth obtained per symbol, and
do not silently substitute a shorter window for the specified one.

From whichever data is obtained: median spread, 95th-percentile spread, both broken out by session
bucket (Asia, London, NY, London/NY overlap, rollover window ±15 min). Add commission per round
turn from the account's Razor schedule.

Express total round-trip cost **as a percentage of 1×ATR** at M15, H1 and H4. This — not basis
points of notional — is the number that determines whether a mechanism can pay for itself.

Until D3 has real data, no cost assumption may be used in a logged result. A backtest run with an
assumed spread is marked `PROVISIONAL_COSTS` and cannot satisfy any acceptance criterion.

### D4 — Correlation matrix
Daily log returns, 5 years, all Phase 1 and Phase 2b candidate instruments.

**If any instrument's history is missing, the resulting effective-N is an upper bound, not an
estimate.** AUDUSD and NZDUSD in particular correlate strongly with each other and with the
commodity complex; omitting them makes the majors look more diversified than they are. Record
which instruments were included and mark the effective-N figure `PARTIAL_UNIVERSE` until the
matrix is complete. Sign-adjust USD-quoted
versus USD-base pairs so the matrix reflects directional co-movement. Report average pairwise |ρ|
and effective independent bets `k / (1 + (k−1)·ρ̄)` for: majors alone, majors + crosses, and the
full Phase 2b candidate set.

### D5 — Benchmark Sharpe (SR*)
Buy-and-hold annualised Sharpe per instrument over the intended backtest window, and for the
equal-risk-weighted panel. These become the `benchmark_sharpe` values wired into DSR. For FX
majors this will be near zero, which is correct and is a further argument for the universe; for
XAUUSD it will not be, which is why the gold results must be re-evaluated against it in Phase 2b.

### D6 — Hardcoded-assumption audit
Grep and catalogue every XAUUSD-specific constant, assumption and code path. Known starting
points: `XAUUSD_MIN_LOT`, `XAUUSD_MAX_LOT`, `LOT_SAFETY_FLOOR_ATR`, the `/ 100` divisor in
`calculate_lot_size` (a contract-size assumption), `ORDER_FILLING_IOC`, magic numbers, Celery beat
schedules, and any place a pip or point value is assumed. Output a table: location, assumption,
generalised replacement.

### D7 — Log integrity baseline
Run `verify()` on the existing chain. Record the terminal hash, `trial_count()`, and total entry
count. This is the migration reference. If `verify()` fails, stop and resolve before any other work.

### D8 — Golden fixtures from WMPS
Before any code is written in the new repository, generate and commit reference outputs from the
**current running WMPS code**:

- Indicators: `wma`, `hma`, `stochastic`, `atr` over a fixed, committed OHLCV sample (XAUUSD H1,
  ≥5,000 bars, including at least four weekend boundaries and one holiday), full output series
  serialised to CSV with float64 repr.
- `calculate_lot_size`: outputs across a grid of balance × ATR × risk_pct × sl_multiplier,
  including the clamp boundaries and the `LOT_SAFETY_FLOOR_ATR` path.
- `DrawdownGuard`: state transitions over a scripted equity sequence, including first-evaluation
  no-trip, peak advance, trip, and post-trip behaviour.

These fixtures are the contract `resources` must satisfy. They are generated once, committed, and
never regenerated except under the WMPS-freeze mirror rule (§1.3).

**Note:** the D8 fixtures are generated from XAUUSD H1 data because that is what the current code
runs on. They pin *numerical* behaviour only. Symbol-agnostic behaviour is a Phase 1 concern and
is not covered by them.

### D9 — Log and artifact location
Establish where `research/log.py`, the JSONL chain, and `research/artifacts/` currently live, and
produce the migration plan: source path, target path (`packages/qh-research/`), and the
`git subtree` command sequence that preserves history. Confirm the chain is self-contained — no
entry depends on a file outside the migrated tree.

### Phase 0 acceptance
- `research/artifacts/phase0_universe_<date>.json` written, containing D1–D5 outputs.
- Memo (≤2 pages) with the shortlist, the granularity verdict, the effective-breadth number, and
  the SR* table.
- D6 table committed as `docs/hardcoded_audit.md`.
- D7 baseline recorded as a log entry of type `AUDIT`, not as a strategy entry.
- D8 fixtures committed, with the generating script and the WMPS commit SHA they came from.
- D9 migration plan written and dry-run on a scratch clone.
- Any task that could not be completed is recorded as `BLOCKED` with its dependency named, its
  collector written and committed, and a re-run command. `BLOCKED` is an acceptable Phase 0 outcome;
  a substituted assumption is not.
- **Zero changes to production code.**

**Execution order when MT5 is unavailable.** D6, D7, D8 and D9 have no broker dependency and gate
everything downstream — run them first regardless. D2, D4 and D5 run partial on available data and
are stamped `PARTIAL_UNIVERSE`. D1 and D3 are `BLOCKED` with collectors committed. Phase 0.5 may
proceed on this basis; **Phase 1 T1 may not close** until D1 is unblocked, per the provenance
refusal rule.

---

## 5A. Phase 0.5 — Repository establishment

A short, mechanical phase. No behavioural change, no new logic.

1. Create the `quant_harness` repository with the §2.1 skeleton and per-package `pyproject.toml`.
2. `git subtree add` the research tree and log from its current location, **preserving history**.
   Copying files in is not acceptable — losing the history of an append-only research record while
   arguing that append-only records matter is not a defensible position.
3. Append two events to the log, in order: `REPO_MIGRATION` (old repo, new repo, source SHA) and
   `PROJECT_RENAME` (old namespace `qhf`, new namespace `quant_harness`, commit SHA). Existing
   entries are not rewritten.
4. Add the CI rules: import-direction test (X19), log append-only check (X21), path-filtered test
   selection per package.
5. Commit the D8 golden fixtures into `packages/qh-resources/tests/fixtures/`.

**Acceptance:** `verify()` passes; `trial_count()` equals the D7 baseline; `resources` is an empty
but importable package with the fixtures present and CI green.

---

## 6. Phase 1 — Implementation tasks

### T1 — `resources/instruments/registry.py`
`InstrumentSpec` dataclass carrying every D1 field plus derived helpers: `value_per_price_unit()`,
`round_to_lot_step()`, `min_position_risk(stop_distance, account_ccy_rate)`.

**Provenance refusal rule.** `Registry.load()` reads the D1 `provenance` field and **raises on a
`HAND_ENTERED` snapshot unless `allow_provisional=True` is passed explicitly at the call site.**
Any artifact produced under a provisional snapshot is stamped `PROVISIONAL_SPECS` in its metadata
and in the log entry. No parity run, no acceptance criterion, and no logged research result may be
produced under one. This converts "we'll pin the real specs later" from an intention into a
mechanical blocker.

`Registry` loads from a pinned JSON snapshot committed to the repo — **no network or MT5 call at
import time**, so backtests are reproducible and offline. A separate `refresh_registry` management
command re-pulls from `mt5-api` and writes a new snapshot with a new `as_of`; snapshots are never
overwritten, only added, and every backtest artifact records which snapshot it used.

### T2 — `resources/data/mask.py`
`TradabilityMask`: a boolean Series aligned to the bar index, `True` where the bar is tradable.
Falsity sources, each independently flagged so they can be attributed:
`session_closed`, `weekend_gap`, `holiday`, `rollover_window`, `spread_above_threshold`,
`insufficient_ticks`, `spec_change_boundary`.

Provide `masked_rolling(series, mask, window, fn)` implementing the R3 ruling: **window indicators
NaN-out masked bars; accumulator indicators skip them while keeping the calendar index.** Every
indicator declares its class at definition time; there is no default and no per-call override. **This is expected to change existing XAUUSD indicator values across weekend gaps.** That
divergence is a bug fix, not a regression; it must be quantified and recorded in the T9 parity
report rather than suppressed.

### T3 — `resources/data/panel.py`
`Panel`: aligned multi-instrument OHLCV plus per-instrument mask, UTC-indexed.

Alignment policy is explicit and tested: union index, **no forward-fill across a closed session**.
A bar that does not exist for an instrument is masked, never synthesised. Any strategy reading a
masked bar must receive NaN, not a stale price.

### T4 — `resources/features/normalize.py`
Instrument-neutral primitives: `atr_normalise(series, atr)`, `vol_zscore(series, window)`,
`log_return(series)`, `range_pct(high, low, close)`. Every strategy input and every target passes
through one of these. A Donchian breakout must carry identical meaning on USDJPY and on gold.

**Invariant to assert in tests:** the disjointness rule already adopted in the harness — feature
inputs and the target normaliser must not share a window. Enforce mechanically, not by convention.

### T5 — `resources/risk/sizer.py` (port of WMPS `sizer.py`)
Signature becomes:

```
size_position(spec: InstrumentSpec, account_balance, account_ccy,
              risk_pct, stop_distance_price, fx_rate_provider)
    -> PositionSize(lots, risk_actual_ccy, risk_actual_pct, granularity_flag, reason)
```

Requirements:
- Currency conversion for non-USD quote currencies (USDJPY, USDCHF, USDCAD). This is the single
  most under-estimated item in the phase; budget for it explicitly.
- `granularity_flag` is set when `min_lot` risk exceeds the risk budget. In that case return
  `lots=0` with `reason=MIN_POSITION_EXCEEDS_RISK_BUDGET` — **do not silently round down to
  min_lot.** Silently trading an oversized position is the current behaviour and is a live risk bug.
- The existing `effective_atr = max(atr, LOT_SAFETY_FLOOR_ATR)` guard generalises to a per-
  instrument floor sourced from the registry, expressed in tick units.
- Caller contract preserved: the returned effective stop distance, not the raw one, is used for
  SL/TP placement.

### T6 — `research/log.py` schema extension
Additive only. New optional fields on pre-registration events, becoming mandatory for entries
created after the migration marker:

| Field | Type | Purpose |
|---|---|---|
| `universe` | list[str] | Instruments the hypothesis is registered against |
| `selection_rule` | enum | `POOLED_ALL` \| `PRE_SPECIFIED_SUBSET` \| `POST_HOC_SELECTION` |
| `null_baseline_structure` | str | Declared before testing; e.g. `regime_filtered_random_entry` |
| `benchmark_sharpe` | float | SR* for the DSR evaluation, from D5 |
| `min_decidable_sharpe` | float | MinTRL-derived floor given the intended sample |
| `registry_snapshot` | str | `as_of` of the InstrumentSpec snapshot used |

**Trial accounting rule, enforced in code:**
- `POOLED_ALL` — one mechanism, one parameter set, all instruments, pooled result → **+1 trial**
- `PRE_SPECIFIED_SUBSET` — subset chosen by a rule declared before seeing results → **+1 trial**
- `POST_HOC_SELECTION` — best-of-N chosen after seeing results → **+N trials**

`trial_count()` must implement this arithmetic rather than counting rows. Per-instrument parameter
tuning is structurally prohibited: reject at pre-registration time with a clear error.

Migration is a single appended `SCHEMA_MIGRATION` event recording the old terminal hash, the new
field set, and an explicit statement that all prior entries have `universe: ["XAUUSD"]` and
`selection_rule: POOLED_ALL`. **Existing entries are not rewritten.** `verify()` must pass across
the migration boundary and `trial_count()` must return the D7 baseline value unchanged.

### T7 — `research/mintrl.py`
Minimum Track Record Length (Bailey & López de Prado), stdlib-only, mirroring `dsr.py`'s structure:

```
MinTRL = 1 + [1 − γ₃·SR + (γ₄−1)/4 · SR²] · (Z_α / (SR − SR*))²
```

Sibling implementation under `research/post/` with the same verified parity contract that exists
between `research.post.dsr` and `resources/metrics/deflated.py`. Exposed as a **pre-registration filter**:
given intended sample length and SR*, return the minimum Sharpe that is decidable. Hypotheses whose
plausible effect size falls below that floor are rejected before any compute is spent.

### T8 — DSR benchmark wiring
`research/dsr.py` currently evaluates against SR* = 0. Add `benchmark_sharpe` as a required
argument sourced from the pre-registration record. Log the SR* used in every
`log_dsr_evaluation()` call. Retrospectively note in the log — as a new entry, not an edit — that
prior gold DSR evaluations used SR* = 0 and were therefore lenient.

### T9 — Parity fixtures

Two legs, because the two halves of the harness produce different artifact types and neither
covers the other's failure modes. The `pre/` leg exercises data loading, indicators, mask and
normalisation. The `post/` leg exercises sizing, SL/TP placement, fills, equity accounting and the
walk-forward machinery. Phase 1 changes both, so both are pinned.

Both fixtures are re-runs of already-adjudicated mechanisms. They are logged as
`PARITY_FIXTURE` events and **must not increment `trial_count()`** — re-running a killed mechanism
as a migration test is not a new trial, and treating it as one would corrupt the DSR denominator.
Neither verdict is reopened by this work.

#### T9a — `pre/` path: `flood_tide_h1` E-Ratio artifact (seq=31)

Assertions in this order, so a failure localises to a layer rather than requiring a bisect:

1. `ohlc_hash` matches. If this fails, the data loader changed; stop and fix before looking at
   anything downstream.
2. `signal_hash` matches.
3. `n_long_signals == 1669`.
4. Signal timestamps match exactly, element-wise.
5. E-Ratios at h=20, 50, 100 match to float equality on serialised float64.

**Mask-off:** all five must hold exactly.

**Mask-on:** will differ, and the difference has two independent channels that must be reported
separately or the result is uninterpretable:

- *Signal-set channel* — signals gained and lost, each attributed to a named mask flag.
- *Normaliser channel* — E-Ratio normalises MFE/MAE by ATR, and the mask changes ATR across
  weekend and holiday boundaries. Recompute E-Ratio on the **intersection** of retained signals
  under old-ATR and new-ATR to isolate this from the signal-set change.

**Horizon semantics: tradable bars, per R4.** h=20 means twenty tradable bars, not twenty calendar
bars containing holes. Recorded explicitly in the artifact so a future reader does not have to
infer it.

#### T9b — `post/` path: `crest_n_keel` walk-forward artifact

Chosen over `zerolag_chandelier` because it exercises the widest slice of the stack: HMA,
Stochastic and ATR (all three D8-pinned indicators), the asymmetric ATR exit that carries the
`effective_atr` contract, multi-fold walk-forward, and DSR.

**Mask-off assertions:**
1. Fold boundaries identical.
2. Trade-for-trade: entry and exit timestamps, prices, direction, and volume.
3. Per-fold and aggregate Sharpe to float equality.
4. DSR reproduced **in legacy mode** — SR\* explicitly passed as 0.0, matching the original run.

Point 4 is load-bearing. T8 makes `benchmark_sharpe` required, so the corrected DSR will not match
the historical value **by design**. The SR\*-corrected number is computed and reported alongside,
as a finding about the original evaluation's leniency — not as a parity failure. Conflating the
two would make T8 and T9 contradict each other.

**Mask-on:** trades gained and lost, delta in per-fold and aggregate Sharpe, each difference
attributed to a named mask flag.

#### T9c — Sizer integration (conditional)

**Required if and only if `btpy_runner` uses `backtesting.py`'s native fractional-equity sizing
rather than routing through `calculate_lot_size`.** In that case no historical artifact is
sensitive to T5, and T11's unit-level golden fixtures cover the sizer's arithmetic but not its
integration with SL/TP placement.

If required: construct a synthetic fixture from the D8 sizer grid, asserting that
`size_position()` output flows into SL/TP placement such that realised risk equals calculated risk
for every cell — the `effective_atr` contract, tested end-to-end rather than at the function
boundary. Include the `granularity_flag` path and confirm it produces no order rather than a
clamped one.

**Resolve this during D6**, since the audit reads `btpy_runner` anyway.

### T10 — Namespace rename `qhf` → `quant_harness`

Now split across two phases, because the execution stack is no longer in the same repository.

**Research side — done in Phase 0.5, not here.** Package directory, imports, `pyproject.toml` /
`uv` project name, artifact path prefixes. Recorded as an appended `PROJECT_RENAME` event.

**Execution side — deferred to Phase 3 (§11).** Django app label and `INSTALLED_APPS`, settings
module path, Celery app name and task routing keys, Docker Compose service names, image tags,
container names, volume names, env-var prefixes. Carries three hazards worth writing down now so
they are not rediscovered under time pressure:

- Django app-label change requires a migration if any model table names derive from it. Check
  `db_table` on every model; if unset, tables are prefixed with the app label and a rename
  migration is mandatory. Verify against the running demo database before merging.
- Celery task names are string-keyed. Any task queued under the old name at cutover fails to
  route. Drain queues first, or register transitional aliases for one release.
- Beat schedule entries reference task paths as strings. Update them and confirm the disabled
  `asqs` entry stays disabled.

Explicitly **not** in scope, in either phase:
- **The append-only log is not rewritten.** Existing entries that reference `qhf.*` module paths in
  provenance, artifact-path or harness-version fields are historical facts about what actually ran.
  Rewriting them would break the hash chain and falsify the record. Readers resolve old paths
  through the `PROJECT_RENAME` event.
- Stored research artifacts and their embedded paths. Same reasoning.
- Historical git tags and commit messages.

### T11 — Ported-code parity

Every function ported from WMPS into `resources` must reproduce its D8 golden fixture exactly
(float equality on serialised float64, not `approx`). Applies to `wma`, `hma`, `stochastic`,
`atr`, `calculate_lot_size` and `DrawdownGuard`.

Where T5's signature change makes exact comparison impossible, provide a thin adapter that calls
the new signature with the old arguments and assert equality through it. The adapter is test-only
and is deleted at Phase 3.

Any intentional deviation requires a logged entry stating the old behaviour, the new behaviour,
the reason, and the effect on the T9 parity run.

### T12 — Broker port and `SimulatedBroker`

Define the broker interface in `resources` (§2.2) and implement `SimulatedBroker` with the four fill
configurations. `btpy_runner` gains a `fill_config` parameter; every backtest artifact records
which configuration produced it.

**Reporting requirement:** no backtest result is logged under a single fill assumption. Every run
emits the full four-configuration frontier alongside the cost-to-ATR ratio from D3. A mechanism
whose edge disappears between `NEXT_OPEN` and `REALISTIC` is reported as failed, not as
conditional.

---

## 7. Tests

| ID | Test | Assertion |
|---|---|---|
| X1 | Registry purity | No symbol string literal appears outside `instruments/`. AST-level check, not grep. |
| X2 | Registry offline | Importing `resources.instruments` with networking disabled succeeds. |
| X3 | Mask — weekend (WINDOW only) | A **WINDOW** indicator computed across a Friday-close/Monday-open boundary emits NaN for bars whose window spans the gap. Property-based over synthetic calendars. Narrowed per R3/X25: ACCUMULATOR indicators legitimately carry state across the gap and must *not* NaN, so applying this to them would fail a correct implementation. X25 covers the ACCUMULATOR case. |
| X4 | Panel — no fill | A masked bar returns NaN, never a forward-filled price. |
| X5 | Look-ahead (Chan test) | Truncate the last N bars, re-run, assert the surviving position series is identical to the untruncated run's prefix. Run for every strategy in the repo. |
| X6 | `iloc[-2]` discipline | Signal generation never reads the forming bar. Assert via a fixture whose final bar is corrupted; output must be unchanged. |
| X7 | Sizer — granularity | XAUUSD at $100 equity with a 2% budget and 1.5×ATR(H1) stop returns `lots=0` and `MIN_POSITION_EXCEEDS_RISK_BUDGET`. |
| X8 | Sizer — risk ceiling | Across a randomised sweep of instruments, balances and stops, realised risk never exceeds the budget. Property-based. |
| X9 | Sizer — FX conversion | USDJPY and USDCHF sizing matches an independently hand-computed reference to within one lot step. |
| X10 | Log — chain | `verify()` passes across the migration boundary; terminal hash chains from the D7 baseline. |
| X11 | Log — trial arithmetic | `POOLED_ALL` over 7 instruments increments by 1; `POST_HOC_SELECTION` over 7 increments by 7. |
| X12 | Log — prohibition | Pre-registering per-instrument parameters raises. |
| X13 | MinTRL parity | `research.post.mintrl` and `resources/metrics` agree to 1e-9 across a parameter sweep. |
| X14 | DSR benchmark | Omitting `benchmark_sharpe` raises rather than silently defaulting to 0. |
| X15a | Parity, `pre/` | T9a mask-off reproduces `ohlc_hash`, `signal_hash`, `n_long_signals=1669`, signal timestamps and E-Ratios at h=20/50/100 exactly. Assertions ordered so failure localises to a layer. |
| X15b | Parity, `post/` | T9b mask-off is trade-for-trade identical on timestamps, prices, direction and volume, with per-fold and aggregate Sharpe matching. |
| X15c | DSR legacy mode | T9b reproduces the historical DSR with SR*=0.0 explicitly passed; the SR*-corrected value is recorded separately and does not fail the test. |
| X15d | Parity fixtures are not trials | Running T9a and T9b leaves `trial_count()` unchanged. |
| X16 | Rename completeness | No `qhf` identifier survives in code, config, Compose files or env-var names. Excludes `research/log/`, `research/artifacts/` and git history, which are intentionally preserved. |
| X17 | Rename is behaviour-neutral | The T10 commit, run against the parity fixture, produces output identical to its parent commit. |
| X18 | Log preserved across rename | `verify()` passes and `trial_count()` is unchanged after the `PROJECT_RENAME` event is appended. |
| X19 | Import direction | AST-level, over the ruled graph `resources <- strategies <- {research, platform}`: `resources` imports none of the other three; `strategies` imports only `resources`; `research` and `platform` never import each other. Fails the build, not a warning. |
| X20 | `resources` standalone | `resources` imports and its full suite passes with no Django settings module, no `DJANGO_SETTINGS_MODULE`, no database, and networking disabled. |
| X21 | Log append-only | CI rejects any commit that modifies or deletes an existing line in the JSONL chain. Additions only. |
| X22 | Ported-code parity | Every D8 golden fixture reproduces exactly. Float equality on serialised float64, not `approx`. |
| X23 | Fill frontier completeness | No backtest artifact is written with fewer than all four `SimulatedBroker` fill configurations recorded. |
| X24 | Registry provenance | `Registry.load()` raises on a `HAND_ENTERED` snapshot without `allow_provisional=True`; artifacts produced under one are stamped `PROVISIONAL_SPECS`. |
| X25 | Indicator mask class | Every indicator declares `WINDOW` or `ACCUMULATOR` at definition; an undeclared indicator fails to register. `masked_rolling` applies NaN or skip-with-index accordingly. |
| X26 | Account risk policy | Position sizing consults a single account-level risk-policy object; no strategy module may set its own `RISK_PCT`. A strategy overriding the account policy fails the test. Motivated by h1_momentum running 5% against a 2% default (§8). |
| X27 | DrawdownGuard precondition | A strategy cannot be registered as live-eligible without a DrawdownGuard wired. Absence is a registration failure, not a warning. The only strategy on the schedule was the only one with no guard; nothing detected that. |
| X28 | Realised risk never exceeds budget | For every (balance, ATR, risk_pct, stop) cell, either the sizer returns 0 lots or `lots x contract_size x stop_distance <= balance x risk_pct`. Run over the full D8 grid against `resources.risk.size_position`. |
| X29 | Schedule from registry | The Celery beat schedule is generated from `strategies/registry.py`, not hand-maintained. A strategy whose registry verdict is KILLED or SHELVED cannot appear in a generated schedule. Supports a `SHADOW` state that evaluates and logs without ordering. Motivated by a KILLED strategy (seq=65) reaching the live path with nothing connecting verdict to scheduler. |
| X30 | Entry vs position management | Entry evaluation and position management are separately addressable: disabling entries must not disable management of an open position. Retiring a strategy whose `evaluate()` also drove trailing/breakeven/partial-close would otherwise strand live positions unmanaged. |
| X31 | MinTRL moments | Skew and kurtosis are measured from the return series under evaluation by default. Passing literal moments requires an explicit override flag, and the flag is stamped into both the artifact and the log entry. Omitting it where literals are used raises. |
| X32 | Stdlib shadowing | From a clean interpreter with `qh-platform` installed, `import platform` resolves to the stdlib module, and `qh-platform`'s own modules can still reach it. A top-level package named `platform` shadows the stdlib; the failure is silent and surfaces far from its cause, so it is tested rather than trusted. |

---

**On X28.** The §8 ruling named X26, X27 and X28 together but described only the first two. The
gap was held open rather than filled with something plausible, then filled with a proposal, then
**ruled and adopted**.

It covers the one risk failure X26 and X27 leave open. X26 makes the *intended* risk
single-sourced; X27 makes the drawdown guard mandatory. Neither catches intended-correct,
**realised**-wrong — which is the actual D8 finding: once lots pin at `volume_min` the clamp stops
bounding risk, and 125 of 480 grid cells (26%) breach their own budget, worst case 600% of
account. That is what put `h1_momentum` on a live schedule, and nothing in X26 or X27 would have
caught it.

The property has one honest form: **either the sizer refuses, or realised risk ≤ budget.**
Refusal has to be a permitted outcome — a sizer that must always return a tradeable lot cannot
express "not at this equity" and will return the minimum instead, which is the bug itself.

---

## 8. Risk-parameter reconciliation

The trading profile states 5% risk per trade and 10% max drawdown. These are mutually infeasible:
two consecutive losses breach the cap, and a four-loss streak is routine for a trend system with a
sub-50% hit rate. The code runs 2% risk and an 8% `DrawdownGuard`. The code is correct; the profile
is stale. Update the profile to 2% / 8% as part of Phase 1 and record the correction.

Separately: with `granularity_flag` implemented (T5), XAUUSD becomes untradeable at $100 under a 2%
budget on H1 stops. This is the correct outcome and should not be worked around by raising the risk
percentage.

---

## 9. Acceptance criteria — Phase 1

Binary. All must hold.

1. `verify()` passes on the migrated log; `trial_count()` equals the D7 baseline.
2. T9a and T9b mask-off parity both hold exactly, against the `flood_tide_h1` E-Ratio artifact and
   the `crest_n_keel` walk-forward artifact respectively.
3. T9 mask-on divergence is fully attributed. For T9a the signal-set and ATR-normaliser channels
   are reported separately; for T9b every differing trade is traced to a named mask flag.
4. X1–X32 pass in CI (X15 counted as X15a–d).
5. A single strategy module runs unmodified against all seven majors and against XAUUSD, producing
   per-instrument results, with no symbol-specific branching anywhere in the call path.
6. `docs/hardcoded_audit.md` has every row marked resolved or explicitly deferred with a reason.
7. No new strategy hypothesis has been pre-registered during the phase.
8. Every D8 golden fixture reproduces exactly through `resources`, or the deviation is logged with
   a stated reason (T11).
9. `SimulatedBroker` produces the full four-configuration fill frontier for the T9 fixture, and
   the cost-to-ATR ratio from D3 is recorded alongside it.
10. WMPS is unchanged apart from mirrored bug fixes, and the demo account has traded no new
    strategy during the phase.

---

## 10. Decisions

### 10.1 Ruled

Each ruling carries a **basis**.

**`PRE_DATA`** — ruled before the relevant numbers existed. These are methodological choices, not
empirical questions, and they were ruled early precisely because seeing the numbers first would
let the answer be chosen for how it looks. R1–R5 are all PRE_DATA, and that is a clean break:
every ruling after R5 was issued after its data landed.

**`POST_DATA`** — ruled in response to a measurement. These are not guarded by construction, so
each one states two things that a PRE_DATA ruling does not need:

- **`rejected_alternative`** — what else was on the table. A ruling with no stated alternative is
  a description of what happened, not a choice.
- **`selection_guard`** — why this ruling was not selected for how it looked. The strongest form
  is a ruling that went against its own interest; the next is one that foreclosed fewer future
  options than the alternative.

This annotation was added on 2026-10-05 after R6, R7 and R8 were found to be sitting in a
sequence whose own definition — "made before data" — they all failed. The numbers stay as they
are: seq=89, 91, 107 and 110 already cite R7 and R8, the log is append-only, and renumbering
would need a mapping event to keep those citations readable. That is more machinery than the
problem warrants.

A **measurement** is not a ruling and does not get an R number. Findings live in §10.4.

**R1 — Sequencing.** `basis: PRE_DATA` New `quant_harness` repository built first; WMPS merged as `platform` at
Phase 3, frozen to bug-fix-only meanwhile (§1.3). Residual risk — two implementations of the same
numerical code coexisting — is controlled by D8 golden fixtures, T11 parity and the freeze rule.
An unmirrored WMPS change is a spec violation, not an inconvenience.

**R2 — Rename timing.** `basis: PRE_DATA` Research-side rename in Phase 0.5, before any module is written, so nothing
is born in the old namespace. Execution-side rename moves to Phase 3.

**R3 — Mask policy: window indicators NaN, accumulator indicators skip-with-index.** `basis: PRE_DATA`

Two classes, not one policy:

- *Window indicators* (ATR, Donchian, HMA, Stochastic, any fixed-lookback): **NaN-out masked bars,
  do not drop them.** Dropping silently changes the wall-clock span of every lookback, and
  different indicators would then disagree about what "55 bars ago" means. NaN preserves the
  calendar and makes contamination visible instead of silent. Cost: longer warm-up and some bars
  produce no signal — which is correct, since those bars were untradable anyway.
- *Accumulator indicators* (AVWAP, any running sum from an anchor): **skip masked bars in the
  accumulation while keeping the calendar index.** A NaN inside a cumulative sum poisons every
  subsequent value, so NaN-out is not available here.

The distinction is structural, not per-indicator taste. Any new indicator is classified into one
of the two at the point it is written.

**R4 — E-Ratio horizon counts tradable bars, not calendar bars.** `basis: PRE_DATA`

E-Ratio measures what a trade would have experienced. Over a weekend you could not have exited, so
the gap is not a period during which MFE or MAE meaningfully accrued. Counting calendar bars with
holes makes h=20 represent different amounts of real market exposure depending on where in the week
the signal fired, injecting a day-of-week artifact into the statistic. Tradable-bar counting
removes it.

Consequence: mask-on E-Ratios will differ from the original `flood_tide_h1` run. That is expected
and is exactly what T9a's normaliser channel measures.

**R5 — Phase 2b gate.** `basis: PRE_DATA` — **re-scoped 2026-10-05, not dropped.**

Phase 2 runs on FX majors alone, because its acceptance is *harness validation* via re-running an
already-falsified mechanism, which does not need breadth. Phase 2b expansion must complete
**before any new mechanism is pre-registered**. The line is between validating the machine and
making a claim with it, and that line stands.

R5 originally rested on two arguments. F1 refutes one and leaves the other untouched.

- **The breadth argument is dead.** It read "seven majors deliver roughly two effective bets",
  implying some larger instrument count would reach the target. At the measured mean |ρ| of
  0.44–0.62, no instrument count reaches eff_N ≥ 4 (F1). A gate whose criterion cannot be
  satisfied by any amount of the work it gates is not a gate.
- **The mechanism-generality argument is untouched**, and was always the stronger one. A
  mechanism that holds with identical parameters across different *market structures* is general.
  One that holds only across nine USD-legged pairs may be a USD artifact. This was never a
  function of effective N.

So the gate keeps its purpose and replaces its numeric target with a structural one:

> **The research universe must span at least three distinct market structures** — FX, metals, and
> indices or energy — before any new mechanism is pre-registered.

That is what eff_N ≥ 4 was a proxy for. The structural criterion measures it directly, rather than
through a coefficient that cannot reach the required value.

**Decidability moves out of this rule.** Whether a result is decidable is set by the measured
`min_decidable_sharpe` from the power sweep (seq=107), not by breadth arithmetic. Conflating the
two is what let a breadth target stand in for a power question it could not answer.

**R6 — `h1_momentum` is halted at the beat schedule.** `basis: POST_DATA`

Ruled and actioned 2026-08-31; `LIVE_RISK_HALT` at log seq=82. A mechanism carrying
`verdict=killed` from two separate entries (seq=65, seq=81) was on the live beat schedule and
fired. seq=81 had already recorded `untradeable_at_100usd=1` — the log contained the number that
should have blocked it. Issued after D6 measured the risk configuration it was running under,
which is what makes it POST_DATA.

- `rejected_alternative` — leave it running on demo for forward data under the existing risk
  configuration. The forward-data rationale is defensible in itself: forward data is the only
  evidence uncontaminated by selection. What was not defensible was the configuration.
- `selection_guard` — halting foreclosed fewer future choices than continuing. A halt can be
  reversed once the configuration is fixed; the trades taken under a bad configuration cannot be
  untaken, and they would have contaminated the forward record the alternative was meant to build.

**R7 — the cost gate uses the entry-conditional spread estimator.** `basis: POST_DATA`

Resolved at seq=91. D3a ran dual schedules for nine symbols: periodic 60s (time-weighted) and
bar-boundary at H1/M15 close + 750 ms (entry-conditional). The two agree to the tick at p50, p75
and p90 on every symbol. The D3b tick-weighted census disagrees by roughly 10x, because ticks
burst precisely when the book is active and the spread is momentarily zero — it measures the
spread when the market is busiest, not when an entry actually fires.

- `rejected_alternative` — the tick-weighted census (448,777,747 spreads, ~11.9 months), by far
  the larger sample.
- `selection_guard` — **this ruling went against its own interest.** Entry-conditional and
  time-weighted spreads push cost above the O1 veto line; tick-weighted does not. Adopting the
  estimator that makes the project's own instruments look *more* expensive, and rejecting the one
  with 400x the sample that made them look cheaper, is evidence the choice was not made for how
  it looked.

**R8 — the breadth target is replaced by a decidability gate.** `basis: POST_DATA`

F1 (§10.4) establishes that eff_N ≥ 4 is unreachable. R8 is the ruling made in response: a result
is decidable when it clears the measured `min_decidable_sharpe` from the power sweep, not when a
breadth coefficient reaches a value it cannot reach. R5's gate is re-scoped structurally rather
than numerically; decidability is a power question and now lives with the power measurement.

- `rejected_alternative` — keep eff_N ≥ 4 and expand the universe until it is reached. Rejected
  because F1 shows no instrument count satisfies it.
- `selection_guard` — **the replacement gate is stricter in practice than the one it removed.**
  eff_N ≥ 4 was unreachable, so it blocked everything by being unsatisfiable — a gate that never
  opens also never has to be argued with. The decidability gate is reachable in principle and
  still blocks every current candidate: measured OOS Sharpes of 0.27–0.41 against a floor of 1.2
  (seq=107). Swapping an unreachable criterion for a reachable one that the project's own
  mechanisms fail does not clear a path anyone wanted cleared, and it converts a permanent excuse
  into a target that can be missed on the record. Recorded 2026-10-05; it was not stated when the
  ruling was made, which is the defect the basis annotation exists to prevent recurring.

**R9 — the H4 prior is withdrawn; the prior is H1, and the cost measurement becomes a veto.**
`basis: POST_DATA`

Ruled 2026-08-31 in `phase0_memo.md` §3.1, and unnumbered until the 2026-10-05 sweep. D2 showed
granularity argues H1 unambiguously, flipping one of the prior's three legs. The other two —
cost-to-ATR and fewer scheduled evaluations — still favoured H4, and D3 was blocked.

The ruling's substance is that the two legs do not conflict symmetrically. **Granularity is a hard
constraint**: below the threshold the trade cannot be placed within budget at all. **Cost is
soft**: it degrades edge continuously. Hard dominates soft, so D3 stops being the decider and
becomes a veto. And because H4 was already dead on granularity, a veto does not redirect the
search to another timeframe — the finding would be that $100 cannot trade this system at any
timeframe.

- `rejected_alternative` — keep the H4 prior standing until D3 unblocked and let the cost
  measurement decide between them, which is what O1 as written called for.
- `selection_guard` — **the veto thresholds were declared before the measurement existed**:
  < 5% of 1×ATR(H1) proceeds, 5–10% marginal, > 10% vetoes H1. The part of this ruling that could
  have been outcome-selected is the part that was pinned in advance, which is the PRE_DATA
  discipline applied to exactly the leg that needed it.

**R9 corrects the record for O1.** seq=106 and seq=108 state `declared_prior: H4` and
`prior_overturned_by: data`. That is wrong: R9 withdrew the H4 prior on 2026-08-31, eleven days
before D3 landed. O1's closure confirmed a prior that had already been ruled; it did not overturn
one. The log is append-only, so the correction is recorded rather than edited — see seq=112.

**R11 — Phase 3 accepts on an enumerated deviation set, not on identity.** `basis: POST_DATA`

§11 writes Phase 3's acceptance as "live strategy signals through `resources` are identical to the
pre-merge signals". F3 shows that is unachievable: the `fsum`/`np.dot` reduction flips a
signal-driving comparison about once in 27,000 bars. An acceptance criterion that cannot be met is
worse than a loose one, because it gets quietly reinterpreted during the cutover rather than
argued with beforehand.

Phase 3's acceptance becomes: **the deviation set is enumerated in advance; every member is
attributed to the `fsum`/`np.dot` reduction; and no member falls on a bar where a live strategy
would have acted.** The third clause decides whether the merge is behaviour-neutral in practice,
and it needs the strategy logic rather than the indicators alone.

- `rejected_alternative` — revert `resources` to `np.dot` so the two agree bit-for-bit. Rejected
  because seq=102 already rejected it, for a reason recorded before this measurement existed: the
  BLAS kernel's summation order is a property of the running CPU, so a reference built on it
  drifts on its own machine across numpy versions. Bit-identity with WMPS would be bought with
  platform non-determinism, which is the worse trade.
- `selection_guard` — **this ruling makes the merge harder, not easier.** "Identical" is a
  criterion nobody can fail, because any difference found during a cutover gets explained away as
  noise. Replacing it with an enumerated set adds an obligation that did not exist: the deviations
  must be listed before the merge and each attributed. It also adds a third clause that is not yet
  measured and may block Phase 3 outright if a flip lands on a bar a deployed strategy traded.

**Note on R6–R11.** All of them were issued after their data landed, into a section whose
definition was "made before data". That was an error in categorisation, not in the rulings
themselves — each survives being restated with its basis and guard. The annotation exists so the
next post-data ruling has to show its guard at the point it is written, rather than being audited
into one later.

**R10 — the third market structure is equity indices, entering as US500.** `basis: POST_DATA`

R5-as-amended requires the research universe to span at least three distinct market structures.
FX and metals are present. This ruling names the third and states its reason before the research
data is pulled.

**Indices, not energy, and the reason is structural rather than statistical.** FX and metals as
held here are both USD-legged, spot, and flat 24h Monday to Friday — metals are commodity-like in
their drivers but FX-like in their *structure*, so they stretch the universe less than their
label suggests. The third structure should break that frame, and the two candidates break
different parts of it:

- **Energy** breaks the spot frame: term structure, inventory cycles, roll. But a CFD rolls
  contracts, and a roll produces a price discontinuity that is not a market move. This repo has no
  machinery to distinguish one from the other, and its entire history is about not mistaking an
  artifact for a finding. Energy would introduce a contamination channel rather than a test.
- **Indices** break the calendar frame: an equity index observes an exchange holiday calendar that
  FX ignores. Its untradable periods follow a *different* calendar rather than the same weekend,
  which is precisely what R3's mask policy and R4's tradable-bar horizon were built for and have
  never been exercised against. A gap in an index is a real price move, not a bookkeeping
  artifact.

So indices test the harness on the axis it was designed for, and energy would test it on an axis
where it cannot tell signal from artifact.

- `rejected_alternative` — energy (WTI or Brent), rejected on the roll-contamination argument
  above, not on any measured property. No energy series exists in the repo, so the alternative was
  rejected on reasoning rather than on numbers that favoured indices.
- `selection_guard` — **the calendar structure of US500 was measured before this ruling was
  written, and the measurement is orthogonal to the outcome the ruling could be selected for.**
  What was measured: bars per week, trading-day counts, gap-to-ATR distribution, and the share of
  partial trading days (US500 21.3% of days under 20 bars, against EURUSD 0.7% and XAUUSD 2.1%).
  None of that is a return, an edge, or a Sharpe. Knowing an instrument keeps an exchange holiday
  calendar says nothing about whether a mechanism will work on it, so the choice could not have
  been made for how the result would look. Stated here because the ordering — measure, then
  declare — is the ordering this scheme exists to make visible rather than hide.

**Not yet satisfiable.** The pinned registry snapshot holds nine instruments, all FX and metals;
no index is in it. CLAUDE.md is explicit that `filling_mode` is broker policy and must not be
taken on trust for a new symbol. US500 therefore needs a registry snapshot refresh — an
MT5-dependent action — before it can enter the universe, even though its H1 history is already
present. Phase 2b cannot start on the structural criterion until that snapshot exists.

### 10.2 Open — genuinely data-dependent

**O1 — Timeframe for the first panel research run: H1 or H4.**

Decided from D2 (granularity) and D3 (cost-to-ATR), and brought back with the numbers attached.
**Not a Phase 1 blocker** — `resources` and the panel harness are timeframe-agnostic; this binds only
the first Phase 2 research run.

Declared prior, to be overturned only by data: **H4.** Larger stop distances improve lot
granularity at $100; lower cost-to-ATR ratio; fewer overlapping windows; fewer scheduled
evaluations, which suits the day-job constraint. If D3 remains blocked when Phase 2 begins, H4
stands by default and the reason is recorded rather than left implicit.

### 10.3 Reclassified — not a decision

**Does `btpy_runner` route sizing through `calculate_lot_size`?** This is a fact about existing
code, resolved by reading it. Moved to a D6 required output. Its consequence is mechanical: if
sizing is `backtesting.py` native, T9c becomes mandatory.

---

### 10.4 Findings — measurements, not decisions

A finding is a measurement plus arithmetic, with no judgment in it. It carries an F number, not an
R number, because nothing was chosen. Findings constrain rulings; they are not rulings.

This section exists because R8 was originally two things fused together — a measurement and a
ruling made in response to it — and that fusion is part of why the category slipped. Once they are
separated, the measurement needs no guard (nothing was selected) and the ruling needs one.

**F1 — eff_N ≥ 4 is unreachable at the measured correlations.** Mean |ρ| across the candidate
universe is 0.44–0.62 (D4). At that level of dependence, no instrument count drives effective N to
4: adding correlated instruments adds progressively less independent information, and the ceiling
sits below the target. Measurement plus arithmetic, no judgment.

Consequences: R5's breadth argument is refuted and the gate is re-scoped structurally (§10.1);
R8 replaces the breadth target with a decidability gate.

**F2 — breadth does not move the detection floor.** Logged at seq=110. The floor is 1.2
annualised at both the current effective breadth (n=2,000 pooled, 17 folds) and Phase 2b's target
(n=3,500). With one fold standing for one year, the t-statistic is `SR_annualised × √years`, which
does not depend on how many observations fill those years — and breadth adds observations within
the same calendar span. Span buys detection power; sampling density does not.

The companion arithmetic, stated separately because it is not what the simulation measured:
pooling raises the pooled effect roughly as `SR_pooled ≈ SR_instrument × √N_eff`, so lifting a
measured 0.3 per-instrument edge above a 1.2 floor needs N_eff ≈ 16. Both halves point the same
way. The simulation treats pooled observations as independent, so its no-gain result is an upper
bound on what breadth buys; correlated instruments do worse.
**F3 — the deterministic reduction flips signal comparisons at about 1 bar in 27,000.**
Logged at seq=113. `resources` reproduces the D8 fixtures exactly (X22, string equality, no
tolerance), but five columns — `wma_9`, `wma_20`, `wma_55`, `hma_21`, `hma_55` — deliberately
differ from the live WMPS code, because `resources` reduces with `math.fsum` where WMPS uses
`np.dot`. That change was made at seq=102, after numpy moved underneath the fixture and BLAS
summation order made the reference drift on its own machine. The gap is 2–5 ULP against a 16 ULP
guard.

A ULP-level difference in a *value* is not automatically a difference in a *signal*, so the
comparisons that drive entries were counted directly — indicator slope, and price-vs-indicator
cross: XAUUSD 5 flips in 124,887 bars, EURUSD 1 in 80,000, GBPUSD 3 in 80,000, US500 4 in 62,726.
Thirteen in 347,613. Up to 44% of bars carry a differing indicator value; almost all are absorbed
by the comparison and a handful are not. The flips concentrate in `wma_20` and `wma_55`;
`hma_21` and `hma_55` produced none despite the largest raw differences, consistent with hma's
extra smoothing stage absorbing the reduction error rather than straddling thresholds with it.

Consequence: Phase 3 cannot accept on "identical" (R11).
**F4 — the deviation flips no deployed-strategy signal.** Logged at seq=114. Phase 3's gate,
measured before any merge work. `asqs` reads only `atr` from the shared indicators; `atr` and
`stochastic` show zero differing bars across four instruments with NaN shapes matching, so `asqs`
is unaffected by measurement rather than by argument. `crest_n_keel` reads `hma(close, 55)` in both
its slope and cross conditions and so sits directly in the deviating path — its live signal logic
run over 124,887 XAUUSD H1 bars produces 227 signals under each implementation and **zero**
differences.

The reason is in F3's own shape: the flips concentrate in `wma_20` and `wma_55`, and `hma`
produced none anywhere despite the largest raw differences. The deviating indicators that flip
comparisons are not the ones any deployed strategy reads. Narrow, not general: a future strategy
reading `wma` directly needs this measured again.



---

## 11. Downstream phases (sketched, not specified)

Recorded here so Phase 1 decisions don't foreclose them. Each gets its own spec when reached.

**Phase 2 — Panel harness.** `signal_edge` extended to run per-instrument across the FX majors
with a pooled significance test against a regime-filtered null, per-instrument attribution, and
pooled DSR/MinTRL against the D5 benchmark. Acceptance is re-running an already-falsified
mechanism across the panel: if `flood_tide_h1` is dead everywhere, the harness is validated and
the verdict is confirmed in one run.

**Phase 2b — Universe expansion.** Add non-USD-legged crosses, metals and indices to reach
effective N ≳ 3.5, per the D4 measurement. Re-evaluate the shelved XAUUSD mechanisms against the
correct SR\* for the first time.

**Phase 3 — Execution merge.** `git subtree add` WMPS into `packages/qh-platform/` and
`services/`, preserving history. Refactor the Django strategies to import indicators, sizer and
drawdown guard from `resources`, then delete the duplicated modules. Adapt `MT5APIClient` to the
broker port and verify by replaying recorded live orders through both the old client and the port.
Complete the execution-side namespace rename (T10). Acceptance: live strategy signals through
`resources` are identical to the pre-merge signals on the D8 fixtures, and the demo stack runs a full
week unattended with no behavioural change.

**Phase 4 — Multi-symbol live.** Portfolio-level inverse-volatility weighting, correlation cap,
account-level drawdown guard, multi-symbol Celery scheduling, and the granularity flag enforced in
the live path. Not entered until a mechanism survives Phase 2b.

**Phase 5 — Gated, optional.** CPCV, purging, sample uniqueness weighting. Entered only if a
surviving mechanism requires per-fold parameter fitting on cross-asset features. Until then these
remain non-goals (§3), not backlog.
