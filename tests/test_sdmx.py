import re

import narwhals.stable.v2 as nw
import pandas as pd
import pytest

from kuznets.sdmx import _SdmxDataflowReader, clear_structure_cache
from kuznets.utils import RemoteDataError
from tests._backends import BACKENDS, as_narwhals, skip_unless_installed
from tests._mock import from_fixtures, patch_session_get

pytestmark = pytest.mark.stable

COMMON = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common"
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
    '<str:Dimension id="COUNTRY" position="0"><str:LocalRepresentation><str:Enumeration>'
    '<Ref agencyID="IMF" id="CL_COUNTRY" version="1.6.0" class="Codelist"/>'
    "</str:Enumeration></str:LocalRepresentation></str:Dimension>"
    '<str:Dimension id="INDICATOR" position="1"/>'
    '<str:Dimension id="COUNTERPART_COUNTRY" position="2"/>'
    '<str:Dimension id="FREQUENCY" position="3"><str:LocalRepresentation><str:Enumeration>'
    '<Ref agencyID="IMF" id="CL_FREQ" version="1.0.0" class="Codelist"/>'
    "</str:Enumeration></str:LocalRepresentation></str:Dimension>"
    '<str:TimeDimension id="TIME_PERIOD"/>'
    "</str:DimensionList></str:DataStructureComponents></str:DataStructure></str:DataStructures>"
    "</mes:Structures></mes:Structure>"
)


