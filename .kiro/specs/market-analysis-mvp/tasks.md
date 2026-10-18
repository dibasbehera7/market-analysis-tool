# Implementation Plan: Market Analysis MVP

## Overview

This plan implements the Phase 1 MVP of the Market Analysis Tool as a Python backend. The implementation follows a bottom-up approach: data models first, then pure-function components (Fetcher, Analyzer, Holdings Manager, Recommendation Engine), then infrastructure (database, API, scheduler), and finally integration wiring. Property-based tests are placed close to each implementation step to catch errors early.

The technology stack is Python 3.11+ with FastAPI, SQLAlchemy 2.0, APScheduler, yfinance/alpha_vantage, pandas/numpy, pandas-ta, and pytest + hypothesis for testing.

## Tasks

- [x] 1. Set up project structure and dependencies
  - [x] 1.1 Create project directory structure and pyproject.toml
    - Create `src/` and `tests/` directory structure with `properties/` and `integration/` subdirectories
    - Add dependencies: fastapi, uvicorn, sqlalchemy[asyncio], alembic, apscheduler, yfinance, alpha_vantage, pandas, numpy, pandas-ta, psycopg2-binary, pytest, hypothesis, httpx
    - Configure pytest with hypothesis plugin in `pyproject.toml`
    - _Requirements: (infrastructure setup)_

- [x] 2. Define core data models
  - [x] 2.1 Define enumerations and core data structures as Python dataclasses
    - Define `TrendType` (BULLISH, BEARISH, NEUTRAL) and `ActionType` (BUY, HOLD, SELL) enums
    - Define dataclasses: `NormalizedRecord`, `CompanyFinancials`, `CompanyMetrics`, `Trend`, `Insight`, `Holding`, `Comparison`, `Recommendation`, `ActionPlan`
    - Add `serialize()` and `deserialize()` methods to `NormalizedRecord` for JSON round-trip
    - _Requirements: 2.4, 3.1-3.5, 4.1-4.4, 5.1, 6.1, 7.2, 8.1_

  - [x] 2.2 Define SQLAlchemy ORM models
    - Define `HoldingModel`, `AnalysisResultModel`, `RecommendationModel`, `UserSettingsModel` with proper indexes, foreign keys, and column types
    - Create `Base` declarative base for all models
    - _Requirements: 10.1, 10.2, 10.3_

