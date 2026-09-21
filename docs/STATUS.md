# quant_harness — Project Status

A living record of where the rewrite stands. The authority on *what* is being
built is `docs/REWRITE.md`; the authority on *what was found* is the research
log (`packages/qh-research/research/log/`). This file is the short answer to
"where are we".

**Last updated:** 2026-09-20 — Phase 1 complete: all ten acceptance criteria met.

> **Note on this file's history.** Until 2026-09-20 it described the
> pre-rewrite package layout and a Phase 1/2a/2b/2c *module* numbering that
> the rewrite replaced with Phase 0/1/2 *project* numbering. It had not been
> updated since the T10 rename, so it reported 82 tests and a next-session
> queue long since done. It is rewritten rather than patched because nothing
> in it still described this repository.

---

## Snapshot

| Metric | Value |
|---|---|
| Tests passing | **524 passed, 25 skipped** on CI; 548 passed, 1 skipped locally with the out-of-repo data present |
| Packages | 3 built — `qh-resources`, `qh-strategies`, `qh-research`. `qh-platform` is in the spec and the pytest path list but does not exist yet |
| Acceptance tests | 35 of 35 X ids covered; 3 CI-limited and declared |
| Research log | 105 entries, chain verified; `trial_count()` = 26 |
| Instruments | 7 FX majors + XAUUSD + XAGUSD, no symbol-specific branching |

---

## Phase progress

| Phase | Scope | Status |
|---|---|---|
| 0 | Diagnostic — D1-D9, no code changes | ✅ done (`docs/phase0_memo.md`) |
| 1 | Registry, mask, panel, normalisation, sizing, log schema, parity | ✅ **done — 10/10 criteria** |
| 2 | Panel harness — `signal_edge` per-instrument across the FX majors | ⏭ next |
| 2b | Universe expansion — non-USD crosses, metals, indices | ⏭ after 2 |
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

---

## Open items

### Needs the user

| Item | Why it is blocked |
|---|---|
| Commission: zero it, and with which spread? | **Measured at 0.00 on all 358 live deals** — the account is not on the Razor schedule (seq=105). The $7.00 constant is a known over-cost, left in place because zeroing it flatters every recorded metric and because the measured spread (0.17 USD/oz) differs from the model's assumed 0.22. The two must move together. |
| Slip is `HAND_ENTERED` at 1 tick | The only cost input with no source at all, and no document can supply it — only a real fill measures it. |
| Branch protection | CI runs again; making it required to merge is a repo setting. |
| O1 timeframe ruling — confirm | **Closed 2026-09-20 as H1** (seq=106), six days past its pinned veto date. Both legs are now measured: H4 is 2.06x cheaper on cost-to-ATR, but zero instruments are tradable there at $100 against three at H1. Flips to H4 above ~$1,100 of capital. The spec says O1 is brought back with the numbers attached, so this wants your confirmation rather than mine. |
| Workstation disk | 92% used, ~9 GB free. A nine-symbol panel run will not like it. |

### Known and carried

| Item | Notes |
|---|---|
| D3b covers 2 of 9 symbols | The frontier cannot fully cost the other seven. |
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
