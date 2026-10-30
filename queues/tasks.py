"""
Celery tasks for processing queued data.
"""

import asyncio
import logging
from datetime import datetime
from queues.celery_app import app
from config.tickers import normalize_symbols
from models.weather import WeatherData
from models.news import NewsArticle
from models.sec_form4 import SECForm4
from models.sec_8k import SEC8K
from modules.llm_enrichment.llm_processor import LLMProcessor

logger = logging.getLogger(__name__)


@app.task
def save_weather_data(weather_dict):
    weather_data = WeatherData(
        location=weather_dict['location'],
        temperature=weather_dict['temperature'],
        humidity=weather_dict['humidity'],
        conditions=weather_dict['conditions'],
        timestamp=datetime.fromisoformat(weather_dict['timestamp']) if weather_dict.get('timestamp') else None,
        confidence=weather_dict.get('confidence'),
    )
    weather_data.save()
    return f"Saved weather data for {weather_dict['location']}"


@app.task
def process_raw_news_article(news_dict):
    news_article = NewsArticle(
        title=news_dict['title'],
        content=news_dict['content'],
        source=news_dict['source'],
        url=news_dict.get('url'),
        published_date=datetime.fromisoformat(news_dict['published_date']),
        article_hash=news_dict.get('article_hash'),
    )
    if NewsArticle.is_enriched(news_article.article_hash):
        return f"Skipped already-enriched article: {news_article.title}"

    enriched_data = asyncio.run(LLMProcessor().enrich_news(news_article))
    news_article.sentiment = enriched_data.get('sentiment')
    news_article.enriched_content = enriched_data.get('enriched_content')
    # Keep the ticker the article was collected for, plus any the LLM found.
    news_article.related_stocks = normalize_symbols(
        list(news_dict.get('related_stocks') or []) + list(enriched_data.get('related_stocks') or [])
    )
    news_article.save()
    return f"Processed raw news article: {news_article.title}"


@app.task
def process_raw_sec_8k_report(report_dict):
    report = SEC8K(
        issuer_cik=report_dict['issuer_cik'],
        issuer_name=report_dict['issuer_name'],
        filing_date=datetime.fromisoformat(report_dict['filing_date']),
        description=report_dict['description'],
        content=report_dict['content'],
        item_summary=report_dict.get('item_summary'),
        form_url=report_dict.get('form_url'),
        report_hash=report_dict.get('report_hash'),
    )

    enriched_data = asyncio.run(LLMProcessor().enrich_8k_report(report))
    report.llm_summary = enriched_data.get('llm_summary')
    report.key_items = enriched_data.get('key_items')
    report.impact_assessment = enriched_data.get('impact_assessment')
    report.save()
    return f"Processed SEC 8-K report for {report.issuer_name}"


@app.task
def save_sec_form4(form4_dict):
    form4_data = SECForm4(
        issuer_cik=form4_dict['issuer_cik'],
        issuer_name=form4_dict['issuer_name'],
        reporter_cik=form4_dict['reporter_cik'],
        reporter_name=form4_dict['reporter_name'],
        transaction_date=datetime.fromisoformat(form4_dict['transaction_date']),
        transaction_code=form4_dict['transaction_code'],
        shares=form4_dict['shares'],
        price=form4_dict.get('price'),
        security_title=form4_dict.get('security_title'),
        transaction_type=form4_dict.get('transaction_type'),
        ownership_nature=form4_dict.get('ownership_nature'),
        form_url=form4_dict.get('form_url'),
        filing_date=datetime.fromisoformat(form4_dict['filing_date']) if form4_dict.get('filing_date') else None,
    )
    form4_data.save()
    return f"Saved SEC Form 4 for {form4_dict['issuer_name']}"


# --- Scheduled collection jobs (see beat_schedule in celery_app) ---
# Collectors are imported inside each task: they import the queue wrappers,
# which import this module, so a top-level import would be circular.

WEATHER_CITIES = ["New York", "San Francisco", "London", "Tokyo"]


@app.task
def collect_weather_job():
    from modules.weather.weather_collector import WeatherModule
    WeatherModule().collect_and_queue(WEATHER_CITIES)
    return f"Queued weather for {len(WEATHER_CITIES)} cities"


@app.task
def collect_news_job():
    from modules.news.news_collector import NewsModule
    NewsModule().collect_for_symbols()
    return "Queued per-ticker news"


@app.task
def collect_sec_form4_job():
    from config.tickers import get_all_ciks
    from modules.sec_form4.sec_collector import SECForm4Module
    SECForm4Module().collect_and_queue(get_all_ciks())
    return "Queued SEC Form 4 filings"


@app.task
def collect_sec_8k_job():
    from config.tickers import get_all_ciks
    from modules.sec_8k.sec8k_collector import SEC8KModule
    SEC8KModule().collect_and_queue(get_all_ciks())
    return "Queued SEC 8-K filings"


@app.task
def collect_prices_job(period: str = "5d"):
    from modules.pricing.yfinance_price import YFinancePriceFetcher
    saved = YFinancePriceFetcher().update_price_history(period=period)
    return f"Saved price history for {len(saved)} symbols"


@app.task
def train_model_job():
    from modules.modeling.xgboost_model import XGBoostModel
    metrics = XGBoostModel(autoload=False).train_model()
    logger.info("Scheduled XGBoost training finished: %s", {k: v for k, v in metrics.items() if k != "classification_report"})
    return metrics.get("error") or f"accuracy={metrics.get('accuracy')} roc_auc={metrics.get('roc_auc')}"

