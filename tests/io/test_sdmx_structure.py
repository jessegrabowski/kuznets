import pytest

from kuznets.io import read_dataflow_structure_ref

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