- [x] 3. Implement Fetcher (market hours, data fetching, normalization)
  - [x] 3.1 Implement `is_market_active()` pure function
    - Implement `is_market_active(now_utc: datetime | None = None) -> bool` in `fetcher.py`
    - Convert `now_utc` (defaulting to `datetime.utcnow()`) to IST (Asia/Kolkata, UTC+5:30)
    - Return `True` iff weekday is Monday–Friday (weekday() in {0,1,2,3,4}) and IST time is in range 09:15–15:30 inclusive
    - Accept an injectable `now_utc` parameter so tests can pass arbitrary datetimes without mocking system time
    - _Requirements: 1.2, 1.3_

  - [ ]* 3.2 Write property test for market hours detection correctness
    - **Property 1: Market hours detection correctness**
    - Generate random datetime values, verify `is_market_active()` returns True iff IST weekday is Mon–Fri and IST time is in [09:15, 15:30]
    - Tag: `# Feature: market-analysis-mvp, Property 1: Market hours detection correctness`
    - **Validates: Requirements 1.2, 1.3**

  - [x] 3.3 Implement DataSource protocol and adapter classes
    - Define `DataSource` Protocol with `fetch_company(symbol) -> dict` and `is_market_active() -> bool` methods
    - Implement `YFinanceAdapter` and `AlphaVantageAdapter` classes conforming to the protocol
    - _Requirements: 1.1, 1.2, 1.3_

  - [x] 3.4 Implement normalization, validation, and serialization methods
    - Implement `normalize(raw_data, api_source) -> NormalizedRecord` as a static method
    - Implement `validate(record) -> bool` returning True iff symbol is a non-empty string, price is strictly positive (> 0), and timestamp is a non-null datetime; when symbol is absent or unparseable, log error with `"[unknown]"` placeholder
    - Implement `serialize(record) -> str` and `deserialize(json_str) -> NormalizedRecord` using JSON
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ]* 3.5 Write property test for normalization produces valid records
    - **Property 2: Normalization produces valid records**
    - Generate random raw API dicts with valid symbol, price, and timestamp values; verify `normalize()` produces a `NormalizedRecord` with non-empty symbol, strictly positive float price, and valid datetime
    - Tag: `# Feature: market-analysis-mvp, Property 2: Normalization produces valid records`
    - **Validates: Requirements 2.1**

  - [ ]* 3.6 Write property test for validation correctness
    - **Property 3: Validation correctness**
    - Generate random `NormalizedRecord` instances with random combinations of None/invalid values; verify `validate()` returns True iff symbol is non-empty string, price > 0, and timestamp is non-null datetime
    - Tag: `# Feature: market-analysis-mvp, Property 3: Validation correctness`
    - **Validates: Requirements 2.2, 2.3**

  - [ ]* 3.7 Write property test for normalization serialization round-trip
    - **Property 4: Normalization serialization round-trip**
    - Generate random valid `NormalizedRecord` instances, serialize then deserialize, verify the restored record has equivalent symbol, price, and timestamp values
    - Tag: `# Feature: market-analysis-mvp, Property 4: Normalization serialization round-trip`
    - **Validates: Requirements 2.4**

  - [x] 3.8 Implement retry with exponential backoff and fallback logic
    - Implement retry logic with max 3 retries and exponential backoff: attempt 0 → sleep 1 s, attempt 1 → sleep 2 s, attempt 2 → sleep 4 s (backoff = 2 ** attempt)
    - Implement source fallback: if all retries fail for one source, try the next configured source
    - When all retries across all sources fail for a company, log the error with the company symbol and skip that company; allow the pipeline to continue with remaining companies
    - _Requirements: 1.4, 1.5_

