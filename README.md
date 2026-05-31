# Stock Tracking and Modeling System

A multi-source data engineering platform that takes news, SEC filings, weather, and price data into a Neo4j graph, enriches news with LLM-based analysis, and trains a XGBoost models on resulting feature set. Built to explore the data engineering and ML modeling stack used by quant firms.

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

4. **Configure credentials (encrypted)**:

The application uses encrypted credential storage for enhanced security. You have two options:

**Option A: Encrypt from environment variables**
```bash
# First, set your credentials in .env or environment
export NEO4J_PASSWORD=your_password
export OPENAI_API_KEY=your_key
# ... (set all required credentials)

# Then encrypt them
python credentials_cli.py encrypt-env
```

**Option B: Manually encrypt each credential**
```bash
python credentials_cli.py encrypt NEO4J_PASSWORD your_password
python credentials_cli.py encrypt OPENAI_API_KEY your_key
# ... (repeat for each credential)
```

**Required encrypted credentials**:
- `NEO4J_URI` (default: `bolt://localhost:7687`)
- `NEO4J_USER` (default: `neo4j`)
- `NEO4J_PASSWORD` (required)
- `OPENAI_API_KEY` (required for LLM enrichment)
- `NEWS_API_KEY` (required for news collection)
- `OPENWEATHER_API_KEY` (required for weather collection)
- `REDIS_URL` (default: `redis://localhost:6379/0`)
- `SEC_USER_AGENT` (optional, for SEC API calls)

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

## Credential Management

The application uses Fernet symmetric encryption to securely store credentials.

### How It Works

1. **Encryption Key**: Generated and stored in `.credentials_key` (automatically created on first use)
2. **Encrypted Credentials**: Stored in `.encrypted_credentials.json`
3. **Fallback**: If encrypted credentials are not found, the system will check environment variables

### Credential CLI Commands

```bash
# Encrypt all credentials from environment variables
python credentials_cli.py encrypt-env

# Encrypt a single credential
python credentials_cli.py encrypt KEY value

# Decrypt and display a credential (for verification)
python credentials_cli.py decrypt KEY

# List all encrypted credential keys
python credentials_cli.py list

# Show encryption key location
python credentials_cli.py show-key
```

### Security Best Practices

⚠️ **IMPORTANT**: Keep `.credentials_key` safe and secret!
- Add `.credentials_key` and `.encrypted_credentials.json` to `.gitignore` (already included)
- Never commit these files to version control
- Store the `.credentials_key` in a secure location (e.g., key management system, vault)
- Rotate credentials regularly
- Use different credentials for different environments (dev, staging, prod)

### Deployment Considerations

For production deployments:
1. Generate and securely store the `.credentials_key` on the deployment server
2. Set encrypted credentials via environment variables during deployment
3. Use a secrets management system (AWS Secrets Manager, HashiCorp Vault, etc.)
4. Implement key rotation policies

## Database Schema

- **Stock**: Basic stock information
- **WeatherData**: Weather conditions with timestamps
- **NewsArticle**: News with sentiment and enrichment
- **Company**: SEC-registered companies
- **Insider**: Company insiders
- **Transaction**: Form 4 transactions

## Development

Each module is self-contained and can be developed independently. The queue system ensures data processing doesn't block the main application.