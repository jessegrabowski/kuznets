import datetime as dt

from pandas import Timestamp, to_datetime
import requests

from pandas_datareader.compat import is_number


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


def _init_session(session: requests.Session | None) -> requests.Session:
    """
    Initialize a requests session.

    Parameters
    ----------
    session : Session or None
        ``requests.sessions.Session`` instance to be used, or ``None`` to create a new session.

    Returns
    -------
    session : Session
        The initialized session.
    """
    if session is None:
        session = requests.Session()
        # do not set requests max_retries here to support arbitrary pause
    else:
        if not isinstance(session, requests.Session):
            raise TypeError("session must be a request.Session")
    return session
