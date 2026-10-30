"""
YFinance price data fetcher.
Fetches current market prices and daily history from Yahoo Finance and
updates Stock / PricePoint records.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from config.tickers import get_all_symbols
from models.price import PricePoint
from models.stock import Stock

logger = logging.getLogger(__name__)

try:
    import yfinance as yf
except ModuleNotFoundError as exc:
    yf = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


def _dependency_ready() -> bool:
    if _IMPORT_ERROR is not None:
        logger.warning(
            "yfinance dependency is not installed. Install yfinance to fetch prices: %s",
            _IMPORT_ERROR,
        )
        return False
    return True


def history_frame_to_rows(hist) -> List[dict]:
    """Convert a yfinance history DataFrame into PricePoint rows."""
    rows = []
    if hist is None or hist.empty:
        return rows
    for index, bar in hist.iterrows():
        close = bar.get("Close")
        if close is None or close != close:  # skip NaN closes
            continue
        rows.append({
            "date": index.strftime("%Y-%m-%d"),
            "open": float(bar.get("Open", close)),
            "high": float(bar.get("High", close)),
            "low": float(bar.get("Low", close)),
            "close": float(close),
            "volume": int(bar.get("Volume", 0) or 0),
        })
    return rows


class YFinancePriceFetcher:
    def fetch_current_price(self, symbol: str) -> Optional[dict]:
        if not _dependency_ready():
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

    def fetch_history(self, symbol: str, period: str = "1mo") -> List[dict]:
        if not _dependency_ready():
            return []
        try:
            hist = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=True)
            return history_frame_to_rows(hist)
        except Exception as exc:
            logger.warning("YFinance history fetch failed for %s: %s", symbol, exc)
            return []

    def update_prices(self, symbols: List[str] = None) -> List[dict]:
        """Refresh the latest (intraday) price on each Stock node."""
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

    def update_price_history(self, symbols: List[str] = None, period: str = "1mo") -> dict:
        """Store daily OHLCV history and set each Stock's price to the last close.

        Use a long period (e.g. "2y") once to backfill, then a short one
        (e.g. "5d") for daily updates; rows are upserted so overlap is safe.
        """
        symbols = symbols or get_all_symbols()
        saved = {}
        for symbol in symbols:
            rows = self.fetch_history(symbol, period=period)
            if not rows:
                continue
            saved[symbol] = PricePoint.save_many(symbol, rows)
            last = rows[-1]
            Stock.update_price(symbol=symbol, price=last["close"], price_timestamp=last["date"])
        logger.info("Saved price history for %d/%d symbols", len(saved), len(symbols))
        return saved


if __name__ == "__main__":
    fetcher = YFinancePriceFetcher()
    saved = fetcher.update_price_history(get_all_symbols(), period="2y")
    print(f"Saved history for {len(saved)} symbols")
