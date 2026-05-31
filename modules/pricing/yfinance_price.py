"""
YFinance price data fetcher.
Fetches current market prices from Yahoo Finance and updates Stock records.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from config.tickers import get_all_symbols
from models.stock import Stock

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
except ModuleNotFoundError as exc:
    yf = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


class YFinancePriceFetcher:
    def __init__(self):
        pass

    def fetch_current_price(self, symbol: str) -> Optional[dict]:
        if _IMPORT_ERROR is not None:
            logger.warning(
                "yfinance dependency is not installed. Install yfinance to fetch prices: %s",
                _IMPORT_ERROR,
            )
            return None

        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period="1d", interval="1m")
            if hist is None or hist.empty:
                hist = ticker.history(period="2d")
            if hist is None or hist.empty:
                return None

            price = float(hist["Close"].iloc[-1])
            timestamp = datetime.now(timezone.utc).isoformat()
            return {
                "symbol": symbol,
                "price": price,
                "price_timestamp": timestamp,
            }
        except Exception as exc:
            logger.warning("YFinance price fetch failed for %s: %s", symbol, exc)
            return None

    def update_prices(self, symbols: List[str] = None) -> List[dict]:
        symbols = symbols or get_all_symbols()
        updated_prices = []

        for symbol in symbols:
            price_data = self.fetch_current_price(symbol)
            if price_data:
                Stock.update_price(
                    symbol=price_data["symbol"],
                    price=price_data["price"],
                    price_timestamp=price_data["price_timestamp"],
                )
                updated_prices.append(price_data)

        return updated_prices


if __name__ == "__main__":
    fetcher = YFinancePriceFetcher()
    symbols = get_all_symbols()
    updated = fetcher.update_prices(symbols)
    print(f"Updated {len(updated)} prices")
