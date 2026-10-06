"""
Order replay — Phase 3 criterion 5.

"MT5APIClient satisfies the resources.execution.broker port, verified by
replaying recorded live orders through both the old client and the port with
identical resulting order parameters."

Two replays, because there are two things that could change.

1. **Strategy paths.** Each live strategy's ``_place_order`` is driven over a
   grid of inputs and everything it sends is captured at the HTTP boundary —
   URL and JSON body — together with the arguments it hands to
   ``create_trade_record``. The baseline in ``fixtures/order_replay_baseline.json``
   was captured from the code *before* the strategies were moved onto the
   port (the parent of the port commit), so this compares the old client path
   with the new one byte for byte, not the new code with itself.

2. **Recorded orders.** ``MT5Broker.submit`` and ``MT5APIClient.send_order``
   are fed the same orders and their HTTP bodies compared. The orders are a
   synthetic set always, plus a real export when ``$QH_RECORDED_ORDERS`` names
   one. The real export is the part of the criterion this repository cannot
   satisfy on its own: the records are in the live Postgres, not here. A JSON
   list of Trade rows (direction, symbol, order_volume, sl, tp, strategy) is
   enough; magic, comment and deviation are per-strategy constants.

Nothing here touches a network or a database: the session's ``post`` is
replaced and ``create_trade_record`` is patched.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.mt5_api import MT5APIClient

FIXTURE = Path(__file__).parent / "fixtures" / "order_replay_baseline.json"
REGENERATE_ENV = "QH_REGENERATE_ORDER_REPLAY"
RECORDED_ENV = "QH_RECORDED_ORDERS"

#: Awkward on purpose: long decimals and a value that is not exactly
#: representable, so a float()/round() slipped into either path shows up.
SL_TP = [(2650.123456789, 2710.987654321), (1999.995, 2000.005), (3301.1, 3200.1)]
LOTS = [0.01, 0.05, 0.1]
SIGNALS = ["BUY", "SELL"]

FAKE_RESPONSE = {
    "success": True, "retcode": 10009, "retcode_description": "done",
    "price": 2675.5, "ticket": 123456789, "order": 123456789, "deal": 987654321,
}


class _Recorder:
    """Stands in for ``requests.Session.post`` and remembers every call."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, url, json=None, timeout=None, verify=None, **kw):
        self.calls.append({"url": url, "body": json})
        resp = MagicMock()
        resp.status_code = 200
        resp.headers = {"content-type": "application/json"}
        resp.json.return_value = dict(FAKE_RESPONSE)
        return resp


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in sorted(obj.items())}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return repr(obj)


def _drive(module_path: str, strategy, calls: list[tuple]) -> list[dict]:
    """Run ``_place_order`` for each argument tuple; capture HTTP and record."""
    out = []
    recorder = _Recorder()
    strategy.mt5_client.session.post = recorder
    with patch(f"{module_path}.create_trade_record") as record:
        for args in calls:
            recorder.calls.clear()
            record.reset_mock()
            strategy._place_order(*args)
            out.append({
                "args": _jsonable(list(args)),
                "http": _jsonable(recorder.calls),
                "record": _jsonable([
                    {"args": list(c.args), "kwargs": dict(c.kwargs)}
                    for c in record.call_args_list
                ]),
            })
    return out


def capture(tmp_path: Path) -> dict[str, list[dict]]:
    from app.quant.strategies.asqs.strategy import ASQSafeScalpingStrategy
    from app.quant.strategies.crest_n_keel.strategy import CrestNKeelStrategy
    from app.quant.strategies.h1_momentum.strategy import H1MomentumStrategy

    base = "http://mt5-replay.invalid:5001"
    cnk = CrestNKeelStrategy(mt5_base_url=base,
                           peak_store_path=str(tmp_path / "cnk_peak.json"))
    asqs = ASQSafeScalpingStrategy(
        mt5_base_url=base,
        peak_store_path=str(tmp_path / "asqs_peak.json"),
        partial_store_path=str(tmp_path / "asqs_partial.json"),
    )
    h1m = H1MomentumStrategy()
    h1m.mt5_client = MT5APIClient(base_url=base)

    grid = [(s, lot, sl, tp, None) for s in SIGNALS for lot in LOTS for sl, tp in SL_TP]
    h1_grid = [(lot, sl, 14.25, 0.93, None) for lot in LOTS for sl, _ in SL_TP]
    return {
        "crest_n_keel": _drive("app.quant.strategies.crest_n_keel.strategy", cnk,
                               grid),
        "asqs": _drive("app.quant.strategies.asqs.strategy", asqs, grid),
        "h1_momentum": _drive("app.quant.strategies.h1_momentum.strategy", h1m, h1_grid),
    }


def test_strategy_order_paths_match_the_pre_port_baseline(tmp_path):
    got = capture(tmp_path)
    if os.environ.get(REGENERATE_ENV) == "1":
        if FIXTURE.exists():
            pytest.fail(f"{FIXTURE.name} exists; a baseline is captured once, from "
                        "the pre-port code, and never regenerated over")
        FIXTURE.write_text(json.dumps(got, indent=1, sort_keys=True) + "\n")
        pytest.skip(f"baseline written to {FIXTURE}")
    want = json.loads(FIXTURE.read_text())
    assert set(got) == set(want)
    for name in want:
        assert len(got[name]) == len(want[name]), name
        for i, (g, w) in enumerate(zip(got[name], want[name])):
            assert g == w, f"{name} case {i} differs from the pre-port baseline"
    # Not vacuous: every case sent exactly one order.
    assert all(len(c["http"]) == 1 for v in got.values() for c in v)


