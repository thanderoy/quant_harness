"""Cross-repo parity contract for the Deflated Sharpe Ratio.

`research.post.dsr` is the **canonical** DSR implementation for this repo. The
walk-forward harness ships its own twin at `qhf/metrics/deflated.py` (separate
repo, separate venv) so it can deflate Sharpe inline without importing this
package. Two implementations means they can silently drift.

These golden vectors are the contract that pins both to the same numbers. They
exercise the deterministic, scalar-only primitives (no RNG, no data) so the
expected values are reproducible byte-for-byte across implementations:

  - ``psr(sr_hat, sr_star, n_obs, skew, kurtosis)``  — Probabilistic Sharpe
  - ``expected_max_sharpe(n_trials, var_sr)``        — deflated benchmark

If you change the math in either repo, these values must move together. The
same table is published in ``research/README.md`` as the qhf-side obligation.
Bump both deliberately; never let one side drift unannounced.
"""

from __future__ import annotations

from research.post.dsr import expected_max_sharpe, psr

# Locked outputs of research.post.dsr — the contract qhf/metrics/deflated.py
# must reproduce. (inputs) -> expected output.
PSR_GOLDEN = [
    # (sr_hat, sr_star, n_obs, skew, kurtosis) -> psr
    ((0.05, 0.00, 500, 0.0, 3.0), 0.8678355793218056),
    ((0.08, 0.02, 1000, -0.5, 6.0), 0.968021483091013),
    ((0.03, 0.01, 250, 0.4, 9.0), 0.6244603832213759),
]

EXPECTED_MAX_SHARPE_GOLDEN = [
    # (n_trials, var_sr) -> expected_max_sharpe
    ((10, 0.001), 0.04979317033695131),
    ((100, 0.001), 0.08002469001362901),
    ((1000, 0.0025), 0.16275607554588317),
]

# Tight: these are deterministic closed-form evaluations, not Monte Carlo.
TOL = 1e-12


def test_psr_golden_vectors():
    for args, expected in PSR_GOLDEN:
        got = psr(*args)
        assert abs(got - expected) < TOL, f"psr{args}: {got!r} != {expected!r}"


def test_expected_max_sharpe_golden_vectors():
    for args, expected in EXPECTED_MAX_SHARPE_GOLDEN:
        got = expected_max_sharpe(*args)
        assert abs(got - expected) < TOL, (
            f"expected_max_sharpe{args}: {got!r} != {expected!r}"
        )
