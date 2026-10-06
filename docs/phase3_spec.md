# Phase 3 — Execution merge

`REWRITE.md` §11 sketches Phase 3 and says each downstream phase gets its own spec when reached.
This is that spec.

**Status:** not started. Unblocked — Phase 3 carries no gate on Phase 2b (only Phase 4 does), and
Phase 2b is itself blocked on a registry snapshot.

**Authority:** `REWRITE.md` remains the authority on what is built. Where this document and §11
disagree, the disagreement is recorded here with its reason, and R11 is the ruling that makes it.

---

## 1. What Phase 3 does

Merge the live trading platform (WMPS) into this repository and make it consume `resources`
instead of its own copies of the same arithmetic.

| Step | Detail |
|---|---|
| Subtree merge | `git subtree add` WMPS into `packages/qh-platform/` and `services/`, preserving history |
| De-duplicate | Django strategies import indicators, sizer and drawdown guard from `resources`; the WMPS copies are deleted |
| Broker port | Adapt `MT5APIClient` to the `resources.execution.broker` port, verified by replaying recorded live orders through both |
| Rename | Complete the execution-side namespace rename (T10) |
| Freeze lifts | R1 freezes WMPS to bug-fix-only *until* Phase 3. Phase 3 is where that ends |

### What is being de-duplicated

Measured 2026-10-05.

| WMPS module | Lines | Replaced by | Lines |
|---|---|---|---|
| `quant/strategies/indicators.py` | 101 | `resources/indicators/` (3 modules) | 219 |
| `quant/strategies/sizer.py` | 97 | `resources/risk/sizer.py` | 188 |
| `quant/strategies/drawdown_guard.py` | 129 | `resources/risk/drawdown_guard.py` | 118 |

`indicators.py` exports `wma`, `hma`, `stochastic`, `atr`. Three strategies import from these
modules: `crest_n_keel`, `asqs`, `h1_momentum`.

---

## 2. The known deviation — read this before planning the cutover

**§11's acceptance criterion cannot be met as written.** It asks for live strategy signals through
`resources` to be *identical* to pre-merge signals. They are not, and the difference is
deliberate.

`resources` reproduces the D8 golden fixtures **exactly** — X22 compares string equality on the
shortest round-trip float64 repr, with no tolerance. But five fixture columns (`wma_9`, `wma_20`,
`wma_55`, `hma_21`, `hma_55`) differ from the **live WMPS code**, because `resources` reduces with
`math.fsum` where WMPS still uses `np.dot`. The change was made at seq=102, after numpy moved
underneath the fixture and BLAS summation order made the reference drift on its own machine. The
gap is 2–5 ULP against a 16 ULP guard.

A ULP-level difference in a value is not automatically a difference in a signal, so F1's style of
reasoning was applied directly: count the comparisons that drive entries.

| Instrument | Bars | Signal-comparison flips |
|---|---|---|
| XAUUSD H1 | 124,887 | 5 |
| EURUSD H1 | 80,000 | 1 |
| GBPUSD H1 | 80,000 | 3 |
| US500 H1 | 62,726 | 4 |
| **Total** | **347,613** | **13** — about 1 in 27,000 |

Up to 44% of bars carry a differing indicator *value*. Almost all are absorbed by the comparison;
a handful are not. The flips concentrate in `wma_20` and `wma_55`. `hma_21` and `hma_55` produced
none despite the largest raw differences, consistent with hma's extra smoothing stage absorbing
the reduction error rather than straddling thresholds with it.

Recorded as **F3** (seq=113). The ruling in response is **R11**.

### 2.1 The gate — measured, and it passes

Criterion 1's third clause was the only one that could refuse the phase, so it was measured before
any merge work.

**Exposure.** `asqs` imports only `atr` from the shared indicators. `crest_n_keel` imports `hma`,
`stochastic` and `atr`, and uses `hma(close, 55)` in *both* of its signal conditions — slope
(`hma_cur > hma_prev`) and cross (`close_cur > hma_cur`) — so it sits directly in the deviating
path. `h1_momentum` is halted under R6.

