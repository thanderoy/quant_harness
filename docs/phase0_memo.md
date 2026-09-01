# Phase 0 memo — universe diagnostic

**Date:** 2026-08-31 · **Repos:** WMPS `3db869a` (dirty), `qhf_harness` `cb48e00`
**Artifact:** `phase0/phase0_universe_20260831.json`
**Stamps:** `PARTIAL_UNIVERSE`, `PROVISIONAL_SPECS`

Status: **D6, D7, D8, D9 complete. D2, D4, D5 complete but stamped. D1 and D3 BLOCKED.**

---

## 1. Verdict in one paragraph

Phase 0 confirms the diagnosis that motivated the rewrite and sharpens it in three places, one
of which overturns a declared prior. Breadth is worse than assumed: five available majors give
**1.55 effective bets**, not the ~1.9 estimated, and that is an upper bound. Granularity is
worse than assumed and points the opposite way to the spec's expectation: **H4 is strictly worse
than H1 at $100**, not better, because minimum lot size is fixed and a wider stop therefore
raises risk per trade rather than lowering it. And the benchmark correction bites harder than
anticipated: gold's own buy-and-hold Sharpe is **+0.634**, which is *above* the entire observed
OOS range of the shelved mechanisms (0.27–0.41). Against a correct SR\*, those mechanisms did not
merely fail significance — they underperformed holding the asset.

---

## 2. D7 — log integrity baseline (GATE: PASSED)

| | |
|---|---|
| `verify()` | `True` — "chain ok (82 entries)" |
| `trial_count()` | **26** |
| entry count | **82** (seq 0–81) |
| terminal hash | `019ff0dd3e1b7209f9be6ef5bd8efb590a15ee627a540d5c8679cb320da31876` |

This is the migration reference. Every post-migration check asserts these four values.

**Superseded by one append.** The `LIVE_RISK_HALT` (§6.1) was written to the log after this
baseline was taken, so the current chain state is:

| | D7 baseline | After `LIVE_RISK_HALT` |
|---|---|---|
| entries | 82 (seq 0–81) | **83** (seq 0–**82**) |
| `trial_count()` | 26 | **26 — unchanged** |
| terminal hash | `019ff0dd…0da31876` | `91470ef9…abf6050d` |
| `verify()` | True | **True** |

`trial_count()` holding at 26 is the invariant that matters: the halt was appended with
`counts_as_trial=False`, so no multiplicity was laundered in either direction. **D9's Step 3
assertions must now target 83 / seq=82 / `91470ef9…`**, and the plan has been updated accordingly.

**Not recorded as a typed `AUDIT` / `LIVE_RISK_HALT` event.** `EventType` has only `HYPOTHESIS`
and `UPDATE`; adding members is a `log.py` change that Phase 0's zero-change rule forbids. The
halt was therefore written as an honest `UPDATE` against the existing `h1_momentum_nested_wf`
hypothesis — the correct shape regardless, since it updates a hypothesis that already exists —
with `LIVE_RISK_HALT` carried in the note and metrics. **The enum members are owed under T6.**
`log.md` was regenerated via `render_markdown()`, not hand-edited; all prior hypotheses verified
still present.

---

## 3. Shortlist and the granularity verdict (D2)

$100 equity, 2% budget, 1.5×ATR stop, median ATR over 24 months. **`PROVISIONAL_SPECS`** — D1 is
blocked, so contract sizes are hand-entered standard values.

| Symbol | TF | Median ATR | Min-position risk | % of $100 | Tradable |
|---|---|---:|---:|---:|:--:|
| **USDCAD** | **H1** | 0.00118 | $1.28 | **1.28%** | **YES** |
| **EURUSD** | **H1** | 0.00129 | $1.94 | **1.94%** | **YES** |
| **USDCHF** | **H1** | 0.00106 | $1.97 | **1.97%** | **YES** |
| USDJPY | H1 | 0.22220 | $2.17 | 2.17% | no |
| GBPUSD | H1 | 0.00159 | $2.39 | 2.39% | no |
| USDCAD | H4 | 0.00242 | $2.61 | 2.61% | no |
| USDCHF | H4 | 0.00226 | $4.20 | 4.20% | no |
| EURUSD | H4 | 0.00276 | $4.14 | 4.14% | no |
| USDJPY | H4 | 0.48589 | $4.75 | 4.75% | no |
| GBPUSD | H4 | 0.00335 | $5.02 | 5.02% | no |
| XAUUSD | H1 | 7.02480 | $10.54 | 10.54% | no |
| XAGUSD | H1 | 0.21461 | $16.10 | 16.10% | no |
| XAUUSD | H4 | 14.19064 | $21.29 | 21.29% | no |
| XAGUSD | H4 | 0.40948 | $30.71 | 30.71% | no |

