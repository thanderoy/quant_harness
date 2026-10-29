"""The swap-deals collector groups by position and strips identity.

Pure functions only — the collector's network path is the shared ``_client``,
which ``test_collector_abort`` already covers.
"""

from __future__ import annotations

from phase0.collectors import swap_deals as sd


def deal(**kw) -> dict:
    base = {"ticket": 900001, "order": 900002, "position_id": 7,
            "magic": 4242, "comment": "x", "external_id": "y",
            "symbol": "XAUUSD", "type": 0, "entry": 0, "reason": 3,
            "volume": 0.01, "price": 2904.26, "time_msc": 1_000_000,
            "swap": 0.0, "profit": 0.0}
    base.update(kw)
    return base


def test_a_position_sums_its_legs_and_drops_identity():
    pos, skipped = sd.positions([
        deal(),
        deal(type=1, entry=1, time_msc=90_000_000, swap=-0.08, profit=1.5),
    ])
    assert skipped == {"no_open_in_window": 0, "still_open": 0}
    assert pos == [{"symbol": "XAUUSD", "side": "BUY", "lots": 0.01,
                    "open_s": 1_000, "close_s": 90_000,
                    "swap": -0.08, "profit": 1.5}]


def test_side_comes_from_the_opening_deal():
    pos, _ = sd.positions([deal(type=1), deal(type=0, entry=1, time_msc=2_000_000)])
    assert pos[0]["side"] == "SELL"


def test_partial_positions_are_counted_not_guessed():
    _, skipped = sd.positions([
        deal(position_id=1),
        deal(position_id=2, entry=1),
    ])
    assert skipped == {"no_open_in_window": 1, "still_open": 1}


def test_non_trade_deals_are_skipped():
    pos, _ = sd.positions([deal(type=2, symbol=""), deal(type=6)])
    assert pos == []
