"""Parity contract for MinTRL, held open for its twin.

`research.post.mintrl` is the canonical implementation. T7 specifies a
sibling under `resources/metrics/`, mirroring the one that already exists
between `research.post.dsr` and the harness's `deflated.py`. That twin has
not been written yet — `resources/metrics/` does not exist.

These vectors are pinned now rather than when the twin appears, for the same
reason the DSR ones were: the contract is worth more written down before
there is a second implementation to argue with. Any change to the math here
must move these numbers deliberately, and the twin must reproduce them.

Scalar-only, no RNG, no data — reproducible byte-for-byte.
"""

from __future__ import annotations

import pytest

from research.post.mintrl import min_decidable_sharpe, min_trl

MIN_TRL_GOLDEN = [
    # (sr_hat, sr_star, skew, kurtosis) -> min_trl
    ((0.05, 0.00, 0.0, 3.0), 1084.570150970246),
    ((0.08, 0.02, -0.5, 6.0), 788.6137593402816),
    ((0.03, 0.01, 0.4, 9.0), 6695.867262361736),
]

MIN_DECIDABLE_GOLDEN = [
    # (n_obs, sr_star, skew, kurtosis) -> min decidable sharpe
    ((500, 0.00, 0.0, 3.0), 0.07373377367402656),
    ((1000, 0.02, -0.5, 6.0), 0.07315476817998381),
    ((250, 0.01, 0.4, 9.0), 0.1132090852690369),
]

TOL = 1e-12


def test_min_trl_golden_vectors():
    for (sr, sr_star, skew, kurt), expected in MIN_TRL_GOLDEN:
        got = min_trl(sr, sr_star, skew=skew, kurtosis=kurt).min_trl
        assert got == pytest.approx(expected, rel=TOL), (sr, sr_star)


def test_min_decidable_sharpe_golden_vectors():
    for (n, sr_star, skew, kurt), expected in MIN_DECIDABLE_GOLDEN:
        got = min_decidable_sharpe(n, sr_star, skew=skew, kurtosis=kurt)
        assert got == pytest.approx(expected, rel=TOL), (n, sr_star)


def test_the_two_tables_are_inverses_of_each_other():
    """Cross-check the pinned values against each other, not just themselves."""
    for (n, sr_star, skew, kurt), floor in MIN_DECIDABLE_GOLDEN:
        back = min_trl(floor, sr_star, skew=skew, kurtosis=kurt).min_trl
        assert back == pytest.approx(n, rel=1e-9)
