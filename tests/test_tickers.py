from config.tickers import (
    SYMBOL_CIK_MAP,
    SYMBOL_NAME_MAP,
    SYMBOL_SECTOR_MAP,
    TICKER_SYMBOLS,
    get_symbol_from_cik,
    normalize_cik,
    normalize_symbols,
)


def test_every_symbol_has_cik_sector_and_name():
    assert len(TICKER_SYMBOLS) == 50
    assert set(SYMBOL_CIK_MAP) == set(SYMBOL_SECTOR_MAP) == set(SYMBOL_NAME_MAP)


def test_normalize_cik_strips_padding():
    assert normalize_cik("0000320193") == "320193"
    assert normalize_cik(320193) == "320193"
    assert normalize_cik(None) is None


def test_get_symbol_from_padded_cik():
    assert get_symbol_from_cik("0000320193") == "AAPL"


def test_normalize_symbols_cleans_llm_output():
    assert normalize_symbols(["$aapl", "MSFT.O", "NASDAQ:NVDA", "Apple", "AAPL", None]) == ["AAPL", "MSFT", "NVDA"]
    assert normalize_symbols("tsla, xyz ,ko") == ["TSLA", "KO"]
    assert normalize_symbols(None) == []
