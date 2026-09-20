# CLAUDE.md — quant_harness

Repo-specific discipline. The spec is `docs/REWRITE.md`, the findings are the
research log, the current state is `docs/STATUS.md`. This file is only the
rules that no test can enforce — everything mechanisable belongs in
`tests/test_x_coverage.py`, `tests/test_docs_are_true.py`, or a gate beside
the thing it guards.

Each rule below was bought with a specific miss. The miss is named so the rule
can be argued with rather than obeyed.

---

## 1. Re-measure before you state it

Any figure describing **current** state — disk free, test counts, CI status,
open PRs, how many rows a table has — is re-derived in the turn it is stated,
or it is dated and marked as of then.

*Bought 2026-09-20:* a "92% disk, 9.7 GB free" figure was carried across many
turns and repeated as current. It was days stale; the real number was 73%.
Nothing was wrong with the original measurement, only with reusing it.

Corollary: **a measurement of one branch is not a measurement of the repo.**
"525 passed, 24 skipped" was true on a feature branch and false on `develop`,
where a branch-comparison test skips. Published counts come from `develop` or
from CI, and name the condition they hold under.

## 2. A change that improves already-recorded metrics gets more scrutiny, not less

When a correction would make past results look better, stop and separate the
measurement from the decision to apply it. Record the measurement; put the
re-pricing to the user.

*Bought 2026-09-20:* commission measured at 0.00 on every live deal, against a
$7.00/lot constant. Zeroing it is probably right and would improve every
metric in the log — and it is only half the change, because the spread that
pays for the missing commission is measured at 0.17 where the model assumes
0.22. Swapping an over-cost for an under-cost is not a correction.

## 3. Prefer making a value deterministic over bounding a non-deterministic one

A tolerance around a value that moves is a contract with the tolerance, not
with the value. If the non-determinism can be removed at the source, remove it.

*Bought 2026-09-20:* five D8 columns were bounded at 16 ULP because `np.dot`
dispatches to BLAS. Re-running the generator on the same machine against
byte-identical sources reproduced four of five only to 5 ULP — numpy had moved
underneath the fixture, and the drifting set was not even stable. `math.fsum`
is correctly rounded, so the bound was retired rather than widened.

## 4. Answer the question, then ask whether it was the right one

A resolved question is not the same as a resolved problem. When the answer
arrives, check the premise it assumed.

*Bought 2026-09-20:* "does commission apply to gold?" was researched at length
across two contradicting Pepperstone sources. The measurement showed the
account pays no commission on *anything* — it is not on the Razor schedule at
all, so the question was moot rather than answered.

## 5. Never weaken a gate to accommodate new prose

If a check fires on something you just wrote, the default is to change what you
wrote. Widening an allowlist is a last resort and never for the files most
likely to drift.

*Bought 2026-09-20:* a historical note reintroduced the pre-rename package
token and the T10 gate caught it. The gate has an allowlist; adding README and
STATUS to it would have blinded it in the two files where a stale reference
does the most damage. The note was reworded instead.

Where a check is genuinely too strict, encode the *distinction* rather than
loosening the pattern — `describes_rather_than_instructs` in
`tests/test_docs_are_true.py` is the worked example: a doc describing the
spec's target or the repo's past is not making a claim about now.

## 6. A gate that cannot fail is decoration

Every guard test is proven against the regression it exists to catch, by
reintroducing that regression once and watching it fail. `DEFERRED` emptying,
an allowlist entry going stale, a summary drifting from its table — each has
an anti-rot check, and each of those was watched to fire.

---

## Standing facts that are easy to get wrong

- **`PYTHONPATH` is pytest-only.** The four package paths live in
  `[tool.pytest.ini_options] pythonpath`. Anything outside pytest — `examples/`,
  an ad-hoc script — needs them passed explicitly.
- **pandas' default CSV float parser is lossy.** Reading a `repr`-encoded
  fixture back needs `float_precision="round_trip"`, or Python's own
  `float(str)`. A harness written without it reports ULP drift that is not in
  the file.
- **WMPS is frozen** under spec §1.3 — mirrored bug fixes only. The port may
  deliberately diverge from it (see `wma`), but the divergence is measured and
  recorded, never silent.
- **Parity fixtures and audits are not trials.** They use
  `append_record(...)`, which forces `counts_as_trial=False`. `trial_count()`
  is the DSR haircut denominator and only real hypotheses move it.
- **A sweep's leader is not a candidate.** Proven twice (seq=49, seq=68).
  Sweeps describe a surface; only a nested walk-forward with the pool control
  is evidence of generalisation.
