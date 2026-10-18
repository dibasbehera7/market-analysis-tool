"""
FastAPI REST API for the Market Analysis MVP.

Exposes three endpoints:

  POST /holdings
      Submit a user holding. Returns HTTP 201 on success, HTTP 400 on
      validation failure (Pydantic or ValueError from HoldingsManager).

  GET /analysis
      Return the latest analysis results from AnalysisResultModel, with an
      optional ``symbol`` query-parameter filter.

  GET /recommendations
      Return the latest personalized recommendations and action plan for a
      given ``user_id``.

Requirements: 9.1, 9.2, 9.3, 9.4
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Load .env before anything else so DATABASE_URL and other vars are available
# when the session module creates its lazy engine on first use.
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:
    pass  # python-dotenv optional; export DATABASE_URL manually if not installed

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import (
    AnalysisResultModel,
    HoldingModel,
    RecommendationModel,
)
from src.database.session import AsyncSessionLocal
from src.models import (
    COMPLIANCE_DISCLAIMER,
    ActionType,
    CompanyMetrics,
    Holding,
    Insight,
    Recommendation,
    Trend,
    TrendType,
)
from src.recommendation import RecommendationEngine
from src.user import HoldingsManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Market Analysis MVP",
    description="NIFTY 500 market analysis — personalized buy/hold/sell recommendations.",
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# Dependency: database session
# ---------------------------------------------------------------------------


async def get_db() -> AsyncSession:  # type: ignore[override]
    """FastAPI dependency that yields an AsyncSession and handles commit/rollback."""
    session: AsyncSession = AsyncSessionLocal()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class HoldingRequest(BaseModel):
    """Request body for POST /holdings.

    Validation rules:
      - user_id: non-empty string
      - symbol:  non-empty string
      - quantity: integer > 0
      - buy_price: float > 0
    """

    user_id: str
    symbol: str
    quantity: int
    buy_price: float

    @field_validator("user_id")
    @classmethod
    def user_id_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("user_id must be a non-empty string")
        return v.strip()

    @field_validator("symbol")
    @classmethod
    def symbol_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("symbol must be a non-empty string")
        return v.strip()

    @field_validator("quantity")
    @classmethod
    def quantity_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError(f"quantity must be > 0, got {v!r}")
        return v

    @field_validator("buy_price")
    @classmethod
    def buy_price_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"buy_price must be > 0, got {v!r}")
        return v


class HoldingResponse(BaseModel):
    """Response body for a persisted Holding."""

    id: str
    user_id: str
    symbol: str
    quantity: int
    buy_price: float
    created_at: datetime

    model_config = {"from_attributes": True}


class InsightResponse(BaseModel):
    """Response body for a single company's analysis result."""

    symbol: str
    pe_ratio: Optional[float]
    pb_ratio: Optional[float]
    roe: Optional[float]
    eps_growth: Optional[float]
    npa: Optional[float]
    trend_type: str
    support_level: Optional[float]
    resistance_level: Optional[float]
    current_price: float
    summary: str
    run_timestamp: datetime


class RecommendationResponse(BaseModel):
    """Response body for a single recommendation."""

    symbol: str
    action: str
    quantity: int
    rationale: str
    compliance_disclaimer: str


class ActionPlanResponse(BaseModel):
    """Response body for the full action plan."""

    recommendations: list[RecommendationResponse]
    buy_ranges: dict[str, tuple[float, float]]
    sell_ranges: dict[str, tuple[float, float]]
    target_prices: dict[str, float]
    rebalancing_suggestions: list[str]
    compliance_disclaimer: str


# ---------------------------------------------------------------------------
# Helper: parse AnalysisResultModel → InsightResponse
# ---------------------------------------------------------------------------


def _parse_insight_response(row: AnalysisResultModel) -> InsightResponse:
    """Deserialize an AnalysisResultModel row into an InsightResponse."""
    metrics_data: dict = json.loads(row.metrics_json)
    trend_data: dict = json.loads(row.trend_json)

    return InsightResponse(
        symbol=row.symbol,
        pe_ratio=metrics_data.get("pe_ratio"),
        pb_ratio=metrics_data.get("pb_ratio"),
        roe=metrics_data.get("roe"),
        eps_growth=metrics_data.get("eps_growth"),
        npa=metrics_data.get("npa"),
        trend_type=trend_data.get("trend_type", "neutral"),
        support_level=trend_data.get("support_level"),
        resistance_level=trend_data.get("resistance_level"),
        current_price=row.current_price,
        summary=row.summary,
        run_timestamp=row.run_timestamp,
    )


