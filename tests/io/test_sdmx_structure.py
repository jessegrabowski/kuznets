import pytest

from kuznets.io import read_data_structure, read_dataflow_structure_ref

pytestmark = pytest.mark.stable


@pytest.fixture
def dirpath(datapath):
    return datapath("io", "data", "sdmx")


class TestReadDataflowStructureRef:
    def test_imf_dataflow(self, dirpath):
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

    def test_document_without_a_data_structure_raises(self, dirpath):
        with pytest.raises(ValueError, match="no data structure"):
            read_data_structure(dirpath / "imf_dataflow_cpi.xml")
