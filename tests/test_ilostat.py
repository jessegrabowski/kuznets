import pandas as pd
import pytest

from kuznets.ilostat import ILOSTATReader
from kuznets.sdmx import clear_structure_cache
from kuznets.utils import RemoteDataError
from tests._mock import from_fixtures, patch_session_get, service_up, tolerate_outage

pytestmark = pytest.mark.stable

COMMON = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common"
MESSAGE = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
STRUCTURE = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"


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
    """A handler answering the structure and data requests, recording each URL and its parameters."""
    requested = []

    def counting(url, params=None, **kwargs):
        requested.append((url, params or {}))
        return from_fixtures(
            {
                "/dataflow/": datapath("io", "data", "sdmx", "ilo_dataflow_earnings.xml"),
                "/datastructure/": datapath("io", "data", "sdmx", "ilo_datastructure_earnings.xml"),
                "CL_AREA": codelist_document("CL_AREA", "ZMB", "AGO", "BWA"),
                "CL_SEX": codelist_document("CL_SEX", "SEX_T", "SEX_M", "SEX_F"),
                "/data/": datapath("data", "ilostat", "earnings_zmb.xml"),
            }
        )(url, params, **kwargs)

    counting.requested = requested
    return counting


class TestILOSTATOffline:
    def test_dimensions_come_back_under_the_ilo_names(self, monkeypatch, service):
        # The ILO calls the country REF_AREA where the IMF calls it COUNTRY. Anything here that read
        # as an IMF name would mean the reader had assumed a shape rather than discovered it.
        patch_session_get(monkeypatch, service)

        df = ILOSTATReader("DF_EAR_CMTA_SEX_CUR_NB", {"REF_AREA": "ZMB"}, start="2015", end="2019").read()

        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.columns.names == ["REF_AREA", "FREQ", "MEASURE", "SEX", "CUR"]
        assert set(df.columns.get_level_values("CUR")) == {"CUR_TYPE_LCU", "CUR_TYPE_PPP", "CUR_TYPE_USD"}

    def test_the_data_request_pins_the_payload_format(self, monkeypatch, service):
        # Left to its own default the ILO answers with SDMX generic data, which this reader's parser
        # reads as a document of no observations rather than refusing outright.
        patch_session_get(monkeypatch, service)

        ILOSTATReader("DF_EAR_CMTA_SEX_CUR_NB", {"REF_AREA": "ZMB"}, start="2015", end="2019").read()

        data_requests = [params for url, params in service.requested if "/data/" in url]
        assert [params["format"] for params in data_requests] == ["structurespecificdata"]

    def test_the_key_follows_the_ilo_dimension_order(self, monkeypatch, service):
        patch_session_get(monkeypatch, service)
        reader = ILOSTATReader("DF_EAR_CMTA_SEX_CUR_NB", {"REF_AREA": "ZMB", "SEX": "SEX_T"}, start="2015", end="2019")

        reader.read()

        # Five dimensions: REF_AREA, FREQ, MEASURE, SEX, CUR. Two are named and three left open.
        assert reader.key == "ZMB...SEX_T."


@pytest.mark.network
class TestILOSTATLive:
    def test_earnings_read_from_the_live_service(self):
        if not service_up(f"{ILOSTATReader._SERVICE}/dataflow/ILO/DF_EAR_CMTA_SEX_CUR_NB"):
            pytest.skip("sdmx.ilo.org unreachable")

        with tolerate_outage():
            df = ILOSTATReader("DF_EAR_CMTA_SEX_CUR_NB", {"REF_AREA": "ZMB"}, start="2015", end="2019").read()

            assert df.columns.names == ["REF_AREA", "FREQ", "MEASURE", "SEX", "CUR"]
            assert not df.empty

    def test_an_unknown_dataflow_reports_the_services_own_message(self):
        if not service_up(f"{ILOSTATReader._SERVICE}/dataflow/ILO/DF_EAR_CMTA_SEX_CUR_NB"):
            pytest.skip("sdmx.ilo.org unreachable")

        with tolerate_outage(), pytest.raises(RemoteDataError, match="Could not find requested structures"):
            ILOSTATReader("DF_NOT_A_DATAFLOW", start="2015", end="2019").read()
