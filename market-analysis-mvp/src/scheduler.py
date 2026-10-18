"""
Scheduler module for the Market Analysis MVP.

Runs the full analysis pipeline every 12 hours:

    fetch → analyze → recommend → persist

The scheduler uses APScheduler 3.x with a ``BackgroundScheduler`` so the
calling process is not blocked.  A ``BlockingScheduler`` variant is also
provided for use in standalone CLI entry-points.

Requirements: 11.1, 11.2
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session

from src.analyzer import Analyzer
from src.database.models import AnalysisResultModel, RecommendationModel
from src.fetcher import Fetcher
from src.models import (
    ActionType,
    CompanyFinancials,
    CompanyMetrics,
    NormalizedRecord,
    Trend,
    TrendType,
)
from src.recommendation import RecommendationEngine
from src.user import HoldingsManager

logger = logging.getLogger(__name__)


class AnalysisScheduler:
    """Schedules and executes the full market-analysis pipeline.

    The pipeline runs every 12 hours, executing these stages in sequence:

    1. **Fetch** — retrieve latest prices for all NIFTY 500 companies via
       :meth:`Fetcher.fetch_nifty500`.
    2. **Analyze** — compute financial metrics and detect trends for each
       company.  Since only current price is available from the fetcher in
       the MVP, a minimal :class:`CompanyFinancials` is constructed per
       company; the current price is used as a single-element price history
       for trend support/resistance computation.
    3. **Recommend** — load user holdings from the database and generate
       personalized buy/hold/sell recommendations with action plans.
    4. **Persist** — store analysis results and recommendations to the
       database with the run timestamp.

    Individual company failures are caught, logged, and skipped — a single
    bad company does not abort the entire run.

    Args:
        fetcher:             Configured :class:`Fetcher` instance.
        analyzer:            Configured :class:`Analyzer` instance.
        reco:                Configured :class:`RecommendationEngine` instance.
        db_session_factory:  Callable that returns a synchronous
                             :class:`~sqlalchemy.orm.Session`.  Called once
                             per pipeline run; the session is committed and
                             closed at the end of each run.
    """

    def __init__(
        self,
        fetcher: Fetcher,
        analyzer: Analyzer,
        reco: RecommendationEngine,
        db_session_factory: Callable[[], Session],
    ) -> None:
        self._fetcher = fetcher
        self._analyzer = analyzer
        self._reco = reco
        self._db_session_factory = db_session_factory
        self._scheduler = None  # set in start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, blocking: bool = False) -> None:
        """Configure APScheduler and start the scheduler.

        By default a :class:`BackgroundScheduler` is used so the calling
        thread is not blocked.  Pass ``blocking=True`` to use a
        :class:`BlockingScheduler` (e.g. in a CLI entry-point where you
        want the process to stay alive as long as the scheduler runs).

        The first pipeline run is triggered immediately on start; subsequent
        runs execute every 12 hours.

        Args:
            blocking: If ``True``, use :class:`BlockingScheduler` (blocks
                      the calling thread).  Default ``False`` uses
                      :class:`BackgroundScheduler`.
        """
        if blocking:
            from apscheduler.schedulers.blocking import BlockingScheduler
            self._scheduler = BlockingScheduler()
        else:
            from apscheduler.schedulers.background import BackgroundScheduler
            self._scheduler = BackgroundScheduler()

        from apscheduler.triggers.interval import IntervalTrigger

        self._scheduler.add_job(
            func=self.run_pipeline,
            trigger=IntervalTrigger(hours=12),
            id="market_analysis_pipeline",
            name="Market Analysis Pipeline (12h)",
            replace_existing=True,
            # Run immediately on start; APScheduler schedules the first
            # execution as soon as start() returns.  Pass next_run_time to
            # trigger the first run without waiting 12 hours.
            next_run_time=datetime.now(),
        )

        logger.info(
            "AnalysisScheduler: starting %s with 12-hour interval.",
            type(self._scheduler).__name__,
        )
        self._scheduler.start()

    def stop(self) -> None:
        """Shut down the scheduler gracefully.

        Waits for any currently running jobs to complete before returning.
        Safe to call even if :meth:`start` has not been called.
        """
        if self._scheduler is not None and self._scheduler.running:
            logger.info("AnalysisScheduler: shutting down scheduler.")
            self._scheduler.shutdown(wait=True)

    def run_pipeline(self) -> None:
        """Execute the full sequential analysis pipeline.

        Stages:
          1. Fetch NIFTY 500 market data.
          2. Analyze each company — build insight from available price data.
          3. Load user holdings and generate recommendations.
          4. Persist all results with the current run timestamp.

        Per-company errors are caught, logged as warnings, and skipped so
        that a single failure does not halt the entire pipeline run.
        The session is always committed (or rolled back on error) and closed.

        Requirements: 11.2
        """
        run_timestamp = datetime.utcnow()
        logger.info(
            "AnalysisScheduler.run_pipeline: starting run at %s UTC.",
            run_timestamp.isoformat(),
        )

        # ------------------------------------------------------------------
        # Stage 1: Fetch
        # ------------------------------------------------------------------
        logger.info("AnalysisScheduler.run_pipeline: stage 1 — fetching NIFTY 500 data.")
        try:
            records: list[NormalizedRecord] = self._fetcher.fetch_nifty500()
        except Exception as exc:
            logger.error(
                "AnalysisScheduler.run_pipeline: fatal error in fetch stage: %s. "
                "Aborting run.",
                exc,
                exc_info=True,
            )
            return

        logger.info(
            "AnalysisScheduler.run_pipeline: fetched %d records.",
            len(records),
        )

        # ------------------------------------------------------------------
        # Stage 2: Analyze
        # Build an Insight per company from the fetched NormalizedRecord.
        # Since the MVP fetcher provides only current price (not full
        # financial statements or price history), a minimal CompanyFinancials
        # is constructed with the current price as EPS/book value proxy and
        # the current price as the single-element price series.
        # ------------------------------------------------------------------
        logger.info("AnalysisScheduler.run_pipeline: stage 2 — analyzing companies.")
        from src.models import Insight

        insights: dict[str, Insight] = {}
        analysis_results: list[AnalysisResultModel] = []

        for record in records:
            try:
                insight = self._analyze_record(record)
                insights[record.symbol] = insight

                # Serialize metrics and trend for persistence.
                metrics_dict = {
                    "pe_ratio": insight.metrics.pe_ratio,
                    "pb_ratio": insight.metrics.pb_ratio,
                    "roe": insight.metrics.roe,
                    "eps_growth": insight.metrics.eps_growth,
                    "npa": insight.metrics.npa,
                }
                trend_dict = {
                    "trend_type": insight.trend.trend_type.value,
                    "support_level": insight.trend.support_level,
                    "resistance_level": insight.trend.resistance_level,
                }

                analysis_results.append(
                    AnalysisResultModel(
                        id=str(uuid.uuid4()),
                        symbol=record.symbol,
                        metrics_json=json.dumps(metrics_dict),
                        trend_json=json.dumps(trend_dict),
                        current_price=record.price,
                        summary=insight.summary,
                        run_timestamp=run_timestamp,
                    )
                )
            except Exception as exc:
                logger.warning(
                    "AnalysisScheduler.run_pipeline: failed to analyze company '%s': %s. "
                    "Skipping.",
                    record.symbol,
                    exc,
                    exc_info=True,
                )

        logger.info(
            "AnalysisScheduler.run_pipeline: analyzed %d / %d companies.",
            len(insights),
            len(records),
        )

        # ------------------------------------------------------------------
        # Stage 3: Recommend
        # Load all user holdings from the database and generate
        # personalized recommendations.
        # ------------------------------------------------------------------
        logger.info("AnalysisScheduler.run_pipeline: stage 3 — generating recommendations.")
        recommendation_models: list[RecommendationModel] = []

        session: Session = self._db_session_factory()
        try:
            holdings_manager = HoldingsManager(session)

            # Retrieve all user IDs that have holdings for any analyzed symbol.
            user_ids = self._get_all_user_ids(session)
            logger.info(
                "AnalysisScheduler.run_pipeline: found %d users with holdings.",
                len(user_ids),
            )

            for user_id in user_ids:
                try:
                    reco_models = self._recommend_for_user(
                        user_id=user_id,
                        holdings_manager=holdings_manager,
                        insights=insights,
                        run_timestamp=run_timestamp,
                    )
                    recommendation_models.extend(reco_models)
                except Exception as exc:
                    logger.warning(
                        "AnalysisScheduler.run_pipeline: failed to generate "
                        "recommendations for user '%s': %s. Skipping.",
                        user_id,
                        exc,
                        exc_info=True,
                    )

            # ------------------------------------------------------------------
            # Stage 4: Persist
            # ------------------------------------------------------------------
            logger.info(
                "AnalysisScheduler.run_pipeline: stage 4 — persisting %d analysis "
                "results and %d recommendations.",
                len(analysis_results),
                len(recommendation_models),
            )
            try:
                session.bulk_save_objects(analysis_results)
                session.bulk_save_objects(recommendation_models)
                session.commit()
                logger.info(
                    "AnalysisScheduler.run_pipeline: run completed successfully at %s UTC.",
                    run_timestamp.isoformat(),
                )
            except Exception as exc:
                session.rollback()
                logger.error(
                    "AnalysisScheduler.run_pipeline: database persistence failed: %s. "
                    "Results not saved.",
                    exc,
                    exc_info=True,
                )

        except Exception as exc:
            session.rollback()
            logger.error(
                "AnalysisScheduler.run_pipeline: unexpected error in recommend/persist "
                "stage: %s.",
                exc,
                exc_info=True,
            )
        finally:
            session.close()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _analyze_record(self, record: NormalizedRecord) -> "Insight":
        """Build an Insight for a single NormalizedRecord.

        In the MVP the fetcher only provides current price, so we construct
        a minimal ``CompanyFinancials`` object.  Fields that require external
        financial statement data (EPS, book value, equity, NPA) are set to
        sentinel values that cause the corresponding metrics to return
        ``None`` (non-positive denominator handling in the Analyzer).

        The price history is set to a single element (current price), which
        means trend classification will return NEUTRAL (insufficient MA data)
        and support/resistance levels will equal the current price.

        Args:
            record: A validated :class:`NormalizedRecord` from the fetcher.

        Returns:
            A fully populated :class:`Insight`.
        """
        # Sentinel financials — metrics will be None for ratios that cannot
        # be computed from just a price point.
        financials = CompanyFinancials(
            symbol=record.symbol,
            earnings_per_share=0.0,     # → pe_ratio = None (EPS ≤ 0)
            book_value_per_share=0.0,   # → pb_ratio = None (BV ≤ 0)
            net_income=0.0,
            shareholder_equity=0.0,     # → roe = None (equity ≤ 0)
            eps_history=[],             # → eps_growth = None (< 4 values)
            is_bank=False,
        )

        # Single-element price history → NEUTRAL trend, support = resistance = price.
        prices = [record.price]

        return self._analyzer.analyze(
            symbol=record.symbol,
            financials=financials,
            prices=prices,
            current_price=record.price,
        )

    def _get_all_user_ids(self, session: Session) -> list[str]:
        """Return distinct user IDs that have at least one holding.

        Args:
            session: Active synchronous SQLAlchemy session.

        Returns:
            List of unique user_id strings.
        """
        from src.database.models import HoldingModel
        from sqlalchemy import select

        result = session.execute(
            select(HoldingModel.user_id).distinct()
        )
        return [row[0] for row in result.fetchall()]

    def _recommend_for_user(
        self,
        user_id: str,
        holdings_manager: HoldingsManager,
        insights: dict[str, "Insight"],
        run_timestamp: datetime,
    ) -> list[RecommendationModel]:
        """Generate and return ORM recommendation rows for a single user.

        For each holding symbol that has a corresponding insight, the
        recommendation engine produces a :class:`Recommendation`.
        Symbols without a matching insight are skipped.

        Per-symbol errors are caught, logged, and skipped so that a single
        bad holding does not block recommendations for the rest of the user's
        portfolio.

        Args:
            user_id:          The user's identifier.
            holdings_manager: Configured :class:`HoldingsManager`.
            insights:         Mapping of symbol → :class:`Insight` from stage 2.
            run_timestamp:    The UTC timestamp for this pipeline run.

        Returns:
            List of :class:`RecommendationModel` ORM instances ready to be
            bulk-saved to the database.
        """
        user_holdings = holdings_manager.get_holdings(user_id=user_id)
        if not user_holdings:
            return []

        # Group holdings by symbol to compute per-symbol cost basis.
        from collections import defaultdict
        holdings_by_symbol: dict[str, list] = defaultdict(list)
        for h in user_holdings:
            holdings_by_symbol[h.symbol].append(h)

        reco_models: list[RecommendationModel] = []

        for symbol, symbol_holdings in holdings_by_symbol.items():
            insight = insights.get(symbol)
            if insight is None:
                logger.debug(
                    "AnalysisScheduler: no insight for symbol '%s' (user '%s'); skipping.",
                    symbol,
                    user_id,
                )
                continue

            try:
                cost_basis = HoldingsManager.compute_cost_basis(symbol_holdings)
                current_price = insight.current_price

                # Generate one recommendation per individual holding.
                for holding in symbol_holdings:
                    try:
                        reco = self._reco.generate_recommendation(
                            holding=holding,
                            insight=insight,
                            cost_basis=cost_basis,
                            current_price=current_price,
                        )

                        reco_models.append(
                            RecommendationModel(
                                id=str(uuid.uuid4()),
                                user_id=user_id,
                                symbol=reco.symbol,
                                action=reco.action.value,
                                quantity=reco.quantity,
                                rationale=reco.rationale,
                                run_timestamp=run_timestamp,
                            )
                        )
                    except Exception as exc:
                        logger.warning(
                            "AnalysisScheduler: failed to recommend for holding "
                            "'%s' (user '%s', holding id '%s'): %s. Skipping.",
                            symbol,
                            user_id,
                            holding.id,
                            exc,
                            exc_info=True,
                        )

            except Exception as exc:
                logger.warning(
                    "AnalysisScheduler: failed to process symbol '%s' for user '%s': %s. "
                    "Skipping.",
                    symbol,
                    user_id,
                    exc,
                    exc_info=True,
                )

        return reco_models
