"""
Weather data model for stock correlation analysis.
"""

from config.database import get_neo4j_session
from datetime import datetime, timezone
from typing import Dict

SEASONAL_BIAS: Dict[str, Dict[str, float]] = {
    "winter": {"temperature": -1.5, "humidity": 2.0},
    "spring": {"temperature": 0.5, "humidity": -1.0},
    "summer": {"temperature": 1.2, "humidity": -2.0},
    "autumn": {"temperature": 0.0, "humidity": 1.0},
}

STATE_SEASON_BIAS: Dict[str, Dict[str, Dict[str, float]]] = {
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


class WeatherData:
    def __init__(
        self,
        location: str,
        temperature: float,
        humidity: float,
        conditions: str,
        timestamp: datetime = None,
        confidence: float = None,
        state: str = None,
        forecast_date: datetime = None,
        day_out: int = 0,
        season: str = None,
        seasonal_bias_temperature: float = None,
        seasonal_bias_humidity: float = None,
        day_out_bias_temperature: float = None,
        day_out_bias_humidity: float = None,
        state_bias_temperature: float = None,
        state_bias_humidity: float = None,
        adjusted_temperature: float = None,
        adjusted_humidity: float = None,
        record_type: str = None,
    ):
        self.location = location
        self.state = state or self._infer_state(location)
        self.temperature = temperature
        self.humidity = humidity
        self.conditions = conditions
        self.timestamp = timestamp or datetime.now(timezone.utc)
        self.forecast_date = forecast_date
        self.day_out = day_out or 0
        self.season = season or self._determine_season()
        self.seasonal_bias_temperature = (
            seasonal_bias_temperature
            if seasonal_bias_temperature is not None
            else self._calculate_seasonal_bias()["temperature"]
        )
        self.seasonal_bias_humidity = (
            seasonal_bias_humidity
            if seasonal_bias_humidity is not None
            else self._calculate_seasonal_bias()["humidity"]
        )
        self.day_out_bias_temperature = (
            day_out_bias_temperature
            if day_out_bias_temperature is not None
            else self._calculate_day_out_bias()["temperature"]
        )
        self.day_out_bias_humidity = (
            day_out_bias_humidity
            if day_out_bias_humidity is not None
            else self._calculate_day_out_bias()["humidity"]
        )
        self.state_bias_temperature = (
            state_bias_temperature
            if state_bias_temperature is not None
            else self._calculate_state_bias()["temperature"]
        )
        self.state_bias_humidity = (
            state_bias_humidity
            if state_bias_humidity is not None
            else self._calculate_state_bias()["humidity"]
        )
        self.adjusted_temperature = (
            adjusted_temperature
            if adjusted_temperature is not None
            else self._calculate_adjusted_temperature()
        )
        self.adjusted_humidity = (
            adjusted_humidity
            if adjusted_humidity is not None
            else self._calculate_adjusted_humidity()
        )
        self.record_type = record_type or ("forecast" if self.day_out > 0 else "observation")
        self.confidence = confidence if confidence is not None else self._calculate_confidence()

    def _infer_state(self, location: str) -> str:
        name = location.split(",")[0].strip()
        return CITY_STATE_MAP.get(name, "Unknown")

    def _determine_season(self) -> str:
        effective_date = self.forecast_date or self.timestamp
        month = effective_date.month
        if month in (12, 1, 2):
            return "winter"
        if month in (3, 4, 5):
            return "spring"
        if month in (6, 7, 8):
            return "summer"
        return "autumn"

    def _calculate_seasonal_bias(self) -> Dict[str, float]:
        return SEASONAL_BIAS.get(self.season, {"temperature": 0.0, "humidity": 0.0})

    def _calculate_day_out_bias(self) -> Dict[str, float]:
        if self.day_out <= 0:
            return {"temperature": 0.0, "humidity": 0.0}
        return {"temperature": round(0.2 * self.day_out, 2), "humidity": round(0.5 * self.day_out, 2)}

    def _calculate_state_bias(self) -> Dict[str, float]:
        if self.state not in STATE_SEASON_BIAS:
            return {"temperature": 0.0, "humidity": 0.0}
        return STATE_SEASON_BIAS[self.state].get(self.season, {"temperature": 0.0, "humidity": 0.0})

    def _calculate_adjusted_temperature(self) -> float:
        return round(
            self.temperature
            + self.seasonal_bias_temperature
            + self.day_out_bias_temperature
            + self.state_bias_temperature,
            2,
        )

    def _calculate_adjusted_humidity(self) -> float:
        return round(
            self.humidity
            + self.seasonal_bias_humidity
            + self.day_out_bias_humidity
            + self.state_bias_humidity,
            2,
        )

    def _calculate_confidence(self) -> float:
        age_hours = (datetime.now(timezone.utc) - self.timestamp).total_seconds() / 3600.0
        confidence = 1.0 - min(max(age_hours / 24.0, 0.0), 1.0)
        if self.day_out > 0:
            confidence -= min(self.day_out * 0.08, 0.4)
        return round(max(confidence, 0.0), 3)

    def save(self):
        with get_neo4j_session() as session:
            query = """
            CREATE (w:WeatherData {
                location: $location,
                state: $state,
                record_type: $record_type,
                temperature: $temperature,
                humidity: $humidity,
                conditions: $conditions,
                timestamp: $timestamp,
                confidence: $confidence,
                forecast_date: $forecast_date,
                day_out: $day_out,
                season: $season,
                seasonal_bias_temperature: $seasonal_bias_temperature,
                seasonal_bias_humidity: $seasonal_bias_humidity,
                day_out_bias_temperature: $day_out_bias_temperature,
                day_out_bias_humidity: $day_out_bias_humidity,
                state_bias_temperature: $state_bias_temperature,
                state_bias_humidity: $state_bias_humidity,
                adjusted_temperature: $adjusted_temperature,
                adjusted_humidity: $adjusted_humidity
            })
            RETURN w
            """
            result = session.run(
                query,
                location=self.location,
                state=self.state,
                record_type=self.record_type,
                temperature=self.temperature,
                humidity=self.humidity,
                conditions=self.conditions,
                timestamp=self.timestamp.isoformat(),
                confidence=self.confidence,
                forecast_date=self.forecast_date.isoformat() if self.forecast_date else None,
                day_out=self.day_out,
                season=self.season,
                seasonal_bias_temperature=self.seasonal_bias_temperature,
                seasonal_bias_humidity=self.seasonal_bias_humidity,
                day_out_bias_temperature=self.day_out_bias_temperature,
                day_out_bias_humidity=self.day_out_bias_humidity,
                state_bias_temperature=self.state_bias_temperature,
                state_bias_humidity=self.state_bias_humidity,
                adjusted_temperature=self.adjusted_temperature,
                adjusted_humidity=self.adjusted_humidity,
            )
            return result.single()

