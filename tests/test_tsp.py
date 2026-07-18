import narwhals.stable.v2 as nw
import pytest

from pandas_datareader import tsp
from tests._backends import BACKENDS, as_narwhals, skip_unless_installed
from tests._mock import patch_session_get, service_up

# The TSP share-price API changed and the reader no longer parses live data, so the historical
# data tests were dropped in favour of the unit test below plus a liveness ping.


class TestTSPReader:
    def test_sanitize_response(self):
        class response:
            pass

        r = response()
        r.text = " , "
        assert tsp.TSPReader._sanitize_response(r) == ""
        r.text = " a,b "
        assert tsp.TSPReader._sanitize_response(r) == "a,b"


@pytest.mark.network
class TestTSPLive:
    def test_endpoint_reachable(self):
        if not service_up(tsp.TSPReader(start="2020-01-01", end="2020-01-02").url):
            pytest.skip("TSP endpoint unreachable")


def _tsp_csv() -> bytes:
    funds = sorted(tsp.TSPReader.all_symbols)
    header = "Date," + ",".join(funds)
    row_one = "2020-01-02," + ",".join(f"{10.0 + i:.2f}" for i in range(len(funds)))
    row_two = "2020-01-03," + ",".join(f"{10.1 + i:.2f}" for i in range(len(funds)))
    return f"{header}\n{row_one}\n{row_two}\n".encode()


class TestTSPBackends:
    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_tidy_schema_matches_pandas(self, monkeypatch, output_type):
        skip_unless_installed(output_type)
        selected = ("G Fund", "C Fund")

        patch_session_get(monkeypatch, {"tsp.gov": _tsp_csv()})
        as_pandas = tsp.TSPReader(symbols=selected, start="2020-01-01", end="2020-01-31").read()
        reader = tsp.TSPReader(symbols=selected, start="2020-01-01", end="2020-01-31", output_type=output_type)
        tidy = as_narwhals(reader.read())

        assert tidy.columns[0] == "Date"
        assert set(tidy.columns) == {"Date", *selected}
        assert tidy.schema["Date"] == nw.Datetime
        assert len(tidy) == len(as_pandas)
        assert tidy["G Fund"].to_list() == as_pandas["G Fund"].tolist()
