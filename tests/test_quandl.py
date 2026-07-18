import os

import narwhals.stable.v2 as nw
import pandas as pd
import pytest

from pandas_datareader import data as web
from pandas_datareader.compat import assert_frame_equal
from pandas_datareader.quandl import QuandlReader
from tests._backends import BACKENDS, as_narwhals, skip_unless_installed
from tests._mock import patch_session_get

TEST_API_KEY = os.getenv("QUANDL_API_KEY")
# Ensure blank TEST_API_KEY not used in pull request
TEST_API_KEY = None if not TEST_API_KEY else TEST_API_KEY


# These are live tests against the keyed Quandl API: deselected by default (like every other
# network test) and additionally skipped when no key is configured. Run with ``-m network`` and
# QUANDL_API_KEY set; the weekly refresh workflow records fixtures when the secret is present.
@pytest.mark.network
@pytest.mark.requires_api_key
@pytest.mark.quandl
@pytest.mark.skipif(TEST_API_KEY is None, reason="QUANDL_API_KEY not set")
class TestQuandl:
    # we test data from 10 years back where possible, 2 years otherwise, or...
    start10 = "2007-01-01"  # over ten years back
    end10 = "2007-01-05"
    day10 = "2007-01-04"
    start2 = "2015-01-01"  # over two years back
    end2 = "2015-01-05"
    day2 = "2015-01-02"

    def check_headers(self, df, expected_cols):
        expected_cols = frozenset(expected_cols)
        act_cols = frozenset(df.columns.tolist())
        assert expected_cols == act_cols, "unexpected cols: " + str(act_cols)

    def test_db_wiki_us(self):
        df = web.DataReader("F", "quandl", self.start10, self.end10, api_key=TEST_API_KEY)
        self.check_headers(
            df,
            [
                "Open",
                "High",
                "Low",
                "Close",
                "Volume",
                "ExDividend",
                "SplitRatio",
                "AdjOpen",
                "AdjHigh",
                "AdjLow",
                "AdjClose",
                "AdjVolume",
            ],
        )
        assert df.Close.at[pd.to_datetime(self.day10)] == 7.70

    def test_db_fse_frankfurt(self):
        # ALV_X: Allianz SE
        df = web.DataReader("FSE/ALV_X", "quandl", self.start10, self.end10, api_key=TEST_API_KEY)
        self.check_headers(
            df,
            [
                "Open",
                "High",
                "Low",
                "Close",
                "Change",
                "TradedVolume",
                "Turnover",
                "LastPriceoftheDay",
                "DailyTradedUnits",
                "DailyTurnover",
            ],
        )
        assert df.Close.at[pd.to_datetime(self.day10)] == 159.45

    def test_fse_eon(self):
        # EON_X: E.on Se
        df = web.DataReader("FSE/EON_X", "quandl", self.start2, self.end2, api_key=TEST_API_KEY)
        self.check_headers(
            df,
            [
                "Low",
                "LastPriceoftheDay",
                "Turnover",
                "Open",
                "DailyTurnover",
                "TradedVolume",
                "Change",
                "DailyTradedUnits",
                "Close",
                "High",
            ],
        )
        assert df.Close.at[pd.to_datetime(self.day2)] == 14.03

    def test_db_euronext_be_fr_nl_pt(self):
        # FP: Total SA
        # as of 2017-06-11, some datasets end a few months after their start,
        # e.g. ALVD, BASD
        df = web.DataReader("EURONEXT/FP", "quandl", self.start2, self.end2, api_key=TEST_API_KEY)
        self.check_headers(df, ["Open", "High", "Low", "Last", "Turnover", "Volume"])
        assert df.Last.at[pd.to_datetime(self.day2)] == 42.525
        df2 = web.DataReader("FP.FR", "quandl", self.start2, self.end2)
        assert (df.Last == df2.Last).all()

    def test_hk_hsbc_uk(self):
        # 00005: HSBC
        df = web.DataReader("HKEX/00005", "quandl", self.start2, self.end2, api_key=TEST_API_KEY)
        self.check_headers(
            df,
            [
                "NominalPrice",
                "NetChange",
                "Change",
                "Bid",
                "Ask",
                "PEx",
                "High",
                "Low",
                "PreviousClose",
                "ShareVolume000",
                "Turnover000",
                "LotSize",
            ],
        )
        # as of 2017-06-11, Price == LastClose, all others are NaN
        assert df.NominalPrice.at[pd.to_datetime(self.day2)] == 74.0

    def test_db_nse_in(self):
        # TCS: Tata Consutancy Services
        df = web.DataReader("NSE/TCS", "quandl", self.start10, self.end10, api_key=TEST_API_KEY)
        self.check_headers(
            df,
            [
                "Open",
                "High",
                "Low",
                "Last",
                "Close",
                "TotalTradeQuantity",
                "TurnoverLacs",
            ],
        )
        assert df.Close.at[pd.to_datetime(self.day10)] == 1259.05

    def test_db_tse_jp(self):
        # TSE/6758: Sony Corp.
        df = web.DataReader("TSE/6758", "quandl", self.start10, self.end10, api_key=TEST_API_KEY)
        self.check_headers(df, ["Open", "High", "Low", "Close", "Volume"])
        assert df.Close.at[pd.to_datetime(self.day10)] == 5190.0

        df2 = web.get_data_quandl("TSE/6758", self.start10, self.end10, api_key=TEST_API_KEY)
        assert_frame_equal(df, df2)

    def test_db_hkex_cn(self):
        # HKEX/00941: China Mobile
        df = web.DataReader("HKEX/00941", "quandl", self.start2, self.end2, api_key=TEST_API_KEY)
        self.check_headers(
            df,
            [
                "NominalPrice",
                "NetChange",
                "Change",
                "Bid",
                "Ask",
                "PEx",
                "High",
                "Low",
                "PreviousClose",
                "ShareVolume000",
                "Turnover000",
                "LotSize",
            ],
        )
        assert df.High.at[pd.to_datetime(self.day2)] == 91.9


@pytest.mark.stable
class TestQuandlBackends:
    # Quandl requires an API key and can't be recorded, so a hand-written sample of the dataset
    # CSV format pins the tidy schema only.
    csv_body = b"Date,Open,Adj. Close\n2020-01-03,10.5,10.6\n2020-01-02,10.0,10.1\n"

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_single_symbol_tidy_schema(self, monkeypatch, output_type):
        skip_unless_installed(output_type)
        patch_session_get(monkeypatch, {"quandl.com": self.csv_body})
        reader = QuandlReader("WIKI/AAPL", api_key="fake-key", output_type=output_type)
        tidy = as_narwhals(reader.read())

        assert tidy.columns == ["Date", "Open", "AdjClose"]
        assert tidy.schema["Date"] == nw.Datetime
        assert tidy["Open"].to_list() == [10.0, 10.5]
