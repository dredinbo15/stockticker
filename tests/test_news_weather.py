from datetime import datetime, timezone

import numpy as np

from modules.analysis.weather_correlation import compute_correlations
from modules.news.news_collector import NewsModule, build_symbol_query
from modules.weather.weather_forecast import aggregate_daily


def test_build_symbol_query_uses_company_name():
    assert build_symbol_query("V") == '"Visa" AND (stock OR shares OR earnings)'


def test_process_news_article_tags_symbol_and_keeps_description():
    article = NewsModule().process_news_article({
        "title": "Visa beats",
        "description": "Visa reported strong volumes.",
        "content": "Visa Inc said... [+1200 chars]",
        "source": {"name": "Reuters"},
        "url": "https://example.com/v",
        "publishedAt": "2026-10-29T12:00:00Z",
    }, symbol="V")
    assert article.related_stocks == ["V"]
    assert article.content.startswith("Visa reported strong volumes.")
    assert "[+1200 chars]" in article.content


def _step(ts, temp, hum, desc):
    return {"dt": int(ts.timestamp()), "main": {"temp": temp, "humidity": hum}, "weather": [{"description": desc}]}


def test_aggregate_daily_forecast():
    now = datetime(2026, 10, 30, 15, tzinfo=timezone.utc)
    forecast = {"list": [
        _step(datetime(2026, 10, 30, 18, tzinfo=timezone.utc), 99, 99, "today"),  # same day: excluded
        _step(datetime(2026, 10, 31, 0, tzinfo=timezone.utc), 10, 50, "rain"),
        _step(datetime(2026, 10, 31, 12, tzinfo=timezone.utc), 20, 70, "rain"),
        _step(datetime(2026, 10, 31, 18, tzinfo=timezone.utc), 15, 60, "clear"),
        _step(datetime(2026, 11, 2, 12, tzinfo=timezone.utc), 5, 40, "snow"),
    ]}
    days = aggregate_daily(forecast, now=now)
    assert [d["day_out"] for d in days] == [1, 3]
    assert days[0]["temperature"] == 15.0
    assert days[0]["humidity"] == 60.0
    assert days[0]["conditions"] == "rain"


def test_compute_correlations_detects_relationship():
    rng = np.random.default_rng(0)
    dates = [f"2026-09-{d:02d}" for d in range(1, 31)]
    temps = rng.normal(20, 5, len(dates))
    price_rows, weather_rows = [], []
    aapl, xom = 100.0, 100.0
    for date, temp in zip(dates, temps):
        aapl *= 1 + (temp - 20) / 500  # tech returns track temperature
        xom *= 1 + rng.normal(0, 0.01)
        price_rows += [{"symbol": "AAPL", "date": date, "close": aapl}, {"symbol": "XOM", "date": date, "close": xom}]
        weather_rows.append({"location": "New York", "timestamp": f"{date}T12:00:00+00:00", "temperature": temp, "humidity": 50 + temp})

    results = compute_correlations(weather_rows, price_rows, min_days=10)
    tech = next(r for r in results if r["sector"] == "Information Technology" and r["metric"] == "temperature")
    assert tech["correlation"] > 0.9
    assert tech["n_days"] == 29
    assert compute_correlations([], price_rows) == []
