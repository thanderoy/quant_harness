"""Shared fixtures. The generator itself lives in ``synthetic.py``.

Split deliberately: several tests need ``make_bars`` outside a fixture (in
parametrisation, and to build a second series mid-test), and importing it
from a module named ``conftest`` would resolve by whichever directory pytest
happened to put on ``sys.path`` first. One distinctly-named module removes
that question.
"""

from __future__ import annotations

import pandas as pd
import pytest

from synthetic import make_bars

__all__ = ["make_bars"]


@pytest.fixture
def bars() -> pd.DataFrame:
    return make_bars()
