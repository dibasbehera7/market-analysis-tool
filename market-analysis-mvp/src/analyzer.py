"""
Analyzer module for the Market Analysis MVP.

Responsibilities:
  - Compute financial metrics (P/E, P/B, ROE, EPS growth, NPA)
  - Detect market trends using 50/200 SMA crossover
  - Compute support and resistance levels
  - Generate company-level Insights combining metrics and trend
"""

from __future__ import annotations

import logging
from typing import Optional

from src.models import (
    CompanyFinancials,
    CompanyMetrics,
    Insight,
    Trend,
    TrendType,
)

logger = logging.getLogger(__name__)


class Analyzer:
    """Analysis engine for NIFTY 500 companies.

    All metric and trend functions are implemented as pure static methods
    with no side effects, making them deterministic for a given input and
    straightforward to property-test in isolation.
    """

    # ------------------------------------------------------------------
    # Metric Computation (pure functions)
    # ------------------------------------------------------------------

    @staticmethod
    def compute_pe_ratio(price: float, earnings_per_share: float) -> Optional[float]:
        """Compute the Price-to-Earnings ratio.

        P/E = price / earnings_per_share

        Args:
            price: Current market price (must be positive in practice).
            earnings_per_share: EPS value for the company.

        Returns:
            The P/E ratio as a float, or ``None`` if ``earnings_per_share``
            is zero or negative (avoids division by zero / meaningless result).
        """
        if earnings_per_share <= 0:
            return None
        return price / earnings_per_share

    @staticmethod
    def compute_pb_ratio(price: float, book_value_per_share: float) -> Optional[float]:
        """Compute the Price-to-Book ratio.

        P/B = price / book_value_per_share

        Args:
            price: Current market price.
            book_value_per_share: Book value per share for the company.

        Returns:
            The P/B ratio as a float, or ``None`` if ``book_value_per_share``
            is zero or negative.
        """
        if book_value_per_share <= 0:
            return None
        return price / book_value_per_share

    @staticmethod
    def compute_roe(net_income: float, shareholder_equity: float) -> Optional[float]:
        """Compute the Return on Equity.

        ROE = net_income / shareholder_equity

        Args:
            net_income: Net income for the period.
            shareholder_equity: Total shareholder equity.

        Returns:
            The ROE as a float, or ``None`` if ``shareholder_equity`` is
            zero or negative.
        """
        if shareholder_equity <= 0:
            return None
        return net_income / shareholder_equity

    @staticmethod
    def compute_eps_growth(eps_history: list[float]) -> Optional[float]:
        """Compute the EPS growth rate over trailing 4+ quarters.

        EPS growth = (last - first) / abs(first) * 100

        where ``first`` and ``last`` are the first and last elements of
        ``eps_history`` respectively.

        Args:
            eps_history: Ordered list of EPS values (oldest first).
                         Must contain at least 4 elements.

        Returns:
            Percentage change as a float, or ``None`` when:
              * the list has fewer than 4 elements, or
              * the first element is zero (avoids division by zero).
        """
        if len(eps_history) < 4:
            return None
        first = eps_history[0]
        if first == 0:
            return None
        last = eps_history[-1]
        return (last - first) / abs(first) * 100

    @staticmethod
    def compute_npa(
        non_performing_assets: float, total_assets: float
    ) -> Optional[float]:
        """Compute Non-Performing Assets as a percentage of total assets.

        NPA % = (non_performing_assets / total_assets) * 100

        This metric is only meaningful for bank-classified companies; callers
        are responsible for ensuring it is only invoked for banks.

        Args:
            non_performing_assets: Value of non-performing assets.
            total_assets: Total assets held by the bank.

        Returns:
            NPA percentage as a float, or ``None`` if ``total_assets`` is
            zero or negative.
        """
        if total_assets <= 0:
            return None
        return (non_performing_assets / total_assets) * 100

    # ------------------------------------------------------------------
    # Trend Detection (pure functions) — stubs for task 4.5
    # ------------------------------------------------------------------

    @staticmethod
    def detect_trend(prices: list[float]) -> TrendType:
        """Classify the price trend using a 50/200 SMA crossover.

        Rules:
          - If ``prices`` has fewer than 200 elements, the long-period SMA
            cannot be computed → NEUTRAL.
          - short_ma = mean(prices[-50:]), long_ma = mean(prices[-200:])
          - short_ma > long_ma → BULLISH
          - short_ma < long_ma → BEARISH
          - short_ma == long_ma → NEUTRAL

        Args:
            prices: Chronological list of closing prices (oldest first).

        Returns:
            A :class:`TrendType` value.
        """
        if len(prices) < 200:
            return TrendType.NEUTRAL

        short_ma = sum(prices[-50:]) / 50
        long_ma = sum(prices[-200:]) / 200

        if short_ma > long_ma:
            return TrendType.BULLISH
        elif short_ma < long_ma:
            return TrendType.BEARISH
        else:
            return TrendType.NEUTRAL

    @staticmethod
    def compute_support_level(
        prices: list[float], period: int = 252
    ) -> Optional[float]:
        """Compute the support level as the trailing-period minimum.

        Args:
            prices: Chronological list of closing prices.
            period: Trailing window size (default 252 trading days ≈ 1 year).

        Returns:
            Minimum price over ``prices[-period:]``, or ``None`` for an
            empty list.
        """
        if not prices:
            return None
        return min(prices[-period:])

    @staticmethod
    def compute_resistance_level(
        prices: list[float], period: int = 252
    ) -> Optional[float]:
        """Compute the resistance level as the trailing-period maximum.

        Args:
            prices: Chronological list of closing prices.
            period: Trailing window size (default 252 trading days ≈ 1 year).

        Returns:
            Maximum price over ``prices[-period:]``, or ``None`` for an
            empty list.
        """
        if not prices:
            return None
        return max(prices[-period:])

    # ------------------------------------------------------------------
    # Insight Generation — stub for task 4.8
    # ------------------------------------------------------------------

    def generate_insight(
        self,
        symbol: str,
        metrics: CompanyMetrics,
        trend: Trend,
        current_price: float,
    ) -> Insight:
        """Combine metrics and trend into a company-level Insight.

        Builds a human-readable ``summary`` from the trend type and key
        metrics (P/E, P/B, ROE), then assembles and returns an
        :class:`Insight`.

        Args:
            symbol:        Company ticker symbol.
            metrics:       Computed :class:`CompanyMetrics`.
            trend:         Detected :class:`Trend`.
            current_price: Latest market price for the company.

        Returns:
            An :class:`Insight` summarising the company's analysis.
        """
        # Build human-readable summary parts
        parts: list[str] = [f"{trend.trend_type.value.upper()} trend"]

        if metrics.pe_ratio is not None:
            parts.append(f"P/E: {metrics.pe_ratio:.2f}")
        if metrics.pb_ratio is not None:
            parts.append(f"P/B: {metrics.pb_ratio:.2f}")
        if metrics.roe is not None:
            parts.append(f"ROE: {metrics.roe:.2f}")
        if metrics.eps_growth is not None:
            parts.append(f"EPS growth: {metrics.eps_growth:.2f}%")
        if metrics.npa is not None:
            parts.append(f"NPA: {metrics.npa:.2f}%")

        summary = "; ".join(parts)

        return Insight(
            symbol=symbol,
            metrics=metrics,
            trend=trend,
            current_price=current_price,
            summary=summary,
        )

    def analyze(
        self,
        symbol: str,
        financials: CompanyFinancials,
        prices: list[float],
        current_price: float,
    ) -> Insight:
        """Run the full Analyzer pipeline for a single company.

        Executes sequentially:
          1. Compute all financial metrics from *financials*.
          2. Detect the price trend from *prices*.
          3. Generate and return an :class:`Insight`.

        Args:
            symbol:        Company ticker symbol.
            financials:    Raw financial data for the company.
            prices:        Chronological closing prices (oldest first).
            current_price: Latest market price.

        Returns:
            A fully populated :class:`Insight` for the company.
        """
        # Step 1: Compute metrics
        npa: Optional[float] = None
        if financials.is_bank and financials.non_performing_assets is not None and financials.total_assets is not None:
            npa = self.compute_npa(financials.non_performing_assets, financials.total_assets)

        metrics = CompanyMetrics(
            symbol=symbol,
            pe_ratio=self.compute_pe_ratio(current_price, financials.earnings_per_share),
            pb_ratio=self.compute_pb_ratio(current_price, financials.book_value_per_share),
            roe=self.compute_roe(financials.net_income, financials.shareholder_equity),
            eps_growth=self.compute_eps_growth(financials.eps_history),
            npa=npa,
        )

        # Step 2: Detect trend
        trend = Trend(
            symbol=symbol,
            trend_type=self.detect_trend(prices),
            support_level=self.compute_support_level(prices),
            resistance_level=self.compute_resistance_level(prices),
        )

        # Step 3: Generate and return insight
        return self.generate_insight(symbol, metrics, trend, current_price)
