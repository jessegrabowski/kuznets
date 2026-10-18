import pandas as pd
import pytest

from kuznets.bis import BISReader
from kuznets.sdmx import clear_structure_cache
from kuznets.utils import RemoteDataError
from tests._mock import from_fixtures, make_response, patch_session_get, service_up, tolerate_outage

pytestmark = pytest.mark.stable

COMMON = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common"
MESSAGE = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
STRUCTURE = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"

INDIA_REAL_BROAD = {"FREQ": "M", "EER_TYPE": "R", "EER_BASKET": "B", "REF_AREA": "IN"}


def codelist_document(identifier: str, *codes: str) -> bytes:
    """A codelist carrying just the codes a test selects, standing in for the service's full one."""
    entries = "".join(f'<str:Code id="{code}"><com:Name xml:lang="en">{code}</com:Name></str:Code>' for code in codes)
    return (
        f'<mes:Structure xmlns:mes="{MESSAGE}" xmlns:str="{STRUCTURE}" xmlns:com="{COMMON}"><mes:Structures>'
        f'<str:Codelists><str:Codelist id="{identifier}">{entries}</str:Codelist></str:Codelists>'
        "</mes:Structures></mes:Structure>"
    ).encode()


@pytest.fixture(autouse=True)
def _forget_resolved_dataflows():
    clear_structure_cache()
    yield
    clear_structure_cache()


@pytest.fixture
def service(datapath):
    """Build a handler answering the structure requests and, when given, the data request, recording each."""

    def build(data=None):
        requested = []
        fixtures = {
            "/dataflow/": datapath("io", "data", "sdmx", "bis_dataflow_eer.xml"),
            "/datastructure/": datapath("io", "data", "sdmx", "bis_datastructure_eer.xml"),
            "CL_FREQ": codelist_document("CL_FREQ", "M", "D"),
            "CL_EER_TYPE": codelist_document("CL_EER_TYPE", "R", "N"),
            "CL_EER_BASKET": codelist_document("CL_EER_BASKET", "B", "N"),
            "CL_AREA": codelist_document("CL_AREA", "IN", "ID", "XM"),
        }
        if data is not None:
            fixtures["/data/"] = data

        def counting(url, params=None, **kwargs):
            requested.append((url, params or {}))
            return from_fixtures(fixtures)(url, params, **kwargs)

        counting.requested = requested
        return counting

    return build


class TestBISOffline:
    def test_real_effective_exchange_rate(self, monkeypatch, datapath, service):
        patch_session_get(monkeypatch, service(datapath("data", "bis", "eer_in_2011.xml")))

        df = BISReader("WS_EER", INDIA_REAL_BROAD, start="2011", end="2011").read()

        assert isinstance(df.index, pd.DatetimeIndex)
        assert list(df.index.month) == list(range(1, 13))
        assert df.columns.names == ["FREQ", "EER_TYPE", "EER_BASKET", "REF_AREA"]
        assert df.iloc[0, 0] == pytest.approx(101.28)

    def test_the_data_request_leaves_the_format_to_the_service(self, monkeypatch, datapath, service):
        # The BIS answers a format parameter with HTTP 406, and its default is the structure-specific
        # payload the parser reads.
        handler = service(datapath("data", "bis", "eer_in_2011.xml"))
        patch_session_get(monkeypatch, handler)

        BISReader("WS_EER", INDIA_REAL_BROAD, start="2011", end="2011").read()

        data_requests = [params for url, params in handler.requested if "/data/" in url]
        assert data_requests == [{"startPeriod": 2011, "endPeriod": 2011}]

    def test_an_empty_selection_is_named_as_missing_coverage(self, monkeypatch, datapath, service):
        # The BIS answers an empty selection with HTTP 404 where other services send an empty document.
        with open(datapath("data", "bis", "no_data.xml"), "rb") as body:
            patch_session_get(monkeypatch, service(make_response(body.read(), status_code=404)))

        selection = INDIA_REAL_BROAD | {"REF_AREA": "XM"}
        with pytest.raises(RemoteDataError, match="every selected code exists"):
            BISReader("WS_EER", selection, start="1960", end="1961").read()

    def test_an_alpha_3_country_code_is_rejected_before_the_data_request(self, monkeypatch, service):
        # No data response is mapped, so reaching the data request fails the test.
        patch_session_get(monkeypatch, service())

        with pytest.raises(ValueError, match="did you mean 'IN'"):
            BISReader("WS_EER", INDIA_REAL_BROAD | {"REF_AREA": "IND"}, start="2011", end="2011").read()


@pytest.mark.network
class TestBISLive:
    def test_effective_exchange_rates_read_from_the_live_service(self):
        if not service_up(f"{BISReader._SERVICE}/dataflow/BIS/WS_EER"):
            pytest.skip("stats.bis.org unreachable")

        with tolerate_outage():
            df = BISReader("WS_EER", INDIA_REAL_BROAD, start="2011", end="2011").read()

            assert df.columns.names == ["FREQ", "EER_TYPE", "EER_BASKET", "REF_AREA"]
            assert len(df) == 12
