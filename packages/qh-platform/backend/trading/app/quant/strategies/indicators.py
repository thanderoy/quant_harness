"""Indicators for the live app — re-exported from `resources`, not redefined.

This module used to carry its own copies of `wma`, `hma`, `stochastic` and
`atr`. `resources.indicators` carries the T11 port of the same four, pinned
to the D8 golden fixture by X22, and Phase 3 step 3a put `resources` on the
image. Two copies of a formula is two chances for the backtest to disagree
with the account, so the copies here are gone and the import is the contract.

`stochastic`, `atr` and `hma`'s window arithmetic were byte-identical, so
removing them changes nothing. **`wma` was not**, and that is worth stating
rather than burying: this module reduced with `np.dot`, `resources` reduces
with `math.fsum`. The live HMA therefore moves by a few ULP.

Measured before the swap, on the instrument crest_n_keel actually trades:

    XAUUSD H1, 124,827 comparable bars, HMA(55)
      bars differing numerically  59.9k of 124.8k  (52%)
      largest difference          2.7e-12          (3.49 ULP)
      slope-sign flips            0
      close-vs-HMA flips          0
    XAUUSD H4, 32,900 comparable bars — same, 3.10 ULP, 0 and 0

Both of crest_n_keel's comparisons (`hma_cur > hma_prev` and
`close_cur > hma_cur`) are unchanged on every bar of 21 years of data. asqs
imports only `atr`, which was identical. So the arithmetic moved and the
signals did not.

The direction of the move is also the right one: `math.fsum` is correctly
rounded and `np.dot` dispatches to a BLAS kernel chosen for the CPU at run
time, so the old reduction was reproducible only by accident of machine and
numpy version. See `resources.indicators.moving_average.wma` for the full
history — it is the reason X22 can assert exact equality at all.
"""

from resources.indicators import atr, hma, stochastic, wma

__all__ = ["atr", "hma", "stochastic", "wma"]
