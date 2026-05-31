"""
SEC 8-K filing model for significant event reports.
"""

import hashlib
from config.database import get_neo4j_session
from datetime import datetime
from typing import Dict, List


class SEC8K:
    def __init__(self, issuer_cik: str, issuer_name: str, filing_date: datetime,
                 description: str, content: str, item_summary: str = None,
                 form_url: str = None, report_hash: str = None,
                 llm_summary: str = None, key_items: str = None,
                 impact_assessment: str = None):
        self.issuer_cik = issuer_cik
        self.issuer_name = issuer_name
        self.filing_date = filing_date
        self.description = description
        self.content = content
        self.item_summary = item_summary
        self.form_url = form_url
        self.llm_summary = llm_summary
        self.key_items = key_items
        self.impact_assessment = impact_assessment
        self.report_hash = report_hash or self._create_hash()

    def _create_hash(self) -> str:
        payload = "|".join([
            self.issuer_cik or "",
            self.issuer_name or "",
            self.filing_date.isoformat() if self.filing_date else "",
            self.form_url or "",
            (self.content or "")[:2000],
        ])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def save(self):
        with get_neo4j_session() as session:
            query = """
            MERGE (c:Company {cik: $issuer_cik})
            SET c.name = COALESCE(c.name, $issuer_name)
            WITH c
            MERGE (r:EightKReport {report_hash: $report_hash})
            ON CREATE SET
                r.issuer_name = $issuer_name,
                r.filing_date = $filing_date,
                r.description = $description,
                r.item_summary = $item_summary,
                r.content = $content,
                r.form_url = $form_url,
                r.llm_summary = $llm_summary,
                r.key_items = $key_items,
                r.impact_assessment = $impact_assessment
            MERGE (r)-[:ABOUT_COMPANY]->(c)
            RETURN r
            """
            result = session.run(query,
                               issuer_cik=self.issuer_cik,
                               issuer_name=self.issuer_name,
                               report_hash=self.report_hash,
                               filing_date=self.filing_date.isoformat(),
                               description=self.description,
                               item_summary=self.item_summary,
                               content=self.content,
                               form_url=self.form_url,
                               llm_summary=self.llm_summary,
                               key_items=self.key_items,
                               impact_assessment=self.impact_assessment)
            return result.single()

    @staticmethod
    def get_reports_by_company(cik: str, limit: int = 20):
        with get_neo4j_session() as session:
            query = """
            MATCH (r:EightKReport)-[:ABOUT_COMPANY]->(c:Company {cik: $cik})
            RETURN r ORDER BY r.filing_date DESC LIMIT $limit
            """
            result = session.run(query, cik=cik, limit=limit)
            return [record["r"] for record in result]
