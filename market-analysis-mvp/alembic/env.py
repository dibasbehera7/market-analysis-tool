"""Alembic environment configuration for the Market Analysis MVP.

This file wires together:
- The ORM ``Base`` metadata (so ``--autogenerate`` can diff the schema).
- A synchronous SQLAlchemy engine built from the ``DATABASE_URL`` environment
  variable (asyncpg prefix is stripped; Alembic needs a synchronous driver).
- Standard offline and online migration runners.

The ``DATABASE_URL`` environment variable controls the target database.
If the variable is not set, the default ``postgresql://localhost/market_analysis``
from ``alembic.ini`` is used as a fallback.
"""

from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

# Load .env from the project root (same directory as alembic.ini) so that
# DATABASE_URL is available when running `alembic upgrade head` without
# manually exporting environment variables first.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass  # python-dotenv is optional; fall back to alembic.ini default URL

from sqlalchemy import engine_from_config, pool

from alembic import context

# ---------------------------------------------------------------------------
# Import ORM Base and all models so their tables are registered on the
# metadata before autogenerate inspects it.
# ---------------------------------------------------------------------------

# ``Base`` is the DeclarativeBase subclass shared by all ORM models.
from src.database.models import (  # noqa: F401
    AnalysisResultModel,
    Base,
    HoldingModel,
    RecommendationModel,
    UserSettingsModel,
)

# ---------------------------------------------------------------------------
# Alembic config object
# ---------------------------------------------------------------------------

config = context.config

# Set up Python logging from the alembic.ini [loggers] section.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Point autogenerate at our ORM metadata.
target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Override sqlalchemy.url from DATABASE_URL environment variable if present.
# Strip the asyncpg driver suffix so the sync psycopg2 driver is used.
# ---------------------------------------------------------------------------

_env_url: str | None = os.environ.get("DATABASE_URL")
if _env_url:
    _sync_url = _env_url.replace(
        "postgresql+asyncpg://", "postgresql+psycopg2://"
    ).replace("postgresql://", "postgresql+psycopg2://")
    config.set_main_option("sqlalchemy.url", _sync_url)


# ---------------------------------------------------------------------------
# Migration runners
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (SQL script output, no live DB).

    The migration SQL is emitted to stdout / a file rather than executed
    against a live database connection.  Useful for generating migration
    scripts to be reviewed before applying.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (live database connection).

    Creates a synchronous engine from the ``alembic.ini`` configuration
    (or the overridden ``sqlalchemy.url``), connects to the database, and
    applies pending migrations within a transaction.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        # NullPool avoids connection-pool state leaking between test runs.
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
