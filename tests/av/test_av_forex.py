import os

import pandas as pd
import pytest

from pandas_datareader import data as web
from tests._backends import BACKENDS, as_narwhals, skip_unless_installed
from tests._mock import make_response, patch_session_get

TEST_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")
TEST_API_KEY = None if not TEST_API_KEY else TEST_API_KEY


@pytest.mark.network
@pytest.mark.requires_api_key
@pytest.mark.alpha_vantage
@pytest.mark.skipif(TEST_API_KEY is None, reason="ALPHAVANTAGE_API_KEY not set")
class TestAlphaVantageForex:
    @classmethod
    def setup_class(cls):
        pytest.importorskip("lxml")

    @pytest.mark.skipif(TEST_API_KEY is None, reason="ALPHAVANTAGE_API_KEY not set")
    def test_bad_pair_format(self):
        with pytest.raises(ValueError):
            web.DataReader("BAD FORMAT", "av-forex")

    @pytest.mark.skipif(TEST_API_KEY is None, reason="ALPHAVANTAGE_API_KEY not set")
    def test_bad_pairs_format(self):
        with pytest.raises(ValueError):
            web.DataReader(["USD/JPY", "BAD FORMAT"], "av-forex")

    @pytest.mark.skipif(TEST_API_KEY is None, reason="ALPHAVANTAGE_API_KEY not set")
    def test_one_pair(self):
        df = web.DataReader("USD/EUR", "av-forex", retry_count=6, pause=20.5)
        assert isinstance(df, pd.DataFrame)
        assert df.loc["To_Currency Name"][0] == "Euro"
        assert df.loc["Time Zone"][0] == "UTC"

    @pytest.mark.skipif(TEST_API_KEY is None, reason="ALPHAVANTAGE_API_KEY not set")
    def test_multiple_pairs(self):
        pairs = ["USD/JPY", "EUR/JPY"]
        df = web.DataReader(pairs, "av-forex", retry_count=6, pause=20.5)
        assert isinstance(df, pd.DataFrame)
        assert df.columns.equals(pd.Index(pairs))


_RATE_PAYLOAD = {
    "Realtime Currency Exchange Rate": {
        "1. From_Currency Code": "USD",
        "2. From_Currency Name": "United States Dollar",
        "3. To_Currency Code": "EUR",
        "4. To_Currency Name": "Euro",
        "5. Exchange Rate": "0.9000",
        "6. Last Refreshed": "2020-01-02 00:00:01",
        "7. Time Zone": "UTC",
        "8. Bid Price": "0.8999",
        "9. Ask Price": "0.9001",
    }
}


@pytest.mark.stable
class TestAlphaVantageForexOffline:
    def _patch(self, monkeypatch):
        patch_session_get(monkeypatch, {"alphavantage.co": make_response(json=_RATE_PAYLOAD)})

    def test_pandas_fields_by_pair(self, monkeypatch):
        self._patch(monkeypatch)
        df = web.DataReader("USD/EUR", "av-forex", api_key="fake")
        assert list(df.columns) == ["USD/EUR"]
        assert df.loc["To_Currency Name", "USD/EUR"] == "Euro"
        assert df.loc["Exchange Rate", "USD/EUR"] == "0.9000"

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_tidy_row_per_pair(self, monkeypatch, output_type):
        skip_unless_installed(output_type)
        self._patch(monkeypatch)
        tidy = as_narwhals(web.DataReader("USD/EUR", "av-forex", api_key="fake", output_type=output_type))

        assert tidy.columns[0] == "Pair"
        assert tidy["Pair"].to_list() == ["USD/EUR"]
        assert {"Exchange Rate", "To_Currency Name"} <= set(tidy.columns)
        assert tidy["Exchange Rate"].to_list() == ["0.9000"]
