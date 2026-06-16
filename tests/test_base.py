import datetime as dt

import pytest
import requests

from pandas_datareader import base as base
from pandas_datareader._utils import (
    DEFAULT_USER_AGENT,
    RETRYABLE_STATUS_CODES,
    RemoteDataError,
    _init_session,
)

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
