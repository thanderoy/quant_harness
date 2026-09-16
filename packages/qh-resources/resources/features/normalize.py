"""T4 — instrument-neutral primitives, and mechanical disjointness.

Every strategy input and every target passes through one of these. The point
is that a Donchian breakout must carry identical meaning on USDJPY and on
gold: a threshold of "0.8" has to be the same statement about both, or the
strategy is nine strategies wearing one name. Each primitive here returns a
dimensionless quantity, so the same constant means the same thing everywhere.

The second half of the module is the part bought with a dead instrument.

At seq=69 the forward target was divided by ATR(14) while the feature under
test was ATR(14)/ATR(100). The resulting monotone -1.049 ATR "separation" was
pure division, and it was written up as a finding before anyone noticed. The
existing guard, ``research.pre.normalizer_check``, asks the caller to declare
two sets of strings at registration time. That works exactly as often as the
declaration is right, which is a convention, not a mechanism -- and a wrong
declaration fails silently in the direction of passing.

So provenance is recorded by the primitives themselves and accumulates through
composition. ``atr_normalise(x, atr14)`` knows it touched ``atr14`` because it
was handed it. A feature and a target that share an input collide in
``assert_disjoint`` without anyone having declared anything.

The failure mode that matters is a series arriving with no provenance. pandas
carries ``.attrs`` through some operations and drops them in others -- a
scalar multiply keeps them, a reduction or a two-series combine generally does
not -- so provenance cannot be assumed to survive arithmetic done outside
these functions. Where it has gone missing, ``assert_disjoint`` raises
``UntaggedSeries`` rather than passing. An unprovable claim of disjointness is
treated as a contamination, because the one thing seq=69 established is that
this check is worthless when it can quietly succeed.

    >>> atr14 = tag(pd.Series([...]), "atr14")
    >>> feature = atr_normalise(close_change, atr14)
    >>> target = atr_normalise(forward_move, atr14)
    >>> assert_disjoint(feature, target)
    ContaminationError: ... share {'atr14'} ...
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

#: Key under which input provenance travels on a Series.
PROVENANCE_KEY = "normalize_inputs"


class ContaminationError(AssertionError):
    """Two series share an input, so any relationship between them is
    algebraic rather than empirical."""


class UntaggedSeries(ValueError):
    """A series carries no provenance, so disjointness cannot be established.

    Not a warning. A check that cannot see its inputs must fail, because the
    alternative is a check that passes by default -- which is the state the
    seq=69 contamination was already in.
    """


def tag(series: pd.Series, *inputs: str) -> pd.Series:
    """Record which named inputs ``series`` was computed from.

    Use it on a raw input (``tag(atr, "atr14")``) or to restore provenance
    after an operation that pandas did not carry ``.attrs`` through.
    """
    if not inputs:
        raise ValueError("tag() needs at least one input name")
    out = series.copy()
    out.attrs = dict(series.attrs)
    out.attrs[PROVENANCE_KEY] = frozenset(inputs)
    return out


def inputs_of(series: pd.Series) -> frozenset[str]:
    """The named inputs behind ``series``.

    Falls back to the series' own ``name`` when no provenance was recorded --
    a named raw input is self-describing. An unnamed, untagged series raises:
    it cannot be distinguished from any other, so it cannot be checked.
    """
    recorded = series.attrs.get(PROVENANCE_KEY)
    if recorded:
        return frozenset(recorded)
    if series.name is not None:
        return frozenset({str(series.name)})
    raise UntaggedSeries(
        "series has neither recorded provenance nor a name, so its inputs "
        "cannot be established. Pass it through tag() at the point it is "
        "built. pandas drops .attrs through reductions and most two-series "
        "combines, which is the usual way provenance goes missing."
    )


def _carry(out: pd.Series, *sources: pd.Series,
           extra: Iterable[str] = ()) -> pd.Series:
    """Union the provenance of every source onto the result."""
    acc: set[str] = set(extra)
    for s in sources:
        acc |= inputs_of(s)
    out.attrs = dict(out.attrs)
    out.attrs[PROVENANCE_KEY] = frozenset(acc)
    return out


def assert_disjoint(feature: pd.Series, target: pd.Series,
                    name: str = "feature") -> None:
    """Raise unless ``feature`` and ``target`` share no input.

    ``target`` is the *normalised* target -- the thing the study correlates
    against, after division. A raw-units target normalised by nothing is
    trivially disjoint, which is the honest escape hatch: express the target
    in dollars and the question becomes empirical again.
    """
    shared = inputs_of(feature) & inputs_of(target)
    if shared:
        raise ContaminationError(
            f"{name} shares {set(shared)} with its target, so the two are "
            f"related by algebra rather than by the market. Either express "
            f"the target in raw units or rebuild the feature without "
            f"{set(shared)}. See research log seq=69."
        )


# -- the primitives --------------------------------------------------------


def log_return(series: pd.Series, periods: int = 1) -> pd.Series:
    """Log return over ``periods`` bars.

    Log rather than simple because returns are then additive across bars and
    symmetric in sign, so a panel of instruments quoted at wildly different
    levels -- USDJPY at 147, gold at 4,389 -- is directly comparable.

    Non-positive prices give NaN rather than -inf: a zero or negative price is
    bad data, and -inf propagates through every downstream mean and z-score
    while looking like a number.
    """
    if periods < 1:
        raise ValueError("periods must be >= 1")
    values = series.astype(float)
    safe = values.where(values > 0)
    out = np.log(safe).diff(periods)
    return _carry(out, series)


def atr_normalise(series: pd.Series, atr: pd.Series) -> pd.Series:
    """``series`` expressed in ATR units.

    The workhorse: a 1.5-ATR stop, a 2-ATR move and a breakout threshold all
    mean the same thing on every instrument once divided by the same scale.

    A non-positive ATR gives NaN, not a division blow-up. ATR is zero on a
    flat bar and on synthetic or padded data, and a 1e9 feature value from a
    near-zero denominator is the kind of outlier that survives into a result.
    """
    scale = atr.astype(float)
    out = series.astype(float) / scale.where(scale > 0)
    return _carry(out, series, atr)


def vol_zscore(series: pd.Series, window: int, min_periods: int | None = None
               ) -> pd.Series:
    """Rolling z-score of ``series`` over ``window`` bars.

    Causal by construction -- the window ends at the current bar, so no future
    information enters. A zero rolling standard deviation gives NaN for the
    same reason a zero ATR does.

    The window is recorded in the provenance (``<name>@z<window>``) as well as
    the underlying input, so a feature z-scored over 20 bars and a target
    z-scored over 20 bars of the same series collide, while the same series
    over genuinely different windows does not.
    """
    if window < 2:
        raise ValueError("window must be >= 2 for a standard deviation")
    values = series.astype(float)
    mp = window if min_periods is None else min_periods
    roll = values.rolling(window, min_periods=mp)
    sd = roll.std()
    out = (values - roll.mean()) / sd.where(sd > 0)
    # The window-qualified name REPLACES the bare one rather than joining
    # it. The collision unit is (input, window): seq=69 shared atr14
    # exactly, and ATR(14) against ATR(100) is two measurements, not one.
    # Unioning both would make every window of a series collide with every
    # other, which fails the honest case and teaches people to skip the check.
    marks = {f"{i}@z{window}" for i in inputs_of(series)}
    out.attrs = dict(out.attrs)
    out.attrs[PROVENANCE_KEY] = frozenset(marks)
    return out


def range_pct(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """Bar range as a fraction of close.

    The cheapest instrument-neutral volatility proxy there is: no lookback, so
    no warm-up and nothing to contaminate a window with.

    Refuses an inverted bar rather than returning a negative range. ``high <
    low`` is impossible in real data and always means a column mix-up or a bad
    merge, and a negative "range" would flow silently into a volatility
    estimate.
    """
    h, l, c = high.astype(float), low.astype(float), close.astype(float)
    both = h.notna() & l.notna()
    inverted = both & (h < l)
    if inverted.any():
        first = inverted.idxmax()
        raise ValueError(
            f"high < low on {int(inverted.sum())} bar(s), first at {first}. "
            "That is a column mix-up or a bad merge, not a market condition"
        )
    out = (h - l) / c.where(c > 0)
    return _carry(out, high, low, close)
