# quant_harness — Project Status

A living record of where the rewrite stands. The authority on *what* is being
built is `docs/REWRITE.md`; the authority on *what was found* is the research
log (`packages/qh-research/research/log/`). This file is the short answer to
"where are we".

**Last updated:** 2026-09-22 — Phase 1 complete; gate power measured and R8 fires; O1 confirmed as H1.

> **Note on this file's history.** Until 2026-09-20 it described the
> pre-rewrite package layout and a Phase 1/2a/2b/2c *module* numbering that
> the rewrite replaced with Phase 0/1/2 *project* numbering. It had not been
> updated since the T10 rename, so it reported 82 tests and a next-session
> queue long since done. It was rewritten rather than patched because nothing
> in it still described this repository.
>
> It then went stale again inside a single day: the 2026-09-20 rewrite was
> merged with an entry count, a disk figure and a resolved decision that were
> already wrong when the merge landed. Every figure below was re-measured on
> 2026-09-22 against `093da59`, which is what the table's provenance column
> now records.

---

## Snapshot

Measured on 2026-09-22 at `093da59`. Each row names how to reproduce it, so
the next reader can check rather than trust.

| Metric | Value | How it was measured |
|---|---|---|
| Tests passing | **614 passed, 25 skipped** on CI for `develop`; 639 tests total, and two independent conditions each unskip some of them (see next column) | 639 tests total. Two conditions gate the rest: hiding the out-of-repo data (`QH_PARITY_DATA_DIR=/nonexistent QH_WMPS_DIR=/nonexistent`) skips **24**, and a log matching `origin/develop` skips **1** more, because `test_no_pre_existing_entry_was_rewritten` has nothing to diff. CI on `develop` hits both: 614 / 25. A branch appending to the log: 615 / 24. Locally with the data present and a log append: 639 / 0. Both gaps measured 2026-09-22. |
| Packages | 3 built — `qh-resources`, `qh-strategies`, `qh-research`. `qh-platform` is in the spec and the pytest path list but does not exist yet | `ls packages/` |
| Acceptance tests | 35 of 35 X ids covered, `DEFERRED` empty; 3 CI-limited and declared (X15a, X17, X22) | `tests/test_x_coverage.py` |
| Research log | 109 entries (to seq=108), chain verified; `trial_count()` = 26 | `research.log.verify()` |
| Instruments | 9 — 7 FX majors + XAUUSD + XAGUSD, no symbol-specific branching | `snapshots/pepperstone_live_20260906.json` |
| Gate detection floor | **1.2 annualised Sharpe**, false-positive rate 0% at n=2,000 pooled | seq=107, `research/reports/power.py` |

---

## Phase progress

| Phase | Scope | Status |
|---|---|---|
| 0 | Diagnostic — D1-D9, no code changes | ✅ done (`docs/phase0_memo.md`) |
| 1 | Registry, mask, panel, normalisation, sizing, log schema, parity | ✅ **done — 10/10 criteria** |
| 2 | Panel harness — `signal_edge` per-instrument across the FX majors | ⏭ next, **at H1** (O1 confirmed, seq=108); `panel_edge.py` written, unrun |
| 2b | Universe expansion — non-USD crosses, metals, indices | ⚠ its rationale is now contested — see below |
| 3+ | Execution merge, live path | ⏭ not entered until a mechanism survives 2b |

### Phase 1 acceptance criteria

All ten hold. The three that took the most work:

- **#2 mask-off parity** — T9a reproduces the seq=31 E-Ratio artifact and T9b
  is trade-for-trade identical against seq=49, the latter against a
  `REGENERATED_FROM` fixture because no artifact anywhere held trade records.
- **#3 mask-on attribution** — T9a splits the divergence into signal-set and
  normaliser channels; T9b traces every differing trade to a named flag and a
  named mechanism. Zero unattributed. (seq=103, seq=104)
- **#8 D8 fixtures** — met by *exact* reproduction rather than a logged
  deviation, after `wma` moved off `np.dot`. (seq=102)

### What the gate power measurement changed

seq=107 measured what five consecutive falsifications could not distinguish:
whether the mechanisms were dead or the six AND-ed gates reject nearly
everything. Injecting alpha at known annualised Sharpe among 19 noise
strategies puts the **detection floor at 1.2** with a 0% false-positive rate.
The falsified mechanisms measured 0.27–0.41 OOS — under the floor, so those
verdicts stand on the mechanisms rather than on gate strictness.

Three consequences worth carrying:

- **R8 fires.** Its conclusion is that the missing ingredient is
  *information, not breadth*.
