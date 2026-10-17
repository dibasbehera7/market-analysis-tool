"""
Unit tests for src/recommendation.py — task 7.1.

Coverage:
  - compare_holding_to_insight() is_profit flag
  - generate_recommendation() action rules (BUY / SELL / HOLD)
  - generate_recommendation() compliance disclaimer always attached
  - generate_recommendation() rationale is a non-empty string
  - Edge cases: BULLISH at/above resistance, BEARISH at/above cost basis
"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.models import (
    ActionType,
    Comparison,
    COMPLIANCE_DISCLAIMER,
    CompanyMetrics,
    Holding,
    Insight,
    Recommendation,
    Trend,
    TrendType,
)
from src.recommendation import RecommendationEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _holding(
    symbol: str = "RELIANCE.NS",
    quantity: int = 10,
    buy_price: float = 2000.0,
    user_id: str = "user1",
) -> Holding:
    return Holding(
        id="test-id",
        user_id=user_id,
        symbol=symbol,
        quantity=quantity,
        buy_price=buy_price,
        created_at=datetime(2024, 1, 1),
    )


def _metrics(symbol: str = "RELIANCE.NS") -> CompanyMetrics:
    return CompanyMetrics(
        symbol=symbol,
        pe_ratio=15.0,
        pb_ratio=2.5,
        roe=0.18,
        eps_growth=10.0,
        npa=None,
    )


def _insight(
    symbol: str = "RELIANCE.NS",
    trend_type: TrendType = TrendType.BULLISH,
    current_price: float = 2500.0,
    support_level: float | None = 1800.0,
    resistance_level: float | None = 3000.0,
) -> Insight:
    return Insight(
        symbol=symbol,
        metrics=_metrics(symbol),
        trend=Trend(
            symbol=symbol,
            trend_type=trend_type,
            support_level=support_level,
            resistance_level=resistance_level,
        ),
        current_price=current_price,
        summary="test summary",
    )


# ---------------------------------------------------------------------------
# compare_holding_to_insight
# ---------------------------------------------------------------------------

class TestCompareHoldingToInsight:

    def test_returns_comparison_instance(self):
        holding = _holding()
        insight = _insight(current_price=2500.0)
        result = RecommendationEngine.compare_holding_to_insight(holding, insight, 2000.0)
        assert isinstance(result, Comparison)

    def test_holding_propagated(self):
        holding = _holding()
        insight = _insight()
        result = RecommendationEngine.compare_holding_to_insight(holding, insight, 2000.0)
        assert result.holding is holding

    def test_insight_propagated(self):
        holding = _holding()
        insight = _insight()
        result = RecommendationEngine.compare_holding_to_insight(holding, insight, 2000.0)
        assert result.insight is insight

    def test_cost_basis_propagated(self):
        holding = _holding()
        insight = _insight()
        result = RecommendationEngine.compare_holding_to_insight(holding, insight, 1950.0)
        assert result.cost_basis == pytest.approx(1950.0)

    def test_is_profit_true_when_price_above_cost_basis(self):
        # current_price=2500 > cost_basis=2000
        result = RecommendationEngine.compare_holding_to_insight(
            _holding(), _insight(current_price=2500.0), cost_basis=2000.0
        )
        assert result.is_profit is True

    def test_is_profit_false_when_price_below_cost_basis(self):
        # current_price=1500 < cost_basis=2000
        result = RecommendationEngine.compare_holding_to_insight(
            _holding(), _insight(current_price=1500.0), cost_basis=2000.0
        )
        assert result.is_profit is False

    def test_is_profit_false_when_price_equals_cost_basis(self):
        # current_price=2000 == cost_basis=2000 → not strictly greater
        result = RecommendationEngine.compare_holding_to_insight(
            _holding(), _insight(current_price=2000.0), cost_basis=2000.0
        )
        assert result.is_profit is False


# ---------------------------------------------------------------------------
# generate_recommendation — action rules
# ---------------------------------------------------------------------------

class TestGenerateRecommendationActions:

    def test_bullish_below_resistance_yields_buy(self):
        # BULLISH + current_price(2500) < resistance(3000) → BUY
        reco = RecommendationEngine.generate_recommendation(
            holding=_holding(),
            insight=_insight(trend_type=TrendType.BULLISH, current_price=2500.0, resistance_level=3000.0),
            cost_basis=2000.0,
            current_price=2500.0,
        )
        assert reco.action == ActionType.BUY

    def test_bearish_below_cost_basis_yields_sell(self):
        # BEARISH + current_price(1800) < cost_basis(2000) → SELL
        reco = RecommendationEngine.generate_recommendation(
            holding=_holding(),
            insight=_insight(trend_type=TrendType.BEARISH, current_price=1800.0),
            cost_basis=2000.0,
            current_price=1800.0,
        )
        assert reco.action == ActionType.SELL

    def test_neutral_trend_yields_hold(self):
        # NEUTRAL → HOLD
        reco = RecommendationEngine.generate_recommendation(
            holding=_holding(),
            insight=_insight(trend_type=TrendType.NEUTRAL, current_price=2500.0),
            cost_basis=2000.0,
            current_price=2500.0,
        )
        assert reco.action == ActionType.HOLD

    def test_bullish_at_resistance_yields_hold(self):
        # BULLISH but current_price(3000) == resistance(3000) → not strictly below → HOLD
        reco = RecommendationEngine.generate_recommendation(
            holding=_holding(),
            insight=_insight(trend_type=TrendType.BULLISH, current_price=3000.0, resistance_level=3000.0),
            cost_basis=2000.0,
            current_price=3000.0,
        )
        assert reco.action == ActionType.HOLD

    def test_bullish_above_resistance_yields_hold(self):
        # BULLISH but current_price(3500) > resistance(3000) → HOLD
        reco = RecommendationEngine.generate_recommendation(
            holding=_holding(),
            insight=_insight(trend_type=TrendType.BULLISH, current_price=3500.0, resistance_level=3000.0),
            cost_basis=2000.0,
            current_price=3500.0,
        )
        assert reco.action == ActionType.HOLD

    def test_bearish_at_cost_basis_yields_hold(self):
        # BEARISH but current_price(2000) == cost_basis(2000) → not strictly below → HOLD
        reco = RecommendationEngine.generate_recommendation(
            holding=_holding(),
            insight=_insight(trend_type=TrendType.BEARISH, current_price=2000.0),
            cost_basis=2000.0,
            current_price=2000.0,
        )
        assert reco.action == ActionType.HOLD

    def test_bearish_above_cost_basis_yields_hold(self):
        # BEARISH but current_price(2500) > cost_basis(2000) → HOLD
        reco = RecommendationEngine.generate_recommendation(
            holding=_holding(),
            insight=_insight(trend_type=TrendType.BEARISH, current_price=2500.0),
            cost_basis=2000.0,
            current_price=2500.0,
        )
        assert reco.action == ActionType.HOLD

    def test_bullish_with_none_resistance_yields_hold(self):
        # BULLISH but resistance_level is None → cannot compare → HOLD
        reco = RecommendationEngine.generate_recommendation(
            holding=_holding(),
            insight=_insight(trend_type=TrendType.BULLISH, current_price=2500.0, resistance_level=None),
            cost_basis=2000.0,
            current_price=2500.0,
        )
        assert reco.action == ActionType.HOLD


# ---------------------------------------------------------------------------
# generate_recommendation — output structure
# ---------------------------------------------------------------------------

class TestGenerateRecommendationStructure:

    def test_returns_recommendation_instance(self):
        reco = RecommendationEngine.generate_recommendation(
            holding=_holding(),
            insight=_insight(),
            cost_basis=2000.0,
            current_price=2500.0,
        )
        assert isinstance(reco, Recommendation)

    def test_symbol_matches_holding_symbol(self):
        reco = RecommendationEngine.generate_recommendation(
            holding=_holding(symbol="TCS.NS"),
            insight=_insight(symbol="TCS.NS"),
            cost_basis=3000.0,
            current_price=3500.0,
        )
        assert reco.symbol == "TCS.NS"

    def test_compliance_disclaimer_always_present(self):
        for trend in TrendType:
            reco = RecommendationEngine.generate_recommendation(
                holding=_holding(),
                insight=_insight(trend_type=trend),
                cost_basis=2000.0,
                current_price=2500.0,
            )
            assert reco.compliance_disclaimer == COMPLIANCE_DISCLAIMER, (
                f"Disclaimer missing for trend {trend}"
            )

    def test_compliance_disclaimer_exact_value(self):
        reco = RecommendationEngine.generate_recommendation(
            holding=_holding(),
            insight=_insight(trend_type=TrendType.BULLISH, current_price=2500.0, resistance_level=3000.0),
            cost_basis=2000.0,
            current_price=2500.0,
        )
        assert reco.compliance_disclaimer == (
            "Insights only, not financial advice. Educational purpose only."
        )

    def test_rationale_is_non_empty_string_for_buy(self):
        reco = RecommendationEngine.generate_recommendation(
            holding=_holding(),
            insight=_insight(trend_type=TrendType.BULLISH, current_price=2500.0, resistance_level=3000.0),
            cost_basis=2000.0,
            current_price=2500.0,
        )
        assert isinstance(reco.rationale, str) and len(reco.rationale) > 0

    def test_rationale_is_non_empty_string_for_sell(self):
        reco = RecommendationEngine.generate_recommendation(
            holding=_holding(),
            insight=_insight(trend_type=TrendType.BEARISH, current_price=1500.0),
            cost_basis=2000.0,
            current_price=1500.0,
        )
        assert isinstance(reco.rationale, str) and len(reco.rationale) > 0

    def test_rationale_is_non_empty_string_for_hold(self):
        reco = RecommendationEngine.generate_recommendation(
            holding=_holding(),
            insight=_insight(trend_type=TrendType.NEUTRAL),
            cost_basis=2000.0,
            current_price=2500.0,
        )
        assert isinstance(reco.rationale, str) and len(reco.rationale) > 0

    def test_quantity_preserved_from_holding(self):
        reco = RecommendationEngine.generate_recommendation(
            holding=_holding(quantity=25),
            insight=_insight(trend_type=TrendType.NEUTRAL),
            cost_basis=2000.0,
            current_price=2500.0,
        )
        assert reco.quantity == 25
