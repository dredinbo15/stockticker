"""
SEC 8-K data collection module.
Fetches 8-K filings from EDGAR and queues them for LLM enrichment.
"""

import logging
import re
import requests
from datetime import datetime, timezone
from html.parser import HTMLParser
from queues.sec_8k_queue import SEC8KQueue
from models.sec_8k import SEC8K
from config.credentials import get_credentials_manager

logger = logging.getLogger(__name__)

creds = get_credentials_manager()
_USER_AGENT = creds.get_credential('SEC_USER_AGENT', 'SEC_USER_AGENT', "stockticker contact@example.com")
_HEADERS = {"User-Agent": _USER_AGENT, "Accept-Encoding": "gzip, deflate"}


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []

    def handle_data(self, data):
        self.result.append(data)

    def get_text(self):
        return " ".join(self.result)


class SEC8KModule:
    def __init__(self):
        self.base_url = "https://www.sec.gov/Archives/edgar/data/"
        self.submissions_url = "https://data.sec.gov/submissions/CIK{}.json"
        self.queue = SEC8KQueue()

    def fetch_recent_filings(self, cik: str, limit: int = 10) -> list:
        padded_cik = cik.zfill(10)
        url = self.submissions_url.format(padded_cik)
        response = requests.get(url, headers=_HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()

        issuer_name = data.get("entityName", "")
        recent = data.get("filings", {}).get("recent", {})
        form_types = recent.get("form", [])
        accession_numbers = recent.get("accessionNumber", [])
        primary_documents = recent.get("primaryDocument", [])

        filings = []
        for i, form_type in enumerate(form_types):
            if len(filings) >= limit:
                break
            if form_type not in {"8-K", "8-K/A", "8-KT"}:
                continue

            accession_no = accession_numbers[i].replace("-", "")
            doc = primary_documents[i]
            doc_url = f"{self.base_url}{cik}/{accession_no}/{doc}"

            try:
                doc_resp = requests.get(doc_url, headers=_HEADERS, timeout=15)
                doc_resp.raise_for_status()
                filings.append((doc_url, doc_resp.text, issuer_name))
            except requests.RequestException as e:
                logger.warning("Failed to download 8-K filing %s: %s", doc_url, e)

        return filings

    def _extract_text(self, raw_content: str) -> str:
        if "<html" in raw_content.lower() or "<body" in raw_content.lower():
            parser = TextExtractor()
            parser.feed(raw_content)
            text = parser.get_text()
        else:
            text = raw_content

        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _parse_items(self, text: str) -> list:
        items = []
        pattern = re.compile(r"(Item\s+\d+\.\d+)(?:\s*[:\-–]?)(.*?)(?=Item\s+\d+\.\d+|$)", re.IGNORECASE | re.DOTALL)
        for match in pattern.finditer(text):
            item_header = match.group(1).strip()
            item_body = match.group(2).strip()
            items.append(f"{item_header}: {item_body[:800]}")
        return items

    def parse_8k_document(self, raw_content: str, issuer_cik: str, issuer_name: str, form_url: str = "") -> SEC8K:
        text = self._extract_text(raw_content)
        items = self._parse_items(text)

        description = items[0] if items else text[:300]
        item_summary = " | ".join(items[:3]) if items else ""

        filing_date = datetime.now(timezone.utc)
        date_match = re.search(r"(Filed|Filing Date)\s*[:\-]?\s*(\d{4}-\d{2}-\d{2})", raw_content)
        if date_match:
            try:
                filing_date = datetime.fromisoformat(date_match.group(2)).replace(tzinfo=timezone.utc)
            except ValueError:
                filing_date = filing_date

        return SEC8K(
            issuer_cik=issuer_cik,
            issuer_name=issuer_name,
            filing_date=filing_date,
            description=description,
            content=text,
            item_summary=item_summary,
            form_url=form_url,
        )

    def collect_and_queue(self, company_ciks: list):
        for cik in company_ciks:
            try:
                filings = self.fetch_recent_filings(cik)
                for form_url, raw_text, issuer_name in filings:
                    try:
                        report = self.parse_8k_document(raw_text, issuer_cik=cik, issuer_name=issuer_name, form_url=form_url)
                        self.queue.add_to_queue(report)
                    except Exception as e:
                        logger.error("Error parsing 8-K from %s: %s", form_url, e)
            except Exception as e:
                logger.error("Error collecting 8-K data for CIK %s: %s", cik, e)


if __name__ == "__main__":
    from config.tickers import get_all_ciks
    sec8k = SEC8KModule()
    sec8k.collect_and_queue(get_all_ciks())
