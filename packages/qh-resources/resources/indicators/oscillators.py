"""Stochastic oscillator — ported from WMPS under T11.

Copied without numerical change from the D8 golden source, including the
`.mask(hl_range == 0, 50.0)` line and the comment explaining it, because that
line is the whole difference between this implementation and the one the
research engines use.

**The two disagree, and the disagreement is live-versus-backtest.**
`research.engines.indicators.stochastic` writes `.where(hl_range > 0, 50.0)`.
A NaN comparison is False, so `.where` treats the entire warm-up region —
where `hl_range` is NaN because the rolling window is not yet full — as
"range is zero" and fills it with a fabricated neutral 50.0. `.mask` on
`== 0` is False for NaN, so the warm-up correctly stays NaN.

Concretely, at the default 14/3/3 that is 13 bars of invented %K at the head
of every series, and every %K/%D cross inside them. The research engines were
deliberately aligned on the fill-to-50 reading during the crest_n_keel sweep
parity work, so every recorded harness result carries it; this port carries
the live reading instead, because D8 pins WMPS as golden and because a
backtest that trades bars the live strategy would skip is the wrong way round.
Neither module is changed to match the other here — see the T11 log entry for
why that is a separate decision with its own cost.
"""

from __future__ import annotations

import pandas as pd


def stochastic(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    k_period: int = 14,
    d_period: int = 3,
    smooth_k: int = 3,
) -> tuple[pd.Series, pd.Series]:
    """
    Stochastic Oscillator. Returns (%K, %D).
    %K = SMA(raw_k, smooth_k) where raw_k = (close - lowest_low) / (highest_high - lowest_low) * 100
    %D = SMA(%K, d_period)

    Edge-case / insufficient-data contract:
      - Warmup: the first ``k_period - 1`` bars have no rolling window and are
        NaN; %K stays NaN until index ``k_period - 1 + smooth_k - 1`` and %D
        until a further ``d_period - 1`` bars. NaN is never silently filled.
      - If ``k_period`` exceeds the series length, every value is NaN.
      - Constant price (range == 0) yields the midpoint 50.0, not NaN — that is
        a defined reading, not missing data.
    Callers evaluating live signals must guard against NaN (e.g. skip the bar)
    rather than assume a numeric %K/%D is always present.
    """
    lowest_low = low.rolling(k_period).min()
    highest_high = high.rolling(k_period).max()
    hl_range = highest_high - lowest_low
    raw_k = (close - lowest_low) / hl_range * 100
    # When the range is exactly 0 (constant prices) default to the midpoint.
    # Use mask on `hl_range == 0` rather than `where(hl_range > 0, ...)`: the
    # latter also matches the warmup region (where hl_range is NaN, so the
    # comparison is False) and would clobber the leading NaN padding with 50.0.
    # `== 0` is False for NaN, so insufficient-data bars correctly stay NaN.
    raw_k = raw_k.mask(hl_range == 0, 50.0)
    k = raw_k.rolling(smooth_k).mean()
    d = k.rolling(d_period).mean()
    return k, d
