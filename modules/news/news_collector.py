"""
News data collection module.
Fetches news articles and queues them for LLM enrichment.
"""

import logging
import time
import requests
from datetime import datetime
import os
from typing import List, Optional

from config.tickers import SYMBOL_NAME_MAP, get_all_symbols
from queues.news_queue import NewsQueue
from models.news import NewsArticle

logger = logging.getLogger(__name__)


def build_symbol_query(symbol: str) -> str:
    """NewsAPI query for one ticker.

    Searching the bare ticker is too noisy for symbols like V, MA, SO or KO,
    so search the company name and require a market-related term.
    """
    name = SYMBOL_NAME_MAP.get(symbol, symbol)
    return f'"{name}" AND (stock OR shares OR earnings)'


class NewsModule:
    def __init__(self):
        self.api_key = os.getenv('NEWS_API_KEY')
        self.base_url = "https://newsapi.org/v2/everything"
        self.queue = NewsQueue()

    def fetch_news(self, query: str, page_size: int = 10) -> dict:
        params = {
            "q": query,
            "apiKey": self.api_key,
            "pageSize": page_size,
            "sortBy": "publishedAt",
            "language": "en",
        }
        for attempt in range(3):
            try:
                response = requests.get(self.base_url, params=params, timeout=10)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                if attempt == 2:
                    raise
                wait = 2 ** attempt
                logger.warning("News fetch for '%s' failed (attempt %d/3): %s. Retrying in %ds.", query, attempt + 1, e, wait)
                time.sleep(wait)

    def process_news_article(self, article_data: dict, symbol: Optional[str] = None) -> NewsArticle:
        # NewsAPI truncates `content` to ~200 chars, so keep the description
        # alongside it to give the LLM more to work with.
        parts = [article_data.get("description"), article_data.get("content")]
        content = "\n\n".join(p for p in parts if p)
        return NewsArticle(
            title=article_data["title"],
            content=content,
            source=article_data["source"]["name"],
            url=article_data["url"],
            published_date=datetime.fromisoformat(article_data["publishedAt"].replace("Z", "+00:00")),
            related_stocks=[symbol] if symbol else [],
        )

    def _collect(self, query: str, symbol: Optional[str], page_size: int):
        try:
            raw_data = self.fetch_news(query, page_size=page_size)
        except Exception as e:
            logger.error("Error collecting news for query '%s': %s", query, e)
            return
        for article_data in raw_data.get("articles", []):
            try:
                news_article = self.process_news_article(article_data, symbol=symbol)
                self.queue.add_to_queue(news_article)
                logger.info("Queued raw news for enrichment: %s", news_article.title)
            except Exception as e:
                logger.error("Error processing article: %s", e)

    def collect_and_process_news(self, queries: list, page_size: int = 10):
        """Collect news for free-text queries (articles are tagged by the LLM only)."""
        for query in queries:
            self._collect(query, symbol=None, page_size=page_size)

    def collect_for_symbols(self, symbols: List[str] = None, page_size: int = 5):
        """Collect news per tracked ticker so each article is tied to its stock.

        One request per symbol: 50 symbols fits within NewsAPI's free tier of
        100 requests/day when run once daily.
        """
        for symbol in symbols or get_all_symbols():
            self._collect(build_symbol_query(symbol), symbol=symbol, page_size=page_size)


if __name__ == "__main__":
    news_module = NewsModule()
    news_module.collect_for_symbols(["AAPL", "TSLA"])
