from datetime import datetime
import os

import narwhals.stable.v2 as nw
import pandas as pd
import pytest

from pandas_datareader import data as web
from pandas_datareader._utils import RemoteDataError
from tests._backends import BACKENDS, as_narwhals, skip_unless_installed
from tests._mock import make_response, patch_session_get

TEST_API_KEY = os.getenv("ALPHAVANTAGE_API_KEY")
TEST_API_KEY = None if not TEST_API_KEY else TEST_API_KEY


@pytest.mark.network
@pytest.mark.requires_api_key
@pytest.mark.alpha_vantage
@pytest.mark.skipif(TEST_API_KEY is None, reason="ALPHAVANTAGE_API_KEY not set")
class TestAVTimeSeries:
    @classmethod
    def setup_class(cls):
        pytest.importorskip("lxml")
        cls.col_index_adj = pd.Index(
            [
                "open",
                "high",
                "low",
                "close",
                "adjusted close",
                "volume",
                "dividend amount",
            ]
        )
        cls.col_index = pd.Index(["open", "high", "low", "close", "volume"])

    @property
    def start(self):
        return datetime(2015, 2, 9)

    @property
    def end(self):
        return datetime(2017, 5, 24)

    def test_av_bad_symbol(self):
        with pytest.raises((ValueError, RemoteDataError)):
            web.DataReader(
                "BADTICKER",
                "av-daily",
                start=self.start,
                end=self.end,
                retry_count=6,
                pause=20.5,
            )

    def test_av_daily(self):
        df = web.DataReader(
            "AAPL",
            "av-daily",
            start=self.start,
            end=self.end,
            retry_count=6,
            pause=20.5,
        )
        assert df.columns.equals(self.col_index)
        assert len(df) == 578
        assert df["volume"][-1] == 19118319

        expected1 = df.loc["2017-02-09"]
        assert expected1["close"] == 132.42
        assert expected1["high"] == 132.445

        expected2 = df.loc["2017-05-24"]
        assert expected2["close"] == 153.34
        assert expected2["high"] == 154.17

    def test_av_daily_adjusted(self):
        df = web.DataReader(
            "AAPL",
            "av-daily-adjusted",
            start=self.start,
            end=self.end,
            retry_count=6,
            pause=20.5,
        )
        assert df.columns.equals(
            pd.Index(
                [
                    "open",
                    "high",
                    "low",
                    "close",
                    "adjusted close",
                    "volume",
                    "dividend amount",
                    "split coefficient",
                ]
            )
        )
        assert len(df) == 578
        assert df["volume"][-1] == 19118319

        expected1 = df.loc["2017-02-09"]
        assert expected1["close"] == 132.42
        assert expected1["high"] == 132.445
        assert expected1["dividend amount"] == 0.57
        assert expected1["split coefficient"] == 1.0

        expected2 = df.loc["2017-05-24"]
        assert expected2["close"] == 153.34
        assert expected2["high"] == 154.17
        assert expected2["dividend amount"] == 0.00
        assert expected2["split coefficient"] == 1.0

    @staticmethod
    def _helper_df_weekly_monthly(df, adj=False):
        expected1 = df.loc["2015-02-27"]
        assert expected1["close"] == 128.46
        assert expected1["high"] == 133.60

        expected2 = df.loc["2017-03-31"]
        assert expected2["close"] == 143.66
        assert expected2["high"] == 144.5

    def test_av_weekly(self):
        df = web.DataReader(
            "AAPL",
            "av-weekly",
            start=self.start,
            end=self.end,
            retry_count=6,
            pause=20.5,
        )

        assert len(df) == 119
        assert df.iloc[0].name == pd.Timestamp("2015-02-13")
        assert df.iloc[-1].name == pd.Timestamp("2017-05-19")
        assert df.columns.equals(self.col_index)
        self._helper_df_weekly_monthly(df, adj=False)

    def test_av_weekly_adjusted(self):
        df = web.DataReader(
            "AAPL",
            "av-weekly-adjusted",
            start=self.start,
            end=self.end,
            retry_count=6,
            pause=20.5,
        )

        assert len(df) == 119
        assert df.iloc[0].name == pd.Timestamp("2015-02-13")
        assert df.iloc[-1].name == pd.Timestamp("2017-05-19")
        assert df.columns.equals(self.col_index_adj)
        self._helper_df_weekly_monthly(df, adj=True)

    def test_av_monthly(self):
        df = web.DataReader(
            "AAPL",
            "av-monthly",
            start=self.start,
            end=self.end,
            retry_count=6,
            pause=20.5,
        )

        assert len(df) == 27
        assert df.iloc[0].name == pd.Timestamp("2015-02-27")
        assert df.iloc[-1].name == pd.Timestamp("2017-04-28")
        assert df.columns.equals(self.col_index)
        self._helper_df_weekly_monthly(df, adj=False)

    def test_av_monthly_adjusted(self):
        df = web.DataReader(
            "AAPL",
            "av-monthly-adjusted",
            start=self.start,
            end=self.end,
            retry_count=6,
            pause=20.5,
        )

        assert df.columns.equals(self.col_index_adj)
        assert len(df) == 27
        assert df.iloc[0].name == pd.Timestamp("2015-02-27")
        assert df.iloc[-1].name == pd.Timestamp("2017-04-28")
        self._helper_df_weekly_monthly(df, adj=True)

    def test_av_intraday(self):
        # Not much available to test, but ensure close in length
        df = web.DataReader("AAPL", "av-intraday", retry_count=6, pause=20.5)

        assert len(df) >= 1
        assert "open" in df.columns
        assert "close" in df.columns

    def test_av_forex_daily(self):
        df = web.DataReader(
            "USD/JPY",
            "av-forex-daily",
            start=self.start,
            end=self.end,
            retry_count=6,
            pause=20.5,
        )
        assert df.columns.equals(self.col_index[:4])  # No volume col for forex
        assert len(df) == 598
        assert df.loc["2015-02-09"]["close"] == 118.6390
        assert df.loc["2017-05-24"]["high"] == 112.1290


