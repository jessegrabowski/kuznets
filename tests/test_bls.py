import json

import narwhals.stable.v2 as nw
import numpy as np
import pandas as pd
import pytest

from kuznets.bls import BLS_API_URL, BLSReader
from kuznets.data import get_data_bls
from kuznets.utils import RemoteDataError
from tests._backends import BACKENDS, as_narwhals, skip_unless_installed
from tests._mock import make_response, patch_session_post, service_up, tolerate_outage

pytestmark = pytest.mark.stable

SERIES_2023 = ["CUUR0000SA0", "CUUS0000SA0", "LES1252881600"]


def bls_response(*series: tuple[str, list[tuple[str, str, str]]]) -> bytes:
    """A successful response carrying each series' (year, period, value) rows."""
    return json.dumps(
        {
            "status": "REQUEST_SUCCEEDED",
            "message": [],
            "Results": {
                "series": [
                    {
                        "seriesID": series_id,
                        "data": [{"year": year, "period": period, "value": value} for year, period, value in rows],
                    }
                    for series_id, rows in series
                ]
            },
        }
    ).encode()


def read_2023(monkeypatch, datapath, **kwargs):
    body = datapath("data", "bls", "cpi_and_earnings_2023.json").read_bytes()
    patch_session_post(monkeypatch, make_response(body))
    return get_data_bls(SERIES_2023, start=2023, end=2023, **kwargs)


class TestBLSOffline:
    def test_observations_are_stamped_at_the_start_of_their_period(self, monkeypatch, datapath):
        df = read_2023(monkeypatch, datapath)

        assert df.index.name == "DATE"
        assert list(df.columns) == SERIES_2023
        assert df.index.is_monotonic_increasing
        # Monthly, semiannual and quarterly series share one index, each at its period's first day.
        assert df.loc["2023-01-01", "CUUR0000SA0"] == pytest.approx(299.170)
        assert df.loc["2023-12-01", "CUUR0000SA0"] == pytest.approx(306.746)
        assert df.loc["2023-07-01", "CUUS0000SA0"] == pytest.approx(306.996)
        assert df.loc["2023-07-01", "LES1252881600"] == 366
        assert df["CUUS0000SA0"].count() == 2
        assert df["LES1252881600"].count() == 4

    def test_annual_averages_are_left_out_and_dashes_read_as_missing(self, monkeypatch):
        rows = [("2023", "M01", "1.5"), ("2023", "M02", "-"), ("2023", "M13", "9.9")]
        patch_session_post(monkeypatch, make_response(bls_response(("SERIES", rows))))

        df = get_data_bls("SERIES", start=2023, end=2023)

        assert list(df.index) == [pd.Timestamp("2023-01-01"), pd.Timestamp("2023-02-01")]
        assert df["SERIES"].iloc[0] == 1.5
        assert np.isnan(df["SERIES"].iloc[1])

    @pytest.mark.parametrize(
        ("api_key", "year_spans", "batch_sizes"),
        [
            (None, [("1979", "1988"), ("1989", "1998"), ("1999", "2008"), ("2009", "2018"), ("2019", "2026")], [25, 5]),
            ("key", [("1979", "1998"), ("1999", "2018"), ("2019", "2026")], [30]),
        ],
    )
    def test_requests_stay_within_the_per_request_limits(self, monkeypatch, api_key, year_spans, batch_sizes):
        # The API truncates a request past its limits and still reports success, so an oversized
        # request would come back short rather than failing.
        names = [f"SERIES{i:02d}" for i in range(30)]
        payloads = []

        def answer(url, json=None, **kwargs):
            payloads.append(json)
            return make_response(
                bls_response(*((name, [(json["startyear"], "A01", "1")]) for name in json["seriesid"]))
            )

        patch_session_post(monkeypatch, answer)
        monkeypatch.setattr("kuznets.bls.time.sleep", lambda seconds: None)
        # A key in the environment would turn the keyless case into a keyed one.
        monkeypatch.delenv("BLS_API_KEY", raising=False)

        df = BLSReader(names, start=1979, end=2026, api_key=api_key).read()

        assert [len(payload["seriesid"]) for payload in payloads[:: len(year_spans)]] == batch_sizes
        assert [(payload["startyear"], payload["endyear"]) for payload in payloads[: len(year_spans)]] == year_spans
        assert all(payload.get("registrationkey") == api_key for payload in payloads)
        assert list(df.columns) == names

    def test_an_unrecognized_period_code_raises(self, monkeypatch):
        # A period the reader cannot place would otherwise land on a wrong date.
        patch_session_post(monkeypatch, make_response(bls_response(("SERIES", [("2023", "W01", "1")]))))

        with pytest.raises(ValueError, match="W01"):
            get_data_bls("SERIES", start=2023, end=2023)

    def test_a_series_with_no_observations_raises(self, monkeypatch, datapath):
        body = datapath("data", "bls", "invalid_series.json").read_bytes()
        patch_session_post(monkeypatch, make_response(body))

        with pytest.raises(RemoteDataError, match="NOTASERIES1"):
            get_data_bls(["NOTASERIES1", "LNS14000000"], start=2023, end=2024)

    def test_a_refused_request_raises_the_api_message(self, monkeypatch):
        refused = {
            "status": "REQUEST_NOT_PROCESSED",
            "message": ["The daily threshold has been reached."],
            "Results": {},
        }
        patch_session_post(monkeypatch, make_response(json=refused))

        with pytest.raises(RemoteDataError, match="daily threshold"):
            get_data_bls("LNS14000000", start=2023, end=2023)

    def test_a_rejected_key_is_not_quoted_in_the_error(self, monkeypatch):
        refused = {
            "status": "REQUEST_NOT_PROCESSED",
            "message": ["The key:abc123 provided by the User is invalid."],
            "Results": {},
        }
        patch_session_post(monkeypatch, make_response(json=refused))

        with pytest.raises(RemoteDataError, match="invalid") as excinfo:
            get_data_bls("LNS14000000", start=2023, end=2023, api_key="abc123")

        assert "abc123" not in str(excinfo.value)


@pytest.mark.network
class TestBLSLive:
    def test_unemployment_rate_reads_a_whole_year(self):
        # One request: the keyless API allows 25 a day.
        if not service_up(f"{BLS_API_URL}LNS14000000"):
            pytest.skip("api.bls.gov unreachable")

        with tolerate_outage():
            df = get_data_bls("LNS14000000", start=2023, end=2023)

            assert list(df.columns) == ["LNS14000000"]
            assert len(df) == 12


class TestBLSBackends:
    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_tidy_schema_matches_pandas(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)

        wide = read_2023(monkeypatch, datapath)
        tidy = as_narwhals(read_2023(monkeypatch, datapath, output_type=output_type))

        assert tidy.columns == ["DATE", *SERIES_2023]
        assert tidy.schema["DATE"] == nw.Datetime
        assert len(tidy) == len(wide)
