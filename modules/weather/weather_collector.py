"""
Weather data collection module.
Fetches weather data and feeds it to the queue for database insertion.
"""

import logging
import time
import requests
from datetime import datetime, timezone
import os

from queues.weather_queue import WeatherQueue
from models.weather import WeatherData

logger = logging.getLogger(__name__)


class WeatherModule:
    def __init__(self):
        self.api_key = os.getenv('OPENWEATHER_API_KEY')
        self.base_url = "http://api.openweathermap.org/data/2.5/weather"
        self.queue = WeatherQueue()

    def fetch_weather(self, city: str) -> dict:
        params = {"q": city, "appid": self.api_key, "units": "metric"}
        for attempt in range(3):
            try:
                response = requests.get(self.base_url, params=params, timeout=10)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                if attempt == 2:
                    raise
                wait = 2 ** attempt
                logger.warning("Weather fetch for %s failed (attempt %d/3): %s. Retrying in %ds.", city, attempt + 1, e, wait)
                time.sleep(wait)

    def process_weather_data(self, data: dict) -> WeatherData:
        main = data["main"]
        weather = data["weather"][0]
        timestamp = None
        if data.get("dt"):
            try:
                timestamp = datetime.fromtimestamp(data["dt"], timezone.utc)
            except Exception:
                timestamp = None

        return WeatherData(
            location=data["name"],
            temperature=main["temp"],
            humidity=main["humidity"],
            conditions=weather["description"],
            timestamp=timestamp,
        )

    def collect_and_queue(self, cities: list):
        for city in cities:
            try:
                raw_data = self.fetch_weather(city)
                weather_data = self.process_weather_data(raw_data)
                self.queue.add_to_queue(weather_data)
                logger.info("Queued weather data for %s", city)
            except Exception as e:
                logger.error("Error collecting weather for %s: %s", city, e)


if __name__ == "__main__":
    weather_module = WeatherModule()
    weather_module.collect_and_queue(["New York", "San Francisco", "London"])
