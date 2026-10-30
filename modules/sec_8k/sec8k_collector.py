"""
SEC 8-K data collection module.
Fetches 8-K filings from EDGAR and queues them for LLM enrichment.
"""

import logging
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from queues.sec_8k_queue import SEC8KQueue
from models.sec_8k import SEC8K
from modules.sec_client import sec_get

logger = logging.getLogger(__name__)


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1

    def handle_data(self, data):
        if not self._skip_depth:
            self.result.append(data)

    def get_text(self):
        return " ".join(self.result)


class SEC8KModule:
    def __init__(self):
        self.base_url = "https://www.sec.gov/Archives/edgar/data/"
        self.submissions_url = "https://data.sec.gov/submissions/CIK{}.json"
        self.queue = SEC8KQueue()

    def fetch_recent_filings(self, cik: str, limit: int = 10) -> list:
        """Return (doc_url, raw_text, issuer_name, filing_date) tuples."""
        padded_cik = cik.zfill(10)
        url = self.submissions_url.format(padded_cik)
        data = sec_get(url, timeout=10).json()

        issuer_name = data.get("entityName", "")
        recent = data.get("filings", {}).get("recent", {})
        form_types = recent.get("form", [])
        accession_numbers = recent.get("accessionNumber", [])
        primary_documents = recent.get("primaryDocument", [])
        filing_dates = recent.get("filingDate", [])

        filings = []
        for i, form_type in enumerate(form_types):
            if len(filings) >= limit:
                break
            if form_type not in {"8-K", "8-K/A", "8-KT"}:
                continue

            accession_no = accession_numbers[i].replace("-", "")
            doc = primary_documents[i]
            doc_url = f"{self.base_url}{cik}/{accession_no}/{doc}"
            filing_date = filing_dates[i] if i < len(filing_dates) else ""

            try:
                doc_resp = sec_get(doc_url, timeout=15)
                filings.append((doc_url, doc_resp.text, issuer_name, filing_date))
            except Exception as e:
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

    def parse_8k_document(self, raw_content: str, issuer_cik: str, issuer_name: str,
                          form_url: str = "", filing_date: str = "") -> SEC8K:
        text = self._extract_text(raw_content)
        items = self._parse_items(text)

        description = items[0] if items else text[:300]
        item_summary = " | ".join(items[:3]) if items else ""

        # EDGAR's submissions index carries the authoritative filing date;
        # the document body rarely states it in a parseable form.
        try:
            parsed_date = datetime.strptime(filing_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            logger.warning("No filing date for %s; using the current time.", form_url)
            parsed_date = datetime.now(timezone.utc)

        return SEC8K(
            issuer_cik=issuer_cik,
            issuer_name=issuer_name,
            filing_date=parsed_date,
            description=description,
            content=text,
            item_summary=item_summary,
            form_url=form_url,
        )

    def collect_and_queue(self, company_ciks: list):
        for cik in company_ciks:
            try:
                filings = self.fetch_recent_filings(cik)
                for form_url, raw_text, issuer_name, filing_date in filings:
                    try:
                        report = self.parse_8k_document(
                            raw_text, issuer_cik=cik, issuer_name=issuer_name,
                            form_url=form_url, filing_date=filing_date,
                        )
                        self.queue.add_to_queue(report)
                    except Exception as e:
                        logger.error("Error parsing 8-K from %s: %s", form_url, e)
            except Exception as e:
                logger.error("Error collecting 8-K data for CIK %s: %s", cik, e)


if __name__ == "__main__":
    from config.tickers import get_all_ciks
    sec8k = SEC8KModule()
    sec8k.collect_and_queue(get_all_ciks())
