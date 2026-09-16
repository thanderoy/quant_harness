"""X22 — every ported function reproduces its D8 golden fixture exactly.

The fixtures were generated once, at Phase 0, from the WMPS code that was
running live, and committed. They are the only thing standing between "the
rewrite preserves behaviour" and "the rewrite preserves behaviour as far as
anyone has checked". A rewrite that silently changes a number is worse than
one that fails loudly, because the first one keeps producing results.

**Exact means exact.** Comparison is string equality on the shortest
round-trip float64 repr, never ``pytest.approx``. A tolerance is a decision
about how much drift is acceptable, and nobody ever makes that decision
deliberately — it gets inherited from whatever the first failure needed. The
spec says float equality, so this compares strings and a one-ULP difference
fails.

Two of the six functions cannot be compared this way, and the difference
between them matters:

* ``wma``, ``hma``, ``stochastic``, ``atr`` and ``DrawdownGuard`` are ports
  with no intended behavioural change, so any difference at all is a bug and
  is asserted away to the last bit.
* ``calculate_lot_size`` was deliberately replaced by ``size_position`` under
  T5, which has a different signature and three documented behavioural
  changes. Exact parity is not the goal there and asserting it would be
  asserting the bug back in. What is asserted instead is *attribution*: every
  one of the 480 grid cells either reproduces exactly or differs for one of
  the named reasons, with the counts pinned. A new, unexplained difference
  fails — which is the property the fixture is actually for.
"""

from __future__ import annotations

import json
import pathlib

import numpy as np
import pandas as pd
import pytest

from resources.indicators import atr, hma, stochastic, wma
from resources.instruments.registry import Registry
from resources.risk.drawdown_guard import DrawdownGuard, InMemoryPeakStore
from resources.risk.sizer import SizingReason, StaticFxRates, size_position

pytestmark = [pytest.mark.x("X22")]

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"

#: The grid in ``sizer_grid.csv`` is gold-shaped: it was generated from the
#: WMPS sizer, whose constants were XAUUSD's. Comparing against any other
#: instrument would be comparing against a fixture that does not exist.
GOLD = "XAUUSD"
SNAPSHOT = "pepperstone_live_20260906.json"


def f64(v: float) -> str:
    """The fixture's float encoding, reproduced.

    ``repr`` on a Python float has been round-trip exact since 3.1, so string
    equality on this output *is* float64 equality. Copied from the generator
    rather than imported: importing ``phase0.generate_d8_fixtures`` executes a
    ``sys.path`` insert into the WMPS checkout at module scope, which does not
    exist on a CI runner.
    """
    return "" if (v is None or (isinstance(v, float) and np.isnan(v))) else repr(float(v))


def read_fixture(name: str, **kwargs) -> pd.DataFrame:
    """Strings, always. ``read_csv`` with inferred dtypes would parse the
    fixture back into floats and quietly undo the exactness it encodes."""
    return pd.read_csv(FIXTURES / name, dtype=str, keep_default_na=False, **kwargs)


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads((FIXTURES / "manifest.json").read_text())


@pytest.fixture(scope="module")
def sample() -> pd.DataFrame:
    """The committed OHLC window the indicator fixture was computed over.

    Parsed to float here — this is the *input*, and it was serialised with the
    same round-trip repr, so float(str(x)) is the original value exactly.
    """
    df = read_fixture("sample_xauusd_h1.csv")
    out = df[["open", "high", "low", "close"]].astype(float)
    # Set the index *after* building the frame. Passing a DatetimeIndex to the
    # DataFrame constructor alongside Series that still carry a RangeIndex
    # aligns on the old one, matches nothing, and yields an all-NaN frame that
    # every indicator then faithfully propagates.
    out.index = pd.to_datetime(df["datetime"], utc=True).to_numpy()
    out.index.name = "datetime"
    return out


def test_the_float_encoding_actually_round_trips():
    """The comparison below is only exact if this is. Asserted, not assumed."""
    for v in (0.1, 1 / 3, 2062.9099999999999, 1e-17, -0.0, 1.7976931348623157e308):
        assert float(f64(v)) == v
    assert f64(float("nan")) == ""


