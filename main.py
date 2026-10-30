"""
Stock Tracking and Modeling Application
Main entry point for the MVC-based Neo4j stock database system.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from jinja2 import Template
from pydantic import BaseModel, ConfigDict, Field

from controllers.stock_controller import StockController
from modules.weather.weather_collector import WeatherModule
from modules.news.news_collector import NewsModule
from modules.sec_form4.sec_collector import SECForm4Module
from modules.sec_8k.sec8k_collector import SEC8KModule
from modules.pricing.yfinance_price import YFinancePriceFetcher
from modules.weather.weather_forecast import WeatherForecastGenerator
from modules.modeling.xgboost_model import HORIZON_DAYS, XGBoostModel
from modules.analysis.weather_correlation import WeatherCorrelationAnalyzer
from config.database import init_neo4j, neo4j_conn
from config.tickers import get_all_ciks, get_all_symbols
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

WEATHER_CITIES = ["New York", "San Francisco", "London", "Tokyo"]
VALID_PRICE_PERIODS = {"5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "max"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await asyncio.to_thread(init_neo4j)
        logger.info("Neo4j database initialized successfully")
    except Exception as e:
        logger.warning("Could not connect to Neo4j: %s. Ensure Neo4j is running.", e)
    yield
    neo4j_conn.close()


app = FastAPI(
    title="Stock Tracker",
    description="Neo4j-based stock tracking and modeling system",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

stock_controller = StockController()
weather_module = WeatherModule()
forecast_generator = WeatherForecastGenerator()
news_module = NewsModule()
sec_module = SECForm4Module()
sec8k_module = SEC8KModule()
xgb_model = XGBoostModel()
weather_analyzer = WeatherCorrelationAnalyzer()

# asyncio only keeps weak references to tasks, so hold them until they finish.
_background_tasks = set()


def run_in_background(func, *args, **kwargs):
    async def runner():
        try:
            await asyncio.to_thread(func, *args, **kwargs)
        except Exception:
            logger.exception("Background job %s failed", getattr(func, "__name__", func))

    task = asyncio.create_task(runner())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


def require_trained_model():
    xgb_model.reload_if_changed()
    if xgb_model.model is None:
        raise HTTPException(status_code=404, detail="Model has not been trained yet. POST /api/model/train first.")


# --- Pydantic schemas ---

class StockCreate(BaseModel):
    symbol: str
    name: Optional[str] = None
    sector: Optional[str] = None


class StockResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    symbol: str
    name: Optional[str] = None
    sector: Optional[str] = None
    price: Optional[float] = None
    price_timestamp: Optional[str] = None


class CollectResponse(BaseModel):
    message: str
    details: dict = Field(default_factory=dict)


# --- Routes ---

@app.get("/")
async def root():
    return {
        "message": "Stock Tracking API",
        "endpoints": [
            "/dashboard",
            "/stocks",
            "/api/collect/weather",
            "/api/collect/weather/forecast",
            "/api/collect/news",
            "/api/collect/sec",
            "/api/collect/sec8k",
            "/api/collect/prices",
            "/api/model/train",
            "/api/model/metrics",
            "/api/model/features",
            "/api/model/predictions",
            "/api/model/predict/{symbol}",
            "/api/analysis/weather-correlation",
        ],
    }


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    from views.templates import dashboard_template
    return dashboard_template


@app.get("/stocks/view", response_class=HTMLResponse)
async def stocks_view(
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
):
    from views.templates import stock_list_template
    stocks = await stock_controller.get_all_stocks(limit=limit, skip=skip)
    return Template(stock_list_template).render(stocks=stocks)


@app.get("/stocks", response_model=List[StockResponse])
async def get_stocks(
    limit: int = Query(100, ge=1, le=1000),
    skip: int = Query(0, ge=0),
):
    return await stock_controller.get_all_stocks(limit=limit, skip=skip)


@app.get("/api/stocks/{symbol}", response_model=StockResponse)
async def get_stock(symbol: str):
    stock = await stock_controller.get_stock(symbol.upper())
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol}' not found")
    return stock


@app.post("/api/stocks", response_model=StockResponse, status_code=201)
async def create_stock(payload: StockCreate):
    return await stock_controller.create_stock(
        symbol=payload.symbol.upper(),
        name=payload.name,
        sector=payload.sector,
    )


@app.post("/api/collect/weather", response_model=CollectResponse)
async def collect_weather():
    run_in_background(weather_module.collect_and_queue, WEATHER_CITIES)
    return CollectResponse(message="Weather data collection started", details={"cities": WEATHER_CITIES})


@app.post("/api/collect/weather/forecast", response_model=CollectResponse)
async def collect_weather_forecast(save: bool = False):
    forecasts = await asyncio.to_thread(forecast_generator.generate_5_day_forecast, WEATHER_CITIES)
    if save:
        for forecast in forecasts:
            await asyncio.to_thread(forecast.save)
    return CollectResponse(
        message="Weather forecast generation completed",
        details={
            "cities": WEATHER_CITIES,
            "forecasts_generated": len(forecasts),
            "saved": save,
        },
    )


@app.post("/api/collect/news", response_model=CollectResponse)
async def collect_news(page_size: int = Query(5, ge=1, le=100)):
    symbols = get_all_symbols()
    run_in_background(news_module.collect_for_symbols, symbols, page_size)
    return CollectResponse(
        message="Per-ticker news collection and enrichment started",
        details={"symbols_count": len(symbols), "page_size": page_size},
    )


@app.post("/api/collect/sec", response_model=CollectResponse)
async def collect_sec_data():
    ciks = get_all_ciks()
    run_in_background(sec_module.collect_and_queue, ciks)
    return CollectResponse(message="SEC Form 4 data collection started", details={"ciks_count": len(ciks)})


@app.post("/api/collect/sec8k", response_model=CollectResponse)
async def collect_sec_8k_data():
    ciks = get_all_ciks()
    run_in_background(sec8k_module.collect_and_queue, ciks)
    return CollectResponse(message="SEC 8-K data collection started", details={"ciks_count": len(ciks)})


@app.post("/api/collect/prices", response_model=CollectResponse)
async def collect_stock_prices(period: str = Query("5d", description="History to fetch, e.g. 5d, 1mo, 1y, 2y")):
    if period not in VALID_PRICE_PERIODS:
        raise HTTPException(status_code=422, detail=f"period must be one of {sorted(VALID_PRICE_PERIODS)}")
    symbols = get_all_symbols()
    price_fetcher = YFinancePriceFetcher()
    run_in_background(price_fetcher.update_price_history, symbols, period)
    return CollectResponse(
        message="Stock price history collection started",
        details={"symbols_count": len(symbols), "period": period},
    )


# --- XGBoost modeling routes ---

@app.post("/api/model/train", response_model=CollectResponse)
async def train_model():
    """Train (or retrain) the XGBoost model in the background."""
    def _train():
        metrics = xgb_model.train_model()
        logger.info(
            "XGBoost training complete: %s",
            {k: v for k, v in metrics.items() if k != "classification_report"},
        )

    run_in_background(_train)
    return CollectResponse(
        message="XGBoost model training started",
        details={
            "target": f"beats cross-sectional median {HORIZON_DAYS}-day forward return",
            "split": "time-ordered, last 20% of days held out",
        },
    )


@app.get("/api/model/metrics")
async def get_model_metrics():
    """Return the metrics from the most recent training run."""
    xgb_model.reload_if_changed()
    if not xgb_model.metrics:
        raise HTTPException(status_code=404, detail="Model has not been trained yet. POST /api/model/train first.")
    return xgb_model.metrics


@app.get("/api/model/features")
async def get_feature_importances():
    """Return feature importances sorted descending."""
    require_trained_model()
    importances = await asyncio.to_thread(xgb_model.get_feature_importances)
    return importances.to_dict(orient="records")


@app.get("/api/model/predictions")
async def get_predictions():
    """Latest outperformance probability for every tracked stock."""
    require_trained_model()
    predictions = await asyncio.to_thread(xgb_model.predict_all)
    return predictions.to_dict(orient="records")


@app.get("/api/model/predict/{symbol}")
async def predict_stock(symbol: str):
    """Probability that a stock beats the median over the next HORIZON_DAYS trading days."""
    require_trained_model()
    result = await asyncio.to_thread(xgb_model.predict_stock, symbol.upper())
    if result is None:
        raise HTTPException(status_code=404, detail=f"Symbol '{symbol.upper()}' not found in model feature set.")
    result["signal_label"] = "outperform" if result["signal"] == 1 else "underperform"
    result["horizon_days"] = HORIZON_DAYS
    return result


# --- Analysis routes ---

@app.get("/api/analysis/weather-correlation")
async def weather_correlation(
    days: int = Query(180, ge=14, le=1825),
    min_days: int = Query(10, ge=3),
    limit: int = Query(25, ge=1, le=500),
):
    """Correlation between city weather and daily sector returns, strongest first."""
    results = await asyncio.to_thread(weather_analyzer.run, days, min_days)
    return {"days": days, "min_days": min_days, "results": results[:limit]}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
