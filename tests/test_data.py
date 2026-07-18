import importlib.util

import pandas as pd
import pytest

from pandas_datareader.data import DataReader
from tests._mock import patch_session_get

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
        with pytest.raises(ImportError, match=r"pandas-datareader\[polars\]"):
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
        monkeypatch.setattr("pandas_datareader.data.get_nasdaq_symbols", lambda **kwargs: listing)

        as_pandas = DataReader("symbols", "nasdaq")
        pd.testing.assert_frame_equal(as_pandas, listing)

        as_polars = DataReader("symbols", "nasdaq", output_type="polars")
        assert isinstance(as_polars, polars.DataFrame)
        assert as_polars.columns == ["Symbol", "Security Name"]
        assert as_polars["Symbol"].to_list() == ["AAPL"]
