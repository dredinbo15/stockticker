"""
Stock model for Neo4j database operations.
"""

from config.database import get_neo4j_session
from typing import List, Dict, Optional

class Stock:
    def __init__(self, symbol: str, name: str = None, sector: str = None, price: float = None, price_timestamp: str = None):
        self.symbol = symbol
        self.name = name
        self.sector = sector
        self.price = price
        self.price_timestamp = price_timestamp

    @staticmethod
    def create_stock(symbol: str, name: str = None, sector: str = None, price: float = None, price_timestamp: str = None):
        with get_neo4j_session() as session:
            query = """
            MERGE (s:Stock {symbol: $symbol})
            SET s.name = COALESCE(s.name, $name),
                s.sector = COALESCE(s.sector, $sector)
            """
            params = {"symbol": symbol, "name": name, "sector": sector}
            if price is not None:
                query += ", s.price = $price, s.price_timestamp = $price_timestamp"
                params["price"] = price
                params["price_timestamp"] = price_timestamp

            query += "\nRETURN s.symbol AS symbol, s.name AS name, s.sector AS sector, s.price AS price, s.price_timestamp AS price_timestamp"
            result = session.run(query, **params)
            record = result.single()
            return Stock(
                symbol=record["symbol"],
                name=record["name"],
                sector=record["sector"],
                price=record.get("price"),
                price_timestamp=record.get("price_timestamp"),
            )

    @staticmethod
    def get_stock(symbol: str):
        with get_neo4j_session() as session:
            query = "MATCH (s:Stock {symbol: $symbol}) RETURN s"
            result = session.run(query, symbol=symbol)
            record = result.single()
            if record:
                stock_data = record["s"]
                return Stock(
                    symbol=stock_data["symbol"],
                    name=stock_data.get("name"),
                    sector=stock_data.get("sector"),
                    price=stock_data.get("price"),
                    price_timestamp=stock_data.get("price_timestamp"),
                )
            return None

    @staticmethod
    def get_all_stocks(limit: int = 100, skip: int = 0) -> List[Dict]:
        with get_neo4j_session() as session:
            query = """
            MATCH (s:Stock)
            RETURN s.symbol AS symbol, s.name AS name, s.sector AS sector,
                   s.price AS price, s.price_timestamp AS price_timestamp
            ORDER BY s.symbol SKIP $skip LIMIT $limit
            """
            result = session.run(query, limit=limit, skip=skip)
            return [record.data() for record in result]

    @staticmethod
    def update_price(symbol: str, price: float, price_timestamp: str):
        with get_neo4j_session() as session:
            query = """
            MERGE (s:Stock {symbol: $symbol})
            SET s.price = $price,
                s.price_timestamp = $price_timestamp
            RETURN s.symbol AS symbol, s.price AS price, s.price_timestamp AS price_timestamp
            """
            result = session.run(query, symbol=symbol, price=price, price_timestamp=price_timestamp)
            record = result.single()
            return Stock(symbol=record["symbol"], price=record.get("price"), price_timestamp=record.get("price_timestamp"))

    def save(self):
        return self.create_stock(self.symbol, self.name, self.sector, self.price, self.price_timestamp)