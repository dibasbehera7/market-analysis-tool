# Requirements Document

## Introduction

This document specifies the requirements for the MVP (Phase 1) of the Market Analysis Tool — an open-source, MIT-licensed automation tool that fetches NIFTY 500 market data, computes financial metrics, detects trends, integrates user holdings, and generates personalized buy/hold/sell recommendations with actionable plans.

The MVP scope covers four core modules: the Data Fetcher, the Analysis Engine, the Recommendation Engine, and the User Holdings Manager, exposed through a REST API backed by a PostgreSQL database with scheduled 12-hour analysis runs. Notification delivery, subscription tiers, Stripe billing, and the mobile application are deferred to Phase 2 and are out of scope for this specification.

## Glossary

- **System**: The market-analysis-mvp application as a whole.
- **Fetcher**: The data fetching component responsible for retrieving market data from external APIs.
- **Analyzer**: The analysis engine component responsible for computing financial metrics and detecting trends.
- **Recommendation_Engine**: The component responsible for generating personalized recommendations and action plans.
- **Holdings_Manager**: The component responsible for storing, retrieving, and computing user stock holdings.
- **API**: The REST API layer component that exposes endpoints to frontend applications.
- **NIFTY_500**: The index of the top 500 companies listed on the National Stock Exchange of India.
- **Market_Data**: Stock price and financial data fetched from external APIs for NIFTY_500 companies.
- **Market_Data_API**: An external data source API providing stock market data (NSE, Yahoo Finance, Alpha Vantage, or Zerodha Kite Connect).
- **EOD_Data**: End-of-day close price data for a company.
- **Intraday_Data**: Live market data for a company during active trading hours.
- **Holding**: A user position in a stock, defined by company symbol, quantity, and buy price.
- **Cost_Basis**: The weighted-average purchase price of a stock when multiple Holdings exist for the same company.
- **Metric**: A financial metric computed from Market_Data, including Price-to-Earnings ratio, Price-to-Book ratio, Return on Equity, EPS growth rate, and Non-Performing Assets.
- **P/E_Ratio**: The Price-to-Earnings ratio, computed as market price divided by earnings per share.
- **P/B_Ratio**: The Price-to-Book ratio, computed as market price divided by book value per share.
- **ROE**: The Return on Equity, computed as net income divided by shareholder equity.
- **EPS_Growth**: The percentage change in earnings per share over the trailing four quarters.
- **NPA**: Non-Performing Assets, computed as a percentage of total assets for bank-classified companies.
- **Trend**: A directional classification for a company: bullish, bearish, or neutral.
- **Support_Level**: The lowest price level for a company over the trailing 52-week period.
- **Resistance_Level**: The highest price level for a company over the trailing 52-week period.
- **Insight**: A company-level summary of computed Metrics and Trend classification.
- **Recommendation**: A personalized action suggestion of type buy, hold, or sell, with a suggested quantity, for a specific Holding.
- **Action_Plan**: A summary of actionable steps including buy/sell ranges, target prices, and portfolio rebalancing suggestions.
- **Compliance_Disclaimer**: The statement "Insights only, not financial advice. Educational purpose only."

## Requirements

### Requirement 1: Fetch NIFTY 500 Market Data

**User Story:** As a market analyst, I want the system to fetch NIFTY 500 market data from external APIs, so that I have current data for analysis.

#### Acceptance Criteria

1. THE Fetcher SHALL fetch last close price data for all NIFTY_500 companies from configured Market_Data_APIs
2. WHEN the market is in active trading hours, THE Fetcher SHALL fetch Intraday_Data for NIFTY_500 companies
3. WHEN the market is outside active trading hours, THE Fetcher SHALL fetch EOD_Data for NIFTY_500 companies
4. WHEN a Market_Data_API request fails, THE Fetcher SHALL retry the request up to 3 times with exponential backoff starting at 1 second
5. IF all retry attempts for a Market_Data_API request fail, THEN THE Fetcher SHALL log the error with the affected company symbol and continue fetching data from remaining Market_Data_APIs

### Requirement 2: Normalize and Validate Fetched Data

**User Story:** As a developer, I want the system to normalize fetched data into a consistent format, so that downstream components can process data uniformly.

#### Acceptance Criteria

1. WHEN Market_Data is fetched from any Market_Data_API, THE Fetcher SHALL normalize the data into a standard record containing symbol, price, and timestamp fields
2. THE Fetcher SHALL validate that every fetched Market_Data record contains the required fields: symbol, price, and timestamp
3. IF a fetched Market_Data record is missing a required field, THEN THE Fetcher SHALL reject the record and log the error with the symbol identifier
4. WHEN a valid normalized Market_Data record is serialized and then deserialized, THE Fetcher SHALL produce an equivalent record

### Requirement 3: Compute Financial Metrics

**User Story:** As a market analyst, I want the system to compute financial metrics, so that I can evaluate company performance.

#### Acceptance Criteria

1. THE Analyzer SHALL compute the P/E_Ratio for each NIFTY_500 company as market price divided by earnings per share
2. THE Analyzer SHALL compute the P/B_Ratio for each NIFTY_500 company as market price divided by book value per share
3. THE Analyzer SHALL compute the ROE for each NIFTY_500 company as net income divided by shareholder equity
4. THE Analyzer SHALL compute the EPS_Growth for each NIFTY_500 company as the percentage change in earnings per share over the trailing four quarters
5. WHERE a company is classified as a bank, THE Analyzer SHALL compute NPA as a percentage of total assets