# ---------------------------------------------------------------------------
# Helper: build Insight from AnalysisResultModel (for recommendation engine)
# ---------------------------------------------------------------------------


def _build_insight_from_row(row: AnalysisResultModel) -> Insight:
    """Reconstruct a domain Insight from a stored AnalysisResultModel row."""
    metrics_data: dict = json.loads(row.metrics_json)
    trend_data: dict = json.loads(row.trend_json)

    metrics = CompanyMetrics(
        symbol=row.symbol,
        pe_ratio=metrics_data.get("pe_ratio"),
        pb_ratio=metrics_data.get("pb_ratio"),
        roe=metrics_data.get("roe"),
        eps_growth=metrics_data.get("eps_growth"),
        npa=metrics_data.get("npa"),
    )

    # trend_type stored as the enum value string (e.g. "bullish")
    raw_trend_type = trend_data.get("trend_type", "neutral")
    try:
        trend_type = TrendType(raw_trend_type)
    except ValueError:
        trend_type = TrendType.NEUTRAL

    trend = Trend(
        symbol=row.symbol,
        trend_type=trend_type,
        support_level=trend_data.get("support_level"),
        resistance_level=trend_data.get("resistance_level"),
    )

    return Insight(
        symbol=row.symbol,
        metrics=metrics,
        trend=trend,
        current_price=row.current_price,
        summary=row.summary,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/holdings", response_model=HoldingResponse, status_code=201)
async def submit_holding(
    request: HoldingRequest,
    db: AsyncSession = Depends(get_db),
) -> HoldingResponse:
    """Submit a user holding.

    Returns HTTP 201 on success.
    Returns HTTP 400 when input validation fails (Pydantic) or when
    HoldingsManager raises a ValueError (e.g. empty symbol, non-positive
    quantity or price).

    Requirements: 9.1, 9.4
    """
    # HoldingsManager uses the synchronous SQLAlchemy Session API (add,
    # flush, query).  AsyncSession exposes these as sync methods too (add,
    # flush are sync; query is absent but we avoid it here).  We use
    # run_sync to execute the blocking HoldingsManager code inside the
    # async endpoint safely.
    user_id = request.user_id
    symbol = request.symbol
    quantity = request.quantity
    buy_price = request.buy_price

    def _add(sync_session):  # type: ignore[no-untyped-def]
        manager = HoldingsManager(sync_session)
        return manager.add_holding(
            user_id=user_id,
            symbol=symbol,
            quantity=quantity,
            buy_price=buy_price,
        )

    try:
        holding: Holding = await db.run_sync(_add)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return HoldingResponse(
        id=holding.id,
        user_id=holding.user_id,
        symbol=holding.symbol,
        quantity=holding.quantity,
        buy_price=holding.buy_price,
        created_at=holding.created_at,
    )


@app.get("/analysis", response_model=list[InsightResponse])
async def get_analysis(
    symbol: Optional[str] = Query(default=None, description="Filter by company symbol"),
    db: AsyncSession = Depends(get_db),
) -> list[InsightResponse]:
    """Retrieve the latest analysis results.

    Optionally filter by ``symbol`` query parameter.  Returns the most
    recent run's results: for each symbol the row with the highest
    ``run_timestamp`` is returned.

    Requirements: 9.2
    """
    # Find the latest run_timestamp overall (or per symbol if filtered).
    if symbol:
        # Fetch all rows for this symbol; return only the latest.
        stmt = (
            select(AnalysisResultModel)
            .where(AnalysisResultModel.symbol == symbol)
            .order_by(AnalysisResultModel.run_timestamp.desc())
        )
    else:
        # Return the single most-recent row per symbol using a subquery.
        # We do this by fetching all rows ordered by timestamp DESC and
        # de-duplicating in Python — acceptable for MVP scale (≤ 500 symbols).
        stmt = select(AnalysisResultModel).order_by(
            AnalysisResultModel.run_timestamp.desc()
        )

    result = await db.execute(stmt)
    rows: list[AnalysisResultModel] = list(result.scalars().all())

    if not rows:
        return []

    # De-duplicate: keep only the latest row per symbol.
    seen: set[str] = set()
    latest_rows: list[AnalysisResultModel] = []
    for row in rows:
        if row.symbol not in seen:
            seen.add(row.symbol)
            latest_rows.append(row)
        if symbol:
            # Only one symbol requested — stop after the first (latest) match.
            break

    return [_parse_insight_response(row) for row in latest_rows]


@app.get("/recommendations", response_model=ActionPlanResponse)
async def get_recommendations(
    user_id: str = Query(..., description="User identifier"),
    db: AsyncSession = Depends(get_db),
) -> ActionPlanResponse:
    """Retrieve the latest personalized recommendations and action plan.

    Fetches the most recent RecommendationModel rows for the given user,
    reconstructs Recommendation domain objects, loads the corresponding
    Insight rows (for range/target computation), and assembles an
    ActionPlanResponse.

    Returns an empty ActionPlan (with compliance disclaimer) when no
    recommendations exist for the user.

    Requirements: 9.3
    """
    # Fetch most-recent recommendations for this user (latest run only).
    # Step 1: find the latest run_timestamp for the user.
    latest_ts_stmt = (
        select(RecommendationModel.run_timestamp)
        .where(RecommendationModel.user_id == user_id)
        .order_by(RecommendationModel.run_timestamp.desc())
        .limit(1)
    )
    ts_result = await db.execute(latest_ts_stmt)
    latest_ts = ts_result.scalar_one_or_none()

    if latest_ts is None:
        # No recommendations found — return empty action plan.
        return ActionPlanResponse(
            recommendations=[],
            buy_ranges={},
            sell_ranges={},
            target_prices={},
            rebalancing_suggestions=["No recommendations available."],
            compliance_disclaimer=COMPLIANCE_DISCLAIMER,
        )

    # Step 2: fetch all recommendation rows for the latest run.
    reco_stmt = (
        select(RecommendationModel)
        .where(
            RecommendationModel.user_id == user_id,
            RecommendationModel.run_timestamp == latest_ts,
        )
    )
    reco_result = await db.execute(reco_stmt)
    reco_rows: list[RecommendationModel] = list(reco_result.scalars().all())

    # Step 3: reconstruct domain Recommendation objects.
    recommendations: list[Recommendation] = []
    symbols: list[str] = []
    for row in reco_rows:
        try:
            action = ActionType(row.action)
        except ValueError:
            action = ActionType.HOLD

        recommendations.append(
            Recommendation(
                symbol=row.symbol,
                action=action,
                quantity=row.quantity,
                rationale=row.rationale,
                compliance_disclaimer=COMPLIANCE_DISCLAIMER,
            )
        )
        symbols.append(row.symbol)

    # Step 4: load the latest Insight for each symbol to build ranges/targets.
    insights: dict[str, Insight] = {}
    if symbols:
        analysis_stmt = (
            select(AnalysisResultModel)
            .where(AnalysisResultModel.symbol.in_(symbols))
            .order_by(AnalysisResultModel.run_timestamp.desc())
        )
        analysis_result = await db.execute(analysis_stmt)
        analysis_rows: list[AnalysisResultModel] = list(
            analysis_result.scalars().all()
        )
        # De-duplicate: keep latest row per symbol.
        for row in analysis_rows:
            if row.symbol not in insights:
                insights[row.symbol] = _build_insight_from_row(row)

    # Step 5: generate the action plan via the RecommendationEngine.
    engine = RecommendationEngine()
    plan = engine.generate_action_plan(recommendations, insights)

    # Step 6: convert to response schema.
    reco_responses = [
        RecommendationResponse(
            symbol=r.symbol,
            action=r.action.value,
            quantity=r.quantity,
            rationale=r.rationale,
            compliance_disclaimer=r.compliance_disclaimer,
        )
        for r in plan.recommendations
    ]

    return ActionPlanResponse(
        recommendations=reco_responses,
        buy_ranges=plan.buy_ranges,
        sell_ranges=plan.sell_ranges,
        target_prices=plan.target_prices,
        rebalancing_suggestions=plan.rebalancing_suggestions,
        compliance_disclaimer=plan.compliance_disclaimer,
    )


# ---------------------------------------------------------------------------
# Exception handler: return 400 for Pydantic validation errors
# ---------------------------------------------------------------------------

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse as _JSONResponse


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):  # type: ignore[override]
    """Return HTTP 400 (not 422) for Pydantic request validation failures.

    Requirement 9.4: invalid input must return HTTP 400 with a descriptive
    error message.
    """
    errors = exc.errors()
    detail = "; ".join(
        f"{'.'.join(str(loc) for loc in e['loc'])}: {e['msg']}"
        for e in errors
    )
    return _JSONResponse(status_code=400, content={"detail": detail})