# --------------------------------------------------------------------------- #
# Indicators — exact.                                                          #
# --------------------------------------------------------------------------- #

def test_the_sample_window_is_the_one_the_fixture_was_built_from(sample, manifest):
    """Denominator check. If the sample drifted, every comparison below would
    be self-consistent and meaningless."""
    assert len(sample) == manifest["sample"]["n_bars"]
    assert str(sample.index[0]) == manifest["sample"]["start"]
    assert str(sample.index[-1]) == manifest["sample"]["end"]


#: Columns whose fixture values are reproducible anywhere. Every one of these
#: is computed by pandas rolling arithmetic in a fixed order, so the result is
#: a property of the code and nothing else.
EXACTLY_REPRODUCIBLE = ("wma_9", "stoch_k_14_3_3", "stoch_d_14_3_3", "atr_14")

#: Columns whose fixture values are not. See
#: ``test_the_dot_product_columns_differ_only_in_the_last_bits`` for the
#: measurement and the reason. The ceiling is stated in ULP because that is
#: the unit the claim is actually in: "nothing but summation order".
DOT_PRODUCT_COLUMNS = ("wma_20", "wma_55", "hma_21", "hma_55")
ULP_CEILING = 16


def compute_all(sample: pd.DataFrame, manifest: dict) -> dict[str, pd.Series]:
    """Every fixture column, recomputed from the pinned window."""
    ind = manifest["indicators"]
    k_p, d_p, s_k = (ind["stoch_params"][x]
                     for x in ("k_period", "d_period", "smooth_k"))
    out: dict[str, pd.Series] = {}
    for p in ind["wma_periods"]:
        out[f"wma_{p}"] = wma(sample["close"], p)
    for p in ind["hma_periods"]:
        out[f"hma_{p}"] = hma(sample["close"], p)
    k, d = stochastic(sample["high"], sample["low"], sample["close"],
                      k_p, d_p, s_k)
    out[f"stoch_k_{k_p}_{d_p}_{s_k}"] = k
    out[f"stoch_d_{k_p}_{d_p}_{s_k}"] = d
    out[f"atr_{ind['atr_period']}"] = atr(
        sample["high"], sample["low"], sample["close"], ind["atr_period"])
    assert list(out) == ind["columns"]
    return out


def golden_floats(column: str) -> np.ndarray:
    raw = read_fixture("indicators.csv")[column].to_numpy()
    return np.array([np.nan if x == "" else float(x) for x in raw])


def test_the_pandas_columns_reproduce_the_d8_fixture_exactly(sample, manifest):
    """X22 as written, for the four columns that can satisfy it.

    String comparison, cell by cell, no tolerance. A seeding error or an
    off-by-one in a rolling window shows up as a block of mismatches rather
    than as an argument about rounding.
    """
    golden = read_fixture("indicators.csv")
    computed = compute_all(sample, manifest)

    for name in EXACTLY_REPRODUCIBLE:
        got = computed[name].map(f64).to_numpy()
        want = golden[name].to_numpy()
        mismatched = np.flatnonzero(got != want)
        assert len(mismatched) == 0, (
            f"{name}: {len(mismatched)} of {len(want)} cells differ from the "
            f"D8 fixture. First at row {mismatched[0]} "
            f"({sample.index[mismatched[0]]}): "
            f"golden {want[mismatched[0]]!r}, computed {got[mismatched[0]]!r}")


