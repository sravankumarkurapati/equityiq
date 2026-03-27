# EquityIQ — AI-Powered Stock Intelligence Platform

> Real-time stock research powered by 5 specialized AI agents, Facebook Prophet forecasting, and a full AWS cloud deployment.

**Live Demo:** https://d12l9wpsob12xr.cloudfront.net

**Built by:** Sravan Kumar Kurapati | MS Information Systems, Northeastern University
**Contact:** kurapati.sr@northeastern.edu | 857-427-7767

---

## What is EquityIQ?

EquityIQ is a production-grade, end-to-end AI stock intelligence platform that analyzes any publicly traded stock in under 90 seconds. It uses a multi-agent AI system where 5 specialized agents work in parallel — each an expert in a different domain — to produce a comprehensive research report with a clear **BUY / HOLD / SELL** verdict.

Every morning at 8:30 AM ET, the system automatically scans 50+ of the most active stocks from Yahoo Finance's real-time screeners, scores each one using a weighted algorithm, and surfaces the top 5 picks of the day — completely autonomously.

---

## Key Features

- **5-Agent AI Crew** — News, Financials, Sentiment, Predictor, and Critic agents run in parallel using CrewAI
- **7-Day Price Forecast** — Facebook Prophet ML model with confidence intervals, RSI, and MACD regressors
- **Real-Time Data** — Live stock prices, SEC filings, professional news sentiment, technical indicators
- **Daily Top 5 Picks** — Automated market screener runs every weekday at 8:30 AM ET via EC2 cron
- **On-Demand Analysis** — Search any NYSE/NASDAQ stock, ETF, or international ticker
- **30-Minute Cache** — DynamoDB-backed caching prevents redundant agent runs
- **Full Disclaimer** — Every report includes financial advice disclaimer

---

## System Architecture

```
User Browser
      ↓
AWS CloudFront (HTTPS CDN)
      ↓
AWS EC2 t2.micro
      ├── Nginx (reverse proxy, port 80)
      │     ├── /api/* → FastAPI (port 8000)
      │     └── /*     → Streamlit (port 8501)
      │
      ├── FastAPI Backend
      │     ├── POST /api/analyze/{ticker}  → triggers CrewAI crew
      │     ├── GET  /api/report/{ticker}   → cached report
      │     ├── GET  /api/top5             → daily picks
      │     ├── GET  /api/history          → past analyses
      │     └── POST /api/screener/run     → on-demand screener
      │
      ├── Streamlit Frontend
      │     ├── Home page   → Top 5 daily picks
      │     ├── Analyzer    → Stock deep dive
      │     └── History     → Past analyses
      │
      └── Docker Compose (3 containers)

CrewAI Multi-Agent System (runs inside FastAPI)
      ├── NewsAgent          → NewsAPI (100 req/day free)
      ├── FinancialsAgent    → yfinance + SEC EDGAR (free)
      ├── SentimentAgent     → Alpha Vantage (25 req/day free)
      ├── PredictorAgent     → Facebook Prophet (local CPU)
      └── CriticAgent        → Validates + produces final verdict

AWS Services
      ├── DynamoDB  → stores analysis reports + daily picks
      ├── S3        → stores report artifacts
      └── CloudFront → HTTPS CDN

Automated Scheduling
      └── EC2 cron (8:30 AM ET weekdays) → runs market screener
```

---

## Tech Stack — Deep Dive

### AI & Machine Learning

| Technology | Version | Role | Why chosen |
|---|---|---|---|
| CrewAI | 0.55.0 | Multi-agent orchestration | Role-based agents, hierarchical crews, built-in memory |
| Groq API | — | LLM inference | Free tier, Llama 3.3 70B, sub-second latency |
| Llama 3.3 70B | — | Language model | Best open-source model for financial reasoning |
| Facebook Prophet | 1.1.5 | Time-series forecasting | CPU-only, handles trend + seasonality, confidence intervals |
| pandas-ta | 0.3.14b | Technical indicators | RSI, MACD calculation for Prophet regressors |

**Prophet Architecture:**
- Trained on 2 years of daily OHLCV data per ticker
- Custom regressors: 14-day RSI (normalized) + MACD (normalized)
- Multiplicative seasonality mode for financial data
- Business-day frequency forecasting (skips weekends)
- Confidence intervals at 80% level
- Fit time: 2–5 seconds on CPU — no GPU required

