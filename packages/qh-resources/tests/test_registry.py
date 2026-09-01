"""T1 tests — instrument registry, and X2 (registry loads offline).

The provenance-refusal tests are the load-bearing ones: they are the mechanism
that stops "we'll pin the real specs later" from becoming a permanent state.
"""

from __future__ import annotations

import json

import pytest

from resources.instruments.registry import SNAPSHOT_DIR
from resources.instruments import (
    InstrumentSpec,
    Provenance,
    ProvisionalSpecError,
    Registry,
    UnknownInstrument,
)

SNAPSHOT = "provisional_20260901.json"


# --------------------------------------------------------------------------- #
# Provenance refusal                                                           #
# --------------------------------------------------------------------------- #
def test_hand_entered_snapshot_is_refused_by_default():
    with pytest.raises(ProvisionalSpecError) as exc:
        Registry.load(SNAPSHOT)
    # The message must name the symbols, or the operator cannot act on it.
    assert "XAUUSD" in str(exc.value)
    assert "allow_provisional=True" in str(exc.value)


def test_explicit_opt_in_loads_and_stamps():
    reg = Registry.load(SNAPSHOT, allow_provisional=True)
    assert reg.is_provisional
    assert "PROVISIONAL_SPECS" in reg.stamps
    # The stamp must reach artifact metadata, not merely exist on the object.
    assert "PROVISIONAL_SPECS" in reg.artifact_metadata()["registry_stamps"]


def test_stamp_is_added_even_if_snapshot_omits_it(tmp_path):
    """A snapshot cannot dodge the stamp by simply leaving it out."""
    body = json.loads((SNAPSHOT_DIR / SNAPSHOT).read_text())
    body["stamps"] = []
    p = tmp_path / "nostamp.json"
    p.write_text(json.dumps(body))
    reg = Registry.load(p, allow_provisional=True)
    assert "PROVISIONAL_SPECS" in reg.stamps


def test_missing_provenance_raises(tmp_path):
    p = tmp_path / "noprov.json"
    p.write_text(json.dumps({
        "as_of_utc": "2026-01-01T00:00:00+00:00",
        "instruments": {"XAUUSD": {
            "contract_size": 100.0, "tick_size": 0.01, "tick_value": 1.0,
            "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01,
            "digits": 2, "currency_margin": "XAU", "currency_profit": "USD",
        }},
    }))
    with pytest.raises(ValueError, match="no provenance"):
        Registry.load(p, allow_provisional=True)


def test_mt5_sourced_snapshot_needs_no_opt_in(tmp_path):
    p = tmp_path / "real.json"
    p.write_text(json.dumps({
        "as_of_utc": "2026-01-01T00:00:00+00:00",
        "provenance": "MT5_SYMBOL_INFO",
        "instruments": {"XAUUSD": {
            "contract_size": 100.0, "tick_size": 0.01, "tick_value": 1.0,
            "volume_min": 0.01, "volume_max": 100.0, "volume_step": 0.01,
            "digits": 2, "currency_margin": "XAU", "currency_profit": "USD",
        }},
    }))
    reg = Registry.load(p)          # no allow_provisional
    assert not reg.is_provisional
    assert reg.provenance_summary() == {"MT5_SYMBOL_INFO": 1}


# --------------------------------------------------------------------------- #
# Access                                                                       #
# --------------------------------------------------------------------------- #
def test_unknown_symbol_raises_named_error():
    reg = Registry.load(SNAPSHOT, allow_provisional=True)
    with pytest.raises(UnknownInstrument, match="NOTREAL"):
        reg["NOTREAL"]


def test_registry_is_iterable_and_sized():
    reg = Registry.load(SNAPSHOT, allow_provisional=True)
    assert len(reg) == 9
    assert "XAUUSD" in reg
    assert reg.symbols == sorted(reg.symbols)


# --------------------------------------------------------------------------- #
# Derived helpers                                                              #
# --------------------------------------------------------------------------- #
@pytest.fixture
def xau() -> InstrumentSpec:
    return Registry.load(SNAPSHOT, allow_provisional=True)["XAUUSD"]


def test_value_per_price_unit(xau):
    assert xau.value_per_price_unit(1.0) == 100.0
    assert xau.value_per_price_unit(0.01) == 1.0


def test_round_to_lot_step_rounds_down_never_up(xau):
    # 0.0199 must not become 0.02: rounding up crosses the risk budget the
    # caller just computed.
    assert xau.round_to_lot_step(0.0199) == 0.01
    assert xau.round_to_lot_step(0.019999999) == 0.01
    assert xau.round_to_lot_step(0.03) == 0.03


def test_round_to_lot_step_below_minimum_returns_zero(xau):
    """'Cannot trade this small' is a real answer.

    Returning volume_min instead is the clamp that lets realised risk exceed
    budget — the D8 finding behind the h1_momentum halt.
    """
    assert xau.round_to_lot_step(0.004) == 0.0
    assert xau.round_to_lot_step(0.0) == 0.0
    assert xau.round_to_lot_step(-1.0) == 0.0


def test_round_to_lot_step_clamps_to_max(xau):
    assert xau.round_to_lot_step(1e6) == xau.volume_max


def test_round_to_lot_step_output_is_exactly_representable(xau):
    """Float division leaves 0.30000000000000004; an equality check downstream
    would then fail for no visible reason."""
    for req in (0.03, 0.07, 0.29, 1.13):
        got = xau.round_to_lot_step(req)
        assert got == round(got, 2)


