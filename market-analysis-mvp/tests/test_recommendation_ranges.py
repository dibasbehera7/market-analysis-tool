"""
Unit tests for RecommendationEngine quantity, range, and target price helpers.

Coverage (task 7.2):
  - compute_suggested_quantity: BUY/SELL/HOLD actions, zero/negative price edge cases
  - compute_buy_range: normal, inverted inputs, equal values
  - compute_sell_range: normal, inverted inputs, equal values
  - compute_target_price: midpoint, equal support/resistance

Requirements: 7.3, 8.1
"""

from __future__ import annotations

import math

import pytest

from src.models import ActionType
from src.recommendation import RecommendationEngine


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine() -> RecommendationEngine:
    return RecommendationEngine()


# ---------------------------------------------------------------------------
# compute_suggested_quantity
# ---------------------------------------------------------------------------

class TestComputeSuggestedQuantity:

    # --- BUY action ---

    def test_buy_typical_case(self):
        # floor(10_000 / 250.0) = 40
        result = RecommendationEngine.compute_suggested_quantity(
            ActionType.BUY, daily_investment=10_000.0, current_price=250.0, holding_qty=5
        )
        assert result == 40

    def test_buy_fractional_result_is_floored(self):
        # floor(1000 / 300) = 3  (not 3.33…)
        result = RecommendationEngine.compute_suggested_quantity(
            ActionType.BUY, daily_investment=1_000.0, current_price=300.0, holding_qty=0
        )
        assert result == 3

    def test_buy_result_is_non_negative_integer(self):
        result = RecommendationEngine.compute_suggested_quantity(
            ActionType.BUY, daily_investment=500.0, current_price=1_000.0, holding_qty=2
        )
        assert isinstance(result, int)
        assert result >= 0

    def test_buy_investment_smaller_than_price_returns_zero(self):
        # floor(50 / 100) = 0
        result = RecommendationEngine.compute_suggested_quantity(
            ActionType.BUY, daily_investment=50.0, current_price=100.0, holding_qty=10
        )
        assert result == 0

    def test_buy_zero_price_returns_zero(self):
        # Guard against divide-by-zero
        result = RecommendationEngine.compute_suggested_quantity(
            ActionType.BUY, daily_investment=5_000.0, current_price=0.0, holding_qty=10
        )
        assert result == 0

    def test_buy_negative_price_returns_zero(self):
        result = RecommendationEngine.compute_suggested_quantity(
            ActionType.BUY, daily_investment=5_000.0, current_price=-50.0, holding_qty=10
        )
        assert result == 0

    def test_buy_holding_qty_not_used(self):
        # BUY only depends on daily_investment and current_price, not holding_qty
        r1 = RecommendationEngine.compute_suggested_quantity(
            ActionType.BUY, daily_investment=1_000.0, current_price=100.0, holding_qty=0
        )
        r2 = RecommendationEngine.compute_suggested_quantity(
            ActionType.BUY, daily_investment=1_000.0, current_price=100.0, holding_qty=999
        )
        assert r1 == r2 == 10

    # --- SELL action ---

    def test_sell_returns_holding_qty(self):
        result = RecommendationEngine.compute_suggested_quantity(
            ActionType.SELL, daily_investment=10_000.0, current_price=250.0, holding_qty=7
        )
        assert result == 7

    def test_sell_zero_holding_returns_zero(self):
        result = RecommendationEngine.compute_suggested_quantity(
            ActionType.SELL, daily_investment=10_000.0, current_price=250.0, holding_qty=0
        )
        assert result == 0

    def test_sell_result_is_non_negative_integer(self):
        result = RecommendationEngine.compute_suggested_quantity(
            ActionType.SELL, daily_investment=10_000.0, current_price=250.0, holding_qty=3
        )
        assert isinstance(result, int)
        assert result >= 0

    def test_sell_daily_investment_not_used(self):
        # SELL only depends on holding_qty, not daily_investment or price
        r1 = RecommendationEngine.compute_suggested_quantity(
            ActionType.SELL, daily_investment=0.0, current_price=1.0, holding_qty=5
        )
        r2 = RecommendationEngine.compute_suggested_quantity(
            ActionType.SELL, daily_investment=999_999.0, current_price=999.0, holding_qty=5
        )
        assert r1 == r2 == 5

    # --- HOLD action ---

    def test_hold_returns_zero(self):
        result = RecommendationEngine.compute_suggested_quantity(
            ActionType.HOLD, daily_investment=10_000.0, current_price=250.0, holding_qty=7
        )
        assert result == 0

    def test_hold_ignores_all_other_params(self):
        result = RecommendationEngine.compute_suggested_quantity(
            ActionType.HOLD, daily_investment=0.0, current_price=0.0, holding_qty=0
        )
        assert result == 0

    def test_hold_result_is_non_negative_integer(self):
        result = RecommendationEngine.compute_suggested_quantity(
            ActionType.HOLD, daily_investment=5_000.0, current_price=100.0, holding_qty=10
        )
        assert isinstance(result, int)
        assert result >= 0


