"""
Smoke and unit tests for src/scheduler.py — task 11.1.

Coverage:
  - AnalysisScheduler can be instantiated with all required components
  - run_pipeline() executes fetch → analyze → recommend → persist in sequence
  - run_pipeline() skips individual company failures without stopping the run
  - run_pipeline() persists AnalysisResultModel rows and RecommendationModel rows
  - start() configures APScheduler with a 12-hour interval job
  - Fetcher total failure (empty fetch result) does not cause a crash
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from unittest.mock import MagicMock, patch, call

import pytest

from sqlalchemy import create_engine, select, distinct
from sqlalchemy.orm import Session, sessionmaker

from src.database.models import (
    AnalysisResultModel,
    Base,
    HoldingModel,
    RecommendationModel,
)
from src.fetcher import Fetcher
from src.analyzer import Analyzer
from src.models import (
    NormalizedRecord,
    Holding,
    Insight,
    CompanyMetrics,
    Trend,
    TrendType,
    ActionType,
    COMPLIANCE_DISCLAIMER,
    Recommendation,
)
from src.recommendation import RecommendationEngine
from src.scheduler import AnalysisScheduler
from src.user import HoldingsManager


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def in_memory_engine():
    """Create a fresh in-memory SQLite engine with all tables."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session_factory(in_memory_engine):
    """Return a callable that creates a new SQLAlchemy Session."""
    factory = sessionmaker(bind=in_memory_engine)
    return factory


@pytest.fixture()
def mock_fetcher():
    fetcher = MagicMock(spec=Fetcher)
    return fetcher


@pytest.fixture()
def analyzer():
    return Analyzer()


@pytest.fixture()
def reco_engine():
    return RecommendationEngine()


@pytest.fixture()
def scheduler(mock_fetcher, analyzer, reco_engine, session_factory):
    return AnalysisScheduler(
        fetcher=mock_fetcher,
        analyzer=analyzer,
        reco=reco_engine,
        db_session_factory=session_factory,
    )


def _make_record(symbol: str = "RELIANCE.NS", price: float = 2500.0) -> NormalizedRecord:
    return NormalizedRecord(
        symbol=symbol,
        price=price,
        timestamp=datetime.utcnow(),
    )


def _add_holding(session: Session, user_id: str, symbol: str, qty: int = 10, price: float = 100.0) -> None:
    session.add(HoldingModel(
        id=str(uuid.uuid4()),
        user_id=user_id,
        symbol=symbol,
        quantity=qty,
        buy_price=price,
        created_at=datetime.utcnow(),
    ))
    session.commit()


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------

class TestAnalysisSchedulerInstantiation:
    def test_constructor_accepts_required_args(self, scheduler):
        """AnalysisScheduler can be created with fetcher, analyzer, reco, session_factory."""
        assert scheduler is not None

    def test_scheduler_not_started_on_init(self, scheduler):
        """Scheduler should not be running until start() is called."""
        assert scheduler._scheduler is None


# ---------------------------------------------------------------------------
# run_pipeline — happy path
# ---------------------------------------------------------------------------

