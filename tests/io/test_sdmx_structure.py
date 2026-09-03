import pytest
import requests

from kuznets.io import read_codelist, read_data_structure, read_dataflow_structure_ref
from tests._mock import service_up, tolerate_outage

pytestmark = pytest.mark.stable

COMMON = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common"
MESSAGE = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"
STRUCTURE = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/structure"

IMF_SDMX = "https://api.imf.org/external/sdmx/2.1"


@pytest.fixture
def dirpath(datapath):
    return datapath("io", "data", "sdmx")


def fetch(path: str) -> str:
    """Get a structure document from the IMF's SDMX service, skipping when it is unreachable."""
    url = f"{IMF_SDMX}/{path}"
    if not service_up(url):
        pytest.skip(f"{url} unreachable")
    return requests.get(url, timeout=30).text


class TestReadDataflowStructureRef:
    def test_imf_dataflow_names_its_data_structure(self, dirpath):
        ref = read_dataflow_structure_ref(dirpath / "imf_dataflow_cpi.xml")

        assert ref == ("IMF.STA", "DSD_CPI", "5.0.0")

    def test_ilo_dataflow_keeps_its_own_version_form(self, dirpath):
        # The ILO writes two-part versions where the IMF writes three. Normalizing either one would
        # produce a URL the other service answers with a 404, so the reference is taken verbatim.
        ref = read_dataflow_structure_ref(dirpath / "ilo_dataflow_earnings.xml")

        assert ref == ("ILO", "EAR_CMTA_SEX_CUR_NB", "1.0")

    def test_document_without_a_dataflow_raises(self, dirpath):
        with pytest.raises(ValueError, match="no dataflow"):
            read_dataflow_structure_ref(dirpath / "ilo_datastructure_earnings.xml")


class TestReadDataStructure:
    def test_imf_dimension_order(self, dirpath):
        # An SDMX key is positional, so this order is the difference between data and an empty
        # document. CPI carries five dimensions where IMTS carries four.
        structure = read_data_structure(dirpath / "imf_datastructure_cpi_children.xml")

        assert structure.dimensions == ["COUNTRY", "INDEX_TYPE", "COICOP_1999", "TYPE_OF_TRANSFORMATION", "FREQUENCY"]
        assert structure.time_dimension == "TIME_PERIOD"

    def test_ilo_dimension_order(self, dirpath):
        # The ILO numbers positions from one where the IMF numbers from zero, so the order has to
        # come from sorting on the attribute rather than from indexing into it. It also names its
        # dimensions differently, which is the reason the reader discovers them instead of assuming.
        structure = read_data_structure(dirpath / "ilo_datastructure_earnings.xml")

        assert structure.dimensions == ["REF_AREA", "FREQ", "MEASURE", "SEX", "CUR"]
        assert structure.time_dimension == "TIME_PERIOD"

    def test_imf_codelists_resolve_through_the_concept_scheme(self, dirpath):
        # IMF dimensions carry no local representation; the codelist is recorded on the concept the
        # dimension identifies with, and is only reachable when the concept schemes are in the same
        # document.
        structure = read_data_structure(dirpath / "imf_datastructure_cpi_children.xml")

        assert {dimension: ref.id for dimension, ref in structure.codelists.items()} == {
            "COUNTRY": "CL_COUNTRY",
            "INDEX_TYPE": "CL_INDEX_TYPE",
            "COICOP_1999": "CL_COICOP_1999",
            "TYPE_OF_TRANSFORMATION": "CL_CPI_TYPE_OF_TRANSFORMATION",
            "FREQUENCY": "CL_FREQ",
        }
        assert structure.codelists["COUNTRY"] == ("IMF", "CL_COUNTRY", "1.6.0")

    def test_ilo_codelists_resolve_from_the_dimension(self, dirpath):
        # The ILO records the codelist on the dimension itself, so no concept scheme is needed.
        structure = read_data_structure(dirpath / "ilo_datastructure_earnings.xml")

        assert {dimension: ref.id for dimension, ref in structure.codelists.items()} == {
            "REF_AREA": "CL_AREA",
            "FREQ": "CL_FREQ",
            "MEASURE": "CL_MEASURE",
            "SEX": "CL_SEX",
            "CUR": "CL_CUR",
        }

    def test_unresolvable_codelists_are_omitted_not_raised(self, dirpath):
        # Without the concept schemes the IMF's codelists cannot be resolved, but the dimensions
        # still can. A caller can key a request off this and simply validate nothing.
        structure = read_data_structure(dirpath / "imf_datastructure_cpi.xml")

        assert structure.dimensions == ["COUNTRY", "INDEX_TYPE", "COICOP_1999", "TYPE_OF_TRANSFORMATION", "FREQUENCY"]
        assert structure.codelists == {}

    def test_dimensions_order_by_position_not_document_order(self):
        # Every recorded fixture happens to declare its dimensions already in position order, so
        # only a document that disagrees can tell the sort from an accident of the source data.
        document = (
            f'<mes:Structure xmlns:mes="{MESSAGE}" xmlns:str="{STRUCTURE}"><mes:Structures>'
            '<str:DataStructures><str:DataStructure id="DSD_TEST"><str:DataStructureComponents>'
            '<str:DimensionList id="DimensionDescriptor">'
            '<str:Dimension id="THIRD" position="2"/>'
            '<str:Dimension id="FIRST" position="0"/>'
            '<str:Dimension id="SECOND" position="1"/>'
            '<str:TimeDimension id="TIME_PERIOD"/>'
            "</str:DimensionList></str:DataStructureComponents></str:DataStructure>"
            "</str:DataStructures></mes:Structures></mes:Structure>"
        )

        assert read_data_structure(document).dimensions == ["FIRST", "SECOND", "THIRD"]

    def test_document_without_a_data_structure_raises(self, dirpath):
        with pytest.raises(ValueError, match="no data structure"):
            read_data_structure(dirpath / "imf_dataflow_cpi.xml")


