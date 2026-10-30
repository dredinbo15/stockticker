"""
Daily price history model (one PricePoint node per symbol per trading day).
"""

from typing import Dict, List, Optional

from config.database import get_neo4j_session


class PricePoint:
    @staticmethod
    def save_many(symbol: str, rows: List[Dict]) -> int:
        """Upsert daily OHLCV rows for a symbol.

        Each row needs: date (YYYY-MM-DD), open, high, low, close, volume.
        """
        if not rows:
            return 0
        with get_neo4j_session() as session:
            query = """
            MERGE (s:Stock {symbol: $symbol})
            WITH s
            UNWIND $rows AS row
            MERGE (p:PricePoint {price_key: $symbol + '|' + row.date})
            SET p.symbol = $symbol,
                p.date = row.date,
                p.open = row.open,
                p.high = row.high,
                p.low = row.low,
                p.close = row.close,
                p.volume = row.volume
            MERGE (s)-[:HAS_PRICE]->(p)
            RETURN count(p) AS saved
            """
            result = session.run(query, symbol=symbol, rows=rows)
            return result.single()["saved"]

    @staticmethod
    def get_history(symbols: Optional[List[str]] = None, since: Optional[str] = None) -> List[Dict]:
        """Return daily rows ordered by symbol and date.

        `since` is an inclusive YYYY-MM-DD lower bound.
        """
        with get_neo4j_session() as session:
            query = """
            MATCH (p:PricePoint)
            WHERE ($symbols IS NULL OR p.symbol IN $symbols)
              AND ($since IS NULL OR p.date >= $since)
            RETURN p.symbol AS symbol, p.date AS date, p.open AS open,
                   p.high AS high, p.low AS low, p.close AS close,
                   p.volume AS volume
            ORDER BY symbol, date
            """
            result = session.run(query, symbols=symbols, since=since)
            return [record.data() for record in result]
