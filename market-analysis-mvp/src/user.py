"""
Holdings Manager for the Market Analysis MVP.

Provides CRUD operations for user stock holdings, cost basis computation,
and daily investment configuration.  All database interactions are performed
through the SQLAlchemy ``Session`` passed to the constructor, making the
class straightforward to test with an in-memory database.

Requirements: 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 6.3
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from src.database.models import HoldingModel, UserSettingsModel
from src.models import Holding


class HoldingsManager:
    """Manages user stock holdings and related settings.

    All write operations are immediately flushed to the session; callers are
    responsible for committing (or rolling back) the surrounding transaction.

    Args:
        session: An active SQLAlchemy :class:`Session` bound to the target
                 database.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Holdings CRUD
    # ------------------------------------------------------------------

    def add_holding(
        self,
        user_id: str,
        symbol: str,
        quantity: int,
        buy_price: float,
    ) -> Holding:
        """Validate inputs and persist a new Holding to the database.

        A user may hold the same symbol at multiple buy prices; each call
        creates a separate row.  (Requirements 5.1, 5.2)

        Args:
            user_id:   Identifier for the user who owns this holding.
            symbol:    Non-empty ticker symbol (e.g. ``"RELIANCE.NS"``).
            quantity:  Number of shares held — must be a positive integer.
            buy_price: Price per share at which the shares were purchased —
                       must be a strictly positive float.

        Returns:
            A :class:`~src.models.Holding` dataclass representing the newly
            created record.

        Raises:
            ValueError: If ``symbol`` is empty or missing, ``quantity`` is ≤ 0,
                        or ``buy_price`` is ≤ 0.
        """
        # --- Input validation ---
        if not symbol or not symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        if quantity <= 0:
            raise ValueError(f"quantity must be > 0, got {quantity!r}")
        if buy_price <= 0:
            raise ValueError(f"buy_price must be > 0, got {buy_price!r}")

        holding_id = str(uuid.uuid4())
        created_at = datetime.utcnow()

        model = HoldingModel(
            id=holding_id,
            user_id=user_id,
            symbol=symbol.strip(),
            quantity=quantity,
            buy_price=buy_price,
            created_at=created_at,
        )
        self._session.add(model)
        self._session.flush()

        return Holding(
            id=holding_id,
            user_id=user_id,
            symbol=symbol.strip(),
            quantity=quantity,
            buy_price=buy_price,
            created_at=created_at,
        )

    def get_holdings(
        self,
        user_id: str,
        symbol: Optional[str] = None,
    ) -> list[Holding]:
        """Retrieve all holdings for a user, optionally filtered by symbol.

        (Requirements 5.4)

        Args:
            user_id: Identifier of the user whose holdings are requested.
            symbol:  Optional ticker symbol to filter by.  When ``None``, all
                     holdings for ``user_id`` are returned.

        Returns:
            A list of :class:`~src.models.Holding` dataclasses.  Returns an
            empty list if no holdings exist for the given user (and symbol).
        """
        query = self._session.query(HoldingModel).filter(
            HoldingModel.user_id == user_id
        )
        if symbol is not None:
            query = query.filter(HoldingModel.symbol == symbol)

        rows = query.all()
        return [
            Holding(
                id=row.id,
                user_id=row.user_id,
                symbol=row.symbol,
                quantity=row.quantity,
                buy_price=row.buy_price,
                created_at=row.created_at,
            )
            for row in rows
        ]

    def set_daily_investment(self, user_id: str, amount: float) -> None:
        """Persist the daily investment amount for a user.

        Creates the ``UserSettingsModel`` row if it does not yet exist, or
        updates the existing row in-place.  (Requirement 5.3)

        Args:
            user_id: Identifier of the user whose setting is being updated.
            amount:  Daily investment amount in local currency — must be > 0.

        Raises:
            ValueError: If ``amount`` is ≤ 0.
        """
        if amount <= 0:
            raise ValueError(f"amount must be > 0, got {amount!r}")

        existing = self._session.get(UserSettingsModel, user_id)
        if existing is None:
            self._session.add(
                UserSettingsModel(user_id=user_id, daily_investment=amount)
            )
        else:
            existing.daily_investment = amount
        self._session.flush()

    # ------------------------------------------------------------------
    # Cost basis and quantity (pure static methods)
    # ------------------------------------------------------------------

    @staticmethod
    def compute_cost_basis(holdings: list[Holding]) -> float:
        """Compute the weighted-average buy price across all holdings.

        cost_basis = sum(h.quantity * h.buy_price) / sum(h.quantity)

        (Requirement 6.1)

        Args:
            holdings: Non-empty list of :class:`~src.models.Holding` objects
                      for a single company.

        Returns:
            The weighted-average buy price as a ``float``.

        Raises:
            ValueError: If ``holdings`` is empty.
        """
        if not holdings:
            raise ValueError("holdings list must not be empty")
        total_cost = sum(h.quantity * h.buy_price for h in holdings)
        total_qty = sum(h.quantity for h in holdings)
        return total_cost / total_qty

    @staticmethod
    def compute_total_quantity(holdings: list[Holding]) -> int:
        """Compute the sum of all holding quantities.

        (Requirements 6.2, 6.3)

        Args:
            holdings: List of :class:`~src.models.Holding` objects (may be
                      empty).

        Returns:
            Total quantity as an ``int``.  Returns ``0`` for an empty list.
        """
        return sum(h.quantity for h in holdings)