- [x] 4. Implement Analyzer (metrics and trend detection)
  - [x] 4.1 Implement metric computation functions
    - Implement `compute_pe_ratio(price, eps)`, `compute_pb_ratio(price, book_value)`, `compute_roe(net_income, equity)` — return None for zero or negative denominator
    - Implement `compute_eps_growth(eps_history)` — percentage change `(last - first) / abs(first) * 100` over trailing 4+ quarters; return None if list has fewer than 4 elements or first element is zero
    - Implement `compute_npa(npa_value, total_assets)` — `(npa / total_assets) * 100`; return None if total assets ≤ 0
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 4.2 Write property test for ratio metric formula correctness
    - **Property 5: Ratio metric formula correctness**
    - Generate random (price, denominator) pairs; verify P/E, P/B, and ROE each equal price/denominator within floating-point tolerance for positive denominators; verify None for zero or negative denominators
    - Tag: `# Feature: market-analysis-mvp, Property 5: Ratio metric formula correctness`
    - **Validates: Requirements 3.1, 3.2, 3.3**

  - [ ]* 4.3 Write property test for EPS growth formula correctness
    - **Property 6: EPS growth formula correctness**
    - Generate random EPS histories of length ≥ 4 with non-zero first element; verify growth equals `(last - first) / abs(first) * 100`; verify None for zero first element or list shorter than 4
    - Tag: `# Feature: market-analysis-mvp, Property 6: EPS growth formula correctness`
    - **Validates: Requirements 3.4**

  - [ ]* 4.4 Write property test for NPA formula correctness
    - **Property 7: NPA formula correctness**
    - Generate random (npa, total_assets) pairs with positive total_assets; verify NPA equals `(npa / total_assets) * 100`; verify None for zero or negative total_assets
    - Tag: `# Feature: market-analysis-mvp, Property 7: NPA formula correctness`
    - **Validates: Requirements 3.5**

  - [x] 4.5 Implement trend detection functions
    - Implement `detect_trend(prices) -> TrendType` using 50/200 SMA crossover: short MA > long MA → BULLISH, short MA < long MA → BEARISH, equal or too-short sequence → NEUTRAL
    - Implement `compute_support_level(prices, period=252)` returning `min(prices[-period:])`, None for empty list
    - Implement `compute_resistance_level(prices, period=252)` returning `max(prices[-period:])`, None for empty list
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ]* 4.6 Write property test for trend classification by MA crossover
    - **Property 8: Trend classification by moving average crossover**
    - Generate random price sequences long enough for both MAs; verify short MA > long MA → BULLISH, short MA < long MA → BEARISH; verify NEUTRAL for too-short sequences
    - Tag: `# Feature: market-analysis-mvp, Property 8: Trend classification by moving average crossover`
    - **Validates: Requirements 4.1**

  - [ ]* 4.7 Write property test for support and resistance bounds
    - **Property 9: Support and resistance bound all prices in the trailing period**
    - Generate random non-empty price lists; verify `compute_support_level()` equals `min(prices[-252:])`, `compute_resistance_level()` equals `max(prices[-252:])`, and support ≤ every price ≤ resistance
    - Tag: `# Feature: market-analysis-mvp, Property 9: Support and resistance bound all prices`
    - **Validates: Requirements 4.2, 4.3**

  - [x] 4.8 Implement insight generation
    - Implement `generate_insight(symbol, metrics, trend) -> Insight` combining metrics and trend into a company-level summary
    - Wire the Analyzer pipeline: receive normalized records → compute metrics → detect trend → generate insight
    - _Requirements: 4.4_

  - [ ]* 4.9 Write property test for insight completeness
    - **Property 10: Insight contains all metrics and trend fields**
    - Generate random `CompanyMetrics` and `Trend` inputs; verify the returned `Insight` contains all metric fields (pe_ratio, pb_ratio, roe, eps_growth, npa) and complete trend classification (trend_type, support_level, resistance_level) with values identical to inputs
    - Tag: `# Feature: market-analysis-mvp, Property 10: Insight contains all metrics and trend fields`
    - **Validates: Requirements 4.4**

- [x] 5. Checkpoint — Ensure all tests pass
  - Ensure all property tests and unit tests pass, ask the user if questions arise.

- [x] 6. Implement Holdings Manager
  - [x] 6.1 Implement holdings CRUD operations with validation
    - Implement `add_holding(user_id, symbol, quantity, buy_price) -> Holding` storing to database; raise `ValueError` when symbol is empty or missing, quantity is ≤ 0, or buy_price is ≤ 0
    - Implement `get_holdings(user_id, symbol=None) -> list[Holding]` with optional symbol filter; return an empty list when no holdings exist for the given symbol
    - Implement `set_daily_investment(user_id, amount) -> None` storing to `UserSettingsModel`; raise `ValueError` if amount ≤ 0
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 6.2 Implement cost basis and total quantity computation
    - Implement `compute_cost_basis(holdings) -> float` as weighted average: `sum(qty * price) / sum(qty)`; raise `ValueError` for empty holdings list
    - Implement `compute_total_quantity(holdings) -> int` as sum of all quantities
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ]* 6.3 Write property test for cost basis weighted average
    - **Property 11: Cost basis equals weighted average buy price**
    - Generate random non-empty lists of Holdings; verify `compute_cost_basis()` equals `sum(h.quantity * h.buy_price for h in holdings) / sum(h.quantity for h in holdings)` within floating-point tolerance
    - Tag: `# Feature: market-analysis-mvp, Property 11: Cost basis equals weighted average buy price`
    - **Validates: Requirements 6.1**

  - [ ]* 6.4 Write property test for total quantity invariant
    - **Property 12: Total quantity equals sum of individual holding quantities**
    - Generate random lists of Holdings (including empty); verify `compute_total_quantity()` equals `sum(h.quantity for h in holdings)`
    - Tag: `# Feature: market-analysis-mvp, Property 12: Total quantity equals sum of individual holding quantities`
    - **Validates: Requirements 6.2, 6.3**

  - [ ]* 6.5 Write property test for holdings retrieval invariant
    - **Property 13: Holdings retrieval invariant**
    - After storing N holdings via `add_holding()` for a user and symbol, verify `get_holdings(user_id, symbol)` returns exactly those N holdings; verify `get_holdings()` returns an empty list when no holdings exist for the symbol
    - Tag: `# Feature: market-analysis-mvp, Property 13: Holdings retrieval invariant`
    - **Validates: Requirements 5.1, 5.2, 5.4**

