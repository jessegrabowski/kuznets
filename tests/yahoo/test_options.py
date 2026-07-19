import numpy as np
import pandas as pd
from pandas import testing as tm
import pytest

from kuznets import data as web
from kuznets.yahoo._auth import _CRUMB_URL
from tests._mock import from_fixtures, live_or_record, make_response, patch_session_get, tolerate_outage

# The crumb/cookie handshake the options reader performs before each request.
_AUTH = {"fc.yahoo.com": make_response(b""), "getcrumb": make_response(b"testcrumb")}

EXP_COLUMNS = pd.Index(
    [
        "Last",
        "Bid",
        "Ask",
        "Chg",
        "PctChg",
        "Vol",
        "Open_Int",
        "IV",
        "Root",
        "IsNonstandard",
        "Underlying",
        "Underlying_Price",
        "Quote_Time",
        "Last_Trade_Date",
        "JSON",
    ]
)


def _assert_option_result(df):
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 1
    tm.assert_index_equal(df.columns, EXP_COLUMNS)
    assert df.index.names == ["Strike", "Expiry", "Type", "Symbol"]
    for col in ("Last", "Bid", "Ask", "IV", "Underlying_Price"):
        assert np.issubdtype(df[col].dtype, np.floating)
    assert df["IsNonstandard"].dtype == np.bool_
    for col in ("Quote_Time", "Last_Trade_Date"):
        assert np.issubdtype(df[col].dtype, np.datetime64)


def _offline(monkeypatch, datapath):
    patch_session_get(
        monkeypatch,
        from_fixtures({**_AUTH, "v7/finance/options/AAPL": datapath("data", "yahoo", "options_aapl.json")}),
    )


class TestYahooOptionsOffline:
    @classmethod
    def setup_class(cls):
        pytest.importorskip("lxml")

    def test_get_options_data(self, monkeypatch, datapath):
        _offline(monkeypatch, datapath)
        opt = web.Options("AAPL")
        _assert_option_result(opt.get_options_data(expiry=opt.expiry_dates[0]))

    def test_get_call_data(self, monkeypatch, datapath):
        _offline(monkeypatch, datapath)
        opt = web.Options("AAPL")
        calls = opt.get_call_data(expiry=opt.expiry_dates[0])
        _assert_option_result(calls)
        assert (calls.index.get_level_values("Type") == "call").all()

    def test_get_put_data(self, monkeypatch, datapath):
        _offline(monkeypatch, datapath)
        opt = web.Options("AAPL")
        puts = opt.get_put_data(expiry=opt.expiry_dates[0])
        _assert_option_result(puts)
        assert (puts.index.get_level_values("Type") == "put").all()

    def test_get_expiry_dates(self, monkeypatch, datapath):
        _offline(monkeypatch, datapath)
        opt = web.Options("AAPL")
        assert len(opt._get_expiry_dates()) > 1

    def test_underlying_price(self, monkeypatch, datapath):
        _offline(monkeypatch, datapath)
        opt = web.Options("AAPL")
        opt.get_options_data(expiry=opt.expiry_dates[0])
        assert isinstance(opt.underlying_price, int | float)

    def test_invalid_month_year(self, monkeypatch, datapath):
        _offline(monkeypatch, datapath)
        opt = web.Options("AAPL")
        with pytest.raises(ValueError):
            opt.get_options_data(month=3)
        with pytest.raises(ValueError):
            opt.get_options_data(year=1992)


@pytest.mark.network
class TestYahooOptionsLive:
    @classmethod
    def setup_class(cls):
        pytest.importorskip("lxml")

    def test_options_data_shape(self, monkeypatch, datapath):
        live_or_record(
            monkeypatch,
            {"v7/finance/options/AAPL": datapath("data", "yahoo", "options_aapl.json")},
            _CRUMB_URL,
        )
        with tolerate_outage():
            opt = web.Options("AAPL")
            _assert_option_result(opt.get_options_data(expiry=opt.expiry_dates[0]))
