import importlib.util

import pandas as pd
import pytest

from kuznets.data import DataReader
from tests._mock import make_response, patch_session_get

pytestmark = pytest.mark.stable


class TestDataReader:
    def test_unknown_source_raises(self):
        with pytest.raises(NotImplementedError):
            DataReader("NA", "NA")

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