**Three of fourteen cells are tradable, all at H1, and two of them pass by three basis points.**
EURUSD (1.94%) and USDCHF (1.97%) clear a 2.00% budget with no margin — a modest volatility
increase flips them. Only USDCAD H1 has real headroom.

XAUUSD H1 at 10.54% corroborates spec §1's "roughly 12%" estimate. XAUUSD H4 is 21.29%: a single
minimum-lot gold trade at H4 risks more than twice the 8% drawdown guard.

### 3.1 This overturns O1's declared prior

§10.2 declares H4 as the prior, reasoning "larger stop distances improve lot granularity at $100."
**That reasoning is inverted.** Minimum lot is fixed at 0.01; you cannot buy a smaller fraction of
a wider stop. Risk per minimum position is `min_lot × contract_size × stop_distance`, which is
*linear and increasing* in stop distance. Every instrument in the table roughly doubles its risk
from H1 to H4, and **zero instruments are tradable at H4**.

Granularity therefore argues **H1**, unambiguously and by a wide margin. The prior's other two
grounds — cost-to-ATR and fewer scheduled evaluations — still favour H4, and cost-to-ATR is the
stronger of the two. But it is D3, and D3 is blocked. So the O1 decision now rests entirely on a
measurement that does not exist yet, with the granularity leg having flipped sides.

**RULED 2026-08-31: the H4 prior is withdrawn; the prior is now H1.**

The two legs conflict, but not symmetrically. **Granularity is a hard constraint** — below the
threshold the trade cannot be placed within budget at all. **Cost is soft** — it degrades edge
continuously. Hard dominates soft, so D3 stops being the decider and becomes a **veto**, with its
threshold declared now, before the measurement exists:

| Round-trip cost as % of 1×ATR(H1) | Outcome |
|---|---|
| **< 5%** | H1 proceeds |
| **5–10%** | Marginal — the mechanism must show edge net of cost across the full fill frontier |
| **> 10%** | H1 vetoed |

And since H4 is already dead on granularity, a veto does not send the search to another timeframe.
The finding to record in that case is that **$100 cannot trade this system at any timeframe** —
not that a fitting timeframe is still out there.

### 3.2 Research universe ≠ execution universe

Three of fourteen cells pass, and two clear by three basis points **against a median ATR**. Half
the time ATR is above median, and EURUSD and USDCHF fail. The executable universe at $100 is
effectively **one instrument** (USDCAD H1), not seven.

This does not block the rebuild, but it forces a rule: **a mechanism is validated on the full
panel and traded on the feasible subset.** Pre-registration carries both `universe` and
`executable_subset`, and passing the first while being undeployable under the second is **not a
falsification**.

Without that separation there is a standing temptation to shrink the research panel to what can
be traded — which would take effective N from 1.55 to 1, and end the programme's ability to decide
anything at all.

---

## 4. Effective breadth (D4)

Daily log returns, 5-year window (2020-12-31 → 2025-12-31, 1,269 aligned observations),
sign-adjusted so every series measures "foreign currency vs USD".

Note the window closes at 2025-12-31 rather than 2026-08-28: the aligned panel is bounded by
XAUUSD, whose local history ends there while the FX series run eight months longer. Refreshing
XAUUSD would extend D4 and should be part of the same MT5 session that unblocks D1/D3a.

| Set | k | Avg pairwise \|ρ\| | Effective N |
|---|---:|---:|---:|
| Majors available (EURUSD, GBPUSD, USDJPY, USDCHF, USDCAD) | 5 | 0.556 | **1.55** |
| Majors + metals (XAUUSD, XAGUSD) | 7 | 0.471 | **1.83** |

**`PARTIAL_UNIVERSE` — these are upper bounds.** AUDUSD and NZDUSD have no local history. They
correlate strongly with each other and with the commodity complex, so including them would raise
average |ρ| and push effective N *down*.

Measured avg |ρ| of 0.556 sits at the top of §1.4's assumed 0.4–0.55 band. The spec's conclusion —
"roughly two independent bets, not seven" — is confirmed and is, if anything, generous. **The
honest figure is closer to 1.5.**