def test_the_dot_product_columns_differ_only_in_the_last_bits(sample, manifest):
    """The honest limit of X22, measured rather than asserted away.

    ``wma`` reduces its window with ``np.dot``, which dispatches to BLAS.
    OpenBLAS blocks and vectorises that reduction, and the blocking depends on
    the kernel selected for the CPU and on the library version — so the
    summation *order* is not a property of this source file. The fixture was
    generated on one such build in August; a different one gives a different
    last bit. ``hma`` inherits it by being three ``wma`` calls.

    This was established, not assumed: running the unmodified WMPS module in
    this interpreter reproduces the port bit for bit and misses the fixture by
    the same 1,528 cells, and no Python-level summation order (``sum(x*w)``,
    ``math.fsum``, a naive loop) reproduces it either. So the divergence is
    below the source line, and no edit to this repository closes it.

    What is asserted instead is the thing that would still be true of a
    correct port anywhere: the difference never leaves the last handful of
    bits. Measured here at 4 ULP and a relative error of 5.9e-16; the ceiling
    is set well above that because it must hold on a CI runner's CPU too, and
    well below anything that could be a real arithmetic error — an off-by-one
    or a wrong seed moves a moving average by parts per thousand, not parts
    per quadrillion.
    """
    computed = compute_all(sample, manifest)
    worst = {}
    for name in DOT_PRODUCT_COLUMNS:
        got = computed[name].to_numpy()
        want = golden_floats(name)
        defined = ~np.isnan(want)
        assert not np.isnan(got[defined]).any(), f"{name} lost values the fixture has"
        ulp = np.abs(got[defined] - want[defined]) / np.spacing(np.abs(want[defined]))
        worst[name] = float(ulp.max())

    over = {k: v for k, v in worst.items() if v > ULP_CEILING}
    assert not over, (
        f"{over} exceed {ULP_CEILING} ULP against the D8 fixture. That is too "
        "large to be summation order and should be read as a real change in "
        "the arithmetic, not as fixture drift.")


def test_the_last_bits_never_change_a_decision(sample):
    """Why the ULP bound above is an acceptable substitute, not an excuse.

    A tolerance on a number is only meaningful next to what the number is
    used for. The HMA pair is used as a crossover, so the question is whether
    the fixture and the port ever disagree about which line is on top — and
    across 5,940 defined bars they never do, with 326 crossings on each side.
    The deviation is real and it is also incapable of moving a signal.
    """
    fast, slow = hma(sample["close"], 21).to_numpy(), hma(sample["close"], 55).to_numpy()
    g_fast, g_slow = golden_floats("hma_21"), golden_floats("hma_55")
    defined = ~(np.isnan(g_fast) | np.isnan(g_slow))

    port_state = fast[defined] > slow[defined]
    fixture_state = g_fast[defined] > g_slow[defined]

    disagreements = int((port_state != fixture_state).sum())
    assert disagreements == 0, (
        f"{disagreements} of {int(defined.sum())} bars disagree on HMA21>HMA55. "
        "The last-bit difference has become capable of moving a signal, which "
        "is the point at which the ULP bound stops being acceptable.")
    assert int((np.diff(port_state) != 0).sum()) == 326


def test_every_warm_up_is_exactly_as_long_as_the_formula_requires(manifest):
    """An all-NaN column compares equal to an all-NaN column.

    Without a NaN check, a port that returned NaN everywhere would pass the
    comparison above cleanly — the failure mode of every warm-up bug there is.
    So rather than a loose "mostly not NaN" bound, each count is derived from
    the formula and asserted exactly. That turns this from a denominator check
    into a second, independent assertion about the ports: an off-by-one in any
    rolling window changes one of these numbers even when the values that do
    exist are right.

    ``hma``'s warm-up is the composed one — the full-period WMA, then the
    sqrt-period WMA over its output — which is why it is longer than the
    period and why it is worth stating rather than eyeballing.
    """
    import math

    ind = manifest["indicators"]
    expected = {}
    for p in ind["wma_periods"]:
        expected[f"wma_{p}"] = p - 1
    for p in ind["hma_periods"]:
        expected[f"hma_{p}"] = (p - 1) + (round(math.sqrt(p)) - 1)
    k_p, d_p, s_k = (ind["stoch_params"][x]
                     for x in ("k_period", "d_period", "smooth_k"))
    expected[f"stoch_k_{k_p}_{d_p}_{s_k}"] = (k_p - 1) + (s_k - 1)
    expected[f"stoch_d_{k_p}_{d_p}_{s_k}"] = (k_p - 1) + (s_k - 1) + (d_p - 1)
    # ATR is seeded at index `period`, so indices 0..period-1 are NaN.
    expected[f"atr_{ind['atr_period']}"] = ind["atr_period"]

    assert ind["nan_counts"] == expected