**`atr` and `stochastic` are clean.** Zero differing bars for `atr_14`, `atr_50`, `%K` and `%D`
across XAUUSD, EURUSD, GBPUSD and US500, with NaN shapes matching exactly. `asqs` is therefore
unaffected by measurement, not by argument from X22's column list.

**The gate.** `crest_n_keel`'s live signal logic was reimplemented against both indicator sets and
run over the full XAUUSD H1 history, with its live parameters (hma 55, stoch 14/3/3, atr 14) and
its live bar convention (current = `iloc[-2]`, previous = `iloc[-3]`).

| | |
|---|---|
| Bars evaluated | 124,887 |
| BUY/SELL signals via `resources` | 227 |
| BUY/SELL signals via WMPS | 227 |
| **Signal differences** | **0** |

**Why it passes despite F3.** The F3 flips concentrate in `wma_20` and `wma_55`. `hma_21` and
`hma_55` produced none on any instrument tested, despite carrying the largest raw ULP differences —
consistent with hma's extra smoothing stage absorbing the reduction error rather than straddling
thresholds with it. The deviating indicators that *do* flip comparisons are not the ones any
deployed strategy reads.

That is a narrow result, not a general one. It holds for the strategies deployed today on the
instrument they run on. A future strategy reading `wma` directly would need this measured again.

---

### 2.2 What the merge actually did, and what it surfaced

Merged 2026-10-06 as `6971806`, parents `531d3b2` and `27f94d8`. Restore path:
`531d3b28ab810720c9e1d61f2715afd6b1a4eb86`.

**WMPS's `research/` tree did not come across.** It held 145 files including a copy of
`entries.jsonl` frozen at seq=85 — the D9 migration entry. Verified to be an exact truncated
prefix of the live chain, so no fork; but a 29-entry-stale duplicate of the project's source of
truth sitting in-tree is something a reader greps and believes. Phase 3 merges the *platform*; the
research tree was superseded by the rewrite, which is R1's whole sequencing argument. Removed in
the same branch; the tree now holds exactly one `entries.jsonl`.

**`git subtree add` cannot target two prefixes.** §1 said `packages/qh-platform/` *and*
`services/`. One subtree add into `packages/qh-platform/`, then a normal `git mv` of
`docker-compose.yml` into `services/`.

**Collection aborted on the first run.** The merged Django suite took the *whole* test run down
with `ModuleNotFoundError: No module named 'django'` — zero tests, not one failure. That reads as
broken code rather than a suite that belongs elsewhere. Criterion 4 now covers it.

**X16 found eight live references, and they are not strings.** See R12.

---

### 2.3 Why step 4 is three different problems

Surveyed 2026-10-06 before executing. The three modules share one blocker and then diverge.

| Module | WMPS | `resources` | Kind of change |
|---|---|---|---|
| `indicators` | `wma`, `hma`, `stochastic`, `atr` | identical signatures | **drop-in**, once packaged |
| `drawdown_guard` | `PeakStore`, **`JsonPeakStore`**, `DrawdownGuard` | `PeakStore`, **`InMemoryPeakStore`**, `DrawdownGuard` | **feature gap** |
| `sizer` | `calculate_lot_size()`, XAUUSD-hardcoded | `size_position()` → `PositionSize`, `InstrumentSpec`-driven | **API rewrite** |

**`drawdown_guard` is the dangerous one.** `resources` has no `JsonPeakStore`, and its
`InMemoryPeakStore` docstring says plainly: *"Non-persistent store. The correct default for a
backtest."* The live strategies persist peak equity to JSON files under the platform's state
directory (the pre-rename path named in R12), with atomic `os.replace` writes. Swapping in the `resources` version replaces a persistent store with an
in-memory one, so peak equity resets on every Celery task run and the **10% maximum-drawdown guard
effectively never fires**.

That is R12's hazard in a second costume: a change that reads as de-duplication and silently
disables a risk control. `resources` needs a persistent store before this module is touched.

**`sizer` changes live position sizing.** Different name, arguments and return type, and
symbol-agnostic where the live one is XAUUSD-hardcoded. It is the only module here that can change
how much money a real order risks, which is why it goes last.

---

---

## 3. Acceptance criteria

