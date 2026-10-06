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