**Agent Architecture (CrewAI):**
- Agents run in parallel using `ThreadPoolExecutor` (4 workers)
- 3-second stagger between agent starts to avoid Groq TPM limits
- CriticAgent runs sequentially after all 4 parallel agents complete
- Each agent: `temperature=0.1` for factual reasoning
- `max_iter=3` to prevent infinite loops

### Backend

| Technology | Version | Role |
|---|---|---|
| FastAPI | 0.111.0 | REST API framework |
| Uvicorn | 0.29.0 | ASGI server |
| Pydantic | 2.7.0 | Data validation + schemas |
| boto3 | 1.34.84 | AWS SDK (DynamoDB, S3) |
| python-dotenv | 1.0.1 | Environment management |
| tenacity | 8.2.3 | Retry logic for external APIs |
| slowapi | 0.1.9 | Rate limiting middleware |

**API Design:**
- Async endpoints with 180-second timeout for agent runs
- Two-level caching: RAM dict (instant) → DynamoDB (persistent)
- Background task pattern for long-running crew executions
- Structured JSON logging for CloudWatch

### Frontend

| Technology | Version | Role |
|---|---|---|
| Streamlit | 1.43.0 | Web UI framework |
| Plotly | 5.22.0 | Interactive forecast charts |
| requests | 2.32.2 | HTTP client for API calls |

**UI Features:**
- Custom dark theme via injected CSS
- Prophet forecast chart with confidence band (upper/lower bounds)
- Color-coded BUY/HOLD/SELL verdict badges
- Expandable agent detail sections
- History table with re-analyze buttons
- Top 5 picks cards with click-to-analyze

### Data Sources

| Source | API | Cost | Data fetched |
|---|---|---|---|
| Yahoo Finance | yfinance | Free | Price, P/E, EPS, analyst ratings, 2yr history |
| SEC EDGAR | Public REST | Free | 10-Q/10-K filings, Form 4 insider trades |
| NewsAPI | REST | Free (100/day) | Headlines + article previews, 7-day window |
| Alpha Vantage | REST | Free (25/day) | News sentiment scores, RSI, MACD |
| Yahoo Finance Screeners | REST | Free | Most active, day gainers, growth stocks |

### Infrastructure & DevOps

| Technology | Role |
|---|---|
| Docker | Containerization |
| Docker Compose | Multi-container orchestration |
| Nginx (Alpine) | Reverse proxy + WebSocket support |
| AWS EC2 t2.micro | Compute (free tier) |
| AWS CloudFront | HTTPS CDN (free tier) |
| AWS DynamoDB | NoSQL database (free forever) |
| AWS S3 | Object storage (free tier) |
| AWS ECR | Docker image registry |
| AWS IAM | Access control |
| GitHub Actions | CI/CD pipeline |
| EC2 cron | Scheduled screener (8:30 AM ET weekdays) |

**Docker Setup:**
- Multi-stage `Dockerfile.api` — builder stage (gcc/g++ for Prophet) + slim runtime
- Single-stage `Dockerfile.ui` — lightweight Streamlit image
- `docker-compose.yml` — local dev with volume mounts for hot reload
- `docker-compose.prod.yml` — production with ECR image pulls
- Nginx WebSocket proxying for Streamlit live updates

**DynamoDB Schema:**

Table `equityiq_analyses`:
- Partition key: `ticker` (String)
- Sort key: `timestamp` (ISO String)
- TTL: 7 days auto-expiry
- Attributes: `report_json`, `direction`, `confidence`

Table `equityiq_daily_picks`:
- Partition key: `date` (String YYYY-MM-DD)
- TTL: 48 hours auto-expiry
- Attributes: `picks_json`, `generated_at`

---

## Agent Details

### 1. NewsAgent
- **Tools:** NewsTool (NewsAPI)
- **Task:** Fetches last 7 days of news, identifies 3 most impactful stories, classifies sentiment (Positive/Negative/Neutral), flags risk events and positive catalysts
- **Output:** NEWS_SENTIMENT, KEY_STORIES, RISK_FLAGS, POSITIVE_CATALYSTS, SUMMARY

### 2. FinancialsAgent
- **Tools:** YFinanceTool + SECTool
- **Task:** Analyzes P/E ratio vs growth rate, revenue growth, profit margins, debt/equity, analyst consensus and price target upside, SEC filing recency, insider activity
- **Output:** FINANCIAL_HEALTH (STRONG/MODERATE/WEAK), VALUATION, KEY_METRICS, ANALYST_VIEW, SEC_SIGNALS

