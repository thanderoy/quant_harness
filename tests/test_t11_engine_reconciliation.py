"""T11 — reconciling the research engines against the ported `resources`.

T10 moved `engines/indicators.py` and `engines/sizer.py` without touching
them, deliberately: merging a rename with a parity task would have made any
deviation impossible to attribute to one or the other. This is the parity
task, and it is where the two copies are compared.

There are three implementations of this arithmetic in the repository, not
two. `resources` now holds the ported one; `research.engines` holds the one
every recorded harness result was produced by; and
`research.post.sweeps.cnk_engine` holds a third, written for the sweep and
documented there as a port of the second. This file reconciles the first two.

**Nothing here changes any code.** Deduplication would be the obvious next
move and it is deliberately not made: `research.engines` is load-bearing for
results already in the hash chain, and a module that produced a logged Sharpe
cannot be edited into agreement with a newer one without the logged number
quietly coming to mean something else. What this file does instead is pin the
relationship — where the copies agree, that agreement becomes an assertion
that fails if either drifts; where they disagree, the disagreement is
measured exactly and cannot widen unnoticed.

The disagreement is one line, and it is a live-versus-backtest one. See
`resources.indicators.oscillators` for the mechanism.
"""

from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd
import pytest

from research.engines import indicators as engines
from research.engines.sizer import calculate_lot_size
from resources.indicators import atr, hma, stochastic, wma

pytestmark = [pytest.mark.x("X22")]

FIXTURES = (pathlib.Path(__file__).resolve().parents[1] / "packages"
            / "qh-resources" / "tests" / "fixtures")


def f64(v: float) -> str:
    return "" if (v is None or (isinstance(v, float) and np.isnan(v))) else repr(float(v))


def read_fixture(name: str) -> pd.DataFrame:
    return pd.read_csv(FIXTURES / name, dtype=str, keep_default_na=False)


@pytest.fixture(scope="module")
def sample() -> pd.DataFrame:
    df = read_fixture("sample_xauusd_h1.csv")
    out = df[["open", "high", "low", "close"]].astype(float)
    out.index = pd.to_datetime(df["datetime"], utc=True).to_numpy()
    return out


@pytest.mark.parametrize("name", ["wma_9", "wma_20", "wma_55", "hma_21",
                                  "hma_55", "atr_14"])
def test_the_engines_and_resources_agree_bit_for_bit(sample, name):
    """Five of the six ported functions are the same code twice over.

    Asserted rather than assumed, because "it's a copy" is a claim with a
    shelf life. These are compared as strings over 6,000 bars, so the day
    somebody optimises one of the two, this says so instead of the difference
    surfacing as a backtest that stopped matching.
    """
    kind, period = name.rsplit("_", 1)
    period = int(period)
    if kind == "atr":
        mine = atr(sample["high"], sample["low"], sample["close"], period)
        theirs = engines.atr(sample["high"], sample["low"], sample["close"], period)
    else:
        fn = {"wma": wma, "hma": hma}[kind]
        mine = fn(sample["close"], period)
        theirs = getattr(engines, kind)(sample["close"], period)

    got, want = mine.map(f64).to_numpy(), theirs.map(f64).to_numpy()
    mismatched = np.flatnonzero(got != want)
    assert len(mismatched) == 0, (
        f"{name}: {len(mismatched)} cells differ between "
        f"research.engines and resources. First at row {mismatched[0]}: "
        f"engines {want[mismatched[0]]!r}, resources {got[mismatched[0]]!r}")


def test_the_stochastic_divergence_is_the_warm_up_and_only_the_warm_up(sample):
    """The one real disagreement, bounded to the bar.

    `research.engines` fills the warm-up with a fabricated 50.0 where the
    ported version leaves NaN. That is 13 bars at the default 14/3/3 — rows 2
    through 14 inclusive — and *nothing else*. Bounding it matters more than
    naming it: "they differ in the warm-up" would still be true if a later
    edit changed a value at bar 4,000, and this would not.

    The engines' reading was adopted on purpose during the crest_n_keel sweep
    parity work, to match the canonical `btpy_runner` strategies. So it is not
    a bug that slipped in; it is a choice that every recorded result now
    depends on, which is exactly why it is pinned rather than fixed.
    """
    k, d = stochastic(sample["high"], sample["low"], sample["close"])
    ek, ed = engines.stochastic(sample["high"], sample["low"], sample["close"])

    differing = np.flatnonzero(k.map(f64).to_numpy() != ek.map(f64).to_numpy())
    assert list(differing) == list(range(2, 15)), (
        f"%K differs on rows {list(differing)[:20]}; expected exactly the "
        "warm-up, rows 2-14")

    # Every differing bar is NaN here. Over there they split into two groups,
    # and the split is the part worth knowing: rows 2-12 are exactly the
    # fabricated 50.0, but rows 13 and 14 are *blends*. %K is a 3-bar mean of
    # raw %K, and raw %K only becomes real at row 13, so the invented values
    # are still inside the smoothing window for two bars after the warm-up
    # ends. The fabrication does not stop where the NaN padding stops — it
    # leaks forward into bars that look, from the outside, fully warmed up.
    assert k.iloc[differing].isna().all()
    fabricated, blended = ek.iloc[differing[:11]], ek.iloc[differing[11:]]
    assert (fabricated == 50.0).all()
    assert not (blended == 50.0).any()
    assert (blended < 50.0).all() and (blended > 0.0).all()

    d_differing = np.flatnonzero(d.map(f64).to_numpy() != ed.map(f64).to_numpy())
    assert d_differing.max() < 20, "the %D divergence has left the warm-up"


def test_the_engine_sizer_still_reproduces_the_d8_grid_exactly(sample):
    """`research.engines.sizer` is the old sizer, and must stay the old sizer.

    It is the code the logged backtests sized with, so its value is entirely
    in being unchanged — including the min-lot clamp that T5 replaced with a
    refusal. All 480 cells, exact string equality.

    This is the assertion that makes the sizer comparison in
    `test_x22_d8_parity` mean something: that file shows `size_position`
    differing from the fixture in four named ways, and this one shows the
    fixture is still an accurate record of what the old code does, rather than
    both having drifted together.
    """
    grid = read_fixture("sizer_grid.csv")
    for i, row in grid.iterrows():
        lots, eff = calculate_lot_size(
            account_balance=float(row["account_balance"]),
            atr_value=float(row["atr_value"]),
            risk_pct=float(row["risk_pct"]),
            sl_atr_multiplier=float(row["sl_atr_multiplier"]),
        )
        assert f64(lots) == row["lots"], f"row {i}: lots"
        assert f64(eff) == row["effective_atr"], f"row {i}: effective_atr"


def test_the_old_sizer_really_does_breach_its_own_budget(sample):
    """The bug T5 exists to fix, demonstrated on the module that still has it.

    Without this, "125 of 480 cells over budget" is a number in a docstring.
    Here it is a property of code that is still imported and still runs.
    """
    grid = read_fixture("sizer_grid.csv")
    breaches = grid[grid["over_budget"] == "True"]
    assert len(breaches) == 125

    worst = max(float(r["realised_risk_pct"]) for _, r in breaches.iterrows())
    assert worst > 1.0, (
        "the worst D8 cell no longer risks more than the whole account; the "
        "fixture or the engine sizer has changed")
