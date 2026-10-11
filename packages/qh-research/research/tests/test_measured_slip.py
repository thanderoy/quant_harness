"""The measured execution cost is wired in by name, and the default did not move.

The constants in ``cost_model`` are copied from the committed aggregate
artifact; these tests keep the two in step and keep per-fill rows out of it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from resources.execution import SlipModel

from research.datasets.cost_model import (
    EXECUTION_COST_MEASURED,
    SLIP_HAND_ENTERED,
    measured_slip_model,
)

ARTIFACT = Path(__file__).resolve().parents[4] / EXECUTION_COST_MEASURED["artifact"]


def test_the_default_slip_did_not_move():
    """The measurement is available by name; nothing was silently re-priced."""
    assert SlipModel().ticks == SLIP_HAND_ENTERED["ticks"] == 1.0
    assert SlipModel().provenance == "HAND_ENTERED"
    assert EXECUTION_COST_MEASURED["default_changed"] is False


def test_measured_slip_is_stamped_measured():
    m = measured_slip_model("EURUSD")
    assert m.provenance == "MEASURED"
    assert m.ticks == 5.0


def test_a_favourable_median_is_floored_and_says_so():
    """XAUUSD's same-second median is -0.5 ticks; a cost may not improve a fill."""
    m = measured_slip_model("XAUUSD")
    assert m.ticks == 0.0
    assert m.provenance == "MEASURED_FLOORED_AT_ZERO"
    assert measured_slip_model("XAUUSD", "p90").ticks == pytest.approx(5.3)


def test_an_unmeasured_symbol_refuses():
    with pytest.raises(KeyError, match="no live fills"):
        measured_slip_model("XAGUSD")


def test_the_constants_are_the_committed_artifact():
    """The numbers in cost_model are copied from the artifact; keep them so."""
    rep = json.loads(ARTIFACT.read_text())
    assert rep["source"]["broker"]["server"] == "PepperstoneKE-MT5-Live01"
    assert rep["source"]["n_trade_deals"] == EXECUTION_COST_MEASURED["n_trade_deals"]
    assert rep["source"]["n_entries"] == EXECUTION_COST_MEASURED["n_entries"]
    entries = rep["quote_method"]["entries"]
    for sym, rec in EXECUTION_COST_MEASURED["per_symbol"].items():
        assert entries["slip_vs_touch"][sym]["ALL"]["n"] == rec["n_entries"]
        same = entries["slip_vs_touch_same_second"][sym]["ALL"]
        pre = entries["slip_vs_touch"][sym]["ALL"]
        mid = entries["cost_vs_mid_same_second"][sym]["ALL"]
        assert same["n"] == rec["n_same_second"]
        for q in ("p50", "p75", "p90"):
            assert same["ticks"][q] == pytest.approx(rec["slip_vs_touch"][q])
            assert pre["ticks"][q] == pytest.approx(rec["slip_vs_touch_pre"][q])
            assert mid["price"][q] == pytest.approx(
                rec["cost_vs_mid_per_side_price"][q])


def test_the_committed_artifact_carries_no_per_fill_rows():
    text = ARTIFACT.read_text()
    for key in ("ticket", "position_id", "\"order\"", "magic", "login",
                "time_msc\": 1"):
        assert key not in text
