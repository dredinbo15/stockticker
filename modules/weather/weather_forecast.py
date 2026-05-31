"""
Weather forecast generator with season/day-out and state-based bias adjustments.
"""

from datetime import timedelta
from typing import List, Optional

from .weather_collector import WeatherModule
from models.weather import WeatherData


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
