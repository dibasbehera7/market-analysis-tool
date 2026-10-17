# Market Analysis MVP

An open-source (MIT) Python backend that fetches NIFTY 500 market data, computes financial metrics, detects trends, and generates personalized buy/hold/sell recommendations with actionable trading plans.

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Language | Python 3.11+ |
| Web Framework | FastAPI + uvicorn |
| Database | PostgreSQL + SQLAlchemy 2.0 (asyncio) |
| Migrations | Alembic |
| Scheduler | APScheduler (12-hour interval) |
| Data Sources | yfinance, alpha_vantage |
| Analysis | pandas, numpy, pandas-ta |
| Testing | pytest, hypothesis (property-based) |

## Project Structure

```
market-analysis-mvp/
├── src/
│   ├── __init__.py
│   ├── fetcher.py          # Market data fetching, normalization, validation
│   ├── analyzer.py         # Metrics computation, trend detection, insights
│   ├── recommendation.py   # Recommendation and action plan generation
│   ├── user.py             # Holdings manager (CRUD + cost basis)
│   ├── api.py              # FastAPI REST endpoints
│   ├── scheduler.py        # APScheduler pipeline runner
│   ├── models.py           # Dataclasses and enumerations
│   └── database.py         # SQLAlchemy engine and session factory
├── tests/
│   ├── __init__.py
│   ├── properties/         # Hypothesis property-based tests
│   │   └── __init__.py
│   └── integration/        # Integration tests
│       └── __init__.py
├── pyproject.toml
└── README.md
```

## Setup

### Prerequisites

- Python 3.11+
- PostgreSQL running locally (or via Docker)

### Installation

```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Linux/macOS
.venv\Scripts\activate             # Windows

# Install the package with dev dependencies
pip install -e ".[dev]"
```

### Configuration

Set the following environment variables (or create a `.env` file):

```env
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/market_analysis
ALPHA_VANTAGE_API_KEY=your_api_key_here
```

### Run migrations

```bash
alembic upgrade head
```

### Run the API server

```bash
uvicorn src.api:app --reload
```

### Run tests

```bash
pytest
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/holdings` | Submit a user stock holding |
| GET | `/analysis` | Retrieve latest analysis results (filter by `?symbol=`) |
| GET | `/recommendations` | Retrieve personalized recommendations (`?user_id=`) |

## Compliance Disclaimer

> Insights only, not financial advice. Educational purpose only.

## License

MIT
