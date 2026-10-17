"""
Recommendation Engine for the Market Analysis MVP.

Responsibilities:
  - Compare user holdings against company insights
  - Generate personalized buy/hold/sell recommendations
  - Compute suggested quantities, buy/sell ranges, and target prices
  - Aggregate recommendations into an ActionPlan with compliance disclaimer

Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 8.1, 8.2, 8.3, 12.1, 12.2
"""

from __future__ import annotations

import logging
import math
from typing import Optional

from src.models import (
    ActionPlan,
    ActionType,
    Comparison,
    COMPLIANCE_DISCLAIMER,
    Holding,
    Insight,
    Recommendation,
    TrendType,
)

logger = logging.getLogger(__name__)


class RecommendationEngine:
    """Generates personalized recommendations and action plans for user holdings.

    All core logic is implemented as pure static methods for easy isolation
    and property-based testing.
    """

    # ------------------------------------------------------------------
    # Comparison (pure static method)
    # ------------------------------------------------------------------

    @staticmethod
    def compare_holding_to_insight(
        holding: Holding,
        insight: Insight,
        cost_basis: float,
    ) -> Comparison:
        """Compare a single holding against its company insight.

        Determines whether the holding is currently in profit by comparing
        the insight's current market price against the cost basis.

        Args:
            holding:    The user's position in the stock.
            insight:    The latest company-level analysis for that stock.
            cost_basis: The weighted-average buy price across all holdings
                        for this company (may equal holding.buy_price when
                        there is only one holding).

        Returns:
            A :class:`~src.models.Comparison` with ``is_profit=True``
            when ``insight.current_price > cost_basis``.
        """
        is_profit = insight.current_price > cost_basis

        return Comparison(
            holding=holding,
            insight=insight,
            cost_basis=cost_basis,
            is_profit=is_profit,
        )

    # ------------------------------------------------------------------
    # Recommendation generation (pure static method)
    # ------------------------------------------------------------------

    @staticmethod
    def generate_recommendation(
        holding: Holding,
        insight: Insight,
        cost_basis: float,
        current_price: float,
    ) -> Recommendation:
        """Generate a personalized buy/hold/sell recommendation for a holding.

        Decision rules (evaluated in priority order):

        1. **BUY** — trend is ``BULLISH`` *and* ``current_price`` is strictly
           below the resistance level (room to grow).
        2. **SELL** — trend is ``BEARISH`` *and* ``current_price`` is strictly
           below the ``cost_basis`` (holding is at a loss).
        3. **HOLD** — trend is ``NEUTRAL`` *or* neither rule above matches.

        The ``compliance_disclaimer`` field is always set to
        ``COMPLIANCE_DISCLAIMER`` (Requirement 12.1).

        Args:
            holding:       The user's position in the stock.
            insight:       The latest company-level analysis for that stock.
            cost_basis:    Weighted-average purchase price for the symbol.
            current_price: Latest market price used for rule evaluation.

        Returns:
            A :class:`~src.models.Recommendation` with an ``ActionType``
            and a human-readable ``rationale``.
        """
        trend_type: TrendType = insight.trend.trend_type
        resistance_level: Optional[float] = insight.trend.resistance_level

        action: ActionType
        rationale: str

        if (
            trend_type == TrendType.BULLISH
            and resistance_level is not None
            and current_price < resistance_level
        ):
            action = ActionType.BUY
            rationale = (
                f"{holding.symbol} shows a BULLISH trend. "
                f"Current price {current_price:.2f} is below resistance "
                f"{resistance_level:.2f}, indicating upside potential."
            )
        elif trend_type == TrendType.BEARISH and current_price < cost_basis:
            action = ActionType.SELL
            rationale = (
                f"{holding.symbol} shows a BEARISH trend. "
                f"Current price {current_price:.2f} is below cost basis "
                f"{cost_basis:.2f}, indicating a loss position."
            )
        else:
            action = ActionType.HOLD
            if trend_type == TrendType.NEUTRAL:
                rationale = (
                    f"{holding.symbol} shows a NEUTRAL trend. "
                    "No clear directional signal — holding current position."
                )
            elif trend_type == TrendType.BULLISH:
                # BULLISH but current_price >= resistance (or resistance is None): hold
                resistance_str = f"{resistance_level:.2f}" if resistance_level is not None else "N/A"
                rationale = (
                    f"{holding.symbol} shows a BULLISH trend but current price "
                    f"{current_price:.2f} is at or above resistance level "
                    f"{resistance_str}. Holding current position."
                )
            else:
                # BEARISH but current_price >= cost_basis: bearish yet not at a loss
                rationale = (
                    f"{holding.symbol} shows a BEARISH trend but current price "
                    f"{current_price:.2f} is at or above cost basis "
                    f"{cost_basis:.2f}. Holding current position."
                )

        return Recommendation(
            symbol=holding.symbol,
            action=action,
            quantity=holding.quantity,
            rationale=rationale,
            compliance_disclaimer=COMPLIANCE_DISCLAIMER,
        )

    # ------------------------------------------------------------------
    # Quantity and range helpers (pure static methods) — task 7.2
    # ------------------------------------------------------------------

    @staticmethod
    def compute_suggested_quantity(
        action: ActionType,
        daily_investment: float,
        current_price: float,
        holding_qty: int,
    ) -> int:
        """Compute the suggested trade quantity for a recommendation.

        Rules:
          - BUY  → ``floor(daily_investment / current_price)``
          - SELL → ``holding_qty``
          - HOLD → ``0``

        The result is always a non-negative integer.

        Args:
            action:            The recommended :class:`ActionType`.
            daily_investment:  The user's configured daily investment budget.
            current_price:     Latest market price.
            holding_qty:       Number of shares currently held.

        Returns:
            Non-negative suggested quantity.
        """
        if action == ActionType.BUY:
            if current_price <= 0:
                return 0
            return max(0, math.floor(daily_investment / current_price))
        elif action == ActionType.SELL:
            return max(0, holding_qty)
        else:  # HOLD
            return 0

    @staticmethod
    def compute_buy_range(
        support_level: float,
        current_price: float,
    ) -> tuple[float, float]:
        """Compute the suggested buy range as (support_level, current_price).

        The invariant ``low <= high`` is guaranteed by taking the min/max of
        the two inputs.

        Args:
            support_level: 52-week support (lowest) price.
            current_price: Current market price.

        Returns:
            Tuple ``(low, high)`` where ``low <= high``.
        """
        low = min(support_level, current_price)
        high = max(support_level, current_price)
        return (low, high)

    @staticmethod
    def compute_sell_range(
        current_price: float,
        resistance_level: float,
    ) -> tuple[float, float]:
        """Compute the suggested sell range as (current_price, resistance_level).

        The invariant ``low <= high`` is guaranteed by taking the min/max of
        the two inputs.

        Args:
            current_price:    Current market price.
            resistance_level: 52-week resistance (highest) price.

        Returns:
            Tuple ``(low, high)`` where ``low <= high``.
        """
        low = min(current_price, resistance_level)
        high = max(current_price, resistance_level)
        return (low, high)

    @staticmethod
    def compute_target_price(
        support_level: float,
        resistance_level: float,
    ) -> float:
        """Compute the target price as the midpoint of support and resistance.

        target = (support_level + resistance_level) / 2

        Args:
            support_level:    52-week support price.
            resistance_level: 52-week resistance price.

        Returns:
            Midpoint price as a float.
        """
        return (support_level + resistance_level) / 2

    # ------------------------------------------------------------------
    # Action plan generation — task 7.4
    # ------------------------------------------------------------------

    def generate_action_plan(
        self,
        recommendations: list[Recommendation],
        insights: dict[str, Insight],
    ) -> ActionPlan:
        """Aggregate recommendations into a full ActionPlan.

        For each recommendation whose symbol has a corresponding insight with
        non-None support and resistance levels, buy/sell ranges and a target
        price are computed.  Rebalancing suggestions are derived from the
        aggregate of all recommendation actions.

        The ``compliance_disclaimer`` is always set to
        ``COMPLIANCE_DISCLAIMER`` (Requirement 12.2).

        Args:
            recommendations: List of individual :class:`Recommendation` objects.
            insights:        Mapping of symbol → :class:`Insight`.

        Returns:
            An :class:`~src.models.ActionPlan` with ranges, targets,
            rebalancing suggestions, and the compliance disclaimer.
        """
        buy_ranges: dict[str, tuple[float, float]] = {}
        sell_ranges: dict[str, tuple[float, float]] = {}
        target_prices: dict[str, float] = {}

        buy_symbols: list[str] = []
        sell_symbols: list[str] = []
        hold_symbols: list[str] = []

        for reco in recommendations:
            symbol = reco.symbol
            insight = insights.get(symbol)

            if insight is not None:
                support = insight.trend.support_level
                resistance = insight.trend.resistance_level
                current_price = insight.current_price

                if support is not None and resistance is not None:
                    buy_ranges[symbol] = self.compute_buy_range(support, current_price)
                    sell_ranges[symbol] = self.compute_sell_range(current_price, resistance)
                    target_prices[symbol] = self.compute_target_price(support, resistance)

            if reco.action == ActionType.BUY:
                buy_symbols.append(symbol)
            elif reco.action == ActionType.SELL:
                sell_symbols.append(symbol)
            else:
                hold_symbols.append(symbol)

        # Build rebalancing suggestions from aggregate action distribution
        rebalancing_suggestions: list[str] = []
        if buy_symbols:
            rebalancing_suggestions.append(
                f"Consider increasing positions in: {', '.join(buy_symbols)}."
            )
        if sell_symbols:
            rebalancing_suggestions.append(
                f"Consider reducing or exiting positions in: {', '.join(sell_symbols)}."
            )
        if hold_symbols:
            rebalancing_suggestions.append(
                f"Maintain current positions in: {', '.join(hold_symbols)}."
            )
        if not rebalancing_suggestions:
            rebalancing_suggestions.append("No rebalancing actions required at this time.")

        return ActionPlan(
            recommendations=recommendations,
            buy_ranges=buy_ranges,
            sell_ranges=sell_ranges,
            target_prices=target_prices,
            rebalancing_suggestions=rebalancing_suggestions,
            compliance_disclaimer=COMPLIANCE_DISCLAIMER,
        )
