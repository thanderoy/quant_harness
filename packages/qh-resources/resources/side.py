"""Direction, defined once.

``Side`` is shared vocabulary: a strategy emits it, a broker fills it, and a
sizer signs a position with it. It lived in ``strategies.base`` until T12
needed it below that layer — ``resources`` may not import ``strategies``
(X19), so a broker port that spoke in sides had either to duplicate the enum
or to have it moved down. Duplicating it would have meant two enums whose
members compare unequal, which is the kind of bug that surfaces as a
position silently never closing.

``strategies.base`` re-exports this object, so ``strategies.Side`` continues
to name it and every existing identity comparison still holds.
"""

from __future__ import annotations

from enum import Enum

__all__ = ["Side"]


class Side(Enum):
    LONG = 1
    SHORT = -1

    @property
    def sign(self) -> int:
        return self.value
