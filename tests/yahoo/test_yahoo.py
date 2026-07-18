import narwhals.stable.v2 as nw
import numpy as np
import pandas as pd
import pytest
import requests

from pandas_datareader import data as web
from pandas_datareader._utils import RemoteDataError
from pandas_datareader.data import YahooDailyReader
from pandas_datareader.yahoo._auth import _CRUMB_URL
from pandas_datareader.yahoo.fx import YahooFXReader
from tests._backends import BACKENDS, as_narwhals, skip_unless_installed
from tests._mock import from_fixtures, live_or_record, make_response, patch_session_get, tolerate_outage

# The crumb/cookie auth handshake every Yahoo reader performs before its real request. Offline these
# are stubbed; when recording they pass through to the real service so the data request is authorized.
_AUTH = {"fc.yahoo.com": make_response(b""), "getcrumb": make_response(b"testcrumb")}

# A real AAPL year that contains both a dividend and the 4:1 split (2020-08-31). Historical values
# never change, so exact assertions stay stable across re-recordings.
_CHART_START = "2020-01-01"
_CHART_END = "2020-12-31"


def _chart_offline(monkeypatch, datapath, symbol):
    patch_session_get(
        monkeypatch,
        from_fixtures({**_AUTH, f"v8/finance/chart/{symbol}": datapath("data", "yahoo", "chart_aapl_2020.json")}),
    )


class TestYahooOffline:
    def test_daily_prices_are_parsed(self, monkeypatch, datapath):
        _chart_offline(monkeypatch, datapath, "AAPL")
        df = web.get_data_yahoo("AAPL", start=_CHART_START, end=_CHART_END)

        assert list(df.columns) == ["High", "Low", "Open", "Close", "Volume", "Adj Close"]
        assert len(df) > 200
        assert (df.dtypes[["Open", "High", "Low", "Close"]] == np.float64).all()
        assert df["Volume"].loc["2020-08-31"] > 0

    def test_adjust_price_applies_ratio(self, monkeypatch, datapath):
        _chart_offline(monkeypatch, datapath, "AAPL")
        raw = web.get_data_yahoo("AAPL", start=_CHART_START, end=_CHART_END)
        adjusted = web.get_data_yahoo("AAPL", start=_CHART_START, end=_CHART_END, adjust_price=True)

        assert "Adj Close" not in adjusted.columns
        ratio = raw["Adj Close"] / raw["Close"]
        pd.testing.assert_series_equal(adjusted["Adj_Ratio"], ratio, check_names=False)
        pd.testing.assert_series_equal(adjusted["Open"], raw["Open"] * ratio, check_names=False)

    def test_supplied_session_is_used(self):
        session = requests.Session()
        assert YahooDailyReader("AAPL", session=session).session is session

    def test_quotes_are_parsed(self, monkeypatch, datapath):
        patch_session_get(
            monkeypatch,
            from_fixtures({**_AUTH, "v7/finance/quote": datapath("data", "yahoo", "quote_aapl_goog.json")}),
        )
        df = web.get_quote_yahoo(["AAPL", "GOOG"])
        assert sorted(df.index) == ["AAPL", "GOOG"]
        assert df.loc["AAPL", "price"] > 0
        assert df.loc["AAPL", "longName"] == "Apple Inc."
        assert "marketCap" in df.columns

    def test_quotes_empty_raises(self, monkeypatch):
        mapping = {**_AUTH, "v7/finance/quote": make_response(json={"quoteResponse": {"result": []}})}
        patch_session_get(monkeypatch, from_fixtures(mapping))
        with pytest.raises(RemoteDataError):
            web.get_quote_yahoo("AAPL")

    def test_actions_are_parsed(self, monkeypatch, datapath):
        _chart_offline(monkeypatch, datapath, "AAPL")
        actions = web.DataReader("AAPL", "yahoo-actions", start=_CHART_START, end=_CHART_END)
        assert set(actions["action"]) == {"DIVIDEND", "SPLIT"}
        # 4:1 split on 2020-08-31 -> ratio denominator/numerator = 0.25.
        assert actions.loc["2020-08-31", "value"] == pytest.approx(0.25)

    def test_ret_index_is_computed(self, monkeypatch, datapath):
        _chart_offline(monkeypatch, datapath, "AAPL")
        df = web.get_data_yahoo("AAPL", start=_CHART_START, end=_CHART_END, ret_index=True)
        assert "Ret_Index" in df.columns
        assert df["Ret_Index"].iloc[0] == pytest.approx(1.0)

    def test_unadjusted_dividends_scale_up_before_split(self, monkeypatch, datapath):
        _chart_offline(monkeypatch, datapath, "AAPL")
        adjusted = web.get_data_yahoo_actions("AAPL", _CHART_START, _CHART_END, adjust_dividends=True)
        unadjusted = web.get_data_yahoo_actions("AAPL", _CHART_START, _CHART_END, adjust_dividends=False)

        adj_div = adjusted[adjusted["action"] == "DIVIDEND"]["value"]
        un_div = unadjusted[unadjusted["action"] == "DIVIDEND"]["value"]
        # Dividends with an ex-date before the 2020-08-31 4:1 split are reported split-adjusted;
        # turning that off scales them back up, so the unadjusted value is larger.
        presplit = adj_div.index[adj_div.index < pd.Timestamp("2020-08-31")]
        assert len(presplit) > 0
        assert (un_div.loc[presplit] > adj_div.loc[presplit]).all()

    def test_empty_history(self, monkeypatch, datapath):
        # A hand-written "no data" response; the real service rarely returns this shape on demand.
        patch_session_get(
            monkeypatch,
            from_fixtures({**_AUTH, "v8/finance/chart/NOPE": datapath("data", "yahoo", "chart_empty.json")}),
        )
        df = web.get_data_yahoo("NOPE", start=_CHART_START, end=_CHART_END)
        assert df.dropna(how="all").empty

    def test_invalid_interval_raises(self):
        with pytest.raises(ValueError):
            YahooDailyReader("F", interval="NOT VALID")


