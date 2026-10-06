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

---

## 3. Acceptance criteria

Binary. All must hold. Criterion 1 replaces §11's "identical" clause per R11.

1. **The deviation set is enumerated before the merge**, every member is attributed to the
   `fsum`/`np.dot` reduction, and **no member falls on a bar where a live strategy would have
   acted.** ✅ **Measured 2026-10-06 — passes (F4, seq=114).** See §2.1.
2. WMPS history is preserved through the subtree merge — `git log --follow` reaches pre-merge
   commits for every moved file.
3. The three duplicated modules are deleted, not merely bypassed, and no import path reaches them.
4. `MT5APIClient` satisfies the `resources.execution.broker` port, verified by replaying recorded
   live orders through both the old client and the port with identical resulting order parameters.
5. The execution-side T10 rename is complete; no pre-rename namespace identifiers remain
   anywhere the X16 guard scans.
6. The demo stack runs a full week unattended with no behavioural change.
7. `trial_count()` is unchanged by the merge. Phase 3 is engineering; it registers no hypothesis.

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
2. Record the pre-merge `develop` SHA.
3. Subtree merge, no refactor. Verify criterion 2 before touching anything.
4. De-duplicate, one module at a time, re-running X22 and T11 after each.
5. Broker port adaptation and order replay.
6. T10 execution rename.
7. Demo week.

---

## 6. What this spec does not cover

- Phase 4's portfolio weighting, correlation cap and multi-symbol scheduling. Gated on a mechanism
  surviving Phase 2b, which nothing has.
- Any change to WMPS behaviour beyond sourcing shared arithmetic from `resources`. A behavioural
  change during Phase 3 is out of scope and would make criterion 6 unfalsifiable.