# ---------------------------------------------------------------------------
# compute_buy_range
# ---------------------------------------------------------------------------

class TestComputeBuyRange:

    def test_normal_case_support_below_price(self):
        low, high = RecommendationEngine.compute_buy_range(
            support_level=200.0, current_price=250.0
        )
        assert low == pytest.approx(200.0)
        assert high == pytest.approx(250.0)

    def test_inverted_inputs_current_price_below_support(self):
        # current_price < support_level: low should still be the smaller value
        low, high = RecommendationEngine.compute_buy_range(
            support_level=300.0, current_price=250.0
        )
        assert low == pytest.approx(250.0)
        assert high == pytest.approx(300.0)

    def test_equal_values_low_equals_high(self):
        low, high = RecommendationEngine.compute_buy_range(
            support_level=200.0, current_price=200.0
        )
        assert low == pytest.approx(200.0)
        assert high == pytest.approx(200.0)

    def test_invariant_low_lte_high(self):
        for support, price in [(100.0, 150.0), (150.0, 100.0), (200.0, 200.0)]:
            low, high = RecommendationEngine.compute_buy_range(support, price)
            assert low <= high, f"Invariant violated for support={support}, price={price}"

    def test_returns_tuple_of_two_floats(self):
        result = RecommendationEngine.compute_buy_range(100.0, 150.0)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_large_values(self):
        low, high = RecommendationEngine.compute_buy_range(
            support_level=50_000.0, current_price=75_000.0
        )
        assert low == pytest.approx(50_000.0)
        assert high == pytest.approx(75_000.0)


# ---------------------------------------------------------------------------
# compute_sell_range
# ---------------------------------------------------------------------------

class TestComputeSellRange:

    def test_normal_case_price_below_resistance(self):
        low, high = RecommendationEngine.compute_sell_range(
            current_price=250.0, resistance_level=350.0
        )
        assert low == pytest.approx(250.0)
        assert high == pytest.approx(350.0)

    def test_inverted_inputs_resistance_below_price(self):
        # resistance_level < current_price: low should still be the smaller value
        low, high = RecommendationEngine.compute_sell_range(
            current_price=400.0, resistance_level=350.0
        )
        assert low == pytest.approx(350.0)
        assert high == pytest.approx(400.0)

    def test_equal_values_low_equals_high(self):
        low, high = RecommendationEngine.compute_sell_range(
            current_price=300.0, resistance_level=300.0
        )
        assert low == pytest.approx(300.0)
        assert high == pytest.approx(300.0)

    def test_invariant_low_lte_high(self):
        for price, resistance in [(100.0, 150.0), (150.0, 100.0), (200.0, 200.0)]:
            low, high = RecommendationEngine.compute_sell_range(price, resistance)
            assert low <= high, f"Invariant violated for price={price}, resistance={resistance}"

    def test_returns_tuple_of_two_floats(self):
        result = RecommendationEngine.compute_sell_range(250.0, 350.0)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_large_values(self):
        low, high = RecommendationEngine.compute_sell_range(
            current_price=100_000.0, resistance_level=120_000.0
        )
        assert low == pytest.approx(100_000.0)
        assert high == pytest.approx(120_000.0)


# ---------------------------------------------------------------------------
# compute_target_price
# ---------------------------------------------------------------------------

class TestComputeTargetPrice:

    def test_simple_midpoint(self):
        result = RecommendationEngine.compute_target_price(
            support_level=100.0, resistance_level=200.0
        )
        assert result == pytest.approx(150.0)

    def test_equal_support_and_resistance(self):
        # Midpoint of identical values equals the value itself
        result = RecommendationEngine.compute_target_price(
            support_level=250.0, resistance_level=250.0
        )
        assert result == pytest.approx(250.0)

    def test_support_close_to_resistance(self):
        result = RecommendationEngine.compute_target_price(
            support_level=100.0, resistance_level=101.0
        )
        assert result == pytest.approx(100.5)

    def test_large_values(self):
        result = RecommendationEngine.compute_target_price(
            support_level=10_000.0, resistance_level=20_000.0
        )
        assert result == pytest.approx(15_000.0)

    def test_fractional_values(self):
        result = RecommendationEngine.compute_target_price(
            support_level=1.5, resistance_level=2.5
        )
        assert result == pytest.approx(2.0)

    def test_target_lies_between_support_and_resistance(self):
        support = 80.0
        resistance = 120.0
        target = RecommendationEngine.compute_target_price(support, resistance)
        assert support <= target <= resistance

    def test_formula_matches_arithmetic_midpoint(self):
        support, resistance = 123.45, 678.90
        expected = (support + resistance) / 2
        result = RecommendationEngine.compute_target_price(support, resistance)
        assert result == pytest.approx(expected)