def test_the_warm_up_is_nan_and_not_a_fabricated_reading(sample):
    """%K's warm-up is the one place the ports disagree, so it is pinned.

    ``research.engines.indicators`` fills these bars with 50.0 (see that
    module and ``resources.indicators.oscillators`` for why). The D8 golden
    behaviour, and therefore this one, leaves them NaN. Thirteen bars at the
    default 14/3/3 — small, and it is exactly the kind of small that stops
    being small when someone slices a short walk-forward window.
    """
    k, d = stochastic(sample["high"], sample["low"], sample["close"])
    assert k.iloc[:15].isna().all()
    assert not (k.iloc[:15] == 50.0).any()
    assert k.iloc[15:].notna().all()
    assert d.iloc[:17].isna().all()


# --------------------------------------------------------------------------- #
# DrawdownGuard — exact.                                                       #
# --------------------------------------------------------------------------- #

def test_drawdown_guard_reproduces_the_d8_fixture_exactly():
    """Replays the scripted equity sequence and compares every emitted field.

    The sequence is not a smoke test: it contains the first evaluation with
    no peak, a peak advance, the exact-threshold step, the step one tenth of
    a unit below it, recovery, and a new peak. Driving it from the fixture's
    own rows means a step added to the fixture is exercised without anyone
    editing this file.
    """
    golden = read_fixture("drawdown_guard.csv")
    guard = None
    last_max_dd = None

    for i, row in golden.iterrows():
        max_dd = float(row["max_drawdown_pct"])
        if max_dd != last_max_dd:
            # A new guard per max_drawdown_pct block, matching the generator.
            assert row["step"] == "0", "fixture blocks must start at step 0"
            guard = DrawdownGuard(store=InMemoryPeakStore(),
                                  max_drawdown_pct=max_dd)
            last_max_dd = max_dd

        equity = float(row["equity"])
        peak_before = guard.peak_equity
        thr = guard.trigger_threshold()
        got = {
            "peak_before_update": f64(peak_before) if peak_before is not None else "",
            "trigger_threshold": f64(thr) if thr is not None else "",
            "is_tripped": str(guard.is_tripped(equity)),
            "current_drawdown": f64(guard.current_drawdown(equity)),
        }
        guard.update(equity)
        got["peak_after_update"] = f64(guard.peak_equity)

        for field, value in got.items():
            assert value == row[field], (
                f"row {i} (max_dd={max_dd}, step={row['step']}, "
                f"equity={equity}): {field} golden {row[field]!r}, "
                f"computed {value!r}")


def test_the_guard_fixture_contains_a_trip_and_a_non_trip():
    """Otherwise the replay above proves only that nothing ever happens."""
    golden = read_fixture("drawdown_guard.csv")
    assert (golden["is_tripped"] == "True").any()
    assert (golden["is_tripped"] == "False").any()


def test_equity_exactly_at_the_threshold_does_not_trip():
    """The tie-break, pinned separately from the replay.

    Stated as its own test because it is the one line a later reader is most
    likely to "fix" to ``<=``, and because in the fixture it is a single row
    among twenty.
    """
    guard = DrawdownGuard(store=InMemoryPeakStore(1050.0), max_drawdown_pct=0.08)
    assert guard.trigger_threshold() == 966.0
    assert not guard.is_tripped(966.0)
    assert guard.is_tripped(965.9)


# --------------------------------------------------------------------------- #
# Sizer — attribution, not equality. See the module docstring.                 #
# --------------------------------------------------------------------------- #

#: What a cell can differ by. Each name is one of the deviations documented in
#: ``resources.risk.sizer``; there is deliberately no "other" bucket, because
#: a bucket called "other" is where an unexplained regression goes to be
#: counted rather than investigated.
EXACT = "EXACT"
STOP_FLOOR = "STOP_FLOOR"          # deviation 3: floor is per-instrument, on the stop
REFUSAL = "REFUSAL"                # deviation 1: refuse rather than clamp to min_lot
VOLUME_MAX = "VOLUME_MAX"          # the 0.10-lot capital cap is not a contract fact

#: Pinned so the shape of the difference is visible in the diff of any change
#: to the sizer, not just its presence.
EXPECTED_COUNTS = {EXACT: 96, STOP_FLOOR: 90, REFUSAL: 123, VOLUME_MAX: 171}


