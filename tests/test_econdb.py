import pytest

from pandas_datareader import data as web
from pandas_datareader._utils import RemoteDataError
from pandas_datareader.econdb import EcondbReader
from tests._mock import make_response, patch_session_get, service_up

# EconDB closed its public series API; requests without credentials now return HTTP 401. The
# data-parsing tests were removed rather than left hitting the live service on every run. Restore
# them with a captured authenticated response and a patched session once the reader gains auth.


class TestEcondbOffline:
    def test_unauthorized_raises_remote_error(self, monkeypatch):
        body = {"detail": "Authentication credentials were not provided."}
        patch_session_get(monkeypatch, make_response(json=body, status_code=401))
        with pytest.raises(RemoteDataError):
            web.DataReader("ticker=RGDPUS", "econdb")


@pytest.mark.network
class TestEcondbLive:
    def test_endpoint_reachable(self):
        if not service_up(EcondbReader._URL):
            pytest.skip("EconDB endpoint unreachable")