### 3. SentimentAgent
- **Tools:** AlphaVantageTool
- **Task:** Scores news sentiment from 50+ professional sources, interprets RSI (overbought/oversold), interprets MACD momentum, checks signal agreement
- **Output:** SENTIMENT_VERDICT, NEWS_SENTIMENT score, RSI_SIGNAL, MACD_SIGNAL, SIGNAL_AGREEMENT

### 4. PredictorAgent
- **Tools:** ProphetForecasterTool
- **Task:** Runs 7-day Prophet forecast, interprets confidence score, assesses daily price trajectory, aligns with recent momentum
- **Output:** PRICE_OUTLOOK, CURRENT_PRICE, PREDICTED_PRICE_7D, DAILY_TARGETS, CONFIDENCE, MOMENTUM

### 5. CriticAgent
- **Tools:** None (reflection agent)
- **Task:** Reads all 4 agent outputs, identifies signal agreements and conflicts, weighs evidence, assigns confidence score, produces BUY/HOLD/SELL verdict with bull/bear cases
- **Output:** FINAL_VERDICT, CONFIDENCE_SCORE, SIGNAL_ALIGNMENT, BULL_CASE, BEAR_CASE, KEY_RISKS, EXECUTIVE_SUMMARY

---

## Daily Screener Algorithm

Scoring system (100 points max):

| Signal | Points | Criteria |
|---|---|---|
| Analyst recommendation | 40 | Strong Buy=40, Buy=30, Hold=10 |
| Upside to price target | 30 | >20%=30, >10%=20, >5%=10 |
| Prophet direction | 20 | BULLISH=20, NEUTRAL=5, BEARISH=0 |
| Forecast confidence | 10 | >90%=10, >80%=7, >70%=5 |

Data sources: Yahoo Finance most active + day gainers + growth technology + undervalued large caps screeners — fetched fresh every morning, no hardcoded ticker list.

---

## Local Development Setup

```bash
# Clone
git clone https://github.com/sravankumarkurapati/equityiq.git
cd equityiq

# Environment
cp .env.example .env
# Fill in: GROQ_API_KEY, NEWS_API_KEY, ALPHA_VANTAGE_KEY, AWS keys

# Python setup
python3.11 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
pip install -r frontend/requirements.txt

# Run with Docker
docker-compose up --build

# Or run directly
uvicorn backend.api.main:app --port 8000 --reload  # Terminal 1
streamlit run frontend/app.py                       # Terminal 2
```

**Access:**
- Streamlit UI: http://localhost:8501
- FastAPI docs: http://localhost:8000/docs
- Full stack via Nginx: http://localhost:80

---

## API Reference

| Method | Endpoint | Description | Response time |
|---|---|---|---|
| POST | `/api/analyze/{ticker}` | Full 5-agent analysis | 60-90s (fresh), instant (cached) |
| GET | `/api/report/{ticker}` | Latest cached report | Instant |
| GET | `/api/top5` | Today's top 5 picks | Instant |
| GET | `/api/history` | Last 20 analyses | Instant |
| POST | `/api/screener/run` | Run screener on demand | 5-8 minutes |
| GET | `/health` | Health check | Instant |

Full interactive docs: https://d12l9wpsob12xr.cloudfront.net/api/docs

---

## Project Structure

```
equityiq/
├── backend/
│   ├── agents/          # 5 CrewAI agent definitions
│   ├── api/             # FastAPI routes + schemas + cache
│   ├── crew/            # Crew orchestrator + report writer
│   ├── db/              # DynamoDB client
│   ├── ml/              # Prophet forecaster + market screener
│   └── tools/           # yfinance, SEC, News, Alpha Vantage tools
├── frontend/
│   ├── app.py           # Main entry + navigation + CSS
│   ├── page_views/      # Home, Deep Dive, History pages
│   └── components/      # Forecast chart + report cards
├── nginx/               # Dev + prod Nginx configs
├── lambda/              # AWS Lambda screener handler
├── .github/workflows/   # GitHub Actions CI/CD
├── Dockerfile.api       # Multi-stage FastAPI image
├── Dockerfile.ui        # Streamlit image
├── docker-compose.yml   # Local development
└── docker-compose.prod.yml  # EC2 production
```

---

## Disclaimer

EquityIQ is for **informational and educational purposes only**. Nothing on this platform constitutes financial advice. All analysis is generated by AI models which can make errors. Always consult a licensed financial advisor before making investment decisions. Past performance is not indicative of future results.

---

*Built by Sravan Kumar Kurapati — MS Information Systems, Northeastern University*
*kurapati.sr@northeastern.edu | 857-427-7767*