Binary. All must hold. Criterion 1 replaces §11's "identical" clause per R11.

1. **The deviation set is enumerated before the merge**, every member is attributed to the
   `fsum`/`np.dot` reduction, and **no member falls on a bar where a live strategy would have
   acted.** ✅ **Measured 2026-10-06 — passes (F4, seq=114).** See §2.1.
2. WMPS history is preserved through the subtree merge — the source commit is an ancestor of
   `HEAD` and all its commits are reachable. ✅ **Met: 228 commits, back to 2024-11-15.**

   > **Corrected 2026-10-06.** This criterion originally read "`git log --follow` reaches
   > pre-merge commits for every moved file". That is not how `git subtree add` preserves
   > history: it grafts the source as a second parent with files at their *original* paths and
   > records no rename, so `--follow` has nothing to bridge and returns zero. The history is
   > fully present — `git log <source-sha> -- backend/...` finds it. The criterion described a
   > mechanism subtree does not use. Corrected rather than ruled on: there was no choice between
   > options here, only a false statement about how git works.
3. The three duplicated modules are deleted, not merely bypassed, and no import path reaches them.
4. The platform's Django suite is not collected by this repository's `pytest`. It needs Django, a
   Postgres test database and the `trading` container. ✅ **Met** — excluded via `norecursedirs`
   in `pyproject.toml`, with the reason recorded there.
5. `MT5APIClient` satisfies the `resources.execution.broker` port, verified by replaying recorded
   live orders through both the old client and the port with identical resulting order parameters.
   ◐ **Partly met 2026-10-07.** The port is satisfied and every strategy order path replays
   identically; the replay over real recorded orders has not run — see §5 step 5.
6. The execution-side T10 rename is complete; no pre-rename namespace identifiers remain
   anywhere the X16 guard scans. ✅ **Met 2026-10-07**, after widening what X16 scans to
   include Dockerfiles and shell scripts — a criterion defined by a guard is only as good as the
   guard's coverage.
7. The demo stack runs a full week unattended with no behavioural change.
8. `trial_count()` is unchanged by the merge. Phase 3 is engineering; it registers no hypothesis.

---

## 4. Risks specific to this phase

**Two of the three affected strategies are deployed.** `asqs` and `crest_n_keel` both carry
`verdict=deployed` in the log. `h1_momentum` is halted under R6 and must stay halted — the merge
must not quietly restore it to the beat schedule, and criterion 3's import-path check is the
mechanical guard.

**The freeze lifts at exactly the moment the code is most disturbed.** R1 holds WMPS to bug-fix-only
precisely so that D8 fixtures and T11 parity stay meaningful. Phase 3 ends that protection while
simultaneously replacing the arithmetic those fixtures pin. The ordering that preserves the
guarantee is: enumerate the deviation set *first*, against the frozen WMPS, and only then merge.

**A subtree merge is hard to reverse.** It rewrites the repository layout and imports history. The
restore path is the pre-merge SHA on `develop`; record it before starting.

---

## 5. Ordering

1. ~~Measure criterion 1's third clause.~~ ✅ Done, 2026-10-06. The gate passed; see §2.1.
2. ~~Record the pre-merge `develop` SHA.~~ ✅ `531d3b28ab810720c9e1d61f2715afd6b1a4eb86`.
3. ~~Subtree merge, no refactor.~~ ✅ Done 2026-10-06, commit `6971806`. See §2.2.
3a. **Package `qh-resources` for platform consumption.** ✅ **Done 2026-10-06 (seq=117).**
    Prerequisite, not in the original ordering. The trading service builds with context `backend/trading`, copies only its own
    `pyproject.toml` and `uv.lock`, and runs `uv sync --frozen`. `packages/qh-resources` is
    outside that build context and undeclared as a dependency, so `from resources…` cannot
    resolve in the container however the strategy imports are rewritten. Widening the context and
    declaring the dependency means changing the `Dockerfile` **and** `docker-compose.yml`, whose
    service definitions are on the platform's do-not-touch list absent a specific instruction.
    Resolved by widening the trading build context to the repository root, adding a
    repo-root `.dockerignore` (context 116 MB → 418 kB), and installing with
    `uv pip install --system --no-deps`. Verified by building the image and importing from it.
    **Also repaired a regression from step 3**: moving `docker-compose.yml` into `services/`
    left five build contexts and four `env_file` paths pointing at directories that do not
    exist. `docker compose config` never validates build-context existence, so it reported the
    file as valid. The live system was unaffected — it still runs from the WMPS repository.
