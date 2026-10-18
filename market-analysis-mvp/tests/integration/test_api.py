"""
Integration tests for the FastAPI REST API — task 10.1.

Uses an in-memory SQLite database (via aiosqlite) and FastAPI's async
TestClient (via httpx + anyio) so the tests exercise the real database
layer without requiring a running PostgreSQL instance.

Coverage:
  - POST /holdings  — valid input returns HTTP 201 with expected body
  - POST /holdings  — empty symbol returns HTTP 400
  - POST /holdings  — quantity ≤ 0 returns HTTP 400
  - POST /holdings  — buy_price ≤ 0 returns HTTP 400
  - GET  /analysis  — returns HTTP 200 with empty list when no data
  - GET  /analysis  — returns HTTP 200 with filtered results by symbol
  - GET  /recommendations — returns HTTP 200 with empty plan when no data

Requirements: 9.1, 9.2, 9.3, 9.4
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.api import app, get_db
from src.database.models import AnalysisResultModel, Base
from src.models import COMPLIANCE_DISCLAIMER

# ---------------------------------------------------------------------------
# In-memory SQLite test database
# ---------------------------------------------------------------------------

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture()
async def db_session():
    """Create a fresh in-memory SQLite database for each test."""
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    session = session_factory()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


@pytest_asyncio.fixture()
async def client(db_session: AsyncSession):
    """AsyncClient wired to the FastAPI app with the test DB session."""

    async def override_get_db():
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /holdings — valid input
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_holdings_returns_201(client: AsyncClient) -> None:
    """Valid holding submission returns HTTP 201."""
    payload = {
        "user_id": "user1",
        "symbol": "RELIANCE.NS",
        "quantity": 10,
        "buy_price": 2500.0,
    }
    response = await client.post("/holdings", json=payload)
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_post_holdings_response_body(client: AsyncClient) -> None:
    """Response body mirrors the submitted holding with an assigned id and created_at."""
    payload = {
        "user_id": "user2",
        "symbol": "TCS.NS",
        "quantity": 5,
        "buy_price": 3800.50,
    }
    response = await client.post("/holdings", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == "user2"
    assert body["symbol"] == "TCS.NS"
    assert body["quantity"] == 5
    assert body["buy_price"] == pytest.approx(3800.50)
    assert "id" in body
    assert "created_at" in body


# ---------------------------------------------------------------------------
# POST /holdings — invalid input (HTTP 400, Requirement 9.4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_holdings_empty_symbol_returns_400(client: AsyncClient) -> None:
    """Empty symbol field returns HTTP 400."""
    payload = {
        "user_id": "user1",
        "symbol": "",
        "quantity": 10,
        "buy_price": 100.0,
    }
    response = await client.post("/holdings", json=payload)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_post_holdings_whitespace_symbol_returns_400(client: AsyncClient) -> None:
    """Whitespace-only symbol field returns HTTP 400."""
    payload = {
        "user_id": "user1",
        "symbol": "   ",
        "quantity": 10,
        "buy_price": 100.0,
    }
    response = await client.post("/holdings", json=payload)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_post_holdings_zero_quantity_returns_400(client: AsyncClient) -> None:
    """quantity = 0 returns HTTP 400."""
    payload = {
        "user_id": "user1",
        "symbol": "INFY.NS",
        "quantity": 0,
        "buy_price": 1500.0,
    }
    response = await client.post("/holdings", json=payload)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_post_holdings_negative_quantity_returns_400(client: AsyncClient) -> None:
    """Negative quantity returns HTTP 400."""
    payload = {
        "user_id": "user1",
        "symbol": "INFY.NS",
        "quantity": -5,
        "buy_price": 1500.0,
    }
    response = await client.post("/holdings", json=payload)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_post_holdings_zero_price_returns_400(client: AsyncClient) -> None:
    """buy_price = 0 returns HTTP 400."""
    payload = {
        "user_id": "user1",
        "symbol": "WIPRO.NS",
        "quantity": 10,
        "buy_price": 0.0,
    }
    response = await client.post("/holdings", json=payload)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_post_holdings_negative_price_returns_400(client: AsyncClient) -> None:
    """Negative buy_price returns HTTP 400."""
    payload = {
        "user_id": "user1",
        "symbol": "WIPRO.NS",
        "quantity": 10,
        "buy_price": -100.0,
    }
    response = await client.post("/holdings", json=payload)
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_post_holdings_400_response_has_detail(client: AsyncClient) -> None:
    """HTTP 400 response includes a descriptive 'detail' field."""
    payload = {
        "user_id": "user1",
        "symbol": "GOOD.NS",
        "quantity": 0,
        "buy_price": 100.0,
    }
    response = await client.post("/holdings", json=payload)
    assert response.status_code == 400
    body = response.json()
    assert "detail" in body
    assert len(body["detail"]) > 0


# ---------------------------------------------------------------------------
# GET /analysis — no data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_analysis_empty_returns_200(client: AsyncClient) -> None:
    """GET /analysis returns HTTP 200 with an empty list when no data exists."""
    response = await client.get("/analysis")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_analysis_with_unknown_symbol_returns_empty(client: AsyncClient) -> None:
    """GET /analysis?symbol=UNKNOWN.NS returns empty list."""
    response = await client.get("/analysis", params={"symbol": "UNKNOWN.NS"})
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# GET /analysis — with seeded data
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def seeded_client(db_session: AsyncSession):
    """Client with pre-seeded AnalysisResultModel rows in the test database."""
    # Seed two analysis records for two different symbols.
    rows = [
        AnalysisResultModel(
            id=str(uuid.uuid4()),
            symbol="RELIANCE.NS",
            metrics_json=json.dumps({
                "pe_ratio": 20.5, "pb_ratio": 3.1, "roe": 0.15,
                "eps_growth": 8.0, "npa": None,
            }),
            trend_json=json.dumps({
                "trend_type": "bullish",
                "support_level": 2200.0,
                "resistance_level": 2800.0,
            }),
            current_price=2500.0,
            summary="Bullish trend with strong fundamentals.",
            run_timestamp=datetime(2024, 6, 1, 12, 0, 0),
        ),
        AnalysisResultModel(
            id=str(uuid.uuid4()),
            symbol="TCS.NS",
            metrics_json=json.dumps({
                "pe_ratio": 28.0, "pb_ratio": 10.0, "roe": 0.45,
                "eps_growth": 12.0, "npa": None,
            }),
            trend_json=json.dumps({
                "trend_type": "neutral",
                "support_level": 3500.0,
                "resistance_level": 4200.0,
            }),
            current_price=3800.0,
            summary="Neutral trend — wait for clearer signal.",
            run_timestamp=datetime(2024, 6, 1, 12, 0, 0),
        ),
    ]
    for row in rows:
        db_session.add(row)
    await db_session.commit()

    async def override_get_db():
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)  # type: ignore[arg-type]
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_get_analysis_returns_all_symbols(seeded_client: AsyncClient) -> None:
    """GET /analysis returns results for all seeded symbols."""
    response = await seeded_client.get("/analysis")
    assert response.status_code == 200
    symbols = {item["symbol"] for item in response.json()}
    assert "RELIANCE.NS" in symbols
    assert "TCS.NS" in symbols


@pytest.mark.asyncio
async def test_get_analysis_response_schema(seeded_client: AsyncClient) -> None:
    """GET /analysis response items contain all required InsightResponse fields."""
    response = await seeded_client.get("/analysis")
    assert response.status_code == 200
    items = response.json()
    assert len(items) > 0
    required_fields = {
        "symbol", "pe_ratio", "pb_ratio", "roe", "eps_growth", "npa",
        "trend_type", "support_level", "resistance_level",
        "current_price", "summary", "run_timestamp",
    }
    for item in items:
        assert required_fields.issubset(item.keys()), f"Missing fields in {item}"


@pytest.mark.asyncio
async def test_get_analysis_filtered_by_symbol(seeded_client: AsyncClient) -> None:
    """GET /analysis?symbol=RELIANCE.NS returns only the matching symbol."""
    response = await seeded_client.get("/analysis", params={"symbol": "RELIANCE.NS"})
    assert response.status_code == 200
    items = response.json()
    assert len(items) == 1
    assert items[0]["symbol"] == "RELIANCE.NS"
    assert items[0]["trend_type"] == "bullish"
    assert items[0]["current_price"] == pytest.approx(2500.0)


# ---------------------------------------------------------------------------
# GET /recommendations — no data
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_recommendations_no_data_returns_200(client: AsyncClient) -> None:
    """GET /recommendations returns HTTP 200 with empty plan when no data."""
    response = await client.get("/recommendations", params={"user_id": "user_unknown"})
    assert response.status_code == 200
    body = response.json()
    assert body["recommendations"] == []
    assert body["compliance_disclaimer"] == COMPLIANCE_DISCLAIMER


@pytest.mark.asyncio
async def test_get_recommendations_response_schema(client: AsyncClient) -> None:
    """GET /recommendations response contains all ActionPlanResponse fields."""
    response = await client.get("/recommendations", params={"user_id": "any_user"})
    assert response.status_code == 200
    body = response.json()
    required_fields = {
        "recommendations", "buy_ranges", "sell_ranges",
        "target_prices", "rebalancing_suggestions", "compliance_disclaimer",
    }
    assert required_fields.issubset(body.keys())