This strengthens R5 considerably. Seven majors cannot support a discovery claim, and five give
one and a half bets. Phase 2b expansion is not an optimisation; it is the precondition for the
programme to produce a decidable result at all.

**R5 is now quantified rather than asserted.** At per-instrument SR 0.40 and effective N 1.55,
portfolio SR is ~0.50. Majors alone are a **harness-validation universe, not a discovery
universe.**

**Phase 2b targets effective N ≥ 4.** That needs roughly 16 instruments at ρ = 0.20, or 9 at
ρ = 0.15, and is **unreachable at any instrument count once ρ ≳ 0.25** — the ceiling is set by
correlation, not by count. Expansion must therefore **break USD dominance**, not add more majors.
Adding AUDUSD and NZDUSD would move effective N *down*, not up.

### 4.1 MinTRL figures depend on assumed moments — flagging a discrepancy

Computing MinTRL under **normal returns** (γ₃ = 0, γ₄ = 3, one-sided α = 0.05) I get lower numbers
than the ones you quoted:

| Case | Normal-returns MinTRL | Quoted |
|---|---:|---:|
| Portfolio SR 0.50 vs SR\* 0 | 13.2 y | 17 y |
| Gold: SR 0.80 vs SR\* 0.634 | 130.6 y | 201 y |
| Gold: SR 1.00 vs SR\* 0.634 | 31.3 y | 51 y |
| Gold: SR 1.50 vs SR\* 0.634 | 8.7 y | 15 y |

The ratios are not constant (1.29, 1.54, 1.63, 1.72), so this is **not** a different `Z_α`. The
pattern is consistent with non-normal moments — negative skew and excess kurtosis, e.g.
γ₃ ≈ −0.5, γ₄ ≈ 5, which reproduces the ratios closely. That is the more realistic assumption for
trading returns, so the quoted figures are likely the better ones; I am recording the difference
rather than silently adopting either.