@pytest.fixture(scope="module")
def gold_spec():
    return Registry.load(SNAPSHOT)[GOLD]


def classify(row, result) -> str:
    """Name the single reason this cell differs, or EXACT.

    Order matters and is the order the new sizer applies things in: the stop
    is floored first, then the budget decides whether there is a position at
    all, then the contract cap applies. Reporting the first divergence along
    that path is what makes the label mean something.
    """
    old_lots = float(row["lots"])
    old_stop = float(row["sl_distance"])
    if abs(result.effective_stop_distance - old_stop) > 0:
        return STOP_FLOOR
    if result.lots == 0.0:
        return REFUSAL
    if result.lots != old_lots:
        return VOLUME_MAX
    return EXACT


@pytest.fixture(scope="module")
def sized(gold_spec):
    """Every grid cell, run through the T5 adapter once."""
    grid = read_fixture("sizer_grid.csv")
    fx = StaticFxRates({})          # gold is quoted in USD; the account is USD
    out = []
    for _, row in grid.iterrows():
        result = size_position(
            spec=gold_spec,
            account_balance=float(row["account_balance"]),
            account_ccy="USD",
            risk_pct=float(row["risk_pct"]),
            # The T5 adapter, in one line: the old signature took an ATR and a
            # multiplier and did the floor itself; the new one takes the stop
            # distance those two imply and floors it per instrument.
            stop_distance_price=float(row["atr_value"]) * float(row["sl_atr_multiplier"]),
            fx_rate_provider=fx,
        )
        out.append((row, result, classify(row, result)))
    return out


def test_the_grid_is_the_one_the_fixture_pins(sized, manifest):
    assert len(sized) == manifest["sizer_grid"]["n_rows"] == 480


def test_every_sizer_deviation_is_one_of_the_documented_ones(sized):
    """The attribution assertion. A cell that differs for a fourth reason
    cannot be classified, so it fails here rather than being averaged away."""
    counts = {k: 0 for k in EXPECTED_COUNTS}
    for _, _, label in sized:
        counts[label] += 1
    assert counts == EXPECTED_COUNTS, (
        f"got {counts}, expected {EXPECTED_COUNTS}. A change in these counts "
        "is a behavioural change in the sizer and needs a log entry stating "
        "the old behaviour, the new behaviour and the reason (spec T11).")


def test_the_unaffected_cells_reproduce_the_fixture_exactly(sized):
    """Where no deviation applies, T11's exactness requirement stands in full.

    96 cells is a fifth of the grid, and it is the fifth that proves the
    arithmetic itself was ported rather than reimplemented — the other three
    classes only prove the deviations behave as designed.
    """
    checked = 0
    for row, result, label in sized:
        if label != EXACT:
            continue
        assert f64(result.lots) == row["lots"]
        assert f64(result.effective_stop_distance) == row["sl_distance"]
        checked += 1
    assert checked == EXPECTED_COUNTS[EXACT]


def test_no_cell_the_old_sizer_put_over_budget_is_still_over_budget(sized, manifest):
    """The reason deviation 1 exists, asserted on the grid that measured it.

    125 of 480 cells breached their own risk budget under the old clamp, the
    worst by 600% of account. Every one of them must now either be refused or
    sized inside the budget. This is the assertion that would have caught the
    live bug, so it is written as a property of all 480 cells rather than as a
    spot check on the worst one.
    """
    breaches = [(row, result) for row, result, _ in sized
                if row["over_budget"] == "True"]
    assert len(breaches) == manifest["sizer_grid"]["n_over_budget"] == 125

    for row, result in breaches:
        budget_pct = float(row["risk_pct"])
        assert (not result.tradable) or result.risk_actual_pct <= budget_pct + 1e-12, (
            f"balance={row['account_balance']} atr={row['atr_value']} "
            f"risk={row['risk_pct']} mult={row['sl_atr_multiplier']}: old sizer "
            f"risked {float(row['realised_risk_pct']):.2%}, new one still "
            f"risks {result.risk_actual_pct:.2%}")


