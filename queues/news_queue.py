"""
News data queue wrapper.
"""

from queues.tasks import process_raw_news_article

class NewsQueue:
    def add_to_queue(self, news_article):
        """Add raw news article to processing queue before LLM enrichment."""
        news_dict = {
            'title': news_article.title,
            'content': news_article.content,
            'source': news_article.source,
            'url': news_article.url,
            'published_date': news_article.published_date.isoformat(),
            'article_hash': news_article.article_hash,
        }
        process_raw_news_article.delay(news_dict)