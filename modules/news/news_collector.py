"""
News data collection module.
Fetches news articles and feeds them through LLM enrichment before queuing.
"""

import asyncio
import logging
import time
import requests
from datetime import datetime
import os

from queues.news_queue import NewsQueue
from models.news import NewsArticle

logger = logging.getLogger(__name__)


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

    def process_news_article(self, article_data: dict) -> NewsArticle:
        return NewsArticle(
            title=article_data["title"],
            content=article_data.get("content", article_data.get("description", "")),
            source=article_data["source"]["name"],
            url=article_data["url"],
            published_date=datetime.fromisoformat(article_data["publishedAt"].replace("Z", "+00:00")),
        )

    async def collect_and_process_news(self, queries: list):
        for query in queries:
            try:
                raw_data = self.fetch_news(query)
                articles = raw_data.get("articles", [])
                for article_data in articles:
                    try:
                        news_article = self.process_news_article(article_data)
                        self.queue.add_to_queue(news_article)
                        logger.info("Queued raw news for enrichment: %s", news_article.title)
                    except Exception as e:
                        logger.error("Error processing article: %s", e)
            except Exception as e:
                logger.error("Error collecting news for query '%s': %s", query, e)


if __name__ == "__main__":
    news_module = NewsModule()
    asyncio.run(news_module.collect_and_process_news(["AAPL stock", "TSLA news"]))
