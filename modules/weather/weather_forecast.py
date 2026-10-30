"""
Weather forecast generator.

Pulls OpenWeather's 5-day / 3-hour forecast, aggregates it to one record per
day, and lets WeatherData apply its season/day-out and state-based bias
adjustments on top (stored as adjusted_temperature / adjusted_humidity).
"""

import logging
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import List, Optional

from .weather_collector import WeatherModule
from models.weather import WeatherData

logger = logging.getLogger(__name__)


def aggregate_daily(forecast: dict, now: Optional[datetime] = None) -> List[dict]:
    """Collapse 3-hour forecast steps into daily means for days 1..5 ahead."""
    now = now or datetime.now(timezone.utc)
    today = now.date()
    by_day = defaultdict(list)
    for step in forecast.get("list", []):
        when = datetime.fromtimestamp(step["dt"], timezone.utc)
        if when.date() > today:
            by_day[when.date()].append(step)

    days = []
    for day in sorted(by_day)[:5]:
        steps = by_day[day]
        temps = [s["main"]["temp"] for s in steps]
        hums = [s["main"]["humidity"] for s in steps]
        conditions = Counter(s["weather"][0]["description"] for s in steps if s.get("weather"))
        days.append({
            "forecast_date": datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc),
            "day_out": (day - today).days,
            "temperature": round(sum(temps) / len(temps), 2),
            "humidity": round(sum(hums) / len(hums), 2),
            "conditions": conditions.most_common(1)[0][0] if conditions else "unknown",
        })
    return days


class WeatherForecastGenerator:
    def __init__(self):
        self.weather_module = WeatherModule()

    def generate_5_day_forecast(self, cities: Optional[List[str]] = None) -> List[WeatherData]:
        cities = cities or ["New York", "San Francisco", "London", "Tokyo"]
        forecasts: List[WeatherData] = []
        issued_at = datetime.now(timezone.utc)

        for city in cities:
            try:
                raw = self.weather_module.fetch_forecast(city)
            except Exception as e:
                logger.error("Error fetching forecast for %s: %s", city, e)
                continue

            location = raw.get("city", {}).get("name", city)
            for day in aggregate_daily(raw, now=issued_at):
                forecasts.append(WeatherData(
                    location=location,
                    temperature=day["temperature"],
                    humidity=day["humidity"],
                    conditions=day["conditions"],
                    timestamp=issued_at,
                    forecast_date=day["forecast_date"],
                    day_out=day["day_out"],
                ))

        return forecasts
