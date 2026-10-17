"""
Core data models for the Market Analysis MVP.

Contains enumerations, dataclasses for domain objects, and JSON
serialization helpers for NormalizedRecord.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Compliance disclaimer constant
# ---------------------------------------------------------------------------

COMPLIANCE_DISCLAIMER = "Insights only, not financial advice. Educational purpose only."


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class TrendType(Enum):
    """Direction classification for a company's price trend."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class ActionType(Enum):
    """Recommended trading action for a holding."""

    BUY = "buy"
    HOLD = "hold"
    SELL = "sell"


# ---------------------------------------------------------------------------
# Core Data Structures
# ---------------------------------------------------------------------------


@dataclass
class NormalizedRecord:
    """Standard normalized market data record produced by the Fetcher.

    Constraints:
        symbol    — non-empty string
        price     — strictly positive float
        timestamp — timezone-aware or naive UTC datetime
    """

    symbol: str
    price: float
    timestamp: datetime

    # ------------------------------------------------------------------
    # Serialization / deserialization
    # ------------------------------------------------------------------

    def serialize(self) -> str:
        """Serialize this record to a JSON string.

        The datetime is encoded as an ISO 8601 string so that the full
        precision (including timezone offset) is preserved across a round-
        trip through JSON.

        Returns:
            A JSON-encoded string representing this NormalizedRecord.
        """
        payload = {
            "symbol": self.symbol,
            "price": self.price,
            "timestamp": self.timestamp.isoformat(),
        }
        return json.dumps(payload)

    @classmethod
    def deserialize(cls, json_str: str) -> "NormalizedRecord":
        """Reconstruct a NormalizedRecord from a JSON string.

        Args:
            json_str: A string previously produced by :meth:`serialize`.

        Returns:
            A NormalizedRecord with symbol, price, and timestamp restored.

        Raises:
            ValueError: If the JSON is missing required fields or the
                        timestamp cannot be parsed.
            json.JSONDecodeError: If *json_str* is not valid JSON.
        """
        data = json.loads(json_str)

        missing = {"symbol", "price", "timestamp"} - data.keys()
        if missing:
            raise ValueError(f"Missing required fields in JSON: {missing}")

        timestamp = datetime.fromisoformat(data["timestamp"])

        return cls(
            symbol=data["symbol"],
            price=float(data["price"]),
            timestamp=timestamp,
        )


@dataclass
class CompanyFinancials:
    """Raw financial inputs used for metric computation.

    Attributes:
        eps_history: Trailing 4+ quarters of EPS values, oldest first.
        non_performing_assets: Banks only; None for non-bank companies.
        total_assets: Banks only; None for non-bank companies.
    """

    symbol: str
    earnings_per_share: float
    book_value_per_share: float
    net_income: float
    shareholder_equity: float
    eps_history: list[float]
    is_bank: bool
    non_performing_assets: Optional[float] = None
    total_assets: Optional[float] = None


@dataclass
class CompanyMetrics:
    """Computed financial metrics for a single NIFTY 500 company.

    Attributes:
        npa: Non-Performing Assets as a percentage of total assets.
             Banks only; None for non-bank companies.
    """

    symbol: str
    pe_ratio: Optional[float]
    pb_ratio: Optional[float]
    roe: Optional[float]
    eps_growth: Optional[float]
    npa: Optional[float]


@dataclass
class Trend:
    """Trend classification for a company.

    Attributes:
        support_level:    None when the price history is empty.
        resistance_level: None when the price history is empty.
    """

    symbol: str
    trend_type: TrendType
    support_level: Optional[float]
    resistance_level: Optional[float]


@dataclass
class Insight:
    """Company-level analysis summary combining metrics and trend."""

    symbol: str
    metrics: CompanyMetrics
    trend: Trend
    current_price: float
    summary: str


@dataclass
class Holding:
    """A single user position in a stock.

    Attributes:
        id:         UUID string uniquely identifying this holding.
        quantity:   Must be > 0.
        buy_price:  Must be > 0.
    """

    id: str
    user_id: str
    symbol: str
    quantity: int
    buy_price: float
    created_at: datetime


@dataclass
class Comparison:
    """Result of comparing a Holding against its company Insight.

    Attributes:
        is_profit: True when the current market price exceeds the cost basis.
    """

    holding: Holding
    insight: Insight
    cost_basis: float
    is_profit: bool


@dataclass
class Recommendation:
    """Personalized action recommendation for a single holding.

    Attributes:
        quantity:              Non-negative suggested trade quantity.
        compliance_disclaimer: Always set to COMPLIANCE_DISCLAIMER.
    """

    symbol: str
    action: ActionType
    quantity: int
    rationale: str
    compliance_disclaimer: str = field(default=COMPLIANCE_DISCLAIMER)


@dataclass
class ActionPlan:
    """Aggregated actionable summary across all user holdings.

    Attributes:
        buy_ranges:              symbol → (low, high) with low ≤ high.
        sell_ranges:             symbol → (low, high) with low ≤ high.
        target_prices:           symbol → midpoint between support and resistance.
        rebalancing_suggestions: Human-readable rebalancing actions.
        compliance_disclaimer:   Always set to COMPLIANCE_DISCLAIMER.
    """

    recommendations: list[Recommendation]
    buy_ranges: dict[str, tuple[float, float]]
    sell_ranges: dict[str, tuple[float, float]]
    target_prices: dict[str, float]
    rebalancing_suggestions: list[str]
    compliance_disclaimer: str = field(default=COMPLIANCE_DISCLAIMER)
