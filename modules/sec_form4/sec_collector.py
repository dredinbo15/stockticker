"""
SEC Form 4 data collection module.
Fetches insider trading data from SEC EDGAR and queues for database insertion.
"""

import logging
import requests
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
from queues.sec_form4_queue import SECForm4Queue
from models.sec_form4 import SECForm4
import xml.etree.ElementTree as ET
import os

# SEC requires a descriptive User-Agent per their crawling policy
_USER_AGENT = os.getenv('SEC_USER_AGENT', "stockticker contact@example.com")
_HEADERS = {"User-Agent": _USER_AGENT, "Accept-Encoding": "gzip, deflate"}


class SECForm4Module:
    def __init__(self):
        self.base_url = "https://www.sec.gov/Archives/edgar/data/"
        self.submissions_url = "https://data.sec.gov/submissions/CIK{}.json"
        self.queue = SECForm4Queue()

    def fetch_recent_filings(self, cik: str, limit: int = 10) -> list:
        """Fetch recent Form 4 XML contents for a company CIK via EDGAR submissions API."""
        padded_cik = cik.zfill(10)
        url = self.submissions_url.format(padded_cik)

        response = requests.get(url, headers=_HEADERS, timeout=10)
        response.raise_for_status()
        data = response.json()

        recent = data.get("filings", {}).get("recent", {})
        form_types = recent.get("form", [])
        accession_numbers = recent.get("accessionNumber", [])
        primary_documents = recent.get("primaryDocument", [])

        xml_contents = []
        for i, form_type in enumerate(form_types):
            if len(xml_contents) >= limit:
                break
            if form_type != "4":
                continue

            accession_no = accession_numbers[i].replace("-", "")
            doc = primary_documents[i]
            xml_url = f"{self.base_url}{cik}/{accession_no}/{doc}"

            try:
                xml_response = requests.get(xml_url, headers=_HEADERS, timeout=10)
                if xml_response.ok:
                    xml_contents.append((xml_url, xml_response.text))
            except requests.RequestException as e:
                logger.error(f"Error downloading filing {xml_url}: {e}")

        return xml_contents

    def parse_form4_xml(self, xml_content: str, form_url: str = "") -> list[SECForm4]:
        """Parse Form 4 XML into a list of SECForm4 objects."""
        root = ET.fromstring(xml_content)

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
                    transaction_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc) if date_str else datetime.now(timezone.utc)
                except ValueError:
                    transaction_date = datetime.now(timezone.utc)

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
                ))

        if not transactions:
            logger.warning("No Form 4 transactions parsed from %s", form_url)

        return transactions

    def collect_and_queue(self, company_ciks: list):
        """Collect SEC Form 4 data for companies and queue for DB insertion."""
        for cik in company_ciks:
            try:
                filings = self.fetch_recent_filings(cik)
                for form_url, xml_content in filings:
                    try:
                        form4_items = self.parse_form4_xml(xml_content, form_url=form_url)
                        for form4_data in form4_items:
                            self.queue.add_to_queue(form4_data)
                    except Exception as e:
                        logger.error(f"Error parsing Form 4 from {form_url}: {e}")
            except Exception as e:
                logger.error(f"Error collecting SEC data for CIK {cik}: {e}")


if __name__ == "__main__":
    from config.tickers import get_all_ciks
    sec_module = SECForm4Module()
    ciks = get_all_ciks()
    sec_module.collect_and_queue(ciks)
