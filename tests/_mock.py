import contextlib
import json as _json
import os
from pathlib import Path

import pytest
import requests

# When set, ``network``-marked tests fetch from the live service and overwrite their fixture files
# with the real response, instead of asserting against the stored copy. The weekly refresh workflow
# (and ``RECORD=1 pytest -m network`` locally) drives this; the default offline suite never does.
RECORD = os.environ.get("RECORD", "").lower() in {"1", "true", "yes"}


class FakeResponse:
    """Minimal stand-in for :class:`requests.Response` for offline tests.

    Carries a captured body and status so reader parsing logic runs unchanged against canned data
    instead of a live service.
    """

    def __init__(
        self,
        content: bytes = b"",
        *,
        status_code: int = 200,
        encoding: str = "utf-8",
        headers: dict | None = None,
    ) -> None:
        self._content = content
        self.status_code = status_code
        self.encoding = encoding
        self.headers = headers or {}

    @property
    def content(self) -> bytes:
        return self._content

    @property
    def text(self) -> str:
        return self._content.decode(self.encoding)

    @property
    def ok(self) -> bool:
        return self.status_code == requests.codes.ok

    def json(self):
        return _json.loads(self._content)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} for fake response")


def make_response(
    content: bytes | str = b"",
    *,
    json: object = None,
    status_code: int = 200,
    encoding: str = "utf-8",
    headers: dict | None = None,
) -> FakeResponse:
    """Build a :class:`FakeResponse` from raw bytes/str or a JSON-serializable object.

    Parameters
    ----------
    content : bytes or str
        Response body. Ignored when ``json`` is given.
    json : object, optional
        Object serialized to the body with :func:`json.dumps`.
    status_code : int
        HTTP status. Default 200.
    encoding : str
        Body encoding. Default ``'utf-8'``.
    headers : dict, optional
        Response headers.

    Returns
    -------
    response : FakeResponse
    """
    if json is not None:
        content = _json.dumps(json)
    if isinstance(content, str):
        content = content.encode(encoding)
    return FakeResponse(content, status_code=status_code, encoding=encoding, headers=headers)


def _load(value, encoding: str) -> FakeResponse:
    """Coerce a fixture-map value into a :class:`FakeResponse`."""
    if isinstance(value, FakeResponse):
        return value
    if isinstance(value, str | Path):
        return FakeResponse(Path(value).read_bytes(), encoding=encoding)
    if isinstance(value, bytes):
        return FakeResponse(value, encoding=encoding)
    raise TypeError(f"Unsupported fixture value: {value!r}")


def from_fixtures(mapping: dict, *, encoding: str = "utf-8"):
    """Build a session-get handler that dispatches by URL substring.

    Parameters
    ----------
    mapping : dict mapping str to value
        Keys are matched as substrings of the requested URL, in insertion order. Values are a
        :class:`FakeResponse`, a path to a fixture file, raw ``bytes``, or a callable
        ``(url, params) -> FakeResponse``.
    encoding : str
        Encoding used when a value is loaded from a path or bytes. Default ``'utf-8'``.

    Returns
    -------
    handler : callable
        ``handler(url, params=None, **kwargs) -> FakeResponse``. Raises ``AssertionError`` on a URL
        that matches no key, so a test can never silently fall through to the real network.
    """

    def handler(url, params=None, **kwargs):
        for key, value in mapping.items():
            if key in url:
                if callable(value) and not isinstance(value, FakeResponse):
                    return value(url, params)
                return _load(value, encoding)
        raise AssertionError(f"Unmapped URL in offline test: {url!r}\nKnown keys: {list(mapping)}")

    return handler


def patch_session_get(monkeypatch, handler, *, record: bool = False) -> None:
    """Replace ``requests.Session.get`` with *handler* for the duration of a test.

    Patching the unbound method covers every session instance, including those built in
    :func:`pandas_datareader._utils._init_session` and the Yahoo crumb/cookie helpers.

    Parameters
    ----------
    monkeypatch : MonkeyPatch
        The pytest ``monkeypatch`` fixture.
    handler : callable or dict or FakeResponse
        ``handler(url, params=None, **kwargs) -> FakeResponse``. A plain :class:`FakeResponse` or a
        dict (forwarded to :func:`from_fixtures`) is also accepted for convenience.
    record : bool
        When True, *handler* must be a dict mapping URL substrings to fixture paths. The real
        ``requests.Session.get`` is called and, for any request whose URL matches a mapped path, the
        live response body overwrites that fixture file. Requests that match no mapped path (e.g. the
        Yahoo crumb handshake) pass through without being saved. Default False.
    """
    if record:
        if not isinstance(handler, dict):
            raise TypeError("record=True requires a dict mapping URL substrings to fixture paths")
        original = requests.Session.get
        mapping = handler

        def recording_get(self, url, params=None, **kwargs):
            response = original(self, url, params=params, **kwargs)
            # Never overwrite a good fixture with an error page from a transient failure.
            if response.status_code != requests.codes.ok:
                return response
            for key, value in mapping.items():
                if key in url and isinstance(value, str | Path):
                    path = Path(value)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(response.content)
                    break
            return response

        monkeypatch.setattr(requests.Session, "get", recording_get)
        return

    if isinstance(handler, FakeResponse):
        response = handler
        handler = lambda url, params=None, **kwargs: response  # noqa: E731
    elif isinstance(handler, dict):
        handler = from_fixtures(handler)

    def fake_get(self, url, params=None, **kwargs):
        return handler(url, params=params, **kwargs)

    monkeypatch.setattr(requests.Session, "get", fake_get)


@contextlib.contextmanager
def tolerate_outage():
    """Skip (not fail) a ``network`` test only when the service is genuinely unreachable.

    Only connection failures and timeouts are turned into skips. A reader-level error such as
    :class:`RemoteDataError` (a moved endpoint returning 404) or ``OSError`` ("returned no data")
    signals real API drift and is left to fail — that is the whole point of the live suite. Wrap the
    reader call and its assertions together.
    """
    try:
        yield
    except (requests.ConnectionError, requests.Timeout) as exc:
        pytest.skip(f"live service unreachable: {exc}")


def live_or_record(monkeypatch, mapping: dict, ping_url: str) -> None:
    """Prepare a ``network``-marked test to run against the live service.

    Under ``RECORD`` the live response bodies are written back to the fixtures in *mapping*. Outside
    record mode the test runs directly against the live service and is skipped when *ping_url* is
    unreachable, so the assertions act as an API-shape drift detector.

    Parameters
    ----------
    monkeypatch : MonkeyPatch
        The pytest ``monkeypatch`` fixture.
    mapping : dict mapping str to path
        URL-substring to fixture-path map, used only when recording.
    ping_url : str
        Endpoint probed to decide whether to skip when not recording.
    """
    if RECORD:
        patch_session_get(monkeypatch, mapping, record=True)
    elif not service_up(ping_url):
        pytest.skip(f"{ping_url} unreachable")


def service_up(url: str, timeout: float = 5.0) -> bool:
    """Report whether *url* is reachable, for ``network``-marked liveness tests.

    Returns ``False`` on any connection error, timeout, or 5xx so liveness tests skip rather than
    fail when a third-party service is down.

    Parameters
    ----------
    url : str
        Endpoint to probe.
    timeout : float
        Per-request timeout in seconds. Default 5.0.

    Returns
    -------
    reachable : bool
    """
    try:
        resp = requests.get(url, timeout=timeout, stream=True)
        resp.close()
        return resp.status_code < 500
    except requests.RequestException:
        return False
