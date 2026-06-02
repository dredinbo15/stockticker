"""
News data model with LLM enrichment.
"""

import hashlib
from config.database import get_neo4j_session
from datetime import datetime, timezone
from typing import List

class NewsArticle:
    def __init__(self, title: str, content: str, source: str, url: str = None,
                 published_date: datetime = None, sentiment: str = None,
                 enriched_content: str = None, related_stocks: List[str] = None,
                 article_hash: str = None):
        self.title = title
        self.content = content
        self.source = source
        self.url = url
        self.published_date = published_date or datetime.now(timezone.utc)
        self.sentiment = sentiment
        self.enriched_content = enriched_content
        self.related_stocks = related_stocks or []
        self.article_hash = article_hash or self._create_hash()

    def _create_hash(self) -> str:
        payload = "|".join([
            self.title or "",
            self.url or "",
            self.published_date.isoformat(),
            self.content or ""
        ])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def save(self):
        if not self.url:
            raise ValueError("NewsArticle.url is required to prevent duplicate articles.")

        with get_neo4j_session() as session:
            query = """
            MERGE (n:NewsArticle {article_hash: $article_hash})
            ON CREATE SET
                n.title = $title,
                n.content = $content,
                n.source = $source,
                n.published_date = $published_date,
                n.url = $url
            SET
                n.sentiment = $sentiment,
                n.enriched_content = $enriched_content,
                n.related_stocks = $related_stocks
            RETURN n
            """
            result = session.run(query,
                               article_hash=self.article_hash,
                               title=self.title,
                               content=self.content,
                               source=self.source,
                               published_date=self.published_date.isoformat(),
                               sentiment=self.sentiment,
                               enriched_content=self.enriched_content,
                               related_stocks=self.related_stocks,
                               url=self.url)
            article_node = result.single()["n"]

            for stock_symbol in self.related_stocks:
                session.run("""
                MATCH (n:NewsArticle {article_hash: $article_hash}), (s:Stock {symbol: $symbol})
                MERGE (n)-[:MENTIONS]->(s)
                """, article_hash=self.article_hash, symbol=stock_symbol)

            return article_node

    @staticmethod
    def get_news_by_stock(symbol: str, limit: int = 20):
        with get_neo4j_session() as session:
            query = """
            MATCH (n:NewsArticle)-[:MENTIONS]->(s:Stock {symbol: $symbol})
            RETURN n ORDER BY n.published_date DESC LIMIT $limit
            """
            result = session.run(query, symbol=symbol, limit=limit)
            return [record["n"] for record in result]

