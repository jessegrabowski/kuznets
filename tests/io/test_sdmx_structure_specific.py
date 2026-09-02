import narwhals.stable.v2 as nw
import pandas as pd
import pytest

from kuznets.io import build_sdmx_key, read_structure_specific
from tests._backends import BACKENDS, as_narwhals, skip_unless_installed

pytestmark = pytest.mark.stable

# The four dimensions of the IMF's IMTS dataflow, named as the reader presents them.
IMTS_DIMENSIONS = {
    "COUNTRY": "country",
    "INDICATOR": "indicator",
    "COUNTERPART_COUNTRY": "counterpart",
    "FREQUENCY": "frequency",
    "TIME_PERIOD": "period",
}


@pytest.fixture
def dirpath(datapath):
    return datapath("io", "data", "sdmx")


@pytest.mark.parametrize(
    "selections, expected",
    [
        (["LAO", "XG_FOB_USD", "THA", "A"], "LAO.XG_FOB_USD.THA.A"),
        (["LAO", "XG_FOB_USD", None, "A"], "LAO.XG_FOB_USD..A"),
        (["LAO", "XG_FOB_USD", "THA", None], "LAO.XG_FOB_USD.THA."),
        ([["LAO", "THA"], ["XG_FOB_USD", "MG_FOB_USD"], None, "A"], "LAO+THA.XG_FOB_USD+MG_FOB_USD..A"),
        (["LAO", "XG_FOB_USD", [], "A"], "LAO.XG_FOB_USD..A"),
    ],
)
def test_build_sdmx_key(selections, expected):
    assert build_sdmx_key(selections) == expected


class TestReadStructureSpecificPandas:
    def test_wide_frame_shape_and_values(self, dirpath):
        df = read_structure_specific(dirpath / "imts_structure_specific.xml", IMTS_DIMENSIONS)

        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.index.name == "period"
        assert list(df.index.year) == [2018, 2019]
        assert df.columns.names == ["country", "indicator", "counterpart", "frequency"]

        thailand = df.xs("THA", axis=1, level="counterpart").iloc[:, 0]
        assert thailand.loc["2018"].iloc[0] == pytest.approx(1810.7)
        assert thailand.loc["2019"].iloc[0] == pytest.approx(2354.6)

    def test_aggregate_counterparts_get_their_own_column(self, dirpath):
        # G-prefixed counterparts are regional and income groupings whose values overlap the ISO3
        # partners; the reader hands them on and the caller decides.
        df = read_structure_specific(dirpath / "imts_structure_specific.xml", IMTS_DIMENSIONS)

        assert set(df.columns.get_level_values("counterpart")) == {"THA", "G001"}

    def test_group_only_document_yields_an_empty_frame(self, dirpath):
        # A wildcarded INDICATOR comes back as HTTP 200 with only <Group> metadata. Reading must
        # succeed and return nothing, leaving the caller to raise.
        df = read_structure_specific(dirpath / "imts_group_only.xml", IMTS_DIMENSIONS)

        assert df.empty
        assert df.index.name == "period"

    def test_series_without_observations_yields_an_empty_frame(self):
        # A period filter that excludes everything leaves the series shells behind with no <Obs>.
        document = """<StructureSpecificData>
          <DataSet>
            <Series COUNTRY="LAO" INDICATOR="XG_FOB_USD" COUNTERPART_COUNTRY="THA" FREQUENCY="A"/>
          </DataSet>
        </StructureSpecificData>"""

        assert read_structure_specific(document, IMTS_DIMENSIONS).empty

    def test_observations_without_a_value_are_dropped(self):
        document = """<StructureSpecificData>
          <DataSet>
            <Series COUNTRY="LAO" INDICATOR="XG_FOB_USD" COUNTERPART_COUNTRY="THA" FREQUENCY="A">
              <Obs TIME_PERIOD="2018" OBS_VALUE="1810.7"/>
              <Obs TIME_PERIOD="2019" OBS_STATUS="M"/>
            </Series>
          </DataSet>
        </StructureSpecificData>"""

        df = read_structure_specific(document, IMTS_DIMENSIONS)

        assert list(df.index.year) == [2018]


