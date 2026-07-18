import narwhals.stable.v2 as nw
import numpy as np
import pandas as pd
import pytest

from pandas_datareader import wb
from pandas_datareader.wb import (
    WB_API_URL,
    WorldBankReader,
    download,
    get_countries,
    get_indicators,
    search,
)
from tests._backends import BACKENDS, as_narwhals, skip_unless_installed
from tests._mock import from_fixtures, live_or_record, patch_session_get, service_up, tolerate_outage

pytestmark = pytest.mark.stable


@pytest.fixture(autouse=True)
def clear_indicator_cache(monkeypatch):
    """Reset the module-level indicator cache so each test serves its own fixture."""
    monkeypatch.setattr(wb, "_cached_series", None)


class TestWorldBankOffline:
    def test_indicators_are_paced(self, monkeypatch):
        # One pause between consecutive indicator requests, none before the first.
        sleeps = []
        monkeypatch.setattr("pandas_datareader.wb.time.sleep", sleeps.append)
        monkeypatch.setattr(
            WorldBankReader,
            "_read_one_data",
            lambda self, url, params: pd.DataFrame(
                [["US", "USA", "2010", 1.0]], columns=["country", "iso_code", "year", "x"]
            ),
        )
        WorldBankReader(symbols=["A", "B", "C"], countries="US").read()
        assert len(sleeps) == 2

    def test_download_parses_values(self, monkeypatch, datapath):
        patch_session_get(monkeypatch, {"NY.GDP.PCAP.CD": datapath("data", "wb", "country_jp_gdp.json")})

        result = download(country="JP", indicator="NY.GDP.PCAP.CD", start=2000, end=2004, errors="ignore")
        # Fixture is a frozen real recording, so round only to the nearest 100 (not 1000).
        result = np.round(result.sort_index(), decimals=-2)

        expected = pd.DataFrame(
            {
                "NY.GDP.PCAP.CD": {
                    ("Japan", "2000"): 39800.0,
                    ("Japan", "2001"): 34900.0,
                    ("Japan", "2002"): 33300.0,
                    ("Japan", "2003"): 35800.0,
                    ("Japan", "2004"): 38700.0,
                }
            }
        ).sort_index()
        expected.index.names = ["country", "year"]
        pd.testing.assert_frame_equal(result, expected)

    def test_invalid_country_raises(self):
        with pytest.raises(ValueError, match=r"Invalid Country Code\(s\): XX"):
            download(country=["USA", "XX"], indicator="NY.GDP.PCAP.CD", start=2003, end=2004, errors="raise")

    def test_bad_indicator_raises(self, monkeypatch, datapath):
        patch_session_get(
            monkeypatch,
            from_fixtures(
                {
                    "NY.GDP.PCAP.CD": datapath("data", "wb", "country_jp_gdp.json"),
                    "BAD_INDICATOR": datapath("data", "wb", "bad_indicator.json"),
                }
            ),
        )
        msg = r"The provided parameter value is not valid\. Indicator: BAD_INDICATOR"
        with pytest.raises(ValueError, match=msg):
            download(
                country=["USA"],
                indicator=["NY.GDP.PCAP.CD", "BAD_INDICATOR"],
                start=2003,
                end=2004,
                errors="raise",
            )

    def test_bad_indicator_warns(self, monkeypatch, datapath):
        patch_session_get(
            monkeypatch,
            from_fixtures(
                {
                    "NY.GDP.PCAP.CD": datapath("data", "wb", "country_jp_gdp.json"),
                    "BAD_INDICATOR": datapath("data", "wb", "bad_indicator.json"),
                }
            ),
        )
        with pytest.warns(Warning):
            result = download(
                country=["USA"],
                indicator=["NY.GDP.PCAP.CD", "BAD_INDICATOR"],
                start=2003,
                end=2004,
                errors="warn",
            )
        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0

    def test_get_countries(self, monkeypatch, datapath):
        patch_session_get(monkeypatch, {"/countries/": datapath("data", "wb", "countries.json")})

        result = get_countries()
        assert {"iso3c", "iso2c", "name", "latitude", "longitude"} <= set(result.columns)
        assert "Zimbabwe" in list(result["name"])
        assert len(result) > 100
        assert pd.notnull(result.latitude).any()
        assert result.latitude.dtype == np.float64

    def test_get_indicators(self, monkeypatch, datapath):
        # The live /indicators endpoint returns ~30k rows; recording it would bloat the repo, so
        # this is a small hand-written sample of the real row shape. TestWorldBankLive checks the
        # full count against the live API.
        patch_session_get(monkeypatch, {"/indicators?": datapath("data", "wb", "indicators.json")})

        result = get_indicators()
        exp_col = pd.Index(["id", "name", "unit", "source", "sourceNote", "sourceOrganization", "topics"])
        assert sorted(result.columns) == sorted(exp_col)
        assert len(result) == 4
        assert "NY.GDP.PCAP.KD" in result["id"].values

    def test_search(self, monkeypatch, datapath):
        patch_session_get(monkeypatch, {"/indicators?": datapath("data", "wb", "indicators.json")})

        result = search("gdp.*capita.*constant")
        assert result.name.str.contains("GDP").any()


@pytest.mark.network
class TestWorldBankLive:
    def test_download_shape(self, monkeypatch, datapath):
        live_or_record(
            monkeypatch,
            {"NY.GDP.PCAP.CD": datapath("data", "wb", "country_jp_gdp.json")},
            WB_API_URL + "/country?format=json&per_page=1",
        )
        with tolerate_outage():
            result = download(country="JP", indicator="NY.GDP.PCAP.CD", start=2000, end=2004, errors="ignore")
            assert result.columns.tolist() == ["NY.GDP.PCAP.CD"]
            assert result.index.names == ["country", "year"]
            assert len(result) > 0

    def test_countries_shape(self, monkeypatch, datapath):
        live_or_record(
            monkeypatch,
            {"/countries/": datapath("data", "wb", "countries.json")},
            WB_API_URL + "/country?format=json&per_page=1",
        )
        with tolerate_outage():
            result = get_countries()
            assert "Zimbabwe" in list(result["name"])
            assert len(result) > 100

    def test_indicators_count(self):
        # Not recorded (too large); assert the live count and row shape directly.
        if not service_up(WB_API_URL + "/country?format=json&per_page=1"):
            pytest.skip("World Bank endpoint unreachable")
        with tolerate_outage():
            result = get_indicators()
            assert len(result) > 10000
            assert {"id", "name", "source"} <= set(result.columns)


class TestWorldBankBackends:
    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_tidy_schema_matches_pandas(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)
        patch_session_get(monkeypatch, {"NY.GDP.PCAP.CD": datapath("data", "wb", "country_jp_gdp.json")})

        reader_kwargs = {"symbols": "NY.GDP.PCAP.CD", "countries": "JP", "start": 2000, "end": 2004, "errors": "ignore"}
        as_pandas = WorldBankReader(**reader_kwargs).read()
        tidy = as_narwhals(WorldBankReader(**reader_kwargs, output_type=output_type).read())

        assert tidy.columns == ["country", "year", "NY.GDP.PCAP.CD"]
        assert tidy.schema["country"] == nw.String
        assert len(tidy) == len(as_pandas)
        assert tidy["NY.GDP.PCAP.CD"].to_list() == as_pandas["NY.GDP.PCAP.CD"].tolist()
