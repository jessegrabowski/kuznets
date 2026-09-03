import narwhals.stable.v2 as nw
import pandas as pd
import pytest

from kuznets.sdmx import _SdmxDataflowReader, clear_structure_cache
from tests._backends import BACKENDS, as_narwhals, skip_unless_installed
from tests._mock import from_fixtures, patch_session_get

pytestmark = pytest.mark.stable

MESSAGE = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
STRUCTURE = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"

SERVICE = "https://sdmx.example/rest"

# A dataflow whose own version differs from nothing in particular, referencing a data structure of
# another name -- the two identities the reader has to keep apart when it builds the data URL.
DATAFLOW_RECORD = (
    f'<mes:Structure xmlns:mes="{MESSAGE}" xmlns:str="{STRUCTURE}"><mes:Structures><str:Dataflows>'
    '<str:Dataflow agencyID="IMF.STA" id="IMTS" version="1.0.0"><str:Structure>'
    '<Ref agencyID="IMF.STA" id="DSD_IMTS" version="1.0.0" class="DataStructure"/>'
    "</str:Structure></str:Dataflow></str:Dataflows></mes:Structures></mes:Structure>"
)

DATA_STRUCTURE = (
    f'<mes:Structure xmlns:mes="{MESSAGE}" xmlns:str="{STRUCTURE}"><mes:Structures>'
    '<str:DataStructures><str:DataStructure id="DSD_IMTS"><str:DataStructureComponents>'
    '<str:DimensionList id="DimensionDescriptor">'
    '<str:Dimension id="COUNTRY" position="0"/>'
    '<str:Dimension id="INDICATOR" position="1"/>'
    '<str:Dimension id="COUNTERPART_COUNTRY" position="2"/>'
    '<str:Dimension id="FREQUENCY" position="3"/>'
    '<str:TimeDimension id="TIME_PERIOD"/>'
    "</str:DimensionList></str:DataStructureComponents></str:DataStructure></str:DataStructures>"
    "</mes:Structures></mes:Structure>"
)


class FakeServiceReader(_SdmxDataflowReader):
    _SERVICE = SERVICE


@pytest.fixture(autouse=True)
def _forget_resolved_dataflows():
    # The cache is module state shared by every reader, so a test that resolved a dataflow would
    # otherwise decide how many requests the next one makes.
    clear_structure_cache()
    yield
    clear_structure_cache()


@pytest.fixture
def service(datapath):
    """A handler answering the two structure requests and the data request, counting each URL."""
    requested = []

    def counting(url, params=None, **kwargs):
        requested.append(url)
        return from_fixtures(
            {
                "/dataflow/": DATAFLOW_RECORD.encode(),
                "/datastructure/": DATA_STRUCTURE.encode(),
                "/data/": datapath("io", "data", "sdmx", "imts_structure_specific.xml"),
            }
        )(url, params, **kwargs)

    counting.requested = requested
    return counting