**Spec consequence for T7:** MinTRL must take γ₃ and γ₄ as **explicit required arguments**, not
defaults. A silent normal-returns default understates the required track length by 30–70% across
this range — which is the same class of error as DSR defaulting SR\* to 0, and deserves the same
mechanical refusal (X14's pattern applied to T7).

---

## 5. Benchmark Sharpe, SR\* (D5)

Long-only buy-and-hold, annualised at 252, zero risk-free rate.

| Symbol | SR\* | Window |
|---|---:|---|
| EURUSD | −0.157 | 2013-10 → 2026-08 |
| GBPUSD | −0.147 | 2013-10 → 2026-08 |
| USDCHF | −0.096 | 2013-10 → 2026-08 |
| USDCAD | +0.319 | 2013-10 → 2026-08 |
| USDJPY | +0.424 | 2013-10 → 2026-08 |
| XAGUSD | +0.282 | 2009-08 → 2026-08 |
| **XAUUSD** | **+0.634** | 2004-06 → 2025-12 |
| Equal-risk-weighted panel | +0.547 | aligned |

FX majors are near zero as predicted, with the caveat that **USDJPY (+0.424) and USDCAD (+0.319)
are not near zero** over this particular window — a decade of USD strength. A mechanism trading
those two long-biased inherits a real benchmark and must be evaluated against it, not against 0.

### 5.1 The gold finding

**XAUUSD SR\* = +0.634 exceeds every OOS Sharpe the programme has produced.** The observed range
across the five falsified mechanisms is 0.27–0.41. Evaluated against SR\* = 0, as every prior DSR
call did, they were merely insignificant. Evaluated against the correct benchmark, **their excess
Sharpe is negative**: they underperformed buying and holding the asset they traded.

This does not reopen any verdict — all five are already dead. It changes what the record should
say about *why*, and it is the concrete justification for T8 making `benchmark_sharpe` a required
argument. It should be appended to the log as a finding under T8's retrospective-note requirement.

Caveat: XAUUSD's window (2004–2025) differs from the FX windows (2013–2026) and covers a
historically exceptional gold bull market. The number is correct for the backtest window actually
used, which is the window that matters for DSR, but it is not a claim about gold in general.

### 5.2 RULED — which benchmark gates, declared before the numbers

A timing overlay is not exposure-matched to continuous buy-and-hold, so two benchmarks are
defensible and the choice would otherwise get made after seeing which is kinder.

**Gate on full buy-and-hold** — that is the alternative actually available to the account.
**Report the exposure-matched figure as a diagnostic**, never as the gate.

Against SR\* = +0.634, the bar this sets for any future gold mechanism (normal-returns basis;
see §4.1 on moments):

| Strategy SR | MinTRL vs gold SR\* |
|---|---:|
| 0.80 | 131 y (quoted: 201 y) |
| 1.00 | 31 y (quoted: 51 y) |
| 1.50 | 9 y (quoted: 15 y) |

Either column says the same thing: gold at this benchmark is not decidable by a mechanism with a
Sharpe below roughly 1.5, and the programme has never produced one above 0.41.

---

## 6. D6 — hardcoded-assumption audit

Full table in `docs/hardcoded_audit.md`: **30 rows, 17 resolved, 13 deferred with reasons.**

**Required output — does `btpy_runner` route sizing through `calculate_lot_size`?** Partly.
`btpy_runner` is sizing-agnostic; strategies decide. `hma_stoch`, `cnk_momentum` and `zlch` route
through the sizer; `ebb_n_flow` and `asq_safe_scalping` each reimplement it. **T9c is not
mandatory** — T9b's fixture is `crest_n_keel` = `hma_stoch`, which does route through the sizer,
so the historical artifact is sensitive to T5.

Three findings that were not assumptions:

1. **The two `sizer.py` copies are numerically identical** (AST-normalised diff). The harness copy
   only omits two input-validation guards, unreachable at every call site. No historical artifact
   is affected, so D8 can pin the WMPS implementation and T11 parity will hold.
2. **`ORDER_FILLING_IOC` is already generalised** — `mt5-api/main.py` branches across IOC/FOK/
   RETURN. D1's guard still applies, but the Phase 3 code change is smaller than assumed.
3. **Three independent sizing implementations exist.** This is the concrete instance of the drift
   risk §1.3 exists to control, and it is already present rather than hypothetical.

### 6.1 §8 is inverted — and the halted strategy was already marked killed

**RULED AND ACTIONED 2026-08-31: `h1_momentum` is halted at the beat schedule.**
`LIVE_RISK_HALT` recorded at log **seq=82**.

The provenance check asked for before Phase 3 returned a worse answer than "unregistered". It was
registered, it was tested, and **it was killed** — then deployed anyway.

| seq | Event | Result |
|---|---|---|
| 59 | `h1_momentum_nested_wf` pre-registered, `edge_gate_role=hard_gate` | open |
| 60–64 | walk-forward, then stress | open |
| **65** | decisive stream declared `nested`; `nested_p = 0.1045` vs `prereg_alpha = 0.05` | **killed** |
| **81** | reaffirmed, recording `deployed_demo=1`, `first_fire_utc=2026-08-31`, `untradeable_at_100usd=1` | **killed** |

The `fixed` stream passed at p=0.010; the `nested` stream, which had been named decisive *in
advance*, failed at p=0.105. This is the exact case CLAUDE.md cites for the "name the decisive
stream before the run" rule, and the rule worked — the kill was correctly recorded.

**The falsification record was not the failure. The deployment was.** A mechanism carrying
`verdict=killed` from two separate entries was on the live beat schedule and first fired today,
and seq=81 had *already recorded* `untradeable_at_100usd=1` — the log contained the number that
should have blocked it.

The forward-data rationale for running a killed mechanism on demo is defensible in itself:
forward data is the only evidence uncontaminated by selection. What is not defensible is the risk
configuration it ran under.

### 6.2 The risk configuration

§8 states: "The code runs 2% risk and an 8% `DrawdownGuard`. The code is correct; the profile is
stale." Measured, this is backwards.

- `sizer.py`'s **default** is `risk_pct=0.02`. But the only scheduled, live-firing strategy,
  `h1_momentum`, sets `RISK_PCT = 0.05` (`strategy.py:71`) and passes it explicitly at line 285.
- `DrawdownGuard` is wired into **`crest_n_keel` and `asqs` only** — both retired from the beat
  schedule. `h1_momentum` does not import it.
- `h1_momentum` also uses `STOP_ATR_MULT = 10.0`.

So live behaviour matched the *stale profile* (5%), not the code default, and ran with no drawdown
protection at all. §8 is therefore a **finding, not a reconciliation**: updating the profile
document to 2%/8% would have left the divergence in place while making it invisible.

**Action taken:** the beat entry is commented out in `settings.py` with the breach statistics
recorded inline. Halted rather than re-parameterised — the minimal correct fix for placing bets
beyond budget is to stop placing them, and choosing new `RISK_PCT` / `STOP_ATR_MULT` values on a
live instrument outside the pipeline is precisely what the two-iteration rule forbids. Disabling
touches no numerical module, so the D8 fixtures are unaffected. Verified: only `sync-trades-hourly`
and `sync-account-daily` remain active; no strategy fires.

**Timing note.** `celery`, `celery-beat`, `mt5` and `mt5-test` containers do not currently exist,
so beat was not running and the halt could not orphan an open position. This matters for
sequencing: `h1_momentum` drives its own 12-bar exit via `manage_positions()` inside the same
scheduled task, so the halt had to land **before** the stack is brought back up for D1/D3a —
otherwise the strategy resumes at 5% unguarded the moment a terminal is available.

**Two structural fixes are owed**, because this bug was only *possible* by design, not by
misconfiguration — a strategy could set its own budget and silently omit the guard:

- **X26** — risk fraction becomes an account-level policy object that strategies read and cannot
  override.
- **X27** — `DrawdownGuard` becomes a precondition of the order path, not a per-strategy opt-in.
- **X28** — the 125/480 grid result becomes a permanent regression test.

Measured from the D8 sizer grid, at `h1_momentum`'s own geometry (10×ATR, 5% requested):

| Balance | ATR $14 | ATR $22 |
|---|---:|---:|
| $100 | 140% | 220% |
| $3,643 (demo) | 3.8% | 6.0% |

The demo balance is what makes this survivable. At the $100 capital base named in the project
constraints it is not.

---

## 7. D8 — golden fixtures (complete)

Generated by `phase0/generate_d8_fixtures.py` into `phase0/d8_fixtures/`, pinned to WMPS
`3db869a` with all three source files **verified clean at HEAD** and sha256-recorded.

| Fixture | Content |
|---|---|
| `sample_xauusd_h1.csv` | 6,000 H1 bars, 2024-01-02 → 2025-01-06. **52 weekend boundaries, 9 intraweek gaps, 1 gap >60h** — clears the ≥5,000 bars / ≥4 weekends / ≥1 holiday requirement |
| `indicators.csv` | `wma` (9, 20, 55), `hma` (21, 55), `stochastic` (14,3,3), `atr` (14) — full series |
| `sizer_grid.csv` | 480 cells: 5 balances × 8 ATRs × 3 risk pcts × 4 stop multipliers |
| `drawdown_guard.csv` | 20 rows — scripted equity sequence at 8% and 20%, covering first-evaluation no-trip, peak advance, exact-threshold boundary, trip, and recovery |
| `manifest.json` | commit SHA, per-file sha256, sample hash, NaN counts, gap census |

Floats are encoded with `repr()` (shortest round-trip), so string equality **is** exact float64
equality — what X22 requires instead of `approx`.

The OHLCV sample is committed alongside the fixtures, so they do not depend on the gitignored
`research/data/` tree.

### 7.1 The sizer grid quantifies the live risk bug

**125 of 480 cells (26%) realise more risk than their own budget.** Worst cell: $100 balance,
ATR $60, 0.5% requested → **600% of account realised**. The clamp does not fail gracefully; it
fails silently and without bound, because once `lots` is pinned at `min_lot` the realised risk is
whatever the stop distance makes it.

This is X7's assertion, already measured: T5 returning `lots=0` with
`MIN_POSITION_EXCEEDS_RISK_BUDGET` is not a refinement, it removes a live unbounded-risk path.

---

## 8. D9 — log and artifact migration (complete, with blockers)

Full plan in `docs/d9_migration_plan.md`. Headline: **the history the migration is meant to
preserve barely exists.**

| | |
|---|---|
| `research/` files tracked / untracked | **34 / 108** |
| Commits touching `research/` | **3** |
| Log entries committed / on disk | **30 / 82** — 52 entries exist only on this disk |
| `research/data/` | **gitignored** |

`git subtree split` today would carry 34 of 142 files across three commits. **Step 0 of the plan
is therefore to commit the outstanding research tree**, and that needs your go-ahead — it is the
one action that cannot be deferred without permanently losing what Phase 0.5 step 2 exists to
protect.

Self-containment: the chain is self-contained in substance, with three exceptions —

1. Two references into `qhf_harness`, which is itself being absorbed; they resolve through the
   `PROJECT_RENAME` mapping.
2. **A prior rename already went unrecorded.** Three artifacts are logged at
   `research/artifacts/…` but live at `research/pre/artifacts/…`; the pre/post reorganisation
   moved them without appending a path-migration event. The exact failure `PROJECT_RENAME` exists
   to prevent has already happened once, silently. That historical mapping must be carried in the
   Phase 0.5 event too.
3. `research/data/` is gitignored, and T9a's `ohlc_hash` assertion depends on it.

### 8.1 T9a is viable — verified

The seq=31 `flood_tide_h1` artifact's `ohlc_hash` was recomputed from the current
`research/data/XAUUSD_H1.csv` through the driver's own loader:

```
n_bars    124887          ohlc_hash  a8cd64270c5376ca
start     2004-06-11 07:00:00+00:00     artifact  a8cd64270c5376ca   ✓ MATCH
end       2025-12-31 23:00:00+00:00
```

Assertion 1 of 5 passes today. But it passes on an untracked file that nothing protects from a
silent re-pull, which would turn a data change into an apparent indicator regression — precisely
the misattribution T9a's ordered assertions are built to prevent. **Pin this file before writing
T9a.**

---

## 9. Blocked items, with collectors owed

Per Phase 0 acceptance, `BLOCKED` is acceptable; a substituted assumption is not.

| Task | Status | Dependency | Collector |
|---|---|---|---|
| D1 contract specs | **BLOCKED** | `mt5`/`mt5-test` containers down | Not yet written — owed |
| D3a forward spread collector | **BLOCKED** | Live MT5 | Not yet written — owed, **highest-value MT5 action** |
| D3b historical spread | **BLOCKED** | `copy_ticks_range` retention | Not yet written — owed |

Nothing in the D1/D3 path was substituted. D2 uses hand-entered specs and is stamped
`PROVISIONAL_SPECS` accordingly; under T1's refusal rule nothing derived from it may close an
acceptance criterion.

**Every day D3a is not running is a day of spread data that cannot be recovered.** Bring
`mt5-test` up when convenient; the D1 dump and the D3a switch-on belong in the same session.

---

## 10. What Phase 0 changed about the plan

### Ruled and actioned

1. **`h1_momentum` halted** at the beat schedule, logged `LIVE_RISK_HALT` at seq=82. It carried
   `verdict=killed` from seq=65 and seq=81 and was live anyway. Halted, not re-parameterised. (§6.1)
2. **O1's H4 prior withdrawn; prior is now H1.** Granularity is a hard constraint and dominates
   soft cost. D3 becomes a **veto** with pre-declared thresholds (<5% proceed / 5–10% marginal /
   >10% veto). A veto means "$100 cannot trade this system at any timeframe", not a new search. (§3.1)
3. **Research universe ≠ execution universe.** Pre-registration carries `universe` *and*
   `executable_subset`; failing the second is not a falsification. Executable universe at $100 is
   effectively one instrument. (§3.2)
4. **Benchmark ruling:** gate on full buy-and-hold, report exposure-matched as diagnostic. (§5.2)
5. **T9c retired** — T9b's fixture routes through `calculate_lot_size`, so it covers sizer
   integration. Reason recorded. (§6)
6. **Phase 2b targets effective N ≥ 4**, which requires breaking USD dominance rather than adding
   majors. (§4)

### New tests owed

| ID | Assertion |
|---|---|
| **X26** | Risk fraction is an account-level policy object; a strategy cannot override it |
| **X27** | `DrawdownGuard` is a precondition of the order path, not a per-strategy opt-in |
| **X28** | The 125/480 over-budget grid result is a permanent regression test |

### Open, needing your decision

7. **Commit the research tree** before Phase 0.5 step 2, or the subtree migration preserves three
   commits and 34 of 142 files. I have not committed anything. (§8)
8. **Pin `XAUUSD_H1.csv`** before T9a is written — it is gitignored and T9a's `ohlc_hash`
   assertion depends on it. (§8.1)
9. **MinTRL moment convention.** My normal-returns figures are 30–70% below the quoted ones;
   the gap is consistent with γ₃ ≈ −0.5, γ₄ ≈ 5. Confirm the convention, and T7 should make
   γ₃/γ₄ required arguments rather than defaulting to normal. (§4.1)

### Owed collectors (blocked on MT5)

D1 contract-spec dump, D3a forward spread collector, D3b historical spread. All three must be
written so they run unattended. **The halt must stay in place when the stack comes back up** — it
is the reason bringing `mt5-test` up is now safe.
