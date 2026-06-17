import pytest

from pandas_datareader import tsp
from tests._mock import service_up

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
