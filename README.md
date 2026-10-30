# Stock Tracking and Modeling System

A multi-source data engineering platform that ingests news, SEC filings, weather, and price data into a Neo4j graph, enriches news and 8-K filings with LLM-based analysis, and trains an XGBoost model on the resulting feature set. Built to explore the data engineering and ML modeling stack used by quant firms.

## Architecture

### MVC Pattern
- **Models**: Neo4j database operations (Stock, PricePoint, WeatherData, NewsArticle, SECForm4, SEC8K)
- **Views**: Web interface templates
- **Controllers**: Business logic handlers

### Modules
- **Weather Module**: Collects current observations and the OpenWeather 5-day forecast (with season/state bias adjustments)
- **News Module**: Fetches news per tracked ticker from NewsAPI, then enriches it with an LLM
- **SEC Form 4 Module**: Processes insider trading data
- **SEC 8-K Module**: Processes 8-K event filings
- **Pricing**: Stores daily OHLCV price history from Yahoo Finance
- **LLM Enrichment**: Uses OpenAI for sentiment, ticker tagging, and summaries
- **Modelling**: Trains an XGBoost model to predict which stocks will beat the median over the next 5 trading days
- **Analysis**: Correlates city weather with daily sector returns

SEC requests share one throttled client (`modules/sec_client.py`) that stays under SEC's 10 requests/second limit.

### Queue System
- Uses Celery with Redis for asynchronous data processing
- Separate tasks for each data type
- Celery beat runs every collector and model training on a schedule (`queues/celery_app.py`)

| Job | Schedule (UTC) |
|-----|----------------|
| Weather observations | every 3 hours |
| News (per ticker) | daily 12:15 |
| Price history | weekdays 22:30 |
| SEC Form 4 | weekdays 23:45 |
| SEC 8-K | Tue–Sat 00:15 |
| Model training | Tue–Sat 02:00 |

## Model

One row per stock per trading day. Features use only data available at that day's close:

| Group | Features |
|-------|----------|
| Price | 1/5/20-day return, 20-day volatility, volume vs 20-day average, distance from 20-day moving average |
| News | article count and mean sentiment over the prior 7 days |
| Insider (Form 4) | open-market buys (`P`) and sales (`S`) over the prior 30 days, dated by filing date |
| 8-K | filings over the prior 30 days |
| Sector | ordinal-encoded |

**Target:** 1 if the stock's next-5-day return beats the median of all tracked stocks that day. This keeps the classes balanced and the label market-neutral.

**Evaluation:** the last 20% of trading days are held out as a test set, with a 5-day gap so no training label overlaps it. Metrics include accuracy, ROC AUC, and the majority-class baseline to compare against.

The trained model is saved to `MODEL_PATH` (default `artifacts/xgb_model.joblib`). The API and Streamlit load that file and pick up retrains automatically.

News and insider features only exist from when you start collecting (NewsAPI's free tier returns about one month of history), so early training runs rely mainly on price features.

## Tracked Tickers (50 Major US Companies)

The system monitors 50 major US stocks across 12 sectors:

**Information Technology (5)**: AAPL, MSFT, NVDA, AVGO, CSCO

**Communication Services (4)**: GOOGL, META, NFLX, DIS

**Consumer Discretionary (5)**: AMZN, TSLA, HD, NKE, MCD

**Consumer Staples (4)**: WMT, PG, KO, COST

**Financials (5)**: JPM, BAC, GS, V, MA

**Healthcare (5)**: JNJ, UNH, LLY, PFE, ABBV

**Industrials (5)**: CAT, BA, GE, UPS, RTX

**Energy (4)**: XOM, CVX, COP, SLB

**Materials (3)**: LIN, FCX, NEM

**Utilities (3)**: NEE, DUK, SO

**Real Estate (3)**: PLD, AMT, EQIX

**Transportation/Rails (4)**: UNP, CSX, NSC, FDX

All tickers are defined in [config/tickers.py](config/tickers.py) with their SEC CIK mappings for efficient data retrieval.

## Quick Start (Docker)

```bash
cp .env.example .env   # set NEO4J_PASSWORD and API keys
docker compose up --build
```

This starts Neo4j, Redis, the API (port 8000), a Celery worker, Celery beat, and Streamlit (port 8501). Then backfill price history once and train:

```bash
curl -X POST "http://localhost:8000/api/collect/prices?period=2y"
curl -X POST http://localhost:8000/api/collect/sec
curl -X POST http://localhost:8000/api/model/train
```

## Manual Setup

Requires Python 3.11–3.13.

1. **Install Neo4j**: Download and install Neo4j Desktop or Server from https://neo4j.com/download/

2. **Start Neo4j**: Start your Neo4j instance (default: localhost:7687)

3. **Install Python dependencies**:
```bash
pip install -r requirements.txt
```

4. **Configure environment variables**: Copy `.env.example` to `.env` and fill in your values:
```bash
cp .env.example .env
```

5. **Install and start Redis** (for queue system):
```bash
# Using Docker
docker run -d -p 6379:6379 redis:alpine

# Or install Redis locally
```

## Running the Application

1. Start the web server:
```bash
python main.py
```

2. Start the Celery worker:
```bash
celery -A queues.celery_app worker --loglevel=info
```

3. Start the Celery beat scheduler:
```bash
celery -A queues.celery_app beat --loglevel=info
```

4. Run the Streamlit dashboard:
```bash
streamlit run streamlit_app.py
```

5. Access the API at `http://localhost:8000`

6. Backfill two years of prices once (later runs only need the last few days):
```bash
curl -X POST "http://localhost:8000/api/collect/prices?period=2y"
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests use synthetic data and mocked HTTP calls, so they don't need Neo4j, Redis, or API keys.

## API Endpoints

- `GET /`: API information
- `GET /stocks`: List all stocks
- `POST /api/collect/weather`: Trigger weather data collection
- `POST /api/collect/weather/forecast`: Generate a 5-day weather forecast
- `POST /api/collect/news?page_size=5`: Trigger per-ticker news collection and enrichment
- `POST /api/collect/sec`: Trigger SEC Form 4 data collection
- `POST /api/collect/sec8k`: Trigger SEC 8-K data collection
- `POST /api/collect/prices?period=5d`: Store daily price history (`period`: 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max)
- `POST /api/model/train`: Train (or retrain) the XGBoost model
- `GET /api/model/metrics`: Latest training metrics
- `GET /api/model/features`: Feature importances
- `GET /api/model/predictions`: Latest outperformance probability for every stock
- `GET /api/model/predict/{symbol}`: Outperformance probability for one symbol
- `GET /api/analysis/weather-correlation?days=180`: Weather vs sector-return correlations

## Database Schema

- **Stock**: Symbol, name, sector, latest price
- **PricePoint**: Daily OHLCV bar, `(Stock)-[:HAS_PRICE]->(PricePoint)`
- **WeatherData**: Weather observations and forecasts with timestamps
- **NewsArticle**: News with sentiment and enrichment, `(NewsArticle)-[:MENTIONS]->(Stock)`
- **Company**: SEC-registered companies
- **Insider**: Company insiders
- **Transaction**: Form 4 transactions (trade date and filing date)
- **EightKReport**: 8-K filings with LLM summary

## Development

Each module is self-contained and can be developed independently. The queue system ensures data processing doesn't block the main application.
