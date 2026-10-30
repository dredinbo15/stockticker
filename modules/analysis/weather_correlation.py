"""
Weather / market correlation analysis.

Correlates each city's daily mean temperature and humidity with the
equal-weighted daily return of each sector over the same trading days.
This is exploratory: with a few months of data most correlations will be
noise, so n_days is reported next to every coefficient.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List

import pandas as pd

from config.tickers import SYMBOL_SECTOR_MAP


def daily_sector_returns(price_rows: List[Dict]) -> pd.DataFrame:
    """Return a date x sector frame of equal-weighted daily close-to-close returns."""
    if not price_rows:
        return pd.DataFrame()
    prices = pd.DataFrame(price_rows)
    closes = prices.pivot_table(index="date", columns="symbol", values="close").sort_index()
    returns = closes.pct_change(fill_method=None).iloc[1:]
    sectors = {sym: SYMBOL_SECTOR_MAP.get(sym, "Unknown") for sym in returns.columns}
    return returns.T.groupby(sectors).mean().T


def daily_weather(weather_rows: List[Dict]) -> pd.DataFrame:
    """Return per-location daily mean temperature and humidity."""
    if not weather_rows:
        return pd.DataFrame()
    weather = pd.DataFrame(weather_rows)
    weather["date"] = pd.to_datetime(weather["timestamp"], utc=True, format="ISO8601").dt.strftime("%Y-%m-%d")
    return (
        weather.groupby(["location", "date"])[["temperature", "humidity"]]
        .mean()
        .reset_index()
    )


def compute_correlations(weather_rows: List[Dict], price_rows: List[Dict], min_days: int = 10) -> List[Dict]:
    sector_returns = daily_sector_returns(price_rows)
    weather = daily_weather(weather_rows)
    if sector_returns.empty or weather.empty:
        return []

    results = []
    for location, loc_weather in weather.groupby("location"):
        joined = loc_weather.set_index("date").join(sector_returns, how="inner")
        if len(joined) < min_days:
            continue
        for metric in ("temperature", "humidity"):
            for sector in sector_returns.columns:
                pair = joined[[metric, sector]].dropna()
                if len(pair) < min_days or pair[metric].std() == 0 or pair[sector].std() == 0:
                    continue
                results.append({
                    "location": location,
                    "metric": metric,
                    "sector": sector,
                    "correlation": round(float(pair[metric].corr(pair[sector])), 4),
                    "n_days": int(len(pair)),
                })
    results.sort(key=lambda r: abs(r["correlation"]), reverse=True)
    return results


class WeatherCorrelationAnalyzer:
    def run(self, days: int = 180, min_days: int = 10) -> List[Dict]:
        from models.price import PricePoint
        from models.weather import WeatherData

        since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        weather_rows = WeatherData.get_observations(since=since)
        price_rows = PricePoint.get_history(since=since)
        return compute_correlations(weather_rows, price_rows, min_days=min_days)
