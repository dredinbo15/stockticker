"""
SEC Form 4 data model for insider trading information.
"""

import hashlib
from config.database import get_neo4j_session
from config.tickers import normalize_cik
from datetime import datetime


class SECForm4:
    def __init__(self, issuer_cik: str, issuer_name: str, reporter_cik: str,
                 reporter_name: str, transaction_date: datetime,
                 transaction_code: str, shares: int, price: float = None,
                 security_title: str = None, transaction_type: str = None,
                 ownership_nature: str = None, form_url: str = None):
        self.issuer_cik = normalize_cik(issuer_cik)
        self.issuer_name = issuer_name
        self.reporter_cik = normalize_cik(reporter_cik)
        self.reporter_name = reporter_name
        self.transaction_date = transaction_date
        self.transaction_code = transaction_code
        self.shares = shares
        self.price = price
        self.security_title = security_title
        self.transaction_type = transaction_type
        self.ownership_nature = ownership_nature
        self.form_url = form_url
        self.transaction_key = self._build_transaction_key()
        self.transaction_hash = self._create_hash()

    def _build_transaction_key(self) -> str:
        return "|".join([
            str(self.form_url or ""),
            str(self.reporter_cik or ""),
            str(self.transaction_date.isoformat()),
            str(self.transaction_code or ""),
            str(self.security_title or ""),
            str(self.shares or ""),
            str(self.price or "")
        ])

    def _create_hash(self) -> str:
        return hashlib.sha256(self.transaction_key.encode("utf-8")).hexdigest()


    def save(self):
        if not self.form_url:
            raise ValueError("SECForm4.form_url is required to prevent duplicate transactions.")

        with get_neo4j_session() as session:
            query = """
            MERGE (i:Company {cik: $issuer_cik})
            SET i.name = COALESCE(i.name, $issuer_name)
            WITH i
            MERGE (r:Insider {cik: $reporter_cik})
            SET r.name = COALESCE(r.name, $reporter_name)
            WITH i, r
            MERGE (t:Transaction {transaction_hash: $transaction_hash})
            ON CREATE SET
                t.transaction_key = $transaction_key,
                t.form_url = $form_url,
                t.security_title = $security_title,
                t.transaction_type = $transaction_type,
                t.ownership_nature = $ownership_nature,
                t.date = $date,
                t.code = $code,
                t.shares = $shares,
                t.price = $price
            MERGE (r)-[:FILED]->(t)
            MERGE (t)-[:FOR_COMPANY]->(i)
            RETURN t
            """
            result = session.run(query,
                               issuer_cik=self.issuer_cik,
                               issuer_name=self.issuer_name,
                               reporter_cik=self.reporter_cik,
                               reporter_name=self.reporter_name,
                               transaction_hash=self.transaction_hash,
                               transaction_key=self.transaction_key,
                               form_url=self.form_url,
                               security_title=self.security_title,
                               transaction_type=self.transaction_type,
                               ownership_nature=self.ownership_nature,
                               date=self.transaction_date.isoformat(),
                               code=self.transaction_code,
                               shares=self.shares,
                               price=self.price)
            return result.single()

    @staticmethod
    def get_transactions_by_company(cik: str, limit: int = 50):
        with get_neo4j_session() as session:
            query = """
            MATCH (r:Insider)-[:FILED]->(t:Transaction)-[:FOR_COMPANY]->(c:Company {cik: $cik})
            RETURN r.name AS insider, t ORDER BY t.date DESC LIMIT $limit
            """
            result = session.run(query, cik=normalize_cik(cik), limit=limit)
            return [record.data() for record in result]
