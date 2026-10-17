"""
Unit tests for src/user.py — tasks 6.1 and 6.2.

Coverage:
  add_holding()
    - raises ValueError for empty symbol
    - raises ValueError for whitespace-only symbol
    - raises ValueError for quantity == 0
    - raises ValueError for negative quantity
    - raises ValueError for buy_price == 0
    - raises ValueError for negative buy_price
    - persists a valid holding and returns correct Holding dataclass
    - multiple holdings for the same symbol are each stored separately

  get_holdings()
    - returns empty list when no holdings exist
    - returns empty list when symbol filter matches nothing
    - returns all holdings for a user when no symbol filter is given
    - returns only holdings matching the symbol filter
    - does not leak holdings between different users

  set_daily_investment()
    - raises ValueError for amount == 0
    - raises ValueError for negative amount
    - stores the amount for a new user
    - updates the amount for an existing user

  compute_cost_basis()
    - raises ValueError for empty holdings list
    - returns buy_price directly for a single holding
    - computes weighted average correctly for two holdings
    - computes weighted average correctly for three holdings with equal quantities

  compute_total_quantity()
    - returns 0 for an empty list
    - returns quantity for a single holding
    - sums quantities for multiple holdings
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.database.models import Base
from src.models import Holding
from src.user import HoldingsManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def session() -> Session:
    """Provide an in-memory SQLite session with the schema created."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture
def manager(session: Session) -> HoldingsManager:
    """HoldingsManager backed by the in-memory session."""
    return HoldingsManager(session)


