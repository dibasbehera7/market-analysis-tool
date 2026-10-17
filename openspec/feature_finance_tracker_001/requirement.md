# Requirement.md — Automated Market Analysis Tool (Finalized)

## Purpose

Design and build an open-source MIT licensed enterprise-grade automation tool that fetches NIFTY 500 market data, analyzes companies, generates insights, and provides personalized action plans (buy/hold/sell/quantity) based on user holdings. Deliverable as web app, mobile app, or background job.

---

## Functional Requirements

### Data Fetching

- Scheduled job (cron/Airflow) every 12 hours.
- Fetch NIFTY 500 last close data via APIs (NSE, Yahoo Finance, Alpha Vantage, Zerodha Kite Connect).
- If market is active → fetch intraday live data.
- If market is closed → use end-of-day (EOD) close.
- Retry mechanism for API failures.

### Analysis Engine

- Compute metrics: P/E, P/B, ROE, EPS growth, NPA (banks).
- Detect trends: bullish/bearish, support/resistance.
- Generate company-level insights.

### User Holdings Integration

- Input holdings (company, quantity, buy price).
- Support multiple buy prices per stock (average cost basis).
- Allow daily investment amount for scalping/short-term profit analysis.
- Compare holdings against analysis.
- Generate personalized recommendations (buy/hold/sell/quantity).

### Action Plan Generation

- Summarize insights into actionable steps.
- Provide buy/sell ranges and target prices.
- Suggest portfolio rebalancing.

### Delivery Channels

- Web app (React/Next.js frontend, Node.js backend).
- Mobile app (React Native).
- Background job (Python/Go microservice).

### Notifications

- App notifications (free) + email alerts.
- Configurable thresholds (e.g., price drop >5%).
- Alerts are both informational (market updates) and action-oriented (buy/sell recommendations).
- Frequency:
  - Free users → 1 notification per day.
  - Premium users → every 12 hours.

### Open Source

- MIT License.
- Public GitHub repository.
- Documentation-first approach.

---

## Non-Functional Requirements

- **Scalability:** Handle 500 companies.
- **Performance:** Analysis completed within 5 minutes per run.
- **Security:** Encrypt user holdings, secure API keys.
- **Reliability:** Automated retries, fallback data.
- **Portability:** Deployable via Docker/Kubernetes.

---

## Subscription Model

### Free Tier

- Daily notifications.
- Basic analytics (EOD data).
- Holdings comparison.

### Premium Tier

- Notifications every 12 hours.
- Intraday alerts for major events (>5% move).
- Advanced analytics (trend detection, scalping analysis).
- Priority API usage.
- Billing: Flat fee ₹99/month via Stripe.

---

## Compliance Section

- **Disclaimer:** All alerts and recommendations must clearly state: “Insights only, not financial advice. Educational purpose only.”

---

## Architecture (C4 Model)

### Level 1: Context Diagram

- Users → interact via mobile/web app.
- System → fetches market data, analyzes, provides insights.
- External APIs → provide stock data.

### Level 2: Container Diagram

- Frontend: React/Next.js (web), React Native (mobile).
- Backend: Node.js/Express or Python FastAPI.
- Database: PostgreSQL (holdings, analysis results).
- Scheduler: Cron jobs / Airflow.
- External Services: NSE/Finance APIs, Zerodha Kite Connect.

### Level 3: Component Diagram

- Data Fetcher: API integration.
- Analyzer: Metrics computation, trend detection.
- Recommendation Engine: Action plan generation.
- User Module: Holdings input, portfolio comparison.
- Notification Module: Push/email alerts.
- Delivery Module: Web/mobile UI.

### Level 4: Code Diagram (MVP)

| File              | Responsibility                  |
|-------------------|--------------------------------|
| `fetcher.py`      | Fetch NIFTY 500 data.           |
| `analyzer.py`     | Compute metrics.                |
| `recommendation.py` | Generate buy/hold/sell.       |
| `user.py`         | Manage holdings.                |
| `notification.py` | Manage alerts.                  |
| `api.py`          | REST endpoints.                 |
| `ui/`             | React frontend.                 |

