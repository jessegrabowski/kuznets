from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd
from pandas import testing as tm
import pytest

from kuznets.io.sdmx import _get_english_name, _read_sdmx_dsd, read_sdmx

pytestmark = pytest.mark.stable


COMMON = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/common"
MESSAGE = "http://www.sdmx.org/resources/sdmxml/schemas/v2_1/message"


def footer_message(*texts: str) -> str:
    """Build an SDMX message carrying only a footer, which is what a service sends instead of data.

    ``read_sdmx`` reads the second ``<Text>``, which is where the service puts either a URL to
    fetch the results from or its reason for sending none.
    """
    body = "".join(f"<com:Text>{text}</com:Text>" for text in texts)
    return f'<mes:Message xmlns:mes="{MESSAGE}" xmlns:com="{COMMON}"><mes:Footer>{body}</mes:Footer></mes:Message>'


@pytest.fixture
def dirpath(datapath):
    return datapath("io", "data")


def test_tourism(dirpath):
    # Eurostat
    # Employed doctorate holders in non managerial and non professional
    # occupations by fields of science (%)
    dsd = _read_sdmx_dsd(dirpath / "sdmx" / "DSD_cdh_e_fos.xml")
    df = read_sdmx(dirpath / "sdmx" / "cdh_e_fos.xml", dsd=dsd)

    assert isinstance(df, pd.DataFrame)
    assert df.shape == (2, 336)

    df = df["Percentage"]["Total"]["Natural sciences"]
    df = df[["Norway", "Poland", "Portugal", "Russia"]]

    exp_col = pd.MultiIndex.from_product(
        [["Norway", "Poland", "Portugal", "Russia"], ["Annual"]], names=["GEO", "FREQ"]
    )
    exp_idx = pd.DatetimeIndex(["2009", "2006"], name="TIME_PERIOD")

    values = np.array([[20.38, 25.1, 27.77, 38.1], [25.49, np.nan, 39.05, np.nan]])
    expected = pd.DataFrame(values, index=exp_idx, columns=exp_col)
    tm.assert_frame_equal(df, expected)


class TestEnglishName:
    def test_picks_the_english_name_over_other_languages(self):
        element = ET.fromstring(
            f'<Codelist xmlns:com="{COMMON}">'
            '<com:Name xml:lang="fr">Pays</com:Name><com:Name xml:lang="en">Country</com:Name></Codelist>'
        )

        assert _get_english_name(element) == "Country"

    def test_returns_none_when_no_english_name_is_declared(self):
        # Codelists and codes are not obliged to carry an English name, so the absence is a
        # missing label rather than a malformed document.
        element = ET.fromstring(f'<Codelist xmlns:com="{COMMON}"><com:Name xml:lang="fr">Pays</com:Name></Codelist>')

        assert _get_english_name(element) is None


class TestReadSdmxFooter:
    def test_a_footer_naming_no_zip_url_raises_with_the_service_message(self):
        with pytest.raises(ValueError, match="Query returned too many results"):
            read_sdmx(footer_message("ignored", "Query returned too many results"))

    def test_an_empty_footer_text_raises_rather_than_crashing(self):
        # An empty <Text/> carries no URL to follow and no message to report, which must still
        # surface as the service having sent nothing usable.
        with pytest.raises(ValueError):
            read_sdmx(footer_message("ignored", ""))