### Requirement 4: Detect Market Trends

**User Story:** As a market analyst, I want the system to detect market trends, so that I can identify bullish or bearish patterns.

#### Acceptance Criteria

1. THE Analyzer SHALL classify the Trend for each NIFTY_500 company as bullish, bearish, or neutral based on price movement analysis
2. THE Analyzer SHALL compute the Support_Level for each company as the lowest price over the trailing 52-week period
3. THE Analyzer SHALL compute the Resistance_Level for each company as the highest price over the trailing 52-week period
4. WHEN metric computation and trend classification are complete for a company, THE Analyzer SHALL generate an Insight summarizing the Metrics and Trend for that company

### Requirement 5: Manage User Holdings

**User Story:** As an investor, I want to input and manage my stock holdings, so that the system can analyze my portfolio.

#### Acceptance Criteria

1. WHEN a user submits a Holding with company symbol, quantity, and buy price, THE Holdings_Manager SHALL store the Holding in the database
2. THE Holdings_Manager SHALL support multiple Holdings with different buy prices for a single company
3. THE Holdings_Manager SHALL accept a daily investment amount for scalping and short-term profit analysis
4. WHEN a user requests Holdings for a specific company, THE Holdings_Manager SHALL return all Holdings associated with that company symbol

### Requirement 6: Compute Cost Basis

**User Story:** As an investor, I want the system to compute my average cost basis, so that I can track my effective purchase price per stock.

#### Acceptance Criteria

1. WHEN a company has multiple Holdings with different buy prices, THE Holdings_Manager SHALL compute the Cost_Basis as the weighted average of buy prices by quantity
2. THE Holdings_Manager SHALL compute the total quantity as the sum of all Holding quantities for a given company
3. WHEN total quantity is computed for a company with multiple Holdings, THE Holdings_Manager SHALL produce a value equal to the sum of individual Holding quantities

### Requirement 7: Generate Personalized Recommendations

**User Story:** As an investor, I want personalized buy/hold/sell recommendations, so that I can make informed trading decisions.

#### Acceptance Criteria

1. WHEN analysis results and user Holdings are available, THE Recommendation_Engine SHALL compare each Holding against the corresponding company Insight
2. THE Recommendation_Engine SHALL generate a personalized Recommendation of type buy, hold, or sell for each Holding
3. THE Recommendation_Engine SHALL include a suggested quantity in each Recommendation
4. WHEN a company Trend is bullish and the current price is below the Resistance_Level, THE Recommendation_Engine SHALL generate a buy Recommendation
5. WHEN a company Trend is bearish and the Holding is at a loss relative to Cost_Basis, THE Recommendation_Engine SHALL generate a sell Recommendation
6. WHEN a company Trend is neutral, THE Recommendation_Engine SHALL generate a hold Recommendation

### Requirement 8: Generate Action Plans

**User Story:** As an investor, I want an actionable summary, so that I can execute trades efficiently.

#### Acceptance Criteria

1. THE Recommendation_Engine SHALL generate an Action_Plan with buy/sell ranges and target prices for each Holding
2. THE Recommendation_Engine SHALL suggest portfolio rebalancing actions based on the aggregate of all Recommendations
3. THE Recommendation_Engine SHALL include the Compliance_Disclaimer in every Action_Plan

### Requirement 9: Expose REST API

**User Story:** As a developer, I want REST API endpoints, so that frontend applications can interact with the system.

#### Acceptance Criteria

1. THE API SHALL expose an endpoint to submit user Holdings
2. THE API SHALL expose an endpoint to retrieve analysis results for NIFTY_500 companies
3. THE API SHALL expose an endpoint to retrieve personalized Recommendations and Action_Plans
4. WHEN the API receives a request with invalid input, THE API SHALL return an HTTP 400 status code with a descriptive error message

### Requirement 10: Persist Data

**User Story:** As a system administrator, I want the system to persist data, so that holdings and analysis results survive restarts.

#### Acceptance Criteria

1. THE System SHALL persist user Holdings to a PostgreSQL database
2. THE System SHALL persist analysis results to a PostgreSQL database with a timestamp
3. WHEN a scheduled analysis run completes, THE System SHALL store the results with the run timestamp

### Requirement 11: Schedule Analysis Runs

**User Story:** As a system administrator, I want scheduled analysis runs, so that market data stays current.

#### Acceptance Criteria

1. THE System SHALL trigger a data fetch and analysis run every 12 hours
2. WHEN a scheduled run is triggered, THE System SHALL execute the fetch, analyze, and recommend pipeline in sequence

### Requirement 12: Compliance Disclaimer

**User Story:** As a user, I want clear disclaimers, so that I understand recommendations are educational only.

#### Acceptance Criteria

1. THE System SHALL include the Compliance_Disclaimer with all Recommendations
2. THE System SHALL include the Compliance_Disclaimer with all Action_Plans

### Requirement 13: Analysis Performance

**User Story:** As a system administrator, I want analysis to complete within a time bound, so that recommendations remain timely.

#### Acceptance Criteria

1. THE System SHALL complete a full analysis run for all 500 NIFTY_500 companies within 5 minutes