4. De-duplicate, one module at a time, re-running X22 and T11 after each — in this order, which
   is not arbitrary (see §2.3):
   1. ~~**`indicators`**~~ ✅ **Done 2026-10-06 (seq=120).** Not the clean swap this line used
      to promise: the signatures were identical but `wma` was not — the platform reduced with
      `np.dot`, `resources` with `math.fsum`. Measured before swapping, on 157,727 bars of XAUUSD
      H1+H4 at HMA(55): 52% of values move, by at most 3.49 ULP, and neither of crest_n_keel's
      comparisons flips on any bar. 101 lines → 37, and a guard in `test_import_direction.py`
      now fails if the platform redefines any name `resources` owns.
   2. ~~**`drawdown_guard`**~~ ✅ **Done 2026-10-06 (seq=118).** The platform imports the port and
      the guard from `resources` and keeps `JsonPeakStore` locally. 129 lines → 64, and nothing
      was added to `resources` — see §2.3.
   3. ~~**`sizer`**~~ ✅ **Done 2026-10-07 (seq=121).** `calculate_lot_size` → `size_order`, a
      thin adapter over `size_position` on the pinned snapshot that keeps the 0.10-lot hard cap.
      The one reachable change is T5's refusal: on a 4,080-cell grid, 1,294 cells refuse where the
      old sizer traded `min_lot` over budget; the floor-semantics difference needs ATR < $0.10,
      which no XAUUSD bar in 650,769 has reached. **At crest_n_keel's geometry it refuses every H1
      signal since 2025 below ~$1,000 and 34.8% at the $3,643 demo balance** — ruled by T5, and
      carried to step 7. asqs had a fourth, private copy (nearest rounding plus the `min_lot`
      clamp), now routed through the same adapter.
5. ~~Broker port adaptation and order replay.~~ ✅ **Code path done 2026-10-07 (seq=122); real-data
   replay pending an export.** `MT5Broker` (`app/adapters/broker.py`) is the port's `LIVE`
   configuration, and crest_n_keel, asqs and h1_momentum send through it. The port grew optional
   `sl`/`tp`/`magic`/`comment` on `OrderRequest` and a `FillConfig.LIVE` kept off the `FRONTIER`.
   All 45 strategy order paths replay byte-identical against a baseline committed before the port
   (541e732). Criterion 5's *recorded live orders* are in the live Postgres; the replay runs on them
   when `$QH_RECORDED_ORDERS` names a JSON export of Trade rows.
6. ~~T10 execution rename.~~ ✅ **Done 2026-10-07 (seq=123).** State directory → `/var/lib/quant_harness`,
   volume → `quant_harness_state`. No Django, Celery or env identifier carried the old namespace, so
   T10's table-rename and task-routing hazards don't arise. Found a **third live state file**
   (`asqs_partial.json`) R12 missed, and an X16 blind spot (Dockerfiles and `.sh` were never
   scanned). `services/migrate_state_volume.sh` does the verified copy the cutover needs — see
   step 7 — and both stores now log CRITICAL on missing or unreadable state instead of starting
   fresh in silence.
7. Demo week — **ready to start; needs you.** It is a week of the stack running unattended against
   the demo account, which no session can do on your behalf. Everything the earlier steps carried
   forward is collected in §5.1 so the week starts from one checklist rather than five PRs.

### 5.1 Demo week: preconditions, what "no behavioural change" means, what to watch

**Preconditions, in order.** Each names who acts.

1. *(you)* Merge #56 → #57 → #58 in that order; each is stacked on the one before.
2. *(you)* **Close criterion 5's real-data clause.** Export the recorded orders from the database
   the live strategies write to — only the fields the replay needs, no account data — to a path
   **outside the repository** (it is trading history), then run the replay on it:

   ```bash
   docker compose exec trading python manage.py shell -c "import json; \
     from app.trades.models import Trade; print(json.dumps(list(Trade.objects.values( \
     'strategy','direction','symbol','order_volume','sl','tp')), default=str))" \
     > ~/recorded_orders.json
   cd packages/qh-platform/backend/trading
   QH_RECORDED_ORDERS=~/recorded_orders.json pytest tests/test_order_replay.py -k recorded
   ```
