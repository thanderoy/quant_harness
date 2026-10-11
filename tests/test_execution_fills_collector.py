"""The execution-fills collector strips identity and splits quotes correctly.

Pure functions only — the collector's network path is the shared ``_client``,
which ``test_collector_abort`` already covers.
"""

from __future__ import annotations

from datetime import datetime, timezone

from phase0.collectors import execution_fills as ef

FILL_S = 1_739_204_469  # 2025-02-10T16:21:09


def deal(**kw) -> dict:
    base = {"ticket": 900001, "order": 900002, "position_id": 900003,
            "magic": 4242, "comment": "x", "external_id": "y",
            "symbol": "XAUUSD", "type": 0, "entry": 0, "reason": 3,
            "volume": 0.01, "price": 2904.26, "time_msc": FILL_S * 1000 + 848}
    base.update(kw)
    return base


def test_identity_is_dropped_at_the_boundary():
    rec = ef.trade_deals([deal()])[0]
    assert set(rec) == {"symbol", "volume", "price", "time_msc",
                        "side", "entry", "reason"}
    assert (rec["side"], rec["entry"], rec["reason"]) == ("BUY", "IN", "EXPERT")


def test_non_trade_deals_are_skipped():
    """Balance and credit deals have no market price."""
    assert ef.trade_deals([deal(type=2, symbol=""), deal(type=6)]) == []


def test_deals_come_back_in_time_order():
    out = ef.trade_deals([deal(time_msc=2000), deal(time_msc=1000, type=1)])
    assert [r["time_msc"] for r in out] == [1000, 2000]
    assert out[0]["side"] == "SELL"


def _tick(offset_s: int, bid: float, ask: float) -> dict:
    t = datetime.fromtimestamp(FILL_S + offset_s, tz=timezone.utc)
    return {"time": t.strftime("%Y-%m-%dT%H:%M:%SZ"), "bid": bid, "ask": ask}


def test_quotes_split_before_during_and_after_the_fill_second():
    ticks = [_tick(-3, 1.0, 1.2), _tick(-1, 2.0, 2.2), _tick(0, 3.0, 3.2),
             _tick(0, 4.0, 4.2), _tick(2, 5.0, 5.2), _tick(3, 6.0, 6.2)]
    q = ef.quotes_around(ticks, FILL_S)
    assert q["pre"]["bid"] == 2.0
    assert q["same_first"]["bid"] == 3.0
    assert q["same_last"]["bid"] == 4.0
    assert q["n_same"] == 2
    assert q["post"]["bid"] == 5.0


def test_an_empty_quote_is_ignored():
    q = ef.quotes_around([_tick(-1, 0.0, 0.0)], FILL_S)
    assert q["pre"] is None
