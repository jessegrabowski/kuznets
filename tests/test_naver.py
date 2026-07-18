from datetime import datetime, timedelta

import narwhals.stable.v2 as nw
import numpy as np
import pytest

from pandas_datareader import DataReader
from pandas_datareader.naver import NaverDailyReader
from tests._backends import BACKENDS, as_narwhals, skip_unless_installed
from tests._mock import patch_session_get, service_up, tolerate_outage

pytestmark = pytest.mark.stable


class TestNaverOffline:
    # Naver's chart endpoint takes a bar count, not a date range, and returns the most recent days,
    # so a faithful recording would be large and change every run. This fixture is a fixed-date
    # sample of the real XML shape; TestNaverLive validates that shape against the live service.
    def test_daily_prices_are_parsed(self, monkeypatch, datapath):
        patch_session_get(
            monkeypatch,
            {"fchart.stock.naver.com": datapath("data", "naver", "005930.xml")},
        )
        start, end = datetime(2019, 10, 1), datetime(2019, 10, 7)
        df = DataReader("005930", "naver", start, end)

        assert df.shape[1] == 5
        assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
        assert df.index.min() >= start
        assert df.index.max() <= end
        assert all(np.issubdtype(dtype, np.number) for dtype in df.dtypes)
        assert df["Close"].loc["2019-10-01"] == 49150

    def test_bulk_fetch_not_implemented(self):
        with pytest.raises(NotImplementedError):
            DataReader(["005930", "000660"])


@pytest.mark.network
class TestNaverLive:
    def test_daily_shape(self):
        if not service_up(NaverDailyReader(symbols="005930").url):
            pytest.skip("Naver endpoint unreachable")
        end = datetime.now()
        start = end - timedelta(days=10)
        with tolerate_outage():
            df = DataReader("005930", "naver", start, end)
            assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
            assert len(df) > 0


class TestNaverBackends:
    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_tidy_schema_matches_pandas(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)
        patch_session_get(
            monkeypatch,
            {"fchart.stock.naver.com": datapath("data", "naver", "005930.xml")},
        )
        start, end = datetime(2019, 10, 1), datetime(2019, 10, 7)

        as_pandas = DataReader("005930", "naver", start, end)
        tidy = as_narwhals(DataReader("005930", "naver", start, end, output_type=output_type))

        assert tidy.columns == ["Date", "Open", "High", "Low", "Close", "Volume"]
        assert tidy.schema["Date"] == nw.Datetime
        assert tidy["Close"].to_list() == as_pandas["Close"].tolist()