class TestRunPipelineHappyPath:
    def test_pipeline_persists_analysis_results(
        self, scheduler, mock_fetcher, session_factory
    ):
        """run_pipeline() persists an AnalysisResultModel row for each fetched record."""
        mock_fetcher.fetch_nifty500.return_value = [
            _make_record("RELIANCE.NS", 2500.0),
            _make_record("INFY.NS", 1500.0),
        ]

        scheduler.run_pipeline()

        with session_factory() as session:
            rows = session.query(AnalysisResultModel).all()
        assert len(rows) == 2
        symbols = {r.symbol for r in rows}
        assert symbols == {"RELIANCE.NS", "INFY.NS"}

    def test_pipeline_sets_run_timestamp_on_analysis_results(
        self, scheduler, mock_fetcher, session_factory
    ):
        """All persisted AnalysisResultModel rows share the same run_timestamp."""
        mock_fetcher.fetch_nifty500.return_value = [
            _make_record("RELIANCE.NS", 2500.0),
            _make_record("INFY.NS", 1500.0),
        ]

        scheduler.run_pipeline()

        with session_factory() as session:
            rows = session.query(AnalysisResultModel).all()
        timestamps = {r.run_timestamp for r in rows}
        assert len(timestamps) == 1, "All rows should share the same run_timestamp"

    def test_pipeline_generates_recommendations_for_users_with_holdings(
        self, scheduler, mock_fetcher, session_factory
    ):
        """run_pipeline() generates a RecommendationModel for each user holding."""
        mock_fetcher.fetch_nifty500.return_value = [
            _make_record("RELIANCE.NS", 2500.0),
        ]

        with session_factory() as session:
            _add_holding(session, user_id="user1", symbol="RELIANCE.NS", qty=5, price=2300.0)

        scheduler.run_pipeline()

        with session_factory() as session:
            rows = session.query(RecommendationModel).filter_by(user_id="user1").all()
        assert len(rows) == 1
        assert rows[0].symbol == "RELIANCE.NS"
        assert rows[0].action in ("buy", "hold", "sell")

    def test_pipeline_stores_valid_metrics_json(
        self, scheduler, mock_fetcher, session_factory
    ):
        """Persisted AnalysisResultModel rows have parseable metrics_json."""
        mock_fetcher.fetch_nifty500.return_value = [_make_record("TCS.NS", 3500.0)]

        scheduler.run_pipeline()

        with session_factory() as session:
            row = session.query(AnalysisResultModel).filter_by(symbol="TCS.NS").first()
        assert row is not None
        metrics = json.loads(row.metrics_json)
        # In MVP, financials are sentinels so ratios are None.
        assert "pe_ratio" in metrics
        assert "pb_ratio" in metrics

    def test_pipeline_stores_valid_trend_json(
        self, scheduler, mock_fetcher, session_factory
    ):
        """Persisted AnalysisResultModel rows have parseable trend_json with expected keys."""
        mock_fetcher.fetch_nifty500.return_value = [_make_record("TCS.NS", 3500.0)]

        scheduler.run_pipeline()

        with session_factory() as session:
            row = session.query(AnalysisResultModel).filter_by(symbol="TCS.NS").first()
        assert row is not None
        trend = json.loads(row.trend_json)
        assert "trend_type" in trend
        assert trend["trend_type"] in ("bullish", "bearish", "neutral")


# ---------------------------------------------------------------------------
# run_pipeline — error resilience
# ---------------------------------------------------------------------------

class TestRunPipelineErrorResilience:
    def test_pipeline_skips_company_on_analyze_failure(
        self, scheduler, mock_fetcher, session_factory
    ):
        """A failure analyzing one company does not stop other companies from being analyzed."""
        # Provide 3 records; patch _analyze_record to fail for the middle one.
        records = [
            _make_record("RELIANCE.NS", 2500.0),
            _make_record("BADFETCH.NS", 0.0),   # invalid price → will fail analyze
            _make_record("TCS.NS", 3500.0),
        ]
        mock_fetcher.fetch_nifty500.return_value = records

        # Patch _analyze_record to raise for BADFETCH.NS
        original_analyze = scheduler._analyze_record

        def patched_analyze(record):
            if record.symbol == "BADFETCH.NS":
                raise RuntimeError("Simulated analysis failure")
            return original_analyze(record)

        scheduler._analyze_record = patched_analyze

        scheduler.run_pipeline()

        with session_factory() as session:
            rows = session.query(AnalysisResultModel).all()
        symbols = {r.symbol for r in rows}
        assert "RELIANCE.NS" in symbols, "RELIANCE.NS should be analyzed"
        assert "TCS.NS" in symbols, "TCS.NS should be analyzed"
        assert "BADFETCH.NS" not in symbols, "BADFETCH.NS should be skipped"

    def test_pipeline_handles_empty_fetch_gracefully(
        self, scheduler, mock_fetcher, session_factory
    ):
        """When fetch_nifty500 returns an empty list, the pipeline runs without error."""
        mock_fetcher.fetch_nifty500.return_value = []

        # Should not raise
        scheduler.run_pipeline()

        with session_factory() as session:
            rows = session.query(AnalysisResultModel).all()
        assert rows == []

    def test_pipeline_handles_fetch_exception_gracefully(
        self, scheduler, mock_fetcher, session_factory
    ):
        """When fetch_nifty500 raises, the pipeline aborts gracefully without crash."""
        mock_fetcher.fetch_nifty500.side_effect = RuntimeError("Network error")

        # Should not raise
        scheduler.run_pipeline()

        with session_factory() as session:
            rows = session.query(AnalysisResultModel).all()
        assert rows == [], "No results should be stored when fetch fails completely"

    def test_pipeline_skips_user_on_recommendation_failure(
        self, scheduler, mock_fetcher, session_factory
    ):
        """A recommendation failure for one user does not block other users."""
        mock_fetcher.fetch_nifty500.return_value = [_make_record("RELIANCE.NS", 2500.0)]

        with session_factory() as session:
            _add_holding(session, user_id="good_user", symbol="RELIANCE.NS")
            _add_holding(session, user_id="bad_user", symbol="RELIANCE.NS")

        # Patch _recommend_for_user to fail for bad_user
        original_recommend = scheduler._recommend_for_user

        def patched_recommend(user_id, **kwargs):
            if user_id == "bad_user":
                raise RuntimeError("Simulated recommendation failure")
            return original_recommend(user_id=user_id, **kwargs)

        scheduler._recommend_for_user = patched_recommend

        scheduler.run_pipeline()

        with session_factory() as session:
            good_rows = session.query(RecommendationModel).filter_by(user_id="good_user").all()
            bad_rows = session.query(RecommendationModel).filter_by(user_id="bad_user").all()

        assert len(good_rows) == 1, "good_user should have a recommendation"
        assert len(bad_rows) == 0, "bad_user recommendation failed and should be skipped"

    def test_pipeline_skips_symbol_without_insight(
        self, scheduler, mock_fetcher, session_factory
    ):
        """Holdings for a symbol that has no insight are silently skipped."""
        # Fetch only RELIANCE.NS — INFY.NS has no insight
        mock_fetcher.fetch_nifty500.return_value = [_make_record("RELIANCE.NS", 2500.0)]

        with session_factory() as session:
            _add_holding(session, user_id="user1", symbol="RELIANCE.NS")
            _add_holding(session, user_id="user1", symbol="INFY.NS")  # no insight

        scheduler.run_pipeline()

        with session_factory() as session:
            rows = session.query(RecommendationModel).filter_by(user_id="user1").all()
        symbols = {r.symbol for r in rows}
        assert "RELIANCE.NS" in symbols
        assert "INFY.NS" not in symbols


