"""
Weather data queue wrapper.
"""

from queues.tasks import save_weather_data

class WeatherQueue:
    def add_to_queue(self, weather_data):
        """Add weather data to processing queue."""
        weather_dict = {
            'location': weather_data.location,
            'temperature': weather_data.temperature,
            'humidity': weather_data.humidity,
            'conditions': weather_data.conditions,
            'timestamp': weather_data.timestamp.isoformat(),
            'confidence': weather_data.confidence,
        }
        save_weather_data.delay(weather_dict)