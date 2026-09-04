import re

import narwhals.stable.v2 as nw
import pandas as pd
import pytest

from kuznets.imf import IMFReader, IMTSReader
from kuznets.utils import RemoteDataError
from tests._backends import BACKENDS, as_narwhals, skip_unless_installed
from tests._mock import from_fixtures, live_or_record, make_response, patch_session_get, tolerate_outage

pytestmark = pytest.mark.stable

# Laos's 2019 goods exports, as recorded from the live service: 105 counterparts, of which 86 are
# individual partners and the rest regional, income and world aggregates.
LAOS_2019 = ("data", "imf", "imts_lao_2019_exports.xml")


def read_laos(monkeypatch, datapath, start="2019", end="2019", **kwargs):
    patch_session_get(monkeypatch, {"api.imf.org": datapath(*LAOS_2019)})
    return IMTSReader("LAO", start=start, end=end, **kwargs).read()


class TestIMTSOffline:
    def test_exports_by_partner(self, monkeypatch, datapath):
        df = read_laos(monkeypatch, datapath)

        assert isinstance(df.index, pd.DatetimeIndex)
        assert list(df.index.year) == [2019]
        assert df.columns.names == ["country", "indicator", "counterpart", "frequency"]
        assert len(df.columns) == 105

        exports = df.xs("XG_FOB_USD", axis=1, level="indicator").iloc[0].droplevel(["country", "frequency"])
        partners = exports[[code.isalpha() for code in exports.index]]
        assert len(partners) == 86
        # The shares that make this dataflow worth reading: Laos's exports are dominated by three
        # neighbors, and those weights are what a trade-weighted foreign output term is built from.
        assert partners["THA"] / partners.sum() == pytest.approx(0.4143, abs=1e-4)
        assert partners["CHN"] / partners.sum() == pytest.approx(0.2879, abs=1e-4)
        assert partners["VNM"] / partners.sum() == pytest.approx(0.1816, abs=1e-4)

    def test_aggregate_counterparts_are_returned(self, monkeypatch, datapath):
        # G001 is the world total, and it very nearly equals the sum of the individual partners --
        # which is exactly why summing the whole counterpart dimension double-counts.
        df = read_laos(monkeypatch, datapath)

        exports = df.xs("XG_FOB_USD", axis=1, level="indicator").iloc[0].droplevel(["country", "frequency"])
        partners = exports[[code.isalpha() for code in exports.index]]
        aggregates = set(exports.index) - set(partners.index)

        # The aggregate codes are not all G-prefixed, which is why nothing filters on the prefix.
        assert aggregates >= {"G001", "GX170", "TX898"}
        assert exports["G001"] == pytest.approx(partners.sum(), rel=1e-5)

    def test_key_follows_the_dataflow_dimension_order(self):
        # COUNTRY.INDICATOR.COUNTERPART_COUNTRY.FREQUENCY. Getting this order wrong is answered with
        # an empty document rather than an error, so it is worth pinning.
        assert IMTSReader("LAO").key == "LAO.XG_FOB_USD..A"
        assert IMTSReader("LAO", counterpart="THA", indicator="TBG_USD", freq="Q").key == "LAO.TBG_USD.THA.Q"
        assert IMTSReader(["LAO", "THA"], indicator=["XG_FOB_USD", "MG_CIF_USD"]).key == (
            "LAO+THA.XG_FOB_USD+MG_CIF_USD..A"
        )

    def test_a_partial_year_keeps_the_periods_the_service_sent(self, monkeypatch, datapath):
        # The request is bounded by year, and an annual period is stamped at January 1st, so local
        # filtering on the exact dates would drop the very rows the service was asked for.
        df = read_laos(monkeypatch, datapath, start="2019-06-01", end="2019-12-31")

        assert list(df.index.year) == [2019]

    def test_reading_costs_one_request(self, monkeypatch, datapath):
        # IMTS declares its own dimensions, so a read goes straight to the data. Discovering them
        # instead would put two structure requests in front of every read.
        requested = []

        def counting(url, params=None, **kwargs):
            requested.append(url)
            return from_fixtures({"api.imf.org": datapath(*LAOS_2019)})(url, params, **kwargs)

        patch_session_get(monkeypatch, counting)

        IMTSReader("LAO", start="2019", end="2019").read()

        assert len(requested) == 1
        assert "/data/IMF.STA,IMTS,1.0.0/" in requested[0]

    def test_params_bound_the_year_range(self):
        reader = IMTSReader("LAO", start="2015", end="2019")

        assert reader.params == {
            "startPeriod": 2015,
            "endPeriod": 2019,
            "format": "structurespecificdata",
        }


