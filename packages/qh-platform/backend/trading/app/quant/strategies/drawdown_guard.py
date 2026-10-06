"""Persistent peak-equity drawdown guard — the platform's filesystem half.

The port (`PeakStore`) and the arithmetic (`DrawdownGuard`) now come from
`resources.risk.drawdown_guard`, de-duplicated at Phase 3 step 4.2. The two
implementations were byte-identical once comments were stripped, so the swap
is behaviour-neutral by inspection as well as by X22.

**`JsonPeakStore` stays here, and that is the design rather than an
oversight.** `resources` ships the port plus `InMemoryPeakStore`; its own
docstring explains why a concrete file-writing store does not belong in the
layer a backtest imports — a `SimulatedBroker` run that persisted its peak to
disk would carry state between runs and quietly stop being reproducible.
Persistence is a platform concern, and this is the platform.

So de-duplication here removes the duplicated *arithmetic*, which is what
step 4 is for, and leaves the filesystem where filesystem belongs. Nothing
needed adding to `resources`.

The store writes to the platform's state directory; the path is live and the
rename of it is a migration, not a find-and-replace (R12).

Usage is unchanged:
    guard = DrawdownGuard(
        store=JsonPeakStore(<state path>),
        max_drawdown_pct=0.20,    # halt at 20% from peak
    )
    if guard.is_tripped(equity=current_equity):
        ...
"""

import json
import logging
import os
from typing import Optional

from resources.risk.drawdown_guard import DrawdownGuard, PeakStore

LOGGER = logging.getLogger(__name__)

#: Re-exported so existing imports keep working. `DrawdownGuard` and
#: `PeakStore` are `resources`' definitions now, not copies of them.
__all__ = ["DrawdownGuard", "PeakStore", "JsonPeakStore"]


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
