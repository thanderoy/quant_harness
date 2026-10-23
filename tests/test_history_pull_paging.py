"""history_pull: the terminal fails a request that reaches past its history."""

from __future__ import annotations

import pytest

from phase0.collectors import history_pull as hp
from phase0.collectors._client import EndpointMissing

HELD = 2_345


def _fake_rates(symbol, timeframe, count, start_pos):
    """A terminal holding HELD bars that refuses any request past the oldest."""
    if start_pos + count > HELD:
        raise EndpointMissing("Terminal: Call failed")
    newest = HELD - 1 - start_pos
    return [{"time": f"t{i:06d}"} for i in range(newest - count + 1, newest + 1)]


@pytest.mark.parametrize("page", [1_000, 10_000, 2_345, 7])
def test_every_held_bar_is_pulled_whatever_the_page(monkeypatch, page):
    monkeypatch.setattr(hp, "_rates", _fake_rates)
    bars, _ = hp.fetch_pages("X", "D1", page=page, max_pages=10_000)
    assert len(bars) == HELD - 1          # newest (forming) bar dropped
    assert bars[0]["time"] == "t000000"


def test_a_terminal_with_nothing_still_raises(monkeypatch):
    def none(*a):
        raise EndpointMissing("no symbol")
    monkeypatch.setattr(hp, "_rates", none)
    with pytest.raises(EndpointMissing):
        hp.fetch_pages("X", "D1")
