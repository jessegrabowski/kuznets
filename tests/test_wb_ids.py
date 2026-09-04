import narwhals.stable.v2 as nw
import pandas as pd
import pytest

from kuznets.utils import RemoteDataError
from kuznets.wb_ids import WorldBankIDSReader, _records
from tests._backends import BACKENDS, as_narwhals, skip_unless_installed
from tests._mock import from_fixtures, patch_session_get, tolerate_outage

pytestmark = pytest.mark.stable

ZMB_DPPG = ("data", "wb_ids", "zmb_dppg.json")


def read_zambia(monkeypatch, datapath, **kwargs):
    patch_session_get(monkeypatch, {"api.worldbank.org": datapath(*ZMB_DPPG)})
    return WorldBankIDSReader("DT.INR.DPPG", "ZMB", **kwargs).read()


class TestRecords:
    def test_concepts_become_positional_codes(self):
        # The service reports a row's dimensions as a list of named concepts rather than as fields,
        # in no guaranteed order, so the parser keys on the concept name.
        rows = [
            {
                "variable": [
                    {"concept": "Time", "id": "YR1994", "value": "1994"},
                    {"concept": "Series", "id": "DT.INR.DPPG", "value": "..."},
                    {"concept": "Counterpart-Area", "id": "WLD", "value": "World"},
                    {"concept": "Country", "id": "ZMB", "value": "Zambia"},
                ],
                "value": 3.5,
            }
        ]

        assert _records(rows) == [(("ZMB", "DT.INR.DPPG", "WLD", "1994"), 3.5)]

    def test_a_concept_the_reader_does_not_map_is_ignored(self):
        # The service is free to add a concept; one it has not been taught about must not become a
        # dimension of the frame.
        rows = [
            {
                "variable": [
                    {"concept": "Country", "id": "ZMB", "value": "Zambia"},
                    {"concept": "Series", "id": "DT.INR.DPPG", "value": "..."},
                    {"concept": "Counterpart-Area", "id": "WLD", "value": "World"},
                    {"concept": "Time", "id": "YR1994", "value": "1994"},
                    {"concept": "Vintage", "id": "2025", "value": "2025"},
                ],
                "value": 3.5,
            }
        ]

        assert _records(rows) == [(("ZMB", "DT.INR.DPPG", "WLD", "1994"), 3.5)]

    def test_rows_without_a_value_are_dropped(self):
        rows = [
            {"variable": [{"concept": "Time", "id": "YR1994", "value": "1994"}], "value": None},
        ]

        assert _records(rows) == []


class TestWorldBankIDSOffline:
    def test_interest_on_new_commitments(self, monkeypatch, datapath):
        df = read_zambia(monkeypatch, datapath, start=1990, end=2020)

        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.columns.names == ["country", "series", "counterpart"]
        assert df.loc["1990", ("ZMB", "DT.INR.DPPG", "WLD")].item() == pytest.approx(8.1026)

    def test_the_year_range_truncates_the_frame(self, monkeypatch, datapath):
        df = read_zambia(monkeypatch, datapath, start=2000, end=2005)

        assert list(df.index.year) == [2000, 2001, 2002, 2003, 2004, 2005]

    def test_several_codes_on_a_dimension_join_into_one_request(self, monkeypatch, datapath):
        # The service takes ';'-joined lists, so reading three creditors stays one request rather
        # than becoming three.
        patch_session_get(monkeypatch, {"api.worldbank.org": datapath(*ZMB_DPPG)})
        reader = WorldBankIDSReader(
            ["DT.INR.DPPG", "DT.INR.OFFT"], ["ZMB", "AGO"], counterpart=["WLD", "905"], start=1990, end=2020
        )

        assert "/country/ZMB;AGO/" in reader.url
        assert "/series/DT.INR.DPPG;DT.INR.OFFT/" in reader.url
        assert "/counterpart-area/WLD;905/" in reader.url

    def test_the_creditor_aggregate_is_the_default(self, monkeypatch, datapath):
        patch_session_get(monkeypatch, {"api.worldbank.org": datapath(*ZMB_DPPG)})
        reader = WorldBankIDSReader("DT.INR.DPPG", "ZMB", start=1990, end=2020)

        assert "/counterpart-area/WLD/" in reader.url

    def test_an_error_document_raises_with_the_services_message(self, monkeypatch, datapath):
        # A series that does not exist, a country outside the database, and a country that simply
        # never borrowed are answered alike: HTTP 200 carrying an XML error.
        patch_session_get(monkeypatch, {"api.worldbank.org": datapath("data", "wb_ids", "error_unknown_series.xml")})

        with pytest.raises(RemoteDataError, match="not valid or data not found"):
            WorldBankIDSReader("NOT.A.SERIES", "ZMB", start=1990, end=2020).read()

    @pytest.mark.parametrize("missing", [None, "", []])
    def test_a_missing_series_or_country_raises(self, missing):
        with pytest.raises(ValueError, match="at least one series"):
            WorldBankIDSReader(missing, "ZMB")
        with pytest.raises(ValueError, match="at least one country"):
            WorldBankIDSReader("DT.INR.DPPG", missing)


class TestPaging:
    def test_every_page_is_collected(self, monkeypatch, datapath):
        # Stopping at the first page would hand back a truncated series that looks complete, which
        # is the failure a caller cannot see.
        pages = {
            1: datapath("data", "wb_ids", "paged_page1.json"),
            2: datapath("data", "wb_ids", "paged_page2.json"),
        }
        requested = []

        def by_page(url, params=None, **kwargs):
            requested.append(params["page"])
            return from_fixtures({"api.worldbank.org": pages[params["page"]]})(url, params, **kwargs)

        patch_session_get(monkeypatch, by_page)

        df = WorldBankIDSReader("DT.INR.DPPG", "ZMB", start=1970, end=2024).read()

        # Page one stops at 2009. Anything after it can only have come from page two.
        assert requested == [1, 2]
        assert df.index.max().year > 2009


class TestWorldBankIDSBackends:
    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_tidy_frame_carries_a_column_per_dimension(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)

        tidy = as_narwhals(read_zambia(monkeypatch, datapath, start=1990, end=2020, output_type=output_type))

        assert tidy.columns == ["country", "series", "counterpart", "period", "value"]
        assert tidy.schema["period"] == nw.Datetime
        assert tidy.schema["value"] == nw.Float64


@pytest.mark.network
class TestWorldBankIDSLive:
    def test_zambia_reads_from_the_live_service(self):
        with tolerate_outage():
            df = WorldBankIDSReader("DT.INR.DPPG", "ZMB", start=1990, end=2020).read()

            assert df.columns.names == ["country", "series", "counterpart"]
            assert not df.empty
