"""Returns that know their own frequency.

Five wrong numbers in this repo came from the same mechanism: a numeric
parameter that could be defaulted, or passed, without anyone having to say
where it came from.

* ``SR* = 0`` — DSR evaluated against a benchmark nobody chose (fixed by T8).
* ``gamma_3 / gamma_4`` defaulting to normal — non-normality assumed away.
* ``commission = 7.0`` — a published figure standing in for a measured one.
* ``max_lag`` — a rule-of-thumb bandwidth that silently biased ``eta``.
* ``periods_per_year = 6048`` applied to **trade** returns — an annualised
  Sharpe of 7.01, where the right factor was trades per year, about 116. The
  entire figure was the constant.

Three of those now have guards (X14, X24, X31). Guarding the fourth and fifth
individually would leave the mechanism intact and wait for the sixth.

The mechanism is that a returns array is just numbers: it cannot object to
being annualised wrongly, because it does not know what it is. So make it
know. ``Returns`` carries the frequency with the values, derived at
construction from something the caller must state — a bar timeframe, or a
trade count over a span — and every metric reads it from there.

That closes the class rather than an instance, and it makes the 7.01 case
**impossible** rather than caught: you cannot pass 6048 to trade returns,
because the returns already know they are trades.

``periods_per_year`` survives as an explicit override for the cases that need
one, but it is never a default and never silent: overriding a ``Returns``
object requires saying so, and the resulting figure records that it was
overridden.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, Sequence

import numpy as np

__all__ = [
    "BAR_PERIODS_PER_YEAR",
    "FrequencyConflict",
    "Returns",
    "resolve_periods_per_year",
]

#: Bars per year by timeframe, on the 252-trading-day convention the README
#: documents. Forex trades ~24h on 5 days a week, so the day multiplier is 24
#: rather than a session length.
BAR_PERIODS_PER_YEAR = {
    "M5": 252 * 24 * 12,
    "M15": 252 * 24 * 4,
    "M30": 252 * 24 * 2,
    "H1": 252 * 24,
    "H4": 252 * 6,
    "D1": 252,
    "W1": 52,
}


class FrequencyConflict(ValueError):
    """A ``periods_per_year`` was passed that disagrees with the returns.

    Raised rather than resolved by precedence, because both values are
    assertions about the same fact and silently preferring one is how the
    7.01 happened.
    """


@dataclass(frozen=True)
class Returns:
    """A return series that carries how to annualise itself.

    Construct through :meth:`from_bars` or :meth:`from_trades` — the bare
    constructor is available but the classmethods are what make the frequency
    derived rather than asserted.
    """

    values: np.ndarray
    kind: Literal["bar", "trade"]
    periods_per_year: float
    provenance: str
    meta: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.values)

    def __array__(self, dtype=None):
        """So a ``Returns`` can be handed to numpy directly."""
        return np.asarray(self.values, dtype=dtype)

    @classmethod
    def from_bars(cls, values: Sequence[float], timeframe: str) -> "Returns":
        """Per-bar returns at a named timeframe.

        The timeframe must be one this module knows, so a typo is a KeyError
        at construction rather than a plausible Sharpe later.
        """
        tf = timeframe.upper()
        if tf not in BAR_PERIODS_PER_YEAR:
            raise KeyError(
                f"unknown timeframe {timeframe!r}; known: "
                f"{sorted(BAR_PERIODS_PER_YEAR)}")
        v = np.asarray(values, dtype=float)
        return cls(values=v, kind="bar",
                   periods_per_year=float(BAR_PERIODS_PER_YEAR[tf]),
                   provenance=f"bar timeframe {tf}",
                   meta={"timeframe": tf})

    @classmethod
    def from_trades(cls, values: Sequence[float],
                    span_days: float) -> "Returns":
        """One return per closed trade, over a span in calendar days.

        The frequency is ``n / (span_days / 365.25)`` — trades per year, as
        actually realised. This is the constructor that makes the 7.01 case
        unreachable: whatever ``span_days`` is, the result is trade frequency,
        not bar frequency.
        """
        v = np.asarray(values, dtype=float)
        if span_days <= 0:
            raise ValueError(f"span_days must be positive, got {span_days}")
        ppy = max(v.size / (span_days / 365.25), 1.0)
        return cls(values=v, kind="trade", periods_per_year=float(ppy),
                   provenance=f"{v.size} trades over {span_days:.1f} days",
                   meta={"span_days": float(span_days), "n_trades": int(v.size)})

    def with_periods_per_year(self, ppy: float, why: str) -> "Returns":
        """An explicit, reasoned override. ``why`` is not optional."""
        if not why:
            raise ValueError("an override must say why")
        return Returns(values=self.values, kind=self.kind,
                       periods_per_year=float(ppy),
                       provenance=f"OVERRIDE({ppy}): {why}",
                       meta={**self.meta, "overridden_from":
                             self.periods_per_year})

    @property
    def overridden(self) -> bool:
        return self.provenance.startswith("OVERRIDE")


def resolve_periods_per_year(returns, periods_per_year: Optional[float],
                             *, caller: str = "metric") -> tuple[np.ndarray, float]:
    """Return ``(values, periods_per_year)`` for either input shape.

    Accepts a :class:`Returns`, which supplies its own frequency, or a bare
    array, which must be told one. A bare array with no frequency is refused
    rather than defaulted — the default is the whole defect.
    """
    if isinstance(returns, Returns):
        if (periods_per_year is not None
                and float(periods_per_year) != returns.periods_per_year):
            raise FrequencyConflict(
                f"{caller}: returns carry {returns.periods_per_year:g} "
                f"periods/year ({returns.provenance}) but "
                f"{periods_per_year:g} was passed. These are two claims about "
                "the same fact. Use Returns.with_periods_per_year(value, why) "
                "to override deliberately.")
        return np.asarray(returns.values, dtype=float), returns.periods_per_year

    if periods_per_year is None:
        raise ValueError(
            f"{caller}: periods_per_year is required for a bare array. Pass "
            "one explicitly, or hand in a Returns built with "
            "Returns.from_bars(...) / Returns.from_trades(...) so the "
            "frequency travels with the values.")
    return np.asarray(returns, dtype=float), float(periods_per_year)