- [x] 7. Implement Recommendation Engine
  - [x] 7.1 Implement comparison and recommendation generation
    - Implement `compare_holding_to_insight(holding, insight, cost_basis) -> Comparison`
    - Implement `generate_recommendation(holding, insight, cost_basis, current_price) -> Recommendation` applying: BULLISH + current_price < resistance_level → BUY; BEARISH + current_price < cost_basis → SELL; NEUTRAL → HOLD
    - Attach the Compliance_Disclaimer `"Insights only, not financial advice. Educational purpose only."` to every Recommendation
    - _Requirements: 7.1, 7.2, 7.4, 7.5, 7.6, 12.1_

  - [x] 7.2 Implement quantity, ranges, and target price computation
    - Implement `compute_suggested_quantity(action, daily_investment, current_price, holding_qty) -> int`: BUY → `floor(daily_investment / current_price)`, SELL → `holding_qty`, HOLD → 0; always non-negative
    - Implement `compute_buy_range(support_level, current_price) -> tuple[float, float]` returning `(support_level, current_price)` where low ≤ high
    - Implement `compute_sell_range(current_price, resistance_level) -> tuple[float, float]` returning `(current_price, resistance_level)` where low ≤ high
    - Implement `compute_target_price(support_level, resistance_level) -> float` as `(support_level + resistance_level) / 2`
    - _Requirements: 7.3, 8.1_

  - [ ]* 7.3 Write property test for recommendation action correctness
    - **Property 14: Recommendation action matches trend and price conditions**
    - Generate random Holdings and Insights; verify action is BUY when trend is BULLISH and price < resistance, SELL when trend is BEARISH and price < cost_basis, HOLD when trend is NEUTRAL; verify quantity is always non-negative and compliance disclaimer is present
    - Tag: `# Feature: market-analysis-mvp, Property 14: Recommendation action matches trend and price conditions`
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 12.1**

  - [x] 7.4 Implement action plan generation
    - Implement `generate_action_plan(recommendations, insights) -> ActionPlan` aggregating buy/sell ranges, target prices, and rebalancing suggestions across all recommendations
    - Include the Compliance_Disclaimer in every ActionPlan
    - Generate rebalancing suggestions based on the aggregate of all Recommendations
    - _Requirements: 8.1, 8.2, 8.3, 12.2_

  - [ ]* 7.5 Write property test for action plan range validity
    - **Property 15: Action plan ranges and targets are valid**
    - Generate random sets of Recommendations and Insights; verify every buy range has low ≤ high, every sell range has low ≤ high, every target price lies within [support_level, resistance_level], and the compliance disclaimer is present
    - Tag: `# Feature: market-analysis-mvp, Property 15: Action plan ranges and targets are valid`
    - **Validates: Requirements 8.1, 12.2**

- [x] 8. Checkpoint — Ensure all tests pass
  - Ensure all property tests and unit tests pass, ask the user if questions arise.

- [x] 9. Set up database connection and migrations
  - [x] 9.1 Implement database session management and Alembic setup
    - Create SQLAlchemy engine and session factory with transaction support and automatic rollback on exception
    - Initialize Alembic for migration management; generate initial migration for all ORM models
    - _Requirements: 10.1, 10.2, 10.3_

