import importlib.util

import pandas as pd
import pytest
import requests

from kuznets.data import DataReader
from kuznets.ilostat import ILOSTATReader
from kuznets.imf import IMFReader, IMTSReader
from kuznets.sdmx import clear_structure_cache
from tests._mock import make_response, patch_session_get

pytestmark = pytest.mark.stable


_COMMON = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common"
_MESSAGE = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
_STRUCTURE = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"

# A structure shaped like the recorded IMTS data, so the dispatch can be exercised against it.
_IMTS_SHAPED_STRUCTURE = (
    f'<mes:Structure xmlns:mes="{_MESSAGE}" xmlns:str="{_STRUCTURE}"><mes:Structures>'
    '<str:DataStructures><str:DataStructure id="DSD_CPI"><str:DataStructureComponents>'
    '<str:DimensionList id="DimensionDescriptor">'
    '<str:Dimension id="COUNTRY" position="0"/>'
    '<str:Dimension id="INDICATOR" position="1"/>'
    '<str:Dimension id="COUNTERPART_COUNTRY" position="2"/>'
    '<str:Dimension id="FREQUENCY" position="3"/>'
    '<str:TimeDimension id="TIME_PERIOD"/>'
    "</str:DimensionList></str:DataStructureComponents></str:DataStructure></str:DataStructures>"
    "</mes:Structures></mes:Structure>"
)


_ILO_AREA_CODELIST = (
    f'<mes:Structure xmlns:mes="{_MESSAGE}" xmlns:str="{_STRUCTURE}" xmlns:com="{_COMMON}"><mes:Structures>'
    '<str:Codelists><str:Codelist id="CL_AREA">'
    '<str:Code id="ZMB"><com:Name xml:lang="en">Zambia</com:Name></str:Code>'
    "</str:Codelist></str:Codelists></mes:Structures></mes:Structure>"
).encode()


@pytest.fixture(autouse=True)
def _forget_resolved_dataflows():
    clear_structure_cache()
    yield
    clear_structure_cache()


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

    def test_imf_dispatch_requires_a_dataflow(self):
        # 'imf' serves over two hundred dataflows, and reading one unrestricted is a multi-megabyte
        # download, so the dataflow is required rather than defaulted.
        with pytest.raises(ValueError, match="needs a dataflow"):
            DataReader("ZMB", "imf", start="2020", end="2020")

    def test_imf_dispatch_reads_the_country_from_name(self, monkeypatch, datapath):
        # 'name' is the country on every IMF dataflow, so the dispatch and the reader called with
        # that selection have to agree.
        fixtures = {
            "/dataflow/": datapath("io", "data", "sdmx", "imf_dataflow_cpi.xml"),
            "/datastructure/": _IMTS_SHAPED_STRUCTURE.encode(),
            "/data/": datapath("data", "imf", "imts_lao_2019_exports.xml"),
        }
        patch_session_get(monkeypatch, fixtures)

        dispatched = DataReader("LAO", "imf", dataflow="CPI", start="2019", end="2019")
        direct = IMFReader("CPI", {"COUNTRY": "LAO"}, start="2019", end="2019").read()

        pd.testing.assert_frame_equal(dispatched, direct)

    def test_ilostat_dispatch_requires_a_dataflow(self):
        with pytest.raises(ValueError, match="needs a dataflow"):
            DataReader("ZMB", "ilostat", start="2015", end="2019")

    def test_ilostat_dispatch_reads_the_country_from_name(self, monkeypatch, datapath):
        # The ILO calls the country REF_AREA, so a dispatch copied from 'imf' would select a
        # dimension this service does not declare.
        patch_session_get(
            monkeypatch,
            {
                "/dataflow/": datapath("io", "data", "sdmx", "ilo_dataflow_earnings.xml"),
                "/datastructure/": datapath("io", "data", "sdmx", "ilo_datastructure_earnings.xml"),
                "CL_AREA": _ILO_AREA_CODELIST,
                "/data/": datapath("data", "ilostat", "earnings_zmb.xml"),
            },
        )

        dispatched = DataReader("ZMB", "ilostat", dataflow="DF_EAR_CMTA_SEX_CUR_NB", start="2015", end="2019")
        direct = ILOSTATReader("DF_EAR_CMTA_SEX_CUR_NB", {"REF_AREA": "ZMB"}, start="2015", end="2019").read()

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
