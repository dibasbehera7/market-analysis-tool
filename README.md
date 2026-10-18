# Automated Market Analysis Tool

An open-source Python backend that fetches NIFTY 500 market data, computes financial metrics, detects price trends, and delivers personalized buy/hold/sell recommendations with actionable trading plans.

> **Disclaimer:** Insights only, not financial advice. Educational purpose only.

---

## What's Inside

```
market-analysis-tool/
├── market-analysis-mvp/        # The Python backend MVP
│   ├── src/
│   │   ├── fetcher.py          # Market data fetching (yfinance + Alpha Vantage), normalization, retry
│   │   ├── analyzer.py         # Financial metrics, trend detection, insight summaries
│   │   ├── recommendation.py   # Buy/hold/sell recommendation and action plan engine
│   │   ├── user.py             # Holdings CRUD, cost-basis computation
│   │   ├── api.py              # FastAPI REST endpoints
│   │   ├── scheduler.py        # APScheduler 12-hour pipeline runner
│   │   ├── models.py           # Domain dataclasses and enumerations
│   │   └── database/           # SQLAlchemy async engine, session, ORM models
│   ├── alembic/                # Database migrations
│   ├── tests/                  # pytest + hypothesis property-based tests
│   └── pyproject.toml
└── requirements/               # Feature specifications
```

---

## Technology Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Web Framework | FastAPI + uvicorn |
| Database | PostgreSQL + SQLAlchemy 2.0 (asyncio) |
| Migrations | Alembic |
| Scheduler | APScheduler 3.x — 12-hour pipeline interval |
| Market Data | yfinance (free), Alpha Vantage (optional API key) |
| Analysis | pandas, numpy, pandas-ta |
| Testing | pytest, hypothesis (property-based), pytest-asyncio |

---

## Prerequisites

- Python 3.11 or later
- PostgreSQL running locally or via Docker
- Git

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-org/market-analysis-tool.git
cd market-analysis-tool/market-analysis-mvp
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv

# Linux / macOS
source .venv/bin/activate

# Windows (PowerShell)
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
# Production dependencies only
pip install -e .

# Include dev / test dependencies
pip install -e ".[dev]"
```

---

## Configuration

Create a `.env` file inside `market-analysis-mvp/` or export the variables in your shell:

```env
# Required — SQLAlchemy async connection URL
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/market_analysis

# Optional — adds Alpha Vantage as a secondary data source
ALPHA_VANTAGE_API_KEY=your_api_key_here

# Optional — server bind settings (defaults shown)
HOST=0.0.0.0
PORT=8000

# Optional — set to "1" to enable SQLAlchemy echo logging
DEBUG=0
```

> If `ALPHA_VANTAGE_API_KEY` is not set, the application runs with yfinance only (no registration required).

---

## Database Setup

### Start PostgreSQL (Docker quick-start)

```bash
docker run -d \
  --name market-analysis-db \
  -e POSTGRES_USER=user \
  -e POSTGRES_PASSWORD=password \
  -e POSTGRES_DB=market_analysis \
  -p 5432:5432 \
  postgres:16
```

### Run migrations

From the `market-analysis-mvp/` directory:

```bash
alembic upgrade head
```

This creates four tables: `holdings`, `analysis_results`, `recommendations`, and `user_settings`.

---

## Data Seeding

The analysis pipeline runs automatically every 12 hours once the server starts. To seed the database with initial data before making API calls, you can seed holdings for a test user by calling the REST API directly:

```bash
# Add a holding for user "alice"
curl -X POST http://localhost:8000/holdings \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "symbol": "RELIANCE.NS", "quantity": 10, "buy_price": 2800.00}'

curl -X POST http://localhost:8000/holdings \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "symbol": "TCS.NS", "quantity": 5, "buy_price": 3500.00}'

curl -X POST http://localhost:8000/holdings \
  -H "Content-Type: application/json" \
  -d '{"user_id": "alice", "symbol": "INFY.NS", "quantity": 20, "buy_price": 1500.00}'
```

To trigger an immediate analysis run without waiting for the scheduler, restart the application — it fires a pipeline run on startup.

---

## Running the Application

### Full application (API + background scheduler)

Runs the FastAPI server and starts the 12-hour analysis pipeline in the background:

```bash
# From the market-analysis-mvp/ directory
python -m src.main
```

### API server only (no scheduler)

Useful for development when you want hot-reload but don't need the background pipeline:

```bash
uvicorn src.api:app --reload --host 0.0.0.0 --port 8000
```

The interactive API docs are available at [http://localhost:8000/docs](http://localhost:8000/docs) once the server is running.

---

## API Reference

### `POST /holdings`

Submit a user stock holding.

**Request body**

```json
{
  "user_id": "alice",
  "symbol": "RELIANCE.NS",
  "quantity": 10,
  "buy_price": 2800.00
}
```

**Response** — `201 Created`

```json
{
  "id": "uuid",
  "user_id": "alice",
  "symbol": "RELIANCE.NS",
  "quantity": 10,
  "buy_price": 2800.0,
  "created_at": "2026-10-18T12:00:00"
}
```

---

### `GET /analysis`

Retrieve the latest analysis results. Optionally filter by symbol.

```
GET /analysis
GET /analysis?symbol=RELIANCE.NS
```

**Response** — `200 OK` — array of insight objects including PE ratio, trend type, support/resistance levels, and a plain-language summary.

---

### `GET /recommendations`

Retrieve the latest personalized buy/hold/sell recommendations and action plan for a user.

```
GET /recommendations?user_id=alice
```

**Response** — `200 OK`

```json
{
  "recommendations": [
    {
      "symbol": "RELIANCE.NS",
      "action": "hold",
      "quantity": 10,
      "rationale": "...",
      "compliance_disclaimer": "Insights only, not financial advice. Educational purpose only."
    }
  ],
  "buy_ranges": { "TCS.NS": [3400.0, 3600.0] },
  "sell_ranges": {},
  "target_prices": { "RELIANCE.NS": 2900.0 },
  "rebalancing_suggestions": ["..."],
  "compliance_disclaimer": "Insights only, not financial advice. Educational purpose only."
}
```

---

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=src --cov-report=term-missing

# Run a specific test file
pytest tests/test_analyzer.py
```

---

## How the Pipeline Works

```
Every 12 hours (and on startup):

  1. Fetch   — pull latest prices for all NIFTY 500 symbols via yfinance
               (falls back to Alpha Vantage when an API key is configured)
  2. Analyze — compute PE, PB, ROE, EPS-growth, NPA metrics; classify
               trend as bullish / bearish / neutral; compute support and
               resistance levels
  3. Recommend — for each user's holdings, generate buy/hold/sell
                 recommendations based on metrics, trend, and cost basis
  4. Persist — write analysis results and recommendations to PostgreSQL
```

Individual company failures are caught and skipped — a single bad symbol does not abort the run.

---

## Contributing

Contributions are welcome. Please open an issue to discuss a change before submitting a pull request.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes
4. Push the branch and open a pull request

---

## License

[MIT](LICENSE)