# -- the adapter itself --------------------------------------------------------

from resources.execution.broker import Bar, Broker, FillConfig, OrderRequest  # noqa: E402
from resources.side import Side  # noqa: E402

from app.adapters.broker import (  # noqa: E402
    DEFAULT_DEVIATION, MT5Broker, OrderRejected, side_from_action,
)

BASE = "http://mt5-replay.invalid:5001"
SIGNAL_BAR = Bar(2670.0, 2676.0, 2668.0, 2675.0)

#: Per-strategy constants a Trade row does not carry. Read from the modules
#: rather than restated, so a changed magic number cannot pass by agreement.
def _strategy_constants() -> dict[str, dict[str, Any]]:
    from app.quant.strategies.asqs import strategy as asqs
    from app.quant.strategies.crest_n_keel import strategy as cnk
    from app.quant.strategies.h1_momentum import strategy as h1m
    return {
        "ASQSafeScalpingStrategy": {"magic": asqs.MAGIC_NUMBER, "comment": "ASQSS"},
        "CrestNKeelStrategy": {"magic": cnk.MAGIC_NUMBER, "comment": "HMA1H"},
        "H1MomentumStrategy": {"magic": h1m.MAGIC_NUMBER, "comment": "H1M"},
    }


def _client(recorder: _Recorder) -> MT5APIClient:
    client = MT5APIClient(base_url=BASE)
    client.session.post = recorder
    return client


def _synthetic_orders() -> list[dict[str, Any]]:
    rows = []
    for strategy in _strategy_constants():
        for direction in SIGNALS:
            for vol in LOTS:
                for sl, tp in SL_TP + [(2601.5, None)]:
                    rows.append({"strategy": strategy, "direction": direction,
                                 "symbol": "XAUUSD", "order_volume": vol,
                                 "sl": sl, "tp": tp})
    return rows


def _recorded_orders() -> list[dict[str, Any]]:
    path = os.environ.get(RECORDED_ENV)
    if not path:
        return []
    return json.loads(Path(path).read_text())


def _replay(rows: list[dict[str, Any]]) -> int:
    consts = _strategy_constants()
    compared = 0
    for row in rows:
        c = consts.get(row["strategy"])
        if c is None:
            continue  # e.g. a legacy strategy that does not use the port
        old, new = _Recorder(), _Recorder()
        _client(old).send_order(
            action=row["direction"], symbol=row["symbol"],
            volume=row["order_volume"], order_type="MARKET",
            sl=row.get("sl"), tp=row.get("tp"), deviation=20,
            magic=c["magic"], comment=c["comment"])
        MT5Broker(_client(new)).submit(OrderRequest(
            symbol=row["symbol"], side=side_from_action(row["direction"]),
            volume=row["order_volume"], sl=row.get("sl"), tp=row.get("tp"),
            magic=c["magic"], comment=c["comment"]))
        assert new.calls == old.calls, row
        compared += 1
    return compared


def test_synthetic_orders_send_identical_requests_through_both():
    assert _replay(_synthetic_orders()) == 3 * 2 * 3 * 4


def test_recorded_live_orders_send_identical_requests_through_both():
    rows = _recorded_orders()
    if not rows:
        pytest.skip(f"no recorded orders; set ${RECORDED_ENV} to a JSON export of "
                    "Trade rows to run criterion 5 on real data")
    assert _replay(rows) > 0, "the export held no order from a ported strategy"


def test_the_mt5_broker_satisfies_the_port():
    broker = MT5Broker(_client(_Recorder()))
    assert isinstance(broker, Broker)
    assert broker.config is FillConfig.LIVE
    assert DEFAULT_DEVIATION == 20


@pytest.mark.parametrize("side, price, adverse", [
    (Side.LONG, 2675.5, 0.5), (Side.SHORT, 2675.5, 0.0), (Side.SHORT, 2674.0, 1.0),
])
def test_fill_reports_the_venue_price_and_attributes_cost(side, price, adverse):
    rec = _Recorder()
    client = _client(rec)
    broker = MT5Broker(client)
    resp = dict(FAKE_RESPONSE, price=price)
    with patch.object(client, "send_order", return_value=resp):
        f = broker.fill(OrderRequest("XAUUSD", side, 0.01, sl=2600.0), SIGNAL_BAR)
    assert f.price == price and f.reference_price == SIGNAL_BAR.close
    assert f.slip_cost == pytest.approx(adverse) and f.spread_cost == 0.0
    assert f.total_adverse_cost >= 0.0
    assert f.ticket == FAKE_RESPONSE["ticket"] and f.response == resp


@pytest.mark.parametrize("response", [
    {"success": False, "retcode": 10019, "retcode_description": "no money"},
    None,
])
def test_a_rejected_order_raises_with_the_venue_response(response):
    client = _client(_Recorder())
    with patch.object(client, "send_order", return_value=response):
        with pytest.raises(OrderRejected) as exc:
            MT5Broker(client).fill(OrderRequest("XAUUSD", Side.LONG, 0.01), SIGNAL_BAR)
    assert exc.value.response == response


def test_a_next_bar_means_history_and_nothing_is_sent():
    rec = _Recorder()
    with pytest.raises(ValueError, match="historical data"):
        MT5Broker(_client(rec)).fill(OrderRequest("XAUUSD", Side.LONG, 0.01),
                                     SIGNAL_BAR, next_bar=SIGNAL_BAR)
    assert rec.calls == []


@pytest.mark.parametrize("bad", ["HOLD", "", None, "LONG"])
def test_an_unknown_action_raises_as_the_old_client_did(bad):
    with pytest.raises(ValueError, match="BUY or SELL"):
        side_from_action(bad)