_DAILY_PAYLOAD = {
    "Time Series (Daily)": {
        "2020-01-03": {"1. open": "10.5", "2. high": "11.5", "3. low": "10.2", "4. close": "11.0", "5. volume": "1200"},
        "2020-01-02": {"1. open": "10.0", "2. high": "10.9", "3. low": "9.8", "4. close": "10.4", "5. volume": "1000"},
        "2019-12-31": {"1. open": "9.5", "2. high": "9.9", "3. low": "9.4", "4. close": "9.8", "5. volume": "900"},
    }
}


@pytest.mark.stable
class TestAVTimeSeriesOffline:
    def _patch(self, monkeypatch):
        patch_session_get(monkeypatch, {"alphavantage.co": make_response(json=_DAILY_PAYLOAD)})

    def _read(self, monkeypatch, **kwargs):
        self._patch(monkeypatch)
        return web.DataReader(
            "AAPL", "av-daily", start=datetime(2020, 1, 1), end=datetime(2020, 1, 31), api_key="fake", **kwargs
        )

    def test_pandas_index_is_datetime(self, monkeypatch):
        df = self._read(monkeypatch)
        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.index.tolist() == [pd.Timestamp("2020-01-02"), pd.Timestamp("2020-01-03")]
        assert df["close"].tolist() == [10.4, 11.0]
        assert str(df["volume"].dtype) == "int64"

    def test_date_range_filters_with_real_dates(self, monkeypatch):
        self._patch(monkeypatch)
        df = web.DataReader("AAPL", "av-daily", start=datetime(2020, 1, 3), end=datetime(2020, 1, 31), api_key="fake")
        assert df.index.tolist() == [pd.Timestamp("2020-01-03")]

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_tidy_schema_matches_pandas(self, monkeypatch, output_type):
        skip_unless_installed(output_type)
        as_pandas = self._read(monkeypatch)
        tidy = as_narwhals(self._read(monkeypatch, output_type=output_type))

        assert tidy.columns == ["Date", "open", "high", "low", "close", "volume"]
        assert tidy.schema["Date"] == nw.Datetime
        assert tidy["close"].to_list() == as_pandas["close"].tolist()
