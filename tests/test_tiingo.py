import os

import narwhals.stable.v2 as nw
import pandas as pd
import pytest

from kuznets.tiingo import (
    TiingoDailyReader,
    TiingoIEXHistoricalReader,
    TiingoMetaDataReader,
    TiingoQuoteReader,
    get_tiingo_symbols,
)
from tests._backends import BACKENDS, as_narwhals, skip_unless_installed
from tests._mock import make_response, patch_session_get

TEST_API_KEY = os.getenv("TIINGO_API_KEY")
# Ensure blank TEST_API_KEY not used in pull request
TEST_API_KEY = None if not TEST_API_KEY else TEST_API_KEY

syms = ["GOOG", ["GOOG", "XOM"]]
ids = list(map(str, syms))


@pytest.fixture(params=syms, ids=ids)
def symbols(request):
    return request.param


@pytest.mark.requires_api_key
@pytest.mark.network
@pytest.mark.skipif(TEST_API_KEY is None, reason="TIINGO_API_KEY not set")
def test_tiingo_quote(symbols):
    df = TiingoQuoteReader(symbols=symbols).read()
    assert isinstance(df, pd.DataFrame)
    if isinstance(symbols, str):
        symbols = [symbols]
    assert df.shape[0] == len(symbols)


@pytest.mark.requires_api_key
@pytest.mark.network
@pytest.mark.skipif(TEST_API_KEY is None, reason="TIINGO_API_KEY not set")
def test_tiingo_historical(symbols):
    df = TiingoDailyReader(symbols=symbols).read()
    assert isinstance(df, pd.DataFrame)
    if isinstance(symbols, str):
        symbols = [symbols]
    assert df.index.levels[0].shape[0] == len(symbols)


@pytest.mark.requires_api_key
@pytest.mark.network
@pytest.mark.skipif(TEST_API_KEY is None, reason="TIINGO_API_KEY not set")
def test_tiingo_iex_historical(symbols):
    df = TiingoIEXHistoricalReader(symbols=symbols).read()
    df.head()
    assert isinstance(df, pd.DataFrame)
    if isinstance(symbols, str):
        symbols = [symbols]
    assert df.index.levels[0].shape[0] == len(symbols)


@pytest.mark.requires_api_key
@pytest.mark.network
@pytest.mark.skipif(TEST_API_KEY is None, reason="TIINGO_API_KEY not set")
def test_tiingo_metadata(symbols):
    df = TiingoMetaDataReader(symbols=symbols).read()
    assert isinstance(df, pd.DataFrame)
    if isinstance(symbols, str):
        symbols = [symbols]
    assert df.shape[1] == len(symbols)


@pytest.mark.requires_api_key
def test_tiingo_no_api_key(symbols):
    try:
        from test.support.os_helper import EnvironmentVarGuard
    except ImportError:
        from test.support import EnvironmentVarGuard

    env = EnvironmentVarGuard()
    env.unset("TIINGO_API_KEY")
    with env:
        with pytest.raises(ValueError):
            TiingoMetaDataReader(symbols=symbols)


@pytest.mark.requires_api_key
@pytest.mark.network
def test_tiingo_stock_symbols():
    # Keyless endpoint; deselected by default so the offline suite never reaches the network.
    sym = get_tiingo_symbols()
    assert isinstance(sym, pd.DataFrame)


_DAILY_RECORDS = [
    {"date": "2020-01-02T00:00:00.000Z", "open": 10.0, "close": 10.4, "volume": 1000},
    {"date": "2020-01-03T00:00:00.000Z", "open": 10.5, "close": 11.0, "volume": 1200},
]
_METADATA = {"ticker": "AAPL", "name": "Apple Inc", "exchangeCode": "NASDAQ"}


@pytest.mark.stable
class TestTiingoOffline:
    def test_daily_pandas_symbol_date_index(self, monkeypatch):
        patch_session_get(monkeypatch, {"api.tiingo.com": make_response(json=_DAILY_RECORDS)})
        df = TiingoDailyReader(["AAPL", "MSFT"], api_key="fake").read()

        assert df.index.names == ["symbol", "date"]
        assert len(df) == 4
        assert sorted(set(df.index.get_level_values("symbol"))) == ["AAPL", "MSFT"]
        assert df.loc[("AAPL",), "close"].tolist() == [10.4, 11.0]

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_daily_tidy_row_per_record(self, monkeypatch, output_type):
        skip_unless_installed(output_type)
        patch_session_get(monkeypatch, {"api.tiingo.com": make_response(json=_DAILY_RECORDS)})
        as_pandas = TiingoDailyReader(["AAPL", "MSFT"], api_key="fake").read()
        tidy = as_narwhals(TiingoDailyReader(["AAPL", "MSFT"], api_key="fake", output_type=output_type).read())

        assert tidy.columns == ["symbol", "date", "open", "close", "volume"]
        assert tidy.schema["date"] == nw.Datetime
        assert len(tidy) == len(as_pandas)
        assert tidy["close"].to_list() == as_pandas["close"].tolist()

    def test_metadata_pandas_fields_by_symbol(self, monkeypatch):
        patch_session_get(monkeypatch, {"api.tiingo.com": make_response(json=_METADATA)})
        df = TiingoMetaDataReader(["AAPL", "MSFT"], api_key="fake").read()

        assert list(df.columns) == ["AAPL", "MSFT"]
        assert df.loc["name", "AAPL"] == "Apple Inc"

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_metadata_tidy_row_per_symbol(self, monkeypatch, output_type):
        skip_unless_installed(output_type)
        patch_session_get(monkeypatch, {"api.tiingo.com": make_response(json=_METADATA)})
        tidy = as_narwhals(TiingoMetaDataReader(["AAPL", "MSFT"], api_key="fake", output_type=output_type).read())

        assert tidy.columns == ["symbol", "ticker", "name", "exchangeCode"]
        assert tidy["symbol"].to_list() == ["AAPL", "MSFT"]
        assert tidy["name"].to_list() == ["Apple Inc", "Apple Inc"]

    @pytest.mark.parametrize("output_type", ["pandas", "polars"])
    def test_iex_historical_matches_daily_shape(self, monkeypatch, output_type):
        skip_unless_installed(output_type)
        patch_session_get(monkeypatch, {"api.tiingo.com": make_response(json=_DAILY_RECORDS)})
        result = TiingoIEXHistoricalReader(["AAPL"], api_key="fake", output_type=output_type).read()

        if output_type == "pandas":
            assert result.index.names == ["symbol", "date"]
            assert result["close"].tolist() == [10.4, 11.0]
        else:
            tidy = as_narwhals(result)
            assert tidy.columns == ["symbol", "date", "open", "close", "volume"]
            assert tidy["close"].to_list() == [10.4, 11.0]
