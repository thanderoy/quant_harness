"""Indicator implementations, instrument-neutral and singly-defined.

Every function here is a T11 port of the corresponding WMPS function and
reproduces its D8 golden fixture exactly (X22). They take and return pandas
Series and know nothing about instruments, lots, currencies or sessions —
the property that lets one strategy module run against the whole registry.

Import from here rather than from the submodules; the split into
`moving_average` / `oscillators` / `volatility` is filing, not interface.
"""

from resources.indicators.moving_average import hma, wma
from resources.indicators.oscillators import stochastic
from resources.indicators.volatility import atr

__all__ = ["atr", "hma", "stochastic", "wma"]
