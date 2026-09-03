import importlib.util

import pandas as pd
import pytest
import requests

from kuznets.data import DataReader
from kuznets.imf import IMTSReader
from tests._mock import make_response, patch_session_get

pytestmark = pytest.mark.stable


class TestDataReader:
    def test_unknown_source_raises(self):
        with pytest.raises(NotImplementedError):
            DataReader("NA", "NA")

    @pytest.mark.parametrize("data_source", ["econdb", "av-daily", "av-intraday"])
    def test_single_symbol_source_rejects_a_list(self, data_source, monkeypatch):
        # These sources read one symbol per request; a list used to reach the reader and fail
        # somewhere less obvious. Sources that do accept lists, such as av-forex, are unaffected.
        patch_session_get(monkeypatch, {})
        with pytest.raises(ValueError, match="one symbol at a time"):
            DataReader(["AAPL", "MSFT"], data_source, api_key="fake")

    def test_invalid_output_type_raises_before_any_request(self, monkeypatch):
        patch_session_get(monkeypatch, {})
        with pytest.raises(ValueError, match="not supported"):
            DataReader("GDP", "fred", output_type="bogus")

    def test_missing_backend_raises_before_any_request(self, monkeypatch):
        patch_session_get(monkeypatch, {})
        monkeypatch.setattr(importlib.util, "find_spec", lambda module: None)
        with pytest.raises(ImportError, match=r"kuznets\[polars\]"):
            DataReader("GDP", "fred", output_type="polars")

    def test_polars_output_end_to_end(self, monkeypatch, datapath):
        polars = pytest.importorskip("polars")
        patch_session_get(monkeypatch, {"fredgraph.csv": datapath("data", "fred", "gdp.csv")})
        result = DataReader("GDP", "fred", output_type="polars")
        assert isinstance(result, polars.DataFrame)
        assert result.columns == ["DATE", "GDP"]
        assert result["DATE"].dtype == polars.Datetime("us")

    def test_pandas_default_matches_explicit_output_type(self, monkeypatch, datapath):
        patch_session_get(monkeypatch, {"fredgraph.csv": datapath("data", "fred", "gdp.csv")})
        default = DataReader("GDP", "fred")
        explicit = DataReader("GDP", "fred", output_type="pandas")
        pd.testing.assert_frame_equal(default, explicit)

    def test_imts_dispatch_matches_the_reader(self, monkeypatch, datapath):
        # The dispatch reads the reporting country straight from ``name``; every other dimension
        # takes the reader's defaults, so the two calls must agree.
        patch_session_get(monkeypatch, {"api.imf.org": datapath("data", "imf", "imts_lao_2019_exports.xml")})

        dispatched = DataReader("LAO", "imts", start="2019", end="2019")
        direct = IMTSReader("LAO", start="2019", end="2019").read()

        pd.testing.assert_frame_equal(dispatched, direct)

    def test_imts_dispatch_forwards_output_type(self, monkeypatch, datapath):
        polars = pytest.importorskip("polars")
        patch_session_get(monkeypatch, {"api.imf.org": datapath("data", "imf", "imts_lao_2019_exports.xml")})

        tidy = DataReader("LAO", "imts", start="2019", end="2019", output_type="polars")

        assert isinstance(tidy, polars.DataFrame)
        assert tidy.columns == ["country", "indicator", "counterpart", "frequency", "period", "value"]

    def test_imts_dispatch_forwards_headers(self, monkeypatch, datapath):
        # Most branches drop ``headers`` on the floor (issue #32); this one must not, so a host that
        # blocks the default agent stays workable through DataReader.
        patch_session_get(monkeypatch, {"api.imf.org": datapath("data", "imf", "imts_lao_2019_exports.xml")})
        session = requests.Session()

        DataReader("LAO", "imts", start="2019", end="2019", headers={"User-Agent": "probe"}, session=session)

        assert session.headers["User-Agent"] == "probe"

    def test_nasdaq_output_type_converts_symbols(self, monkeypatch):
        polars = pytest.importorskip("polars")
        listing = pd.DataFrame({"Security Name": ["Apple Inc."]}, index=pd.Index(["AAPL"], name="Symbol"))
        monkeypatch.setattr("kuznets.data.get_nasdaq_symbols", lambda **kwargs: listing)

        as_pandas = DataReader("symbols", "nasdaq")
        pd.testing.assert_frame_equal(as_pandas, listing)

        as_polars = DataReader("symbols", "nasdaq", output_type="polars")
        assert isinstance(as_polars, polars.DataFrame)
        assert as_polars.columns == ["Symbol", "Security Name"]
        assert as_polars["Symbol"].to_list() == ["AAPL"]

    def test_max_workers_flows_through_the_dispatch(self, monkeypatch, datapath):
        spy = datapath("data", "stooq", "spy.csv").read_bytes()
        patch_session_get(monkeypatch, lambda url, params=None, **kwargs: make_response(spy))

        sequential = DataReader(["SPY", "AAPL"], "stooq", max_workers=1)
        parallel = DataReader(["SPY", "AAPL"], "stooq", max_workers=2)
        pd.testing.assert_frame_equal(parallel, sequential)
