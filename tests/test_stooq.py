import narwhals.stable.v2 as nw
import pytest

from pandas_datareader import data as web
from pandas_datareader._utils import SymbolWarning
from pandas_datareader.data import get_data_stooq
from tests._backends import BACKENDS, as_narwhals, skip_unless_installed
from tests._mock import make_response, patch_session_get, service_up

pytestmark = pytest.mark.stable


class TestStooqOffline:
    # Stooq now serves a JavaScript anti-bot challenge to every non-browser client, so its real
    # response can't be recorded (see TestStooqLive). This fixture is a hand-written sample of the
    # historical CSV format and pins the parser only; it can't catch upstream shape drift.
    def test_datareader_parses_prices(self, monkeypatch, datapath):
        patch_session_get(monkeypatch, {"stooq.com": datapath("data", "stooq", "spy.csv")})
        df = web.DataReader("SPY", "stooq")
        assert df.shape[0] == 9
        assert {"Open", "High", "Low", "Close", "Volume"} <= set(df.columns)

    def test_close_value_is_parsed(self, monkeypatch, datapath):
        patch_session_get(monkeypatch, {"stooq.com": datapath("data", "stooq", "spy.csv")})
        df = get_data_stooq("SPY", start="20180101", end="20180115")
        assert df["Close"].loc["2018-01-12"] == pytest.approx(277.92)

    def test_failed_symbol_warns_and_fills_nan(self, monkeypatch, datapath):
        # Stooq sends every symbol to the same URL (only the query string differs), so dispatch on
        # the ``s`` param: a real CSV for SPY, an empty body for the bad symbol.
        spy = datapath("data", "stooq", "spy.csv").read_bytes()

        def handler(url, params=None, **kwargs):
            return make_response(b"") if "BADSYM" in (params or {}).get("s", "") else make_response(spy)

        patch_session_get(monkeypatch, handler)
        with pytest.warns(SymbolWarning):
            df = web.DataReader(["SPY", "BADSYM"], "stooq")

        assert df["Close"]["BADSYM"].isna().all()
        assert df["Close"]["SPY"].notna().any()


@pytest.mark.network
@pytest.mark.xfail(reason="Stooq serves a JS anti-bot challenge to non-browser clients", strict=False)
class TestStooqLive:
    def test_returns_price_csv(self):
        # Will xpass if Stooq ever drops the anti-bot wall for the reader's plain client.
        if not service_up("https://stooq.com"):
            pytest.skip("Stooq unreachable")
        df = web.DataReader("SPY", "stooq")
        assert {"Open", "High", "Low", "Close", "Volume"} <= set(df.columns)
        assert len(df) > 0


class TestStooqBackends:
    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_single_symbol_tidy_schema(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)
        patch_session_get(monkeypatch, {"stooq.com": datapath("data", "stooq", "spy.csv")})

        as_pandas = web.DataReader("SPY", "stooq")
        tidy = as_narwhals(web.DataReader("SPY", "stooq", output_type=output_type))

        assert tidy.columns[0] == "Date"
        assert set(tidy.columns) >= {"Open", "High", "Low", "Close", "Volume"}
        assert tidy.schema["Date"] == nw.Datetime
        assert len(tidy) == len(as_pandas)
        assert tidy["Close"].to_list() == as_pandas["Close"].tolist()

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_multi_symbol_long_panel(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)
        spy = datapath("data", "stooq", "spy.csv").read_bytes()

        def handler(url, params=None, **kwargs):
            return make_response(b"") if "BADSYM" in (params or {}).get("s", "") else make_response(spy)

        patch_session_get(monkeypatch, handler)
        with pytest.warns(SymbolWarning):
            wide = web.DataReader(["SPY", "BADSYM"], "stooq")
        with pytest.warns(SymbolWarning):
            tidy = as_narwhals(web.DataReader(["SPY", "BADSYM"], "stooq", output_type=output_type))

        assert tidy.columns[:2] == ["Date", "Symbol"]
        assert set(tidy.columns) >= {"Open", "High", "Low", "Close"}
        assert tidy.schema["Date"] == nw.Datetime
        assert sorted(set(tidy["Symbol"].to_list())) == ["BADSYM", "SPY"]
        # One row per (date, symbol); the failed symbol appears as all-null rows.
        assert len(tidy) == 2 * len(wide)
        rows = list(zip(tidy["Symbol"].to_list(), tidy["Close"].to_list(), strict=True))
        bad_close = [value for symbol, value in rows if symbol == "BADSYM"]
        assert all(value is None or value != value for value in bad_close)
        spy_close = [value for symbol, value in rows if symbol == "SPY"]
        assert spy_close == wide["Close"]["SPY"].sort_index().tolist()
