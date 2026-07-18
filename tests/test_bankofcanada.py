from datetime import date, timedelta

import narwhals.stable.v2 as nw
import pandas as pd
import pytest

from pandas_datareader import data as web
from pandas_datareader._utils import RemoteDataError
from pandas_datareader.bankofcanada import BankOfCanadaReader
from tests._backends import BACKENDS, as_narwhals, skip_unless_installed
from tests._mock import live_or_record, make_response, patch_session_get, tolerate_outage

pytestmark = pytest.mark.stable


class TestBankOfCanadaOffline:
    def test_observations_are_parsed(self, monkeypatch, datapath):
        patch_session_get(
            monkeypatch,
            {"valet/observations": datapath("data", "bankofcanada", "fx_usd_cad.csv")},
        )

        df = web.DataReader("FXUSDCAD", "bankofcanada", "2017-07-01", "2017-07-31")
        assert "FXUSDCAD" in df.columns
        assert isinstance(df.index, pd.DatetimeIndex)
        assert df.index.name == "date"
        assert len(df) > 15  # ~20 business days in July 2017
        assert df["FXUSDCAD"].loc["2017-07-05"] == pytest.approx(1.2982)

    def test_bad_range_raises(self):
        with pytest.raises(ValueError):
            web.DataReader(
                "FXCADUSD",
                "bankofcanada",
                date.today(),
                date.today() - timedelta(days=30),
            )

    def test_remote_error_on_bad_status(self, monkeypatch):
        patch_session_get(monkeypatch, make_response(b"", status_code=404))
        with pytest.raises(RemoteDataError):
            web.DataReader("abcdefgh", "bankofcanada", "2017-07-01", "2017-07-31")


@pytest.mark.network
class TestBankOfCanadaLive:
    def test_observations_shape(self, monkeypatch, datapath):
        live_or_record(
            monkeypatch,
            {"valet/observations": datapath("data", "bankofcanada", "fx_usd_cad.csv")},
            BankOfCanadaReader._URL,
        )
        with tolerate_outage():
            df = web.DataReader("FXUSDCAD", "bankofcanada", "2017-07-01", "2017-07-31")
            assert "FXUSDCAD" in df.columns
            assert len(df) > 0


class TestBankOfCanadaBackends:
    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_tidy_schema_matches_pandas(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)
        patch_session_get(
            monkeypatch,
            {"valet/observations": datapath("data", "bankofcanada", "fx_usd_cad.csv")},
        )

        as_pandas = web.DataReader("FXUSDCAD", "bankofcanada", "2017-07-01", "2017-07-31")
        tidy = as_narwhals(
            web.DataReader("FXUSDCAD", "bankofcanada", "2017-07-01", "2017-07-31", output_type=output_type)
        )

        assert tidy.columns == ["date", "FXUSDCAD"]
        assert tidy.schema["date"] == nw.Datetime
        assert len(tidy) == len(as_pandas)
        assert tidy["FXUSDCAD"].to_list() == as_pandas["FXUSDCAD"].tolist()