---

## Data Flow Diagram (DFD)

### Level 0 (High-Level)

```
[User] → [Frontend UI] → [Backend API] → [Data Fetcher] → [Market Data APIs]
                                      ↓
                               [Analyzer Engine]
                                      ↓
                             [Recommendation Engine]
                                      ↓
                               [Database + Holdings]
                                      ↓
                               [Frontend UI Output]
```

### Level 1 (Detailed Flow)

1. **User Input:** Holdings entered via web/mobile.
2. **Scheduler:** Triggers fetcher every 12 hours.
3. **Data Fetcher:**
   - If market active → fetch intraday snapshot.
   - If market closed → fetch EOD close.
4. **Analyzer:** Computes metrics, detects trends.
5. **Recommendation Engine:** Generates personalized buy/hold/sell.
6. **Database:** Stores holdings, analysis results.
7. **Frontend UI:** Displays insights, recommendations, action plan.

---

## Notification Flow Diagram

### Level 0 (High-Level)

```
[Recommendation Engine] → [Notification Module] → [Push Service / Email Service] → [User Device]
```

### Level 1 (Detailed Flow)

1. **Recommendation Engine:** Detects actionable event (e.g., price drop >5%).
2. **Notification Module:**
   - Formats message (informational + action-oriented).
   - Chooses delivery channel (push/email).
3. **Push Service:** Sends notification to mobile/web app.
4. **Email Service:** Sends email alert.
5. **User Device:** Receives notification.

---

## User Interaction Flow Diagram

### Level 0 (High-Level)

```
[User] → [Frontend UI] → [Holdings Module] → [Database]
                                      ↓
                               [Notification Preferences]
                                      ↓
                               [Recommendation Engine]
                                      ↓
                               [Alerts + Insights]
```

### Level 1 (Detailed Flow)

1. **User Configures Holdings:** Inputs company, quantity, buy price.
2. **User Sets Preferences:** Chooses thresholds (e.g., price drop %, target price).
3. **Database:** Stores holdings and preferences.
4. **Recommendation Engine:** Uses holdings + preferences to generate insights.
5. **Notification Module:** Delivers alerts (informational + action-oriented).
6. **Frontend UI:** Displays portfolio comparison, recommendations, and alerts.

---

## Testing Strategy

- **Isolated Unit Testing:** Fetcher, analyzer, recommendation engine.
- **Integration Testing:**
  - Zerodha Kite Connect sandbox (included in subscription).
  - GitHub Actions integration → mock fallback if invalid API key.
- **CI/CD:** Automated test suite in pipeline.

---

## Deployment Plan

- **CI/CD Pipeline:** GitHub Actions or GitLab CI.
- **Containerization:** Docker images.
- **Orchestration:** Kubernetes cluster sizing based on user load.

### Cluster Sizing Assumptions

| Phase      | Pods | Users     |
|------------|------|-----------|
| MVP        | 2    | 1–10      |
| Beta       | 3    | 10–10k    |
| Enterprise | 5–6  | 10k–1M    |

---

## Roadmap (Enterprise Release)

| Phase                       | Scope                                                                        |
|-----------------------------|------------------------------------------------------------------------------|
| Phase 1 (MVP)               | Core fetcher, analyzer, recommendation engine, holdings input.                |
| Phase 2 (Beta)              | Notifications, subscription model, Stripe integration.                       |
| Phase 3 (Enterprise Release)| Kubernetes deployment, premium analytics, enterprise marketing.               |

---

## License

MIT License — free to use, modify, and distribute.

---

## Deliverables

- Requirement.md (this document).
- C4 diagrams.
- Data Flow Diagram (DFD).
- Notification Flow Diagram.
- User Interaction Flow Diagram.
- Subscription & Compliance Section.
- MVP codebase.
- Deployment scripts.
- Documentation.