@pytest.mark.network
class TestYahooLive:
    def test_daily_shape(self, monkeypatch, datapath):
        live_or_record(
            monkeypatch,
            {"v8/finance/chart/AAPL": datapath("data", "yahoo", "chart_aapl_2020.json")},
            _CRUMB_URL,
        )
        with tolerate_outage():
            df = web.get_data_yahoo("AAPL", start=_CHART_START, end=_CHART_END)
            assert list(df.columns) == ["High", "Low", "Open", "Close", "Volume", "Adj Close"]
            assert len(df) > 200

    def test_actions_shape(self, monkeypatch, datapath):
        live_or_record(
            monkeypatch,
            {"v8/finance/chart/AAPL": datapath("data", "yahoo", "chart_aapl_2020.json")},
            _CRUMB_URL,
        )
        with tolerate_outage():
            actions = web.DataReader("AAPL", "yahoo-actions", start=_CHART_START, end=_CHART_END)
            assert set(actions["action"]) == {"DIVIDEND", "SPLIT"}

    def test_quotes_shape(self, monkeypatch, datapath):
        live_or_record(
            monkeypatch,
            {"v7/finance/quote": datapath("data", "yahoo", "quote_aapl_goog.json")},
            _CRUMB_URL,
        )
        with tolerate_outage():
            df = web.get_quote_yahoo(["AAPL", "GOOG"])
            assert sorted(df.index) == ["AAPL", "GOOG"]
            assert "marketCap" in df.columns


