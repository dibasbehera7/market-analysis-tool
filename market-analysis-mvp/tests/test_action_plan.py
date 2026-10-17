"""
Unit tests for RecommendationEngine.generate_action_plan() — task 7.4.

Coverage:
  - Returns an ActionPlan instance
  - Compliance disclaimer is always present with exact value
  - Buy/sell ranges populated only when both support and resistance are non-None
  - Target prices computed correctly as midpoints of support/resistance
  - All buy ranges satisfy low <= high
  - All sell ranges satisfy low <= high
  - Target price lies within [support_level, resistance_level]
  - Rebalancing suggestions generated for BUY, SELL, and HOLD symbols
  - Empty recommendations produce "No rebalancing actions required" suggestion
  - Symbols with None support or None resistance are excluded from ranges/targets
  - Mixed BUY/SELL/HOLD recommendations produce all three suggestion types
  - Symbols missing from the insights dict are excluded from ranges/targets

Requirements: 8.1, 8.2, 8.3, 12.2
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from src.models import (
    COMPLIANCE_DISCLAIMER,
    ActionPlan,
    ActionType,
    CompanyMetrics,
    Holding,
    Insight,
    Recommendation,
    Trend,
    TrendType,
)
from src.recommendation import RecommendationEngine


# ---------------------------------------------------------------------------
# Helpers / factories
# ---------------------------------------------------------------------------

def _metrics(symbol: str = "A.NS") -> CompanyMetrics:
    return CompanyMetrics(
        symbol=symbol,
        pe_ratio=15.0,
        pb_ratio=2.0,
        roe=0.18,
        eps_growth=10.0,
        npa=None,
    )


def _trend(
    symbol: str = "A.NS",
    trend_type: TrendType = TrendType.BULLISH,
    support: float | None = 100.0,
    resistance: float | None = 200.0,
) -> Trend:
    return Trend(
        symbol=symbol,
        trend_type=trend_type,
        support_level=support,
        resistance_level=resistance,
    )


def _insight(
    symbol: str = "A.NS",
    current_price: float = 150.0,
    support: float | None = 100.0,
    resistance: float | None = 200.0,
    trend_type: TrendType = TrendType.BULLISH,
) -> Insight:
    return Insight(
        symbol=symbol,
        metrics=_metrics(symbol),
        trend=_trend(symbol, trend_type, support, resistance),
        current_price=current_price,
        summary="Test insight",
    )


def _holding(
    symbol: str = "A.NS",
    quantity: int = 10,
    buy_price: float = 130.0,
    user_id: str = "u1",
) -> Holding:
    return Holding(
        id=str(uuid.uuid4()),
        user_id=user_id,
        symbol=symbol,
        quantity=quantity,
        buy_price=buy_price,
        created_at=datetime.utcnow(),
    )


def _reco(
    symbol: str = "A.NS",
    action: ActionType = ActionType.BUY,
    quantity: int = 5,
) -> Recommendation:
    return Recommendation(
        symbol=symbol,
        action=action,
        quantity=quantity,
        rationale="Test rationale",
        compliance_disclaimer=COMPLIANCE_DISCLAIMER,
    )


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestGenerateActionPlan:

    def setup_method(self) -> None:
        self.engine = RecommendationEngine()

    # -----------------------------------------------------------------------
    # Basic return type
    # -----------------------------------------------------------------------

    def test_returns_action_plan_instance(self) -> None:
        plan = self.engine.generate_action_plan([], {})
        assert isinstance(plan, ActionPlan)

    # -----------------------------------------------------------------------
    # Compliance disclaimer (Requirement 12.2)
    # -----------------------------------------------------------------------

    def test_compliance_disclaimer_present_with_empty_recommendations(self) -> None:
        plan = self.engine.generate_action_plan([], {})
        assert plan.compliance_disclaimer == COMPLIANCE_DISCLAIMER

    def test_compliance_disclaimer_present_with_single_buy(self) -> None:
        reco = _reco("A.NS", ActionType.BUY)
        insight = _insight("A.NS")
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        assert plan.compliance_disclaimer == COMPLIANCE_DISCLAIMER

    def test_compliance_disclaimer_exact_string(self) -> None:
        plan = self.engine.generate_action_plan([], {})
        assert plan.compliance_disclaimer == (
            "Insights only, not financial advice. Educational purpose only."
        )

    def test_compliance_disclaimer_present_with_mixed_recommendations(self) -> None:
        recos = [
            _reco("A.NS", ActionType.BUY),
            _reco("B.NS", ActionType.SELL),
            _reco("C.NS", ActionType.HOLD),
        ]
        insights = {
            "A.NS": _insight("A.NS"),
            "B.NS": _insight("B.NS", trend_type=TrendType.BEARISH),
            "C.NS": _insight("C.NS", trend_type=TrendType.NEUTRAL),
        }
        plan = self.engine.generate_action_plan(recos, insights)
        assert plan.compliance_disclaimer == COMPLIANCE_DISCLAIMER

    # -----------------------------------------------------------------------
    # Recommendations list propagation
    # -----------------------------------------------------------------------

    def test_recommendations_list_is_propagated(self) -> None:
        recos = [_reco("A.NS", ActionType.BUY), _reco("B.NS", ActionType.HOLD)]
        insights = {"A.NS": _insight("A.NS"), "B.NS": _insight("B.NS")}
        plan = self.engine.generate_action_plan(recos, insights)
        assert plan.recommendations == recos

    # -----------------------------------------------------------------------
    # Buy/sell ranges populated only when support AND resistance are non-None
    # (Requirement 8.1)
    # -----------------------------------------------------------------------

    def test_buy_range_populated_when_support_and_resistance_not_none(self) -> None:
        reco = _reco("A.NS", ActionType.BUY)
        insight = _insight("A.NS", current_price=150.0, support=100.0, resistance=200.0)
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        assert "A.NS" in plan.buy_ranges

    def test_sell_range_populated_when_support_and_resistance_not_none(self) -> None:
        reco = _reco("A.NS", ActionType.SELL)
        insight = _insight("A.NS", current_price=150.0, support=100.0, resistance=200.0)
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        assert "A.NS" in plan.sell_ranges

    def test_target_price_populated_when_support_and_resistance_not_none(self) -> None:
        reco = _reco("A.NS", ActionType.BUY)
        insight = _insight("A.NS", current_price=150.0, support=100.0, resistance=200.0)
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        assert "A.NS" in plan.target_prices

    def test_ranges_excluded_when_support_is_none(self) -> None:
        reco = _reco("A.NS", ActionType.BUY)
        insight = _insight("A.NS", support=None, resistance=200.0)
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        assert "A.NS" not in plan.buy_ranges
        assert "A.NS" not in plan.sell_ranges
        assert "A.NS" not in plan.target_prices

    def test_ranges_excluded_when_resistance_is_none(self) -> None:
        reco = _reco("A.NS", ActionType.BUY)
        insight = _insight("A.NS", support=100.0, resistance=None)
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        assert "A.NS" not in plan.buy_ranges
        assert "A.NS" not in plan.sell_ranges
        assert "A.NS" not in plan.target_prices

    def test_ranges_excluded_when_both_support_and_resistance_are_none(self) -> None:
        reco = _reco("A.NS", ActionType.HOLD)
        insight = _insight("A.NS", support=None, resistance=None)
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        assert "A.NS" not in plan.buy_ranges
        assert "A.NS" not in plan.sell_ranges
        assert "A.NS" not in plan.target_prices

    def test_ranges_excluded_when_symbol_not_in_insights(self) -> None:
        reco = _reco("GHOST.NS", ActionType.BUY)
        plan = self.engine.generate_action_plan([reco], {})
        assert "GHOST.NS" not in plan.buy_ranges
        assert "GHOST.NS" not in plan.sell_ranges
        assert "GHOST.NS" not in plan.target_prices

    # -----------------------------------------------------------------------
    # Buy range correctness and invariant low <= high (Requirement 8.1)
    # -----------------------------------------------------------------------

    def test_buy_range_low_equals_min_of_support_and_price(self) -> None:
        reco = _reco("A.NS", ActionType.BUY)
        insight = _insight("A.NS", current_price=150.0, support=100.0, resistance=200.0)
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        low, high = plan.buy_ranges["A.NS"]
        assert low == pytest.approx(min(100.0, 150.0))

    def test_buy_range_high_equals_max_of_support_and_price(self) -> None:
        reco = _reco("A.NS", ActionType.BUY)
        insight = _insight("A.NS", current_price=150.0, support=100.0, resistance=200.0)
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        low, high = plan.buy_ranges["A.NS"]
        assert high == pytest.approx(max(100.0, 150.0))

    def test_buy_range_low_lte_high_normal(self) -> None:
        reco = _reco("A.NS", ActionType.BUY)
        insight = _insight("A.NS", current_price=150.0, support=100.0, resistance=200.0)
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        low, high = plan.buy_ranges["A.NS"]
        assert low <= high

    def test_buy_range_low_lte_high_when_price_below_support(self) -> None:
        # Edge case: current price is below support level
        reco = _reco("A.NS", ActionType.BUY)
        insight = _insight("A.NS", current_price=80.0, support=100.0, resistance=200.0)
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        low, high = plan.buy_ranges["A.NS"]
        assert low <= high

    def test_buy_range_low_lte_high_when_price_equals_support(self) -> None:
        reco = _reco("A.NS", ActionType.BUY)
        insight = _insight("A.NS", current_price=100.0, support=100.0, resistance=200.0)
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        low, high = plan.buy_ranges["A.NS"]
        assert low <= high

    # -----------------------------------------------------------------------
    # Sell range correctness and invariant low <= high (Requirement 8.1)
    # -----------------------------------------------------------------------

    def test_sell_range_low_equals_min_of_price_and_resistance(self) -> None:
        reco = _reco("A.NS", ActionType.SELL)
        insight = _insight("A.NS", current_price=150.0, support=100.0, resistance=200.0)
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        low, high = plan.sell_ranges["A.NS"]
        assert low == pytest.approx(min(150.0, 200.0))

    def test_sell_range_high_equals_max_of_price_and_resistance(self) -> None:
        reco = _reco("A.NS", ActionType.SELL)
        insight = _insight("A.NS", current_price=150.0, support=100.0, resistance=200.0)
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        low, high = plan.sell_ranges["A.NS"]
        assert high == pytest.approx(max(150.0, 200.0))

    def test_sell_range_low_lte_high_normal(self) -> None:
        reco = _reco("A.NS", ActionType.SELL)
        insight = _insight("A.NS", current_price=150.0, support=100.0, resistance=200.0)
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        low, high = plan.sell_ranges["A.NS"]
        assert low <= high

    def test_sell_range_low_lte_high_when_price_above_resistance(self) -> None:
        # Edge case: current price is above resistance level
        reco = _reco("A.NS", ActionType.SELL)
        insight = _insight("A.NS", current_price=250.0, support=100.0, resistance=200.0)
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        low, high = plan.sell_ranges["A.NS"]
        assert low <= high

    def test_sell_range_low_lte_high_when_price_equals_resistance(self) -> None:
        reco = _reco("A.NS", ActionType.SELL)
        insight = _insight("A.NS", current_price=200.0, support=100.0, resistance=200.0)
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        low, high = plan.sell_ranges["A.NS"]
        assert low <= high

    # -----------------------------------------------------------------------
    # Target price correctness (Requirement 8.1)
    # -----------------------------------------------------------------------

    def test_target_price_is_midpoint_of_support_and_resistance(self) -> None:
        reco = _reco("A.NS", ActionType.BUY)
        insight = _insight("A.NS", current_price=150.0, support=100.0, resistance=200.0)
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        assert plan.target_prices["A.NS"] == pytest.approx((100.0 + 200.0) / 2)

    def test_target_price_midpoint_with_asymmetric_range(self) -> None:
        reco = _reco("A.NS", ActionType.BUY)
        insight = _insight("A.NS", current_price=500.0, support=300.0, resistance=700.0)
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        assert plan.target_prices["A.NS"] == pytest.approx(500.0)

    def test_target_price_within_support_resistance_range(self) -> None:
        reco = _reco("A.NS", ActionType.BUY)
        support, resistance = 100.0, 200.0
        insight = _insight("A.NS", current_price=150.0, support=support, resistance=resistance)
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        target = plan.target_prices["A.NS"]
        assert support <= target <= resistance

    def test_target_price_within_range_for_multiple_symbols(self) -> None:
        recos = [_reco("A.NS"), _reco("B.NS")]
        insights = {
            "A.NS": _insight("A.NS", support=50.0, resistance=150.0),
            "B.NS": _insight("B.NS", support=1000.0, resistance=2000.0),
        }
        plan = self.engine.generate_action_plan(recos, insights)
        assert 50.0 <= plan.target_prices["A.NS"] <= 150.0
        assert 1000.0 <= plan.target_prices["B.NS"] <= 2000.0

    # -----------------------------------------------------------------------
    # Rebalancing suggestions (Requirement 8.2)
    # -----------------------------------------------------------------------

    def test_empty_recommendations_produces_no_rebalancing_needed_message(self) -> None:
        plan = self.engine.generate_action_plan([], {})
        assert len(plan.rebalancing_suggestions) == 1
        assert plan.rebalancing_suggestions[0] == "No rebalancing actions required at this time."

    def test_buy_recommendation_produces_increase_positions_suggestion(self) -> None:
        reco = _reco("A.NS", ActionType.BUY)
        insight = _insight("A.NS")
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        assert any("Consider increasing positions" in s for s in plan.rebalancing_suggestions)

    def test_buy_suggestion_contains_symbol(self) -> None:
        reco = _reco("RELIANCE.NS", ActionType.BUY)
        insight = _insight("RELIANCE.NS")
        plan = self.engine.generate_action_plan([reco], {"RELIANCE.NS": insight})
        buy_suggestions = [s for s in plan.rebalancing_suggestions if "increasing" in s]
        assert any("RELIANCE.NS" in s for s in buy_suggestions)

    def test_sell_recommendation_produces_reduce_positions_suggestion(self) -> None:
        reco = _reco("A.NS", ActionType.SELL)
        insight = _insight("A.NS", trend_type=TrendType.BEARISH)
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        assert any("Consider reducing or exiting positions" in s for s in plan.rebalancing_suggestions)

    def test_sell_suggestion_contains_symbol(self) -> None:
        reco = _reco("HDFCBANK.NS", ActionType.SELL)
        insight = _insight("HDFCBANK.NS")
        plan = self.engine.generate_action_plan([reco], {"HDFCBANK.NS": insight})
        sell_suggestions = [s for s in plan.rebalancing_suggestions if "reducing" in s]
        assert any("HDFCBANK.NS" in s for s in sell_suggestions)

    def test_hold_recommendation_produces_maintain_positions_suggestion(self) -> None:
        reco = _reco("A.NS", ActionType.HOLD)
        insight = _insight("A.NS", trend_type=TrendType.NEUTRAL)
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        assert any("Maintain current positions" in s for s in plan.rebalancing_suggestions)

    def test_hold_suggestion_contains_symbol(self) -> None:
        reco = _reco("TCS.NS", ActionType.HOLD)
        insight = _insight("TCS.NS")
        plan = self.engine.generate_action_plan([reco], {"TCS.NS": insight})
        hold_suggestions = [s for s in plan.rebalancing_suggestions if "Maintain" in s]
        assert any("TCS.NS" in s for s in hold_suggestions)

    def test_only_buy_recommendations_produces_no_sell_or_hold_suggestion(self) -> None:
        recos = [_reco("A.NS", ActionType.BUY), _reco("B.NS", ActionType.BUY)]
        insights = {"A.NS": _insight("A.NS"), "B.NS": _insight("B.NS")}
        plan = self.engine.generate_action_plan(recos, insights)
        assert not any("reducing" in s for s in plan.rebalancing_suggestions)
        assert not any("Maintain" in s for s in plan.rebalancing_suggestions)

    def test_only_sell_recommendations_produces_no_buy_or_hold_suggestion(self) -> None:
        recos = [_reco("A.NS", ActionType.SELL)]
        insights = {"A.NS": _insight("A.NS")}
        plan = self.engine.generate_action_plan(recos, insights)
        assert not any("increasing" in s for s in plan.rebalancing_suggestions)
        assert not any("Maintain" in s for s in plan.rebalancing_suggestions)

    def test_only_hold_recommendations_produces_no_buy_or_sell_suggestion(self) -> None:
        recos = [_reco("A.NS", ActionType.HOLD)]
        insights = {"A.NS": _insight("A.NS")}
        plan = self.engine.generate_action_plan(recos, insights)
        assert not any("increasing" in s for s in plan.rebalancing_suggestions)
        assert not any("reducing" in s for s in plan.rebalancing_suggestions)

    # -----------------------------------------------------------------------
    # Mixed BUY/SELL/HOLD → all three suggestion types present (Req 8.2)
    # -----------------------------------------------------------------------

    def test_mixed_recommendations_produce_all_three_suggestion_types(self) -> None:
        recos = [
            _reco("A.NS", ActionType.BUY),
            _reco("B.NS", ActionType.SELL),
            _reco("C.NS", ActionType.HOLD),
        ]
        insights = {
            "A.NS": _insight("A.NS"),
            "B.NS": _insight("B.NS"),
            "C.NS": _insight("C.NS"),
        }
        plan = self.engine.generate_action_plan(recos, insights)
        suggestions_text = " ".join(plan.rebalancing_suggestions)
        assert "increasing" in suggestions_text
        assert "reducing" in suggestions_text
        assert "Maintain" in suggestions_text

    def test_mixed_suggestions_contain_correct_symbols(self) -> None:
        recos = [
            _reco("BUY_STOCK.NS", ActionType.BUY),
            _reco("SELL_STOCK.NS", ActionType.SELL),
            _reco("HOLD_STOCK.NS", ActionType.HOLD),
        ]
        insights = {
            "BUY_STOCK.NS": _insight("BUY_STOCK.NS"),
            "SELL_STOCK.NS": _insight("SELL_STOCK.NS"),
            "HOLD_STOCK.NS": _insight("HOLD_STOCK.NS"),
        }
        plan = self.engine.generate_action_plan(recos, insights)
        buy_sugg = next(s for s in plan.rebalancing_suggestions if "increasing" in s)
        sell_sugg = next(s for s in plan.rebalancing_suggestions if "reducing" in s)
        hold_sugg = next(s for s in plan.rebalancing_suggestions if "Maintain" in s)
        assert "BUY_STOCK.NS" in buy_sugg
        assert "SELL_STOCK.NS" in sell_sugg
        assert "HOLD_STOCK.NS" in hold_sugg

    # -----------------------------------------------------------------------
    # Multiple symbols — ranges computed for each
    # -----------------------------------------------------------------------

    def test_multiple_symbols_each_get_own_ranges(self) -> None:
        recos = [_reco("A.NS", ActionType.BUY), _reco("B.NS", ActionType.BUY)]
        insights = {
            "A.NS": _insight("A.NS", current_price=150.0, support=100.0, resistance=200.0),
            "B.NS": _insight("B.NS", current_price=500.0, support=400.0, resistance=600.0),
        }
        plan = self.engine.generate_action_plan(recos, insights)
        assert "A.NS" in plan.buy_ranges
        assert "B.NS" in plan.buy_ranges
        assert "A.NS" in plan.target_prices
        assert "B.NS" in plan.target_prices

    def test_multiple_symbols_independent_target_prices(self) -> None:
        recos = [_reco("A.NS"), _reco("B.NS")]
        insights = {
            "A.NS": _insight("A.NS", support=100.0, resistance=200.0),
            "B.NS": _insight("B.NS", support=400.0, resistance=800.0),
        }
        plan = self.engine.generate_action_plan(recos, insights)
        assert plan.target_prices["A.NS"] == pytest.approx(150.0)
        assert plan.target_prices["B.NS"] == pytest.approx(600.0)

    # -----------------------------------------------------------------------
    # Partial insights (some symbols have None support/resistance)
    # -----------------------------------------------------------------------

    def test_only_symbols_with_valid_levels_get_ranges(self) -> None:
        recos = [
            _reco("GOOD.NS", ActionType.BUY),
            _reco("BAD.NS", ActionType.BUY),
        ]
        insights = {
            "GOOD.NS": _insight("GOOD.NS", support=100.0, resistance=200.0),
            "BAD.NS": _insight("BAD.NS", support=None, resistance=None),
        }
        plan = self.engine.generate_action_plan(recos, insights)
        assert "GOOD.NS" in plan.buy_ranges
        assert "BAD.NS" not in plan.buy_ranges
        assert "GOOD.NS" in plan.target_prices
        assert "BAD.NS" not in plan.target_prices

    # -----------------------------------------------------------------------
    # Empty input edge cases
    # -----------------------------------------------------------------------

    def test_empty_recommendations_produces_empty_buy_ranges(self) -> None:
        plan = self.engine.generate_action_plan([], {})
        assert plan.buy_ranges == {}

    def test_empty_recommendations_produces_empty_sell_ranges(self) -> None:
        plan = self.engine.generate_action_plan([], {})
        assert plan.sell_ranges == {}

    def test_empty_recommendations_produces_empty_target_prices(self) -> None:
        plan = self.engine.generate_action_plan([], {})
        assert plan.target_prices == {}

    def test_empty_recommendations_with_nonempty_insights(self) -> None:
        insights = {"A.NS": _insight("A.NS")}
        plan = self.engine.generate_action_plan([], insights)
        assert plan.buy_ranges == {}
        assert plan.rebalancing_suggestions == ["No rebalancing actions required at this time."]

    # -----------------------------------------------------------------------
    # Symmetry: buy_ranges and sell_ranges are always computed for ALL symbols
    # regardless of the recommendation action
    # -----------------------------------------------------------------------

    def test_hold_recommendation_still_gets_ranges_when_support_resistance_present(
        self,
    ) -> None:
        """Ranges are computed for every symbol that has a matching insight with
        non-None support/resistance, regardless of the action type."""
        reco = _reco("A.NS", ActionType.HOLD)
        insight = _insight("A.NS", current_price=150.0, support=100.0, resistance=200.0)
        plan = self.engine.generate_action_plan([reco], {"A.NS": insight})
        assert "A.NS" in plan.buy_ranges
        assert "A.NS" in plan.sell_ranges
        assert "A.NS" in plan.target_prices
