"""
Persistent peak-equity drawdown guard.

Tracks peak account equity across evaluations and trips when current
equity falls below peak * (1 - max_drawdown_pct).

v1.0 of the strategy used `equity < balance * 0.90` per evaluation, which
only checked open-position P&L vs current closed balance — NOT a drawdown
guard at all. This module replaces that check with a true persistent
peak-tracking circuit-breaker.

Backend: simple JSON file on disk by default. Replace `JsonPeakStore`
with `DBPeakStore` (using app.trades.models.Account) for production.

Usage:
    guard = DrawdownGuard(
        store=JsonPeakStore("/var/lib/qhf/peak_equity_HMA1H.json"),
        max_drawdown_pct=0.20,    # halt at 20% from peak
    )
    if guard.is_tripped(equity=current_equity):
        log.warning(f"Drawdown guard tripped: {guard.diagnostics()}")
        return None
    guard.update(equity=current_equity)   # raises peak if new high
"""

from __future__ import annotations

import json
import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

LOGGER = logging.getLogger(__name__)


# -- Storage abstraction ------------------------------------------------------


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


class JsonPeakStore(PeakStore):
    """Single-file JSON peak store. Atomic via os.replace."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)

    def read(self) -> Optional[float]:
        try:
            with open(self.filepath, "r") as f:
                data = json.load(f)
            return float(data["peak_equity"])
        except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError):
            return None

    def write(self, peak_equity: float) -> None:
        tmp = self.filepath + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"peak_equity": float(peak_equity)}, f)
        os.replace(tmp, self.filepath)


# -- Guard --------------------------------------------------------------------


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