# ---------------------------------------------------------------------------
# run_pipeline — multiple holdings same symbol (cost basis)
# ---------------------------------------------------------------------------

class TestRunPipelineCostBasis:
    def test_pipeline_handles_multiple_holdings_same_symbol(
        self, scheduler, mock_fetcher, session_factory
    ):
        """Multiple holdings for the same symbol produce one recommendation per holding."""
        mock_fetcher.fetch_nifty500.return_value = [_make_record("RELIANCE.NS", 2500.0)]

        with session_factory() as session:
            _add_holding(session, "user1", "RELIANCE.NS", qty=5, price=2000.0)
            _add_holding(session, "user1", "RELIANCE.NS", qty=10, price=2200.0)

        scheduler.run_pipeline()

        with session_factory() as session:
            rows = session.query(RecommendationModel).filter_by(user_id="user1").all()
        assert len(rows) == 2


# ---------------------------------------------------------------------------
# Scheduler start() — APScheduler configuration
# ---------------------------------------------------------------------------

class TestSchedulerStart:
    def test_start_creates_background_scheduler(self, scheduler):
        """start() creates a BackgroundScheduler when blocking=False (default)."""
        from apscheduler.schedulers.background import BackgroundScheduler

        try:
            scheduler.start(blocking=False)
            assert isinstance(scheduler._scheduler, BackgroundScheduler)
            assert scheduler._scheduler.running
        finally:
            scheduler.stop()

    def test_start_registers_12h_interval_job(self, scheduler):
        """start() registers exactly one job with a 12-hour interval trigger."""
        from apscheduler.triggers.interval import IntervalTrigger

        try:
            scheduler.start(blocking=False)
            jobs = scheduler._scheduler.get_jobs()
            assert len(jobs) == 1
            job = jobs[0]
            assert isinstance(job.trigger, IntervalTrigger)
            # Verify 12-hour interval in seconds (12 * 3600 = 43200)
            assert job.trigger.interval.total_seconds() == 43200
        finally:
            scheduler.stop()

    def test_stop_shuts_down_scheduler(self, scheduler):
        """stop() shuts down the scheduler cleanly."""
        scheduler.start(blocking=False)
        assert scheduler._scheduler.running
        scheduler.stop()
        assert not scheduler._scheduler.running

    def test_stop_safe_before_start(self, scheduler):
        """stop() is a no-op when start() has not been called."""
        # Should not raise
        scheduler.stop()