class TestDiscovery:
    def test_the_key_follows_the_discovered_dimension_order(self, monkeypatch, service):
        patch_session_get(monkeypatch, service)
        reader = FakeServiceReader("IMTS", {"COUNTRY": "LAO", "FREQUENCY": "A"}, start="2018", end="2019")

        reader.read()

        assert reader.key == "LAO...A"

    def test_the_data_url_addresses_the_dataflow_not_its_structure(self, monkeypatch, service):
        # The dataflow is IMTS and the structure it points at is DSD_IMTS; a data request built from
        # the structure's identity asks for a dataflow that does not exist.
        patch_session_get(monkeypatch, service)
        reader = FakeServiceReader("IMTS", {"COUNTRY": "LAO"}, start="2018", end="2019")

        reader.read()

        assert reader.url == f"{SERVICE}/data/IMF.STA,IMTS,1.0.0/LAO..."

    def test_the_structure_is_requested_at_the_version_the_dataflow_names(self, monkeypatch, service):
        # Omitting the version lets the service pick one, and it does not always pick the same data.
        patch_session_get(monkeypatch, service)

        FakeServiceReader("IMTS", start="2018", end="2019").read()

        assert any("/datastructure/IMF.STA/DSD_IMTS/1.0.0" in url for url in service.requested)

    def test_several_codes_on_one_dimension_join_into_a_single_request(self, monkeypatch, service):
        # The service takes a '+'-joined list, so restricting a dimension to several codes stays one
        # request rather than becoming one per code.
        patch_session_get(monkeypatch, service)
        reader = FakeServiceReader("IMTS", {"COUNTRY": ["LAO", "THA"], "FREQUENCY": "A"}, start="2018", end="2019")

        reader.read()

        assert reader.key == "LAO+THA...A"
        assert sum("/data/" in url for url in service.requested) == 1

    def test_the_agency_addresses_the_dataflow_request(self, monkeypatch, service):
        patch_session_get(monkeypatch, service)

        FakeServiceReader("IMTS", agency="IMF.STA", start="2018", end="2019").read()

        assert any(url.endswith("/dataflow/IMF.STA/IMTS") for url in service.requested)

    def test_an_unresolved_reader_reports_the_service_rather_than_a_half_built_url(self):
        reader = FakeServiceReader("IMTS")

        assert reader.url == SERVICE
        with pytest.raises(RuntimeError, match="not known until"):
            _ = reader.key

    def test_a_missing_dataflow_identifier_raises(self):
        with pytest.raises(ValueError, match="requires a dataflow identifier"):
            FakeServiceReader("")


class TestStructureCache:
    def test_a_second_read_reuses_the_resolved_structure(self, monkeypatch, service):
        patch_session_get(monkeypatch, service)

        FakeServiceReader("IMTS", {"COUNTRY": "LAO"}, start="2018", end="2019").read()
        FakeServiceReader("IMTS", {"COUNTRY": "THA"}, start="2018", end="2019").read()

        structure_requests = [url for url in service.requested if "/data/" not in url]
        assert len(structure_requests) == 2
        assert sum("/data/" in url for url in service.requested) == 2

    def test_a_different_dataflow_resolves_separately(self, monkeypatch, service):
        # The cache is shared by every reader, so keying it too loosely would serve one dataflow's
        # dimensions for another's key.
        patch_session_get(monkeypatch, service)

        FakeServiceReader("IMTS", start="2018", end="2019").read()
        FakeServiceReader("CPI", start="2018", end="2019").read()

        assert sum("/dataflow/" in url for url in service.requested) == 2

    def test_readers_differing_only_by_date_range_share_one_resolution(self, monkeypatch, service):
        # The cache is keyed on the dataflow, not the request, so a date range must not leak into it.
        patch_session_get(monkeypatch, service)

        FakeServiceReader("IMTS", start="2018", end="2018").read()
        FakeServiceReader("IMTS", start="2019", end="2019").read()

        assert sum("/dataflow/" in url for url in service.requested) == 1


class TestPresentation:
    def test_pandas_frame_is_named_by_the_discovered_dimensions(self, monkeypatch, service):
        patch_session_get(monkeypatch, service)

        df = FakeServiceReader("IMTS", start="2018", end="2019").read()

        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.columns.names == ["COUNTRY", "INDICATOR", "COUNTERPART_COUNTRY", "FREQUENCY"]
        assert df.xs("THA", axis=1, level="COUNTERPART_COUNTRY").iloc[0].item() == pytest.approx(1810.7)

    def test_the_year_range_truncates_the_frame(self, monkeypatch, service):
        patch_session_get(monkeypatch, service)

        df = FakeServiceReader("IMTS", start="2019", end="2019").read()

        assert list(df.index.year) == [2019]

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_tidy_frame_carries_a_column_per_dimension(self, monkeypatch, service, output_type):
        skip_unless_installed(output_type)
        patch_session_get(monkeypatch, service)

        tidy = as_narwhals(FakeServiceReader("IMTS", start="2018", end="2019", output_type=output_type).read())

        assert tidy.columns == ["COUNTRY", "INDICATOR", "COUNTERPART_COUNTRY", "FREQUENCY", "period", "value"]
        assert tidy.schema["period"] == nw.Datetime
        assert len(tidy) == 4
