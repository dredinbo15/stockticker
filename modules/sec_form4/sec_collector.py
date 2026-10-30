"""
SEC Form 4 data collection module.
Fetches insider trading data from SEC EDGAR and queues for database insertion.
"""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

from queues.sec_form4_queue import SECForm4Queue
from models.sec_form4 import SECForm4
from modules.sec_client import raw_document_name, sec_get

logger = logging.getLogger(__name__)


class SECForm4Module:
    def __init__(self):
        self.base_url = "https://www.sec.gov/Archives/edgar/data/"
        self.submissions_url = "https://data.sec.gov/submissions/CIK{}.json"
        self.queue = SECForm4Queue()

    def fetch_recent_filings(self, cik: str, limit: int = 25) -> list:
        """Fetch recent Form 4 XML contents for a company CIK via EDGAR submissions API.

        Returns (xml_url, xml_text, filing_date) tuples.
        """
        padded_cik = cik.zfill(10)
        url = self.submissions_url.format(padded_cik)

        data = sec_get(url, timeout=10).json()

        recent = data.get("filings", {}).get("recent", {})
        form_types = recent.get("form", [])
        accession_numbers = recent.get("accessionNumber", [])
        primary_documents = recent.get("primaryDocument", [])
        filing_dates = recent.get("filingDate", [])

        xml_contents = []
        for i, form_type in enumerate(form_types):
            if len(xml_contents) >= limit:
                break
            if form_type not in {"4", "4/A"}:
                continue

            accession_no = accession_numbers[i].replace("-", "")
            doc = raw_document_name(primary_documents[i])
            xml_url = f"{self.base_url}{cik}/{accession_no}/{doc}"
            filing_date = filing_dates[i] if i < len(filing_dates) else ""

            try:
                xml_response = sec_get(xml_url, timeout=10)
                xml_contents.append((xml_url, xml_response.text, filing_date))
            except Exception as e:
                logger.error("Error downloading filing %s: %s", xml_url, e)

        return xml_contents

    def parse_form4_xml(self, xml_content: str, form_url: str = "", filing_date: str = "") -> list[SECForm4]:
        """Parse Form 4 XML into a list of SECForm4 objects."""
        root = ET.fromstring(xml_content.strip())

        # Transactions without their own date fall back to the filing date
        # rather than "now", which would leak them into the wrong time window.
        try:
            filed_on = datetime.strptime(filing_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            filed_on = None
        fallback_date = filed_on or datetime.now(timezone.utc)

        def text(node, path, default=""):
            el = node.find(path) if node is not None else None
            return el.text.strip() if el is not None and el.text else default

        issuer = root.find(".//issuer")
        issuer_cik = text(issuer, "issuerCik")
        issuer_name = text(issuer, "issuerName")

        reporting_owner = root.find(".//reportingOwner")
        reporting_owner_id = reporting_owner.find("reportingOwnerId") if reporting_owner is not None else None
        reporter_cik = text(reporting_owner_id, "rptOwnerCik")
        reporter_name = text(reporting_owner_id, "rptOwnerName")
        ownership_nature = text(reporting_owner, "reportingOwnerRelationship/relationship")

        transactions = []
        transaction_paths = [
            ("nonDerivative", ".//nonDerivativeTable/nonDerivativeTransaction"),
            ("derivative", ".//derivativeTable/derivativeTransaction"),
        ]

        for transaction_type, xpath in transaction_paths:
            for transaction in root.findall(xpath):
                date_str = text(transaction, "transactionDate/value")
                try:
                    transaction_date = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc) if date_str else fallback_date
                except ValueError:
                    transaction_date = fallback_date

                try:
                    shares = int(float(text(transaction, "transactionAmounts/transactionShares/value", "0")))
                except ValueError:
                    shares = 0

                try:
                    price_str = text(transaction, "transactionAmounts/transactionPricePerShare/value")
                    price = float(price_str) if price_str else None
                except ValueError:
                    price = None

                security_title = text(transaction, "securityTitle/value")
                transaction_code = text(transaction, "transactionCoding/transactionCode")

                transactions.append(SECForm4(
                    issuer_cik=issuer_cik,
                    issuer_name=issuer_name,
                    reporter_cik=reporter_cik,
                    reporter_name=reporter_name,
                    transaction_date=transaction_date,
                    transaction_code=transaction_code,
                    shares=shares,
                    price=price,
                    security_title=security_title,
                    transaction_type=transaction_type,
                    ownership_nature=ownership_nature,
                    form_url=form_url,
                    filing_date=filed_on,
                ))

        if not transactions:
            logger.warning("No Form 4 transactions parsed from %s", form_url)

        return transactions

    def collect_and_queue(self, company_ciks: list):
        """Collect SEC Form 4 data for companies and queue for DB insertion."""
        for cik in company_ciks:
            try:
                filings = self.fetch_recent_filings(cik)
                for form_url, xml_content, filing_date in filings:
                    try:
                        form4_items = self.parse_form4_xml(xml_content, form_url=form_url, filing_date=filing_date)
                        for form4_data in form4_items:
                            self.queue.add_to_queue(form4_data)
                    except Exception as e:
                        logger.error("Error parsing Form 4 from %s: %s", form_url, e)
            except Exception as e:
                logger.error("Error collecting SEC data for CIK %s: %s", cik, e)


if __name__ == "__main__":
    from config.tickers import get_all_ciks
    sec_module = SECForm4Module()
    ciks = get_all_ciks()
    sec_module.collect_and_queue(ciks)
