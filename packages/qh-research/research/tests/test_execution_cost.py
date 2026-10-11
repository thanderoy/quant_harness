"""Execution cost from live fills: sign convention, estimators, privacy.

All synthetic. The real per-fill dump is a real-money account's history and
never enters the repo, so nothing here needs it.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from research.datasets import execution_cost as ec

T0 = 1_739_204_469_848  # 2025-02-10T16:21:09.848 server-clock epoch, ms


def fill(side: str, price: float, *, bid: float = 100.00, ask: float = 100.20,
         entry: str = "IN", symbol: str = "XAUUSD", t_msc: int = T0,
         pre_age_s: int = 1) -> dict:
    return {"symbol": symbol, "side": side, "entry": entry, "reason": "EXPERT",
            "volume": 0.01, "price": price, "time_msc": t_msc,
            "quotes": {"pre": {"t": t_msc // 1000 - pre_age_s,
                               "bid": bid, "ask": ask}}}


def m5(symbol_open: float, high: float, low: float, close: float,
       t_msc: int = T0) -> pd.DataFrame:
    key = pd.Timestamp(t_msc, unit="ms", tz="UTC").floor("5min")
    return pd.DataFrame({"open": [symbol_open], "high": [high], "low": [low],
                         "close": [close]}, index=pd.DatetimeIndex([key]))


def test_a_buy_at_the_ask_has_zero_slip_and_half_a_spread_vs_mid():
    q = ec.quote_costs([fill("BUY", 100.20)])
    row = q.iloc[0]
    assert row.slip == pytest.approx(0.0)
    assert row.vs_mid == pytest.approx(0.10)
    assert row.spread == pytest.approx(0.20)


def test_a_sell_at_the_bid_has_zero_slip_and_half_a_spread_vs_mid():
    row = ec.quote_costs([fill("SELL", 100.00)]).iloc[0]
    assert row.slip == pytest.approx(0.0)
    assert row.vs_mid == pytest.approx(0.10)


def test_adverse_is_positive_on_both_sides():
    """A buy that paid up and a sell that was paid down are both costs."""
    q = ec.quote_costs([fill("BUY", 100.25), fill("SELL", 99.95)])
    assert list(q.slip.round(8)) == [0.05, 0.05]


def test_favourable_fills_are_negative_and_never_clipped():
    """Clipping at zero turns symmetric noise into a one-sided cost."""
    q = ec.quote_costs([fill("BUY", 100.15), fill("SELL", 100.05)])
    assert list(q.slip.round(8)) == [-0.05, -0.05]


def test_a_fill_with_no_pre_quote_is_dropped_not_zeroed():
    f = fill("BUY", 100.2)
    f["quotes"] = {"pre": None}
    assert ec.quote_costs([f]).empty


def test_staleness_is_measured_from_the_fill_second():
    q = ec.quote_costs([fill("BUY", 100.2, pre_age_s=7)])
    assert q.iloc[0].staleness_s == 7


def test_bar_method_signs_by_side_and_orients_range_position():
    bars = {"XAUUSD": m5(100.0, 101.0, 99.0, 100.5)}
    b = ec.bar_costs([fill("BUY", 100.8), fill("SELL", 99.2)], bars)
    buy, sell = b.iloc[0], b.iloc[1]
    assert buy.vs_open == pytest.approx(0.8)
    assert sell.vs_open == pytest.approx(0.8)
    # 1.0 is the worst price for the side: the high for a buy, low for a sell.
    assert buy.range_pos == pytest.approx(0.9)
    assert sell.range_pos == pytest.approx(0.9)


def test_bar_method_skips_fills_without_a_bar():
    bars = {"XAUUSD": m5(100.0, 101.0, 99.0, 100.5, t_msc=T0 + 3_600_000)}
    assert ec.bar_costs([fill("BUY", 100.2)], bars).empty


def test_alignment_scan_peaks_at_the_true_offset():
    """A fill sits in its own bar; shifted hours away it does not."""
    idx = pd.date_range(pd.Timestamp(T0, unit="ms", tz="UTC").floor("5min")
                        - pd.Timedelta(hours=4), periods=12 * 8, freq="5min")
    df = pd.DataFrame({"open": 50.0, "high": 51.0, "low": 49.0, "close": 50.0},
                      index=idx)
    df.loc[pd.Timestamp(T0, unit="ms", tz="UTC").floor("5min"),
           ["open", "high", "low", "close"]] = [100.0, 101.0, 99.0, 100.0]
    scan = ec.alignment_scan([fill("SELL", 100.0)], {"XAUUSD": df})
    assert scan["0"]["share"] == 1.0
    assert all(scan[k]["share"] == 0.0 for k in scan if k != "0")


def test_summary_reports_price_and_ticks():
    q = ec.quote_costs([fill("BUY", 100.20 + 0.01 * k) for k in range(5)])
    s = ec.summarise(q, "slip", {"XAUUSD": 0.01})
    assert s["XAUUSD"]["BUY"]["n"] == 5
    assert s["XAUUSD"]["BUY"]["ticks"]["p50"] == pytest.approx(2.0)
    assert s["XAUUSD"]["ALL"]["price"]["p90"] == pytest.approx(0.036)


def test_report_is_entry_conditional_and_carries_no_identity():
    """R7: the headline is the IN leg. And nothing per-fill leaks out."""
    fills = [fill("BUY", 100.21), fill("SELL", 99.90, entry="OUT")]
    for f in fills:
        f.update(ticket=111111, order=222222, position_id=333333)
    raw = {"run": {"collected_at_utc": "x", "broker": {"server": "S"},
                   "span": ["a", "b"], "tick_size": {"XAUUSD": {"tick_size": 0.01}}},
           "fills": fills}
    rep = ec.build_report(raw, {}, {})
    assert rep["source"]["n_entries"] == 1
    assert rep["quote_method"]["entries"]["slip_vs_touch"]["XAUUSD"]["ALL"]["n"] == 1
    assert rep["quote_method"]["exits"]["slip_vs_touch"]["XAUUSD"]["ALL"]["n"] == 1
    text = json.dumps(rep, default=str)
    for ident in ("111111", "222222", "333333", str(T0)):
        assert ident not in text

