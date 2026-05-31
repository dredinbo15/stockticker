"""
Weather forecast generator with season/day-out and state-based bias adjustments.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

from .weather_collector import WeatherModule
from models.weather import WeatherData


SEASONAL_BIAS_MAP: Dict[str, Dict[str, float]] = {
    "winter": {"temperature": -1.5, "humidity": 2.0},
    "spring": {"temperature": 0.5, "humidity": -1.0},
    "summer": {"temperature": 1.2, "humidity": -2.0},
    "autumn": {"temperature": 0.0, "humidity": 1.0},
}

STATE_SEASON_BIAS_MAP: Dict[str, Dict[str, Dict[str, float]]] = {
    "California": {
        "winter": {"temperature": 0.4, "humidity": -0.8},
        "spring": {"temperature": 0.3, "humidity": -0.5},
        "summer": {"temperature": 0.8, "humidity": -1.5},
        "autumn": {"temperature": 0.3, "humidity": 0.0},
    },
    "New York": {
        "winter": {"temperature": -0.4, "humidity": 1.2},
        "spring": {"temperature": 0.2, "humidity": -0.5},
        "summer": {"temperature": 0.6, "humidity": -1.0},
        "autumn": {"temperature": -0.1, "humidity": 0.8},
    },
    "Texas": {
        "winter": {"temperature": 0.5, "humidity": -0.2},
        "spring": {"temperature": 0.7, "humidity": -0.8},
        "summer": {"temperature": 1.0, "humidity": -1.5},
        "autumn": {"temperature": 0.4, "humidity": -0.4},
    },
    "Florida": {
        "winter": {"temperature": 0.8, "humidity": -1.0},
        "spring": {"temperature": 0.5, "humidity": -0.8},
        "summer": {"temperature": 1.0, "humidity": -2.0},
        "autumn": {"temperature": 0.5, "humidity": -0.5},
    },
}

CITY_STATE_MAP: Dict[str, str] = {
    "New York": "New York",
    "San Francisco": "California",
    "Los Angeles": "California",
    "San Jose": "California",
    "Seattle": "Washington",
    "Chicago": "Illinois",
    "Boston": "Massachusetts",
    "Miami": "Florida",
    "Dallas": "Texas",
    "Austin": "Texas",
    "Houston": "Texas",
    "London": "England",
    "Tokyo": "Tokyo",
}


class WeatherForecastGenerator:
    def __init__(self):
        self.weather_module = WeatherModule()

    def generate_5_day_forecast(self, cities: Optional[List[str]] = None) -> List[WeatherData]:
        cities = cities or ["New York", "San Francisco", "London", "Tokyo"]
        forecasts: List[WeatherData] = []

        for city in cities:
            try:
                raw_weather = self.weather_module.fetch_weather(city)
                observation = self.weather_module.process_weather_data(raw_weather)
            except Exception:
                continue

            for day_out in range(1, 6):
                forecast_date = observation.timestamp + timedelta(days=day_out)
                forecast = WeatherData(
                    location=observation.location,
                    temperature=observation.temperature,
                    humidity=observation.humidity,
                    conditions=observation.conditions,
                    timestamp=observation.timestamp,
                    state=observation.state,
                    forecast_date=forecast_date,
                    day_out=day_out,
                )
                forecasts.append(forecast)

        return forecasts

    def get_state_for_location(self, location: str) -> str:
        name = location.split(",")[0].strip()
        return CITY_STATE_MAP.get(name, "Unknown")

    @staticmethod
    def get_season(date: datetime) -> str:
        month = date.month
        if month in (12, 1, 2):
            return "winter"
        if month in (3, 4, 5):
            return "spring"
        if month in (6, 7, 8):
            return "summer"
        return "autumn"

    @staticmethod
    def day_out_bias(day_out: int) -> Dict[str, float]:
        if day_out <= 0:
            return {"temperature": 0.0, "humidity": 0.0}
        return {
            "temperature": round(0.18 * day_out, 2),
            "humidity": round(0.6 * day_out, 2),
        }

    @staticmethod
    def seasonal_bias(season: str) -> Dict[str, float]:
        return SEASONAL_BIAS_MAP.get(season, {"temperature": 0.0, "humidity": 0.0})

    @staticmethod
    def state_bias(state: str, season: str) -> Dict[str, float]:
        return STATE_SEASON_BIAS_MAP.get(state, {}).get(season, {"temperature": 0.0, "humidity": 0.0})
