"""tests/test_cost_model.py — tests for Pepperstone XAUUSD cost model."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta

from research.datasets.cost_model import (
    PepperstoneXAUUSDCostModel, CostBreakdown,
    PEPPERSTONE_XAUUSD_RAZOR_MT5_COMMISSION_PER_LOT_RT,
)


class TestSpread(unittest.TestCase):

    def test_spread_at_typical(self):
        m = PepperstoneXAUUSDCostModel.for_scenario("conservative")
        # 0.22 USD/oz * 0.10 lots * 100 oz/lot = $2.20
        self.assertAlmostEqual(m.spread_cost_usd(0.10), 2.20, places=4)

    def test_spread_zero_at_zero_lots(self):
        m = PepperstoneXAUUSDCostModel()
        self.assertEqual(m.spread_cost_usd(0.0), 0.0)


class TestCommission(unittest.TestCase):

    def test_one_lot_round_turn(self):
        m = PepperstoneXAUUSDCostModel.for_scenario("conservative")
        self.assertEqual(m.commission_round_turn_usd(1.0),
                         PEPPERSTONE_XAUUSD_RAZOR_MT5_COMMISSION_PER_LOT_RT)

    def test_pro_rata_for_micro(self):
        m = PepperstoneXAUUSDCostModel.for_scenario("conservative")
        # $7 RT per lot, scaled to 0.01 = $0.07
        self.assertAlmostEqual(m.commission_round_turn_usd(0.01), 0.07, places=4)


class TestSwap(unittest.TestCase):

    def setUp(self):
        # Override placeholders with simple, easy-to-verify rates.
        self.m = PepperstoneXAUUSDCostModel(
            swap_long_per_lot_night=-1.0,
            swap_short_per_lot_night=-2.0,
        )

    def test_no_swap_for_intraday(self):
        # Open and close on the same day before any midnight.
        entry = datetime(2024, 5, 6, 9, 0)   # Mon
        exit_ = datetime(2024, 5, 6, 16, 0)  # Mon same day
        swap, n, t = self.m.swap_usd(0.10, "BUY", entry, exit_)
        self.assertEqual((swap, n, t), (0.0, 0, 0))

    def test_one_night_long(self):
        # Mon 12pm -> Tue 12pm: crosses one midnight (Tue 00:00).
        entry = datetime(2024, 5, 6, 12, 0)
        exit_ = datetime(2024, 5, 7, 12, 0)
        swap, n, t = self.m.swap_usd(1.0, "BUY", entry, exit_)
        self.assertEqual(n, 1)
        self.assertEqual(t, 0)
        self.assertAlmostEqual(swap, -1.0, places=4)

    def test_wednesday_triple_swap(self):
        # Tue 23:00 -> Thu 01:00: crosses Wed 00:00 (triple) and Thu 00:00 (regular).
        entry = datetime(2024, 5, 7, 23, 0)   # Tue
        exit_ = datetime(2024, 5, 9, 1, 0)    # Thu
        swap, n, t = self.m.swap_usd(1.0, "BUY", entry, exit_)
        self.assertEqual(n, 2)        # Wed and Thu midnights
        self.assertEqual(t, 1)        # Wed is the triple-swap day
        # 1 regular + 3*triple = 4 effective nights @ -$1 = -$4
        self.assertAlmostEqual(swap, -4.0, places=4)

    def test_short_uses_short_rate(self):
        entry = datetime(2024, 5, 6, 12, 0)
        exit_ = datetime(2024, 5, 7, 12, 0)
        swap, _, _ = self.m.swap_usd(1.0, "SELL", entry, exit_)
        self.assertAlmostEqual(swap, -2.0, places=4)


class TestCompositeBreakdown(unittest.TestCase):

    def test_full_round_trip(self):
        m = PepperstoneXAUUSDCostModel(
            spread_usd_per_oz=0.22,
            commission_per_lot_round_turn=7.0,
            swap_long_per_lot_night=-10.0,
        )
        # 0.10 lots, BUY, held over one (regular) night.
        entry = datetime(2024, 5, 6, 12, 0)   # Mon
        exit_ = datetime(2024, 5, 7, 12, 0)   # Tue
        cb = m.trade_cost(0.10, "BUY", entry, exit_)
        self.assertIsInstance(cb, CostBreakdown)
        # Spread:  0.22 * 0.10 * 100 = $2.20
        # Commission:  7.0 * 0.10 = $0.70
        # Swap:  1 night * -10 * 0.10 = -$1.00
        # Total: $2.20 + $0.70 + (-$1.00) = $1.90
        self.assertAlmostEqual(cb.spread_usd, 2.20, places=4)
        self.assertAlmostEqual(cb.commission_usd, 0.70, places=4)
        self.assertAlmostEqual(cb.swap_usd, -1.00, places=4)
        self.assertAlmostEqual(cb.total_usd, 1.90, places=4)
        self.assertEqual(cb.nights_held, 1)
        self.assertEqual(cb.triple_swap_nights, 0)


if __name__ == "__main__":
    unittest.main()
