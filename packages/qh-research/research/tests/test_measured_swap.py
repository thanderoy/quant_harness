"""The measured swap is recorded by name, and the default did not move.

The constants in ``cost_model`` are copied from the committed aggregate
artifact; these tests keep the two in step and keep per-position rows out of it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from research.datasets.cost_model import (
    PEPPERSTONE_XAUUSD_SWAP_LONG_USD_PER_LOT_NIGHT,
    PEPPERSTONE_XAUUSD_SWAP_SHORT_USD_PER_LOT_NIGHT,
    SWAP_MEASURED,
    PepperstoneXAUUSDCostModel,
)
from research.datasets.swap_cost import booked, quoted, rollover_units

ARTIFACT = Path(__file__).resolve().parents[4] / SWAP_MEASURED["artifact"]


def _s(iso: str) -> int:
    return int(datetime.fromisoformat(iso).replace(tzinfo=timezone.utc).timestamp())


def test_the_default_swap_did_not_move():
    """The measurement is available by name; nothing was silently re-priced."""
    m = PepperstoneXAUUSDCostModel()
    assert m.swap_long_per_lot_night == PEPPERSTONE_XAUUSD_SWAP_LONG_USD_PER_LOT_NIGHT == -10.0
    assert m.swap_short_per_lot_night == PEPPERSTONE_XAUUSD_SWAP_SHORT_USD_PER_LOT_NIGHT == -2.0
    assert SWAP_MEASURED["default_changed"] is False


def test_constants_match_the_artifact():
    rep = json.loads(ARTIFACT.read_text())
    assert rep["source"]["broker"]["server"] == "PepperstoneKE-MT5-Live01"
    assert rep["source"]["n_positions"] == SWAP_MEASURED["n_positions"]
    assert rep["triple_weekday"] == SWAP_MEASURED["triple_weekday"]
    b = rep["booked"]
    for k in ("n_crossed_rollover", "crossed_but_uncharged",
              "charged_but_not_crossed"):
        assert b[k] == SWAP_MEASURED[k], k
    assert rep["quoted"]["usd_per_lot_night"]["XAUUSD"] == {
        "converted": True, **SWAP_MEASURED["xauusd_quoted"]}
    gold = b["by_symbol"]["XAUUSD"]["SELL"]
    assert gold["median_usd_per_lot_night"] == SWAP_MEASURED["xauusd_booked"]["SELL"]
    assert gold["n"] == SWAP_MEASURED["xauusd_booked"]["n"]


def test_the_artifact_holds_no_per_position_rows():
    text = ARTIFACT.read_text()
    for field in ("open_s", "close_s", "profit", "positions", "ticket"):
        assert f'"{field}"' not in text, field


def test_rollover_units_count_server_midnights_and_triple_wednesday():
    # Mon 16:00 -> Tue 01:00: one plain night.
    assert rollover_units(_s("2026-02-23T16:00"), _s("2026-02-24T01:00")) == (1, 1)
    # Wed 17:00 -> Thu 03:00: the triple night.
    assert rollover_units(_s("2026-02-25T17:00"), _s("2026-02-26T03:00")) == (3, 1)
    # Fri 16:00 -> Mon 10:00: Friday's rollover only, none on the weekend.
    assert rollover_units(_s("2026-02-20T16:00"), _s("2026-02-23T10:00")) == (1, 1)
    # Same day: none.
    assert rollover_units(_s("2026-02-23T09:00"), _s("2026-02-23T20:00")) == (0, 0)


def test_booked_flags_charges_that_disagree_with_the_calendar():
    pos = [
        {"symbol": "EURUSD", "side": "BUY", "lots": 0.01, "swap": -0.08,
         "open_s": _s("2026-02-23T16:00"), "close_s": _s("2026-02-24T01:00")},
        {"symbol": "EURUSD", "side": "BUY", "lots": 0.01, "swap": 0.0,
         "open_s": _s("2026-02-23T16:00"), "close_s": _s("2026-02-24T01:00")},
        {"symbol": "EURUSD", "side": "BUY", "lots": 0.01, "swap": -0.08,
         "open_s": _s("2026-02-23T09:00"), "close_s": _s("2026-02-23T20:00")},
    ]
    b = booked(pos)
    assert b["crossed_but_uncharged"] == 1
    assert b["charged_but_not_crossed"] == 1
    assert b["by_symbol"]["EURUSD"]["BUY"]["median_usd_per_lot_night"] == -8.0


def test_quoted_points_convert_through_tick_value():
    spec = {"digits": 2, "tick_size": 0.01, "tick_value": 1.0}
    out = quoted({"XAUUSD": {"swap_mode": 1, "swap_long": -86.42,
                             "swap_short": 30.41}}, {"XAUUSD": spec})
    assert out["XAUUSD"] == {"converted": True, "BUY": -86.42, "SELL": 30.41}
    # A mode other than points is reported, not converted.
    other = quoted({"X": {"swap_mode": 2, "swap_long": 1.0, "swap_short": 1.0}},
                   {"X": spec})
    assert other["X"]["converted"] is False