def _holding(
    symbol: str = "RELIANCE.NS",
    quantity: int = 10,
    buy_price: float = 2500.0,
    user_id: str = "user-1",
) -> Holding:
    """Build a Holding dataclass directly (not via DB) for pure-function tests."""
    return Holding(
        id=str(uuid.uuid4()),
        user_id=user_id,
        symbol=symbol,
        quantity=quantity,
        buy_price=buy_price,
        created_at=datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# add_holding — validation errors
# ---------------------------------------------------------------------------

class TestAddHoldingValidation:
    def test_raises_for_empty_symbol(self, manager: HoldingsManager) -> None:
        with pytest.raises(ValueError, match="symbol"):
            manager.add_holding("u1", "", 5, 100.0)

    def test_raises_for_whitespace_symbol(self, manager: HoldingsManager) -> None:
        with pytest.raises(ValueError, match="symbol"):
            manager.add_holding("u1", "   ", 5, 100.0)

    def test_raises_for_zero_quantity(self, manager: HoldingsManager) -> None:
        with pytest.raises(ValueError, match="quantity"):
            manager.add_holding("u1", "TCS.NS", 0, 100.0)

    def test_raises_for_negative_quantity(self, manager: HoldingsManager) -> None:
        with pytest.raises(ValueError, match="quantity"):
            manager.add_holding("u1", "TCS.NS", -3, 100.0)

    def test_raises_for_zero_buy_price(self, manager: HoldingsManager) -> None:
        with pytest.raises(ValueError, match="buy_price"):
            manager.add_holding("u1", "TCS.NS", 5, 0.0)

    def test_raises_for_negative_buy_price(self, manager: HoldingsManager) -> None:
        with pytest.raises(ValueError, match="buy_price"):
            manager.add_holding("u1", "TCS.NS", 5, -50.0)


# ---------------------------------------------------------------------------
# add_holding — successful persistence
# ---------------------------------------------------------------------------

class TestAddHoldingSuccess:
    def test_returns_holding_instance(self, manager: HoldingsManager) -> None:
        result = manager.add_holding("u1", "RELIANCE.NS", 10, 2500.0)
        assert isinstance(result, Holding)

    def test_returned_holding_has_correct_fields(self, manager: HoldingsManager) -> None:
        result = manager.add_holding("u1", "RELIANCE.NS", 10, 2500.0)
        assert result.user_id == "u1"
        assert result.symbol == "RELIANCE.NS"
        assert result.quantity == 10
        assert result.buy_price == 2500.0

    def test_returned_holding_has_non_empty_id(self, manager: HoldingsManager) -> None:
        result = manager.add_holding("u1", "RELIANCE.NS", 10, 2500.0)
        assert result.id != ""

    def test_returned_holding_has_created_at(self, manager: HoldingsManager) -> None:
        result = manager.add_holding("u1", "RELIANCE.NS", 10, 2500.0)
        assert isinstance(result.created_at, datetime)

    def test_symbol_is_stripped(self, manager: HoldingsManager) -> None:
        result = manager.add_holding("u1", "  INFY.NS  ", 5, 1500.0)
        assert result.symbol == "INFY.NS"

    def test_multiple_holdings_same_symbol_stored_separately(
        self, manager: HoldingsManager
    ) -> None:
        h1 = manager.add_holding("u1", "RELIANCE.NS", 5, 2400.0)
        h2 = manager.add_holding("u1", "RELIANCE.NS", 10, 2600.0)
        assert h1.id != h2.id
        holdings = manager.get_holdings("u1", "RELIANCE.NS")
        assert len(holdings) == 2


# ---------------------------------------------------------------------------
# get_holdings — retrieval and filtering
# ---------------------------------------------------------------------------

class TestGetHoldings:
    def test_returns_empty_list_when_no_holdings_exist(
        self, manager: HoldingsManager
    ) -> None:
        assert manager.get_holdings("u1") == []

    def test_returns_empty_list_when_symbol_filter_matches_nothing(
        self, manager: HoldingsManager
    ) -> None:
        manager.add_holding("u1", "RELIANCE.NS", 10, 2500.0)
        assert manager.get_holdings("u1", "TCS.NS") == []

    def test_returns_all_holdings_when_no_symbol_filter(
        self, manager: HoldingsManager
    ) -> None:
        manager.add_holding("u1", "RELIANCE.NS", 10, 2500.0)
        manager.add_holding("u1", "TCS.NS", 5, 3500.0)
        holdings = manager.get_holdings("u1")
        assert len(holdings) == 2

    def test_returns_only_matching_symbol(self, manager: HoldingsManager) -> None:
        manager.add_holding("u1", "RELIANCE.NS", 10, 2500.0)
        manager.add_holding("u1", "TCS.NS", 5, 3500.0)
        holdings = manager.get_holdings("u1", "RELIANCE.NS")
        assert len(holdings) == 1
        assert holdings[0].symbol == "RELIANCE.NS"

    def test_does_not_return_other_users_holdings(
        self, manager: HoldingsManager
    ) -> None:
        manager.add_holding("u1", "RELIANCE.NS", 10, 2500.0)
        assert manager.get_holdings("u2", "RELIANCE.NS") == []

    def test_returned_holding_fields_match_stored_values(
        self, manager: HoldingsManager
    ) -> None:
        manager.add_holding("u1", "INFY.NS", 20, 1800.0)
        holdings = manager.get_holdings("u1", "INFY.NS")
        assert holdings[0].symbol == "INFY.NS"
        assert holdings[0].quantity == 20
        assert holdings[0].buy_price == 1800.0
        assert holdings[0].user_id == "u1"


# ---------------------------------------------------------------------------
# set_daily_investment
# ---------------------------------------------------------------------------

class TestSetDailyInvestment:
    def test_raises_for_zero_amount(self, manager: HoldingsManager) -> None:
        with pytest.raises(ValueError, match="amount"):
            manager.set_daily_investment("u1", 0.0)

    def test_raises_for_negative_amount(self, manager: HoldingsManager) -> None:
        with pytest.raises(ValueError, match="amount"):
            manager.set_daily_investment("u1", -500.0)

    def test_stores_amount_for_new_user(
        self, manager: HoldingsManager, session: Session
    ) -> None:
        from src.database.models import UserSettingsModel

        manager.set_daily_investment("u1", 5000.0)
        row = session.get(UserSettingsModel, "u1")
        assert row is not None
        assert row.daily_investment == 5000.0

    def test_updates_amount_for_existing_user(
        self, manager: HoldingsManager, session: Session
    ) -> None:
        from src.database.models import UserSettingsModel

        manager.set_daily_investment("u1", 5000.0)
        manager.set_daily_investment("u1", 10000.0)
        row = session.get(UserSettingsModel, "u1")
        assert row is not None
        assert row.daily_investment == 10000.0


# ---------------------------------------------------------------------------
# compute_cost_basis (pure static method — no DB required)
# ---------------------------------------------------------------------------

class TestComputeCostBasis:
    def test_raises_for_empty_list(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            HoldingsManager.compute_cost_basis([])

    def test_single_holding_returns_its_buy_price(self) -> None:
        h = _holding(quantity=10, buy_price=2500.0)
        assert HoldingsManager.compute_cost_basis([h]) == pytest.approx(2500.0)

    def test_two_holdings_weighted_average(self) -> None:
        # 5 shares @ 100, 10 shares @ 200 → (500 + 2000) / 15 = 166.666...
        h1 = _holding(quantity=5, buy_price=100.0)
        h2 = _holding(quantity=10, buy_price=200.0)
        expected = (5 * 100.0 + 10 * 200.0) / (5 + 10)
        assert HoldingsManager.compute_cost_basis([h1, h2]) == pytest.approx(expected)

    def test_equal_quantities_gives_simple_average(self) -> None:
        # 3 holdings, each quantity=10: simple average of prices
        h1 = _holding(quantity=10, buy_price=100.0)
        h2 = _holding(quantity=10, buy_price=200.0)
        h3 = _holding(quantity=10, buy_price=300.0)
        expected = (100.0 + 200.0 + 300.0) / 3
        assert HoldingsManager.compute_cost_basis([h1, h2, h3]) == pytest.approx(expected)

    def test_cost_basis_between_min_and_max_buy_price(self) -> None:
        h1 = _holding(quantity=5, buy_price=1000.0)
        h2 = _holding(quantity=15, buy_price=2000.0)
        cost_basis = HoldingsManager.compute_cost_basis([h1, h2])
        assert 1000.0 <= cost_basis <= 2000.0

    def test_higher_quantity_weights_more(self) -> None:
        # More shares at 2000 than at 1000 → cost basis closer to 2000
        h1 = _holding(quantity=1, buy_price=1000.0)
        h2 = _holding(quantity=99, buy_price=2000.0)
        cost_basis = HoldingsManager.compute_cost_basis([h1, h2])
        assert cost_basis > 1500.0


# ---------------------------------------------------------------------------
# compute_total_quantity (pure static method — no DB required)
# ---------------------------------------------------------------------------

class TestComputeTotalQuantity:
    def test_returns_zero_for_empty_list(self) -> None:
        assert HoldingsManager.compute_total_quantity([]) == 0

    def test_returns_quantity_for_single_holding(self) -> None:
        h = _holding(quantity=7)
        assert HoldingsManager.compute_total_quantity([h]) == 7

    def test_sums_quantities_for_multiple_holdings(self) -> None:
        h1 = _holding(quantity=5)
        h2 = _holding(quantity=10)
        h3 = _holding(quantity=3)
        assert HoldingsManager.compute_total_quantity([h1, h2, h3]) == 18

    def test_total_quantity_equals_sum_of_individuals(self) -> None:
        quantities = [4, 8, 12, 16]
        holdings = [_holding(quantity=q) for q in quantities]
        assert HoldingsManager.compute_total_quantity(holdings) == sum(quantities)
