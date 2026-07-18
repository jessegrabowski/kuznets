from datetime import datetime

import narwhals.stable.v2 as nw
import pandas as pd
import pytest

from pandas_datareader import data as web
from pandas_datareader._utils import RemoteDataError
from pandas_datareader.econdb import EcondbReader
from tests._backends import BACKENDS, as_narwhals, skip_unless_installed
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


_SERIES_PAYLOAD = {
    "results": [
        {
            "ticker": "CPIUS",
            "data": {"dates": ["2020-01-01", "2020-02-01", "2020-03-01"], "values": [1.0, 2.0, 3.0]},
            "additional_metadata": {"1:Country": "US:United States", "2:Measure": "CPI:Consumer price index"},
        },
        {
            "ticker": "CPIDE",
            "data": {"dates": ["2020-01-01", "2020-02-01"], "values": [4.0, 5.0]},
            "additional_metadata": {"1:Country": "DE:Germany", "2:Measure": "CPI:Consumer price index"},
        },
    ]
}


class TestEcondbBackends:
    def _read(self, monkeypatch, **kwargs):
        patch_session_get(monkeypatch, make_response(json=_SERIES_PAYLOAD))
        return web.DataReader(
            "dataset=CPI_ALL", "econdb", start=datetime(2020, 1, 1), end=datetime(2020, 12, 31), **kwargs
        )

    def test_pandas_wide_frame_unchanged(self, monkeypatch):
        df = self._read(monkeypatch)
        assert isinstance(df.columns, pd.MultiIndex)
        assert df.columns.names == ["Country", "Measure"]
        assert df.index.name == "TIME_PERIOD"
        assert df.shape == (3, 2)

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_tidy_long_records(self, monkeypatch, output_type):
        skip_unless_installed(output_type)
        wide = self._read(monkeypatch)
        tidy = as_narwhals(self._read(monkeypatch, output_type=output_type))

        assert tidy.columns == ["Country", "Measure", "TIME_PERIOD", "value"]
        assert tidy.schema["TIME_PERIOD"] == nw.Datetime
        assert len(tidy) == int(wide.notna().sum().sum())
        assert sorted(set(tidy["Country"].to_list())) == ["Germany", "United States"]
        assert sum(tidy["value"].to_list()) == pytest.approx(float(wide.sum().sum()))

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_tidy_date_filter(self, monkeypatch, output_type):
        skip_unless_installed(output_type)
        patch_session_get(monkeypatch, make_response(json=_SERIES_PAYLOAD))
        tidy = as_narwhals(
            web.DataReader(
                "dataset=CPI_ALL",
                "econdb",
                start=datetime(2020, 2, 1),
                end=datetime(2020, 12, 31),
                output_type=output_type,
            )
        )
        assert len(tidy) == 3
