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

# Sector groupings for the tracked tickers — the source of truth for
# Stock.sector (the SYMBOL_CIK_MAP comments above are illustrative only).
SECTOR_SYMBOLS = {
    "Information Technology": ["AAPL", "MSFT", "NVDA", "AVGO", "CSCO"],
    "Communication Services": ["GOOGL", "META", "NFLX", "DIS"],
    "Consumer Discretionary": ["AMZN", "TSLA", "HD", "NKE", "MCD"],
    "Consumer Staples": ["WMT", "PG", "KO", "COST"],
    "Financials": ["JPM", "BAC", "GS", "V", "MA"],
    "Healthcare": ["JNJ", "UNH", "LLY", "PFE", "ABBV"],
    "Industrials": ["CAT", "BA", "GE", "UPS", "RTX"],
    "Energy": ["XOM", "CVX", "COP", "SLB"],
    "Materials": ["LIN", "FCX", "NEM"],
    "Utilities": ["NEE", "DUK", "SO"],
    "Real Estate": ["PLD", "AMT", "EQIX"],
    "Transportation/Rails": ["UNP", "CSX", "NSC", "FDX"],
}

# Reverse lookup: symbol -> sector
SYMBOL_SECTOR_MAP = {
    symbol: sector
    for sector, symbols in SECTOR_SYMBOLS.items()
    for symbol in symbols
}

# Sentiment mapping for enrichment
SENTIMENT_MAP = {
    "positive": 1,
    "neutral": 0,
    "negative": -1,
}


def normalize_cik(cik) -> str:
    """Return the canonical CIK form: digits with leading zeros stripped.

    SEC EDGAR returns CIKs zero-padded to 10 digits (e.g. '0000320193') in
    filing XML and the submissions API, while SYMBOL_CIK_MAP stores the
    unpadded form ('320193'). Normalizing everywhere ensures Company nodes,
    SEC lookups, and the model's insider labels all join on the same value.
    """
    if cik is None:
        return None
    digits = str(cik).strip().lstrip("0")
    return digits or "0"


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


def get_sector(symbol: str) -> str:
    """Get the sector for a stock symbol, or None if untracked."""
    return SYMBOL_SECTOR_MAP.get(symbol.upper())
