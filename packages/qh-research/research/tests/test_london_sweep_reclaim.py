"""london_sweep_reclaim: synthetic checks only. No real outcome is computed."""

from __future__ import annotations

import numpy as np
import pytest

from research.pre import london_sweep_reclaim as ls


def _day(close_path: dict[int, float], base: float = 105.0) -> np.ndarray:
    """A flat day at ``base`` with a $10 Asian range and chosen bars."""
    b = np.full((ls.EXIT_BAR + 1, 4), base)
    b[0, 1], b[1, 2] = 110.0, 100.0            # Asian high and low
    for k, (o, h, l, c) in close_path.items():
        b[k] = (o, h, l, c)
    return b


def _short_setup_day() -> np.ndarray:
    k = ls.KZ_FIRST
    return _day({k: (109.0, 112.0, 108.5, 109.0),     # sweeps 110 + 1.5
                 k + 1: (108.0, 108.2, 107.8, 108.0)})


def test_feature_inputs_are_disjoint_from_the_target_normalizer():
    spec = ls.feature_spec()
    assert not set(spec["feature_inputs"]) & set(spec["target_normalizer"])


def test_a_sweep_and_close_back_inside_is_a_short_setup():
    s, why = ls.find_setup("2020-01-06", _short_setup_day())
    assert why == "setup" and s.direction == -1
    assert s.sweep_bar == s.reclaim_bar == ls.KZ_FIRST
    assert s.entry == 108.0 and s.target == 105.0
    assert s.stop == 112.0                       # extreme, already > entry + 2


def test_the_stop_is_at_least_the_floor_from_entry():
    k = ls.KZ_FIRST
    s, _ = ls.find_setup("d", _day({k: (100.5, 101.0, 98.4, 101.0),
                                    k + 1: (100.2, 100.2, 100.2, 100.2)}))
    assert s.direction == 1 and s.entry == 100.2
    assert s.stop == pytest.approx(100.2 - ls.MIN_STOP_USD)   # extreme 98.4 is closer


@pytest.mark.parametrize("path,why", [
    ({0: (105, 140, 100, 105)}, "width"),
    ({ls.KZ_FIRST: (105, 112, 98, 105)}, "both_sides"),
    ({}, "no_sweep"),
    ({ls.KZ_FIRST: (111, 112, 111, 111.5), ls.KZ_FIRST + 1: (111, 111, 111, 111),
      ls.KZ_FIRST + 2: (111, 111, 111, 111)}, "no_reclaim"),
])
def test_days_that_fail_a_rule_are_skipped_with_the_reason(path, why):
    assert ls.find_setup("d", _day(path)) == (None, why)


def test_a_bar_reaching_stop_and_target_is_a_stop():
    b = _short_setup_day()
    k = ls.KZ_FIRST + 2
    b[k] = (108.0, 113.0, 104.0, 108.0)
    assert ls.simulate(b, -1, ls.KZ_FIRST + 1, 4.0, 3.0) == pytest.approx(-4.0)


def test_an_untouched_trade_exits_at_the_16_00_open():
    b = _short_setup_day()
    b[ls.EXIT_BAR, 0] = 107.0                    # target 103 and stop 112 untouched
    assert ls.simulate(b, -1, ls.KZ_FIRST + 1, 4.0, 5.0) == pytest.approx(1.0)


def test_the_timing_null_finds_a_planted_edge_and_not_a_flat_one():
    rng = np.random.default_rng(0)
    table = rng.normal(0, 1, (400, 12))
    assert ls.timing_test(table[:, 0] + 0.5, table, 500)["p"] < 0.01
    assert ls.timing_test(table[:, 0], table, 500)["p"] > 0.05


def _res(p: float, net: float, n=(200, 200), side_net=(1.0, 1.0)) -> dict:
    return {"streams": {"p_timing": p}, "net_mean_usd": net,
            "sides": {"long": {"n": n[0], "net_mean_usd": side_net[0]},
                      "short": {"n": n[1], "net_mean_usd": side_net[1]}}}


@pytest.mark.parametrize("res,label", [
    (_res(0.01, 1.0, n=(100, 200)), "VOID"),
    (_res(0.20, 1.0), "DEAD"),
    (_res(0.01, -0.1), "UNTRADEABLE"),
    (_res(0.01, 0.5, side_net=(1.0, -0.2)), "ALIVE_ONE_SIDE"),
    (_res(0.01, 0.5), "ALIVE"),
])
def test_the_verdict_applies_the_registered_rule(res, label):
    assert ls.verdict(res, ls.decisive_stream())[0] == label


def test_run_refuses_before_registration(tmp_path):
    with pytest.raises(RuntimeError, match="not registered"):
        ls.run(log_dir=tmp_path)


def test_registration_parameters_are_one_set_for_the_universe():
    params = ls.registration_parameters()
    assert params["symbol"] == ls.SYMBOL and "XAUUSD" not in params.get("by_instrument", {})
    assert params["decisive_stream"] == "p_timing"


def test_a_published_trade_carries_no_price_level():
    s, _ = ls.find_setup("2020-01-06", _short_setup_day())
    t = ls.public_trade(s, 1.0)
    assert not {"entry", "stop", "target", "asian_high", "asian_low"} & set(t)
    assert t["stop_dist_usd"] == 4.0 and t["target_dist_usd"] == 3.0
