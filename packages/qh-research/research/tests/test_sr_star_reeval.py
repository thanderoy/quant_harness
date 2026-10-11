"""Phase 2b: the shelved XAUUSD DSRs re-priced against SR*.

What these pin, in the order a reader should trust them:

1. The benchmark helper reproduces D5 exactly from the in-repo H1 file, so
   the same-window figures are D5's method and not a lookalike.
2. The saved streams are the files the manifest describes.
3. The fast regenerations rebuild those streams bit-for-bit from the frozen
   runners, and the read streams match their out-of-repo sources.
4. With SR* = 0 every row reproduces the DSR the log recorded. Only then do
   the other columns mean "the same evaluation, benchmark changed".
5. The committed artifact is what the module produces now.
"""
from __future__ import annotations

import json
import math

import numpy as np
import pytest

from research.post import sr_star_reeval as S
from research.post.sweeps import data as sweep_data

D5_XAUUSD = 0.634324777595297
FAST = ["h1_momentum_unfiltered", "h1_momentum_lowvol",
        "zlch_sweep_leader", "flood_tide_median_config"]
READ = {"cnk_sweep_leader": "crest_n_keel/cnk_leader_returns.csv",
        "crest_n_keel_wf_24h": "crest_n_keel/crest_n_keel_oos_returns_24h.csv",
        "crest_n_keel_wf_session":
            "crest_n_keel/crest_n_keel_oos_returns_session.csv"}


def _have(tf: str) -> bool:
    return (sweep_data.DATA_DIR / f"XAUUSD_{tf}.csv").exists()


needs_h1 = pytest.mark.skipif(not _have("H1"), reason="XAUUSD_H1.csv absent")
needs_h1_h4 = pytest.mark.skipif(not (_have("H1") and _have("H4")),
                                 reason="XAUUSD_H1/H4.csv absent")


@pytest.fixture(scope="module")
def table() -> dict:
    return S.build_table()


@needs_h1
def test_same_window_helper_reproduces_d5_over_the_full_file():
    bh = S.same_window_buy_and_hold("2000-01-01", "2030-01-01")
    assert bh["start"] == "2004-06-14" and bh["end"] == "2025-12-31"
    assert bh["n_days"] == 5515
    assert bh["sharpe_annualised"] == pytest.approx(D5_XAUUSD, abs=1e-12)
    assert S.d5_xauusd_annualised() == pytest.approx(D5_XAUUSD, abs=1e-15)


def test_saved_streams_match_the_manifest():
    manifest = json.loads(S.MANIFEST.read_text())
    assert set(manifest) == {ev.key for ev in S.EVALUATIONS}
    for key, meta in manifest.items():
        assert S._sha256(S._stream_path(key)) == meta["sha256"], key
        r, _, _ = S.read_stream(key)
        assert r.size == meta["n"]


@needs_h1_h4
@pytest.mark.parametrize("key", FAST)
def test_fast_regeneration_is_bit_identical(key):
    r_new, held_new, meta_new = S.REGENERATORS[key]()
    r_saved, held_saved, meta_saved = S.read_stream(key)
    assert np.array_equal(r_new, r_saved)
    assert np.array_equal(held_new, held_saved)
    assert meta_new["ppy"] == meta_saved["ppy"]


@pytest.mark.parametrize("key,rel", sorted(READ.items()))
def test_read_streams_match_their_source(key, rel):
    src = S.QH_DATA_DIR / rel
    if not src.exists():
        pytest.skip(f"out-of-repo source absent: {src}")
    _, _, meta = S.read_stream(key)
    assert meta["source_sha256"] == S._sha256(src)


@needs_h1_h4
def test_zero_benchmark_reproduces_every_logged_dsr(table):
    for ev in table["evaluations"]:
        for row in ev["rows"]:
            assert row["reproduced"], (ev["key"], row["n_trials"],
                                       row["logged_dsr"], row["dsr"]["zero"])


@needs_h1_h4
def test_benchmarks_are_per_trade_at_the_streams_own_frequency(table):
    for ev in table["evaluations"]:
        ppy = ev["stream"]["ppy"]
        b = ev["benchmarks_per_obs"]
        assert b["d5"] == pytest.approx(D5_XAUUSD / math.sqrt(ppy), rel=1e-12)
        assert b["same_window"] == pytest.approx(
            ev["same_window_buy_and_hold"]["sharpe_annualised"] / math.sqrt(ppy),
            rel=1e-12)
        # Never the daily per-obs figure: that would be sqrt(252/ppy) off.
        assert b["d5"] != pytest.approx(D5_XAUUSD / math.sqrt(252), rel=1e-3)


@needs_h1_h4
def test_a_positive_benchmark_can_only_lower_dsr(table):
    for ev in table["evaluations"]:
        for name, sr_star in ev["benchmarks_per_obs"].items():
            if sr_star <= 0:
                continue
            for row in ev["rows"]:
                assert row["dsr"][name] <= row["dsr"]["zero"] + 1e-15


@needs_h1_h4
def test_committed_artifact_is_current(table):
    committed = json.loads(S.OUT.read_text())
    assert _close(json.loads(json.dumps(table)), committed)


def _close(a, b, tol: float = 1e-12) -> bool:
    """Structural equality with a float tolerance, for nested JSON."""
    if isinstance(a, dict):
        assert isinstance(b, dict) and set(a) == set(b), (sorted(a), sorted(b))
        return all(_close(a[k], b[k], tol) for k in a)
    if isinstance(a, list):
        assert isinstance(b, list) and len(a) == len(b)
        return all(_close(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, float) and isinstance(b, (int, float)):
        assert math.isclose(a, b, rel_tol=tol, abs_tol=tol), (a, b)
        return True
    assert a == b, (a, b)
    return True


def test_no_log_writes_are_made_by_the_module():
    source = (S.Path(S.__file__)).read_text()
    for forbidden in ("log_dsr_evaluation(", "append_record(",
                      "from research import log", "research.log"):
        assert forbidden not in source, forbidden
