import datetime as dt
from importlib.metadata import PackageNotFoundError, version

from pandas import Timestamp, to_datetime
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from pandas_datareader.compat import is_number

try:
    DEFAULT_USER_AGENT = f"pandas-datareader/{version('pandas-datareader')}"
except PackageNotFoundError:  # pragma: no cover
    DEFAULT_USER_AGENT = "pandas-datareader"

# Transient statuses worth retrying. Other 4xx (e.g. 404) won't recover, so they fall straight
# through to the caller. 429 and 503 carry a ``Retry-After`` that the Retry strategy honors.
RETRYABLE_STATUS_CODES = (413, 429, 500, 502, 503, 504)


class SymbolWarning(UserWarning):
    pass


class RemoteDataError(IOError):
    pass


def _sanitize_dates(
    start: str | int | dt.date | dt.datetime | Timestamp,
    end: str | int | dt.date | dt.datetime | Timestamp,
) -> tuple[Timestamp, Timestamp]:
    """
    Return (timestamp_start, timestamp_end) tuple.

    If start is None, default is 5 years before the current date. If end is None, default is today.

    Parameters
    ----------
    start : str, int, date, datetime, or Timestamp
        Desired start date.
    end : str, int, date, datetime, or Timestamp
        Desired end date.

    Returns
    -------
    start : Timestamp
        Sanitized start date.
    end : Timestamp
        Sanitized end date.
    """
    if is_number(start):
        # regard int as year
        start = dt.datetime(start, 1, 1)

    if is_number(end):
        end = dt.datetime(end, 1, 1)

    if start is None:
        # default to 5 years before today
        today = dt.date.today()
        start = today - dt.timedelta(days=365 * 5)
    if end is None:
        # default to today
        end = dt.date.today()
    try:
        start = to_datetime(start)
        end = to_datetime(end)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid date format.") from exc
    if start > end:
        raise ValueError("start must be an earlier date than end")
    return start, end


def _init_session(
    session: requests.Session | None,
    retry_count: int = 3,
    pause: float = 0.1,
    headers: dict | None = None,
) -> requests.Session:
    """
    Initialize a requests session with a retry strategy.

    Mount an :class:`~urllib3.util.Retry`-backed adapter so urllib3 handles retry counting,
    exponential backoff, and ``Retry-After`` for transient failures. ``raise_on_status`` is left
    off so the exhausted response flows back to :meth:`~pandas_datareader.base._BaseReader._get_response`,
    which raises a ``RemoteDataError`` carrying the response body.

    Parameters
    ----------
    session : Session or None
        ``requests.sessions.Session`` instance to be used, or ``None`` to create a new session.
    retry_count : int, optional
        Maximum number of retries for transient failures. Default 3.
    pause : float, optional
        Backoff factor, in seconds, between retries. The nth retry waits ``pause * 2 ** (n - 1)``
        seconds. Default 0.1.
    headers : dict, optional
        Headers to apply to the session, taking precedence over the defaults.

    Returns
    -------
    session : Session
        The initialized session.
    """
    if session is None:
        session = requests.Session()
        # Identify ourselves so hosts can throttle politely rather than blocking the anonymous
        # ``python-requests`` agent that requests sets by default.
        session.headers["User-Agent"] = DEFAULT_USER_AGENT
    elif not isinstance(session, requests.Session):
        raise TypeError("session must be a request.Session")

    if headers:
        session.headers.update(headers)

    retry = Retry(
        total=retry_count,
        backoff_factor=pause,
        status_forcelist=RETRYABLE_STATUS_CODES,
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session
