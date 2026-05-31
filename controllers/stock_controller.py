"""
Stock controller for handling stock-related operations.
"""

from models.stock import Stock
from typing import List, Dict, Optional


class StockController:
    async def get_all_stocks(self, limit: int = 100, skip: int = 0) -> List[Dict]:
        return Stock.get_all_stocks(limit=limit, skip=skip)

    async def get_stock(self, symbol: str) -> Optional[Stock]:
        return Stock.get_stock(symbol)

    async def create_stock(self, symbol: str, name: str = None, sector: str = None) -> Stock:
        stock = Stock(symbol, name, sector)
        return stock.save()
