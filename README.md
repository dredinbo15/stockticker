# Stock Tracking and Modeling System

A multi-source data engineering platform that ingests news, SEC filings, weather, and price data into a Neo4j graph, enriches news with LLM-based analysis, and trains an XGBoost model on resulting feature set. Built to explore the data engineering and ML modeling stack used by quant firms.

## Architecture

### MVC Pattern
- **Models**: Neo4j database operations (Stock, WeatherData, NewsArticle, SECForm4)
- **Views**: Web interface templates
- **Controllers**: Business logic handlers

### Modules
- **Weather Module**: Collects weather data for correlation analysis
- **News Module**: Fetches news articles with LLM enrichment
- **SEC Form 4 Module**: Processes insider trading data
- **SEC 8-k module**: Process 8-ks
- **Pricing**: Pulls pricing info for stocks
- **LLM Enrichment**: Uses OpenAI for sentiment analysis and content enrichment
- **Modelling**: models futures for stocks

### Queue System
- Uses Celery with Redis for asynchronous data processing
- Separate queues for each data type

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

## Setup

1. **Install Neo4j**: Download and install Neo4j Desktop or Server from https://neo4j.com/download/

2. **Start Neo4j**: Start your Neo4j instance (default: localhost:7687)

3. **Install Python dependencies**:
```bash
pip install -r requirements.txt
```

4. **Configure credentials**: Copy `.env.example` to `.env` and fill in your credentials:
```bash
cp .env.example .env

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

4. Run the Streamlit dashboard:
```bash
streamlit run streamlit_app.py
```

5. Access the API at `http://localhost:8000`

## API Endpoints

- `GET /`: API information
- `GET /stocks`: List all stocks
- `POST /api/collect/weather`: Trigger weather data collection
- `POST /api/collect/news`: Trigger news collection and enrichment
- `POST /api/collect/sec`: Trigger SEC Form 4 data collection

## Database Schema

- **Stock**: Basic stock information
- **WeatherData**: Weather conditions with timestamps
- **NewsArticle**: News with sentiment and enrichment
- **Company**: SEC-registered companies
- **Insider**: Company insiders
- **Transaction**: Form 4 transactions

## Development

Each module is self-contained and can be developed independently. The queue system ensures data processing doesn't block the main application.
