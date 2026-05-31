"""
Celery tasks for processing queued data.
"""

import asyncio
from datetime import datetime
from queues.celery_app import app
from models.weather import WeatherData
from models.news import NewsArticle
from models.sec_form4 import SECForm4
from models.sec_8k import SEC8K
from modules.llm_enrichment.llm_processor import LLMProcessor


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

    enriched_data = asyncio.run(LLMProcessor().enrich_news(news_article))
    news_article.sentiment = enriched_data.get('sentiment')
    news_article.enriched_content = enriched_data.get('enriched_content')
    news_article.related_stocks = enriched_data.get('related_stocks', [])
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
    )
    form4_data.save()
    return f"Saved SEC Form 4 for {form4_dict['issuer_name']}"
