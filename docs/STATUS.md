# quant_harness — Project Status

A living record of where the rewrite stands. The authority on *what* is being
built is `docs/REWRITE.md`; the authority on *what was found* is the research
log (`packages/qh-research/research/log/`). This file is the short answer to
"where are we".

**Last updated:** 2026-10-13 — **Phase 4: no mechanism established.** COT positioning first passed (seq=142, p=0.022) and passed again net of past returns (seq=144, p=0.047). Costing then showed only 2.3 bp a week, which exposed a design flaw: the outcome subtracted a trailing 52-week mean that the trend-following signal correlates with, manufacturing most of the contrarian spread (seq=146). Tick activity (seq=138) and scheduled releases (seq=140) are dead. A corrected COT test can only be judged on reports after 2026-10-13. Phase 3 is closed: the demo strategies are off the schedule and the canary is running (#76).

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
| Tests passing | **784 passed, 10 skipped** on CI; 794 tests total. Every skip is declared and is for data the runner does not have | 794 tests total, measured on run 38302297860 (#75, which appends seq=139 and seq=140, so the log-rewrite check had something to diff and ran). Locally with `QH_DATA_DIR` pointing at the WMPS `research/data/` and a WMPS checkout present, all 794 pass with none skipped. Where the log matches `origin/develop` the rewrite check skips, giving one fewer passed and one more skipped. The CI skips are: X22's port-vs-WMPS comparison (needs a WMPS checkout, a separate repository); one case in `test_parity_data_resolution.py` that asserts the recorded path wins *where it resolves*, so it skips on a runner by design; five Phase 2b panel checks (`test_panel_edge_phase2b.py` ×4, `test_panel_edge_r4.py` ×1) that need the GER40, XAUUSD and FX H1 CSVs; and three `test_sr_star_reeval.py` cases that re-hash the committed SR\* streams against their raw crest_n_keel sources. So the Phase 2b panel result (seq=135) is reproduced locally only, never on CI. 23 further checks used to skip for want of out-of-repo CSVs and no longer do — see the parity-data note below. |
| Packages | 4 built — `qh-resources`, `qh-strategies`, `qh-research`, and `qh-platform` as of the Phase 3 subtree merge | `ls packages/` |
| Acceptance tests | 35 of 35 X ids covered, `DEFERRED` empty; **2** CI-limited and declared (X17, X22) | `tests/test_x_coverage.py` |
| Research log | 147 entries (to seq=146), chain verified; `trial_count()` = 30 | `research.log.verify()` |
| Instruments | 9 — 7 FX majors + XAUUSD + XAGUSD, no symbol-specific branching | `snapshots/pepperstone_live_20260906.json` |
| Gate detection floor | **1.2 annualised Sharpe**, false-positive rate 0% at n=2,000 pooled | seq=107, `research/reports/power.py` |

---

## Phase progress

| Phase | Scope | Status |
|---|---|---|
| 0 | Diagnostic — D1-D9, no code changes | ✅ done (`docs/phase0_memo.md`) |
| 1 | Registry, mask, panel, normalisation, sizing, log schema, parity | ✅ **done — 10/10 criteria** |
| 2 | Panel harness — `signal_edge` per-instrument across the FX majors | ✅ **done** — run at H1, `flood_tide_h1` dead everywhere (seq=109) |
| 2b | Universe expansion — non-USD crosses, metals, indices | ✅ **done** (seq=136) — FX, metals and GER40 (R14); every instrument passes `research.admission`; R3/R4 exercised on GER40's calendar; `flood_tide_h1` across ten instruments is DEAD_ON_AVERAGE, pooled p 0.534 (seq=135); the shelved gold mechanisms re-checked against SR*=D5, no verdict moved (#70) |
| 3 | Execution merge | ✅ **closed 2026-10-13** — demo week 2026-10-07..13 placed 0 orders. Criterion 7 is not falsified but weakly evidenced: the sizer and order paths were never exercised. crest_n_keel and asqs came off the schedule with no asqs position open (#76). The read-only canary has run every 15 minutes on `mt5-test` since 08:52Z that day; all runs were OK in the first 3 hours. Rollback images are tagged `:pre-closeout` |
| 4+ | Multi-symbol live, CPCV | ⏸ **nothing established** — COT positioning's two passes (seq=142, seq=144) are withdrawn as a drift-term artifact (seq=146): on raw returns only GBPUSD and USDCAD lean contrarian, and pooled FX makes 2.3 bp a week gross. Dead: tick activity (seq=138), scheduled releases (seq=140). Trial count 30. **Paused by the owner 2026-10-13.** If it resumes, the open options are an out-of-sample COT test on raw returns (reports after 2026-10-13) and cross-asset, the one input class not yet tried |

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

### Resolved since the last update

| Item | Outcome |
|---|---|
| CFTC positioning data | **Built 2026-10-13** (`research/datasets/cot/`): TFF and Disaggregated futures-only, 2006–2026, for the seven currencies, gold, silver and E-mini S&P. It records actual release times, including the 2013, 2018–19 and 2025 shutdowns and the 2023 ION incident. Rows dated before each report launched are excluded because the CFTC backcast their categories. There is no CFTC report for the DAX. |
| Phase 3 demo week | **Ended 2026-10-13.** 1,006 asqs and 84 crest_n_keel evaluations; 0 orders and 0 trade records. asqs's 11 signals were blocked by spread or H1 confirmation, and crest had none. No CRITICAL lines or tracebacks, and no restarts. `mt5-test` authorization failed twice on 2026-10-12 and recovered within one run. Criterion 7 is not falsified but weakly evidenced: the sizer and order path were never exercised. |
| A macro-release calendar | **Built 2026-10-12** (`research/datasets/calendar/`): 1,438 FOMC, NFP, CPI, ECB, BoE and BoJ releases from 2004-06, all from central-bank and BLS pages, with sources and build scripts. 384 rows carry a documented standard time rather than a per-release one; BoJ publishes no time for 156 of 259. Broker server time was confirmed as Europe/Athens (EU DST) from bar spacing: gold's New York-fixed daily break shifts by an hour in the weeks the two DST regimes disagree. |
| Order flow as Phase 4's input | **Not available; tested activity instead** (2026-10-12). The live Pepperstone feed carries quote updates only: `volume` and `last` are zero on every tick and the BUY/SELL flags never appear. Raw ticks are retained from 2025-01-08 (plus a 4-week island in 2021-10); EURUSD's flag encoding changes on 2025-12-31. Bar `tick_volume` covers 10–20 years but its level moves with the feed (XAUUSD median 33→5,263 ticks/h over 2004–13), so the mechanism used it relative to the same hour of the week. Result: DEAD (seq=138). Depth scan: `phase0/tick_depth_20261012.csv` (live `mt5`, GET-only, one 10-minute window each Wednesday 14:00 UTC, 2016–2026, EURUSD, XAUUSD, GER40; counts and modal flags only). |
| Branch protection | **Applied 2026-10-11.** `develop` requires the "Test suite" check; force-pushes and deletion are blocked; no review is required and admins can override. **CI green is not all tests green:** X22's port-vs-WMPS comparison cannot run on a runner (`CI_LIMITED`), so a change touching parity needs a local run with the WMPS checkout before merge. |
| Slip is `HAND_ENTERED` at 1 tick | **Measured 2026-10-11** (seq=133, #68) from 179 live entries against the same-second quote. XAUUSD: median −0.5 ticks, p90 5.3 — the 1-tick default stays. **FX: fills land about 0.5 pip beyond the quote feed on every pair and both sides**, so any FX cost built from the feed is too low for this account by roughly a pip per round trip; an FX panel run must cost from fills. No default moved. The reference quote was chosen after seeing both candidates; the FX result holds under either. |
| Operational monitoring after the demo week | **Built 2026-10-11** (#67): `quant.canary.run`, read-only by construction — no order, close, modify or trade-record path exists on its MT5 handle, and tests prove it end to end. Its beat entry is committed **disabled**; it is enabled when crest_n_keel and asqs come off, with the owner's approval. |
| Phase 2b's third market structure | **Ruled 2026-10-09** (R14, seq=132): GER40, with UK100 as fallback, chosen on drivers before any data was pulled and declared only after `research.admission` passed it on integrity alone. Its H1 file holds monthly, daily and H4 bars before 2018-07-13, so it is admitted from there. The same gate refuses US500 for an undeclared 55-day hole (2025-07-16..09-09). |
| Re-run seq=74 on hourly data? | **Done 2026-10-09** (seq=131), at the owner's request. Same specification and decisive stream; seq=74's observed figures were first reproduced exactly on the original window. On 2016-01-25..2025-12-31: advantage +0.0879, p=0.9055, against a null mean of +0.1562 (was +0.0687, p=0.9701). **The kill holds.** Five folds instead of nine. Not a new trial. |
| Phase 2b — blocked on a registry snapshot | **Closed 2026-10-09** (seq=127). The live `mt5` container had run no terminal since 2026-09-29; rebuilding it on `main` brought it back, and the D1 collector, now taking `--symbols`, dumped fourteen symbols from PepperstoneKE-MT5-Live01 with `--expect-server` armed. IOC holds on all fourteen, US500 included. Pinned as `pepperstone_live_20261009.json` beside the 20260906 snapshot, which the live sizer still reads. Two things it does not settle: swaps read exactly 0.0 on eight symbols, cause unknown and read by no code; and the build is 6182, from the terminal log, with 6230 on offer. |
| Commission: zero it, and with which spread? | **Closed.** Measured at 0.00 across all 358 live deals (seq=105) — the account is Standard, not Razor, which made the gold dispute moot rather than settled. `cost_model.py` now defaults to `MEASURED` (commission 0.00, spread 0.17) with `CONSERVATIVE` (7.00, 0.22) as a declared scenario, and every `CostBreakdown` stamps which one produced it. The two moved together, as required. |
| O1 timeframe ruling | **Confirmed by the user 2026-09-22** (seq=108). H1 for the first panel run; the spec's declared prior was H4 and was overturned by data, which is the only thing it allowed. The **~$1,100 flip threshold is accepted and now live**: if capital crosses it the timeframe decision reopens on its own terms rather than needing re-argument. Nothing in Phase 2 is blocked on this. |
| Workstation disk | 79% used, 23 GB free (2026-09-22), against 92%/9 GB when last written. A nine-symbol panel run has room. This figure goes stale fastest of anything here — re-measure rather than cite it. |

### Known and carried

| Item | Notes |
|---|---|
| D3b covers 2 of 9 symbols | The frontier cannot fully cost the other seven. |
| Parity CSVs resolve from this repo | `default_data_paths()` prefers `$QH_PARITY_DATA_DIR`, then the WMPS path recorded in the seq=31 artifact, then the copies tracked here. Safe because `ohlc_hash` is parity layer 1 and is compared before anything downstream runs. This un-skipped 23 CI checks, two of which carry Phase 1 criteria #2 and #3 — previously met locally and unproven on a runner. |
| `n_trades` gate is inert | Passed at every injected alpha level (seq=107); contributes nothing to the six-way AND. |
| Three copies of the indicator arithmetic | `resources`, `research.engines`, `cnk_engine`. The first two are held together by T11's bit-for-bit test; the third is frozen as a parity generator. |
| DSR twin duplication | `research/post/dsr.py` is canonical; the harness twin must reproduce the parity vectors. |
| `research.engines.strategies` vs top-level `strategies` | Name overlap, **measured benign and guarded**. No module imports both, and nothing under `research/` uses a bare `import strategies` — every import there is fully qualified, so the interpreter never chooses between them. A rename would touch ten files to remove a cosmetic wart and move real risk around, so the fix is a guard instead: `tests/test_strategies_namespace.py` fails if a bare `import strategies` ever appears under `research/`, which is the one way the wart could become a bug. |
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

## Phase 2 — what the panel run found

Run at H1 on 2026-09-22 (seq=109), 1,000 permutations, seed fixed.

| | E(h=20) | E(h=50) | E(h=100) |
|---|---|---|---|
| Pooled E-Ratio | 0.959 | 0.966 | 0.987 |
| Null mean | 0.990 | 0.987 | 0.992 |
| p | 0.947 | 0.859 | 0.602 |

**Alive at their own gate: none.** The highest per-instrument E-Ratio anywhere
is 1.085 (NZDUSD, h=20) against a 1.15 hard gate — `flood_tide` is a breakout
entry, so the gate applies rather than being diagnostic-only. All seven
instruments cleared `MIN_SIGNALS_TO_DECIDE`; the mechanism sits below its own
null at every horizon.

That is the acceptance condition met. Under R5, Phase 2 is *harness
validation* by re-running an already-falsified mechanism: `flood_tide_h1`
being dead everywhere confirms the harness and seq=34's shelving in one run.
A dead result is the pass.

Two things worth carrying:

- **NZDUSD carries the highest ratios and the thinnest sample** — 124 signals
  over 20 months, against 835-1,166 over twelve years elsewhere. It clears the
  30-signal decidability floor comfortably, but the thinnest instrument
  showing the highest numbers is what noise looks like. It changes nothing
  here; it would matter if anything were near the gate.
- **A smoke run at 3 permutations reported p=1.0000 at every horizon.** At
  1,000 the p-values are 0.947 / 0.859 / 0.602. Reporting the smoke run would
  have published "worse than every random draw", which the data does not
  support. The honest reading is weaker: the entry fails to beat random
  entries, and is not reliably worse than them.

The resampling check travels with the result (`resampling_check` in the entry's
metrics): the majors have no native H4, so every trend filter in this run read
a resampled series, and that assumption is recorded next to the verdict that
depends on it rather than asserted in a docstring.

---

## What "done" looks like for Phase 2b

**Met 2026-10-11** (seq=136). R5 as re-scoped: the research universe spans three
market structures — FX, metals and, per R14, GER40 — before any new mechanism is
pre-registered. The original effective-N target was dropped because F1 showed no
instrument count reaches it.

- Registry spec for the third structure: `pepperstone_live_20261009b.json` (seq=132).
- H1 history through the panel loader, behind the admission gate: GER40 from 2018-07-13.
- R3's mask and R4's tradable-bar horizon exercised against GER40's calendar (seq=134/135).
- The shelved XAUUSD mechanisms re-evaluated against SR*=D5: no deciding verdict moves (#70).

Two figures elsewhere in this repo were corrected along the way: cnk_momentum's
OOS Sharpe of 1.20 counts overlapping folds twice and is about 0.85 at the true
trade rate, and seq=94 misstates D5's window (it is 2004-06-14..2025-12-31).