class TestReadCodelist:
    def test_country_codes(self, dirpath):
        codes = read_codelist(dirpath / "imf_codelist_country.xml")

        assert len(codes) == 343
        assert codes["LAO"] == "Lao People's Democratic Republic"

    def test_alpha_2_codes_are_absent(self, dirpath):
        # The trap this whole mechanism exists to catch: the IMF answers an alpha-2 country code
        # with HTTP 200 and no observations, so 'LA' has to be rejected before the request goes out.
        codes = read_codelist(dirpath / "imf_codelist_country.xml")

        assert "LAO" in codes
        assert "LA" not in codes

    def test_document_without_a_codelist_raises(self, dirpath):
        with pytest.raises(ValueError, match="no codelist"):
            read_codelist(dirpath / "imf_dataflow_cpi.xml")

    def test_codes_without_an_english_name_fall_back_to_the_identifier(self):
        # A code names itself in whatever languages it likes, and the identifier is what a caller
        # validates against, so it has to survive a missing English label.
        document = (
            f'<mes:Structure xmlns:mes="{MESSAGE}" xmlns:str="{STRUCTURE}" xmlns:com="{COMMON}">'
            '<str:Codelist id="CL_TEST">'
            '<str:Code id="NAMED"><com:Name xml:lang="en">Named</com:Name></str:Code>'
            '<str:Code id="UNNAMED"><com:Name xml:lang="fr">Sans nom</com:Name></str:Code>'
            "</str:Codelist></mes:Structure>"
        )

        assert read_codelist(document) == {"NAMED": "Named", "UNNAMED": "UNNAMED"}


@pytest.mark.network
class TestIMFStructureLive:
    def test_a_dataflow_resolves_to_a_structure_the_parsers_can_read(self):
        # The two parsers composed the way a reader will use them: resolve the reference from the
        # dataflow, then fetch that exact version rather than assuming one.
        with tolerate_outage():
            ref = read_dataflow_structure_ref(fetch("dataflow/all/CPI"))
            structure = read_data_structure(
                fetch(f"datastructure/{ref.agency}/{ref.id}/{ref.version}?references=children")
            )

            assert ref.id == "DSD_CPI"
            assert structure.dimensions[0] == "COUNTRY"
            assert structure.dimensions[-1] == "FREQUENCY"
            assert structure.codelists["COUNTRY"].id == "CL_COUNTRY"

    def test_a_plain_data_structure_resolves_no_codelists(self):
        # What makes the concept schemes worth requesting: the IMF records codelists on the concept,
        # so the data structure alone carries none of them.
        with tolerate_outage():
            ref = read_dataflow_structure_ref(fetch("dataflow/all/CPI"))
            structure = read_data_structure(fetch(f"datastructure/{ref.agency}/{ref.id}/{ref.version}"))

            assert structure.dimensions[0] == "COUNTRY"
            assert structure.codelists == {}

    def test_alpha_2_country_codes_are_absent_from_the_codelist(self):
        # The trap the codelists exist to catch: the IMF answers an alpha-2 country code with HTTP
        # 200 and no observations, so 'LA' has to be rejected before the request goes out.
        with tolerate_outage():
            codes = read_codelist(fetch("codelist/IMF/CL_COUNTRY"))

            assert codes["LAO"] == "Lao People's Democratic Republic"
            assert "LA" not in codes