- **This does not block Phase 2**, whose acceptance under R5 is *harness
  validation* by re-running an already-falsified mechanism — it expects
  `flood_tide_h1` to be dead everywhere. It bears on **Phase 2b**, whose
  stated rationale is that a discovery claim needs breadth. If breadth is not
  what is missing, that rationale needs revisiting before 2b is entered. That
  is a spec decision, not a status one.
- `n_trades` is **inert** — it passed at every injected level, so it
  contributes nothing to a six-way AND. Tightening PBO 0.5→0.3 and trades
  30→100 costs zero detection power.

---

## Open items

### Needs the user

| Item | Why it is blocked |
|---|---|
| Phase 2b's rationale, after R8 | R5 requires 2b to complete before any new mechanism is pre-registered, because "a discovery claim does need breadth". seq=107 measures the missing ingredient as information rather than breadth. Both can't be the governing reason; which one holds is a spec decision. |
| Branch protection | CI runs again; making it required to merge is a repo setting only you can change. |
| Slip is `HAND_ENTERED` at 1 tick | The only cost input with no source at all, and no document can supply it — only a real fill measures it. The 358 deals carry the fill price but not the requested price, so they cannot close this. |

### Resolved since the last update

| Item | Outcome |
|---|---|
| Commission: zero it, and with which spread? | **Closed.** Measured at 0.00 across all 358 live deals (seq=105) — the account is Standard, not Razor, which made the gold dispute moot rather than settled. `cost_model.py` now defaults to `MEASURED` (commission 0.00, spread 0.17) with `CONSERVATIVE` (7.00, 0.22) as a declared scenario, and every `CostBreakdown` stamps which one produced it. The two moved together, as required. |
| O1 timeframe ruling | **Confirmed by the user 2026-09-22** (seq=108). H1 for the first panel run; the spec's declared prior was H4 and was overturned by data, which is the only thing it allowed. The **~$1,100 flip threshold is accepted and now live**: if capital crosses it the timeframe decision reopens on its own terms rather than needing re-argument. Nothing in Phase 2 is blocked on this. |
| Workstation disk | 79% used, 23 GB free (2026-09-22), against 92%/9 GB when last written. A nine-symbol panel run has room. This figure goes stale fastest of anything here — re-measure rather than cite it. |

### Known and carried

| Item | Notes |
|---|---|
| D3b covers 2 of 9 symbols | The frontier cannot fully cost the other seven. |
| `n_trades` gate is inert | Passed at every injected alpha level (seq=107); contributes nothing to the six-way AND. |
| Three copies of the indicator arithmetic | `resources`, `research.engines`, `cnk_engine`. The first two are held together by T11's bit-for-bit test; the third is frozen as a parity generator. |
| DSR twin duplication | `research/post/dsr.py` is canonical; the harness twin must reproduce the parity vectors. |
| `research.engines.strategies` vs top-level `strategies` | Name overlap, not yet resolved. |
| Scan/position visualisation | Parked, unpublished (VortexEdge + Astra Terminal concept). |

---

## Architecture invariants

These hold throughout. If a change would break one, that is the moment to stop.

1. **The harness scores returns; it does not run strategies.** Engine-agnostic.
2. **Pre-registered gates only.** Threshold changes go through a documented
   override, never a silent in-code edit.
3. **`trial_count()` is honest.** Every sweep cell counts. Parity fixtures and
   audits do not (X15d).
4. **Bar-close evaluation only.** No look-ahead through intra-bar prices, no
   decision on the forming bar.
5. **The MT5 live path is deterministic.** No LLM in the order-placing path.
6. **One definition of each formula**, with any duplicate held to it by a test.
7. **A sweep describes a surface; its leader is not a candidate.** Proven twice
   (seq=49, seq=68). Only a nested walk-forward with the pool control is
   evidence of generalisation.
8. **WMPS is frozen** under spec §1.3 — mirrored bug fixes only.

---

## What "done" looks like for Phase 2

`signal_edge` running per-instrument across the FX majors from one strategy
module, producing per-instrument results with no symbol-specific branching
anywhere in the call path — which Phase 1 criterion 5 already demonstrates on
synthetic bars. Phase 2 is that same claim against real data, on the panel,
with costs that are measured rather than assumed.

Its acceptance is **harness validation, not discovery** (R5): re-running an
already-falsified mechanism, where `flood_tide_h1` being dead everywhere
validates the harness and confirms the verdict in one run. A dead result is a
pass. This is worth stating plainly because seq=107's detection floor makes a
live result unlikely, and that is the expected outcome rather than a
disappointment.

The timeframe is settled: **H1**, confirmed at seq=108, with the ~$1,100 flip
to H4 accepted as a live trigger rather than a caveat.
`packages/qh-research/research/pre/panel_edge.py` is written and has not been
run.