def test_min_position_risk_gold(xau):
    # 0.01 lots x 100 oz = 1 oz; a $14 stop risks $14.
    assert xau.min_position_risk(14.0) == pytest.approx(14.0)
    # ...which is 14% of a $100 account. This is D2's finding, mechanised.
    assert xau.min_position_risk(14.0) / 100.0 == pytest.approx(0.14)


def test_min_position_risk_converts_quote_currency():
    reg = Registry.load(SNAPSHOT, allow_provisional=True)
    jpy = reg["USDJPY"]
    # 0.01 x 100,000 = 1,000 units; a 0.5 JPY stop = 500 JPY; /150 = $3.33.
    assert jpy.min_position_risk(0.5, account_ccy_rate=150.0) == pytest.approx(
        1000 * 0.5 / 150.0)


def test_min_position_risk_rejects_bad_inputs(xau):
    with pytest.raises(ValueError):
        xau.min_position_risk(-1.0)
    with pytest.raises(ValueError):
        xau.min_position_risk(1.0, account_ccy_rate=0.0)


# --------------------------------------------------------------------------- #
# X2 — registry loads offline                                                  #
# --------------------------------------------------------------------------- #
def test_x2_registry_loads_with_networking_disabled(monkeypatch):
    """Importing and loading the registry must not touch the network.

    Enforced by making socket construction raise, so any accidental HTTP call
    added later fails this test rather than silently working on a dev machine
    that happens to be online.
    """
    import socket

    def _no_network(*a, **k):
        raise AssertionError("registry attempted a network call")

    monkeypatch.setattr(socket, "socket", _no_network)
    monkeypatch.setattr(socket, "create_connection", _no_network)

    reg = Registry.load(SNAPSHOT, allow_provisional=True)
    assert len(reg) == 9


# --------------------------------------------------------------------------- #
# D1 — the broker-confirmed snapshot                                           #
# --------------------------------------------------------------------------- #
REAL = "pepperstone_demo_20260901.json"


def test_real_snapshot_loads_without_opt_in():
    """MT5_SYMBOL_INFO provenance needs no allow_provisional and carries no stamp."""
    reg = Registry.load(REAL)
    assert not reg.is_provisional
    assert reg.provenance_summary() == {"MT5_SYMBOL_INFO": 9}
    assert "PROVISIONAL_SPECS" not in reg.artifact_metadata()["registry_stamps"]


def test_tick_value_embeds_the_fx_rate_which_is_why_we_do_not_use_it():
    """`tick_value` is reported in the ACCOUNT currency, not the quote currency.

    Measured, not asserted. For a pair quoted in something other than USD, the
    ratio of `contract_size * tick_size` to the reported `tick_value` is the
    live FX rate at the moment the spec was pulled:

        USDJPY  160.08   (spot 160.149 at capture)
        USDCHF    0.810  (spot 0.81019)
        USDCAD    1.388  (spot 1.38824)

    A registry pinned in January and used in June would therefore size every
    JPY-quoted position against a stale rate. This is precisely why
    `value_per_price_unit()` derives from `contract_size` and leaves
    conversion to the caller, with a rate the caller supplies.
    """
    reg = Registry.load(REAL)
    for sym, spot in (("USDJPY", 160.149), ("USDCHF", 0.81019), ("USDCAD", 1.38824)):
        spec = reg[sym]
        implied = (spec.contract_size * spec.tick_size) / spec.tick_value
        assert implied == pytest.approx(spot, rel=0.02), (
            f"{sym}: tick_value implies rate {implied}, spot was {spot}")

    # USD-quoted pairs need no conversion, so the two agree exactly.
    for sym in ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"):
        spec = reg[sym]
        assert spec.contract_size * spec.tick_size == pytest.approx(spec.tick_value)


def test_metals_tick_value_disagrees_by_exactly_ten():
    """Gold and silver are USD-quoted, so no FX rate explains this.

    contract_size * tick_size is 10x the reported tick_value for both metals.
    Whatever the broker's reason, sizing gold from tick_value would be wrong by
    an order of magnitude — which is the concrete cost of the shortcut this
    registry refuses to take.
    """
    reg = Registry.load(REAL)
    for sym in ("XAUUSD", "XAGUSD"):
        spec = reg[sym]
        assert spec.currency_profit == "USD"          # no conversion involved
        derived = spec.contract_size * spec.tick_size
        assert derived / spec.tick_value == pytest.approx(10.0)


def test_ioc_does_not_generalise_across_the_universe():
    """The repo-wide ORDER_FILLING_IOC rule holds for 3 of 9 symbols.

    filling_mode is a bitmask; bit 2 is SYMBOL_FILLING_IOC. Six majors report
    mode 1 — FOK only. Sending IOC to those is the silent-rejection failure the
    architecture rule warns about for ORDER_FILLING_RETURN, arrived at from the
    other direction.
    """
    reg = Registry.load(REAL)
    IOC = 2
    supported = {s for s in reg.symbols if (reg[s].filling_mode or 0) & IOC}
    assert supported == {"NZDUSD", "XAUUSD", "XAGUSD"}
    assert len(reg.symbols) - len(supported) == 6


def test_gold_min_position_risk_from_real_specs():
    """D2's headline, recomputed from broker-confirmed terms."""
    xau = Registry.load(REAL)["XAUUSD"]
    # 0.01 lots x 100 oz = 1 oz; a $14 stop risks $14 = 14% of a $100 account.
    assert xau.min_position_risk(14.0) == pytest.approx(14.0)
