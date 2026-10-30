from datetime import datetime, timezone

from modules.sec_client import raw_document_name
from modules.sec_form4 import sec_collector
from modules.sec_form4.sec_collector import SECForm4Module
from modules.sec_8k.sec8k_collector import SEC8KModule

FORM4_XML = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer><issuerCik>0000320193</issuerCik><issuerName>Apple Inc.</issuerName></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerCik>0001214156</rptOwnerCik><rptOwnerName>COOK TIMOTHY D</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isOfficer>1</isOfficer></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>2026-10-01</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>1000</value></transactionShares>
        <transactionPricePerShare><value>230.5</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts><transactionShares><value>50</value></transactionShares></transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""


def test_raw_document_name_strips_xsl_prefix():
    assert raw_document_name("xslF345X05/wk-form4_1.xml") == "wk-form4_1.xml"
    assert raw_document_name("form4.xml") == "form4.xml"
    assert raw_document_name("aapl-20261001.htm") == "aapl-20261001.htm"


class FakeResponse:
    def __init__(self, payload=None, text=""):
        self._payload = payload
        self.text = text

    def json(self):
        return self._payload


def test_form4_fetch_uses_raw_xml_url(monkeypatch):
    submissions = {"filings": {"recent": {
        "form": ["8-K", "4"],
        "accessionNumber": ["0000320193-26-000001", "0000320193-26-000002"],
        "primaryDocument": ["a.htm", "xslF345X05/wk-form4.xml"],
        "filingDate": ["2026-10-01", "2026-10-03"],
    }}}
    requested = []

    def fake_get(url, timeout=15):
        requested.append(url)
        return FakeResponse(submissions) if "submissions" in url else FakeResponse(text=FORM4_XML)

    monkeypatch.setattr(sec_collector, "sec_get", fake_get)
    filings = SECForm4Module().fetch_recent_filings("320193")

    assert requested[-1] == "https://www.sec.gov/Archives/edgar/data/320193/000032019326000002/wk-form4.xml"
    assert filings == [(requested[-1], FORM4_XML, "2026-10-03")]


def test_parse_form4_xml():
    items = SECForm4Module().parse_form4_xml(FORM4_XML, form_url="u", filing_date="2026-10-03")
    assert len(items) == 2
    sale, buy = items
    assert sale.issuer_cik == "320193"
    assert sale.reporter_cik == "1214156"
    assert sale.transaction_code == "S"
    assert sale.shares == 1000 and sale.price == 230.5
    assert sale.transaction_date == datetime(2026, 10, 1, tzinfo=timezone.utc)
    assert sale.filing_date == datetime(2026, 10, 3, tzinfo=timezone.utc)
    # Missing transaction date falls back to the filing date, not "now".
    assert buy.transaction_date == datetime(2026, 10, 3, tzinfo=timezone.utc)


def test_parse_8k_uses_filing_date_and_skips_scripts():
    html = ("<html><head><style>.x{}</style><script>var a=1;</script></head><body>"
            "Item 2.02 Results of Operations. Apple announced Q4. Item 9.01 Exhibits</body></html>")
    report = SEC8KModule().parse_8k_document(html, "0000320193", "Apple", form_url="u", filing_date="2026-10-30")
    assert report.filing_date == datetime(2026, 10, 30, tzinfo=timezone.utc)
    assert report.issuer_cik == "320193"
    assert "var a" not in report.content and ".x{}" not in report.content
    assert report.item_summary.startswith("Item 2.02")
