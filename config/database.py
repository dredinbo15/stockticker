"""Database configuration for Neo4j connection."""

import os
import threading

from neo4j import GraphDatabase
from dotenv import load_dotenv

load_dotenv()

class Neo4jConnection:
    def __init__(self):
        self.uri = os.getenv('NEO4J_URI', "bolt://localhost:7687")
        self.user = os.getenv('NEO4J_USER', "neo4j")
        self.password = os.getenv('NEO4J_PASSWORD')
        self.driver = None
        self._lock = threading.Lock()

    def connect(self):
        with self._lock:
            if self.driver is not None:
                return
            if not self.password:
                raise EnvironmentError("NEO4J_PASSWORD not found in environment variables.")
            driver = GraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password),
                max_connection_pool_size=50,
            )
            driver.verify_connectivity()
            self.driver = driver

    def close(self):
        if self.driver:
            self.driver.close()
            self.driver = None

    def get_session(self):
        # Connect lazily so processes that never call init_neo4j() (Celery
        # workers, one-off scripts) can still talk to the database.
        if self.driver is None:
            self.connect()
        return self.driver.session()

# Global connection instance
neo4j_conn = Neo4jConnection()

def init_neo4j():
    neo4j_conn.connect()
    # Create constraints and indexes
    with neo4j_conn.get_session() as session:
        session.run("CREATE CONSTRAINT stock_symbol IF NOT EXISTS FOR (s:Stock) REQUIRE s.symbol IS UNIQUE")
        session.run("CREATE CONSTRAINT news_url IF NOT EXISTS FOR (n:NewsArticle) REQUIRE n.url IS UNIQUE")
        session.run("CREATE CONSTRAINT news_hash IF NOT EXISTS FOR (n:NewsArticle) REQUIRE n.article_hash IS UNIQUE")
        session.run("DROP CONSTRAINT transaction_form_url IF EXISTS")
        session.run("CREATE CONSTRAINT transaction_hash IF NOT EXISTS FOR (t:Transaction) REQUIRE t.transaction_hash IS UNIQUE")
        session.run("CREATE CONSTRAINT eightk_hash IF NOT EXISTS FOR (r:EightKReport) REQUIRE r.report_hash IS UNIQUE")
        session.run("CREATE CONSTRAINT price_key IF NOT EXISTS FOR (p:PricePoint) REQUIRE p.price_key IS UNIQUE")
        session.run("CREATE INDEX stock_name IF NOT EXISTS FOR (s:Stock) ON (s.name)")
        session.run("CREATE INDEX weather_location IF NOT EXISTS FOR (w:WeatherData) ON (w.location)")
        session.run("CREATE INDEX transaction_date IF NOT EXISTS FOR (t:Transaction) ON (t.date)")
        session.run("CREATE INDEX price_date IF NOT EXISTS FOR (p:PricePoint) ON (p.date)")
        # Seed the tracked tickers as Stock nodes (with their sector and name)
        # so news MENTIONS edges and the model's (s:Stock) matches have
        # something to attach to before any price-collection job has run.
        from config.tickers import SYMBOL_NAME_MAP, SYMBOL_SECTOR_MAP
        session.run(
            """
            UNWIND $rows AS row
            MERGE (s:Stock {symbol: row.symbol})
            SET s.sector = coalesce(s.sector, row.sector),
                s.name = coalesce(s.name, row.name)
            """,
            rows=[
                {"symbol": sym, "sector": sec, "name": SYMBOL_NAME_MAP.get(sym)}
                for sym, sec in SYMBOL_SECTOR_MAP.items()
            ],
        )

def get_neo4j_session():
    return neo4j_conn.get_session()
