from datetime import datetime

import pandas as pd
import pytest

from pandas_datareader import data as web
from pandas_datareader._utils import RemoteDataError
from pandas_datareader.oecd import OECDReader
from tests._mock import live_or_record, make_response, patch_session_get, tolerate_outage

pytestmark = pytest.mark.stable

# OECD trade union density dataflow.
TUD = "OECD.ELS.SAE,DSD_TUD_CBC@DF_TUD,1.0"


class TestOECDOffline:
    def test_trade_union_density_is_parsed(self, monkeypatch, datapath):
        patch_session_get(monkeypatch, {"sdmx.oecd.org": datapath("data", "oecd", "tud.json")})

        df = web.DataReader(TUD, "oecd", start=datetime(2009, 1, 1), end=datetime(2010, 1, 1))
        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.index.min().year >= 2009
        assert df.index.max().year <= 2010

        au = (
            df.xs("Australia", axis=1, level="Reference area")
            .xs("Trade union density", axis=1, level="Measure")
            .iloc[:, 0]
        )
        assert au.loc["2009"].iloc[0] == pytest.approx(19.7, abs=0.1)

    def test_invalid_symbol_type_raises(self):
        with pytest.raises(ValueError):
            web.DataReader(1234, "oecd")

    def test_remote_error_on_bad_status(self, monkeypatch):
        patch_session_get(monkeypatch, make_response(b"", status_code=404))
        with pytest.raises(RemoteDataError):
            web.DataReader("OECD,INVALID_FLOW,1.0", "oecd")


@pytest.mark.network
class TestOECDLive:
    def test_trade_union_density_shape(self, monkeypatch, datapath):
        live_or_record(monkeypatch, {"sdmx.oecd.org": datapath("data", "oecd", "tud.json")}, OECDReader._URL)
        with tolerate_outage():
            df = web.DataReader(TUD, "oecd", start=datetime(2009, 1, 1), end=datetime(2010, 1, 1))
            assert isinstance(df.index, pd.DatetimeIndex)
            assert "Reference area" in df.columns.names
            assert len(df) > 0
