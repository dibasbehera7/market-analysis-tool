"""
Application entry point for the Market Analysis MVP.

Wires all components together:
  - Creates the database engine and session factory
  - Instantiates Fetcher, Analyzer, RecommendationEngine
  - Instantiates and starts the AnalysisScheduler (background, 12-hour interval)
  - Starts the FastAPI server with uvicorn

Usage (from the market-analysis-mvp/ directory)::

    python -m src.main

Or via uvicorn directly (no scheduler)::

    uvicorn src.api:app --reload

Environment variables:
  DATABASE_URL   — SQLAlchemy async connection URL (default: local PostgreSQL)
  ALPHA_VANTAGE_API_KEY — API key for Alpha Vantage adapter (optional)
  HOST           — Bind host for uvicorn (default: 0.0.0.0)
  PORT           — Bind port for uvicorn (default: 8000)
  DEBUG          — Set to "1" or "true" to enable SQL echo

Requirements: 1.1, 3.1, 7.1, 10.1, 11.2
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

# Load .env from the project root before any other imports touch env vars.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)

logger = logging.getLogger(__name__)


def create_app():
    """Import and return the FastAPI app instance.

    Kept as a factory function so the app module can be imported lazily
    (e.g. for testing) without triggering database connections.
    """
    from src.api import app  # noqa: PLC0415
    return app


def build_fetcher():
    """Construct a Fetcher with all configured data sources.

    Sources configured:
      1. YFinanceAdapter — always available (no API key required).
      2. AlphaVantageAdapter — only added when ALPHA_VANTAGE_API_KEY is set.

    The Fetcher will try sources in order, falling back to the next source
    if all retries for the current one are exhausted.

    Returns:
        A configured :class:`~src.fetcher.Fetcher` instance.
    """
    from src.fetcher import AlphaVantageAdapter, Fetcher, YFinanceAdapter

    sources = [YFinanceAdapter()]

    alpha_key = os.environ.get("ALPHA_VANTAGE_API_KEY", "").strip()
    if alpha_key:
        sources.append(AlphaVantageAdapter(api_key=alpha_key))
        logger.info("main: AlphaVantageAdapter added as secondary data source.")
    else:
        logger.info(
            "main: ALPHA_VANTAGE_API_KEY not set; using only YFinanceAdapter."
        )

    return Fetcher(sources=sources)


def build_sync_session_factory():
    """Return a callable that produces synchronous SQLAlchemy sessions.

    The scheduler uses synchronous sessions; the FastAPI app uses async
    sessions (via ``src.database.session.AsyncSessionLocal``).  This
    factory creates a separate synchronous engine so both can coexist.

    Returns:
        A no-argument callable that returns a new :class:`~sqlalchemy.orm.Session`.
    """
    import os

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # Build the sync URL from the environment (replace asyncpg with psycopg2).
    async_url = os.environ.get(
        "DATABASE_URL",
        "postgresql+asyncpg://localhost/market_analysis",
    )
    sync_url = async_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")

    engine = create_engine(
        sync_url,
        echo=os.environ.get("DEBUG", "").lower() in {"1", "true", "yes"},
        pool_size=5,
        max_overflow=10,
    )

    # Import ORM models so their metadata is registered on the Base.
    from src.database.models import Base  # noqa: F401,PLC0415

    Session = sessionmaker(bind=engine, autoflush=True, autocommit=False)
    return Session


def main() -> None:
    """Wire all components and start the application.

    Execution order:
      1. Build Fetcher, Analyzer, RecommendationEngine.
      2. Build sync session factory for the scheduler.
      3. Instantiate and start AnalysisScheduler (background thread, 12 h interval).
         The first pipeline run fires immediately on startup.
      4. Start uvicorn serving the FastAPI app.  uvicorn blocks the main
         thread until interrupted; the scheduler runs in a background thread.
      5. On shutdown (KeyboardInterrupt / SIGTERM), stop the scheduler
         gracefully before exiting.
    """
    import uvicorn

    from src.analyzer import Analyzer
    from src.recommendation import RecommendationEngine
    from src.scheduler import AnalysisScheduler

    # ------------------------------------------------------------------
    # Component instantiation
    # ------------------------------------------------------------------
    fetcher = build_fetcher()
    analyzer = Analyzer()
    reco_engine = RecommendationEngine()
    session_factory = build_sync_session_factory()

    # ------------------------------------------------------------------
    # Scheduler
    # ------------------------------------------------------------------
    scheduler = AnalysisScheduler(
        fetcher=fetcher,
        analyzer=analyzer,
        reco=reco_engine,
        db_session_factory=session_factory,
    )
    scheduler.start(blocking=False)  # background thread; does not block

    # ------------------------------------------------------------------
    # FastAPI / uvicorn
    # ------------------------------------------------------------------
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))

    logger.info("main: starting uvicorn on %s:%d", host, port)

    try:
        uvicorn.run(
            "src.api:app",
            host=host,
            port=port,
            reload=False,
            log_level="info",
        )
    finally:
        logger.info("main: shutting down scheduler.")
        scheduler.stop()


if __name__ == "__main__":
    main()
