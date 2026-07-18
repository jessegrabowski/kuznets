import datetime as dt
import importlib.util
import threading

import pandas as pd
import pytest
import requests

from pandas_datareader import base as base
from pandas_datareader._utils import (
    DEFAULT_USER_AGENT,
    RETRYABLE_STATUS_CODES,
    RemoteDataError,
    _init_session,
)
from tests._mock import from_fixtures, make_response, patch_session_get

pytestmark = pytest.mark.stable


class _FakeResponse:
    def __init__(self, status_code, headers=None, encoding=None, text=""):
        self.status_code = status_code
        self.headers = headers or {}
        self.encoding = encoding
        self.text = text


class _FakeSession:
    def __init__(self, response):
        self._response = response
        self.calls = 0

    def get(self, *args, **kwargs):
        self.calls += 1
        return self._response

    def close(self):
        pass


def _retry_strategy(session):
    return session.get_adapter("https://").max_retries


class TestBaseReader:
    def test_requests_not_monkey_patched(self):
        assert not hasattr(requests.Session(), "stor")

    def test_valid_retry_count(self):
        with pytest.raises(ValueError):
            base._BaseReader([], retry_count="stuff")
        with pytest.raises(ValueError):
            base._BaseReader([], retry_count=-1)

    def test_invalid_url(self):
        with pytest.raises(NotImplementedError):
            _ = base._BaseReader([]).url

    def test_invalid_format(self):
        b = base._BaseReader([])
        b._format = "IM_NOT_AN_IMPLEMENTED_TYPE"
        with pytest.raises(NotImplementedError):
            b._read_one_data("a", None)

    def test_default_start_date(self):
        b = base._BaseReader([])
        assert b.default_start_date == dt.date.today() - dt.timedelta(days=365 * 5)

    def test_created_session_advertises_user_agent(self):
        assert _init_session(None).headers["User-Agent"] == DEFAULT_USER_AGENT
        assert DEFAULT_USER_AGENT.startswith("pandas-datareader")

    def test_supplied_session_user_agent_preserved(self):
        session = requests.Session()
        session.headers["User-Agent"] = "custom/1.0"
        assert _init_session(session).headers["User-Agent"] == "custom/1.0"

    def test_headers_kwarg_overrides_user_agent(self):
        ua = "Mozilla/5.0 (custom)"
        assert _init_session(None, headers={"User-Agent": ua}).headers["User-Agent"] == ua

    def test_reader_headers_kwarg_applied_to_session(self):
        ua = "Mozilla/5.0 (custom)"
        b = base._BaseReader([], headers={"User-Agent": ua})
        assert b.session.headers["User-Agent"] == ua

    def test_get_response_returns_ok(self):
        b = base._BaseReader([])
        b.session = _FakeSession(_FakeResponse(requests.codes.ok))
        assert b._get_response("http://example.com").status_code == requests.codes.ok

    def test_get_response_raises_on_error(self):
        b = base._BaseReader([])
        b.session = _FakeSession(_FakeResponse(404, encoding="utf-8", text="nope"))
        with pytest.raises(RemoteDataError):
            b._get_response("http://example.com")

    def test_get_response_lets_output_error_raise_first(self):
        # A subclass's _output_error gets the final response and may raise a more specific error.
        class _Reader(base._BaseReader):
            def _output_error(self, out):
                raise ValueError("specific")

        b = _Reader([])
        b.session = _FakeSession(_FakeResponse(400))
        with pytest.raises(ValueError, match="specific"):
            b._get_response("http://example.com")


class TestRetryStrategy:
    def test_created_session_mounts_retry(self):
        retry = _retry_strategy(_init_session(None, retry_count=5, pause=0.25))
        assert retry.total == 5
        assert retry.backoff_factor == 0.25
        assert retry.respect_retry_after_header is True
        # raise_on_status must be False so the exhausted response reaches our error handling.
        assert retry.raise_on_status is False
        assert set(RETRYABLE_STATUS_CODES) == set(retry.status_forcelist)

    def test_reader_configures_session_from_retry_args(self):
        retry = _retry_strategy(base._BaseReader([], retry_count=7, pause=0.5).session)
        assert retry.total == 7
        assert retry.backoff_factor == 0.5


class TestDailyBaseReader:
    def test_get_params(self):
        b = base._DailyBaseReader()
        with pytest.raises(NotImplementedError):
            b._get_params()


class _CsvOutputReader(base._BaseReader):
    @property
    def url(self):
        return "https://example.test/data.csv"