class TestYahooBackends:
    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_daily_single_tidy(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)
        _chart_offline(monkeypatch, datapath, "AAPL")
        as_pandas = web.get_data_yahoo("AAPL", start=_CHART_START, end=_CHART_END)
        tidy = as_narwhals(web.get_data_yahoo("AAPL", start=_CHART_START, end=_CHART_END, output_type=output_type))

        assert tidy.columns == ["Date", "High", "Low", "Open", "Close", "Volume", "Adj Close"]
        assert tidy.schema["Date"] == nw.Datetime
        assert len(tidy) == len(as_pandas)
        assert tidy["Close"].to_list() == as_pandas["Close"].tolist()

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_daily_multi_long_panel(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)
        chart = datapath("data", "yahoo", "chart_aapl_2020.json")
        mapping = {**_AUTH, "v8/finance/chart/AAPL": chart, "v8/finance/chart/MSFT": chart}
        patch_session_get(monkeypatch, from_fixtures(mapping))

        wide = web.get_data_yahoo(["AAPL", "MSFT"], start=_CHART_START, end=_CHART_END)
        tidy = as_narwhals(
            web.get_data_yahoo(["AAPL", "MSFT"], start=_CHART_START, end=_CHART_END, output_type=output_type)
        )

        assert tidy.columns[:2] == ["Date", "Symbol"]
        assert sorted(set(tidy["Symbol"].to_list())) == ["AAPL", "MSFT"]
        assert len(tidy) == 2 * len(wide)

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_quotes_row_per_symbol(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)
        patch_session_get(
            monkeypatch,
            from_fixtures({**_AUTH, "v7/finance/quote": datapath("data", "yahoo", "quote_aapl_goog.json")}),
        )
        as_pandas = web.get_quote_yahoo(["AAPL", "GOOG"])
        tidy = as_narwhals(web.get_quote_yahoo(["AAPL", "GOOG"], output_type=output_type))

        assert "symbol" in tidy.columns
        assert "price" in tidy.columns
        assert sorted(tidy["symbol"].to_list()) == ["AAPL", "GOOG"]
        assert len(tidy) == len(as_pandas)

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_actions_single_long(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)
        _chart_offline(monkeypatch, datapath, "AAPL")
        as_pandas = web.DataReader("AAPL", "yahoo-actions", start=_CHART_START, end=_CHART_END)
        tidy = as_narwhals(
            web.DataReader("AAPL", "yahoo-actions", start=_CHART_START, end=_CHART_END, output_type=output_type)
        )

        assert tidy.columns == ["Date", "action", "value"]
        assert set(tidy["action"].to_list()) == {"DIVIDEND", "SPLIT"}
        assert len(tidy) == len(as_pandas)

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_actions_multi_single_long_frame(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)
        chart = datapath("data", "yahoo", "chart_aapl_2020.json")
        mapping = {**_AUTH, "v8/finance/chart/AAPL": chart, "v8/finance/chart/MSFT": chart}
        patch_session_get(monkeypatch, from_fixtures(mapping))

        as_dict = web.DataReader(["AAPL", "MSFT"], "yahoo-actions", start=_CHART_START, end=_CHART_END)
        assert isinstance(as_dict, dict)
        tidy = as_narwhals(
            web.DataReader(
                ["AAPL", "MSFT"], "yahoo-actions", start=_CHART_START, end=_CHART_END, output_type=output_type
            )
        )

        assert tidy.columns == ["Date", "Symbol", "action", "value"]
        assert sorted(set(tidy["Symbol"].to_list())) == ["AAPL", "MSFT"]
        assert len(tidy) == sum(len(frame) for frame in as_dict.values())

    def test_empty_history_converts(self, monkeypatch, datapath):
        skip_unless_installed("polars")
        patch_session_get(
            monkeypatch,
            from_fixtures({**_AUTH, "v8/finance/chart/NOPE": datapath("data", "yahoo", "chart_empty.json")}),
        )
        as_pandas = web.get_data_yahoo("NOPE", start=_CHART_START, end=_CHART_END)
        tidy = as_narwhals(web.get_data_yahoo("NOPE", start=_CHART_START, end=_CHART_END, output_type="polars"))
        assert len(tidy) == len(as_pandas)
        assert tidy["Close"].to_list() == [None] * len(tidy)

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_fx_single_tidy(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)
        chart = datapath("data", "yahoo", "chart_aapl_2020.json")
        patch_session_get(monkeypatch, from_fixtures({"v8/finance/chart/AUDUSD=X": chart}))

        as_pandas = YahooFXReader("AUDUSD", start=_CHART_START, end=_CHART_END).read()
        tidy = as_narwhals(YahooFXReader("AUDUSD", start=_CHART_START, end=_CHART_END, output_type=output_type).read())

        assert tidy.columns[0] == "Date"
        assert {"Open", "High", "Low", "Close"} <= set(tidy.columns)
        assert "Volume" not in tidy.columns
        assert len(tidy) == len(as_pandas)

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_fx_multi_tidy(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)
        chart = datapath("data", "yahoo", "chart_aapl_2020.json")
        mapping = {"chart/AUDUSD=X": chart, "chart/EURUSD=X": chart}
        patch_session_get(monkeypatch, from_fixtures(mapping))

        as_pandas = YahooFXReader(["AUDUSD", "EURUSD"], start=_CHART_START, end=_CHART_END).read()
        reader = YahooFXReader(["AUDUSD", "EURUSD"], start=_CHART_START, end=_CHART_END, output_type=output_type)
        tidy = as_narwhals(reader.read())

        assert {"PairCode", "Date"} <= set(tidy.columns)
        assert sorted(set(tidy["PairCode"].to_list())) == ["AUDUSD", "EURUSD"]
        assert len(tidy) == len(as_pandas)

    @pytest.mark.parametrize("output_type", BACKENDS)
    def test_dividends_single_long(self, monkeypatch, datapath, output_type):
        skip_unless_installed(output_type)
        _chart_offline(monkeypatch, datapath, "AAPL")
        as_pandas = web.DataReader("AAPL", "yahoo-dividends", start=_CHART_START, end=_CHART_END)
        tidy = as_narwhals(
            web.DataReader("AAPL", "yahoo-dividends", start=_CHART_START, end=_CHART_END, output_type=output_type)
        )

        assert tidy.columns == ["Date", "action", "value"]
        assert set(tidy["action"].to_list()) == {"DIVIDEND"}
        assert len(tidy) == len(as_pandas)
