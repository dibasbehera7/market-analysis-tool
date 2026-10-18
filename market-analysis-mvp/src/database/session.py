"""SQLAlchemy engine and session management for the Market Analysis MVP.

Provides:
- ``get_engine()``       — returns the (lazily created) async engine.
- ``get_sync_engine()``  — returns the sync engine used by Alembic.
- ``AsyncSessionLocal``  — async session factory (``expire_on_commit=False``).
- ``get_session()``      — async context manager with auto-commit / rollback.
- ``init_db()``          — coroutine that creates all tables from ORM metadata.

Configuration
-------------
The database connection URL is read from the ``DATABASE_URL`` environment
variable.  If the variable is not set the default points to a local
PostgreSQL database named ``market_analysis``:

    postgresql+asyncpg://localhost/market_analysis  (async driver)
    postgresql://localhost/market_analysis           (sync driver — Alembic)

Engines are created lazily on first access so importing this module does not
attempt to connect to (or import driver packages for) the database.  This
makes the module safe to import in environments where the driver is not
available (e.g., Alembic running ``env.py`` which imports only
``src.database.models``).

Requirements: 10.1, 10.2, 10.3
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Import Base and ORM models so their metadata is registered before any
# ``create_all`` or Alembic autogenerate call is made.
from src.database.models import (  # noqa: F401 — side-effect import
    AnalysisResultModel,
    Base,
    HoldingModel,
    RecommendationModel,
    UserSettingsModel,
)

# ---------------------------------------------------------------------------
# Connection URLs (read from environment; engines created lazily below)
# ---------------------------------------------------------------------------

def _async_url() -> str:
    """Return the async (asyncpg) database URL."""
    return os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://localhost/market_analysis",
    )


def _sync_url() -> str:
    """Return the sync database URL using the psycopg2 driver.

    Replaces the asyncpg driver prefix with psycopg2 so that Alembic and
    any synchronous code use psycopg2-binary rather than requiring psycopg
    (v3) which is not installed.
    """
    return _async_url().replace(
        "postgresql+asyncpg://", "postgresql+psycopg2://"
    )


# ---------------------------------------------------------------------------
# Lazy engine singletons
# ---------------------------------------------------------------------------

_async_engine: AsyncEngine | None = None
_sync_engine: Engine | None = None


def get_engine() -> AsyncEngine:
    """Return the async SQLAlchemy engine, creating it on first call."""
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_engine(
            _async_url(),
            echo=os.environ.get("DEBUG", "").lower() in {"1", "true", "yes"},
            pool_size=5,
            max_overflow=10,
        )
    return _async_engine


def get_sync_engine() -> Engine:
    """Return the synchronous SQLAlchemy engine used by Alembic migrations.

    This engine is created lazily and uses the standard psycopg2 (or
    psycopg) driver rather than asyncpg.
    """
    global _sync_engine
    if _sync_engine is None:
        _sync_engine = create_engine(
            _sync_url(),
            echo=os.environ.get("DEBUG", "").lower() in {"1", "true", "yes"},
        )
    return _sync_engine


# ---------------------------------------------------------------------------
# Session factory
#
# ``AsyncSessionLocal`` is a factory; calling it produces a new
# ``AsyncSession``.  ``expire_on_commit=False`` keeps attributes accessible
# after a commit without issuing a new SELECT.
# ---------------------------------------------------------------------------

def _make_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=True,
        autocommit=False,
    )


# Module-level reference — created lazily via property-like accessor below.
_session_factory: async_sessionmaker[AsyncSession] | None = None


def AsyncSessionLocal() -> AsyncSession:  # noqa: N802 — matches design doc naming
    """Return a new ``AsyncSession`` from the session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = _make_session_factory()
    return _session_factory()


# ---------------------------------------------------------------------------
# Async context manager
# ---------------------------------------------------------------------------


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an :class:`AsyncSession` that is automatically managed.

    Usage::

        async with get_session() as session:
            result = await session.execute(select(HoldingModel))

    Behaviour:
    - On normal exit: commits the transaction.
    - On any exception: rolls back the transaction, then re-raises.
    - The session is always closed on exit regardless of outcome.

    Yields:
        An :class:`~sqlalchemy.ext.asyncio.AsyncSession` bound to the engine.
    """
    session = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# Table initialisation
# ---------------------------------------------------------------------------


async def init_db() -> None:
    """Create all database tables defined in the ORM metadata.

    This is a convenience function for development and testing.  In
    production the schema should be managed via Alembic migrations.
    """
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
