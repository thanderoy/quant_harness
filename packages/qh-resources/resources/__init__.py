"""``resources`` — the instrument-neutral core of quant_harness.

Imports nothing from ``strategies``, ``research`` or ``platform``, and is
importable with no Django settings configured and no network access (X2, X19).
That contract is what makes backtest/live parity structural rather than
aspirational; it is the one rule not relaxed for convenience.
"""

__all__ = ["instruments"]