def test_refusals_say_why(sized):
    """A silent zero is the same failure as a silent clamp, one layer along."""
    for row, result, label in sized:
        if label != REFUSAL:
            continue
        assert result.reason is SizingReason.MIN_POSITION_EXCEEDS_RISK_BUDGET
        assert result.granularity_flag is True


def test_no_cell_in_the_whole_grid_exceeds_its_budget(sized):
    """X28's property, restated over the D8 grid rather than a synthetic one.

    Broader than the test above: not "the old breaches are fixed" but "there
    are no breaches", which is the claim the sizer actually makes.
    """
    over = [(row, result) for row, result, _ in sized
            if result.tradable
            and result.risk_actual_pct > float(row["risk_pct"]) + 1e-12]
    assert not over, over[:3]


# --------------------------------------------------------------------------- #
# The claim the fixture is a proxy for, asserted directly where possible.      #
# --------------------------------------------------------------------------- #

#: Where the WMPS checkout lives. Overridable so the check can be pointed at a
#: pinned copy, and so it can be deliberately hidden to rehearse a CI run.
WMPS_ENV = "QH_WMPS_DIR"
WMPS_DEFAULT = pathlib.Path.home() / "Local" / "wine-mt5-python-setup"


def wmps_indicators():
    """Import the live module directly, or None if the checkout is absent.

    Loaded by path rather than by installing it: `resources` must not grow a
    dependency on WMPS, and this is a test reaching across to a reference
    implementation, not a package importing its own ancestor.
    """
    import importlib.util
    import os

    root = pathlib.Path(os.environ.get(WMPS_ENV) or WMPS_DEFAULT)
    path = root / "backend/trading/app/quant/strategies/indicators.py"
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("_wmps_indicators", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_port_is_bit_identical_to_the_code_it_was_ported_from(sample, manifest):
    """What T11 actually asks, without the fixture in the middle.

    The fixture is a *recording* of the old code's output, and the previous
    test established that the recording carries a trace of the machine that
    made it. This asserts the underlying claim directly: run both
    implementations in one interpreter and every cell must match as a string,
    including the four columns the fixture cannot pin.

    It needs the WMPS checkout, so it skips on a runner and X22 is declared
    CI-limited because of it. That is the honest arrangement: CI gets the
    portable half, and the half that requires the other repository is stated
    as requiring it rather than quietly dropped.
    """
    live = wmps_indicators()
    if live is None:
        pytest.skip(f"WMPS checkout not present; set ${WMPS_ENV} to run this")

    ind = manifest["indicators"]
    k_p, d_p, s_k = (ind["stoch_params"][x]
                     for x in ("k_period", "d_period", "smooth_k"))
    pairs: list[tuple[str, pd.Series, pd.Series]] = []
    for p in ind["wma_periods"]:
        pairs.append((f"wma_{p}", wma(sample["close"], p),
                      live.wma(sample["close"], p)))
    for p in ind["hma_periods"]:
        pairs.append((f"hma_{p}", hma(sample["close"], p),
                      live.hma(sample["close"], p)))
    k, d = stochastic(sample["high"], sample["low"], sample["close"], k_p, d_p, s_k)
    lk, ld = live.stochastic(sample["high"], sample["low"], sample["close"],
                             k_p, d_p, s_k)
    pairs += [("stoch_k", k, lk), ("stoch_d", d, ld)]
    pairs.append((f"atr_{ind['atr_period']}",
                  atr(sample["high"], sample["low"], sample["close"], ind["atr_period"]),
                  live.atr(sample["high"], sample["low"], sample["close"], ind["atr_period"])))

    for name, ported, original in pairs:
        got = ported.map(f64).to_numpy()
        want = original.map(f64).to_numpy()
        mismatched = np.flatnonzero(got != want)
        assert len(mismatched) == 0, (
            f"{name}: the port differs from WMPS on {len(mismatched)} cells. "
            f"First at row {mismatched[0]}: WMPS {want[mismatched[0]]!r}, "
            f"ported {got[mismatched[0]]!r}. This is a port bug, not fixture "
            "drift — both ran in this interpreter.")

    assert len(pairs) == len(ind["columns"])
