"""Persistent peak-equity drawdown guard — ported from WMPS under T11.

`PeakStore` and `DrawdownGuard` are copied without behavioural change from
the D8 golden source and reproduce its fixture exactly (X22). The guard's
arithmetic is in account-currency equity throughout, so there is nothing
instrument-specific to strip.

Two things are deliberately left behind, and both are omissions rather than
changes:

**`JsonPeakStore` does not come with it.** It creates directories and writes
files, and `resources` is the layer that must import cleanly with no Django
settings and no filesystem expectations (X2). Persistence is a platform
concern and the concrete store belongs there at Phase 3; D8 already scoped
the JSON store's atomic-write behaviour out as non-numerical. What ships here
is the abstract port plus `InMemoryPeakStore`, which is what a backtest wants
anyway — a `SimulatedBroker` run that persisted its peak to disk would carry
state between runs and quietly stop being reproducible.

**The module does not log.** WMPS's copy holds a module logger it never
calls; carried over, it would be the first `logging` import in `resources`
and would earn its keep by doing nothing.

The threshold comparison is strict (`equity < threshold`), so equity exactly
at the limit does not trip. That is an arbitrary tie-break, but it is a
*pinned* one: the D8 fixture includes the exact -8.00% step precisely so a
later "tidy" to `<=` fails rather than silently halting a live strategy one
step earlier than its backtest did.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


class PeakStore(ABC):
    """Persistent storage for peak equity. Implement read/write."""

    @abstractmethod
    def read(self) -> Optional[float]:
        """Return stored peak equity, or None if no peak recorded yet."""
        raise NotImplementedError

    @abstractmethod
    def write(self, peak_equity: float) -> None:
        """Persist new peak equity."""
        raise NotImplementedError


class InMemoryPeakStore(PeakStore):
    """Non-persistent store. The correct default for a backtest.

    D8 generated its fixture through an equivalent in-memory store, so this
    is also what X22 exercises.
    """

    def __init__(self, peak_equity: float | None = None) -> None:
        self._peak = peak_equity

    def read(self) -> Optional[float]:
        return self._peak

    def write(self, peak_equity: float) -> None:
        self._peak = peak_equity


@dataclass
class DrawdownGuard:
    store: PeakStore
    max_drawdown_pct: float  # e.g. 0.20 for 20%

    def __post_init__(self) -> None:
        if not (0 < self.max_drawdown_pct < 1):
            raise ValueError(
                f"max_drawdown_pct must be in (0, 1), got {self.max_drawdown_pct}"
            )
        self._cached_peak: Optional[float] = self.store.read()

    @property
    def peak_equity(self) -> Optional[float]:
        return self._cached_peak

    def trigger_threshold(self) -> Optional[float]:
        if self._cached_peak is None:
            return None
        return self._cached_peak * (1.0 - self.max_drawdown_pct)

    def is_tripped(self, equity: float) -> bool:
        threshold = self.trigger_threshold()
        if threshold is None:
            # No peak yet — first evaluation. Cannot be tripped.
            return False
        return equity < threshold

    def current_drawdown(self, equity: float) -> float:
        """Fractional drawdown from peak, e.g. 0.08 for 8% below peak.

        Read-only helper for logging. Returns 0.0 when no peak is recorded
        yet or when equity is at/above the peak.
        """
        if self._cached_peak is None or self._cached_peak <= 0:
            return 0.0
        return max(0.0, (self._cached_peak - equity) / self._cached_peak)

    def update(self, equity: float) -> None:
        """Raise peak if new high. Idempotent if equity <= current peak."""
        if self._cached_peak is None or equity > self._cached_peak:
            self._cached_peak = equity
            self.store.write(equity)

    def diagnostics(self) -> dict:
        return {
            "peak_equity": self._cached_peak,
            "trigger_threshold": self.trigger_threshold(),
            "max_drawdown_pct": self.max_drawdown_pct,
        }