class TestOutputType:
    csv_body = b"Date,Close\n2020-01-02,1.5\n2020-01-01,1.0\n"

    def test_invalid_output_type_raises_before_any_request(self, monkeypatch):
        patch_session_get(monkeypatch, from_fixtures({}))
        with pytest.raises(ValueError, match="not supported"):
            base._BaseReader([], output_type="bogus")

    def test_missing_backend_raises_import_error_before_any_request(self, monkeypatch):
        patch_session_get(monkeypatch, from_fixtures({}))
        monkeypatch.setattr(importlib.util, "find_spec", lambda module: None)
        with pytest.raises(ImportError, match=r"pandas-datareader\[polars\]"):
            base._BaseReader([], output_type="polars")

    def test_pandas_default_unchanged_through_dispatcher(self, monkeypatch):
        patch_session_get(monkeypatch, from_fixtures({"example.test": self.csv_body}))
        result = _CsvOutputReader("X").read()
        assert isinstance(result.index, pd.DatetimeIndex)
        assert result.index.name == "Date"
        assert result["Close"].tolist() == [1.0, 1.5]

    def test_polars_output_through_base_dispatcher(self, monkeypatch):
        polars = pytest.importorskip("polars")
        patch_session_get(monkeypatch, from_fixtures({"example.test": self.csv_body}))
        result = _CsvOutputReader("X", output_type="polars").read()
        assert isinstance(result, polars.DataFrame)
        assert result.columns == ["Date", "Close"]
        assert result["Close"].to_list() == [1.0, 1.5]

    def test_pyarrow_output_through_base_dispatcher(self, monkeypatch):
        pyarrow = pytest.importorskip("pyarrow")
        patch_session_get(monkeypatch, from_fixtures({"example.test": self.csv_body}))
        result = _CsvOutputReader("X", output_type="pyarrow").read()
        assert isinstance(result, pyarrow.Table)
        assert result.column_names == ["Date", "Close"]
        assert result["Close"].to_pylist() == [1.0, 1.5]

    def test_dict_payload_raises_not_implemented_for_non_pandas(self):
        pytest.importorskip("polars")

        class _DictPayloadReader(base._BaseReader):
            def _read_core(self):
                return {0: pd.DataFrame({"x": [1.0]}), "DESCR": "description"}

        with pytest.raises(NotImplementedError, match="not yet supported by _DictPayloadReader"):
            _DictPayloadReader([], output_type="polars").read()

    def test_multiindex_column_payload_raises_not_implemented_for_non_pandas(self):
        pytest.importorskip("polars")

        class _PanelPayloadReader(base._BaseReader):
            def _read_core(self):
                columns = pd.MultiIndex.from_tuples([("a", "x"), ("a", "y")])
                return pd.DataFrame([[1.0, 2.0]], columns=columns)

        with pytest.raises(NotImplementedError, match="not yet supported by _PanelPayloadReader"):
            _PanelPayloadReader([], output_type="polars").read()


class _ConcurrentDailyReader(base._DailyBaseReader):
    @property
    def url(self):
        return "https://example.test/prices"

    def _get_params(self, symbol):
        return {"s": symbol}


def _price_handler(call_log, lock):
    def handler(url, params=None, **kwargs):
        symbol = (params or {})["s"]
        with lock:
            call_log.append((threading.get_ident(), symbol))
        if symbol.startswith("BAD"):
            return make_response(b"")
        value = float(symbol[3:])
        return make_response(f"Date,Close\n2020-01-02,{value}\n2020-01-03,{value + 0.5}\n".encode())

    return handler


class TestConcurrentFetch:
    def test_helper_preserves_input_order_under_staggered_completion(self):
        release_first = threading.Event()

        def fetch_one(symbol):
            if symbol == "A":
                assert release_first.wait(5)
            else:
                release_first.set()
            return symbol.lower()

        results = base._fetch_symbols_concurrently(["A", "B"], fetch_one, max_workers=2)
        assert results == [("A", "a"), ("B", "b")]

    def test_helper_returns_caught_exceptions_and_propagates_others(self):
        def fetch_one(symbol):
            if symbol == "OS":
                raise OSError("caught")
            raise RuntimeError("propagates")

        results = base._fetch_symbols_concurrently(["OS"], fetch_one, max_workers=2)
        assert isinstance(results[0][1], OSError)
        with pytest.raises(RuntimeError):
            base._fetch_symbols_concurrently(["RT"], fetch_one, max_workers=2)

    def test_helper_catch_parameter_narrows_capture(self):
        def fetch_one(symbol):
            raise KeyError(symbol)

        with pytest.raises(KeyError):
            base._fetch_symbols_concurrently(["A"], fetch_one, max_workers=1, catch=(OSError,))

    def test_parallel_read_matches_sequential(self, monkeypatch):
        symbols = [f"SYM{i}" for i in range(40)]
        call_log, lock = [], threading.Lock()
        patch_session_get(monkeypatch, _price_handler(call_log, lock))

        sequential = _ConcurrentDailyReader(symbols, max_workers=1).read()
        sequential_threads = {thread for thread, _ in call_log}
        call_log.clear()

        parallel = _ConcurrentDailyReader(symbols, max_workers=8).read()

        pd.testing.assert_frame_equal(parallel, sequential)
        assert sorted(symbol for _, symbol in call_log) == sorted(symbols)
        assert len({thread for thread, _ in call_log}) > 1
        assert len(sequential_threads) == 1

    def test_mixed_failures_warn_once_per_symbol_from_main_thread(self, monkeypatch):
        call_log, lock = [], threading.Lock()
        patch_session_get(monkeypatch, _price_handler(call_log, lock))

        with pytest.warns(base.SymbolWarning) as caught:
            wide = _ConcurrentDailyReader(["SYM1", "BAD1", "SYM2", "BAD2"], max_workers=4).read()

        messages = sorted(str(warning.message) for warning in caught)
        assert messages == [
            "Failed to read symbol: 'BAD1', replacing with NaN.",
            "Failed to read symbol: 'BAD2', replacing with NaN.",
        ]
        assert wide["Close"]["BAD1"].isna().all()
        assert wide["Close"]["SYM2"].notna().all()

    def test_all_failed_raises_remote_data_error(self, monkeypatch):
        call_log, lock = [], threading.Lock()
        patch_session_get(monkeypatch, _price_handler(call_log, lock))
        with pytest.raises(base.RemoteDataError), pytest.warns(base.SymbolWarning):
            _ConcurrentDailyReader(["BAD1", "BAD2"], max_workers=2).read()
