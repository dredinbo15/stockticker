"""
Stock ticker configuration with CIK mappings.
Contains 50 major US stock tickers across 12 sectors with their SEC CIK numbers.
"""

# 50 Stock Tickers Organized by Sector with SEC CIK Numbers
SYMBOL_CIK_MAP = {
    # Information Technology (5)
    "AAPL": "320193",      # Apple
    "MSFT": "789019",      # Microsoft
    "NVDA": "1045810",     # NVIDIA
    "AVGO": "1391904",     # Broadcom
    "CSCO": "858877",      # Cisco
    
    # Communication Services (4)
    "GOOGL": "1652044",    # Alphabet
    "META": "1326801",     # Meta Platforms
    "NFLX": "1065280",     # Netflix
    "DIS": "1001085",      # Disney
    
    # Consumer Discretionary (5)
    "AMZN": "1018724",     # Amazon
    "TSLA": "1318605",     # Tesla
    "HD": "354950",        # Home Depot
    "NKE": "320187",       # Nike
    "MCD": "63908",        # McDonald's
    
    # Consumer Staples (4)
    "WMT": "104169",       # Walmart
    "PG": "80424",         # Procter & Gamble
    "KO": "21344",         # Coca-Cola
    "COST": "909832",      # Costco
    
    # Financials (5)
    "JPM": "19617",        # JPMorgan Chase
    "BAC": "70858",        # Bank of America
    "GS": "886676",        # Goldman Sachs
    "V": "1144659",        # Visa
    "MA": "1141391",       # Mastercard
    
    # Healthcare (5)
    "JNJ": "200406",       # Johnson & Johnson
    "UNH": "731766",       # UnitedHealth
    "LLY": "319686",       # Eli Lilly
    "PFE": "78003",        # Pfizer
    "ABBV": "1551152",     # AbbVie
    
    # Industrials (5)
    "CAT": "18230",        # Caterpillar
    "BA": "12927",         # Boeing
    "GE": "40545",         # General Electric
    "UPS": "1090727",      # United Parcel Service
    "RTX": "1823424",      # Raytheon Technologies
    
    # Energy (4)
    "XOM": "34088",        # ExxonMobil
    "CVX": "93410",        # Chevron
    "COP": "1163165",      # ConocoPhillips
    "SLB": "87350",        # Schlumberger
    
    # Materials (3)
    "LIN": "60086",        # Linde
    "FCX": "831706",       # Freeport-McMoRan
    "NEM": "1164727",      # Newmont
    
    # Utilities (3)
    "NEE": "1001039",      # NextEra Energy
    "DUK": "92046",        # Duke Energy
    "SO": "51143",         # Southern Company
    
    # Real Estate (3)
    "PLD": "1045609",      # Prologis
    "AMT": "1053507",      # American Tower
    "EQIX": "1101575",     # Equinix
    
    # Transportation/Rails (4)
    "UNP": "100885",       # Union Pacific
    "CSX": "1051471",      # CSX Corporation
    "NSC": "702165",       # Norfolk Southern
    "FDX": "1048911",      # FedEx
}

# List of all ticker symbols (50 total)
TICKER_SYMBOLS = sorted(SYMBOL_CIK_MAP.keys())

# Sentiment mapping for enrichment
SENTIMENT_MAP = {
    "positive": 1,
    "neutral": 0,
    "negative": -1,
}


def get_all_ciks():
    """Get all CIK numbers for the tracked companies."""
    return list(SYMBOL_CIK_MAP.values())


def get_all_symbols():
    """Get all stock symbols for the tracked companies."""
    return TICKER_SYMBOLS


def get_cik_from_symbol(symbol: str) -> str:
    """Get CIK from stock symbol."""
    return SYMBOL_CIK_MAP.get(symbol.upper())


def get_symbol_from_cik(cik: str) -> str:
    """Get stock symbol from CIK."""
    for symbol, c in SYMBOL_CIK_MAP.items():
        if c == cik:
            return symbol
    return None
