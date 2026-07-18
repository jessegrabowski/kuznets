from datetime import datetime

import narwhals.stable.v2 as nw
import numpy as np
import pandas as pd
import pytest

from pandas_datareader import data as web
from pandas_datareader._utils import RemoteDataError
from pandas_datareader.fred import FRED_API_URL, FRED_CSV_URL, FredReader
from tests._backends import BACKENDS, as_narwhals, skip_unless_installed
from tests._mock import live_or_record, make_response, patch_session_get, tolerate_outage

pytestmark = pytest.mark.stable


class TestFredEndpointSelection:
    def test_csv_endpoint_without_key(self, monkeypatch):
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        assert FredReader("GDP").url == FRED_CSV_URL

    def test_api_endpoint_with_explicit_key(self):
        assert FredReader("GDP", api_key="abc").url == FRED_API_URL

    def test_api_key_from_environment(self, monkeypatch):
        monkeypatch.setenv("FRED_API_KEY", "abc")
        assert FredReader("GDP").url == FRED_API_URL


class TestFredOffline:
    def test_csv_series_is_parsed(self, monkeypatch, datapath):
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        patch_session_get(monkeypatch, {"fredgraph.csv": datapath("data", "fred", "gdp.csv")})

        df = web.DataReader("GDP", "fred", datetime(2010, 1, 1), datetime(2013, 1, 1))
        ts = df["GDP"]

        assert ts.index[0] == pd.Timestamp("2010-01-01")
        assert ts.index[-1] == pd.Timestamp("2013-01-01")
        assert ts.index.name == "DATE"
        assert ts.name == "GDP"
        assert len(ts) == 13
        assert np.issubdtype(ts.values.dtype, np.floating)

    def test_csv_missing_value_is_nan(self, monkeypatch, datapath):
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        patch_session_get(monkeypatch, {"fredgraph.csv": datapath("data", "fred", "dfii5.csv")})

        df = web.DataReader("DFII5", "fred", datetime(2010, 1, 1), datetime(2013, 1, 27))
        assert pd.isnull(df.loc["2010-01-01"].iloc[0])

    def test_multiple_series_outer_join(self, monkeypatch, datapath):
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        patch_session_get(
            monkeypatch,
            {
                "id=GDP": datapath("data", "fred", "gdp.csv"),
                "id=DFII5": datapath("data", "fred", "dfii5.csv"),
            },
        )

        df = web.DataReader(["GDP", "DFII5"], "fred", datetime(2010, 1, 1), datetime(2013, 1, 27))
        assert list(df.columns) == ["GDP", "DFII5"]
        # Quarterly GDP and daily DFII5 share an outer-joined index, so each leaves gaps in the other.
        assert df["GDP"].notna().any()
        assert df["DFII5"].notna().any()
        assert df["GDP"].isna().any()

    def test_json_api_series_is_parsed(self, monkeypatch, datapath):
        patch_session_get(monkeypatch, {"api.stlouisfed.org": datapath("data", "fred", "gdp_api.json")})

        df = web.DataReader("GDP", "fred", datetime(2010, 1, 1), datetime(2011, 1, 1), api_key="abc")
        assert df["GDP"].iloc[0] == 14721.35
        assert pd.isnull(df["GDP"].iloc[-1])

    def test_remote_error_on_bad_status(self, monkeypatch):
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        patch_session_get(monkeypatch, make_response(b"", status_code=404))

        with pytest.raises(RemoteDataError):
            web.DataReader("NOT A REAL SERIES", "fred", datetime(2010, 1, 1), datetime(2013, 1, 1))


@pytest.mark.network
class TestFredLive:
    def test_csv_shape(self, monkeypatch, datapath):
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        live_or_record(monkeypatch, {"fredgraph.csv": datapath("data", "fred", "gdp.csv")}, FRED_CSV_URL)

        with tolerate_outage():
            df = web.DataReader("GDP", "fred", datetime(2010, 1, 1), datetime(2013, 1, 1))
            assert list(df.columns) == ["GDP"]
            assert df.index.name == "DATE"
            assert len(df) > 0
            assert np.issubdtype(df["GDP"].values.dtype, np.floating)


class TestFredBackends:
    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_single_series_tidy_schema(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        patch_session_get(monkeypatch, {"fredgraph.csv": datapath("data", "fred", "gdp.csv")})

        as_pandas = web.DataReader("GDP", "fred", datetime(2010, 1, 1), datetime(2013, 1, 1))
        tidy = as_narwhals(
            web.DataReader("GDP", "fred", datetime(2010, 1, 1), datetime(2013, 1, 1), output_type=output_type)
        )

        assert tidy.columns == ["DATE", "GDP"]
        assert tidy.schema["DATE"] == nw.Datetime
        assert len(tidy) == len(as_pandas)
        assert tidy["GDP"].to_list() == as_pandas["GDP"].tolist()

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_multiple_series_outer_join_keeps_nulls(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        monkeypatch.setattr("pandas_datareader.fred.time.sleep", lambda seconds: None)
        patch_session_get(
            monkeypatch,
            {
                "id=GDP": datapath("data", "fred", "gdp.csv"),
                "id=DFII5": datapath("data", "fred", "dfii5.csv"),
            },
        )

        as_pandas = web.DataReader(["GDP", "DFII5"], "fred", datetime(2010, 1, 1), datetime(2013, 1, 27))
        tidy = as_narwhals(
            web.DataReader(
                ["GDP", "DFII5"], "fred", datetime(2010, 1, 1), datetime(2013, 1, 27), output_type=output_type
            )
        )

        assert tidy.columns == ["DATE", "GDP", "DFII5"]
        assert len(tidy) == len(as_pandas)
        # The outer join of quarterly GDP and daily DFII5 leaves gaps; nulls must survive conversion.
        assert tidy["GDP"].null_count() == int(as_pandas["GDP"].isna().sum())
        assert tidy["DFII5"].null_count() == int(as_pandas["DFII5"].isna().sum())
