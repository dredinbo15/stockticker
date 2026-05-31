"""
LLM enrichment module for news articles.
Uses OpenAI to analyze sentiment, extract related stocks, and enrich content.
"""

import json
import logging
import re
from typing import Any, Dict

from openai import AsyncOpenAI

from config.credentials import get_credentials_manager

logger = logging.getLogger(__name__)


class LLMProcessor:
    def __init__(self):
        creds = get_credentials_manager()
        api_key = creds.get_credential("OPENAI_API_KEY", "OPENAI_API_KEY")
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = creds.get_credential("OPENAI_MODEL", "OPENAI_MODEL", "gpt-4o-mini")

    @staticmethod
    def _parse_json_payload(payload: str) -> Dict[str, Any]:
        if not payload:
            raise ValueError("Received an empty response from OpenAI")

        cleaned = payload.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(
                r"^```(?:json)?\s*|\s*```$",
                "",
                cleaned,
                flags=re.IGNORECASE | re.DOTALL,
            ).strip()

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("OpenAI response did not contain a JSON object")

        parsed = json.loads(cleaned[start : end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("OpenAI response JSON was not an object")
        return parsed

    async def _generate_json(self, prompt: str, max_output_tokens: int) -> Dict[str, Any]:
        if hasattr(self.client, "responses"):
            response = await self.client.responses.create(
                model=self.model,
                input=prompt,
                max_output_tokens=max_output_tokens,
                temperature=0.3,
            )
            return self._parse_json_payload(getattr(response, "output_text", "") or "")

        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_output_tokens,
            temperature=0.3,
        )
        content = response.choices[0].message.content or ""
        return self._parse_json_payload(content)

    async def enrich_news(self, news_article) -> Dict:
        prompt = f"""
        Analyze the following news article and provide:
        1. Sentiment analysis (positive, negative, neutral)
        2. List of stock symbols mentioned or related to the article
        3. A brief enriched summary highlighting key financial implications

        Article Title: {news_article.title}
        Content: {news_article.content}

        Respond in JSON format with keys: sentiment, related_stocks (array), enriched_content
        """

        try:
            result = await self._generate_json(prompt, max_output_tokens=500)

            return {
                "sentiment": result.get("sentiment", "neutral"),
                "related_stocks": result.get("related_stocks", []),
                "enriched_content": result.get("enriched_content", news_article.content),
            }
        except Exception as exc:
            logger.warning("News enrichment failed for model %s: %s", self.model, exc)
            return {
                "sentiment": "neutral",
                "related_stocks": [],
                "enriched_content": news_article.content,
            }

    async def enrich_8k_report(self, report) -> Dict:
        content = report.content
        if len(content) > 5000:
            content = content[:5000] + "\n\n[...truncated]"

        prompt = f"""
        Analyze the following SEC 8-K report and provide:
        1. A concise summary of the filing
        2. The most important items and sections
        3. The likely business or market impact

        Company: {report.issuer_name}
        Filing Date: {report.filing_date}
        Description: {report.description}
        Item Summary: {report.item_summary}
        Report Content: {content}

        Respond in JSON format with keys: llm_summary, key_items, impact_assessment
        """

        try:
            result = await self._generate_json(prompt, max_output_tokens=700)
            return {
                "llm_summary": result.get("llm_summary", ""),
                "key_items": result.get("key_items", ""),
                "impact_assessment": result.get("impact_assessment", ""),
            }
        except Exception as exc:
            logger.warning("8-K enrichment failed for model %s: %s", self.model, exc)
            return {
                "llm_summary": report.description,
                "key_items": report.item_summary,
                "impact_assessment": "",
            }

# Usage example
if __name__ == "__main__":
    import asyncio
    from models.news import NewsArticle

    processor = LLMProcessor()
    article = NewsArticle(
        title="Apple Reports Strong Q4 Earnings",
        content="Apple Inc. reported better than expected quarterly earnings...",
        source="Reuters"
    )

    enriched = asyncio.run(processor.enrich_news(article))
    print(enriched)