def codelist_document(identifier: str, *codes: str) -> str:
    entries = "".join(f'<str:Code id="{code}"><com:Name xml:lang="en">{code}</com:Name></str:Code>' for code in codes)
    return (
        f'<mes:Structure xmlns:mes="{MESSAGE}" xmlns:str="{STRUCTURE}" xmlns:com="{COMMON}"><mes:Structures>'
        f'<str:Codelists><str:Codelist id="{identifier}">{entries}</str:Codelist></str:Codelists>'
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


def make_service(data_fixture):
    """A handler answering the structure, codelist and data requests, recording each URL."""
    requested = []

    def counting(url, params=None, **kwargs):
        requested.append(url + (f"?references={params['references']}" if params and "references" in params else ""))
        return from_fixtures(
            {
                "/dataflow/": DATAFLOW_RECORD.encode(),
                "/datastructure/": DATA_STRUCTURE.encode(),
                "CL_COUNTRY": codelist_document("CL_COUNTRY", "LAO", "LKA", "LVA", "THA", "VNM").encode(),
                "CL_FREQ": codelist_document("CL_FREQ", "A", "M", "Q").encode(),
                "/data/": data_fixture,
            }
        )(url, params, **kwargs)

    counting.requested = requested
    return counting


@pytest.fixture
def service(datapath):
    return make_service(datapath("io", "data", "sdmx", "imts_structure_specific.xml"))


@pytest.fixture
def service_without_observations(datapath):
    return make_service(datapath("io", "data", "sdmx", "imts_group_only.xml"))


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

    def test_a_selection_naming_no_declared_dimension_raises(self, monkeypatch, service):
        # Silently dropping it would widen the key to every dimension, so a caller who asked for one
        # country would be handed the whole dataflow instead of an error.
        patch_session_get(monkeypatch, service)
        reader = FakeServiceReader("IMTS", {"CONTRY": "LAO"}, start="2018", end="2019")

        with pytest.raises(ValueError, match="declares no dimension named CONTRY"):
            reader.read()

    def test_the_error_lists_the_dimensions_the_dataflow_does_declare(self, monkeypatch, service):
        patch_session_get(monkeypatch, service)
        reader = FakeServiceReader("IMTS", {"COUNTERPART": "THA"}, start="2018", end="2019")

        with pytest.raises(ValueError, match="COUNTRY, INDICATOR, COUNTERPART_COUNTRY, FREQUENCY"):
            reader.read()

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

        structure_requests = [url for url in service.requested if "/dataflow/" in url or "/datastructure/" in url]
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


class TestSelectionValidation:
    def test_a_code_the_service_does_not_list_raises_before_the_data_request(self, monkeypatch, service):
        patch_session_get(monkeypatch, service)
        reader = FakeServiceReader("IMTS", {"COUNTRY": "ZZZ"}, start="2018", end="2019")

        with pytest.raises(ValueError, match="COUNTRY has no code 'ZZZ' in codelist CL_COUNTRY"):
            reader.read()

        assert not any("/data/" in url for url in service.requested)

    def test_the_message_suggests_a_near_miss(self, monkeypatch, service):
        # The trap this exists to catch: an alpha-2 country code is answered with 200 and no
        # observations, so 'LA' has to be rejected with the alpha-3 it was meant to be.
        patch_session_get(monkeypatch, service)
        reader = FakeServiceReader("IMTS", {"COUNTRY": "LA"}, start="2018", end="2019")

        with pytest.raises(ValueError, match=re.escape("did you mean 'LAO', 'LVA', 'LKA'")):
            reader.read()

    def test_every_code_of_a_multi_value_selection_is_checked(self, monkeypatch, service):
        patch_session_get(monkeypatch, service)
        reader = FakeServiceReader("IMTS", {"COUNTRY": ["LAO", "ZZZ"]}, start="2018", end="2019")

        with pytest.raises(ValueError, match="'ZZZ'"):
            reader.read()

    def test_a_dimension_the_service_does_not_enumerate_is_skipped(self, monkeypatch, service):
        # INDICATOR carries no codelist reference, so there is nothing to validate against and the
        # read proceeds rather than failing on a code that might be perfectly good.
        patch_session_get(monkeypatch, service)

        df = FakeServiceReader("IMTS", {"INDICATOR": "ANYTHING"}, start="2018", end="2019").read()

        assert not df.empty

    def test_a_restricted_dimension_without_a_codelist_asks_for_the_concept_schemes(self, monkeypatch, service):
        # The IMF records codelists on the concept, so the plain structure resolves none of them and
        # the reader has to escalate before it can validate anything.
        patch_session_get(monkeypatch, service)

        FakeServiceReader("IMTS", {"INDICATOR": "XG_FOB_USD"}, start="2018", end="2019").read()

        assert any("references=children" in url for url in service.requested)

    def test_a_selection_the_structure_already_enumerates_does_not_escalate(self, monkeypatch, service):
        patch_session_get(monkeypatch, service)

        FakeServiceReader("IMTS", {"COUNTRY": "LAO"}, start="2018", end="2019").read()

        assert not any("references=children" in url for url in service.requested)

    def test_a_code_with_no_near_miss_reports_the_codelist_size(self, monkeypatch, service):
        patch_session_get(monkeypatch, service)
        reader = FakeServiceReader("IMTS", {"COUNTRY": "QQQQQQ"}, start="2018", end="2019")

        with pytest.raises(ValueError, match="which lists 5 codes"):
            reader.read()

    def test_a_codelist_is_fetched_once_across_reads(self, monkeypatch, service):
        patch_session_get(monkeypatch, service)

        FakeServiceReader("IMTS", {"COUNTRY": "LAO"}, start="2018", end="2019").read()
        FakeServiceReader("IMTS", {"COUNTRY": "THA"}, start="2018", end="2019").read()

        assert sum("/codelist/" in url for url in service.requested) == 1


class TestCodelistEscalation:
    def test_the_concept_schemes_are_requested_once_across_reads(self, monkeypatch, service):
        # Escalation is remembered with the structure, so a dimension the service never enumerates
        # costs one extra request per dataflow rather than one per read.
        patch_session_get(monkeypatch, service)

        FakeServiceReader("IMTS", {"INDICATOR": "XG_FOB_USD"}, start="2018", end="2019").read()
        FakeServiceReader("IMTS", {"INDICATOR": "MG_CIF_USD"}, start="2018", end="2019").read()

        assert sum("references=children" in url for url in service.requested) == 1

    def test_a_structure_cached_without_codelists_is_upgraded_on_demand(self, monkeypatch, service):
        # The first reader restricts nothing, so the plain structure satisfies it and is cached. The
        # second needs a codelist that structure does not carry, and has to escalate off the hit.
        patch_session_get(monkeypatch, service)

        FakeServiceReader("IMTS", start="2018", end="2019").read()
        assert not any("references=children" in url for url in service.requested)

        FakeServiceReader("IMTS", {"INDICATOR": "XG_FOB_USD"}, start="2018", end="2019").read()

        assert any("references=children" in url for url in service.requested)

    def test_each_codelist_is_fetched_on_its_own(self, monkeypatch, service):
        # One cache entry per codelist reference; keying it any looser would validate one dimension
        # against another's codes.
        patch_session_get(monkeypatch, service)

        FakeServiceReader("IMTS", {"COUNTRY": "LAO", "FREQUENCY": "A"}, start="2018", end="2019").read()

        assert sum("/codelist/" in url for url in service.requested) == 2


class TestEmptyObservations:
    def test_an_empty_document_raises_naming_the_key(self, monkeypatch, service_without_observations):
        patch_session_get(monkeypatch, service_without_observations)
        reader = FakeServiceReader("IMTS", {"COUNTRY": "LAO"}, start="2018", end="2019")

        with pytest.raises(RemoteDataError, match=re.escape("'LAO...'")):
            reader.read()

    def test_a_validated_selection_reports_missing_coverage(self, monkeypatch, service_without_observations):
        # Every code was checked, so an empty result cannot be a bad code -- the service simply
        # carries nothing for this selection, which is the distinction context.md asks for.
        patch_session_get(monkeypatch, service_without_observations)
        reader = FakeServiceReader("IMTS", {"COUNTRY": "LAO"}, start="2018", end="2019")

        with pytest.raises(RemoteDataError, match="every selected code exists"):
            reader.read()

    def test_an_unchecked_selection_says_a_bad_code_is_still_possible(self, monkeypatch, service_without_observations):
        patch_session_get(monkeypatch, service_without_observations)
        reader = FakeServiceReader("IMTS", {"INDICATOR": "XG_FOB_USD"}, start="2018", end="2019")

        with pytest.raises(RemoteDataError, match="INDICATOR could not be checked"):
            reader.read()
