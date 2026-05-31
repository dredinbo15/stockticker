"""
Stock Tracking and Modeling Application
Main entry point for the MVC-based Neo4j stock database system.
"""

import asyncio
import logging
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
from modules.modeling.xgboost_model import XGBoostModel
from config.database import init_neo4j
from config.tickers import get_all_ciks, get_all_symbols
import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Stock Tracker",
    description="Neo4j-based stock tracking and modeling system",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

try:
    init_neo4j()
    logger.info("Neo4j database initialized successfully")
except Exception as e:
    logger.warning("Could not connect to Neo4j: %s. Ensure Neo4j is running.", e)

stock_controller = StockController()
weather_module = WeatherModule()
forecast_generator = WeatherForecastGenerator()
news_module = NewsModule()
sec_module = SECForm4Module()
sec8k_module = SEC8KModule()
xgb_model = XGBoostModel()


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
            "/api/model/predict/{symbol}",
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
    cities = ["New York", "San Francisco", "London", "Tokyo"]
    asyncio.create_task(asyncio.to_thread(weather_module.collect_and_queue, cities))
    return CollectResponse(message="Weather data collection started", details={"cities": cities})


@app.post("/api/collect/weather/forecast", response_model=CollectResponse)
async def collect_weather_forecast(save: bool = False):
    cities = ["New York", "San Francisco", "London", "Tokyo"]
    forecasts = await asyncio.to_thread(forecast_generator.generate_5_day_forecast, cities)
    if save:
        for forecast in forecasts:
            await asyncio.to_thread(forecast.save)
    return CollectResponse(
        message="Weather forecast generation completed",
        details={
            "cities": cities,
            "forecasts_generated": len(forecasts),
            "saved": save,
        },
    )


@app.post("/api/collect/news", response_model=CollectResponse)
async def collect_news():
    queries = ["stocks", "finance", "market analysis"]
    asyncio.create_task(news_module.collect_and_process_news(queries))
    return CollectResponse(message="News collection and enrichment started", details={"queries": queries})


@app.post("/api/collect/sec", response_model=CollectResponse)
async def collect_sec_data():
    ciks = get_all_ciks()
    asyncio.create_task(asyncio.to_thread(sec_module.collect_and_queue, ciks))
    return CollectResponse(message="SEC Form 4 data collection started", details={"ciks_count": len(ciks)})


@app.post("/api/collect/sec8k", response_model=CollectResponse)
async def collect_sec_8k_data():
    ciks = get_all_ciks()
    asyncio.create_task(asyncio.to_thread(sec8k_module.collect_and_queue, ciks))
    return CollectResponse(message="SEC 8-K data collection started", details={"ciks_count": len(ciks)})


@app.post("/api/collect/prices", response_model=CollectResponse)
async def collect_stock_prices():
    symbols = get_all_symbols()
    price_fetcher = YFinancePriceFetcher()
    asyncio.create_task(asyncio.to_thread(price_fetcher.update_prices, symbols))
    return CollectResponse(message="Stock price collection started", details={"symbols_count": len(symbols)})


# --- XGBoost modeling routes ---

@app.post("/api/model/train", response_model=CollectResponse)
async def train_model():
    """Train (or retrain) the XGBoost insider-buy model in the background."""
    async def _train():
        metrics = await asyncio.to_thread(xgb_model.train_model)
        logger.info("XGBoost training complete: %s", metrics)

    asyncio.create_task(_train())
    return CollectResponse(
        message="XGBoost model training started",
        details={"feature_window_days": "31–90", "label_window_days": "0–30"},
    )


@app.get("/api/model/metrics")
async def get_model_metrics():
    """Return the metrics from the most recent training run."""
    if not xgb_model.metrics:
        raise HTTPException(status_code=404, detail="Model has not been trained yet. POST /api/model/train first.")
    return xgb_model.metrics


@app.get("/api/model/features")
async def get_feature_importances():
    """Return feature importances sorted descending."""
    if xgb_model.model is None:
        raise HTTPException(status_code=404, detail="Model has not been trained yet. POST /api/model/train first.")
    importances = await asyncio.to_thread(xgb_model.get_feature_importances)
    return importances.to_dict(orient="records")


@app.get("/api/model/predict/{symbol}")
async def predict_stock(symbol: str):
    """Return the insider-buy prediction (0 or 1) for a single stock symbol."""
    if xgb_model.model is None:
        raise HTTPException(status_code=404, detail="Model has not been trained yet. POST /api/model/train first.")
    result = await asyncio.to_thread(xgb_model.predict_stock, symbol.upper())
    if result is None:
        raise HTTPException(status_code=404, detail=f"Symbol '{symbol.upper()}' not found in model feature set.")
    return {"symbol": symbol.upper(), "insider_buy_signal": result, "signal_label": "buy" if result == 1 else "neutral"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
