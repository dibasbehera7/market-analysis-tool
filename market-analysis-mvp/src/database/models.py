"""SQLAlchemy 2.0 ORM models for the Market Analysis MVP.

All models inherit from ``Base`` (a SQLAlchemy ``DeclarativeBase`` subclass).
Column types use the ``Mapped`` / ``mapped_column`` API introduced in
SQLAlchemy 2.0 for full type-safety.

Tables
------
- holdings            – user stock positions (Requirements 10.1)
- analysis_results    – per-company analysis snapshots (Requirements 10.2, 10.3)
- recommendations     – generated buy/hold/sell advice (Requirements 10.2, 10.3)
- user_settings       – per-user configuration (daily investment amount)
"""

from datetime import datetime

from sqlalchemy import DateTime, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models.

    Using ``DeclarativeBase`` (SQLAlchemy 2.0 style) instead of the legacy
    ``declarative_base()`` factory gives us a proper Python class hierarchy
    and plays well with type-checkers and Alembic auto-generation.
    """


# ---------------------------------------------------------------------------
# Holdings
# ---------------------------------------------------------------------------


class HoldingModel(Base):
    """Persisted user stock holding.

    A user may hold the same symbol at different buy prices, so multiple rows
    can share the same ``(user_id, symbol)`` pair.  The composite index on
    ``(user_id, symbol)`` makes queries that filter by both columns fast.
    """

    __tablename__ = "holdings"

    # Primary key — UUID stored as a string.
    id: Mapped[str] = mapped_column(primary_key=True)

    # Individual indexes support queries that filter by only one dimension.
    user_id: Mapped[str] = mapped_column(index=True)
    symbol: Mapped[str] = mapped_column(index=True)

    quantity: Mapped[int]
    buy_price: Mapped[float]
    created_at: Mapped[datetime] = mapped_column(DateTime)

    # Composite index: most holding lookups filter on both user_id and symbol.
    __table_args__ = (
        Index("ix_holdings_user_id_symbol", "user_id", "symbol"),
    )


# ---------------------------------------------------------------------------
# Analysis results
# ---------------------------------------------------------------------------


class AnalysisResultModel(Base):
    """Snapshot of a single company's analysis output for one scheduled run.

    ``metrics_json`` and ``trend_json`` store JSON-serialised ``CompanyMetrics``
    and ``Trend`` dataclasses so the schema stays stable even as the Python
    dataclasses evolve.
    """

    __tablename__ = "analysis_results"

    # Primary key — UUID stored as a string.
    id: Mapped[str] = mapped_column(primary_key=True)

    # Index on symbol supports fast lookups for a single company.
    symbol: Mapped[str] = mapped_column(index=True)

    # JSON blobs for complex nested structures.
    metrics_json: Mapped[str]  # JSON-serialised CompanyMetrics
    trend_json: Mapped[str]    # JSON-serialised Trend

    current_price: Mapped[float]
    summary: Mapped[str]

    # Index on run_timestamp enables efficient "latest run" queries.
    run_timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


class RecommendationModel(Base):
    """A single buy/hold/sell recommendation generated for a user holding.

    The composite index on ``(user_id, run_timestamp)`` supports the common
    pattern of retrieving all recommendations for a user from the most recent
    analysis run.
    """

    __tablename__ = "recommendations"

    # Primary key — UUID stored as a string.
    id: Mapped[str] = mapped_column(primary_key=True)

    # Index on user_id supports queries that retrieve all recommendations for
    # a specific user.
    user_id: Mapped[str] = mapped_column(index=True)

    symbol: Mapped[str]
    action: Mapped[str]    # ActionType.value — one of "buy", "hold", "sell"
    quantity: Mapped[int]
    rationale: Mapped[str]

    # Index on run_timestamp enables filtering by analysis run.
    run_timestamp: Mapped[datetime] = mapped_column(DateTime, index=True)

    # Composite index: most recommendation queries filter on user and recency.
    __table_args__ = (
        Index("ix_recommendations_user_id_run_timestamp", "user_id", "run_timestamp"),
    )


# ---------------------------------------------------------------------------
# User settings
# ---------------------------------------------------------------------------


class UserSettingsModel(Base):
    """Per-user configuration, keyed by ``user_id``.

    ``daily_investment`` is the amount the user is willing to invest each day
    for scalping and short-term profit analysis (Requirement 5.3).
    """

    __tablename__ = "user_settings"

    # user_id is the primary key — one settings row per user.
    user_id: Mapped[str] = mapped_column(primary_key=True)

    daily_investment: Mapped[float]