class TestDimensionSelection:
    def test_sequence_keeps_the_sdmx_identifiers(self, dirpath):
        df = read_structure_specific(
            dirpath / "imts_structure_specific.xml",
            ["COUNTRY", "INDICATOR", "COUNTERPART_COUNTRY", "FREQUENCY"],
        )

        assert df.columns.names == ["COUNTRY", "INDICATOR", "COUNTERPART_COUNTRY", "FREQUENCY"]
        assert df.index.name == "TIME_PERIOD"

    def test_none_takes_every_attribute(self, dirpath):
        # Without a data structure definition nothing separates dimensions from attributes, so the
        # default keeps them all -- including SCALE and UNIT_MEASURE.
        df = read_structure_specific(dirpath / "imts_structure_specific.xml")

        assert set(df.columns.names) == {
            "COUNTRY",
            "INDICATOR",
            "COUNTERPART_COUNTRY",
            "FREQUENCY",
            "UNIT_MEASURE",
            "SCALE",
        }

    def test_undeclared_dimensions_are_left_out(self, dirpath):
        df = read_structure_specific(dirpath / "imts_structure_specific.xml", {"COUNTERPART_COUNTRY": "counterpart"})

        assert df.columns.names == ["counterpart"]

    def test_bare_string_is_rejected(self, dirpath):
        # A single dimension name is an easy slip, and iterating it would silently make one column
        # per character.
        with pytest.raises(TypeError, match="mapping or a sequence"):
            read_structure_specific(dirpath / "imts_structure_specific.xml", "COUNTERPART_COUNTRY")

    def test_observation_attributes_override_series(self):
        # SDMX lets an observation restate a series-level attribute; the observation's value is the
        # one that applies to it.
        document = """<StructureSpecificData>
          <DataSet>
            <Series COUNTRY="LAO" COUNTERPART_COUNTRY="THA" OBS_STATUS="A">
              <Obs TIME_PERIOD="2018" OBS_VALUE="1810.7"/>
              <Obs TIME_PERIOD="2019" OBS_VALUE="2354.6" OBS_STATUS="E"/>
            </Series>
          </DataSet>
        </StructureSpecificData>"""

        df = read_structure_specific(document, ["OBS_STATUS"])

        assert list(df.columns) == ["A", "E"]

    def test_elements_match_on_local_name(self, dirpath):
        # The target namespace is dataflow-specific, so nothing may depend on the IMF's.
        df = read_structure_specific(
            dirpath / "structure_specific_other_namespace.xml", ["REF_AREA", "MEASURE", "FREQ"]
        )

        assert df.columns.names == ["REF_AREA", "MEASURE", "FREQ"]
        assert df.iloc[0, 0] == pytest.approx(12.5)


class TestReadStructureSpecificBackends:
    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_long_schema_and_value_parity(self, dirpath, output_type):
        skip_unless_installed(output_type)
        path = dirpath / "imts_structure_specific.xml"

        wide = read_structure_specific(path, IMTS_DIMENSIONS)
        tidy = as_narwhals(read_structure_specific(path, IMTS_DIMENSIONS, output_type=output_type))

        assert tidy.columns == ["country", "indicator", "counterpart", "frequency", "period", "value"]
        assert tidy.schema["period"] == nw.Datetime
        assert len(tidy) == int(wide.notna().sum().sum())
        assert sum(tidy["value"].to_list()) == pytest.approx(float(wide.sum().sum()))

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_empty_document_keeps_the_schema(self, dirpath, output_type):
        skip_unless_installed(output_type)

        tidy = as_narwhals(read_structure_specific(dirpath / "imts_group_only.xml", IMTS_DIMENSIONS, output_type))

        assert len(tidy) == 0
        assert tidy.columns == ["country", "indicator", "counterpart", "frequency", "period", "value"]
        assert tidy.schema["period"] == nw.Datetime