- [ ] 10. Implement FastAPI REST API
  - [ ] 10.1 Define Pydantic schemas and implement API endpoints
    - Define `HoldingRequest` with Pydantic validators enforcing: symbol is non-empty string, quantity > 0, buy_price > 0
    - Define `HoldingResponse`, `InsightResponse`, `ActionPlanResponse` Pydantic schemas
    - Implement `POST /holdings` endpoint calling `HoldingsManager.add_holding`; return HTTP 201 on success, HTTP 400 with descriptive message on `ValueError` or Pydantic validation failure
    - Implement `GET /analysis` endpoint returning the latest analysis results, optionally filtered by symbol
    - Implement `GET /recommendations` endpoint returning personalized recommendations and action plan for a given user_id
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [ ] 11. Implement Scheduler and pipeline
  - [ ] 11.1 Implement AnalysisScheduler with 12-hour interval and pipeline
    - Implement `start()` configuring APScheduler with a 12-hour interval trigger
    - Implement `run_pipeline()` executing fetch → analyze → recommend in sequence; log and skip individual company failures without stopping the run
    - _Requirements: 11.1, 11.2_

- [ ] 12. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 13. Integration and wiring
  - [ ] 13.1 Wire all components together in the pipeline
    - Connect Fetcher, Analyzer, HoldingsManager, RecommendationEngine, Database, and Scheduler
    - Ensure the full pipeline runs end-to-end: fetch NIFTY 500 → normalize → validate → analyze → compare holdings → generate recommendations → persist results
    - _Requirements: 1.1, 3.1, 7.1, 10.1, 11.2_

  - [ ]* 13.2 Write integration tests for API endpoints
    - Test `POST /holdings` with valid and invalid input (empty symbol, quantity ≤ 0, price ≤ 0) using FastAPI TestClient; verify HTTP 201 on success and HTTP 400 on invalid input
    - Test `GET /analysis` and `GET /recommendations` with TestClient; verify HTTP 200 and response schemas
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

  - [ ]* 13.3 Write integration tests for pipeline execution
    - Mock external APIs, run full pipeline via `AnalysisScheduler.run_pipeline()`, verify fetch → analyze → recommend executes in sequence and results are persisted to the test database
    - Verify a single-company failure (all sources exhausted) is logged and skipped without stopping the run
    - _Requirements: 11.2, 10.1, 10.2, 10.3, 1.5_

  - [ ]* 13.4 Write performance test for 500-company run
    - Run the full pipeline for 500 companies with mocked data sources; verify completion within 5 minutes
    - _Requirements: 13.1_

- [ ] 14. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at key breaks
- Property tests validate universal correctness properties using Hypothesis (minimum 100 iterations via `@settings(max_examples=100)`)
- Unit tests validate specific examples and edge cases (retry backoff timing, fallback behavior, compliance disclaimer presence, holdings validation boundaries)
- Integration tests verify component wiring, database operations, and API behavior
- The implementation follows a bottom-up approach: data models → pure functions → infrastructure → integration

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "2.2"] },
    { "id": 2, "tasks": ["3.1", "3.3", "3.4", "4.1", "6.1", "9.1"] },
    { "id": 3, "tasks": ["3.2", "3.8", "4.5", "6.2"] },
    { "id": 4, "tasks": ["3.5", "3.6", "3.7", "4.2", "4.3", "4.4", "4.6", "4.7", "4.8", "6.3", "6.4", "6.5", "11.1"] },
    { "id": 5, "tasks": ["4.9", "7.1"] },
    { "id": 6, "tasks": ["7.2", "7.3"] },
    { "id": 7, "tasks": ["7.4"] },
    { "id": 8, "tasks": ["7.5", "10.1"] },
    { "id": 9, "tasks": ["13.1"] },
    { "id": 10, "tasks": ["13.2", "13.3", "13.4"] }
  ]
}
```