3. *(you)* **Decide the asqs daily-cap bug before the week, not during it.** `_check_daily_cap`
   compares `dj_tz.now().date()` (UTC) with an `entry_time__date` lookup Django evaluates in
   `Africa/Nairobi`, so from 21:00 to 24:00 UTC it counts the wrong day — confirmed by experiment
   (seq=123). The one-line fix is `dj_tz.localdate()`. Fixing it mid-week would make criterion 7
   unreadable; leaving it means a known deviation during those three hours.
4. *(you)* **Decide which strategies the week runs.** The beat schedule currently runs none. §4
   says `asqs` and `crest_n_keel` carry `verdict=deployed`; the settings comment calls both
   retired. `h1_momentum` stays halted under R6 either way.
5. *(you)* **Migrate the state, with the workers stopped.** The WMPS stack and this one use
   different Docker volumes regardless of the rename (neither Compose file sets a project name).
   `docker volume ls --format '{{.Name}}' | grep state` gives both names; then
   `services/migrate_state_volume.sh <wmps volume> <new volume>`. Its file listing also answers
   R12's open question — whether an orphaned `peak_equity_HMA1H.json` sits on the old volume.
6. *(you)* Start the new stack against `mt5-test`. A CRITICAL "no peak-state file" line at the
   first evaluation means the migration did not happen; stop and rerun step 5.

**What "no behavioural change" (criterion 7) can mean.** Read literally it cannot hold, because
Phase 3 changed behaviour on purpose, each change ruled before data or forced by a bug. So the
criterion is: **every difference from the WMPS stack is one of these, and nothing else is.**

| Intended change | From | Expect during the week |
|---|---|---|
| Refuse when one minimum lot exceeds the budget (T5, X7) | step 4.3 | At the $3,643 demo balance, crest_n_keel declines ~35% of H1 signals (seq=121); asqs trades above $600 at its default 0.5% |
| asqs rounds lots down, not to nearest | step 4.3 | Occasionally 0.01 lot smaller than WMPS would send |
| CRITICAL on missing or unreadable state | step 6 | Never, after a correct migration |
| HMA via `math.fsum` | step 4.1 | Nothing observable — 0 signal flips in 157,727 bars |

Order *requests* are not on the list: all 45 strategy order paths replay byte-identical (seq=122).

**What to look at, daily.**

- `declined by sizer` / `sizer_declined` lines against signals — the refusal rate should sit near
  the table above. Far higher means a sizing input changed.
- `Order execution error` and `Order failed` lines. **Every one is a finding.** During step 5 a
  stale install made every order raise inside `_place_order`, which caught it, logged one ERROR
  line and returned — no order, no trade record, nothing else. That is what a broken order path
  looks like in production: a quiet week. An alert on these lines is worth adding before day one.
- CRITICAL lines, which after the first start should be none.
- Peak-state files advancing, and trade records reconciling with the broker's deals.

**Pass:** five trading days with zero order errors, no unexplained difference from the table, and
no CRITICAL after first start.

**What the week does not validate.** `mt5-test` is MetaQuotes-Demo, not Pepperstone (CLAUDE.md
rule 7). For XAUUSD the terms the sizer reads are identical on both — contract 100, step 0.01,
minimum 0.01, tick 0.01, USD — and the filling-mode difference (3 vs 2) is resolved per symbol by
the MT5 API, so **sizing and order construction carry over; fills, spreads and costs do not.**

---

## 6. What this spec does not cover

- Phase 4's portfolio weighting, correlation cap and multi-symbol scheduling. Gated on a mechanism
  surviving Phase 2b, which nothing has.
- Any change to WMPS behaviour beyond sourcing shared arithmetic from `resources`. A behavioural
  change during Phase 3 is out of scope and would make criterion 6 unfalsifiable.