class TestIMTSGuards:
    def test_alpha_2_country_code_raises(self, monkeypatch):
        # The IMF answers 'LA' with HTTP 200 and no observations, so this has to fail before the
        # request goes out. An unmapped handler makes any request an error.
        patch_session_get(monkeypatch, {})

        with pytest.raises(ValueError, match="alpha-3"):
            IMTSReader("LA")

    def test_counterpart_alpha_2_code_raises(self, monkeypatch):
        patch_session_get(monkeypatch, {})

        with pytest.raises(ValueError, match="alpha-3"):
            IMTSReader("LAO", counterpart=["THA", "VN"])

    def test_aggregate_counterpart_is_accepted(self):
        # G001 is the world aggregate and a legitimate selection, so the alpha-3 check must not
        # reject codes that are merely not alpha-3.
        assert IMTSReader("LAO", counterpart="G001").key == "LAO.XG_FOB_USD.G001.A"

    def test_missing_indicator_raises(self, monkeypatch):
        patch_session_get(monkeypatch, {})

        with pytest.raises(ValueError, match="explicit indicator"):
            IMTSReader("LAO", indicator=None)

    @pytest.mark.parametrize("symbols", [None, "", []])
    def test_missing_country_raises(self, symbols):
        with pytest.raises(ValueError, match="at least one reporting country"):
            IMTSReader(symbols)

    def test_country_codes_are_upper_cased(self):
        assert IMTSReader("lao", counterpart="tha").key == "LAO.XG_FOB_USD.THA.A"

    @pytest.mark.parametrize("output_type", ["pandas", *BACKENDS])
    def test_empty_observation_set_raises(self, monkeypatch, datapath, output_type):
        # What a wildcarded indicator returns: a well-formed document of <Group> metadata and no
        # observations, under HTTP 200.
        skip_unless_installed(output_type)
        patch_session_get(monkeypatch, {"api.imf.org": datapath("io", "data", "sdmx", "imts_group_only.xml")})

        with pytest.raises(RemoteDataError, match=re.escape("LAO.XG_FOB_USD..A")):
            IMTSReader("LAO", output_type=output_type).read()

    def test_remote_error_on_bad_status(self, monkeypatch):
        patch_session_get(monkeypatch, make_response(b"", status_code=404))

        with pytest.raises(RemoteDataError):
            IMTSReader("LAO").read()


@pytest.mark.network
class TestIMTSLive:
    def test_exports_by_partner_shape(self, monkeypatch, datapath):
        live_or_record(monkeypatch, {"api.imf.org": datapath(*LAOS_2019)}, IMTSReader._URL)

        with tolerate_outage():
            df = IMTSReader("LAO", start="2019", end="2019").read()

            # Shape, not values: the IMF revises historical trade figures, and a revision is not
            # the drift this test exists to catch.
            assert isinstance(df.index, pd.DatetimeIndex)
            assert df.columns.names == ["country", "indicator", "counterpart", "frequency"]
            assert "THA" in df.columns.get_level_values("counterpart")
            assert len(df.columns) > 50


class TestIMTSBackends:
    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_long_schema_and_value_parity(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)

        wide = read_laos(monkeypatch, datapath)
        tidy = as_narwhals(read_laos(monkeypatch, datapath, output_type=output_type))

        assert tidy.columns == ["country", "indicator", "counterpart", "frequency", "period", "value"]
        assert tidy.schema["period"] == nw.Datetime
        assert len(tidy) == int(wide.notna().sum().sum())
        assert sum(tidy["value"].to_list()) == pytest.approx(float(wide.sum().sum()))
        assert set(tidy["counterpart"].to_list()) == set(wide.columns.get_level_values("counterpart"))

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_a_partial_year_keeps_the_periods_the_service_sent(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)

        tidy = as_narwhals(
            read_laos(monkeypatch, datapath, start="2019-06-01", end="2019-12-31", output_type=output_type)
        )

        assert len(tidy) == 105


@pytest.mark.network
class TestIMFDataflowsLive:
    @pytest.mark.filterwarnings("ignore:Could not infer format:UserWarning")
    def test_dataflows_of_different_shapes_read_from_one_code_path(self):
        # CPI carries five dimensions and MFS_IR three, so a key of the wrong arity would come back
        # empty rather than raising. Nothing here names either shape.
        with tolerate_outage():
            prices = IMFReader("CPI", {"COUNTRY": "ZMB", "FREQUENCY": "M"}, start="2020", end="2020").read()
            rates = IMFReader("MFS_IR", {"COUNTRY": "ZMB", "FREQUENCY": "M"}, start="2020", end="2020").read()

            assert list(prices.columns.names) == [
                "COUNTRY",
                "INDEX_TYPE",
                "COICOP_1999",
                "TYPE_OF_TRANSFORMATION",
                "FREQUENCY",
            ]
            assert list(rates.columns.names) == ["COUNTRY", "INDICATOR", "FREQUENCY"]

    def test_an_alpha_2_country_code_is_rejected_before_the_data_request(self):
        with tolerate_outage(), pytest.raises(ValueError, match="did you mean 'LAO'"):
            IMFReader("CPI", {"COUNTRY": "LA", "FREQUENCY": "M"}, start="2020", end="2020").read()

    def test_a_country_that_does_not_report_is_named_as_missing_coverage(self):
        # Lao PDR reports no monetary statistics at any frequency, with every code in the key valid.
        with tolerate_outage(), pytest.raises(RemoteDataError, match="every selected code exists"):
            IMFReader("MFS_IR", {"COUNTRY": "LAO", "FREQUENCY": "M"}, start="2020", end="2020").read()
